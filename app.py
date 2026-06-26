from flask import Flask, request, jsonify, send_file, send_from_directory, Response
from test_runner import get_active_tests, run_test, stop_test
from db import get_connection
import pandas as pd
import io
import time
import threading
import queue
import logging
import os
from datetime import datetime
from functools import wraps
from cachetools import TTLCache
import json
import math
from pymodbus.client.sync import ModbusTcpClient
from config import MODBUS
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# The React app (client/) is built to client/dist and served as static
# files by this same Flask process in production. See client/README.md.
CLIENT_DIST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "client", "dist")

app = Flask(__name__, static_folder=None)

# =========================================================
# GLOBALS
# =========================================================
ALL_GAUGES  = list(range(1, 65))
FIXTURE_CACHE = []
MODBUS_CACHE  = {}
REPORT_CACHE  = TTLCache(maxsize=200, ttl=30)
LOCK          = threading.Lock()

# Per-client SSE queues (one queue per connected browser tab)
SSE_QUEUES = []
SSE_LOCK   = threading.Lock()

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

    return jsonify({
        "error": "Frontend build not found",
        "hint": "Run `npm run build` inside client/, or use `npm run dev` "
                "in client/ for local development (http://localhost:5173)."
    }), 404

# =========================================================
# HEALTH CHECK
# =========================================================
@app.route("/api/health")
def health():
    with LOCK:
        active  = sum(1 for v in MODBUS_CACHE.values() if v is not None)
        polled  = len(MODBUS_CACHE)
    return jsonify({
        "status": "ok",
        "gateway": f"{MODBUS['HOST']}:{MODBUS['PORT']}",
        "gauges_responding": active,
        "gauges_polled": polled,
        "timestamp": datetime.now().isoformat()
    })

# =========================================================
# TODAY'S STATS
# =========================================================
@app.route("/api/stats/today")
@db_safe
def today_stats():
    conn = get_connection()
    cur  = conn.cursor()
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
        row[0] or 0, row[1] or 0, row[2] or 0, row[3] or 0
    )
    return jsonify({
        "total":     total,
        "pass":      pass_c,
        "fail":      fail_c,
        "running":   running,
        "pass_rate": round(pass_c / total * 100, 1) if total > 0 else 0.0
    })

