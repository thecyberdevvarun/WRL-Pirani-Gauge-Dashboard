import time
import math
import logging
import threading
from pymodbus.client.sync import ModbusTcpClient
from db import create_test_header, close_test_header, log_reading
from register_maps import REGISTER_MAPS, DEFAULT_REGISTER_MAP

logger = logging.getLogger(__name__)


# Condition 1 of the test stop logic: a test always stops after this many
# minutes if Condition 2 (IN/OUT gauge cycle, see app.py's
# auto_stop_cycle_gauge) hasn't already stopped it first. No longer
# per-recipe configurable — every test uses this fixed cap.
MAX_DURATION_MIN = 60

# Maps (line_key, slave_id) -> {"event": Event, "manual": bool, ...} for
# currently-running tests. The key includes the line because slave IDs are the
# gauge numbers *within* a line, so "gauge 1" exists on every line.
# "manual" distinguishes an operator-requested abort (forces final_status to
# ABORTED) from the automatic IN/OUT-cycle stop (lets the result of the last
# valid reading stand, same as a normal timeout completion).
STOP_FLAGS: dict[tuple, dict] = {}
_STOP_LOCK = threading.Lock()


def stop_test(line_key: str, slave_id: int, manual: bool = True) -> bool:
    """Signal the running test on (line_key, slave_id) to stop. Returns True if a test was running.

    manual=True (operator "Stop Test" button): always takes effect immediately
    and forces final result to ABORTED — this overrides any pending deferred
    auto-stop below.

    manual=False (automatic IN/OUT-cycle trigger): final result is the result
    of the last valid reading (PASS/FAIL), same as a normal timeout.
    If the test hasn't yet run for its line's configured minimum duration,
    the stop is deferred (via a background timer) until that minimum is
    reached instead of cutting the test short right away; if the minimum has
    already elapsed, it stops immediately like before.
    """
    flag_key = (line_key, slave_id)
    with _STOP_LOCK:
        entry = STOP_FLAGS.get(flag_key)
        if not entry:
            return False

        if manual:
            entry["manual"] = True
            timer = entry.pop("deferred_timer", None)
            if timer:
                timer.cancel()
            entry["event"].set()
            return True

        # manual=False: automatic IN/OUT-cycle stop request.
        if entry.get("deferred_timer") is not None:
            return True  # already scheduled; nothing new to do

        elapsed = time.time() - entry["start_time"]
        remaining = entry["min_duration_sec"] - elapsed
        if remaining <= 0:
            entry["manual"] = False
            entry["event"].set()
            return True

        stop_event = entry["event"]

        def _fire(this_entry=entry, this_event=stop_event):
            with _STOP_LOCK:
                if STOP_FLAGS.get(flag_key) is this_entry:
                    this_entry["manual"] = False
            this_event.set()
            logger.info(
                "%s gauge %s: minimum test duration reached — applying deferred "
                "IN/OUT auto-stop",
                line_key,
                slave_id,
            )

        t = threading.Timer(remaining, _fire)
        t.daemon = True
        entry["deferred_timer"] = t
        t.start()
        logger.info(
            "%s gauge %s: IN/OUT auto-stop requested at %.1fs elapsed (line's "
            "minimum test duration is %ss) — deferring stop by %.1fs",
            line_key,
            slave_id,
            elapsed,
            entry["min_duration_sec"],
            remaining,
        )
        return True


def get_active_tests(line_key: str):
    """Return a sorted list of gauge IDs with a test running on this line."""
    with _STOP_LOCK:
        return sorted(sid for (lk, sid) in STOP_FLAGS if lk == line_key)


