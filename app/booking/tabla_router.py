"""Client-facing + admin endpoints for tabla (food board) feature."""
import json as _json
import logging
import os
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

logger = logging.getLogger(__name__)
tabla_router = APIRouter()

TABLA_HTML_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "tabla.html")

TABLA_CATALOG = {
    "salada": {
        "label": "Tabla Salada",
        "emoji": "🧀",
        "tier1": ["Aceitunas drvillanas 200gr", "Hummus Buka 220g", "Papas Lay's 150g"],
        "tier2": ["Jamón serrano", "Salame premium", "Cajú premium", "Cranberries 150gr",
                  "Pepinillos 200gr", "Queso crema + soya y sésamo", "Grisines"],
        "tier3": ["Maní 150gr", "Crackers 90gr", "Super 8", "Galletas obsesión"],
    },
    "dulce": {
        "label": "Tabla Dulce",
        "emoji": "🍫",
        "tier1": ["Chocolate sahnenuss 90gr"],
        "tier2": ["Queso crema + mermelada pimentón", "Galletas Chip Choco 150gr"],
        "tier3": ["Alfajor entrelagos", "Super 8", "Galletas obsesión"],
    },
    "arma": {
        "label": "Arma tu Tabla",
        "emoji": "🎨",
        "tier1": ["Aceitunas sevillanas 200gr", "Hummus Buka 220g", "Papas Lay's 150g",
                  "Chocolate sahnenuss 90gr", "Jamón serrano 60gr"],
        "tier2": ["Salame premium", "Cajú premium", "Cranberries 150gr", "Pepinillos 200gr",
                  "Queso crema + mermelada pimentón", "Queso crema + soya y sésamo", "Grisines 120gr"],
        "tier3": ["Chocolate vegano 140gr", "Maní 150gr", "Alfajor entrelagos",
                  "Crackers 90gr", "Super 8", "Galletas obsesión"],
    },
    "vegana": {
        "label": "Tabla Vegana",
        "emoji": "🥑",
        "tier1": ["Aceitunas sevillanas 200gr", "Hummus Buka 220g"],
        "tier2": ["Cajú premium", "Cranberries 150gr", "Pepinillos 200gr", "Grisines 120gr"],
        "tier3": ["Chocolate vegano 140gr", "Maní 150gr", "Crackers 90gr"],
    },
}

DEFAULT_PRICE = 25000

# All unique ingredients across all tabla types with their purchase cost (CLP)
# Prices from supplier catalog. show_in_booking=False so they don't appear
# in the regular booking extras dropdown — only used in tabla flow + stock.
_TABLA_INGREDIENTS = [
    ("Aceitunas drvillanas 200gr",          3090, "🫒"),
    ("Aceitunas sevillanas 200gr",          3090, "🫒"),
    ("Hummus Buka 220g",                    2595, "🥙"),
    ("Papas Lay's 150g",                    2499, "🍟"),
    ("Galletas Chip Choco 150gr",           2599, "🍪"),
    ("Chocolate sahnenuss 90gr",            2495, "🍫"),
    ("Jamón serrano",                       2100, "🥩"),
    ("Jamón serrano 60gr",                  2100, "🥩"),
    ("Salame premium",                      2100, "🍖"),
    ("Cajú premium",                        2100, "🥜"),
    ("Queso crema + mermelada pimentón",    2000, "🧀"),
    ("Cranberries 150gr",                   1990, "🫐"),
    ("Pepinillos 200gr",                    1799, "🥒"),
    ("Queso crema + soya y sésamo",         1750, "🧀"),
    ("Grisines",                            1690, "🥖"),
    ("Grisines 120gr",                      1690, "🥖"),
    ("Chocolate vegano 140gr",              1248, "🍫"),
    ("Maní 150gr",                           999, "🥜"),
    ("Galletas obsesión",                    999, "🍪"),
    ("Alfajor entrelagos",                   998, "🍬"),
    ("Crackers 90gr",                        799, "🍘"),
    ("Super 8",                              399, "🍫"),
]


def _ensure_tabla_table() -> None:
    """Create tabla_selections table if it doesn't exist yet (idempotent)."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tabla_selections (
                  id           SERIAL PRIMARY KEY,
                  booking_ref  VARCHAR(50) UNIQUE NOT NULL,
                  tabla_type   VARCHAR(50),
                  elige_1      TEXT,
                  elige_2      JSONB DEFAULT '[]',
                  elige_3      JSONB DEFAULT '[]',
                  completed_at TIMESTAMP WITH TIME ZONE,
                  created_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_tabla_booking_ref ON tabla_selections(booking_ref);
            """)
            conn.commit()


