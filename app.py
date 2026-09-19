from flask import Flask, request, jsonify, send_file, send_from_directory, Response
from test_runner import get_active_tests, run_test, stop_test, MAX_DURATION_MIN
from db import (
    get_connection,
    ensure_gauge_config_table,
    ensure_test_header_columns,
    get_gauge_config_rows,
    get_conflicting_slave_ids,
    replace_line_gauge_config,
    delete_line_gauge_config,
    get_material_name,
)
import pandas as pd
import io
import time
import threading
import queue
import logging
import os
import re
from datetime import datetime
from functools import wraps
from cachetools import TTLCache
import json
import math
from pymodbus.client.sync import ModbusTcpClient
import sys
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from openpyxl.drawing.image import Image as XLImage
import openpyxl
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.legends import Legend
from datetime import datetime
from reportlab.graphics.shapes import Drawing, String
from reportlab.graphics.charts.linecharts import HorizontalLineChart
from reportlab.graphics.charts.legends import Legend
from reportlab.lib import colors

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# The React app (client/) is built to client/dist and served as static
# files by this same Flask process in production. See client/README.md.
CLIENT_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client", "dist")

app = Flask(__name__, static_folder=None)

# =========================================================
# GLOBALS
# =========================================================
# GAUGE_CONFIG: slave_id -> {name, host, port, line_key, enabled}
# ALL_GAUGES: derived, sorted, enabled-only slave ids (kept for fixture_worker)
# HOST_POLLERS: (host, port) -> {"thread": Thread, "stop_event": Event}
# LINE_GAP: line_key -> IN/OUT auto-stop distance (0 = disabled)
# LINE_GAUGE_ORDER: line_key -> sorted enabled slave_ids, the cyclic position
#   sequence a gap is measured against (see _auto_stop_out_of_cycle_gauge)
# LINE_READING_DELAY: line_key -> reading startup delay in seconds (0 = disabled)
# LINE_UPPER_LIMIT: line_key -> single common pass/fail ceiling (0 = not configured)
# LINE_POLL_INTERVAL: line_key -> seconds between readings during a test
# LINE_MIN_DURATION: line_key -> floor (seconds) the IN/OUT auto-stop can't cut
#   a test shorter than (0 = disabled); never applies to a manual Stop
GAUGE_CONFIG = {}
ALL_GAUGES = []
HOST_POLLERS = {}
LINE_GAP = {}
LINE_GAUGE_ORDER = {}
LINE_READING_DELAY = {}
LINE_UPPER_LIMIT = {}
LINE_POLL_INTERVAL = {}
LINE_MIN_DURATION = {}
CONFIG_LOCK = threading.Lock()
POLLER_LOCK = threading.Lock()

# Company logo, embedded in the app header/login page (via the built
# frontend) and in PDF/Excel report exports (directly, below).
LOGO_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "logo", "Western-Refrigeration-768x453.jpg"
)

FIXTURE_CACHE = []
MODBUS_CACHE = {}
REPORT_CACHE = TTLCache(maxsize=200, ttl=30)
LOCK = threading.Lock()

# Per-client SSE queues (one queue per connected browser tab)
SSE_QUEUES = []
SSE_LOCK = threading.Lock()


# =========================================================
# GAUGE / LINE CONFIG — load from DB, reconcile poller threads
# =========================================================
def load_gauge_config_from_db():
    rows = get_gauge_config_rows()
    new_cfg = {
        r["slave_id"]: {
            "name": r["gauge_name"],
            "host": r["host"],
            "port": r["port"],
            "line_key": r["line_key"],
            "enabled": bool(r["enabled"]),
        }
        for r in rows
    }
    new_gap = {}
    new_reading_delay = {}
    new_upper_limit = {}
    new_poll_interval = {}
    new_min_duration = {}
    for r in rows:
        new_gap.setdefault(r["line_key"], r["gap"] or 0)
        new_reading_delay.setdefault(r["line_key"], r["reading_delay_sec"] or 0)
        new_upper_limit.setdefault(r["line_key"], r["upper_limit"] or 0)
        new_poll_interval.setdefault(r["line_key"], r["poll_interval_sec"] or 60)
        new_min_duration.setdefault(
            r["line_key"], r["min_duration_sec"] if r["min_duration_sec"] is not None else 600
        )

    with CONFIG_LOCK:
        GAUGE_CONFIG.clear()
        GAUGE_CONFIG.update(new_cfg)
        ALL_GAUGES[:] = sorted(sid for sid, g in GAUGE_CONFIG.items() if g["enabled"])

        LINE_GAP.clear()
        LINE_GAP.update(new_gap)

        LINE_READING_DELAY.clear()
        LINE_READING_DELAY.update(new_reading_delay)

        LINE_UPPER_LIMIT.clear()
        LINE_UPPER_LIMIT.update(new_upper_limit)

        LINE_POLL_INTERVAL.clear()
        LINE_POLL_INTERVAL.update(new_poll_interval)

        LINE_MIN_DURATION.clear()
        LINE_MIN_DURATION.update(new_min_duration)

        LINE_GAUGE_ORDER.clear()
        for sid, g in GAUGE_CONFIG.items():
            if g["enabled"]:
                LINE_GAUGE_ORDER.setdefault(g["line_key"], []).append(sid)
        for line_key in LINE_GAUGE_ORDER:
            LINE_GAUGE_ORDER[line_key].sort()


