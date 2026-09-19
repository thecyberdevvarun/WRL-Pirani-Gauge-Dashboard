import json
import pytest

import app as application
from app import app as flask_app


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client


def test_health_endpoint(client):
    # Prepare gauge config and modbus cache
    application.GAUGE_CONFIG.clear()
    application.GAUGE_CONFIG.update({
        1: {"name": "Pirani_1", "host": "127.0.0.1", "port": 502, "line_key": "DEFAULT", "enabled": True},
        2: {"name": "Pirani_2", "host": "127.0.0.1", "port": 502, "line_key": "DEFAULT", "enabled": True},
    })
    application.MODBUS_CACHE.clear()
    application.MODBUS_CACHE.update({1: 0.123, 2: None})

    rv = client.get("/api/health")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["gauges_polled"] == 2
    assert data["gauges_responding"] == 1
    assert data["gateways"] == ["127.0.0.1:502"]


def test_material_lookup_found(monkeypatch, client):
    monkeypatch.setattr(application, "get_material_name", lambda alt_name: "Deep Freezer 250L")

    rv = client.get("/api/material/2501")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["exists"] is True
    assert data["name"] == "Deep Freezer 250L"


def test_material_lookup_not_found(monkeypatch, client):
    monkeypatch.setattr(application, "get_material_name", lambda alt_name: None)

    rv = client.get("/api/material/NOSUCH")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["exists"] is False
    assert data["name"] is None