def _ensure_catalog_table() -> None:
    """Create tabla_catalog_items table if not exists (idempotent)."""
    from app.db.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS tabla_catalog_items (
                  id          SERIAL PRIMARY KEY,
                  tabla_type  VARCHAR(50) NOT NULL,
                  tier        INTEGER NOT NULL CHECK (tier IN (1, 2, 3)),
                  ingredient  TEXT NOT NULL,
                  sort_order  INTEGER DEFAULT 0,
                  UNIQUE (tabla_type, tier, ingredient)
                );
                CREATE INDEX IF NOT EXISTS idx_tci_type ON tabla_catalog_items(tabla_type, tier);
            """)
            conn.commit()


def _seed_catalog_defaults() -> None:
    """Seed the DB catalog from hardcoded TABLA_CATALOG defaults.
    Updates sort_order on conflict so existing admin-added ingredients are preserved
    but the canonical defaults always have correct ordering."""
    from app.db.connection import get_connection

    rows = []
    for t_type, cat in TABLA_CATALOG.items():
        for tier_num, key in ((1, "tier1"), (2, "tier2"), (3, "tier3")):
            for i, ing in enumerate(cat[key]):
                rows.append((t_type, tier_num, ing, i))

    with get_connection() as conn:
        with conn.cursor() as cur:
            for t_type, tier_num, ing, sort_order in rows:
                cur.execute(
                    """INSERT INTO tabla_catalog_items (tabla_type, tier, ingredient, sort_order)
                       VALUES (%s, %s, %s, %s)
                       ON CONFLICT (tabla_type, tier, ingredient) DO UPDATE
                           SET sort_order = EXCLUDED.sort_order""",
                    (t_type, tier_num, ing, sort_order),
                )
        conn.commit()


def _out_of_stock_ingredients() -> set:
    """Return a set of lowercased ingredient names that are out of stock across
    ALL matching stock products. Matching mirrors the deduction logic, which
    looks up stock_products by LOWER(name). When duplicate products share a
    name, the ingredient is considered out of stock only if every duplicate is
    depleted (MAX current_stock <= 0) — so a name with stock in any row stays."""
    from app.db.connection import get_connection

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT LOWER(name)
                    FROM stock_products
                    GROUP BY LOWER(name)
                    HAVING MAX(current_stock) <= 0
                """)
                return {r[0] for r in cur.fetchall()}
    except Exception as e:
        logger.warning("_out_of_stock_ingredients skipped: %s", e)
        return set()


def _filter_catalog_by_stock(catalog: dict) -> dict:
    """Remove ingredients whose linked stock product is out of stock so clients
    can't pick items we can't serve. Ingredients with no matching stock product
    (no tracking) are always kept. Builds fresh lists to avoid mutating
    TABLA_CATALOG defaults."""
    out = _out_of_stock_ingredients()
    if not out:
        return catalog
    result = {}
    for t_type, cat in catalog.items():
        new_cat = {**cat}
        for key in ("tier1", "tier2", "tier3"):
            if key in new_cat:
                new_cat[key] = [ing for ing in new_cat[key] if ing.lower() not in out]
        result[t_type] = new_cat
    return result


def _get_catalog_from_db(filter_stock: bool = True) -> dict:
    """Return catalog in same format as TABLA_CATALOG, reading from DB.
    Falls back to hardcoded TABLA_CATALOG if DB not ready or empty.
    When filter_stock=True (default), ingredients whose linked stock product is
    at 0 are removed so out-of-stock items don't appear in the tabla picker."""
    from app.db.connection import get_connection

    catalog = None
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT tabla_type, tier, ingredient FROM tabla_catalog_items ORDER BY tabla_type, tier, sort_order, ingredient"
                )
                rows = cur.fetchall()
        if rows:
            catalog = {k: {**v, "tier1": [], "tier2": [], "tier3": []} for k, v in TABLA_CATALOG.items()}
            for t_type, tier_num, ing in rows:
                if t_type in catalog:
                    catalog[t_type][f"tier{tier_num}"].append(ing)
    except Exception as e:
        logger.warning("_get_catalog_from_db fallback to hardcoded: %s", e)

    if catalog is None:
        # DB table empty or unavailable — use hardcoded defaults so the picker always works
        catalog = {k: {**v} for k, v in TABLA_CATALOG.items()}

    if filter_stock:
        catalog = _filter_catalog_by_stock(catalog)
    return catalog


