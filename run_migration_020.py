"""Migration 020: add variants JSONB column to alojamientos + seed real prices."""
import os, sys, json
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from dotenv import load_dotenv
load_dotenv()
import psycopg2

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

cur.execute("""
ALTER TABLE alojamientos
ADD COLUMN IF NOT EXISTS variants JSONB DEFAULT '[]';
""")

OPEN_SKY_VARIANTS = json.dumps([
    {"name": "Domo con Tina de Baño",   "price_per_night": 100000, "cost_per_night": 0, "capacity": 2, "description": "Domo transparente con tina de baño interior, vista a las estrellas"},
    {"name": "Domo con Hidromasaje",     "price_per_night": 120000, "cost_per_night": 0, "capacity": 2, "description": "Domo transparente con hidromasaje interior, experiencia premium"},
])

RELIKURA_VARIANTS = json.dumps([
    {"name": "Cabaña 2 personas", "price_per_night": 60000,  "cost_per_night": 0, "capacity": 2, "description": "Cabaña junto al río con tinaja, ideal para parejas"},
    {"name": "Cabaña 4 personas", "price_per_night": 80000,  "cost_per_night": 0, "capacity": 4, "description": "Cabaña espaciosa junto al río, ideal para familias"},
    {"name": "Cabaña 6 personas", "price_per_night": 100000, "cost_per_night": 0, "capacity": 6, "description": "Cabaña grande junto al río, perfecta para grupos"},
    {"name": "Hostal",            "price_per_night": 20000,  "cost_per_night": 0, "capacity": 1, "description": "Hostal económico por persona, tinaja compartida"},
])

cur.execute("""
UPDATE alojamientos SET
    price_from = 100000,
    variants = %s
WHERE slug = 'open-sky';
""", (OPEN_SKY_VARIANTS,))

cur.execute("""
UPDATE alojamientos SET
    price_from = 20000,
    variants = %s
WHERE slug = 'relikura';
""", (RELIKURA_VARIANTS,))

conn.commit()

cur.execute("SELECT slug, name, price_from, variants FROM alojamientos ORDER BY display_order")
for r in cur.fetchall():
    slug, name, price, variants = r
    vlist = json.loads(variants) if isinstance(variants, str) else (variants or [])
    print(f"\n{slug} | {name} | precio_desde=${price:,}")
    for v in vlist:
        print(f"  - {v['name']}: ${v['price_per_night']:,}/noche ({v['capacity']}p)")

cur.close(); conn.close()
print("\nMigration 020 done.")
