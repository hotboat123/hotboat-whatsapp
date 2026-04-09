"""Add quien_atendio column to all_appointments. Run: python _migrate_quien_atendio.py"""
import os
import psycopg

db = os.environ.get("DATABASE_URL", "")
if not db:
    with open(".env") as f:
        for line in f:
            if line.startswith("DATABASE_URL"):
                db = line.split("=", 1)[1].strip()
                break

with psycopg.connect(db) as conn:
    with conn.cursor() as cur:
        cur.execute(
            "ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS quien_atendio TEXT"
        )
        conn.commit()
    print("OK: quien_atendio column added to all_appointments")
