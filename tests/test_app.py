import dataclasses
import json
import queue
import threading
import time

import pandas as pd
import pytest

import app as application
from app import app as flask_app
from lines_config import Gateway
from polling import PollingService


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    # A fresh polling service per test: no workers, every gauge "unavailable".
    monkeypatch.setattr(application, "POLLING",
                        PollingService(application.LINES, application.SETTINGS))
    application.FIXTURE_CACHE.clear()
    application.REPORT_CACHE.clear()
    yield
    application.FIXTURE_CACHE.clear()
    application.REPORT_CACHE.clear()


def set_gauge(line, sid, value=None, status="success", age=0.0):
    """Put a gauge into a known live state (value read `age` seconds ago)."""
    g = application.POLLING._gauges[(line, sid)]
    g["communication_status"] = status
    if value is not None:
        g["value"] = value
        g["last_success"] = time.time() - age
    return g


def set_usr(line, usr_id, alive=True, **fields):
    """Describe a USR's worker; alive=True registers a (fake) running worker."""
    application.POLLING._usrs[(line, usr_id)].update(fields)
    if alive:
        application.POLLING._workers[(line, usr_id)] = {
            "thread": threading.current_thread(), "stop": threading.Event()}


@pytest.fixture
def anon():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


def _logged_in(username, password):
    flask_app.config["TESTING"] = True
    c = flask_app.test_client()
    rv = c.post("/api/auth/login", json={"username": username, "password": password})
    assert rv.status_code == 200, rv.get_data(as_text=True)
    return c


@pytest.fixture
def client():
    """Logged in as the ALPHA line (6 gauges, two USR gateways)."""
    return _logged_in("alpha", "alpha-pw")


@pytest.fixture
def admin():
    """Admin with every line authorised, working on ALPHA."""
    c = _logged_in("root", "root-pw")
    assert c.post("/api/auth/select-line", json={"line": "ALPHA"}).status_code == 200
    return c


@pytest.fixture
def dual():
    """Operator authorised for ALPHA and BETA; has not chosen a line yet."""
    return _logged_in("dual", "dual-pw")


@pytest.fixture
def beta():
    """Logged in as the BETA line (4 gauges, gauge 2 disabled, one gateway)."""
    return _logged_in("beta", "beta-pw")


def post_json(c, url, payload):
    return c.post(url, data=json.dumps(payload), content_type="application/json")


def set_line(monkeypatch, key, **changes):
    """Swap a line for a modified copy (Line is frozen) for the duration of a test."""
    monkeypatch.setitem(application.LINES, key, dataclasses.replace(application.LINES[key], **changes))


def fake_run_test_factory(captured=None, **extra):
    def fake_run_test(serial_no, model_code, model_name, line_name, slave_id, host, port,
                      upper_limit, poll_interval_sec, reading_delay_sec=0, min_duration_sec=0,
                      register_map="pirani_default"):
        if captured is not None:
            captured.update(register_map=register_map,
                serial_no=serial_no, model_code=model_code, model_name=model_name,
                line_name=line_name, slave_id=slave_id, host=host, port=port,
                upper_limit=upper_limit, poll_interval_sec=poll_interval_sec,
                reading_delay_sec=reading_delay_sec, min_duration_sec=min_duration_sec,
            )
        return {"status": "STARTED", "test_id": "fake-id", "message": "ok", **extra}
    return fake_run_test


# ---------------------------------------------------------------------------
# Login / session
# ---------------------------------------------------------------------------
def test_login_success_returns_the_line(anon):
    rv = post_json(anon, "/api/auth/login", {"username": "alpha", "password": "alpha-pw"})
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["line"] == "ALPHA"
    assert data["line_label"] == "Alpha Line"
    assert data["gauge_count"] == 6
    assert data["username"] == "alpha"

    me = anon.get("/api/auth/me")
    assert me.status_code == 200 and me.get_json()["line"] == "ALPHA"


def test_each_login_lands_on_its_own_line(anon):
    b = _logged_in("beta", "beta-pw")
    assert b.get("/api/auth/me").get_json()["line"] == "BETA"
    assert b.get("/api/auth/me").get_json()["gauge_count"] == 3   # 4 gauges, 1 disabled


def test_login_rejects_bad_credentials(anon):
    assert post_json(anon, "/api/auth/login", {"username": "alpha", "password": "nope"}).status_code == 401
    assert post_json(anon, "/api/auth/login", {"username": "ghost", "password": "alpha-pw"}).status_code == 401
    # Another line's password does not work for this line's username.
    assert post_json(anon, "/api/auth/login", {"username": "alpha", "password": "beta-pw"}).status_code == 401
    assert anon.get("/api/auth/me").status_code == 401


def test_login_validates_input(anon):
    assert post_json(anon, "/api/auth/login", {}).status_code == 400
    assert post_json(anon, "/api/auth/login", {"username": "alpha"}).status_code == 400
    assert post_json(anon, "/api/auth/login", {"username": 1, "password": 2}).status_code == 400
    assert anon.post("/api/auth/login", data="not json", content_type="text/plain").status_code == 400


def test_username_is_case_insensitive_but_password_is_not(anon):
    assert post_json(anon, "/api/auth/login", {"username": " ALPHA ", "password": "alpha-pw"}).status_code == 200
    assert post_json(anon, "/api/auth/login", {"username": "alpha", "password": "ALPHA-PW"}).status_code == 401


def test_logging_in_as_another_line_replaces_the_session(client):
    rv = post_json(client, "/api/auth/login", {"username": "beta", "password": "beta-pw"})
    assert rv.status_code == 200
    assert client.get("/api/auth/me").get_json()["line"] == "BETA"


