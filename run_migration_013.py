"""
Migration 013: Create and populate all_appointments table.

This script:
  1. Creates the all_appointments table
  2. Imports ALL records from Reservas_Con_Extras_Sheets (historical source of truth)
  3. Imports FUTURE booknetic_appointments (fecha > max from sheets)
  4. Imports FUTURE hotboat_appointments (fecha > max from sheets)

Run: python run_migration_013.py
"""
import os, re, sys
from datetime import date
from dotenv import load_dotenv

load_dotenv()
import psycopg2
from psycopg2.extras import Json as PgJson

DB_URL = os.getenv("DATABASE_URL")
if not DB_URL:
    print("ERROR: DATABASE_URL not set"); sys.exit(1)

conn = psycopg2.connect(DB_URL)
conn.autocommit = False
cur = conn.cursor()

# ── 1. Create table ──────────────────────────────────────────────────────────
print("Creating all_appointments table...")
with open(os.path.join(os.path.dirname(__file__), "migrations", "013_all_appointments.sql")) as f:
    cur.execute(f.read())
conn.commit()
print("  ✓ Table ready")


# ── 2. Get max fecha from Reservas_Con_Extras_Sheets ────────────────────────
cur.execute('SELECT MAX(fecha) FROM "Reservas_Con_Extras_Sheets"')
max_sheets_fecha = cur.fetchone()[0]
print(f"  Max fecha in Reservas_Con_Extras_Sheets: {max_sheets_fecha}")


# ── Helper: parse CLP payment string ────────────────────────────────────────
def parse_clp(s):
    """'$139.980' -> 139980.0"""
    if not s:
        return 0.0
    return float(re.sub(r"[^0-9]", "", str(s)) or 0)


def normalize_phone(ph):
    if not ph:
        return None
    ph = re.sub(r"[^\d+]", "", str(ph))
    if ph.startswith("+"):
        return ph
    # Chilean number without country code
    if len(ph) == 9 and ph.startswith("9"):
        return "+56" + ph
    return ph


# ── 3. Import from Reservas_Con_Extras_Sheets ────────────────────────────────
print("\nImporting from Reservas_Con_Extras_Sheets...")

# Check how many already imported
cur.execute("SELECT COUNT(*) FROM all_appointments WHERE source='sheets'")
already = cur.fetchone()[0]
if already > 0:
    print(f"  Already {already} sheets records in all_appointments, skipping.")
else:
    cur.execute("""
        SELECT id, appointment_id, reservation_id,
               fecha, hora, nombre_cliente, email, telefono,
               servicio, num_personas, num_adultos, num_ninos,
               ingreso_reserva, ingreso_extras, ingreso_total,
               costo_operativo_fijo, costo_operativo_variable, costo_operativo_total,
               ciudad_origen, como_supieron, clima_del_dia,
               categoria_clientes, tipo_clientes,
               status, tiene_cruce, extras_json, source, created_at
        FROM "Reservas_Con_Extras_Sheets"
        ORDER BY fecha, hora
    """)
    sheets_rows = cur.fetchall()
    inserted_sheets = 0
    for row in sheets_rows:
        (sid, appt_id, res_id, fecha, hora, nombre, email, tel,
         servicio, num_p, num_a, num_n,
         ing_r, ing_e, ing_t, cop_f, cop_v, cop_t,
         ciudad, supieron, clima, cat, tipo,
         status, cruce, extras, src, created) = row
        cur.execute("""
            INSERT INTO all_appointments
            (source, source_id, appointment_id,
             fecha, hora, nombre_cliente, email, telefono,
             servicio, num_personas, num_adultos, num_ninos,
             ingreso_reserva, ingreso_extras, ingreso_total,
             costo_operativo_fijo, costo_operativo_variable, costo_operativo_total,
             ciudad_origen, como_supieron, clima_del_dia,
             categoria_clientes, tipo_clientes,
             status, tiene_cruce, extras_json, created_at, updated_at)
            VALUES
            ('sheets', %s, %s,
             %s, %s, %s, %s, %s,
             %s, %s, %s, %s,
             %s, %s, %s,
             %s, %s, %s,
             %s, %s, %s,
             %s, %s,
             %s, %s, %s, %s, NOW())
            ON CONFLICT DO NOTHING
        """, (
            str(sid), appt_id,
            fecha, hora, nombre, email, normalize_phone(tel),
            servicio, num_p, num_a or 0, num_n or 0,
            float(ing_r or 0), float(ing_e or 0), float(ing_t or 0),
            float(cop_f or 0), float(cop_v or 0), float(cop_t or 0),
            ciudad, supieron, clima, cat, tipo,
            status, cruce or False, PgJson(extras or {}), created
        ))
        inserted_sheets += 1
    conn.commit()
    print(f"  ✓ Imported {inserted_sheets} sheets records")


