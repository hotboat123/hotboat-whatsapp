"""Inspects Reservas_Con_Extras_Sheets columns"""
import os
from dotenv import load_dotenv
load_dotenv()
import psycopg2

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

for tname in ["Reservas_Con_Extras_Sheets", "reservas_con_extras_sheets"]:
    cur.execute("SELECT column_name,data_type FROM information_schema.columns WHERE table_name=%s ORDER BY ordinal_position", (tname,))
    cols = cur.fetchall()
    if cols:
        print(f"=== {tname} ===")
        for c in cols: print(f"  {c[0]:40s} {c[1]}")
        cur.execute(f'SELECT * FROM "{tname}" LIMIT 2')
        for r in cur.fetchall(): print(" SAMPLE:", r)
        break

cur.close(); conn.close()