def test_logout_ends_the_session(client):
    assert client.get("/api/fixtures").status_code == 200
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/fixtures").status_code == 401


def test_session_of_a_user_removed_from_env_is_rejected(client, monkeypatch):
    monkeypatch.delitem(application.USERS, "alpha")
    assert client.get("/api/fixtures").status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_session_whose_line_is_no_longer_authorised_is_rejected(client, monkeypatch):
    user = application.USERS["alpha"]
    monkeypatch.setitem(application.USERS, "alpha",
                        dataclasses.replace(user, lines=("BETA",)))
    rv = client.get("/api/fixtures")
    assert rv.status_code == 409 and rv.get_json()["code"] == "line_not_selected"


@pytest.mark.parametrize("method,url", [
    ("get", "/api/auth/me"), ("get", "/api/fixtures"), ("get", "/api/fixtures/stream"),
    ("get", "/api/stats/today"), ("get", "/api/reports?limit=5"), ("get", "/api/settings/lines"),
    ("get", "/api/modbus/diagnostics"), ("get", "/api/active-tests"), ("get", "/api/fixture-live/1"),
    ("get", "/api/fixture/1"), ("get", "/api/material/2501"), ("get", "/api/report/abc/trend"),
    ("get", "/api/report/abc/pdf"), ("post", "/start-test"), ("post", "/stop-test/1"),
    ("post", "/api/settings/test-connection"),
])
def test_every_data_endpoint_requires_login(anon, method, url):
    assert getattr(anon, method)(url).status_code == 401


def test_line_settings_can_no_longer_be_edited_over_the_api(client):
    # Configuration lives in .env now.
    assert client.post("/api/settings/lines", json={}).status_code == 405
    assert client.delete("/api/settings/lines/ALPHA").status_code == 405


def test_health_is_public_but_only_shows_gateways_when_logged_in(anon, client):
    body = anon.get("/api/health").get_json()
    assert body["status"] == "ok" and "gateways" not in body

    set_gauge("ALPHA", 1, 0.123)
    set_gauge("ALPHA", 2, status="timeout")
    set_gauge("BETA", 1, 0.5)
    set_usr("ALPHA", "alpha-usr-01", connection="connected", polling="running")
    data = client.get("/api/health").get_json()
    assert data["gateways"] == ["10.0.0.1:502", "10.0.0.2:5020"]
    assert data["gauges_polled"] == 2          # BETA's reading is not counted
    assert data["gauges_responding"] == 1
    assert data["polling"]["mode"] == "centralized" and data["polling"]["polled_here"] is True
    assert data["polling"]["usrs_enabled"] == 2 and data["polling"]["usrs_connected"] == 1
    assert data["polling"]["workers_alive"] == 1


# ---------------------------------------------------------------------------
# Line isolation
# ---------------------------------------------------------------------------
def test_settings_returns_only_the_logged_in_line_and_never_a_password(client, beta):
    rv = client.get("/api/settings/lines")
    lines = rv.get_json()
    assert [l["line_key"] for l in lines] == ["ALPHA"]
    hosts = lines[0]["hosts"]
    assert [(h["host"], h["port"], h["first_gauge"], h["last_gauge"]) for h in hosts] == [
        ("10.0.0.1", 502, 1, 3), ("10.0.0.2", 5020, 4, 6)]
    assert [g["slave_id"] for h in hosts for g in h["gauges"]] == [1, 2, 3, 4, 5, 6]
    assert lines[0]["upper_limit"] == 1.0
    text = rv.get_data(as_text=True)
    assert "alpha-pw" not in text and "beta-pw" not in text and "10.0.1.1" not in text

    b = beta.get("/api/settings/lines").get_json()
    assert [l["line_key"] for l in b] == ["BETA"]
    flags = {g["slave_id"]: g["enabled"] for g in b[0]["hosts"][0]["gauges"]}
    assert flags == {1: True, 2: False, 3: True, 4: True}


def test_fixtures_are_only_the_logged_in_lines(client, beta):
    application.FIXTURE_CACHE.update({
        "ALPHA": [{"slave_id": n, "status": "IDLE"} for n in range(1, 7)],
        "BETA": [{"slave_id": n, "status": "RUNNING"} for n in (1, 3, 4)],
    })
    a = client.get("/api/fixtures").get_json()
    b = beta.get("/api/fixtures").get_json()
    assert [f["slave_id"] for f in a] == [1, 2, 3, 4, 5, 6]
    assert [f["slave_id"] for f in b] == [1, 3, 4]
    assert all(f["status"] == "RUNNING" for f in b)


def test_live_vacuum_is_looked_up_per_line(client, beta):
    """Both lines have a gauge 1 — each must read its own."""
    set_gauge("ALPHA", 1, 0.111)
    set_gauge("BETA", 1, 0.999)
    assert client.get("/api/fixture-live/1").get_json()["vacuum"] == 0.111
    assert beta.get("/api/fixture-live/1").get_json()["vacuum"] == 0.999


def test_live_gauge_carries_identity_and_status(client):
    set_gauge("ALPHA", 5, 0.25)
    set_usr("ALPHA", "alpha-usr-02", connection="connected", polling="running",
            last_cycle_at=time.time())
    d = client.get("/api/fixture-live/5").get_json()
    assert (d["line"], d["gauge_id"], d["slave_id"]) == ("ALPHA", 5, 5)
    assert (d["usr_id"], d["usr_ip"], d["usr_port"]) == ("alpha-usr-02", "10.0.0.2", 5020)
    assert (d["freshness"], d["communication_status"]) == ("valid", "success")
    assert (d["connection_status"], d["polling_status"]) == ("connected", "running")
    assert d["unit"] == "mbar" and d["vacuum"] == 0.25 and d["polled_here"] is True
    assert d["last_success"] and d["last_error"] is None