def test_start_test_and_stop(monkeypatch, client):
    # Patch the run_test and stop_test used by the app module
    def fake_run_test(serial_no, model_code, model_name, line_name, slave_id, host, port,
                       upper_limit, poll_interval_sec, reading_delay_sec=0, min_duration_sec=0):
        return {"status": "STARTED", "test_id": "fake-id", "message": "ok"}

    def fake_stop_test(gauge_id, manual=True):
        return True

    monkeypatch.setattr(application, "run_test", fake_run_test)
    monkeypatch.setattr(application, "stop_test", fake_stop_test)
    monkeypatch.setattr(application, "get_material_name", lambda code: None)

    application.GAUGE_CONFIG.clear()
    application.GAUGE_CONFIG.update({
        5: {"name": "Pirani_5", "host": "127.0.0.1", "port": 502, "line_key": "DEFAULT", "enabled": True},
    })
    application.LINE_GAP.clear()  # no IN/OUT auto-stop configured for this line

    # Valid start
    payload = {"serial_no": "S123", "model_code": "M1", "gauge_id": 5}
    rv = client.post("/start-test", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["status"] == "STARTED"

    # Unknown gauge id
    payload = {"serial_no": "S123", "model_code": "M1", "gauge_id": 999}
    rv = client.post("/start-test", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 404

    # Stop test route
    rv = client.post("/stop-test/5")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["status"] == "STOPPED"


def test_active_tests_route(monkeypatch, client):
    monkeypatch.setattr(application, "get_active_tests", lambda: [13, 22])

    rv = client.get("/api/active-tests")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["count"] == 2
    assert data["active_gauges"] == [13, 22]


def _fake_gauge_config_store():
    """A tiny in-memory stand-in for the pirani_gauge_config table."""
    store = {"rows": []}

    def get_rows():
        return list(store["rows"])

    def get_conflicts(line_key, slave_ids):
        return [
            (r["slave_id"], r["line_key"])
            for r in store["rows"]
            if r["slave_id"] in slave_ids and r["line_key"] != line_key
        ]

    def replace_line(line_key, line_label, hosts, gap=0, reading_delay_sec=0,
                      upper_limit=0, poll_interval_sec=60, min_duration_sec=600):
        store["rows"] = [r for r in store["rows"] if r["line_key"] != line_key]
        sort_order = 0
        for h in hosts:
            for g in h["gauges"]:
                store["rows"].append({
                    "id": sort_order + 1, "line_key": line_key, "line_label": line_label,
                    "host": h["host"], "port": h["port"], "gauge_name": g["name"],
                    "slave_id": g["slave_id"], "enabled": g["enabled"], "sort_order": sort_order,
                    "gap": gap, "reading_delay_sec": reading_delay_sec,
                    "upper_limit": upper_limit, "poll_interval_sec": poll_interval_sec,
                    "min_duration_sec": min_duration_sec,
                })
                sort_order += 1

    def delete_line(line_key):
        store["rows"] = [r for r in store["rows"] if r["line_key"] != line_key]

    return store, get_rows, get_conflicts, replace_line, delete_line


def test_save_and_get_line_settings(monkeypatch, client):
    store, get_rows, get_conflicts, replace_line, delete_line = _fake_gauge_config_store()
    monkeypatch.setattr(application, "get_gauge_config_rows", get_rows)
    monkeypatch.setattr(application, "get_conflicting_slave_ids", get_conflicts)
    monkeypatch.setattr(application, "replace_line_gauge_config", replace_line)
    monkeypatch.setattr(application, "delete_line_gauge_config", delete_line)
    monkeypatch.setattr(application, "reconcile_pollers", lambda: None)
    monkeypatch.setattr(application, "get_active_tests", lambda: [])

    payload = {
        "line_key": "VISI_COOLER",
        "line_label": "Visi Cooler",
        "gap": 5,
        "reading_delay_sec": 10,
        "upper_limit": 0.5,
        "poll_interval_sec": 90,
        "min_duration_sec": 120,
        "hosts": [
            {"host": "192.168.0.3", "port": 502, "gauges": [
                {"name": "Pirani_1", "slave_id": 1, "enabled": True},
                {"name": "Pirani_2", "slave_id": 2, "enabled": True},
            ]},
        ],
    }
    rv = client.post("/api/settings/lines", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 200

    rv = client.get("/api/settings/lines")
    assert rv.status_code == 200
    lines = rv.get_json()
    assert len(lines) == 1
    assert lines[0]["line_key"] == "VISI_COOLER"
    assert lines[0]["gap"] == 5
    assert lines[0]["reading_delay_sec"] == 10
    assert lines[0]["upper_limit"] == 0.5
    assert lines[0]["poll_interval_sec"] == 90
    assert lines[0]["min_duration_sec"] == 120
    assert len(lines[0]["hosts"]) == 1
    assert len(lines[0]["hosts"][0]["gauges"]) == 2
    assert application.GAUGE_CONFIG[1]["host"] == "192.168.0.3"
    assert application.LINE_GAP["VISI_COOLER"] == 5
    assert application.LINE_READING_DELAY["VISI_COOLER"] == 10
    assert application.LINE_UPPER_LIMIT["VISI_COOLER"] == 0.5
    assert application.LINE_POLL_INTERVAL["VISI_COOLER"] == 90
    assert application.LINE_MIN_DURATION["VISI_COOLER"] == 120
    assert application.LINE_GAUGE_ORDER["VISI_COOLER"] == [1, 2]


def test_save_line_settings_rejects_invalid_gap(monkeypatch, client):
    store, get_rows, get_conflicts, replace_line, delete_line = _fake_gauge_config_store()
    monkeypatch.setattr(application, "get_gauge_config_rows", get_rows)
    monkeypatch.setattr(application, "get_conflicting_slave_ids", get_conflicts)
    monkeypatch.setattr(application, "get_active_tests", lambda: [])

    payload = {
        "line_key": "VISI_COOLER",
        "line_label": "Visi Cooler",
        "gap": -1,
        "hosts": [{"host": "192.168.0.3", "port": 502, "gauges": [
            {"name": "Pirani_1", "slave_id": 1, "enabled": True},
        ]}],
    }
    rv = client.post("/api/settings/lines", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 400


def test_save_line_settings_rejects_invalid_upper_limit(monkeypatch, client):
    store, get_rows, get_conflicts, replace_line, delete_line = _fake_gauge_config_store()
    monkeypatch.setattr(application, "get_gauge_config_rows", get_rows)
    monkeypatch.setattr(application, "get_conflicting_slave_ids", get_conflicts)
    monkeypatch.setattr(application, "get_active_tests", lambda: [])

    payload = {
        "line_key": "VISI_COOLER",
        "line_label": "Visi Cooler",
        "upper_limit": -0.5,
        "hosts": [{"host": "192.168.0.3", "port": 502, "gauges": [
            {"name": "Pirani_1", "slave_id": 1, "enabled": True},
        ]}],
    }
    rv = client.post("/api/settings/lines", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 400


def test_save_line_settings_rejects_invalid_poll_interval(monkeypatch, client):
    store, get_rows, get_conflicts, replace_line, delete_line = _fake_gauge_config_store()
    monkeypatch.setattr(application, "get_gauge_config_rows", get_rows)
    monkeypatch.setattr(application, "get_conflicting_slave_ids", get_conflicts)
    monkeypatch.setattr(application, "get_active_tests", lambda: [])

    payload = {
        "line_key": "VISI_COOLER",
        "line_label": "Visi Cooler",
        "poll_interval_sec": 10,  # below the 60s floor
        "hosts": [{"host": "192.168.0.3", "port": 502, "gauges": [
            {"name": "Pirani_1", "slave_id": 1, "enabled": True},
        ]}],
    }
    rv = client.post("/api/settings/lines", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 400


def test_save_line_settings_rejects_invalid_min_duration(monkeypatch, client):
    store, get_rows, get_conflicts, replace_line, delete_line = _fake_gauge_config_store()
    monkeypatch.setattr(application, "get_gauge_config_rows", get_rows)
    monkeypatch.setattr(application, "get_conflicting_slave_ids", get_conflicts)
    monkeypatch.setattr(application, "get_active_tests", lambda: [])

    payload = {
        "line_key": "VISI_COOLER",
        "line_label": "Visi Cooler",
        "min_duration_sec": 4000,  # over the 3600s cap
        "hosts": [{"host": "192.168.0.3", "port": 502, "gauges": [
            {"name": "Pirani_1", "slave_id": 1, "enabled": True},
        ]}],
    }
    rv = client.post("/api/settings/lines", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 400


def test_save_line_settings_allows_min_duration_zero(monkeypatch, client):
    """0 is a legitimate, deliberate value (auto-stop floor disabled) — must
    not be silently coerced back to the 600s default."""
    store, get_rows, get_conflicts, replace_line, delete_line = _fake_gauge_config_store()
    monkeypatch.setattr(application, "get_gauge_config_rows", get_rows)
    monkeypatch.setattr(application, "get_conflicting_slave_ids", get_conflicts)
    monkeypatch.setattr(application, "replace_line_gauge_config", replace_line)
    monkeypatch.setattr(application, "reconcile_pollers", lambda: None)
    monkeypatch.setattr(application, "get_active_tests", lambda: [])

    payload = {
        "line_key": "VISI_COOLER",
        "line_label": "Visi Cooler",
        "min_duration_sec": 0,
        "hosts": [{"host": "192.168.0.3", "port": 502, "gauges": [
            {"name": "Pirani_1", "slave_id": 1, "enabled": True},
        ]}],
    }
    rv = client.post("/api/settings/lines", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 200

    rv = client.get("/api/settings/lines")
    assert rv.get_json()[0]["min_duration_sec"] == 0
    assert application.LINE_MIN_DURATION["VISI_COOLER"] == 0


def test_save_line_settings_conflict(monkeypatch, client):
    store, get_rows, get_conflicts, replace_line, delete_line = _fake_gauge_config_store()
    store["rows"] = [{
        "id": 1, "line_key": "OTHER_LINE", "line_label": "Other Line",
        "host": "192.168.0.9", "port": 502, "gauge_name": "Pirani_X",
        "slave_id": 1, "enabled": True, "sort_order": 0, "gap": 0, "reading_delay_sec": 0,
        "upper_limit": 0, "poll_interval_sec": 60, "min_duration_sec": 600,
    }]
    monkeypatch.setattr(application, "get_gauge_config_rows", get_rows)
    monkeypatch.setattr(application, "get_conflicting_slave_ids", get_conflicts)
    monkeypatch.setattr(application, "replace_line_gauge_config", replace_line)
    monkeypatch.setattr(application, "get_active_tests", lambda: [])

    payload = {
        "line_key": "VISI_COOLER",
        "line_label": "Visi Cooler",
        "hosts": [{"host": "192.168.0.3", "port": 502, "gauges": [
            {"name": "Pirani_1", "slave_id": 1, "enabled": True},
        ]}],
    }
    rv = client.post("/api/settings/lines", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 409


def test_save_line_settings_blocked_by_active_test(monkeypatch, client):
    store, get_rows, get_conflicts, replace_line, delete_line = _fake_gauge_config_store()
    store["rows"] = [{
        "id": 1, "line_key": "VISI_COOLER", "line_label": "Visi Cooler",
        "host": "192.168.0.3", "port": 502, "gauge_name": "Pirani_1",
        "slave_id": 1, "enabled": True, "sort_order": 0, "gap": 0, "reading_delay_sec": 0,
        "upper_limit": 0, "poll_interval_sec": 60, "min_duration_sec": 600,
    }]
    monkeypatch.setattr(application, "get_gauge_config_rows", get_rows)
    monkeypatch.setattr(application, "get_conflicting_slave_ids", get_conflicts)
    monkeypatch.setattr(application, "replace_line_gauge_config", replace_line)
    monkeypatch.setattr(application, "get_active_tests", lambda: [1])

    # Attempt to disable gauge 1, which has "an active test" per the fake above.
    payload = {
        "line_key": "VISI_COOLER",
        "line_label": "Visi Cooler",
        "hosts": [{"host": "192.168.0.3", "port": 502, "gauges": [
            {"name": "Pirani_1", "slave_id": 1, "enabled": False},
        ]}],
    }
    rv = client.post("/api/settings/lines", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 409


def test_delete_line_settings_blocked_by_active_test(monkeypatch, client):
    store, get_rows, get_conflicts, replace_line, delete_line = _fake_gauge_config_store()
    store["rows"] = [{
        "id": 1, "line_key": "VISI_COOLER", "line_label": "Visi Cooler",
        "host": "192.168.0.3", "port": 502, "gauge_name": "Pirani_1",
        "slave_id": 1, "enabled": True, "sort_order": 0, "gap": 0, "reading_delay_sec": 0,
        "upper_limit": 0, "poll_interval_sec": 60, "min_duration_sec": 600,
    }]
    monkeypatch.setattr(application, "get_gauge_config_rows", get_rows)
    monkeypatch.setattr(application, "delete_line_gauge_config", delete_line)
    monkeypatch.setattr(application, "get_active_tests", lambda: [1])

    rv = client.delete("/api/settings/lines/VISI_COOLER")
    assert rv.status_code == 409

    monkeypatch.setattr(application, "get_active_tests", lambda: [])
    monkeypatch.setattr(application, "reconcile_pollers", lambda: None)
    rv = client.delete("/api/settings/lines/VISI_COOLER")
    assert rv.status_code == 200
    assert get_rows() == []


def test_start_test_triggers_auto_stop_on_cycle_gauge(monkeypatch, client):
    """Scanning gauge 1 IN on a 5-gauge line with gap=2 should sweep-stop
    every gauge in the 2 positions immediately ahead of it (gauges 2 and 3,
    nearest first), not just the single gauge exactly gap-positions ahead —
    leaving each one's naturally-accumulated result rather than forcing
    ABORTED."""

    def fake_run_test(serial_no, model_code, model_name, line_name, slave_id, host, port,
                       upper_limit, poll_interval_sec, reading_delay_sec=0, min_duration_sec=0):
        return {"status": "STARTED", "test_id": "fake-id", "message": "ok"}

    stopped_calls = []

    def fake_stop_test(gauge_id, manual=True):
        stopped_calls.append((gauge_id, manual))
        return True

    monkeypatch.setattr(application, "run_test", fake_run_test)
    monkeypatch.setattr(application, "stop_test", fake_stop_test)
    monkeypatch.setattr(application, "get_material_name", lambda code: None)

    application.GAUGE_CONFIG.clear()
    application.GAUGE_CONFIG.update({
        sid: {"name": f"G{sid}", "host": "10.0.0.1", "port": 502, "line_key": "L", "enabled": True}
        for sid in [1, 2, 3, 4, 5]
    })
    application.LINE_GAP.clear()
    application.LINE_GAP.update({"L": 2})
    application.LINE_GAUGE_ORDER.clear()
    application.LINE_GAUGE_ORDER.update({"L": [1, 2, 3, 4, 5]})

    payload = {"serial_no": "S123", "model_code": "M1", "gauge_id": 1}
    rv = client.post("/start-test", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 200
    assert stopped_calls == [(2, False), (3, False)]

    # gauge 5 is position 4 (0-indexed); sweeps positions 0 and 1 -> gauges 1, 2 (wraps around).
    stopped_calls.clear()
    payload = {"serial_no": "S124", "model_code": "M1", "gauge_id": 5}
    rv = client.post("/start-test", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 200
    assert stopped_calls == [(1, False), (2, False)]


def test_start_test_auto_stop_sweeps_whole_gap_window(monkeypatch, client):
    """Matches the reported real-world case: on a 30-gauge line with gap=5,
    scanning gauge 15 IN must stop ANY running test in gauges 16-20 (ahead
    of it in the sequence), not just gauge 20. Only gauges that are actually
    running (per stop_test's own no-op-if-not-running behavior) end up
    reflected as stopped; here we simulate gauges 17 and 19 as the only ones
    currently running."""

    def fake_run_test(serial_no, model_code, model_name, line_name, slave_id, host, port,
                       upper_limit, poll_interval_sec, reading_delay_sec=0, min_duration_sec=0):
        return {"status": "STARTED", "test_id": "fake-id", "message": "ok"}

    running = {17, 19}
    attempted = []
    stopped = []

    def fake_stop_test(gauge_id, manual=True):
        attempted.append(gauge_id)
        if gauge_id in running:
            stopped.append(gauge_id)
            return True
        return False

    monkeypatch.setattr(application, "run_test", fake_run_test)
    monkeypatch.setattr(application, "stop_test", fake_stop_test)
    monkeypatch.setattr(application, "get_material_name", lambda code: None)

    application.GAUGE_CONFIG.clear()
    application.GAUGE_CONFIG.update({
        sid: {"name": f"G{sid}", "host": "192.168.0.3", "port": 502, "line_key": "VISI_COOLER", "enabled": True}
        for sid in range(1, 31)
    })
    application.LINE_GAP.clear()
    application.LINE_GAP.update({"VISI_COOLER": 5})
    application.LINE_GAUGE_ORDER.clear()
    application.LINE_GAUGE_ORDER.update({"VISI_COOLER": list(range(1, 31))})

    payload = {"serial_no": "S123", "model_code": "M1", "gauge_id": 15}
    rv = client.post("/start-test", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 200
    # Every gauge from 16 up to 20 gets a stop attempt (nearest first)...
    assert attempted == [16, 17, 18, 19, 20]
    # ...but only the ones actually running are reported as stopped.
    assert stopped == [17, 19]

    application.LINE_GAP.clear()
    application.LINE_GAUGE_ORDER.clear()


def test_start_test_no_auto_stop_when_gap_disabled(monkeypatch, client):
    def fake_run_test(serial_no, model_code, model_name, line_name, slave_id, host, port,
                       upper_limit, poll_interval_sec, reading_delay_sec=0, min_duration_sec=0):
        return {"status": "STARTED", "test_id": "fake-id", "message": "ok"}

    stopped_calls = []
    monkeypatch.setattr(application, "run_test", fake_run_test)
    monkeypatch.setattr(application, "stop_test", lambda gid, manual=True: stopped_calls.append(gid))
    monkeypatch.setattr(application, "get_material_name", lambda code: None)

    application.GAUGE_CONFIG.clear()
    application.GAUGE_CONFIG.update({
        1: {"name": "G1", "host": "10.0.0.1", "port": 502, "line_key": "L", "enabled": True},
    })
    application.LINE_GAP.clear()  # gap not configured -> feature off
    application.LINE_GAUGE_ORDER.clear()

    payload = {"serial_no": "S123", "model_code": "M1", "gauge_id": 1}
    rv = client.post("/start-test", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 200
    assert stopped_calls == []


class _FakeRegisterResult:
    def __init__(self, registers):
        self.registers = registers

    def isError(self):
        return False


class _FakeErrorResult:
    def isError(self):
        return True


def _make_fake_modbus_client(connect_ok, responding_slave_ids=()):
    """Builds a fake replacement for pymodbus's ModbusTcpClient class."""

    class FakeClient:
        def __init__(self, host, port, timeout=5):
            self.host = host
            self.port = port

        def connect(self):
            return connect_ok

        def read_holding_registers(self, address, count, unit):
            if unit in responding_slave_ids:
                return _FakeRegisterResult([0, 123])  # -> 0.123
            return _FakeErrorResult()

        def close(self):
            pass

    return FakeClient


def test_test_connection_unreachable(monkeypatch, client):
    monkeypatch.setattr(application, "ModbusTcpClient", _make_fake_modbus_client(connect_ok=False))
    application.GAUGE_CONFIG.clear()

    payload = {"host": "10.0.0.5", "port": 502, "slave_ids": [1, 2]}
    rv = client.post("/api/settings/test-connection", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["reachable"] is False
    assert data["gauges"] == []


def test_test_connection_reachable_with_gauge_results(monkeypatch, client):
    monkeypatch.setattr(
        application, "ModbusTcpClient",
        _make_fake_modbus_client(connect_ok=True, responding_slave_ids={1}),
    )
    application.GAUGE_CONFIG.clear()

    payload = {"host": "10.0.0.5", "port": 502, "slave_ids": [1, 2]}
    rv = client.post("/api/settings/test-connection", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["reachable"] is True
    gauges_by_id = {g["slave_id"]: g for g in data["gauges"]}
    assert gauges_by_id[1]["responding"] is True
    assert gauges_by_id[1]["value"] == 0.123
    assert gauges_by_id[2]["responding"] is False


def test_test_connection_invalid_input(client):
    rv = client.post(
        "/api/settings/test-connection",
        data=json.dumps({"host": "", "port": 502, "slave_ids": []}),
        content_type="application/json",
    )
    assert rv.status_code == 400

    rv = client.post(
        "/api/settings/test-connection",
        data=json.dumps({"host": "10.0.0.5", "port": 99999, "slave_ids": []}),
        content_type="application/json",
    )
    assert rv.status_code == 400


def test_test_connection_blocked_by_active_test(monkeypatch, client):
    monkeypatch.setattr(application, "get_active_tests", lambda: [7])
    application.GAUGE_CONFIG.clear()
    application.GAUGE_CONFIG.update({
        7: {"name": "G7", "host": "10.0.0.5", "port": 502, "line_key": "L", "enabled": True},
    })

    payload = {"host": "10.0.0.5", "port": 502, "slave_ids": [7]}
    rv = client.post("/api/settings/test-connection", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 409


def test_start_test_passes_resolved_settings_to_run_test(monkeypatch, client):
    """/start-test resolves reading_delay/upper_limit/poll_interval/
    min_duration from the line's Settings, and model_name from the (mocked)
    external Material lookup — none of these come from the client payload."""
    captured = {}

    def fake_run_test(serial_no, model_code, model_name, line_name, slave_id, host, port,
                       upper_limit, poll_interval_sec, reading_delay_sec=0, min_duration_sec=0):
        captured.update(
            model_name=model_name,
            upper_limit=upper_limit,
            poll_interval_sec=poll_interval_sec,
            reading_delay_sec=reading_delay_sec,
            min_duration_sec=min_duration_sec,
        )
        return {"status": "STARTED", "test_id": "fake-id", "message": "ok"}

    monkeypatch.setattr(application, "run_test", fake_run_test)
    monkeypatch.setattr(application, "auto_stop_cycle_gauge", lambda *a, **k: [])
    monkeypatch.setattr(application, "get_material_name", lambda code: "Deep Freezer 250L")

    application.GAUGE_CONFIG.clear()
    application.GAUGE_CONFIG.update({
        9: {"name": "G9", "host": "10.0.0.1", "port": 502, "line_key": "L", "enabled": True},
    })
    application.LINE_READING_DELAY.clear()
    application.LINE_READING_DELAY.update({"L": 15})
    application.LINE_UPPER_LIMIT.clear()
    application.LINE_UPPER_LIMIT.update({"L": 0.75})
    application.LINE_POLL_INTERVAL.clear()
    application.LINE_POLL_INTERVAL.update({"L": 120})
    application.LINE_MIN_DURATION.clear()
    application.LINE_MIN_DURATION.update({"L": 300})

    payload = {"serial_no": "S123", "model_code": "2501", "gauge_id": 9}
    rv = client.post("/start-test", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 200
    assert captured == {
        "model_name": "Deep Freezer 250L",
        "upper_limit": 0.75,
        "poll_interval_sec": 120,
        "reading_delay_sec": 15,
        "min_duration_sec": 300,
    }

    application.LINE_READING_DELAY.clear()
    application.LINE_UPPER_LIMIT.clear()
    application.LINE_POLL_INTERVAL.clear()
    application.LINE_MIN_DURATION.clear()


def test_start_test_survives_material_lookup_failure(monkeypatch, client):
    """A Material-lookup exception must not block starting the test — it's
    display-only now."""

    def fake_run_test(serial_no, model_code, model_name, line_name, slave_id, host, port,
                       upper_limit, poll_interval_sec, reading_delay_sec=0, min_duration_sec=0):
        return {"status": "STARTED", "test_id": "fake-id", "message": "ok", "model_name": model_name}

    def fake_get_material_name(code):
        raise RuntimeError("DB unreachable")

    monkeypatch.setattr(application, "run_test", fake_run_test)
    monkeypatch.setattr(application, "auto_stop_cycle_gauge", lambda *a, **k: [])
    monkeypatch.setattr(application, "get_material_name", fake_get_material_name)

    application.GAUGE_CONFIG.clear()
    application.GAUGE_CONFIG.update({
        9: {"name": "G9", "host": "10.0.0.1", "port": 502, "line_key": "L", "enabled": True},
    })

    payload = {"serial_no": "S123", "model_code": "2501", "gauge_id": 9}
    rv = client.post("/start-test", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 200
    assert rv.get_json()["status"] == "STARTED"
