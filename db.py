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
