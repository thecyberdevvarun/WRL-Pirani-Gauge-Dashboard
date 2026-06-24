import time
import math
import logging
import threading
from pymodbus.client.sync import ModbusTcpClient
from config import MODBUS
from db import get_recipe, create_test_header, close_test_header, log_reading

logger = logging.getLogger(__name__)

MAX_DURATION_MIN = 480   # Safety cap: 8 hours
MODBUS_REGISTER  = 3

# Maps slave_id → stop Event for currently-running tests
STOP_FLAGS: dict[int, threading.Event] = {}
_STOP_LOCK = threading.Lock()


def stop_test(slave_id: int) -> bool:
    """Signal the running test on slave_id to abort. Returns True if a test was running."""
    with _STOP_LOCK:
        event = STOP_FLAGS.get(slave_id)
    if event:
        event.set()
        return True
    return False


def get_active_tests():
    """Return a sorted list of currently active gauge IDs."""
    with _STOP_LOCK:
        return sorted(STOP_FLAGS.keys())


def run_test(serial_no, model_code, line_name, slave_id):
    """Start a vacuum leak test. Returns immediately; test runs in background thread."""

    recipe = get_recipe(model_code)
    if not recipe:
        return {
            "status": "ERROR",
            "message": f"No recipe found for model code '{model_code}'"
        }

    _, model_name, ll, ul, duration_min, poll_sec = recipe
    duration_min = min(int(duration_min), MAX_DURATION_MIN)
    test_id = create_test_header(serial_no, model_code, model_name, line_name, slave_id)

    stop_event = threading.Event()
    with _STOP_LOCK:
        STOP_FLAGS[slave_id] = stop_event

    def _execute():
        final_status = "PASS"
        end_time = time.time() + (duration_min * 60)
        client = None

        try:
            client = ModbusTcpClient(
                host=MODBUS["HOST"],
                port=MODBUS["PORT"],
                timeout=5
            )

            if not client.connect():
                logger.error("Gauge %s: Modbus gateway unreachable", slave_id)
                close_test_header(test_id, "ERROR")
                return

            logger.info("Test started: gauge=%s  serial=%s  model=%s  duration=%smin",
                        slave_id, serial_no, model_code, duration_min)

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
                            reading_ok = ll <= vacuum <= ul
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
                final_status = "ABORTED"
                logger.info("Test aborted by operator: gauge=%s", slave_id)

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
                STOP_FLAGS.pop(slave_id, None)
            close_test_header(test_id, final_status)
            logger.info("Test complete: gauge=%s  result=%s", slave_id, final_status)

    threading.Thread(target=_execute, daemon=True, name=f"test-g{slave_id}").start()

    return {
        "status": "STARTED",
        "test_id": str(test_id),
        "message": f"Test started on Gauge {slave_id}"
    }
