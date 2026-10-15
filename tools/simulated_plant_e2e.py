"""End-to-end check of the polling and API against SIMULATED USR devices.

Starts fake Modbus TCP USRs on localhost, runs the real application against
them and checks: independent failure, recovery, dead gauges, stale data,
multi-line users, roles and shutdown. Needs no hardware and touches no real
network: it is fully offline (the database and your .env are NOT used).

    python tools/simulated_plant_e2e.py          # prints PASS/FAIL, exit code 0 = all passed
"""
import os, sys, time, threading
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Never read the real .env and never contact the real database.
import dotenv; dotenv.load_dotenv = lambda *a, **k: False
os.environ["DB_PASSWORD"] = "offline-simulation"
os.environ["DB_SERVER"] = "127.0.0.1"
import db
def _no_database(*a, **k):
    raise RuntimeError("database disabled in simulation")
db.get_connection = _no_database
db.ensure_test_header_columns = lambda: None
for _name in list(os.environ):
    if _name.startswith(("LINE_", "USER_", "POLL", "MODBUS_", "STALE_", "SESSION_")) or _name in ("LINES", "USERS"):
        del os.environ[_name]
from pymodbus.server.sync import ModbusTcpServer
from pymodbus.datastore import ModbusSequentialDataBlock, ModbusSlaveContext, ModbusServerContext

def usr(port, values):
    slaves = {}
    for sid, v in values.items():
        regs = [0] * 10; regs[4] = int(round(v * 1000))
        slaves[sid] = ModbusSlaveContext(hr=ModbusSequentialDataBlock(0, regs), zero_mode=True)
    srv = ModbusTcpServer(ModbusServerContext(slaves=slaves, single=False), address=("127.0.0.1", port))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv

usr(15031, {1: 0.11, 2: 0.12, 3: 0.13})                  # CHOC usr-01 up
# CHOC usr-02 (port 15032, gauges 4-6) is OFFLINE at first
usr(15033, {1: 5.01, 2: 5.02, 4: 5.04})                  # FRZ: gauge 3 is dead (no slave answers)

os.environ.update({
    "DB_PASSWORD": "offline-simulation", "DB_SERVER": "127.0.0.1", "SECRET_KEY": "e2e", "DISABLE_WORKERS": "0",
    "POLLING_MODE": "centralized", "USERS": "ADMIN",
    "USER_ADMIN_USERNAME": "admin", "USER_ADMIN_PASSWORD": "ap", "USER_ADMIN_LINES": "ALL", "USER_ADMIN_ROLE": "admin",
    "MODBUS_TIMEOUT_SEC": "1", "POLL_CYCLE_PAUSE_SEC": "0.3", "MODBUS_BACKOFF_INITIAL_SEC": "0.5",
    "MODBUS_BACKOFF_MAX_SEC": "1", "STALE_AFTER_SEC": "4", "POLL_LEASE_PORT": "47999",
    "LINES": "CHOC,FRZ",
    "LINE_CHOC_USERNAME": "choc", "LINE_CHOC_PASSWORD": "cp", "LINE_CHOC_GAUGES": "6", "LINE_CHOC_UPPER_LIMIT": "0.5",
    "LINE_CHOC_GATEWAYS": "127.0.0.1:15031:1-3,127.0.0.1:15032:4-6",
    "LINE_FRZ_USERNAME": "frz", "LINE_FRZ_PASSWORD": "fp", "LINE_FRZ_GAUGES": "4", "LINE_FRZ_UPPER_LIMIT": "6",
    "LINE_FRZ_GATEWAYS": "127.0.0.1:15033",
})
import app as A, test_runner as T
logged = []
T.create_test_header = lambda serial, model, name, line, gauge, ul: f"{line}-{gauge}"
T.log_reading = lambda tid, v, r: logged.append((tid, round(v, 3), r))
T.close_test_header = lambda tid, res: logged.append((tid, "CLOSED", res))
A.get_material_name = lambda c: "Model"

ok = True
def check(name, cond):
    global ok; ok &= bool(cond); print(("PASS " if cond else "FAIL ") + name)
def wait(cond, t=12):
    end = time.time() + t
    while time.time() < end:
        if cond(): return True
        time.sleep(0.1)
    return False

check("polling service started with lease", A.POLL_LEASE.held)
check("one worker per USR (2 CHOC + 1 FRZ)", len(A.POLLING._workers) == 3)
c1, c2, adm = A.app.test_client(), A.app.test_client(), A.app.test_client()
c1.post("/api/auth/login", json={"username": "choc", "password": "cp"})
c2.post("/api/auth/login", json={"username": "frz", "password": "fp"})
live = lambda c, n: c.get(f"/api/fixture-live/{n}").get_json()

