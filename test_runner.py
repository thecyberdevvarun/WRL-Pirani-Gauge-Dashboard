import time
import math
import logging
import threading
from pymodbus.client.sync import ModbusTcpClient
from db import create_test_header, close_test_header, log_reading

logger = logging.getLogger(__name__)


# Condition 1 of the test stop logic: a test always stops after this many
# minutes if Condition 2 (IN/OUT gauge cycle, see app.py's
# auto_stop_cycle_gauge) hasn't already stopped it first. No longer
# per-recipe configurable — every test uses this fixed cap.
MAX_DURATION_MIN = 60
MODBUS_REGISTER  = 3

# Maps slave_id -> {"event": Event, "manual": bool} for currently-running tests.
# "manual" distinguishes an operator-requested abort (forces final_status to
# ABORTED) from the automatic IN/OUT-cycle stop (lets the naturally
# accumulated PASS/FAIL stand, same as a normal timeout completion).
STOP_FLAGS: dict[int, dict] = {}
_STOP_LOCK = threading.Lock()


def stop_test(slave_id: int, manual: bool = True) -> bool:
    """Signal the running test on slave_id to stop. Returns True if a test was running.

    manual=True (operator "Stop Test" button): always takes effect immediately
    and forces final result to ABORTED — this overrides any pending deferred
    auto-stop below.

    manual=False (automatic IN/OUT-cycle trigger): final result is whatever the
    test naturally accumulated so far (PASS/FAIL), same as a normal timeout.
    If the test hasn't yet run for its line's configured minimum duration,
    the stop is deferred (via a background timer) until that minimum is
    reached instead of cutting the test short right away; if the minimum has
    already elapsed, it stops immediately like before.
    """
    with _STOP_LOCK:
        entry = STOP_FLAGS.get(slave_id)
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
                if STOP_FLAGS.get(slave_id) is this_entry:
                    this_entry["manual"] = False
            this_event.set()
            logger.info(
                "Gauge %s: minimum test duration reached — applying deferred "
                "IN/OUT auto-stop", slave_id,
            )

        t = threading.Timer(remaining, _fire)
        t.daemon = True
        entry["deferred_timer"] = t
        t.start()
        logger.info(
            "Gauge %s: IN/OUT auto-stop requested at %.1fs elapsed (line's "
            "minimum test duration is %ss) — deferring stop by %.1fs",
            slave_id, elapsed, entry["min_duration_sec"], remaining,
        )
        return True


def get_active_tests():
    """Return a sorted list of currently active gauge IDs."""
    with _STOP_LOCK:
        return sorted(STOP_FLAGS.keys())


def run_test(serial_no, model_code, model_name, line_name, slave_id, host, port,
             upper_limit, poll_interval_sec, reading_delay_sec=0, min_duration_sec=0):
    """Start a vacuum leak test. Returns immediately; test runs in background thread.

    Every value here is already resolved by the caller (app.py) — from
    GAUGE_CONFIG (host/port), the line's Settings (upper_limit,
    poll_interval_sec, reading_delay_sec, min_duration_sec), and the external
    Material lookup (model_name). No recipe/DB lookup happens in here anymore.

    upper_limit: single common pass/fail ceiling (no lower bound).
    reading_delay_sec: settle time after connecting before readings start
    counting toward PASS/FAIL (e.g. letting the vacuum stabilize right after
    a test begins). Comes out of the overall MAX_DURATION_MIN window rather
    than extending it.
    min_duration_sec: floor on how soon the automatic IN/OUT-cycle stop can
    end this test (0 = no floor) — see stop_test(). Never applies to a
    manual Stop.
    """

    duration_min = MAX_DURATION_MIN
    poll_sec = poll_interval_sec
    test_id = create_test_header(serial_no, model_code, model_name, line_name, slave_id, upper_limit)

    stop_event = threading.Event()
    with _STOP_LOCK:
        STOP_FLAGS[slave_id] = {
            "event": stop_event,
            "manual": True,
            "start_time": time.time(),
            "min_duration_sec": min_duration_sec,
            "deferred_timer": None,
        }

    def _execute():
        final_status = "PASS"
        end_time = time.time() + (duration_min * 60)
        client = None

        try:
            client = ModbusTcpClient(
                host=host,
                port=port,
                timeout=5
            )

            if not client.connect():
                logger.error("Gauge %s: Modbus gateway unreachable", slave_id)
                close_test_header(test_id, "ERROR")
                return

            logger.info("Test started: gauge=%s  serial=%s  model=%s  duration=%smin",
                        slave_id, serial_no, model_code, duration_min)

            if reading_delay_sec > 0:
                logger.info(
                    "Gauge %s: reading startup delay %ss before logging begins",
                    slave_id, reading_delay_sec,
                )
                stop_event.wait(reading_delay_sec)

            while time.time() < end_time and not stop_event.is_set():
                try:
                    rr = client.read_holding_registers(
                        address=MODBUS_REGISTER, count=2, unit=slave_id
                    )

                    if rr and not rr.isError():
                        raw = rr.registers[1] / 1000
                        vacuum = raw if math.isfinite(raw) else None

                        if vacuum is None:
                            log_reading(test_id, None, "ERROR")
                        else:
                            reading_ok = vacuum <= upper_limit
                            if not reading_ok:
                                final_status = "FAIL"
                            log_reading(test_id, vacuum, "PASS" if reading_ok else "FAIL")
                    else:
                        log_reading(test_id, None, "ERROR")

                except Exception as ex:
                    logger.warning("Gauge %s read error: %s", slave_id, ex)
                    log_reading(test_id, None, "ERROR")

                stop_event.wait(poll_sec)

            if stop_event.is_set():
                with _STOP_LOCK:
                    manual = STOP_FLAGS.get(slave_id, {}).get("manual", True)
                if manual:
                    final_status = "ABORTED"
                    logger.info("Test aborted by operator: gauge=%s", slave_id)
                else:
                    logger.info(
                        "Test auto-completed by IN/OUT cycle: gauge=%s result=%s",
                        slave_id, final_status,
                    )

        except Exception as e:
            logger.error("Test fatal error on gauge %s: %s", slave_id, e)
            final_status = "ERROR"

        finally:
            try:
                if client:
                    client.close()
            except Exception:
                pass
            with _STOP_LOCK:
                popped = STOP_FLAGS.pop(slave_id, None)
                timer = popped.get("deferred_timer") if popped else None
            if timer:
                timer.cancel()
            close_test_header(test_id, final_status)
            logger.info("Test complete: gauge=%s  result=%s", slave_id, final_status)

    threading.Thread(target=_execute, daemon=True, name=f"test-g{slave_id}").start()

    return {
        "status": "STARTED",
        "test_id": str(test_id),
        "message": f"Test started on Gauge {slave_id}"
    }
