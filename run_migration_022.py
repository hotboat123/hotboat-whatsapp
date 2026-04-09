"""Migration 022: add owner_whatsapp column to alojamientos table."""
import os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from dotenv import load_dotenv
load_dotenv()
import psycopg2

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

cur.execute("ALTER TABLE alojamientos ADD COLUMN IF NOT EXISTS owner_whatsapp VARCHAR(50) DEFAULT '';")
print("Column owner_whatsapp added.")

# Seed known numbers for existing accommodations
cur.execute("UPDATE alojamientos SET owner_whatsapp='+56964634691' WHERE slug LIKE '%open-sky%' OR slug LIKE '%sky%';")
cur.execute("UPDATE alojamientos SET owner_whatsapp='+56990508175' WHERE slug LIKE '%relikura%';")
print("Known numbers seeded.")

conn.commit()

# Verify
cur.execute("SELECT slug, name, owner_whatsapp FROM alojamientos ORDER BY display_order, id")
print("\nFinal state:")
for r in cur.fetchall():
    print(f"  {r[0]:<35} | {r[2]}")

cur.close(); conn.close()
print("\nMigration 022 done.")