def auto_stop_cycle_gauge(line_key, in_gauge_id):
    """After a new IN scan starts a test on in_gauge_id, this line's gap
    setting means every gauge in the `gap` positions immediately *ahead* of
    it is now in the exit window — scanning gauge 15 with gap=5 sweeps
    gauges 16, 17, 18, 19, 20 (wrapping around if needed). Any of those that
    still have a test running gets stopped, letting its naturally
    accumulated PASS/FAIL stand (not ABORTED) — same outcome as a normal
    timeout completion. Gauges in the window with no active test are simply
    a no-op. If a swept gauge's test hasn't yet reached its line's minimum
    test duration, stop_test() defers the actual stop rather than cutting it
    short — it still counts as "stopped" here (the request was accepted).
    Returns the list of gauge ids a stop was requested for (may be empty)."""
    with CONFIG_LOCK:
        gap = LINE_GAP.get(line_key, 0)
        order = list(LINE_GAUGE_ORDER.get(line_key, []))

    if not gap or len(order) < 2 or in_gauge_id not in order:
        return []

    idx = order.index(in_gauge_id)
    n = len(order)
    span = min(gap, n - 1)  # never wrap far enough to include in_gauge_id itself

    stopped = []
    for offset in range(1, span + 1):
        target = order[(idx + offset) % n]
        if stop_test(target, manual=False):
            stopped.append(target)
            logger.info(
                "IN/OUT cycle: gauge %s scanned IN -> auto-stopping gauge %s "
                "(%s of %s positions ahead, gap=%s, line=%s)",
                in_gauge_id, target, offset, span, gap, line_key,
            )
    return stopped


def _gauges_for_host(host, port):
    with CONFIG_LOCK:
        return sorted(
            sid for sid, g in GAUGE_CONFIG.items()
            if g["host"] == host and g["port"] == port and g["enabled"]
        )


def reconcile_pollers():
    """Start a poller thread for every (host, port) with >=1 enabled gauge
    across ALL lines combined, and stop pollers for hosts no longer needed."""
    with POLLER_LOCK:
        with CONFIG_LOCK:
            desired = {(g["host"], g["port"]) for g in GAUGE_CONFIG.values() if g["enabled"]}

        for key in list(HOST_POLLERS.keys()):
            if key not in desired:
                entry = HOST_POLLERS.pop(key)
                entry["stop_event"].set()
                logger.info("Stopping Modbus poller for %s:%s", *key)

        for (host, port) in desired:
            if (host, port) not in HOST_POLLERS:
                stop_event = threading.Event()
                t = threading.Thread(
                    target=modbus_worker, args=(host, port, stop_event),
                    daemon=True, name=f"modbus-{host}:{port}",
                )
                HOST_POLLERS[(host, port)] = {"thread": t, "stop_event": stop_event}
                t.start()
                logger.info("Starting Modbus poller for %s:%s", host, port)


def _apply_gauge_config_change():
    """Call after every successful settings DB write to hot-reload polling."""
    load_gauge_config_from_db()
    reconcile_pollers()


