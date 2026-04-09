"""Migration 021: flatten alojamientos variants into individual rows.
Each variant becomes its own row with capacity, description, and group_name.
"""
import os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from dotenv import load_dotenv
load_dotenv()
import psycopg2

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

# 1. Add new columns
cur.execute("ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS capacity INTEGER DEFAULT 2;")
cur.execute("ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';")
cur.execute("ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS group_name VARCHAR(200) DEFAULT '';")

print("Columns added.")

# 2. Remove parent rows (their variants will become individual rows)
cur.execute("DELETE FROM alojamientos WHERE slug IN ('open-sky', 'relikura');")
print("Parent rows deleted.")

# 3. Insert 6 individual rows — one per accommodation option
rows = [
    # Open Sky
    ("open-sky-domo-tina",  "Open Sky – Domo con Tina de Baño",  "Open Sky",
     100000, 0, 2,
     "Domo transparente con tina de baño interior, vista a las estrellas. Perfecto para parejas románticas. 🌌",
     True, 10),
    ("open-sky-domo-hidro",  "Open Sky – Domo con Hidromasaje",    "Open Sky",
     120000, 0, 2,
     "Domo transparente con hidromasaje interior, la experiencia más exclusiva y premium. 🌟",
     True, 11),
    # Raíces de Relikura
    ("relikura-cabana-2",   "Raíces de Relikura – Cabaña 2 personas",  "Raíces de Relikura",
     60000, 0, 2,
     "Cabaña acogedora junto al río con tinaja exterior, ideal para parejas. 🌿",
     True, 20),
    ("relikura-cabana-4",   "Raíces de Relikura – Cabaña 4 personas",  "Raíces de Relikura",
     80000, 0, 4,
     "Cabaña espaciosa junto al río con tinaja, ideal para familias. 🏡",
     True, 21),
    ("relikura-cabana-6",   "Raíces de Relikura – Cabaña 6 personas",  "Raíces de Relikura",
     100000, 0, 6,
     "Cabaña grande junto al río, perfecta para grupos y familias grandes. 👨‍👩‍👧‍👦",
     True, 22),
    ("relikura-hostal",     "Raíces de Relikura – Hostal",              "Raíces de Relikura",
     20000, 0, 1,
     "Hostal económico por persona junto al río, con tinaja compartida y actividades disponibles. 🎒",
     True, 23),
]

for slug, name, group_name, price, cost, capacity, desc, active, order_ in rows:
    cur.execute(
        """INSERT INTO alojamientos
           (slug, name, group_name, price_from, cost_from, capacity, description, is_active, display_order)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (slug) DO UPDATE SET
             name=EXCLUDED.name, group_name=EXCLUDED.group_name,
             price_from=EXCLUDED.price_from, cost_from=EXCLUDED.cost_from,
             capacity=EXCLUDED.capacity, description=EXCLUDED.description,
             is_active=EXCLUDED.is_active, display_order=EXCLUDED.display_order
        """,
        (slug, name, group_name, price, cost, capacity, desc, active, order_)
    )
    print(f"  ✓ {slug}: {name} — ${price:,}/noche — {capacity}p")

conn.commit()

# Verify
cur.execute("SELECT slug, name, price_from, capacity, group_name FROM alojamientos ORDER BY display_order, id")
print("\nFinal state:")
for r in cur.fetchall():
    print(f"  {r[4]:<25} | {r[0]:<30} | {r[1]:<45} | ${r[2]:>8,}/noche | {r[3]}p")

cur.close(); conn.close()
print("\nMigration 021 done.")
