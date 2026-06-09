"""
Migration 032 — Add Pack Termas Angostura
Inserts the "Termas Angostura" complete pack (HotBoat + Termas + 2 noches cabaña
+ arriendo de auto + pensión completa) if it doesn't already exist.
"""
import json
import os
import psycopg

PACK = {
    "slug":        "termas-angostura",
    "name":        "Pack Termas Angostura",
    "icon":        "♨️",
    "description": (
        "¿Te animas a una pausa?\n\n"
        "Escápate a una cabaña rodeada de bosque nativo, donde el tiempo se detiene. "
        "Durante dos noches disfrutarás de desayuno, almuerzo y cena en el restaurante "
        "del complejo, y de acceso ilimitado a las piscinas de aguas termales al aire libre.\n\n"
        "Y como broche de oro: la experiencia única e inigualable del HotBoat — una tinaja "
        "flotante que navega en medio de la laguna, rodeada de volcanes y bosque nativo. "
        "Una sensación que no encontrarás en ningún otro lugar del mundo."
    ),
    "personas":    "2 personas",
    "price_from":  399990,
    "cost_from":   0,
    "image_path":  None,
    "includes": [
        "2 noches en Cabaña exclusiva Termas Angostura",
        "Acceso ilimitado a Termas Angostura",
        "Pensión completa (desayuno, almuerzo y cena)",
        "Paseo en HotBoat (2 personas)",
    ],
    "is_active":      True,
    "display_order":  4,
}


def run():
    conn = psycopg.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO packs
          (slug, name, icon, description, personas,
           price_from, cost_from, image_path, includes,
           is_active, display_order)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (slug) DO UPDATE SET
          name         = EXCLUDED.name,
          icon         = EXCLUDED.icon,
          description  = EXCLUDED.description,
          personas     = EXCLUDED.personas,
          price_from   = EXCLUDED.price_from,
          cost_from    = EXCLUDED.cost_from,
          includes     = EXCLUDED.includes,
          is_active    = EXCLUDED.is_active,
          display_order = EXCLUDED.display_order
        """,
        (
            PACK["slug"],
            PACK["name"],
            PACK["icon"],
            PACK["description"],
            PACK["personas"],
            PACK["price_from"],
            PACK["cost_from"],
            PACK["image_path"],
            json.dumps(PACK["includes"], ensure_ascii=False),
            PACK["is_active"],
            PACK["display_order"],
        ),
    )

    conn.commit()
    cur.close()
    conn.close()
    print("Migration 032 complete — Pack Termas Angostura inserted/updated.")


if __name__ == "__main__":
    run()