# =========================================================
# DB AUTO-HEAL DECORATOR
# =========================================================
def db_safe(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        for _ in range(3):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                logger.warning("[DB RETRY] %s: %s", fn.__name__, e)
                time.sleep(0.5)
        return jsonify({"error": "Database unavailable"}), 500

    return wrapper


# =========================================================
# UI ROUTES — serve the built React app (client/dist) in production.
# In development the React app runs separately on Vite (npm run dev,
# localhost:5173) and proxies API calls here, so these routes are not
# used at all in dev. They only matter once `npm run build` has been
# run and client/dist exists.
# =========================================================
@app.route("/")
@app.route("/<path:path>")
def serve_react_app(path=""):
    if path and os.path.exists(os.path.join(CLIENT_DIST, path)):
        return send_from_directory(CLIENT_DIST, path)

    index_path = os.path.join(CLIENT_DIST, "index.html")
    if os.path.exists(index_path):
        return send_from_directory(CLIENT_DIST, "index.html")

    return (
        jsonify(
            {
                "error": "Frontend build not found",
                "hint": "Run `npm run build` inside client/, or use `npm run dev` "
                "in client/ for local development (http://localhost:5173).",
            }
        ),
        404,
    )


# =========================================================
# HEALTH CHECK
# =========================================================
@app.route("/api/health")
def health():
    with CONFIG_LOCK:
        gateways = sorted({(g["host"], g["port"]) for g in GAUGE_CONFIG.values() if g["enabled"]})
    with LOCK:
        active = sum(1 for v in MODBUS_CACHE.values() if v is not None)
        polled = len(MODBUS_CACHE)
    return jsonify(
        {
            "status": "ok",
            "gateways": [f"{h}:{p}" for h, p in gateways],
            "gauges_responding": active,
            "gauges_polled": polled,
            "timestamp": datetime.now().isoformat(),
        }
    )


# =========================================================
# TODAY'S STATS
# =========================================================
@app.route("/api/stats/today")
@db_safe
def today_stats():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            COUNT(*)                                                        AS total,
            SUM(CASE WHEN final_result = 'PASS' THEN 1 ELSE 0 END)        AS pass_count,
            SUM(CASE WHEN final_result = 'FAIL' THEN 1 ELSE 0 END)        AS fail_count,
            SUM(CASE WHEN final_result IS NULL   THEN 1 ELSE 0 END)       AS running_count
        FROM pirani_test_header
        WHERE CAST(start_time AS DATE) = CAST(GETDATE() AS DATE)
    """)
    row = cur.fetchone()
    conn.close()

    total, pass_c, fail_c, running = (
        row[0] or 0,
        row[1] or 0,
        row[2] or 0,
        row[3] or 0,
    )
    return jsonify(
        {
            "total": total,
            "pass": pass_c,
            "fail": fail_c,
            "running": running,
            "pass_rate": round(pass_c / total * 100, 1) if total > 0 else 0.0,
        }
    )


# =========================================================
# MATERIAL LOOKUP (external system, display-only — does not gate testing)
# =========================================================
@app.route("/api/material/<alt_name>")
@db_safe
def material_lookup(alt_name):
    name = get_material_name(alt_name)
    return jsonify({"exists": name is not None, "name": name})


# =========================================================
# START TEST
# =========================================================
@app.route("/start-test", methods=["POST"])
def start_test():
    d = request.json or {}

    serial_no = d.get("serial_no", "").strip()
    model_code = d.get("model_code", "").strip()
    line_name = d.get("line", "")

    try:
        gauge_id = int(d.get("gauge_id", 0))
    except (ValueError, TypeError):
        return jsonify({"status": "ERROR", "message": "Invalid gauge ID"}), 400

    if not serial_no or not model_code:
        return (
            jsonify(
                {"status": "ERROR", "message": "Serial number and model code required"}
            ),
            400,
        )

    with CONFIG_LOCK:
        gcfg = GAUGE_CONFIG.get(gauge_id)
        line_key = gcfg["line_key"] if gcfg else None
        reading_delay = LINE_READING_DELAY.get(line_key, 0) if gcfg else 0
        upper_limit = LINE_UPPER_LIMIT.get(line_key, 0) if gcfg else 0
        poll_interval = LINE_POLL_INTERVAL.get(line_key, 60) if gcfg else 60
        min_duration = LINE_MIN_DURATION.get(line_key, 600) if gcfg else 600

    if gcfg is None:
        return jsonify({"status": "ERROR", "message": f"Unknown Gauge ID {gauge_id}"}), 404
    if not gcfg["enabled"]:
        return jsonify({"status": "ERROR", "message": f"Gauge {gauge_id} is disabled"}), 400

    # Display-only lookup in an external system — never blocks starting a test.
    try:
        model_name = get_material_name(model_code) or ""
    except Exception:
        logger.warning("Material lookup failed for model_code=%s", model_code, exc_info=True)
        model_name = ""

    result = run_test(
        serial_no=serial_no,
        model_code=model_code,
        model_name=model_name,
        line_name=line_name,
        slave_id=gauge_id,
        host=gcfg["host"],
        port=gcfg["port"],
        upper_limit=upper_limit,
        poll_interval_sec=poll_interval,
        reading_delay_sec=reading_delay,
        min_duration_sec=min_duration,
    )

    if result.get("status") == "STARTED":
        auto_stop_cycle_gauge(gcfg["line_key"], gauge_id)

    return jsonify(result)


# =========================================================
# STOP TEST
# =========================================================
@app.route("/stop-test/<int:gauge_id>", methods=["POST"])
def stop_test_route(gauge_id):
    if stop_test(gauge_id):
        return jsonify(
            {"status": "STOPPED", "message": f"Stop signal sent to Gauge {gauge_id}"}
        )
    return (
        jsonify(
            {"status": "NOT_RUNNING", "message": f"No active test on Gauge {gauge_id}"}
        ),
        404,
    )


@app.route("/api/active-tests")
def active_tests_api():
    gauges = get_active_tests()
    return jsonify({"active_gauges": gauges, "count": len(gauges)})


# =========================================================
# FIXTURE BACKGROUND WORKER
# =========================================================
def _broadcast_fixtures(data):
    """Push data to all connected SSE clients."""
    with SSE_LOCK:
        for q in SSE_QUEUES:
            try:
                q.put_nowait(data)
            except queue.Full:
                pass  # Slow client — drop this update


def fixture_worker():
    conn = None
    cur = None

    while True:
        try:
            if conn is None:
                conn = get_connection()
                cur = conn.cursor()

            cur.execute("""
                SELECT
                    h.gauge_id,
                    h.serial_no,
                    h.final_result,
                    h.line_name,
                    DATEDIFF(
                        SECOND,
                        GETDATE(),
                        DATEADD(MINUTE, ?, h.start_time)
                    ) AS remaining_sec
                FROM pirani_test_header h
                WHERE h.start_time = (
                    SELECT MAX(start_time)
                    FROM pirani_test_header h2
                    WHERE h2.gauge_id = h.gauge_id
                )
            """, (MAX_DURATION_MIN,))

            rows = cur.fetchall()
            latest = {r[0]: (r[1], r[2], r[3], r[4]) for r in rows}
            fixtures = []

            with CONFIG_LOCK:
                gauges_snapshot = list(ALL_GAUGES)

            for gid in gauges_snapshot:
                if gid not in latest:
                    fixtures.append(
                        {
                            "slave_id": gid,
                            "status": "IDLE",
                            "color": "gray",
                            "remaining": None,
                            "line": None,
                            "serial_no": None,
                        }
                    )
                    continue

                serial, result, line, remaining = latest[gid]

                if remaining is not None and remaining <= 0 and result is not None:
                    status, color = ("IDLE", "gray")
                    remaining = None
                elif result is None:
                    status, color = ("RUNNING", "yellow")
                    remaining = max(0, remaining or 0)
                elif result == "PASS":
                    status, color = ("PASS", "green")
                    remaining = None
                elif result == "FAIL":
                    status, color = ("FAIL", "red")
                    remaining = None
                else:
                    status, color = ("ERROR", "orange")
                    remaining = None

                fixtures.append(
                    {
                        "slave_id": gid,
                        "status": status,
                        "color": color,
                        "remaining": remaining,
                        "line": line,
                        "serial_no": serial,
                    }
                )

            with LOCK:
                FIXTURE_CACHE[:] = fixtures

            _broadcast_fixtures(fixtures)

        except Exception as e:
            logger.error("[FIXTURE WORKER] %s", e)
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
            conn = None
            cur = None
            time.sleep(2)

        time.sleep(2)


if "pytest" not in sys.modules:
    try:
        ensure_gauge_config_table()
        ensure_test_header_columns()
        load_gauge_config_from_db()
    except Exception:
        logger.critical(
            "Gauge config unavailable at startup — Modbus polling disabled",
            exc_info=True,
        )

if "pytest" not in sys.modules and os.environ.get("DISABLE_WORKERS", "0") != "1":
    threading.Thread(target=fixture_worker, daemon=True).start()


# =========================================================
# FIXTURES REST API
# =========================================================
@app.route("/api/fixtures")
def get_fixtures():
    return jsonify(FIXTURE_CACHE)


# =========================================================
# FIXTURES SSE (multi-client safe)
# =========================================================
@app.route("/api/fixtures/stream")
def fixtures_stream():
    client_q = queue.Queue(maxsize=10)
    with SSE_LOCK:
        SSE_QUEUES.append(client_q)

    def stream():
        # Push current state immediately on connect
        with LOCK:
            snapshot = list(FIXTURE_CACHE)
        if snapshot:
            yield f"data: {json.dumps(snapshot)}\n\n"

        try:
            while True:
                try:
                    data = client_q.get(timeout=30)
                    yield f"data: {json.dumps(data)}\n\n"
                except queue.Empty:
                    yield ": keepalive\n\n"  # Prevent proxy timeout
        except GeneratorExit:
            pass
        finally:
            with SSE_LOCK:
                if client_q in SSE_QUEUES:
                    SSE_QUEUES.remove(client_q)

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# =========================================================
# MODBUS POLLING WORKER
# =========================================================
def modbus_worker(host, port, stop_event):
    logger.info("Modbus polling started → %s:%s", host, port)
    client = None

    while not stop_event.is_set():
        try:
            if client is None:
                client = ModbusTcpClient(host=host, port=port, timeout=5)

            if not client.connect():
                logger.warning("Modbus gateway not reachable: %s:%s", host, port)
                stop_event.wait(5)
                continue

            for sid in _gauges_for_host(host, port):
                if stop_event.is_set():
                    break
                try:
                    rr = client.read_holding_registers(address=3, count=2, unit=sid)
                    with LOCK:
                        if rr and not rr.isError():
                            value = rr.registers[1] / 1000
                            MODBUS_CACHE[sid] = value if math.isfinite(value) else None
                        else:
                            MODBUS_CACHE[sid] = None
                except Exception:
                    with LOCK:
                        MODBUS_CACHE[sid] = None
                stop_event.wait(0.03)

            stop_event.wait(2)

        except Exception as e:
            logger.error("Modbus worker error (%s:%s): %s", host, port, e)
            try:
                if client:
                    client.close()
            except Exception:
                pass
            client = None
            stop_event.wait(5)

    try:
        if client:
            client.close()
    except Exception:
        pass
    logger.info("Modbus polling stopped → %s:%s", host, port)


if "pytest" not in sys.modules and os.environ.get("DISABLE_WORKERS", "0") != "1":
    reconcile_pollers()


# =========================================================
# LIVE VACUUM API
# =========================================================
@app.route("/api/fixture-live/<int:slave_id>")
def get_live_vacuum(slave_id):
    with LOCK:
        vacuum = MODBUS_CACHE.get(slave_id)
    if not isinstance(vacuum, (int, float)) or not math.isfinite(vacuum):
        vacuum = None
    return jsonify({"vacuum": vacuum})


# =========================================================
# FIXTURE DETAIL API (extended)
# =========================================================
@app.route("/api/fixture/<int:slave_id>")
@db_safe
def fixture_detail(slave_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT TOP 1
            h.gauge_id,
            h.serial_no,
            h.model_code,
            h.model_name,
            h.line_name,
            h.final_result,
            h.start_time,
            h.upper_limit
        FROM pirani_test_header h
        WHERE h.gauge_id = ?
        ORDER BY h.start_time DESC
    """,
        (slave_id,),
    )
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify(
            {
                "gauge_id": slave_id,
                "serial_no": None,
                "model_code": None,
                "model_name": None,
                "line_name": None,
                "final_result": None,
                "start_time": None,
                "ul": None,
            }
        )

    return jsonify(
        {
            "gauge_id": row[0],
            "serial_no": row[1],
            "model_code": row[2],
            "model_name": row[3],
            "line_name": row[4],
            "final_result": row[5],
            "start_time": str(row[6]) if row[6] else None,
            "ul": float(row[7]) if row[7] is not None else None,
        }
    )


