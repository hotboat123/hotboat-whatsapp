"""Run migration 012: create hotboat_appointments table"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from app.db.connection import get_connection

sql_path = os.path.join(os.path.dirname(__file__), "migrations", "012_hotboat_appointments.sql")

with open(sql_path, "r") as f:
    sql = f.read()

try:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    print("Migration 012 completed successfully")
    print("Table hotboat_appointments created")
except Exception as e:
    print(f"Migration failed: {e}")
    sys.exit(1)