# =========================================================
# RECIPE VALIDATION (returns LL/UL for frontend chart)
# =========================================================
@app.route("/api/recipe/<model_code>")
@db_safe
def get_recipe_api(model_code):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT model_name, lower_limit, upper_limit
        FROM pirani_recipe_master
        WHERE model_code = ?
    """, (model_code,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({"exists": False, "model_name": None, "ll": None, "ul": None})
    return jsonify({
        "exists":     True,
        "model_name": row[0],
        "ll":  float(row[1]) if row[1] is not None else None,
        "ul":  float(row[2]) if row[2] is not None else None,
    })

# =========================================================
# RECIPE MASTER API
# =========================================================
@app.route("/api/recipes", methods=["GET", "POST"])
@db_safe
def recipe_master():
    conn = get_connection()
    cur  = conn.cursor()

    if request.method == "POST":
        d = request.json or {}
        try:
            ll       = float(d["ll"])
            ul       = float(d["ul"])
            duration = int(d["duration"])
            poll     = int(d["poll"])
        except (KeyError, ValueError, TypeError) as e:
            conn.close()
            return jsonify({"error": f"Invalid data: {e}"}), 400

        if ll >= ul:
            conn.close()
            return jsonify({"error": "Lower limit must be less than upper limit"}), 400

        cur.execute("""
            MERGE pirani_recipe_master AS target
            USING (SELECT ? AS model_code, ? AS model_name, ? AS lower_limit,
                          ? AS upper_limit, ? AS test_duration_min, ? AS poll_interval_sec)
                  AS source ON target.model_code = source.model_code
            WHEN MATCHED THEN
                UPDATE SET model_name       = source.model_name,
                           lower_limit      = source.lower_limit,
                           upper_limit      = source.upper_limit,
                           test_duration_min = source.test_duration_min,
                           poll_interval_sec = source.poll_interval_sec
            WHEN NOT MATCHED THEN
                INSERT (model_code, model_name, lower_limit, upper_limit,
                        test_duration_min, poll_interval_sec)
                VALUES (source.model_code, source.model_name, source.lower_limit,
                        source.upper_limit, source.test_duration_min, source.poll_interval_sec);
        """, (d["model"], d.get("model_name", ""), ll, ul, duration, poll))
        conn.commit()

    cur.execute("""
        SELECT model_code, model_name, lower_limit, upper_limit,
               test_duration_min, poll_interval_sec
        FROM pirani_recipe_master
        ORDER BY model_code
    """)
    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()
    conn.close()
    return jsonify([dict(zip(cols, r)) for r in rows])

@app.route("/api/recipes/<model_code>", methods=["DELETE"])
@db_safe
def delete_recipe(model_code):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("DELETE FROM pirani_recipe_master WHERE model_code = ?", (model_code,))
    conn.commit()
    conn.close()
    return jsonify({"success": True})

# =========================================================
# START TEST
# =========================================================
@app.route("/start-test", methods=["POST"])
def start_test():
    d = request.json or {}

    serial_no  = d.get("serial_no",  "").strip()
    model_code = d.get("model_code", "").strip()
    line_name  = d.get("line", "")

    try:
        gauge_id = int(d.get("gauge_id", 0))
    except (ValueError, TypeError):
        return jsonify({"status": "ERROR", "message": "Invalid gauge ID"}), 400

    if not serial_no or not model_code:
        return jsonify({"status": "ERROR", "message": "Serial number and model code required"}), 400

    if not 1 <= gauge_id <= 64:
        return jsonify({"status": "ERROR", "message": "Gauge ID must be between 1 and 64"}), 400

    result = run_test(
        serial_no=serial_no,
        model_code=model_code,
        line_name=line_name,
        slave_id=gauge_id
    )
    return jsonify(result)

# =========================================================
# STOP TEST
# =========================================================
@app.route("/stop-test/<int:gauge_id>", methods=["POST"])
def stop_test_route(gauge_id):
    if not 1 <= gauge_id <= 64:
        return jsonify({"status": "ERROR", "message": "Gauge ID must be between 1 and 64"}), 400
    if stop_test(gauge_id):
        return jsonify({"status": "STOPPED", "message": f"Stop signal sent to Gauge {gauge_id}"})
    return jsonify({"status": "NOT_RUNNING", "message": f"No active test on Gauge {gauge_id}"}), 404


@app.route("/api/active-tests")
def active_tests_api():
    gauges = get_active_tests()
    return jsonify({
        "active_gauges": gauges,
        "count": len(gauges)
    })

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
                pass   # Slow client — drop this update


def fixture_worker():
    conn = None
    cur  = None

    while True:
        try:
            if conn is None:
                conn = get_connection()
                cur  = conn.cursor()

            cur.execute("""
                SELECT
                    h.gauge_id,
                    h.serial_no,
                    h.final_result,
                    h.line_name,
                    DATEDIFF(
                        SECOND,
                        GETDATE(),
                        DATEADD(MINUTE, r.test_duration_min, h.start_time)
                    ) AS remaining_sec
                FROM pirani_test_header h
                JOIN pirani_recipe_master r ON h.model_code = r.model_code
                WHERE h.start_time = (
                    SELECT MAX(start_time)
                    FROM pirani_test_header h2
                    WHERE h2.gauge_id = h.gauge_id
                )
            """)

            rows   = cur.fetchall()
            latest = {r[0]: (r[1], r[2], r[3], r[4]) for r in rows}
            fixtures = []

            for gid in ALL_GAUGES:
                if gid not in latest:
                    fixtures.append({
                        "slave_id": gid, "status": "IDLE",
                        "color": "gray", "remaining": None,
                        "line": None, "serial_no": None
                    })
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

                fixtures.append({
                    "slave_id": gid, "status": status,
                    "color": color, "remaining": remaining,
                    "line": line, "serial_no": serial
                })

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
            cur  = None
            time.sleep(2)

        time.sleep(2)


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
                    yield ": keepalive\n\n"   # Prevent proxy timeout
        except GeneratorExit:
            pass
        finally:
            with SSE_LOCK:
                if client_q in SSE_QUEUES:
                    SSE_QUEUES.remove(client_q)

    return Response(
        stream(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )

# =========================================================
# MODBUS POLLING WORKER
# =========================================================
def modbus_worker():
    logger.info("Modbus polling started → %s:%s", MODBUS["HOST"], MODBUS["PORT"])
    client = None

    while True:
        try:
            if client is None:
                client = ModbusTcpClient(
                    host=MODBUS["HOST"], port=MODBUS["PORT"], timeout=5
                )

            if not client.connect():
                logger.warning("Modbus gateway not reachable")
                time.sleep(5)
                continue

            for sid in ALL_GAUGES:
                try:
                    rr = client.read_holding_registers(
                        address=3, count=2, unit=sid
                    )
                    with LOCK:
                        if rr and not rr.isError():
                            value = rr.registers[1] / 1000
                            MODBUS_CACHE[sid] = value if math.isfinite(value) else None
                        else:
                            MODBUS_CACHE[sid] = None
                    time.sleep(0.03)
                except Exception:
                    with LOCK:
                        MODBUS_CACHE[sid] = None

            time.sleep(2)

        except Exception as e:
            logger.error("Modbus worker error: %s", e)
            try:
                if client:
                    client.close()
            except Exception:
                pass
            client = None
            time.sleep(5)


if "pytest" not in sys.modules and os.environ.get("DISABLE_WORKERS", "0") != "1":
    threading.Thread(target=modbus_worker, daemon=True).start()

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
    cur  = conn.cursor()
    cur.execute("""
        SELECT TOP 1
            h.gauge_id,
            h.serial_no,
            h.model_code,
            h.model_name,
            h.line_name,
            h.final_result,
            h.start_time,
            r.lower_limit,
            r.upper_limit,
            r.test_duration_min
        FROM pirani_test_header h
        LEFT JOIN pirani_recipe_master r ON h.model_code = r.model_code
        WHERE h.gauge_id = ?
        ORDER BY h.start_time DESC
    """, (slave_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        return jsonify({
            "gauge_id": slave_id, "serial_no": None,
            "model_code": None, "model_name": None,
            "line_name": None, "final_result": None,
            "start_time": None, "ll": None, "ul": None, "duration_min": None
        })

    return jsonify({
        "gauge_id":    row[0],
        "serial_no":   row[1],
        "model_code":  row[2],
        "model_name":  row[3],
        "line_name":   row[4],
        "final_result": row[5],
        "start_time":  str(row[6]) if row[6] else None,
        "ll":          float(row[7]) if row[7] is not None else None,
        "ul":          float(row[8]) if row[8] is not None else None,
        "duration_min": int(row[9]) if row[9] is not None else None,
    })

# =========================================================
# MODBUS DIAGNOSTICS
# =========================================================
@app.route("/api/modbus/diagnostics")
def modbus_diagnostics():
    with LOCK:
        active   = sum(1 for v in MODBUS_CACHE.values() if v is not None)
        snapshot = dict(MODBUS_CACHE)
    return jsonify({
        "gateway_ip":        MODBUS["HOST"],
        "port":              MODBUS["PORT"],
        "gauges_polled":     len(snapshot),
        "gauges_responding": active,
        "readings": {
            k: round(v, 3) if v is not None else None
            for k, v in snapshot.items()
        }
    })

# =========================================================
# REPORTS API
# =========================================================
@app.route("/api/reports")
@db_safe
def reports_api():
    cache_key = tuple(sorted(request.args.items()))
    if cache_key in REPORT_CACHE and request.args.get("export") != "excel":
        return jsonify(REPORT_CACHE[cache_key])

    limit  = request.args.get("limit",  type=int)
    start  = request.args.get("start")
    end    = request.args.get("end")
    model  = request.args.get("model")
    result = request.args.get("result")
    line   = request.args.get("line")
    gauge  = request.args.get("gauge",  type=int)

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
            l.vacuum AS last_vacuum
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
            base_query
            + " ORDER BY h.start_time DESC "
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
    df   = pd.read_sql(query, conn, params=params)
    conn.close()

    for col in ["start_time", "end_time"]:
        if col in df.columns:
            df[col] = df[col].astype(str).replace("NaT", None)

    if "test_id" in df.columns:
        df["test_id"] = df["test_id"].astype(str)

    data = df.to_dict(orient="records")
    REPORT_CACHE[cache_key] = data

    if request.args.get("export") == "excel":
        out = io.BytesIO()
        df.to_excel(out, index=False)
        out.seek(0)
        fname = f"pirani_report_{start or 'all'}.xlsx"
        return send_file(
            out, as_attachment=True, download_name=fname,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    return jsonify(data)

# =========================================================
# REPORT TREND API  (UUID-safe — was incorrectly int:)
# =========================================================
@app.route("/api/report/<string:test_id>/trend")
@db_safe
def report_trend(test_id):
    conn = get_connection()
    cur  = conn.cursor()
    cur.execute("""
        SELECT log_time, vacuum, result
        FROM pirani_test_log
        WHERE test_id = ?
        ORDER BY log_time
    """, (test_id,))
    rows = cur.fetchall()
    conn.close()

    return jsonify([
        {
            "time":   str(r[0]),
            "vacuum": float(r[1]) if r[1] is not None else None,
            "result": r[2]
        }
        for r in rows
    ])

# =========================================================
# APP START
# =========================================================
if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=5000, threaded=True, debug=debug)