# =========================================================
# MODBUS DIAGNOSTICS
# =========================================================
@app.route("/api/modbus/diagnostics")
def modbus_diagnostics():
    with CONFIG_LOCK:
        cfg = dict(GAUGE_CONFIG)
    with LOCK:
        cache = dict(MODBUS_CACHE)

    gateways = {}
    for sid, g in cfg.items():
        if not g["enabled"]:
            continue
        key = f"{g['host']}:{g['port']}"
        gw = gateways.setdefault(key, {
            "host": g["host"], "port": g["port"],
            "gauges_polled": 0, "gauges_responding": 0, "readings": {},
        })
        v = cache.get(sid)
        gw["gauges_polled"] += 1
        if v is not None:
            gw["gauges_responding"] += 1
        gw["readings"][sid] = round(v, 3) if v is not None else None

    return jsonify({"gateways": list(gateways.values())})


# =========================================================
# LINE / GAUGE SETTINGS API
# =========================================================
LINE_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,50}$")


@app.route("/api/settings/lines", methods=["GET"])
@db_safe
def settings_lines():
    rows = get_gauge_config_rows()
    lines = {}
    for r in rows:
        line = lines.setdefault(r["line_key"], {
            "line_key": r["line_key"],
            "line_label": r["line_label"],
            "gap": r["gap"] or 0,
            "reading_delay_sec": r["reading_delay_sec"] or 0,
            "upper_limit": r["upper_limit"] or 0,
            "poll_interval_sec": r["poll_interval_sec"] or 60,
            "min_duration_sec": r["min_duration_sec"] if r["min_duration_sec"] is not None else 600,
            "hosts": {},
        })
        host = line["hosts"].setdefault((r["host"], r["port"]), {
            "host": r["host"],
            "port": r["port"],
            "gauges": [],
        })
        host["gauges"].append({
            "id": r["id"],
            "name": r["gauge_name"],
            "slave_id": r["slave_id"],
            "enabled": bool(r["enabled"]),
        })

    return jsonify([
        {**line, "hosts": list(line["hosts"].values())} for line in lines.values()
    ])