def _seed_tabla_products() -> None:
    """Insert tabla ingredients into extras_visibility with their purchase cost.
    Uses ON CONFLICT DO NOTHING — never overwrites admin edits.
    show_in_booking=False so they don't appear in the regular extras dropdown.
    """
    from app.db.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Ensure required columns exist first
            for col_def in ["costo INTEGER", "icon TEXT", "precio_venta INTEGER",
                            "name TEXT", "description TEXT"]:
                cur.execute(f"ALTER TABLE extras_visibility ADD COLUMN IF NOT EXISTS {col_def}")
            for name, cost, icon in _TABLA_INGREDIENTS:
                cur.execute(
                    """
                    INSERT INTO extras_visibility
                        (extra_name_lower, name, show_in_booking, costo, precio_venta, icon, sort_order, updated_at)
                    VALUES (%s, %s, false, %s, 0, %s, 900, NOW())
                    ON CONFLICT (extra_name_lower) DO NOTHING
                    """,
                    (name.lower(), name, cost, icon),
                )
            # Remove any duplicate tabla entries with spaces or alternate spellings
            cur.execute("""
                DELETE FROM extras_visibility
                WHERE extra_name_lower != 'tabla_de_picoteo'
                  AND REPLACE(LOWER(extra_name_lower), ' ', '_') = 'tabla_de_picoteo'
            """)
            # Seed the master "Tabla de picoteo" booking extra — always restore/update
            cur.execute(
                """
                INSERT INTO extras_visibility
                    (extra_name_lower, name, show_in_booking, costo, precio_venta, icon, sort_order, updated_at)
                VALUES ('tabla_de_picoteo', 'Tabla de picoteo', true, 10000, 20000, '🧺', 80, NOW())
                ON CONFLICT (extra_name_lower) DO UPDATE
                    SET show_in_booking = TRUE,
                        user_hidden     = FALSE,
                        costo           = 10000,
                        precio_venta    = 20000,
                        name            = COALESCE(EXCLUDED.name, extras_visibility.name),
                        icon            = COALESCE(NULLIF(extras_visibility.icon,''), EXCLUDED.icon),
                        sort_order      = EXCLUDED.sort_order,
                        updated_at      = NOW()
                """,
            )
        conn.commit()
    logger.info("Tabla ingredients seeded into extras_visibility (%d products)", len(_TABLA_INGREDIENTS))


def _tabla_html() -> str:
    with open(TABLA_HTML_PATH, "r", encoding="utf-8") as f:
        return f.read()


def _resolve_booking(booking_ref: str) -> Optional[dict]:
    from app.db.connection import get_connection

    if not booking_ref:
        return None
    if booking_ref.upper().startswith("AA-"):
        try:
            apt_id = int(booking_ref[3:])
        except ValueError:
            return None
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT nombre_cliente, fecha, hora, num_personas, email FROM all_appointments WHERE id=%s",
                    (apt_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                return {
                    "customer_name": row[0] or "",
                    "booking_date": str(row[1]) if row[1] else "",
                    "booking_time": str(row[2])[:5] if row[2] else "",
                    "num_people": row[3],
                    "customer_email": row[4] or "",
                    "booking_ref": booking_ref,
                }
    from app.booking.db import get_booking_by_ref
    b = get_booking_by_ref(booking_ref)
    if b:
        return {
            "customer_name": b.get("customer_name") or "",
            "booking_date": str(b.get("booking_date") or ""),
            "booking_time": str(b.get("booking_time") or "")[:5],
            "num_people": b.get("num_people"),
            "customer_email": b.get("customer_email") or "",
            "booking_ref": booking_ref,
        }
    return None


def _get_apt_id(booking_ref: str) -> Optional[int]:
    from app.db.connection import get_connection

    if booking_ref.upper().startswith("AA-"):
        try:
            return int(booking_ref[3:])
        except ValueError:
            return None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM all_appointments WHERE source='hotboat_web' AND source_id=%s LIMIT 1",
                (booking_ref,),
            )
            row = cur.fetchone()
            return row[0] if row else None


