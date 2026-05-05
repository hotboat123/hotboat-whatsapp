"""Inspect Booknetic-synced rows in all_appointments (source='booknetic')."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from app.db.connection import get_connection


def main():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT MIN(fecha), MAX(fecha), COUNT(*)
                FROM all_appointments
                WHERE source = 'booknetic'
                """
            )
            row = cur.fetchone()
            print(f"all_appointments (booknetic): min={row[0]}, max={row[1]}, total={row[2]}")

            cur.execute(
                """
                SELECT source_id, nombre_cliente, fecha, hora,
                       COALESCE(telefono::text, '') AS phone,
                       status
                FROM all_appointments
                WHERE source = 'booknetic'
                ORDER BY fecha DESC NULLS LAST, hora DESC NULLS LAST
                LIMIT 5
                """
            )
            print("sample:")
            for r in cur.fetchall():
                print(" ", r)


if __name__ == "__main__":
    main()