@app.route("/api/settings/lines", methods=["POST"])
@db_safe
def save_line_config():
    d = request.json or {}
    line_key = (d.get("line_key") or "").strip()
    line_label = (d.get("line_label") or "").strip()
    hosts = d.get("hosts") or []
    gap = d.get("gap", 0) or 0
    reading_delay_sec = d.get("reading_delay_sec", 0) or 0
    upper_limit = d.get("upper_limit", 0) or 0
    poll_interval_sec = d.get("poll_interval_sec", 60) or 60
    min_duration_sec = d.get("min_duration_sec", 600)
    if min_duration_sec is None:
        min_duration_sec = 600

    if not LINE_KEY_RE.match(line_key):
        return jsonify({"error": "line_key must be 1-50 chars of letters/digits/_/-"}), 400
    if not line_label:
        return jsonify({"error": "line_label is required"}), 400
    if not isinstance(gap, int) or isinstance(gap, bool) or not (0 <= gap <= 500):
        return jsonify({"error": "gap must be an integer between 0 and 500"}), 400
    if (
        not isinstance(reading_delay_sec, int)
        or isinstance(reading_delay_sec, bool)
        or not (0 <= reading_delay_sec <= 3600)
    ):
        return jsonify({"error": "reading_delay_sec must be an integer between 0 and 3600"}), 400
    if (
        not isinstance(upper_limit, (int, float))
        or isinstance(upper_limit, bool)
        or upper_limit < 0
    ):
        return jsonify({"error": "upper_limit must be a non-negative number"}), 400
    if (
        not isinstance(poll_interval_sec, int)
        or isinstance(poll_interval_sec, bool)
        or not (60 <= poll_interval_sec <= 3600)
    ):
        return jsonify({"error": "poll_interval_sec must be an integer between 60 and 3600"}), 400
    if (
        not isinstance(min_duration_sec, int)
        or isinstance(min_duration_sec, bool)
        or not (0 <= min_duration_sec <= 3600)
    ):
        return jsonify({"error": "min_duration_sec must be an integer between 0 and 3600"}), 400

    all_slave_ids = []
    for h in hosts:
        host, port = (h.get("host") or "").strip(), h.get("port")
        if not host or not isinstance(port, int) or not (1 <= port <= 65535):
            return jsonify({"error": f"Invalid host/port: {h}"}), 400
        for g in h.get("gauges", []):
            sid = g.get("slave_id")
            if not isinstance(sid, int) or not (1 <= sid <= 247):
                return jsonify({"error": f"Invalid slave_id: {sid}"}), 400
            if not (g.get("name") or "").strip():
                return jsonify({"error": f"Gauge name required for slave_id {sid}"}), 400
            all_slave_ids.append(sid)

    if len(all_slave_ids) != len(set(all_slave_ids)):
        return jsonify({"error": "Duplicate slave_id within this line's submission"}), 400

    conflicts = get_conflicting_slave_ids(line_key, all_slave_ids)
    if conflicts:
        return jsonify({
            "error": "slave_id already used by another line",
            "conflicts": [{"slave_id": sid, "line_key": lk} for sid, lk in conflicts],
        }), 409

    # Don't let a save yank config out from under an active test.
    existing = [r for r in get_gauge_config_rows() if r["line_key"] == line_key]
    old_enabled = {r["slave_id"] for r in existing if r["enabled"]}
    new_enabled = {
        g["slave_id"] for h in hosts for g in h.get("gauges", []) if g.get("enabled")
    }
    at_risk = (old_enabled - new_enabled) & set(get_active_tests())
    if at_risk:
        return jsonify({
            "error": "Cannot save: gauge(s) have an active test running",
            "gauge_ids": sorted(at_risk),
        }), 409

    replace_line_gauge_config(
        line_key, line_label, hosts, gap, reading_delay_sec, upper_limit, poll_interval_sec,
        min_duration_sec,
    )
    _apply_gauge_config_change()
    return jsonify({"success": True})


