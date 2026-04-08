"""Migration 019: create alojamientos table for admin CMS."""
import os, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
from dotenv import load_dotenv
load_dotenv()
import psycopg2

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS alojamientos (
    id             SERIAL PRIMARY KEY,
    slug           TEXT UNIQUE NOT NULL,
    name           TEXT NOT NULL,
    icon           TEXT DEFAULT '🏠',
    description    TEXT,
    price_from     INTEGER DEFAULT 0,
    cost_from      INTEGER DEFAULT 0,
    image_path     TEXT,
    is_active      BOOLEAN DEFAULT TRUE,
    display_order  INTEGER DEFAULT 0,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

INSERT INTO alojamientos (slug, name, icon, description, price_from, cost_from, display_order) VALUES
  ('open-sky',    'Open Sky',           '🌌', 'Domos románticos con vista a las estrellas', 0, 0, 0),
  ('relikura',    'Raíces de Relikura', '🌿', 'Cabañas y hostal junto al río',              0, 0, 1)
ON CONFLICT (slug) DO NOTHING;
""")
conn.commit()

cur.execute("SELECT id, slug, name, is_active FROM alojamientos ORDER BY display_order")
rows = cur.fetchall()
print("Alojamientos creados:")
for r in rows:
    print(f"  id={r[0]}  slug={r[1]}  name={r[2]}  active={r[3]}")

cur.close(); conn.close()
print("Migration 019 done.")
