import os
import uuid
from datetime import datetime

import pyodbc
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "server":   os.environ.get("DB_SERVER",   "10.100.95.160"),
    "database": os.environ.get("DB_NAME",     "Garuda_WRL_LIVE"),
    "username": os.environ.get("DB_USER",     "sa"),
    "password": os.environ.get("DB_PASSWORD"),
}

if not DB_CONFIG["password"]:
    raise RuntimeError(
        "DB_PASSWORD is not set. Create a .env file (see .env.example) "
        "or set the DB_PASSWORD environment variable before starting the app."
    )


def get_connection():
    conn_str = (
        "DRIVER={SQL Server};"
        f"SERVER={DB_CONFIG['server']};"
        f"DATABASE={DB_CONFIG['database']};"
        f"UID={DB_CONFIG['username']};"
        f"PWD={DB_CONFIG['password']};"
        "Connection Timeout=10;"
    )
    return pyodbc.connect(conn_str)


# ---------- MATERIAL LOOKUP (external system, display-only) ----------
def get_material_name(alt_name):
    """Looks up a model code's display name from the Material master table.
    Purely cosmetic (report display) — no longer gates whether a test can
    start. Returns None if not found."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT Name FROM Material WHERE AltName = ?", (alt_name,))
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


# ---------- TEST HEADER ----------
def ensure_test_header_columns():
    """Idempotent migration: adds pirani_test_header.upper_limit if missing.
    Nullable — pre-existing rows stay NULL (no snapshot available for tests
    that predate the single-common-Upper-Limit change)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        IF COL_LENGTH('dbo.pirani_test_header', 'upper_limit') IS NULL
        BEGIN
            ALTER TABLE dbo.pirani_test_header ADD upper_limit FLOAT NULL
        END
    """)
    conn.commit()
    conn.close()


def create_test_header(serial, model_code, model_name, line, gauge, upper_limit):
    test_id = uuid.uuid4()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pirani_test_header
        (test_id, serial_no, model_code, model_name, line_name, gauge_id, start_time, upper_limit)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (test_id, serial, model_code, model_name, line, gauge, datetime.now(), upper_limit))
    conn.commit()
    conn.close()
    return test_id


def close_test_header(test_id, final_result):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE pirani_test_header
        SET end_time = ?, final_result = ?
        WHERE test_id = ?
    """, (datetime.now(), final_result, test_id))
    conn.commit()
    conn.close()


# ---------- LOGGING ----------
def log_reading(test_id, vacuum, result):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pirani_test_log
        (test_id, log_time, vacuum, result)
        VALUES (?, ?, ?, ?)
    """, (test_id, datetime.now(), vacuum, result))
    conn.commit()
    conn.close()


# ---------- GAUGE / LINE CONFIG ----------
def ensure_gauge_config_table():
    """Idempotent: creates pirani_gauge_config if missing, and seeds it
    from today's single-gateway .env config if it's empty, so a fresh
    deploy behaves exactly like the app did before this table existed."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        IF OBJECT_ID('dbo.pirani_gauge_config', 'U') IS NULL
        BEGIN
            CREATE TABLE dbo.pirani_gauge_config (
                id          INT IDENTITY(1,1) PRIMARY KEY,
                line_key    VARCHAR(50)  NOT NULL,
                line_label  VARCHAR(100) NOT NULL,
                host        VARCHAR(100) NOT NULL,
                port        INT          NOT NULL DEFAULT 502,
                gauge_name  VARCHAR(100) NOT NULL,
                slave_id    INT          NOT NULL,
                enabled     BIT          NOT NULL DEFAULT 1,
                sort_order  INT          NOT NULL DEFAULT 0,
                gap         INT          NOT NULL DEFAULT 0,
                reading_delay_sec INT    NOT NULL DEFAULT 0,
                upper_limit FLOAT        NOT NULL DEFAULT 0,
                poll_interval_sec INT    NOT NULL DEFAULT 60,
                min_duration_sec INT     NOT NULL DEFAULT 600,
                updated_at  DATETIME     NOT NULL DEFAULT GETDATE(),
                CONSTRAINT UQ_pirani_gauge_config_slave_id UNIQUE (slave_id)
            );
            CREATE INDEX IX_pirani_gauge_config_line ON dbo.pirani_gauge_config(line_key);
            CREATE INDEX IX_pirani_gauge_config_host ON dbo.pirani_gauge_config(host, port);
        END
    """)
    conn.commit()

    # Migration for a table created before the `gap` column existed.
    cur.execute("""
        IF COL_LENGTH('dbo.pirani_gauge_config', 'gap') IS NULL
        BEGIN
            ALTER TABLE dbo.pirani_gauge_config ADD gap INT NOT NULL DEFAULT 0
        END
    """)
    conn.commit()

    # Migration for a table created before the `reading_delay_sec` column existed.
    cur.execute("""
        IF COL_LENGTH('dbo.pirani_gauge_config', 'reading_delay_sec') IS NULL
        BEGIN
            ALTER TABLE dbo.pirani_gauge_config ADD reading_delay_sec INT NOT NULL DEFAULT 0
        END
    """)
    conn.commit()

    # Migration for a table created before `upper_limit`/`poll_interval_sec` existed.
    cur.execute("""
        IF COL_LENGTH('dbo.pirani_gauge_config', 'upper_limit') IS NULL
        BEGIN
            ALTER TABLE dbo.pirani_gauge_config ADD upper_limit FLOAT NOT NULL DEFAULT 0
        END
    """)
    conn.commit()
    cur.execute("""
        IF COL_LENGTH('dbo.pirani_gauge_config', 'poll_interval_sec') IS NULL
        BEGIN
            ALTER TABLE dbo.pirani_gauge_config ADD poll_interval_sec INT NOT NULL DEFAULT 60
        END
    """)
    conn.commit()

    # Migration for a table created before `min_duration_sec` existed.
    cur.execute("""
        IF COL_LENGTH('dbo.pirani_gauge_config', 'min_duration_sec') IS NULL
        BEGIN
            ALTER TABLE dbo.pirani_gauge_config ADD min_duration_sec INT NOT NULL DEFAULT 600
        END
    """)
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM pirani_gauge_config")
    if cur.fetchone()[0] == 0:
        from config import MODBUS
        rows = [
            ("DEFAULT", "Default Line", MODBUS["HOST"], MODBUS["PORT"],
             f"Pirani_{i}", i, 1, i)
            for i in range(1, 65)
        ]
        cur.executemany("""
            INSERT INTO pirani_gauge_config
                (line_key, line_label, host, port, gauge_name, slave_id, enabled, sort_order)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, rows)
        conn.commit()
    conn.close()


