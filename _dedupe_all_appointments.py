"""
Elimina duplicados típicos en all_appointments:

1) Filas source='booknetic' cuando ya existe source='sheets' con el mismo
   appointment_id (misma reserva: viene de reservas_con_extras + sync Booknetic).

2) Filas booknetic repetidas con el mismo source_id (se queda la de id mínimo).

Ejecutar: python _dedupe_all_appointments.py
"""
import os
import psycopg

db = os.environ.get("DATABASE_URL", "")
if not db:
    with open(".env") as f:
        for line in f:
            if line.startswith("DATABASE_URL"):
                db = line.split("=", 1)[1].strip()
                break

print("Conectando...")
with psycopg.connect(db) as conn:
    with conn.cursor() as cur:
        # 1) booknetic duplicado de sheets
        cur.execute(
            """
            DELETE FROM all_appointments a
            USING all_appointments b
            WHERE a.source = 'booknetic'
              AND b.source = 'sheets'
              AND b.appointment_id IS NOT NULL
              AND TRIM(b.appointment_id::text) = TRIM(a.source_id::text)
            """
        )
        n1 = cur.rowcount
        print(f"Eliminadas {n1} filas booknetic que ya estaban en sheets (mismo appointment_id)")

        # 2) booknetic duplicado entre sí (mismo source_id)
        cur.execute(
            """
            DELETE FROM all_appointments a
            WHERE a.source = 'booknetic'
              AND EXISTS (
                SELECT 1 FROM all_appointments b
                WHERE b.source = 'booknetic'
                  AND b.source_id = a.source_id
                  AND b.id < a.id
              )
            """
        )
        n2 = cur.rowcount
        print(f"Eliminadas {n2} filas booknetic duplicadas (mismo source_id)")

    conn.commit()
print("Listo.")
