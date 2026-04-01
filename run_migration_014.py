"""Migration 014: Add pagos JSONB column to all_appointments."""
import os, sys
from dotenv import load_dotenv
load_dotenv()
import psycopg2

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

cur.execute("""
    ALTER TABLE all_appointments
    ADD COLUMN IF NOT EXISTS pagos JSONB DEFAULT '[]'::jsonb
""")
conn.commit()

cur.execute("SELECT COUNT(*) FROM all_appointments WHERE pagos IS NULL")
nulls = cur.fetchone()[0]
if nulls:
    cur.execute("UPDATE all_appointments SET pagos='[]'::jsonb WHERE pagos IS NULL")
    conn.commit()
    print(f"Fixed {nulls} NULL pagos rows")

cur.execute("SELECT column_name, data_type FROM information_schema.columns WHERE table_name='all_appointments' AND column_name='pagos'")
print("Column added:", cur.fetchone())
cur.close(); conn.close()
print("Migration 014 done.")