def test_a_stale_or_failed_gauge_never_shows_as_a_current_value(client):
    # Never read -> unavailable.
    d = client.get("/api/fixture-live/1").get_json()
    assert d["freshness"] == "unavailable" and d["vacuum"] is None

    # Read, but too long ago -> stale; the last value is kept apart, not shown as current.
    set_gauge("ALPHA", 1, 0.4, age=application.SETTINGS.stale_after_sec + 5)
    d = client.get("/api/fixture-live/1").get_json()
    assert d["freshness"] == "stale" and d["vacuum"] is None and d["last_value"] == 0.4

    # A recent success followed by a failed read is no longer "healthy".
    set_gauge("ALPHA", 2, 0.5, age=1)
    set_gauge("ALPHA", 2, status="timeout")
    application.POLLING._gauges[("ALPHA", 2)]["last_error"] = "no response from gauge"
    d = client.get("/api/fixture-live/2").get_json()
    assert d["freshness"] == "stale" and d["vacuum"] is None
    assert d["communication_status"] == "timeout" and d["last_error"] == "no response from gauge"


def test_polling_status_running_delayed_stopped_error(client):
    now = time.time()
    status = lambda sid: client.get(f"/api/fixture-live/{sid}").get_json()["polling_status"]

    assert status(1) == "stopped"                               # no worker
    set_usr("ALPHA", "alpha-usr-01", last_cycle_at=now, polling="running")
    assert status(1) == "running"
    set_usr("ALPHA", "alpha-usr-01", last_cycle_at=now - 999)
    assert status(1) == "delayed"                               # worker alive, cycles overdue
    set_usr("ALPHA", "alpha-usr-01", polling="error")
    assert status(1) == "error"


def test_live_gauge_of_another_lines_number_is_not_found(client, beta):
    assert client.get("/api/fixture-live/7").status_code == 404     # ALPHA has 1-6
    assert beta.get("/api/fixture-live/2").status_code == 404       # BETA's gauge 2 is disabled
    assert beta.get("/api/fixture-live/5").status_code == 404


def test_diagnostics_are_per_line_and_per_usr(client, beta):
    for sid, v in ((1, 0.1), (3, 0.3)):
        set_gauge("ALPHA", sid, v)
    set_gauge("ALPHA", 2, status="timeout")
    set_gauge("BETA", 1, 9.0)
    set_usr("ALPHA", "alpha-usr-01", connection="connected", polling="running",
            last_cycle_at=time.time())
    set_usr("ALPHA", "alpha-usr-02", alive=False, connection="disconnected", polling="error",
            last_error="cannot connect to the USR")

    gws = client.get("/api/modbus/diagnostics").get_json()["gateways"]
    assert [(g["usr_id"], g["host"], g["port"]) for g in gws] == [
        ("alpha-usr-01", "10.0.0.1", 502), ("alpha-usr-02", "10.0.0.2", 5020)]
    assert gws[0]["gauges_polled"] == 3 and gws[0]["gauges_responding"] == 2
    assert gws[0]["connection_status"] == "connected" and gws[0]["polling_status"] == "running"
    assert gws[0]["readings"] == {"1": 0.1, "2": None, "3": 0.3}
    assert gws[0]["gauges"]["2"]["communication_status"] == "timeout"

    # One failed USR is reported on its own and does not affect the other.
    assert gws[1]["gauges_responding"] == 0
    assert (gws[1]["connection_status"], gws[1]["polling_status"]) == ("disconnected", "stopped")
    assert gws[1]["last_error"] == "cannot connect to the USR"

    # BETA: one USR; the disabled gauge 2 is not reported.
    bgws = beta.get("/api/modbus/diagnostics").get_json()["gateways"]
    assert len(bgws) == 1 and bgws[0]["host"] == "10.0.1.1" and bgws[0]["usr_id"] == "beta-usr-01"
    assert bgws[0]["readings"] == {"1": 9.0, "3": None, "4": None}


def test_active_tests_only_lists_this_lines_gauges(monkeypatch, client, beta):
    monkeypatch.setattr(application, "get_active_tests",
                        lambda line_key: {"ALPHA": [3, 5], "BETA": [1]}[line_key])
    assert client.get("/api/active-tests").get_json() == {"active_gauges": [3, 5], "count": 2}
    assert beta.get("/api/active-tests").get_json() == {"active_gauges": [1], "count": 1}


def test_fixture_states(monkeypatch):
    s = application._fixture_state
    assert s(3, None) == {"slave_id": 3, "status": "IDLE", "color": "gray",
                          "remaining": None, "line": None, "serial_no": None}
    assert s(1, ("S1", None, "ALPHA", 120))["status"] == "RUNNING"
    assert s(1, ("S1", None, "ALPHA", -5))["remaining"] == 0
    assert s(1, ("S1", "PASS", "ALPHA", 300))["color"] == "green"
    assert s(1, ("S1", "FAIL", "ALPHA", 300))["color"] == "red"
    assert s(1, ("S1", "ABORTED", "ALPHA", 300))["status"] == "ERROR"
    assert s(1, ("S1", "PASS", "ALPHA", -1))["status"] == "IDLE"   # finished long ago


