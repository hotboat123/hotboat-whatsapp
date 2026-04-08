"""Migration 017 – experiences, packs & extras_bookings tables."""
import os, sys, json
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
from dotenv import load_dotenv
load_dotenv()
import psycopg2

SQL = """
-- Otras experiencias administrables
CREATE TABLE IF NOT EXISTS experiences (
    id             SERIAL PRIMARY KEY,
    slug           TEXT UNIQUE NOT NULL,
    name           TEXT NOT NULL,
    icon           TEXT DEFAULT '🚣',
    description    TEXT,
    price_per_person INTEGER DEFAULT 0,
    cost_per_person  INTEGER DEFAULT 0,
    image_path     TEXT,
    is_active      BOOLEAN DEFAULT TRUE,
    display_order  INTEGER DEFAULT 0,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Packs completos administrables
CREATE TABLE IF NOT EXISTS packs (
    id             SERIAL PRIMARY KEY,
    slug           TEXT UNIQUE NOT NULL,
    name           TEXT NOT NULL,
    icon           TEXT DEFAULT '🎁',
    description    TEXT,
    personas       TEXT DEFAULT '2 personas',
    price_from     INTEGER DEFAULT 0,
    cost_from      INTEGER DEFAULT 0,
    image_path     TEXT,
    includes       JSONB DEFAULT '[]',
    is_active      BOOLEAN DEFAULT TRUE,
    display_order  INTEGER DEFAULT 0,
    created_at     TIMESTAMPTZ DEFAULT NOW(),
    updated_at     TIMESTAMPTZ DEFAULT NOW()
);

-- Reservas de extras (packs / experiencias / alojamiento) con rango de fechas
CREATE TABLE IF NOT EXISTS extras_bookings (
    id             SERIAL PRIMARY KEY,
    booking_ref    TEXT,
    customer_name  TEXT NOT NULL,
    customer_phone TEXT,
    item_type      TEXT NOT NULL,   -- 'experience' | 'pack' | 'alojamiento'
    item_slug      TEXT NOT NULL,
    item_name      TEXT NOT NULL,
    start_date     DATE NOT NULL,
    end_date       DATE,
    num_people     INTEGER DEFAULT 1,
    total_price    INTEGER DEFAULT 0,
    deposit_paid   INTEGER DEFAULT 0,
    status         TEXT DEFAULT 'pendiente',
    notes          TEXT,
    created_at     TIMESTAMPTZ DEFAULT NOW()
);
"""

EXPERIENCES_SEED = [
    ("rafting",    "Rafting",             "🚣", "Rio Trancura · Bajo o Alto",    30000, 15000,
     "/media/images/experiencias/rafting/Rafting.jpg",        True,  1),
    ("cabalgata",  "Cabalgata",           "🐴", "Parque Ojos del Caburguá",      50000, 25000,
     "/media/images/experiencias/cabalgata/CAbalgatas.jpg",   True,  2),
    ("velerismo",  "Navegacion a Vela",   "⛵", "Lago Villarrica",               50000, 25000,
     "/media/images/experiencias/velerismo/Velerismo.jpg",    True,  3),
    ("volcan",     "Subida al Volcan",    "🌋", "Trek guiado desde Pucon",       40000, 20000, None, True, 4),
    ("auto",       "Arriendo Vehiculo",   "🚗", "$50.000/dia",                   50000, 25000, None, True, 5),
]

PACKS_SEED = [
    ("romantico", "Pack Romantico",   "💕", "Escapada romantica con todo incluido", "2 personas", 400000, 200000,
     "/media/images/packs/pack_romantico/01-pack-romantico.jpg",
     '["Open Sky Domo (1-2 noches)", "Paseo en HotBoat (2p)", "Navegacion a velero", "Modo Romantico a bordo"]', True, 1),
    ("familiar",  "Pack Familiar",    "👨‍👩‍👧‍👦", "Aventura familiar en la naturaleza", "4 personas", 650000, 300000,
     "/media/images/packs/pack_familiar/01-pack-familiar.jpg",
     '["Cabana Relikura 4p (1-2 noches)", "Paseo en HotBoat (4p)", "Rafting Bajo", "Cabalgata"]', True, 2),
    ("amigos",    "Pack Amigos",      "👥", "Experiencia grupal de aventura", "6 personas", 700000, 350000,
     "/media/images/packs/pack_amigos/01-pack-amigos.jpg",
     '["Cabana Relikura 6p (1-2 noches)", "Paseo en HotBoat (6p)", "Rafting Alto", "Extras a bordo"]', True, 3),
]


def run():
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    print("Creating tables…")
    cur.execute(SQL)

    print("Seeding experiences…")
    for row in EXPERIENCES_SEED:
        cur.execute(
            """INSERT INTO experiences
               (slug,name,icon,description,price_per_person,cost_per_person,image_path,is_active,display_order)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (slug) DO NOTHING""",
            row,
        )

    print("Seeding packs…")
    for row in PACKS_SEED:
        cur.execute(
            """INSERT INTO packs
               (slug,name,icon,description,personas,price_from,cost_from,image_path,includes,is_active,display_order)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON CONFLICT (slug) DO NOTHING""",
            row,
        )

    conn.commit()
    cur.close()
    conn.close()
    print("Migration 017 complete.")


if __name__ == "__main__":
    run()