def run_test(
    serial_no,
    model_code,
    model_name,
    line_name,
    slave_id,
    host,
    port,
    upper_limit,
    poll_interval_sec,
    reading_delay_sec=0,
    min_duration_sec=0,
    register_map="pirani_default",
):
    """Start a vacuum leak test. Returns immediately; test runs in background thread.

    Every value here is already resolved by the caller (app.py) — from the
    line's .env configuration (host/port, upper_limit, poll_interval_sec,
    reading_delay_sec, min_duration_sec), and the external Material lookup
    (model_name). No recipe/DB lookup happens in here anymore.

    line_name is the line's key (e.g. "CHOCOLATE"). It is stored on the test
    header and, together with slave_id, identifies the gauge: slave IDs repeat
    across lines.

    upper_limit: single common pass/fail ceiling (no lower bound). The test's
    overall result is decided by the last valid reading only.
    reading_delay_sec: settle time after connecting before readings start
    counting toward PASS/FAIL (e.g. letting the vacuum stabilize right after
    a test begins). Comes out of the overall MAX_DURATION_MIN window rather
    than extending it.
    min_duration_sec: floor on how soon the automatic IN/OUT-cycle stop can
    end this test (0 = no floor) — see stop_test(). Never applies to a
    manual Stop.
    """
    reg_map = REGISTER_MAPS.get(register_map, DEFAULT_REGISTER_MAP)


    duration_min = MAX_DURATION_MIN
    poll_sec = poll_interval_sec
    test_id = create_test_header(
        serial_no, model_code, model_name, line_name, slave_id, upper_limit
    )

    stop_event = threading.Event()
    flag_key = (line_name, slave_id)
    with _STOP_LOCK:
        STOP_FLAGS[flag_key] = {
            "event": stop_event,
            "manual": True,
            "start_time": time.time(),
            "min_duration_sec": min_duration_sec,
            "deferred_timer": None,
        }

    def _execute():
        final_status = "PASS"
        valid_readings = 0  # readings actually logged; failed reads are skipped
        end_time = time.time() + (duration_min * 60)
        client = None

        try:
            client = ModbusTcpClient(host=host, port=port, timeout=5)

            if not client.connect():
                logger.error("%s gauge %s: Modbus gateway unreachable", line_name, slave_id)
                close_test_header(test_id, "ERROR")
                return

            logger.info(
                "Test started: line=%s gauge=%s  serial=%s  model=%s  duration=%smin",
                line_name,
                slave_id,
                serial_no,
                model_code,
                duration_min,
            )

            if reading_delay_sec > 0:
                logger.info(
                    "%s gauge %s: reading startup delay %ss before logging begins",
                    line_name,
                    slave_id,
                    reading_delay_sec,
                )
                stop_event.wait(reading_delay_sec)

            while time.time() < end_time and not stop_event.is_set():
                try:
                    rr = client.read_holding_registers(
                        address=reg_map.address, count=reg_map.count, unit=slave_id
                    )

                    if rr and not rr.isError():
                        vacuum = rr.registers[reg_map.value_index] / reg_map.scale

                        if math.isfinite(vacuum):
                            reading_ok = vacuum <= upper_limit
                            # Overall result follows the LAST valid reading
                            # only: an earlier FAIL is overwritten by a later
                            # PASS, and a late FAIL fails the whole test.
                            final_status = "PASS" if reading_ok else "FAIL"
                            log_reading(
                                test_id, vacuum, "PASS" if reading_ok else "FAIL"
                            )
                            valid_readings += 1
                        else:
                            logger.warning(
                                "%s gauge %s: invalid reading skipped", line_name, slave_id
                            )
                    else:
                        logger.warning(
                            "%s gauge %s: no reading from gauge, skipped", line_name, slave_id
                        )

                except Exception as ex:
                    logger.warning("%s gauge %s read error, skipped: %s", line_name, slave_id, ex)

                stop_event.wait(poll_sec)

            if stop_event.is_set():
                with _STOP_LOCK:
                    manual = STOP_FLAGS.get(flag_key, {}).get("manual", True)
                if manual:
                    final_status = "ABORTED"
                    logger.info("Test aborted by operator: line=%s gauge=%s", line_name, slave_id)
                else:
                    logger.info(
                        "Test auto-completed by IN/OUT cycle: line=%s gauge=%s result=%s",
                        line_name,
                        slave_id,
                        final_status,
                    )

            # No valid reading at all (gauge offline/unreadable) must not
            # be reported as PASS.
            if final_status == "PASS" and valid_readings == 0:
                logger.error("%s gauge %s: no valid readings during test", line_name, slave_id)
                final_status = "ERROR"

        except Exception as e:
            logger.error("Test fatal error on %s gauge %s: %s", line_name, slave_id, e)
            final_status = "ERROR"

        finally:
            try:
                if client:
                    client.close()
            except Exception:
                pass
            with _STOP_LOCK:
                popped = STOP_FLAGS.pop(flag_key, None)
                timer = popped.get("deferred_timer") if popped else None
            if timer:
                timer.cancel()
            close_test_header(test_id, final_status)
            logger.info("Test complete: line=%s gauge=%s  result=%s", line_name, slave_id, final_status)

    threading.Thread(target=_execute, daemon=True, name=f"test-{line_name}-g{slave_id}").start()

    return {
        "status": "STARTED",
        "test_id": str(test_id),
        "message": f"Test started on Gauge {slave_id}",
    }