@app.route("/api/settings/lines/<line_key>", methods=["DELETE"])
@db_safe
def delete_line_config(line_key):
    rows = [r for r in get_gauge_config_rows() if r["line_key"] == line_key]
    at_risk = {r["slave_id"] for r in rows if r["enabled"]} & set(get_active_tests())
    if at_risk:
        return jsonify({
            "error": "Cannot delete: gauge(s) have an active test running",
            "gauge_ids": sorted(at_risk),
        }), 409

    delete_line_gauge_config(line_key)
    _apply_gauge_config_change()
    return jsonify({"success": True})


def _host_has_active_test(host, port):
    """True if any gauge on this (host, port) — per the SAVED config — has a
    test running right now. Guards test-connection from stealing the TCP
    connection out from under a real test on gateways that only support one
    connection at a time (common with cheap Modbus TCP-to-RTU gateways)."""
    with CONFIG_LOCK:
        host_slave_ids = {
            sid for sid, g in GAUGE_CONFIG.items() if g["host"] == host and g["port"] == port
        }
    return bool(host_slave_ids & set(get_active_tests()))


def _test_modbus_connection(host, port, slave_ids, timeout=3):
    """One-shot connectivity check, independent of the persistent poller
    threads. Connects, then (if any slave_ids given) reads a register from
    each to confirm the gauges themselves respond, not just the gateway TCP
    port."""
    client = ModbusTcpClient(host=host, port=port, timeout=timeout)
    try:
        if not client.connect():
            return {"reachable": False, "error": "Connection timed out or refused", "gauges": []}

        gauges = []
        for sid in slave_ids:
            try:
                rr = client.read_holding_registers(address=3, count=2, unit=sid)
                if rr and not rr.isError():
                    value = rr.registers[1] / 1000
                    gauges.append({
                        "slave_id": sid, "responding": True,
                        "value": round(value, 3) if math.isfinite(value) else None,
                    })
                else:
                    gauges.append({"slave_id": sid, "responding": False, "value": None})
            except Exception:
                gauges.append({"slave_id": sid, "responding": False, "value": None})

        return {"reachable": True, "error": None, "gauges": gauges}
    except Exception as e:
        return {"reachable": False, "error": str(e), "gauges": []}
    finally:
        try:
            client.close()
        except Exception:
            pass


@app.route("/api/settings/test-connection", methods=["POST"])
def test_connection_route():
    d = request.json or {}
    host = (d.get("host") or "").strip()
    port = d.get("port")
    slave_ids = d.get("slave_ids") or []

    if not host or not isinstance(port, int) or isinstance(port, bool) or not (1 <= port <= 65535):
        return jsonify({"error": "Invalid host/port"}), 400
    if not isinstance(slave_ids, list) or not all(
        isinstance(s, int) and not isinstance(s, bool) for s in slave_ids
    ):
        return jsonify({"error": "slave_ids must be a list of integers"}), 400

    if _host_has_active_test(host, port):
        return jsonify({
            "error": "Cannot test — an active test is currently using this gateway",
        }), 409

    result = _test_modbus_connection(host, port, slave_ids)
    return jsonify(result)


