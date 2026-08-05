"""
Additive migration: merge extras_visibility into stock_products, add
tabla_catalog_items.product_id. Does NOT drop or touch extras_bom /
extras_visibility / reservation_consumption — old code keeps working
against them until the new code is deployed. Safe to re-run (idempotent
ALTERs, upserts keyed by id/slug).
"""
import unicodedata
from app.db.connection import get_connection


def norm_name(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


with get_connection() as conn:
    with conn.cursor() as cur:
        # 1. New columns on stock_products
        for col_def in [
            "slug TEXT",
            "show_in_booking BOOLEAN NOT NULL DEFAULT FALSE",
            "sort_order INTEGER NOT NULL DEFAULT 999",
            "precio_venta INTEGER",
            "description TEXT",
            "icon TEXT",
            "user_hidden BOOLEAN NOT NULL DEFAULT FALSE",
            "name_en TEXT",
            "name_pt TEXT",
            "description_en TEXT",
            "description_pt TEXT",
        ]:
            cur.execute(f"ALTER TABLE stock_products ADD COLUMN IF NOT EXISTS {col_def}")
        conn.commit()
        print("stock_products: new columns ensured")

        # 2. Backfill from extras_visibility rows WITH stock_product_id (linked)
        cur.execute("""
            SELECT extra_name_lower, name, show_in_booking, sort_order, description,
                   precio_venta, costo, icon, user_hidden, name_en, name_pt,
                   description_en, description_pt, stock_product_id
            FROM extras_visibility
            WHERE stock_product_id IS NOT NULL
        """)
        linked = cur.fetchall()
        for (slug, name, show_in_booking, sort_order, description, precio_venta,
             costo, icon, user_hidden, name_en, name_pt, description_en,
             description_pt, spid) in linked:
            cur.execute("""
                UPDATE stock_products
                SET slug = %s,
                    name = COALESCE(NULLIF(%s, ''), name),
                    show_in_booking = %s,
                    sort_order = COALESCE(%s, 999),
                    description = %s,
                    precio_venta = %s,
                    icon = %s,
                    user_hidden = %s,
                    name_en = %s, name_pt = %s,
                    description_en = %s, description_pt = %s,
                    cost_per_unit = COALESCE(cost_per_unit, %s, 0)
                WHERE id = %s
            """, (slug, name, bool(show_in_booking), sort_order, description,
                  precio_venta, icon, bool(user_hidden), name_en, name_pt,
                  description_en, description_pt, costo, spid))
        conn.commit()
        print(f"stock_products: {len(linked)} linked extras backfilled")

        # 3. Insert extras_visibility rows WITHOUT stock_product_id as new
        #    stock_products rows with current_stock=NULL (unlimited/not inventory)
        cur.execute("""
            SELECT extra_name_lower, name, show_in_booking, sort_order, description,
                   precio_venta, costo, icon, user_hidden, name_en, name_pt,
                   description_en, description_pt
            FROM extras_visibility
            WHERE stock_product_id IS NULL
        """)
        unlinked = cur.fetchall()
        inserted_ids = {}
        for (slug, name, show_in_booking, sort_order, description, precio_venta,
             costo, icon, user_hidden, name_en, name_pt, description_en,
             description_pt) in unlinked:
            display_name = (name or slug or "").strip() or slug
            cur.execute("""
                INSERT INTO stock_products
                    (name, category, unit, current_stock, min_stock, cost_per_unit,
                     notes, is_active, consumption_qty, slug, show_in_booking,
                     sort_order, description, precio_venta, icon, user_hidden,
                     name_en, name_pt, description_en, description_pt)
                VALUES (%s, 'Extras (sin stock)', 'unidad', NULL, 0, %s,
                        '', TRUE, 1, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s)
                RETURNING id
            """, (display_name, costo or 0, slug, bool(show_in_booking),
                  sort_order, description, precio_venta, icon, bool(user_hidden),
                  name_en, name_pt, description_en, description_pt))
            new_id = cur.fetchone()[0]
            inserted_ids[slug] = new_id
        conn.commit()
        print(f"stock_products: {len(unlinked)} unlinked (service) extras inserted")

        # 4. Verification: show_in_booking counts should match
        cur.execute("SELECT COUNT(*) FROM extras_visibility WHERE show_in_booking = TRUE")
        old_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM stock_products WHERE show_in_booking = TRUE")
        new_count = cur.fetchone()[0]
        print(f"show_in_booking count — old extras_visibility: {old_count}, new stock_products: {new_count}")
        assert old_count == new_count, "MISMATCH — stopping before touching tabla_catalog_items"

        # 5. tabla_catalog_items.product_id
        cur.execute("ALTER TABLE tabla_catalog_items ADD COLUMN IF NOT EXISTS product_id INTEGER REFERENCES stock_products(id)")
        conn.commit()

        cur.execute("SELECT id, name FROM stock_products")
        norm_to_id = {}
        for pid, pname in cur.fetchall():
            norm_to_id.setdefault(norm_name(pname), pid)

        cur.execute("SELECT id, ingredient FROM tabla_catalog_items")
        tci_rows = cur.fetchall()
        unmatched = []
        for tci_id, ingredient in tci_rows:
            pid = norm_to_id.get(norm_name(ingredient))
            if pid:
                cur.execute("UPDATE tabla_catalog_items SET product_id = %s WHERE id = %s", (pid, tci_id))
            else:
                unmatched.append(ingredient)
        conn.commit()
        print(f"tabla_catalog_items: {len(tci_rows)} rows, {len(unmatched)} unmatched")
        if unmatched:
            print("UNMATCHED INGREDIENTS (need manual review):", unmatched)

print("Migration step complete. extras_bom / extras_visibility / reservation_consumption left untouched.")