def test_build_fixtures_keeps_each_lines_gauge_1_separate():
    rows = [
        # (line_name, gauge_id, serial, result, remaining)
        ("ALPHA", 1, "S-A1", "PASS", 100),
        ("BETA", 1, "S-B1", None, 100),
        ("ALPHA", 6, "S-A6", "FAIL", 100),
        ("OLD_LINE", 1, "S-OLD", "PASS", 100),   # not configured any more -> ignored
    ]
    by_line = application.build_fixtures_by_line(rows)
    assert set(by_line) == {"ALPHA", "BETA"}

    alpha = {f["slave_id"]: f for f in by_line["ALPHA"]}
    beta = {f["slave_id"]: f for f in by_line["BETA"]}
    assert sorted(alpha) == [1, 2, 3, 4, 5, 6]
    assert sorted(beta) == [1, 3, 4]                       # gauge 2 disabled
    assert alpha[1]["status"] == "PASS" and alpha[1]["serial_no"] == "S-A1"
    assert beta[1]["status"] == "RUNNING" and beta[1]["serial_no"] == "S-B1"
    assert alpha[6]["status"] == "FAIL"
    assert alpha[2]["status"] == "IDLE" and beta[3]["status"] == "IDLE"


def test_sse_broadcast_routes_each_line_to_its_own_clients(monkeypatch):
    qa, qb = queue.Queue(), queue.Queue()
    monkeypatch.setattr(application, "SSE_CLIENTS", [("ALPHA", qa), ("BETA", qb)])
    application._broadcast_fixtures({"ALPHA": [{"slave_id": 1}], "BETA": [{"slave_id": 9}]})
    assert qa.get_nowait() == [{"slave_id": 1}]
    assert qb.get_nowait() == [{"slave_id": 9}]
    assert qa.empty() and qb.empty()


# ---------------------------------------------------------------------------
# Material lookup
# ---------------------------------------------------------------------------
def test_material_lookup_found(monkeypatch, client):
    monkeypatch.setattr(application, "get_material_name", lambda alt_name: "Deep Freezer 250L")
    data = client.get("/api/material/2501").get_json()
    assert data == {"exists": True, "name": "Deep Freezer 250L"}


def test_material_lookup_not_found(monkeypatch, client):
    monkeypatch.setattr(application, "get_material_name", lambda alt_name: None)
    data = client.get("/api/material/NOSUCH").get_json()
    assert data == {"exists": False, "name": None}


# ---------------------------------------------------------------------------
# Start / stop test
# ---------------------------------------------------------------------------
def test_start_test_uses_the_gauges_own_usr_device(monkeypatch, client):
    captured = {}
    monkeypatch.setattr(application, "run_test", fake_run_test_factory(captured))
    monkeypatch.setattr(application, "get_material_name", lambda code: "Model X")

    # Gauge 2 is behind the first USR; gauge 5 behind the second (port 5020).
    assert post_json(client, "/start-test", {"serial_no": "S1", "model_code": "M1", "gauge_id": 2}).status_code == 200
    assert (captured["host"], captured["port"], captured["slave_id"]) == ("10.0.0.1", 502, 2)

    assert post_json(client, "/start-test", {"serial_no": "S1", "model_code": "M1", "gauge_id": 5}).status_code == 200
    assert (captured["host"], captured["port"], captured["slave_id"]) == ("10.0.0.2", 5020, 5)
    assert captured["line_name"] == "ALPHA"
    assert captured["model_name"] == "Model X"


def test_start_test_only_accepts_gauges_of_the_logged_in_line(monkeypatch, client, beta):
    monkeypatch.setattr(application, "run_test", fake_run_test_factory())
    monkeypatch.setattr(application, "get_material_name", lambda code: None)
    body = {"serial_no": "S1", "model_code": "M1"}

    # ALPHA has gauges 1-6; BETA has 1-4 with 2 disabled.
    assert post_json(client, "/start-test", {**body, "gauge_id": 6}).status_code == 200
    assert post_json(client, "/start-test", {**body, "gauge_id": 7}).status_code == 404
    assert post_json(client, "/start-test", {**body, "gauge_id": 999}).status_code == 404
    assert post_json(client, "/start-test", {**body, "gauge_id": 0}).status_code == 404

    assert post_json(beta, "/start-test", {**body, "gauge_id": 4}).status_code == 200
    assert post_json(beta, "/start-test", {**body, "gauge_id": 5}).status_code == 404
    rv = post_json(beta, "/start-test", {**body, "gauge_id": 2})
    assert rv.status_code == 400 and "disabled" in rv.get_json()["message"]


def test_start_test_ignores_a_line_sent_by_the_client(monkeypatch, client):
    """The line comes from the login session; a tampered request can't start a
    test on another line."""
    captured = {}
    monkeypatch.setattr(application, "run_test", fake_run_test_factory(captured))
    monkeypatch.setattr(application, "get_material_name", lambda code: None)
    rv = post_json(client, "/start-test",
                   {"serial_no": "S1", "model_code": "M1", "gauge_id": 1, "line": "BETA", "line_key": "BETA"})
    assert rv.status_code == 200
    assert captured["line_name"] == "ALPHA" and captured["host"] == "10.0.0.1"


def test_start_test_validation(monkeypatch, client):
    monkeypatch.setattr(application, "run_test", fake_run_test_factory())
    assert post_json(client, "/start-test", {"serial_no": "", "model_code": "M1", "gauge_id": 1}).status_code == 400
    assert post_json(client, "/start-test", {"serial_no": "S1", "model_code": "", "gauge_id": 1}).status_code == 400
    assert post_json(client, "/start-test", {"serial_no": "S1", "model_code": "M1", "gauge_id": "abc"}).status_code == 400
    assert post_json(client, "/start-test", {"model_code": "M1", "gauge_id": 1}).status_code == 400


