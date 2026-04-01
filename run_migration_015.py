"""Migration 015: vacation_days and hotboat_settings tables."""
import os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from dotenv import load_dotenv
load_dotenv()
import psycopg2

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS vacation_days (
    fecha       DATE PRIMARY KEY,
    reason      TEXT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hotboat_settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO hotboat_settings (key, value)
VALUES ('urgency_mode', 'false')
ON CONFLICT (key) DO NOTHING;
""")
conn.commit()
cur.execute("SELECT key, value FROM hotboat_settings")
print("Settings:", cur.fetchall())
cur.execute("SELECT COUNT(*) FROM vacation_days")
print("Vacation days:", cur.fetchone()[0])
cur.close(); conn.close()
print("Migration 015 done.")
