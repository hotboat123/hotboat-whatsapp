"""Inspect booknetic_appointments and find max date"""
import os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from dotenv import load_dotenv
load_dotenv()
import psycopg2

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

# Max date in Reservas_Con_Extras_Sheets
cur.execute('SELECT MAX(fecha), COUNT(*) FROM "Reservas_Con_Extras_Sheets"')
row = cur.fetchone()
print(f"Reservas_Con_Extras_Sheets: max_fecha={row[0]}, total={row[1]}")

# booknetic_appointments - count future vs past
cur.execute("SELECT MIN(starts_at::date), MAX(starts_at::date), COUNT(*) FROM booknetic_appointments")
row = cur.fetchone()
print(f"booknetic_appointments: min={row[0]}, max={row[1]}, total={row[2]}")

# hotboat_appointments
cur.execute("SELECT MIN(booking_date), MAX(booking_date), COUNT(*) FROM hotboat_appointments")
row = cur.fetchone()
print(f"hotboat_appointments: min={row[0]}, max={row[1]}, total={row[2]}")

# Sample raw field from booknetic to understand phone
cur.execute("SELECT id, customer_name, starts_at::date, raw->>'customer_phone_number' as phone, raw->>'payment' as payment FROM booknetic_appointments LIMIT 5")
print("\nBooknetic samples (id, name, date, phone, payment):")
for r in cur.fetchall():
    print(f"  {r[0]:6s} | {str(r[1]):30s} | {str(r[2])} | {str(r[3])} | {str(r[4])}")

cur.close(); conn.close()