wait(lambda: live(c1, 1)["freshness"] == "valid" and live(c2, 4)["freshness"] == "valid"
     and live(c1, 5)["communication_status"] == "connection_error"
     and live(c2, 3)["communication_status"] == "timeout")

g = live(c1, 1)
check("CHOC g1 valid 0.11 via choc-usr-01", g["vacuum"] == 0.11 and g["usr_id"] == "choc-usr-01" and g["connection_status"] == "connected")
check("FRZ  g1 valid 5.01 (own line, own USR)", live(c2, 1)["vacuum"] == 5.01 and live(c2, 1)["usr_id"] == "frz-usr-01")
g = live(c1, 5)
check("OFFLINE USR: g5 unavailable/connection_error/disconnected/error",
      (g["freshness"], g["communication_status"], g["connection_status"], g["polling_status"]) == ("unavailable", "connection_error", "disconnected", "error"))
check("   ...and its last_error is reported", g["last_error"] and g["last_error_time"])
g = live(c2, 3)
check("DEAD GAUGE behind healthy USR: timeout, USR still connected",
      (g["communication_status"], g["connection_status"], g["freshness"]) == ("timeout", "connected", "unavailable"))
check("   ...neighbours on same USR unaffected", live(c2, 2)["freshness"] == "valid" and live(c2, 4)["freshness"] == "valid")
check("failed CHOC USR did not stop CHOC usr-01 gauges", live(c1, 3)["freshness"] == "valid")

d = c1.get("/api/modbus/diagnostics").get_json()["gateways"]
check("diagnostics: usr-01 connected/running, usr-02 disconnected/error",
      (d[0]["connection_status"], d[0]["polling_status"], d[1]["connection_status"], d[1]["polling_status"]) == ("connected", "running", "disconnected", "error"))
h = c1.get("/api/health").get_json()["polling"]
check("health: 1/2 USRs connected, 2 workers alive", h["usrs_connected"] == 1 and h["workers_alive"] == 2)

# --- the offline USR comes back ---
usr(15032, {4: 0.14, 5: 0.15, 6: 0.16})
check("RECOVERY: USR comes back, g5 becomes valid 0.15", wait(lambda: live(c1, 5)["vacuum"] == 0.15))
check("   ...USR reported connected/running again", c1.get("/api/modbus/diagnostics").get_json()["gateways"][1]["connection_status"] == "connected")

# --- a real test uses the right USR ---
rv = c1.post("/start-test", json={"serial_no": "S4123456789012", "model_code": "1234", "gauge_id": 5})
check("start-test g5 (behind recovered USR) STARTED", rv.get_json()["status"] == "STARTED")
check("test logged real reading 0.15 PASS", wait(lambda: ("CHOC-5", 0.15, "PASS") in logged, 5))
c1.post("/stop-test/5")

# --- stale detection: a gauge that stops answering is never shown as current ---
A.POLLING._gauges[("FRZ", 1)]["last_success"] = time.time() - 60       # simulate old reading
A.POLLING._gauges[("FRZ", 1)]["communication_status"] = "timeout"
g = live(c2, 1)
check("STALE: old/failed reading is not shown as the current value", g["freshness"] == "stale" and g["vacuum"] is None and g["last_value"] == 5.01)

# --- multi-line admin ---
adm.post("/api/auth/login", json={"username": "admin", "password": "ap"})
me = adm.get("/api/auth/me").get_json()
check("admin must choose a line", me["needs_line_selection"] and len(me["lines"]) == 2)
check("no data before choosing", adm.get("/api/fixtures").status_code == 409)
adm.post("/api/auth/select-line", json={"line": "FRZ"})
check("admin on FRZ sees FRZ gauge 4 only (5.04)", live(adm, 4)["vacuum"] == 5.04 and adm.get("/api/fixture-live/5").status_code == 404)
adm.post("/api/auth/select-line", json={"line": "CHOC"})
check("admin switched to CHOC sees CHOC gauge 5 (0.15)", live(adm, 5)["vacuum"] == 0.15)
check("workers unchanged by logins/switching", len(A.POLLING._workers) == 3 and all(w["thread"].is_alive() for w in A.POLLING._workers.values()))
check("operator cannot run connection test, admin can",
      c1.post("/api/settings/test-connection", json={"host": "127.0.0.1", "port": 15031, "slave_ids": [1]}).status_code == 403
      and adm.post("/api/settings/test-connection", json={"host": "127.0.0.1", "port": 15031, "slave_ids": [1]}).get_json()["gauges"][0]["responding"])

# --- graceful shutdown ---
A._shutdown_polling()
check("shutdown stops all workers and frees the lease", not any(w["thread"].is_alive() for w in A.POLLING._workers.values()) and not A.POLL_LEASE.held)
print("\nALL OK" if ok else "\nFAILURES"); sys.exit(0 if ok else 1)