# ── 4. Import future booknetic_appointments ──────────────────────────────────
print(f"\nImporting booknetic_appointments with fecha > {max_sheets_fecha}...")
cur.execute("""
    SELECT id, customer_name, customer_email,
           starts_at, status, raw, created_at
    FROM booknetic_appointments
    WHERE starts_at::date > %s
    ORDER BY starts_at
""", (max_sheets_fecha,))
book_rows = cur.fetchall()
inserted_book = 0
skipped_book = 0
for row in book_rows:
    (bid, nombre, email, starts_at, status, raw, created) = row
    raw = raw or {}
    phone = normalize_phone(raw.get("customer_phone_number"))
    service = raw.get("service") or ""
    payment_str = raw.get("payment") or ""
    ingreso = parse_clp(payment_str)
    hora = starts_at.time() if starts_at else None
    fecha = starts_at.date() if starts_at else None
    # Extract num_personas from service name e.g. "HotBoat Trip 4 people ..."
    m = re.search(r"(\d+)\s*people", service, re.I)
    num_p = m.group(1) if m else None

    # Check if already imported
    cur.execute("SELECT id FROM all_appointments WHERE source='booknetic' AND source_id=%s", (str(bid),))
    if cur.fetchone():
        skipped_book += 1
        continue

    cur.execute("""
        INSERT INTO all_appointments
        (source, source_id, appointment_id,
         fecha, hora, nombre_cliente, email, telefono,
         servicio, num_personas,
         ingreso_reserva, ingreso_total,
         costo_operativo_fijo, costo_operativo_total,
         status, extras_json, created_at, updated_at)
        VALUES
        ('booknetic', %s, %s,
         %s, %s, %s, %s, %s,
         %s, %s,
         %s, %s,
         18000, 18000,
         %s, '{}', %s, NOW())
    """, (
        str(bid), str(bid),
        fecha, hora, nombre, email, phone,
        service, num_p,
        ingreso, ingreso,
        status, created
    ))
    inserted_book += 1
conn.commit()
print(f"  ✓ Imported {inserted_book} booknetic records (skipped {skipped_book} already imported)")


# ── 5. Import future hotboat_appointments ────────────────────────────────────
print(f"\nImporting hotboat_appointments with fecha > {max_sheets_fecha}...")
cur.execute("""
    SELECT booking_ref, customer_name, customer_email, customer_phone,
           booking_date, booking_time, num_people,
           subtotal, extras_total, total_price,
           extras, status, payment_id, payment_status,
           source, notes, created_at
    FROM hotboat_appointments
    WHERE booking_date > %s
      AND status != 'solicitud'
    ORDER BY booking_date
""", (max_sheets_fecha,))
hb_rows = cur.fetchall()
inserted_hb = 0
skipped_hb = 0
for row in hb_rows:
    (ref, nombre, email, phone, fecha, hora, num_p,
     subtotal, extras_total, total, extras, status,
     pay_id, pay_status, src, notes, created) = row

    cur.execute("SELECT id FROM all_appointments WHERE source='hotboat_web' AND source_id=%s", (ref,))
    if cur.fetchone():
        skipped_hb += 1
        continue

    cur.execute("""
        INSERT INTO all_appointments
        (source, source_id, appointment_id,
         fecha, hora, nombre_cliente, email, telefono,
         servicio, num_personas,
         ingreso_reserva, ingreso_extras, ingreso_total,
         costo_operativo_fijo, costo_operativo_total,
         status, extras_json, observaciones,
         payment_id, payment_status, created_at, updated_at)
        VALUES
        ('hotboat_web', %s, %s,
         %s, %s, %s, %s, %s,
         %s, %s,
         %s, %s, %s,
         18000, 18000,
         %s, %s, %s,
         %s, %s, %s, NOW())
    """, (
        ref, ref,
        fecha, hora, nombre, email, normalize_phone(phone),
        f"HotBoat Web ({num_p}p)", str(num_p),
        float(subtotal or 0), float(extras_total or 0), float(total or 0),
        status, PgJson(extras or {}), notes,
        pay_id, pay_status, created
    ))
    inserted_hb += 1
conn.commit()
print(f"  ✓ Imported {inserted_hb} hotboat_web records (skipped {skipped_hb} already imported)")


# ── Summary ──────────────────────────────────────────────────────────────────
cur.execute("SELECT source, COUNT(*), MIN(fecha), MAX(fecha) FROM all_appointments GROUP BY source ORDER BY source")
print("\n=== all_appointments summary ===")
for row in cur.fetchall():
    print(f"  {row[0]:15s}: {row[1]:4d} rows  {row[2]} → {row[3]}")

cur.execute("SELECT COUNT(*) FROM all_appointments")
total = cur.fetchone()[0]
print(f"\n  TOTAL: {total} appointments")

cur.close()
conn.close()
print("\nDone! Run this script anytime to sync new records from booknetic/hotboat.")