def test_start_test_passes_the_lines_env_settings_to_run_test(monkeypatch, client):
    captured = {}
    monkeypatch.setattr(application, "run_test", fake_run_test_factory(captured))
    monkeypatch.setattr(application, "auto_stop_cycle_gauge", lambda *a, **k: [])
    monkeypatch.setattr(application, "get_material_name", lambda code: "Deep Freezer 250L")
    set_line(monkeypatch, "ALPHA", upper_limit=0.75, poll_interval_sec=120,
             reading_delay_sec=15, min_duration_sec=300)

    rv = post_json(client, "/start-test", {"serial_no": "S123", "model_code": "2501", "gauge_id": 1})
    assert rv.status_code == 200
    assert (captured["model_name"], captured["upper_limit"], captured["poll_interval_sec"],
            captured["reading_delay_sec"], captured["min_duration_sec"]) == (
        "Deep Freezer 250L", 0.75, 120, 15, 300)


def test_start_test_survives_material_lookup_failure(monkeypatch, client):
    def boom(code):
        raise RuntimeError("DB unreachable")
    monkeypatch.setattr(application, "run_test", fake_run_test_factory())
    monkeypatch.setattr(application, "auto_stop_cycle_gauge", lambda *a, **k: [])
    monkeypatch.setattr(application, "get_material_name", boom)
    rv = post_json(client, "/start-test", {"serial_no": "S123", "model_code": "2501", "gauge_id": 1})
    assert rv.status_code == 200 and rv.get_json()["status"] == "STARTED"


def test_stop_test_is_scoped_to_the_logged_in_line(monkeypatch, client, beta):
    calls = []

    def fake_stop(line_key, gauge_id, manual=True):
        calls.append((line_key, gauge_id))
        return True

    monkeypatch.setattr(application, "stop_test", fake_stop)
    assert client.post("/stop-test/1").get_json()["status"] == "STOPPED"
    assert beta.post("/stop-test/1").get_json()["status"] == "STOPPED"
    assert calls == [("ALPHA", 1), ("BETA", 1)]


def test_stop_test_not_running(monkeypatch, client):
    monkeypatch.setattr(application, "stop_test", lambda *a, **k: False)
    rv = client.post("/stop-test/3")
    assert rv.status_code == 404 and rv.get_json()["status"] == "NOT_RUNNING"


# ---------------------------------------------------------------------------
# IN/OUT auto-stop
# ---------------------------------------------------------------------------
def _record_stops(monkeypatch, running=None):
    calls = []

    def fake_stop(line_key, gauge_id, manual=True):
        calls.append((line_key, gauge_id, manual))
        return True if running is None else gauge_id in running

    monkeypatch.setattr(application, "run_test", fake_run_test_factory())
    monkeypatch.setattr(application, "stop_test", fake_stop)
    monkeypatch.setattr(application, "get_material_name", lambda code: None)
    return calls


def test_auto_stop_sweeps_the_gap_window_ahead_and_wraps(monkeypatch, client):
    calls = _record_stops(monkeypatch)
    set_line(monkeypatch, "ALPHA", gap=2)
    body = {"serial_no": "S", "model_code": "M1"}

    assert post_json(client, "/start-test", {**body, "gauge_id": 1}).status_code == 200
    assert calls == [("ALPHA", 2, False), ("ALPHA", 3, False)]

    calls.clear()   # gauge 6 is last on the ring: window wraps to 1, 2
    assert post_json(client, "/start-test", {**body, "gauge_id": 6}).status_code == 200
    assert calls == [("ALPHA", 1, False), ("ALPHA", 2, False)]


def test_auto_stop_on_a_30_gauge_line_covers_gauges_16_to_20(monkeypatch, client):
    """Scanning gauge 15 with gap=5 attempts 16..20; only running ones count as stopped."""
    calls = _record_stops(monkeypatch, running={17, 19})
    big = Gateway("192.168.0.3", 502, 1, 30)
    set_line(monkeypatch, "ALPHA", gauge_count=30, gateways=(big,), gap=5)

    rv = post_json(client, "/start-test", {"serial_no": "S", "model_code": "M1", "gauge_id": 15})
    assert rv.status_code == 200
    assert [c[1] for c in calls] == [16, 17, 18, 19, 20]
    assert application.auto_stop_cycle_gauge(application.LINES["ALPHA"], 15) == [17, 19]


def test_auto_stop_never_touches_another_line(monkeypatch, client):
    calls = _record_stops(monkeypatch)
    set_line(monkeypatch, "ALPHA", gap=3)
    post_json(client, "/start-test", {"serial_no": "S", "model_code": "M1", "gauge_id": 1})
    assert calls and all(lk == "ALPHA" for lk, _, _ in calls)


def test_auto_stop_skips_disabled_gauges(monkeypatch, beta):
    """BETA order is 1,3,4 (2 disabled): gap=1 after gauge 1 targets gauge 3."""
    calls = _record_stops(monkeypatch)
    set_line(monkeypatch, "BETA", gap=1)
    post_json(beta, "/start-test", {"serial_no": "S", "model_code": "M1", "gauge_id": 1})
    assert calls == [("BETA", 3, False)]


def test_no_auto_stop_when_gap_is_zero(monkeypatch, client):
    calls = _record_stops(monkeypatch)
    assert application.LINES["ALPHA"].gap == 0
    assert post_json(client, "/start-test", {"serial_no": "S", "model_code": "M1", "gauge_id": 1}).status_code == 200
    assert calls == []


# ---------------------------------------------------------------------------
# Test-connection (Settings page)
# ---------------------------------------------------------------------------
class _FakeRegisterResult:
    def __init__(self, registers):
        self.registers = registers

    def isError(self):
        return False


class _FakeErrorResult:
    def isError(self):
        return True


