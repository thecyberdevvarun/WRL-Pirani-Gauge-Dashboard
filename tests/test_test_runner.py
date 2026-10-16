import threading
import time

import test_runner as tr


class _FakeReadResult:
    def __init__(self, value):
        self.registers = [0, int(value * 1000)]

    def isError(self):
        return False


class _FakeModbusClient:
    """Always returns a fixed reading (0.5) regardless of address/unit."""

    def __init__(self, host, port, timeout=5):
        pass

    def connect(self):
        return True

    def read_holding_registers(self, address, count, unit):
        return _FakeReadResult(0.5)

    def close(self):
        pass


def test_reading_delay_blocks_first_log(monkeypatch):
    """reading_delay_sec must delay the first logged reading by roughly that
    many seconds, without needing a real Modbus gateway or database."""
    events = []
    finished = threading.Event()

    monkeypatch.setattr(tr, "ModbusTcpClient", _FakeModbusClient)
    monkeypatch.setattr(tr, "create_test_header", lambda *a, **k: "fake-test-id")
    monkeypatch.setattr(tr, "log_reading", lambda *a, **k: events.append(time.time()))
    monkeypatch.setattr(tr, "close_test_header", lambda *a, **k: finished.set())

    start = time.time()
    result = tr.run_test(
        "S1", "M1", "Model 1", "LINE", 42, "10.0.0.1", 502,
        upper_limit=1.0, poll_interval_sec=1, reading_delay_sec=1,
    )
    assert result["status"] == "STARTED"

    try:
        deadline = time.time() + 5
        while not events and time.time() < deadline:
            time.sleep(0.05)

        assert events, "expected at least one log_reading call before the deadline"
        assert events[0] - start >= 0.9  # ~1s delay, small slack for scheduling
    finally:
        tr.stop_test("LINE", 42, manual=True)
        # Let the background thread finish while this test's patches are still
        # active, so it can't call into the next test's patched functions.
        assert finished.wait(3)


def test_zero_reading_delay_logs_immediately(monkeypatch):
    """reading_delay_sec=0 (the default) should not introduce any wait."""
    events = []
    finished = threading.Event()

    monkeypatch.setattr(tr, "ModbusTcpClient", _FakeModbusClient)
    monkeypatch.setattr(tr, "create_test_header", lambda *a, **k: "fake-test-id")
    monkeypatch.setattr(tr, "log_reading", lambda *a, **k: events.append(time.time()))
    monkeypatch.setattr(tr, "close_test_header", lambda *a, **k: finished.set())

    start = time.time()
    result = tr.run_test(
        "S2", "M1", "Model 1", "LINE", 43, "10.0.0.1", 502,
        upper_limit=1.0, poll_interval_sec=1,
    )
    assert result["status"] == "STARTED"

    try:
        deadline = time.time() + 3
        while not events and time.time() < deadline:
            time.sleep(0.05)

        assert events, "expected at least one log_reading call before the deadline"
        assert events[0] - start < 0.5
    finally:
        tr.stop_test("LINE", 43, manual=True)
        assert finished.wait(3)


def _run_to_one_reading_then_stop(monkeypatch, slave_id, upper_limit):
    """Starts a test (fixed 0.5 reading via _FakeModbusClient), waits for at
    least one reading to be logged, then stops it non-manually (so the
    naturally-accumulated PASS/FAIL stands instead of being forced to
    ABORTED) and waits for close_test_header to be called. Returns the
    final_result it was closed with."""
    logged = []
    closed = {}

    monkeypatch.setattr(tr, "ModbusTcpClient", _FakeModbusClient)
    monkeypatch.setattr(tr, "create_test_header", lambda *a, **k: "fake-test-id")
    monkeypatch.setattr(tr, "log_reading", lambda *a, **k: logged.append(1))
    monkeypatch.setattr(tr, "close_test_header", lambda test_id, result: closed.update(result=result))

    result = tr.run_test(
        "S", "M1", "Model 1", "LINE", slave_id, "10.0.0.1", 502,
        upper_limit=upper_limit, poll_interval_sec=1,
    )
    assert result["status"] == "STARTED"

    deadline = time.time() + 3
    while not logged and time.time() < deadline:
        time.sleep(0.05)
    assert logged, "expected at least one reading before stopping"

    tr.stop_test("LINE", slave_id, manual=False)

    deadline = time.time() + 2
    while "result" not in closed and time.time() < deadline:
        time.sleep(0.05)

    return closed.get("result")


def test_reading_at_or_below_upper_limit_passes(monkeypatch):
    """No lower bound at all anymore — a reading exactly at (or below) the
    single common Upper Limit is a PASS. Fixed reading is 0.5."""
    assert _run_to_one_reading_then_stop(monkeypatch, slave_id=44, upper_limit=0.5) == "PASS"