def get_gauge_config_rows():
    """All gauge config rows, ordered for stable grouped rendering."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, line_key, line_label, host, port, gauge_name, slave_id, enabled, sort_order,
               gap, reading_delay_sec, upper_limit, poll_interval_sec, min_duration_sec
        FROM pirani_gauge_config
        ORDER BY line_key, host, port, sort_order, slave_id
    """)
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    conn.close()
    return rows


def get_conflicting_slave_ids(line_key, slave_ids):
    """Returns [(slave_id, owning_line_key), ...] for any of slave_ids that
    already belong to a DIFFERENT line_key. Empty list if none/no input."""
    if not slave_ids:
        return []
    conn = get_connection()
    cur = conn.cursor()
    placeholders = ",".join("?" * len(slave_ids))
    cur.execute(
        f"""
        SELECT slave_id, line_key FROM pirani_gauge_config
        WHERE slave_id IN ({placeholders}) AND line_key <> ?
        """,
        (*slave_ids, line_key),
    )
    rows = [(r[0], r[1]) for r in cur.fetchall()]
    conn.close()
    return rows


def replace_line_gauge_config(
    line_key, line_label, hosts, gap=0, reading_delay_sec=0,
    upper_limit=0, poll_interval_sec=60, min_duration_sec=600,
):
    """Transactional replace-all-for-line_key.
    hosts: [{host, port, gauges: [{name, slave_id, enabled}, ...]}, ...]
    gap: IN/OUT auto-stop distance for this line (0 = disabled).
    reading_delay_sec: settle time after a test starts before readings count
        toward PASS/FAIL (0 = disabled).
    upper_limit: the single common pass/fail ceiling for this line's tests
        (0 = not configured yet — everything will read as FAIL).
    poll_interval_sec: how often a running test reads its gauge.
    min_duration_sec: the IN/OUT auto-stop cycle can't cut a test shorter
        than this (0 = disabled — auto-stop can end a test immediately).
        Never applies to a manual Stop, which always takes effect right away.
    """
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM pirani_gauge_config WHERE line_key = ?", (line_key,))
        sort_order = 0
        for h in hosts:
            for g in h["gauges"]:
                cur.execute("""
                    INSERT INTO pirani_gauge_config
                        (line_key, line_label, host, port, gauge_name, slave_id, enabled,
                         sort_order, gap, reading_delay_sec, upper_limit, poll_interval_sec,
                         min_duration_sec, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, GETDATE())
                """, (line_key, line_label, h["host"], h["port"],
                      g["name"], g["slave_id"], bool(g["enabled"]), sort_order, gap,
                      reading_delay_sec, upper_limit, poll_interval_sec, min_duration_sec))
                sort_order += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def delete_line_gauge_config(line_key):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM pirani_gauge_config WHERE line_key = ?", (line_key,))
    conn.commit()
    conn.close()