def _make_fake_modbus_client(connect_ok, responding_slave_ids=()):
    class FakeClient:
        def __init__(self, host, port, timeout=5):
            self.host, self.port = host, port

        def connect(self):
            return connect_ok

        def read_holding_registers(self, address, count, unit):
            if unit in responding_slave_ids:
                return _FakeRegisterResult([0, 123])  # -> 0.123
            return _FakeErrorResult()

        def close(self):
            pass

    return FakeClient


def test_test_connection_unreachable(monkeypatch, admin):
    monkeypatch.setattr(application, "ModbusTcpClient", _make_fake_modbus_client(connect_ok=False))
    rv = post_json(admin, "/api/settings/test-connection",
                   {"host": "10.0.0.1", "port": 502, "slave_ids": [1, 2]})
    assert rv.status_code == 200
    assert rv.get_json()["reachable"] is False and rv.get_json()["gauges"] == []


def test_test_connection_reachable_with_gauge_results(monkeypatch, admin):
    monkeypatch.setattr(application, "ModbusTcpClient",
                        _make_fake_modbus_client(connect_ok=True, responding_slave_ids={1}))
    rv = post_json(admin, "/api/settings/test-connection",
                   {"host": "10.0.0.1", "port": 502, "slave_ids": [1, 2]})
    data = rv.get_json()
    assert data["reachable"] is True
    by_id = {g["slave_id"]: g for g in data["gauges"]}
    assert by_id[1]["responding"] is True and by_id[1]["value"] == 0.123
    assert by_id[2]["responding"] is False


def test_test_connection_invalid_input(admin):
    assert post_json(admin, "/api/settings/test-connection",
                     {"host": "", "port": 502, "slave_ids": []}).status_code == 400
    assert post_json(admin, "/api/settings/test-connection",
                     {"host": "10.0.0.1", "port": 99999, "slave_ids": []}).status_code == 400
    assert post_json(admin, "/api/settings/test-connection",
                     {"host": "10.0.0.1", "port": 502, "slave_ids": ["x"]}).status_code == 400


def test_test_connection_refuses_hosts_that_are_not_this_lines_gateways(monkeypatch, admin):
    """Must not be usable as a generic port scanner, or to probe another line."""
    monkeypatch.setattr(application, "ModbusTcpClient", _make_fake_modbus_client(connect_ok=True))
    for host, port in [("8.8.8.8", 502), ("10.0.1.1", 502), ("10.0.0.1", 9999)]:
        rv = post_json(admin, "/api/settings/test-connection", {"host": host, "port": port, "slave_ids": []})
        assert rv.status_code == 403, (host, port)


def test_test_connection_slave_ids_must_belong_to_the_gateway(monkeypatch, admin):
    monkeypatch.setattr(application, "ModbusTcpClient", _make_fake_modbus_client(connect_ok=True))
    rv = post_json(admin, "/api/settings/test-connection",
                   {"host": "10.0.0.1", "port": 502, "slave_ids": [1, 5]})   # 5 is behind the other USR
    assert rv.status_code == 400


def test_test_connection_blocked_by_active_test_on_that_gateway(monkeypatch, admin):
    monkeypatch.setattr(application, "get_active_tests", lambda line_key: [2])
    monkeypatch.setattr(application, "ModbusTcpClient", _make_fake_modbus_client(connect_ok=True))
    rv = post_json(admin, "/api/settings/test-connection", {"host": "10.0.0.1", "port": 502, "slave_ids": [1]})
    assert rv.status_code == 409
    # ...but the other USR (gauges 4-6) is free to test.
    rv = post_json(admin, "/api/settings/test-connection", {"host": "10.0.0.2", "port": 5020, "slave_ids": [4]})
    assert rv.status_code == 200


# ---------------------------------------------------------------------------
# Reports: every query is restricted to the logged-in line
# ---------------------------------------------------------------------------
class _FakeCursor:
    def __init__(self, log, fetchone=None, fetchall=()):
        self.log, self._one, self._all = log, fetchone, list(fetchall)
        self.description = [("test_id",), ("gauge_id",), ("serial_no",), ("model_code",), ("model_name",),
                            ("line_name",), ("final_result",), ("start_time",), ("end_time",), ("ul",)]

    def execute(self, sql, params=()):
        self.log.append((" ".join(sql.split()), tuple(params)))

    def fetchone(self):
        return self._one

    def fetchall(self):
        return self._all


class _FakeConn:
    def __init__(self, log, **kw):
        self.log, self.kw = log, kw

    def cursor(self):
        return _FakeCursor(self.log, **self.kw)

    def close(self):
        pass


def _patch_db(monkeypatch, **kw):
    log = []
    monkeypatch.setattr(application, "get_connection", lambda: _FakeConn(log, **kw))
    return log


def _patch_read_sql(monkeypatch):
    seen = []

    def fake_read_sql(query, conn, params=None):
        seen.append((" ".join(query.split()), list(params)))
        return pd.DataFrame([{"test_id": "t1", "gauge_id": 1, "serial_no": "S", "model_code": "M",
                              "model_name": "N", "line_name": params[0], "final_result": "PASS",
                              "start_time": "2026-01-01 00:00:00", "end_time": None,
                              "last_vacuum": 0.1, "ul": 1.0}])

    monkeypatch.setattr(application, "get_connection", lambda: _FakeConn([]))
    monkeypatch.setattr(application.pd, "read_sql", fake_read_sql)
    return seen


def test_reports_are_always_filtered_to_the_logged_in_line(monkeypatch, client, beta):
    seen = _patch_read_sql(monkeypatch)
    qs = "start=2026-01-01&end=2026-01-02&model=2501&result=PASS&gauge=3"

    assert client.get(f"/api/reports?{qs}").status_code == 200
    assert beta.get(f"/api/reports?{qs}").status_code == 200

    (q_a, p_a), (q_b, p_b) = seen
    assert "h.line_name = ?" in q_a
    assert p_a == ["ALPHA", "2026-01-01", "2026-01-02", "2501", "PASS", 3]
    assert p_b[0] == "BETA"          # identical query string, different line, not served from cache