def test_reading_above_upper_limit_fails(monkeypatch):
    """A reading above the single common Upper Limit is a FAIL — the fixed
    reading (0.5) exceeds a deliberately low Upper Limit (0.1)."""
    assert _run_to_one_reading_then_stop(monkeypatch, slave_id=45, upper_limit=0.1) == "FAIL"


def test_auto_stop_deferred_until_min_duration(monkeypatch):
    """An automatic (manual=False) IN/OUT-cycle stop request arriving before
    the line's configured minimum test duration must not end the test right
    away — it should be deferred until that minimum is reached."""
    closed = {}

    monkeypatch.setattr(tr, "ModbusTcpClient", _FakeModbusClient)
    monkeypatch.setattr(tr, "create_test_header", lambda *a, **k: "fake-test-id")
    monkeypatch.setattr(tr, "log_reading", lambda *a, **k: None)
    monkeypatch.setattr(
        tr, "close_test_header",
        lambda test_id, result: closed.update(result=result, t=time.time()),
    )

    start = time.time()
    result = tr.run_test(
        "S", "M1", "Model 1", "LINE", 46, "10.0.0.1", 502,
        upper_limit=1.0, poll_interval_sec=1, min_duration_sec=1,
    )
    assert result["status"] == "STARTED"

    # Request an auto-stop almost immediately — well before min_duration_sec.
    tr.stop_test("LINE", 46, manual=False)

    time.sleep(0.4)
    assert "result" not in closed, "auto-stop should have been deferred, not applied immediately"

    deadline = time.time() + 3
    while "result" not in closed and time.time() < deadline:
        time.sleep(0.05)

    assert closed.get("result") == "PASS"
    assert closed["t"] - start >= 0.8  # deferred roughly until min_duration_sec elapsed


def test_manual_stop_overrides_min_duration(monkeypatch):
    """A manual Stop always takes effect immediately and forces ABORTED,
    even if the line's minimum test duration hasn't elapsed yet."""
    closed = {}

    monkeypatch.setattr(tr, "ModbusTcpClient", _FakeModbusClient)
    monkeypatch.setattr(tr, "create_test_header", lambda *a, **k: "fake-test-id")
    monkeypatch.setattr(tr, "log_reading", lambda *a, **k: None)
    monkeypatch.setattr(tr, "close_test_header", lambda test_id, result: closed.update(result=result))

    result = tr.run_test(
        "S", "M1", "Model 1", "LINE", 47, "10.0.0.1", 502,
        upper_limit=1.0, poll_interval_sec=5, min_duration_sec=600,
    )
    assert result["status"] == "STARTED"

    start = time.time()
    tr.stop_test("LINE", 47, manual=True)

    deadline = time.time() + 2
    while "result" not in closed and time.time() < deadline:
        time.sleep(0.02)

    assert closed.get("result") == "ABORTED"
    assert time.time() - start < 1.5  # must not wait anywhere near the 600s min duration


def test_same_gauge_number_on_two_lines_does_not_collide(monkeypatch):
    """Slave IDs are the gauge number *within* a line, so gauge 1 exists on
    every line. Running gauge 1 on two lines at once must give two independent
    tests: stopping one must leave the other running, and active-test lists
    are per line."""
    closed = {}

    monkeypatch.setattr(tr, "ModbusTcpClient", _FakeModbusClient)
    monkeypatch.setattr(tr, "create_test_header", lambda serial, model, name, line, gauge, ul: f"{line}-{gauge}")
    monkeypatch.setattr(tr, "log_reading", lambda *a, **k: None)
    monkeypatch.setattr(tr, "close_test_header", lambda test_id, result: closed.update({test_id: result}))

    for line in ("COLLIDE_A", "COLLIDE_B"):
        res = tr.run_test("S", "M1", "Model", line, 1, "10.0.0.1", 502, upper_limit=1.0, poll_interval_sec=5)
        assert res["status"] == "STARTED"

    try:
        assert tr.get_active_tests("COLLIDE_A") == [1]
        assert tr.get_active_tests("COLLIDE_B") == [1]

        # Stopping gauge 1 on line A must not touch gauge 1 on line B.
        assert tr.stop_test("COLLIDE_A", 1, manual=True) is True
        deadline = time.time() + 2
        while "COLLIDE_A-1" not in closed and time.time() < deadline:
            time.sleep(0.02)

        assert closed.get("COLLIDE_A-1") == "ABORTED"
        assert "COLLIDE_B-1" not in closed
        assert tr.get_active_tests("COLLIDE_A") == []
        assert tr.get_active_tests("COLLIDE_B") == [1]

        # A line with nothing running reports nothing, and can't stop another line's gauge.
        assert tr.stop_test("COLLIDE_C", 1, manual=True) is False
    finally:
        tr.stop_test("COLLIDE_B", 1, manual=True)
        deadline = time.time() + 2
        while "COLLIDE_B-1" not in closed and time.time() < deadline:
            time.sleep(0.02)