class TablaPayload(BaseModel):
    tabla_type: str
    elige_1: str
    elige_2: List[str]
    elige_3: List[str]
    price: Optional[int] = DEFAULT_PRICE


@tabla_router.get("/tabla/{booking_ref:path}", response_class=HTMLResponse)
async def serve_tabla_form(booking_ref: str):
    try:
        return HTMLResponse(content=_tabla_html())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Página de tabla no encontrada")


@tabla_router.get("/api/tabla/catalog")
async def get_tabla_catalog():
    return {"catalog": _get_catalog_from_db(), "default_price": DEFAULT_PRICE}


@tabla_router.get("/api/tabla/{booking_ref}/info")
async def get_tabla_info(booking_ref: str):
    from app.db.connection import get_connection

    if booking_ref.lower() == "demo":
        return {
            "booking_ref": "demo",
            "customer_name": None,
            "booking_date": None,
            "booking_time": None,
            "catalog": _get_catalog_from_db(),
            "default_price": DEFAULT_PRICE,
            "existing": None,
            "is_demo": True,
        }

    booking = _resolve_booking(booking_ref)
    if not booking:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")

    existing = None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT tabla_type, elige_1, elige_2, elige_3, completed_at FROM tabla_selections WHERE booking_ref=%s",
                (booking_ref,),
            )
            row = cur.fetchone()
            if row:
                existing = {
                    "tabla_type": row[0],
                    "elige_1": row[1],
                    "elige_2": row[2] if row[2] is not None else [],
                    "elige_3": row[3] if row[3] is not None else [],
                    "completed_at": str(row[4]) if row[4] else None,
                }

    return {
        "booking_ref": booking["booking_ref"],
        "customer_name": booking["customer_name"],
        "booking_date": booking["booking_date"],
        "booking_time": booking["booking_time"],
        "catalog": _get_catalog_from_db(),
        "default_price": DEFAULT_PRICE,
        "existing": existing,
    }


@tabla_router.post("/api/tabla/{booking_ref}")
async def submit_tabla(booking_ref: str, payload: TablaPayload):
    from app.db.connection import get_connection

    if booking_ref.lower() == "demo":
        return {"status": "ok", "demo": True}

    booking = _resolve_booking(booking_ref)
    if not booking:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")

    # Validate against the full catalog (not stock-filtered) so a valid
    # ingredient name isn't rejected just because it momentarily ran out.
    live_catalog = _get_catalog_from_db(filter_stock=False)
    if payload.tabla_type not in live_catalog:
        raise HTTPException(status_code=400, detail="Tipo de tabla inválido")

    cat = live_catalog[payload.tabla_type]
    if payload.elige_1 not in cat["tier1"]:
        raise HTTPException(status_code=400, detail="Ingrediente tier 1 inválido")
    if len(payload.elige_2) != 2 or not all(i in cat["tier2"] for i in payload.elige_2):
        raise HTTPException(status_code=400, detail="Selección tier 2 inválida (necesita exactamente 2)")
    if len(payload.elige_3) != 3 or not all(i in cat["tier3"] for i in payload.elige_3):
        raise HTTPException(status_code=400, detail="Selección tier 3 inválida (necesita exactamente 3)")

    price = payload.price if payload.price and payload.price > 0 else DEFAULT_PRICE
    now = datetime.now(timezone.utc)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO tabla_selections (booking_ref, tabla_type, elige_1, elige_2, elige_3, completed_at)
                VALUES (%s, %s, %s, %s::jsonb, %s::jsonb, %s)
                ON CONFLICT (booking_ref) DO UPDATE SET
                  tabla_type   = EXCLUDED.tabla_type,
                  elige_1      = EXCLUDED.elige_1,
                  elige_2      = EXCLUDED.elige_2,
                  elige_3      = EXCLUDED.elige_3,
                  completed_at = EXCLUDED.completed_at
                """,
                (
                    booking_ref,
                    payload.tabla_type,
                    payload.elige_1,
                    _json.dumps(payload.elige_2, ensure_ascii=False),
                    _json.dumps(payload.elige_3, ensure_ascii=False),
                    now,
                ),
            )

            apt_id = _get_apt_id(booking_ref)
            if apt_id:
                tabla_key = f"tabla__{payload.tabla_type}"
                tabla_val = {
                    "qty": 1,
                    "unit_price": price,
                    "name": f"{cat['emoji']} {cat['label']}",
                    "tabla_type": payload.tabla_type,
                    "elige_1": payload.elige_1,
                    "elige_2": payload.elige_2,
                    "elige_3": payload.elige_3,
                }
                # Remove any existing tabla__ key, then merge new one
                cur.execute(
                    """
                    UPDATE all_appointments
                    SET extras_json = (
                        COALESCE(
                          (SELECT jsonb_object_agg(k, v)
                           FROM jsonb_each(COALESCE(extras_json, '{}')) t(k, v)
                           WHERE k NOT LIKE 'tabla\\_%%'),
                          '{}'::jsonb
                        ) || %s::jsonb
                    )
                    WHERE id = %s
                    """,
                    (
                        _json.dumps({tabla_key: tabla_val}, ensure_ascii=False),
                        apt_id,
                    ),
                )
        conn.commit()

    return {"ok": True, "tabla_type": payload.tabla_type}


# ── Admin: Tabla Catalog CRUD ─────────────────────────────────────────────────

@tabla_router.get("/api/admin/tabla/catalog")
async def admin_get_catalog():
    from app.db.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, tabla_type, tier, ingredient, sort_order
                FROM tabla_catalog_items
                ORDER BY tabla_type, tier, sort_order, ingredient
            """)
            rows = [{"id": r[0], "tabla_type": r[1], "tier": r[2], "ingredient": r[3], "sort_order": r[4]}
                    for r in cur.fetchall()]
    # Also return labels/emojis from hardcoded TABLA_CATALOG
    types_meta = {k: {"label": v["label"], "emoji": v["emoji"]} for k, v in TABLA_CATALOG.items()}
    return {"items": rows, "types_meta": types_meta}