def test_reports_ignore_a_line_chosen_by_the_client(monkeypatch, client):
    seen = _patch_read_sql(monkeypatch)
    rv = client.get("/api/reports?start=2026-01-01&end=2026-01-01&line=BETA")
    assert rv.status_code == 200
    assert seen[0][1][0] == "ALPHA" and "BETA" not in seen[0][1]
    assert rv.get_json()[0]["line_name"] == "ALPHA"


def test_latest_reports_list_is_line_scoped_too(monkeypatch, client):
    seen = _patch_read_sql(monkeypatch)
    assert client.get("/api/reports?limit=10").status_code == 200
    query, params = seen[0]
    assert "WHERE h.line_name = ?" in query and "FETCH NEXT ? ROWS ONLY" in query
    assert params == ["ALPHA", 10]


def test_report_cache_is_not_shared_between_lines(monkeypatch, client, beta):
    seen = _patch_read_sql(monkeypatch)
    client.get("/api/reports?limit=10")
    client.get("/api/reports?limit=10")      # same line again -> cached
    beta.get("/api/reports?limit=10")        # other line -> must hit the DB
    assert [p[0] for _, p in seen] == ["ALPHA", "BETA"]


def test_report_without_dates_returns_nothing(monkeypatch, client):
    seen = _patch_read_sql(monkeypatch)
    assert client.get("/api/reports").get_json() == [] and seen == []


def test_trend_is_restricted_to_the_lines_tests(monkeypatch, client, beta):
    log = _patch_db(monkeypatch, fetchall=[])
    assert client.get("/api/report/abc-123/trend").get_json() == []
    assert beta.get("/api/report/abc-123/trend").get_json() == []
    assert "h.line_name = ?" in log[0][0]
    assert [p for _, p in log] == [("abc-123", "ALPHA"), ("abc-123", "BETA")]


def test_pdf_of_another_lines_test_is_not_found(monkeypatch, client, beta):
    log = _patch_db(monkeypatch, fetchone=None)
    assert client.get("/api/report/abc-123/pdf").status_code == 404
    assert beta.get("/api/report/abc-123/pdf").status_code == 404
    assert "h.line_name = ?" in log[0][0]
    assert [p for _, p in log] == [("abc-123", "ALPHA"), ("abc-123", "BETA")]


def test_today_stats_are_counted_per_line(monkeypatch, client, beta):
    log = _patch_db(monkeypatch, fetchone=(10, 7, 2, 1))
    data = client.get("/api/stats/today").get_json()
    beta.get("/api/stats/today")
    assert data == {"total": 10, "pass": 7, "fail": 2, "running": 1, "pass_rate": 70.0}
    assert "line_name = ?" in log[0][0]
    assert [p for _, p in log] == [("ALPHA",), ("BETA",)]


def test_fixture_detail_is_looked_up_by_line_and_gauge(monkeypatch, client, beta):
    log = _patch_db(monkeypatch, fetchone=None)
    data = client.get("/api/fixture/4").get_json()
    beta.get("/api/fixture/4")
    assert data["gauge_id"] == 4 and data["serial_no"] is None
    assert "h.line_name = ?" in log[0][0]
    assert [p for _, p in log] == [(4, "ALPHA"), (4, "BETA")]


# ---------------------------------------------------------------------------
# Multi-line users and the line chooser
# ---------------------------------------------------------------------------
def test_single_line_user_has_the_line_selected_automatically(client):
    me = client.get("/api/auth/me").get_json()
    assert me["line"] == "ALPHA" and me["needs_line_selection"] is False
    assert [l["key"] for l in me["lines"]] == ["ALPHA"]


def test_multi_line_user_must_choose_a_line_first(dual):
    me = dual.get("/api/auth/me").get_json()
    assert me["needs_line_selection"] is True and me["line"] is None
    assert [(l["key"], l["gauge_count"]) for l in me["lines"]] == [("ALPHA", 6), ("BETA", 3)]

    rv = dual.get("/api/fixtures")                       # no line chosen yet
    assert rv.status_code == 409 and rv.get_json()["code"] == "line_not_selected"
    assert dual.get("/api/reports?limit=5").status_code == 409
    assert post_json(dual, "/start-test", {"serial_no": "S", "model_code": "M", "gauge_id": 1}).status_code == 409


def test_choosing_a_line_scopes_everything_to_it_and_switching_changes_scope(dual):
    application.FIXTURE_CACHE.update({
        "ALPHA": [{"slave_id": n} for n in range(1, 7)],
        "BETA": [{"slave_id": n} for n in (1, 3, 4)],
    })
    set_gauge("ALPHA", 6, 0.6)

    assert post_json(dual, "/api/auth/select-line", {"line": "ALPHA"}).get_json()["line"] == "ALPHA"
    assert len(dual.get("/api/fixtures").get_json()) == 6
    assert dual.get("/api/fixture-live/6").get_json()["vacuum"] == 0.6

    assert post_json(dual, "/api/auth/select-line", {"line": "beta"}).status_code == 200   # case-insensitive
    assert [f["slave_id"] for f in dual.get("/api/fixtures").get_json()] == [1, 3, 4]
    assert dual.get("/api/fixture-live/6").status_code == 404     # ALPHA's gauge is not visible any more
    assert dual.get("/api/settings/lines").get_json()[0]["line_key"] == "BETA"


