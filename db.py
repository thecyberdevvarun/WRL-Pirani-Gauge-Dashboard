import pyodbc
import os
from datetime import datetime
import uuid

DB_CONFIG = {
    "server":   os.environ.get("DB_SERVER",   "10.100.95.160"),
    "database": os.environ.get("DB_NAME",     "Garuda_WRL_LIVE"),
    "username": os.environ.get("DB_USER",     "sa"),
    "password": os.environ.get("DB_PASSWORD", "TnTMES@2022"),
}


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


# ---------- RECIPE ----------
def get_recipe(model_code):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT model_code, model_name, lower_limit, upper_limit,
               test_duration_min, poll_interval_sec
        FROM pirani_recipe_master
        WHERE model_code = ?
    """, (model_code,))
    row = cur.fetchone()
    conn.close()
    return row


# ---------- TEST HEADER ----------
def create_test_header(serial, model_code, model_name, line, gauge):
    test_id = uuid.uuid4()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pirani_test_header
        (test_id, serial_no, model_code, model_name, line_name, gauge_id, start_time)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (test_id, serial, model_code, model_name, line, gauge, datetime.now()))
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