# =========================================================
# REPORTS API
# =========================================================
@app.route("/api/reports")
@db_safe
def reports_api():
    cache_key = tuple(sorted(request.args.items()))
    if cache_key in REPORT_CACHE and request.args.get("export") != "excel":
        return jsonify(REPORT_CACHE[cache_key])

    limit = request.args.get("limit", type=int)
    start = request.args.get("start")
    end = request.args.get("end")
    model = request.args.get("model")
    result = request.args.get("result")
    line = request.args.get("line")
    gauge = request.args.get("gauge", type=int)

    base_query = """
        SELECT
            h.test_id,
            h.gauge_id,
            h.serial_no,
            h.model_code,
            h.model_name,
            h.line_name,
            h.final_result,
            h.start_time,
            h.end_time,
            l.vacuum AS last_vacuum,
            h.upper_limit AS ul
        FROM pirani_test_header h
        OUTER APPLY (
            SELECT TOP 1 vacuum
            FROM pirani_test_log
            WHERE test_id = h.test_id
            ORDER BY log_time DESC
        ) l
    """
    params = []

    if limit:
        query = (
            base_query + " ORDER BY h.start_time DESC "
            "OFFSET 0 ROWS FETCH NEXT ? ROWS ONLY"
        )
        params.append(limit)
    else:
        if not start or not end:
            return jsonify([])

        # Use CAST so the full end-date is included
        query = base_query + " WHERE CAST(h.start_time AS DATE) BETWEEN ? AND ?"
        params.extend([start, end])

        if model:
            query += " AND h.model_code = ?"
            params.append(model)
        if result:
            query += " AND h.final_result = ?"
            params.append(result)
        if line:
            query += " AND h.line_name = ?"
            params.append(line)
        if gauge:
            query += " AND h.gauge_id = ?"
            params.append(gauge)

        query += " ORDER BY h.start_time DESC"

    conn = get_connection()
    df = pd.read_sql(query, conn, params=params)
    conn.close()

    if "test_id" in df.columns:
        df["test_id"] = df["test_id"].astype(str)

    data = df.to_dict(orient="records")

    # A running test has no end_time yet (and often no final_result / last
    # reading). Depending on pandas dtype inference these missing values can
    # come through as NaN/NaT rather than None, and json.dumps emits those
    # as a bare `NaN` token, which is NOT valid JSON and breaks the browser's
    # JSON.parse(). pd.isna() reliably detects NaN/NaT/None/pd.NA regardless
    # of column dtype, so normalize everything to a real `None` here.
    for row in data:
        for key, value in row.items():
            if pd.isna(value):
                row[key] = None
            elif isinstance(value, pd.Timestamp):
                row[key] = str(value)

    REPORT_CACHE[cache_key] = data

    if request.args.get("export") == "excel":
        out = io.BytesIO()
        # Reserve the top rows for the logo; the real header/data starts below it.
        df.to_excel(out, index=False, startrow=3)
        out.seek(0)

        if os.path.exists(LOGO_PATH):
            wb = openpyxl.load_workbook(out)
            ws = wb.active
            img = XLImage(LOGO_PATH)
            img.width, img.height = 120, 70
            ws.add_image(img, "A1")
            out = io.BytesIO()
            wb.save(out)
            out.seek(0)

        fname = f"pirani_report_{start or 'all'}.xlsx"
        return send_file(
            out,
            as_attachment=True,
            download_name=fname,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    return jsonify(data)


# =========================================================
# REPORT TREND API  (UUID-safe — was incorrectly int:)
# =========================================================
@app.route("/api/report/<string:test_id>/trend")
@db_safe
def report_trend(test_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT log_time, vacuum, result
        FROM pirani_test_log
        WHERE test_id = ?
        ORDER BY log_time
    """,
        (test_id,),
    )
    rows = cur.fetchall()
    conn.close()

    return jsonify(
        [
            {
                "time": str(r[0]),
                "vacuum": float(r[1]) if r[1] is not None else None,
                "result": r[2],
            }
            for r in rows
        ]
    )


# =========================================================
# REPORT PDF EXPORT  (single test: header info + every poll reading)
# =========================================================
def _trend_chart_drawing(readings, ul, width=480, height=190):
    """Vacuum Trend Chart
    X-axis : Time (min)
    Y-axis : Vacuum (mbar)
    Blue   : Actual Vacuum
    Red    : Upper Limit
    """

    if len(readings) < 2:
        return None

    # -----------------------------
    # Convert timestamps to elapsed minutes
    # -----------------------------
    try:
        start = datetime.fromisoformat(str(readings[0][0]))
    except Exception:
        start = None

    x_labels = []
    values = []

    for r in readings:
        if r[1] is None:
            continue

        values.append(float(r[1]))

        if start:
            try:
                t = datetime.fromisoformat(str(r[0]))
                mins = (t - start).total_seconds() / 60.0
                x_labels.append(f"{mins:.1f}")
            except Exception:
                x_labels.append(str(len(x_labels)))
        else:
            x_labels.append(str(len(x_labels)))

    n = len(values)

    if n < 2:
        return None

    # -----------------------------
    # Axis limits
    # -----------------------------
    bounds = values.copy()

    if ul is not None:
        bounds.append(float(ul))

    pad = (max(bounds) - min(bounds)) * 0.15 or 0.05

    y_min = min(bounds) - pad
    y_max = max(bounds) + pad

    drawing = Drawing(width, height)

    chart = HorizontalLineChart()
    chart.x = 55
    chart.y = 40
    chart.width = width - 80
    chart.height = height - 70

    chart.valueAxis.valueMin = y_min
    chart.valueAxis.valueMax = y_max
    chart.valueAxis.labelTextFormat = "%.3f"

    chart.valueAxis.labels.fontSize = 7
    chart.categoryAxis.labels.fontSize = 7

    # Show only every few labels
    step = max(1, n // 8)

    chart.categoryAxis.categoryNames = [
        x_labels[i] if i % step == 0 else "" for i in range(n)
    ]

    # -----------------------------
    # Data series
    # -----------------------------
    chart.data = [
        values,  # Blue
        [float(ul)] * n if ul is not None else [],
    ]

    # Vacuum
    chart.lines[0].strokeColor = colors.blue
    chart.lines[0].strokeWidth = 2
    chart.lines[0].symbol = None

    # Upper Limit
    if ul is not None:
        chart.lines[1].strokeColor = colors.red
        chart.lines[1].strokeWidth = 1.5
        chart.lines[1].strokeDashArray = (4, 2)
        chart.lines[1].symbol = None

    drawing.add(chart)

    # -----------------------------
    # Axis Titles
    # -----------------------------
    drawing.add(
        String(
            width / 2,
            8,
            "Time (min)",
            textAnchor="middle",
            fontSize=8,
        )
    )

    drawing.add(
        String(
            12,
            height / 2,
            "Vacuum (mbar)",
            angle=90,
            fontSize=8,
        )
    )

    # -----------------------------
    # Legend
    # -----------------------------
    legend = Legend()
    legend.x = width - 90
    legend.y = height - 10
    legend.dx = 10
    legend.dy = 10
    legend.fontSize = 7

    legend.colorNamePairs = [
        (colors.blue, "Vacuum"),
        (colors.red, "Upper Limit"),
    ]

    drawing.add(legend)

    return drawing


@app.route("/api/report/<string:test_id>/pdf")
@db_safe
def report_pdf(test_id):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        SELECT h.test_id, h.gauge_id, h.serial_no, h.model_code, h.model_name,
               h.line_name, h.final_result, h.start_time, h.end_time,
               h.upper_limit AS ul
        FROM pirani_test_header h
        WHERE h.test_id = ?
    """,
        (test_id,),
    )
    header_row = cur.fetchone()
    if not header_row:
        conn.close()
        return jsonify({"error": "Test not found"}), 404
    header = dict(zip([c[0] for c in cur.description], header_row))

    cur.execute(
        """
        SELECT log_time, vacuum, result
        FROM pirani_test_log
        WHERE test_id = ?
        ORDER BY log_time
    """,
        (test_id,),
    )
    readings = cur.fetchall()
    conn.close()

    def fmt_dt(v):
        return str(v) if v else "—"

    def fmt_num(v):
        return f"{float(v):.3f}" if v is not None else "—"

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=18 * mm,
        bottomMargin=16 * mm,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle", parent=styles["Title"], fontSize=16, spaceAfter=4
    )
    sub_style = ParagraphStyle(
        "ReportSub",
        parent=styles["Normal"],
        textColor=colors.HexColor("#64748b"),
        fontSize=9,
    )
    h2_style = ParagraphStyle(
        "ReportH2", parent=styles["Heading2"], fontSize=12, spaceBefore=2, spaceAfter=6
    )

    elements = []
    if os.path.exists(LOGO_PATH):
        logo = Image(LOGO_PATH, width=32 * mm, height=18.8 * mm)
        elements += [logo, Spacer(1, 6)]
    elements += [
        Paragraph("Pirani Gauge Test Report", title_style),
        Paragraph(f"Test ID: {header['test_id']}", sub_style),
        Spacer(1, 10),
    ]

    info_rows = [
        [
            "Gauge",
            str(header.get("gauge_id") or "—"),
            "Line",
            header.get("line_name") or "—",
        ],
        [
            "Serial No.",
            header.get("serial_no") or "—",
            "Model",
            header.get("model_code") or "—",
        ],
        [
            "Model Name",
            header.get("model_name") or "—",
            "Result",
            header.get("final_result") or "—",
        ],
        [
            "Start Time",
            fmt_dt(header.get("start_time")),
            "End Time",
            fmt_dt(header.get("end_time")),
        ],
        [
            "Upper Limit",
            fmt_num(header.get("ul")),
            "",
            "",
        ],
    ]
    info_table = Table(info_rows, colWidths=[28 * mm, 55 * mm, 28 * mm, 55 * mm])
    info_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#64748b")),
                ("TEXTCOLOR", (2, 0), (2, -1), colors.HexColor("#64748b")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f8fafc")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#f8fafc")),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    elements += [info_table, Spacer(1, 14)]

    vacs = [float(r[1]) for r in readings if r[1] is not None]
    if vacs:
        stats_table = Table(
            [
                ["Min (mbar)", "Max (mbar)", "Avg (mbar)", "Readings"],
                [
                    f"{min(vacs):.3f}",
                    f"{max(vacs):.3f}",
                    f"{(sum(vacs) / len(vacs)):.3f}",
                    str(len(vacs)),
                ],
            ],
            colWidths=[41.5 * mm] * 4,
        )
        stats_table.setStyle(
            TableStyle(
                [
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        elements += [stats_table, Spacer(1, 14)]

    chart_drawing = _trend_chart_drawing(readings, header.get("ul"))
    if chart_drawing:
        elements.append(Paragraph("Vacuum Trend", h2_style))
        elements.append(chart_drawing)
        elements.append(Spacer(1, 14))

    elements.append(Paragraph("Readings Log", h2_style))

    table_data = [["#", "Time", "Vacuum (mbar)", "Upper Limit (mbar)", "Result"]]

    for i, r in enumerate(readings, start=1):
        table_data.append(
            [
                str(i),
                str(r[0]),
                f"{float(r[1]):.3f}" if r[1] is not None else "—",
                fmt_num(header.get("ul")),
                r[2] or "—",
            ]
        )

    if len(table_data) == 1:
        table_data.append(["—", "No readings recorded", "", "", ""])

    readings_table = Table(
        table_data,
        colWidths=[
            10 * mm,  # #
            50 * mm,  # Time
            33 * mm,  # Vacuum
            30 * mm,  # Upper Limit
            22 * mm,  # Result
        ],
        repeatRows=1,
    )

    readings_table.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
                (
                    "ROWBACKGROUNDS",
                    (0, 1),
                    (-1, -1),
                    [colors.white, colors.HexColor("#f8fafc")],
                ),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    elements.append(readings_table)

    doc.build(elements)
    buf.seek(0)

    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"pirani_report_{test_id}.pdf",
    )


# =========================================================
# APP START
# =========================================================
if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5000, threaded=True, debug=debug)