def test_a_user_cannot_select_a_line_they_are_not_authorised_for(client, dual):
    # alpha is only authorised for ALPHA; dual is not authorised for anything else.
    assert post_json(client, "/api/auth/select-line", {"line": "BETA"}).status_code == 403
    assert client.get("/api/auth/me").get_json()["line"] == "ALPHA"       # unchanged
    for bad in ("GAMMA", "", None, 5):
        assert post_json(dual, "/api/auth/select-line", {"line": bad}).status_code == 403
    assert post_json(client, "/api/auth/select-line", {}).status_code == 403


def test_select_line_requires_login(anon):
    assert post_json(anon, "/api/auth/select-line", {"line": "ALPHA"}).status_code == 401


def test_admin_is_authorised_for_every_line(admin):
    me = admin.get("/api/auth/me").get_json()
    assert me["role"] == "Admin" and [l["key"] for l in me["lines"]] == ["ALPHA", "BETA"]
    assert post_json(admin, "/api/auth/select-line", {"line": "BETA"}).status_code == 200


def test_switching_lines_and_logging_in_never_touch_the_polling_workers(dual, client):
    set_usr("ALPHA", "alpha-usr-01")
    set_usr("BETA", "beta-usr-01")
    before = dict(application.POLLING._workers)

    for line in ("ALPHA", "BETA", "ALPHA"):
        post_json(dual, "/api/auth/select-line", {"line": line})
        dual.get("/api/fixtures")
    _logged_in("alpha", "alpha-pw")             # extra logins / tabs
    client.post("/api/auth/logout")             # a logout

    assert application.POLLING._workers == before
    assert all(w["thread"].is_alive() for w in application.POLLING._workers.values())


def test_a_line_sent_by_the_client_is_ignored_for_multi_line_users_too(monkeypatch, dual):
    post_json(dual, "/api/auth/select-line", {"line": "ALPHA"})
    seen = _patch_read_sql(monkeypatch)
    dual.get("/api/reports?start=2026-01-01&end=2026-01-01&line=BETA")
    assert seen[0][1][0] == "ALPHA"


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
def test_connection_test_is_admin_only(monkeypatch, client, dual, admin):
    monkeypatch.setattr(application, "ModbusTcpClient", _make_fake_modbus_client(connect_ok=True))
    body = {"host": "10.0.0.1", "port": 502, "slave_ids": [1]}
    assert post_json(client, "/api/settings/test-connection", body).status_code == 403   # operator
    post_json(dual, "/api/auth/select-line", {"line": "ALPHA"})
    assert post_json(dual, "/api/settings/test-connection", body).status_code == 403     # operator
    assert post_json(admin, "/api/settings/test-connection", body).status_code == 200


def test_roles_are_reported_at_login(client, admin):
    assert client.get("/api/auth/me").get_json()["role"] == "Operator"
    assert admin.get("/api/auth/me").get_json()["role"] == "Admin"


# ---------------------------------------------------------------------------
# Line-specific polling mode: this PC only controls the lines it is wired to
# ---------------------------------------------------------------------------
@pytest.fixture
def only_alpha_here(monkeypatch):
    s = dataclasses.replace(application.SETTINGS, polling_mode="line_specific",
                            poll_lines=frozenset({"ALPHA"}))
    monkeypatch.setattr(application, "SETTINGS", s)
    monkeypatch.setattr(application.POLLING, "settings", s)


def test_tests_cannot_be_started_on_a_line_this_pc_does_not_poll(monkeypatch, only_alpha_here, client, beta):
    monkeypatch.setattr(application, "run_test", fake_run_test_factory())
    monkeypatch.setattr(application, "get_material_name", lambda code: None)
    body = {"serial_no": "S", "model_code": "M1", "gauge_id": 1}

    assert post_json(client, "/start-test", body).status_code == 200
    rv = post_json(beta, "/start-test", body)
    assert rv.status_code == 409 and "line PC" in rv.get_json()["message"]


def test_connection_test_refused_for_a_line_not_reachable_from_this_pc(monkeypatch, only_alpha_here, admin):
    monkeypatch.setattr(application, "ModbusTcpClient", _make_fake_modbus_client(connect_ok=True))
    post_json(admin, "/api/auth/select-line", {"line": "BETA"})
    rv = post_json(admin, "/api/settings/test-connection", {"host": "10.0.1.1", "port": 502, "slave_ids": []})
    assert rv.status_code == 409


def test_not_polled_lines_report_stopped_and_unavailable_not_healthy(only_alpha_here, beta, client):
    d = beta.get("/api/fixture-live/1").get_json()
    assert d["polled_here"] is False
    assert (d["polling_status"], d["freshness"]) == ("stopped", "unavailable")
    assert beta.get("/api/settings/lines").get_json()[0]["polled_here"] is False
    assert client.get("/api/settings/lines").get_json()[0]["polled_here"] is True
    assert beta.get("/api/health").get_json()["polling"]["polled_here"] is False


# ---------------------------------------------------------------------------
# Line configuration payload (read-only page): network + USR identity
# ---------------------------------------------------------------------------
def test_settings_expose_usr_ids_and_line_network(client, beta):
    a = client.get("/api/settings/lines").get_json()[0]
    assert a["network"] == {"subnet": "10.0.0.0/24", "pc_ip": "10.0.0.254",
                            "router_ip": "10.0.0.253", "company_pc_ip": "172.16.0.5"}
    assert [(h["usr_id"], h["enabled"]) for h in a["hosts"]] == [("alpha-usr-01", True), ("alpha-usr-02", True)]
    assert a["register_map"] == "pirani_default" and a["polling_mode"] == "centralized"

    b = beta.get("/api/settings/lines").get_json()[0]
    assert b["network"]["subnet"] is None            # not configured -> simply absent
    assert b["hosts"][0]["usr_id"] == "beta-usr-01"
