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
    # Prepare modbus cache and gateway info
    application.MODBUS = {"HOST": "127.0.0.1", "PORT": 502}
    application.MODBUS_CACHE.clear()
    application.MODBUS_CACHE.update({1: 0.123, 2: None})

    rv = client.get("/api/health")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["gauges_polled"] == 2
    assert data["gauges_responding"] == 1
    assert "gateway" in data


def test_get_recipe_exists(monkeypatch, client):
    # Mock DB connection to return a recipe row
    # `get_recipe_api` expects (model_name, lower_limit, upper_limit)
    row = ("Model X1", 1.5, 3.0)

    def fake_get_connection():
        class Cursor:
            def execute(self, q, params=None):
                self._q = q

            def fetchone(self):
                return row

            def close(self):
                pass

        class Conn:
            def cursor(self):
                return Cursor()

            def close(self):
                pass

        return Conn()

    # The app module imports `get_connection` directly, patch it there
    monkeypatch.setattr(application, "get_connection", fake_get_connection)

    rv = client.get("/api/recipe/X1")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["exists"] is True
    assert data["ll"] == float(row[1])
    assert data["ul"] == float(row[2])


def test_get_recipe_not_found(monkeypatch, client):
    def fake_get_connection():
        class Cursor:
            def execute(self, q, params=None):
                pass

            def fetchone(self):
                return None

            def close(self):
                pass

        class Conn:
            def cursor(self):
                return Cursor()

            def close(self):
                pass

        return Conn()

    # Patch the `get_connection` symbol used by the app module
    monkeypatch.setattr(application, "get_connection", fake_get_connection)

    rv = client.get("/api/recipe/NOSUCH")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["exists"] is False


def test_start_test_and_stop(monkeypatch, client):
    # Patch the run_test and stop_test used by the app module
    def fake_run_test(serial_no, model_code, line_name, slave_id):
        return {"status": "STARTED", "test_id": "fake-id", "message": "ok"}

    def fake_stop_test(gauge_id):
        return True

    monkeypatch.setattr(application, "run_test", fake_run_test)
    monkeypatch.setattr(application, "stop_test", fake_stop_test)

    # Valid start
    payload = {"serial_no": "S123", "model_code": "M1", "gauge_id": 5}
    rv = client.post("/start-test", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 200
    data = rv.get_json()
    assert data["status"] == "STARTED"

    # Invalid gauge id
    payload = {"serial_no": "S123", "model_code": "M1", "gauge_id": 999}
    rv = client.post("/start-test", data=json.dumps(payload), content_type="application/json")
    assert rv.status_code == 400

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