@tabla_router.post("/api/admin/tabla/catalog/item")
async def admin_add_catalog_item(request: Request):
    from app.db.connection import get_connection

    body = await request.json()
    tabla_type = (body.get("tabla_type") or "").strip()
    tier = int(body.get("tier") or 0)
    ingredient = (body.get("ingredient") or "").strip()

    if tabla_type not in TABLA_CATALOG:
        raise HTTPException(status_code=400, detail="Tipo de tabla inválido")
    if tier not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="Tier debe ser 1, 2 o 3")
    if not ingredient:
        raise HTTPException(status_code=400, detail="Ingrediente requerido")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO tabla_catalog_items (tabla_type, tier, ingredient, sort_order)
                   VALUES (%s, %s, %s,
                     COALESCE((SELECT MAX(sort_order)+1 FROM tabla_catalog_items
                               WHERE tabla_type=%s AND tier=%s), 0))
                   ON CONFLICT (tabla_type, tier, ingredient) DO NOTHING
                   RETURNING id""",
                (tabla_type, tier, ingredient, tabla_type, tier),
            )
            row = cur.fetchone()
        conn.commit()
    return {"ok": True, "id": row[0] if row else None}


@tabla_router.delete("/api/admin/tabla/catalog/item/{item_id}")
async def admin_delete_catalog_item(item_id: int):
    from app.db.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM tabla_catalog_items WHERE id=%s", (item_id,))
        conn.commit()
    return {"ok": True}


@tabla_router.put("/api/admin/tabla/catalog/item/{item_id}")
async def admin_move_catalog_item(item_id: int, request: Request):
    """Move ingredient to a different tabla_type or tier."""
    from app.db.connection import get_connection

    body = await request.json()
    tabla_type = (body.get("tabla_type") or "").strip()
    tier = int(body.get("tier") or 0)

    if tabla_type and tabla_type not in TABLA_CATALOG:
        raise HTTPException(status_code=400, detail="Tipo de tabla inválido")
    if tier and tier not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="Tier inválido")

    sets = []
    vals = []
    if tabla_type:
        sets.append("tabla_type=%s"); vals.append(tabla_type)
    if tier:
        sets.append("tier=%s"); vals.append(tier)
    if not sets:
        raise HTTPException(status_code=400, detail="Nada que actualizar")

    vals.append(item_id)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE tabla_catalog_items SET {', '.join(sets)} WHERE id=%s",
                vals,
            )
        conn.commit()
    return {"ok": True}
