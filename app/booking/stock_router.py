"""
Stock management router — /api/admin/stock/...
Handles: products CRUD, bill-of-materials per extra, stock adjustments,
         booking consumption (deducted after reservation date passes), low-stock alerts.
"""
import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.db.connection import get_connection

logger = logging.getLogger(__name__)
stock_router = APIRouter()

ADMIN_NOTIFICATION_EMAIL = "hotboatnotification@gmail.com"


# ─────────────────────────── helpers ────────────────────────────────────────

def _check_auth(key: str):
    pass   # auth disabled — same as rest of admin


def _row_to_dict(cur, row):
    return dict(zip([d.name for d in cur.description], row))


def _ensure_tables():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS stock_products (
                    id SERIAL PRIMARY KEY, name TEXT NOT NULL, category TEXT DEFAULT '',
                    unit TEXT DEFAULT 'unidad', current_stock NUMERIC DEFAULT 0,
                    min_stock NUMERIC DEFAULT 0, cost_per_unit NUMERIC DEFAULT 0,
                    notes TEXT DEFAULT '', is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMPTZ DEFAULT NOW(), updated_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE TABLE IF NOT EXISTS extras_bom (
                    id SERIAL PRIMARY KEY, extra_slug TEXT NOT NULL,
                    product_id INT REFERENCES stock_products(id) ON DELETE CASCADE,
                    quantity NUMERIC DEFAULT 1, is_variant BOOLEAN DEFAULT FALSE,
                    variant_label TEXT DEFAULT '', created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_bom_slug ON extras_bom(extra_slug);
                CREATE TABLE IF NOT EXISTS stock_movements (
                    id SERIAL PRIMARY KEY,
                    product_id INT REFERENCES stock_products(id),
                    product_name TEXT DEFAULT '', delta NUMERIC NOT NULL,
                    reason TEXT DEFAULT '', booking_ref TEXT DEFAULT '',
                    extra_slug TEXT DEFAULT '', notes TEXT DEFAULT '',
                    created_at TIMESTAMPTZ DEFAULT NOW()
                );
                CREATE INDEX IF NOT EXISTS idx_movements_product ON stock_movements(product_id);
                CREATE INDEX IF NOT EXISTS idx_movements_booking  ON stock_movements(booking_ref);
                ALTER TABLE hotboat_appointments
                    ADD COLUMN IF NOT EXISTS stock_consumed_at TIMESTAMPTZ;
                ALTER TABLE all_appointments
                    ADD COLUMN IF NOT EXISTS stock_consumed_at TIMESTAMPTZ;
            """)
            conn.commit()


def _apply_movement(cur, product_id: int, delta: float, reason: str,
                    booking_ref: str = "", extra_slug: str = "", notes: str = ""):
    """Apply delta to stock_products.current_stock and log the movement."""
    cur.execute("SELECT name FROM stock_products WHERE id=%s", (product_id,))
    row = cur.fetchone()
    pname = row[0] if row else ""
    cur.execute(
        "UPDATE stock_products SET current_stock=current_stock+%s, updated_at=NOW() WHERE id=%s",
        (delta, product_id)
    )
    cur.execute(
        """INSERT INTO stock_movements
           (product_id, product_name, delta, reason, booking_ref, extra_slug, notes)
           VALUES (%s,%s,%s,%s,%s,%s,%s)""",
        (product_id, pname, delta, reason, booking_ref, extra_slug, notes)
    )


def _check_low_stock(conn):
    """Return list of products at or below min_stock.
    Excludes products linked to a deleted/hidden extra so alerts don't keep
    flagging items the user already removed."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT sp.id, sp.name, sp.category, sp.unit, sp.current_stock, sp.min_stock
            FROM stock_products sp
            WHERE sp.is_active AND sp.current_stock <= sp.min_stock AND sp.min_stock > 0
              AND NOT EXISTS (
                  SELECT 1 FROM extras_visibility ev
                  WHERE ev.stock_product_id = sp.id
                    AND COALESCE(ev.user_hidden, FALSE) = TRUE
              )
            ORDER BY (sp.current_stock - sp.min_stock), sp.name
        """)
        cols = [d.name for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]


def _send_low_stock_alert(alerts: list):
    try:
        import resend, os
        resend.api_key = os.getenv("RESEND_API_KEY", "")
        rows = "".join(f"""
            <tr>
              <td style="padding:8px 10px;border-bottom:1px solid #1e2d45;color:#f1f5f9">{a['name']}</td>
              <td style="padding:8px 10px;border-bottom:1px solid #1e2d45;color:#fbbf24;text-align:center">{a['current_stock']} {a['unit']}</td>
              <td style="padding:8px 10px;border-bottom:1px solid #1e2d45;color:#94a3b8;text-align:center">{a['min_stock']} {a['unit']}</td>
            </tr>""" for a in alerts)
        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#0b1120;margin:0;padding:24px">
<div style="background:#131c2e;border-radius:14px;max-width:520px;margin:auto;overflow:hidden">
  <div style="height:4px;background:linear-gradient(90deg,#ef4444,#f59e0b)"></div>
  <div style="padding:22px 26px">
    <h2 style="color:#f87171;margin:0 0 6px">⚠️ Stock bajo mínimo</h2>
    <p style="color:#94a3b8;margin:0 0 18px;font-size:14px">{len(alerts)} producto(s) necesitan reposición</p>
    <table width="100%" cellspacing="0" style="border-collapse:collapse">
      <tr style="background:#1e2d45">
        <th style="padding:8px 10px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase">Producto</th>
        <th style="padding:8px 10px;color:#64748b;font-size:11px;text-transform:uppercase">Stock actual</th>
        <th style="padding:8px 10px;color:#64748b;font-size:11px;text-transform:uppercase">Mínimo</th>
      </tr>
      {rows}
    </table>
  </div>
  <div style="padding:12px 26px 18px;color:#475569;font-size:12px;border-top:1px solid #1e2d45">
    HotBoat Chile · alerta automática de stock
  </div>
</div></body></html>"""
        resend.Emails.send({
            "from": os.getenv("RESEND_FROM_CONFIRMATIONS", os.getenv("EMAIL_FROM", "reservas@reservas.hotboat.cl")),
            "to": [ADMIN_NOTIFICATION_EMAIL],
            "subject": f"⚠️ Stock bajo mínimo — {len(alerts)} producto(s)",
            "html": html,
        })
        logger.info("low_stock_alert sent for %d products", len(alerts))
    except Exception as e:
        logger.error("low_stock_alert failed: %s", e)


# ─────────────────────────── Products CRUD ──────────────────────────────────

class ProductBody(BaseModel):
    name: str
    category: str = ""
    unit: str = "unidad"
    current_stock: float = 0
    min_stock: float = 0
    cost_per_unit: float = 0
    notes: str = ""
    is_active: bool = True


@stock_router.get("/api/admin/stock/products")
def list_products(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    _ensure_tables()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, name, category, unit, current_stock, min_stock,
                       cost_per_unit, notes, is_active, updated_at
                FROM stock_products ORDER BY category, name
            """)
            cols = [d.name for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            for r in rows:
                if r.get("updated_at"):
                    r["updated_at"] = str(r["updated_at"])
            return {"products": rows}


@stock_router.post("/api/admin/stock/products")
def create_product(body: ProductBody, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Insert with current_stock already set; log it without adding again
            cur.execute(
                """INSERT INTO stock_products
                   (name, category, unit, current_stock, min_stock, cost_per_unit, notes, is_active)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (body.name, body.category, body.unit, body.current_stock,
                 body.min_stock, body.cost_per_unit, body.notes, body.is_active)
            )
            new_id = cur.fetchone()[0]
            # Only log the movement — do NOT apply delta (stock already set by INSERT)
            if body.current_stock > 0:
                cur.execute(
                    """INSERT INTO stock_movements
                       (product_id, product_name, delta, reason, notes)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (new_id, body.name, body.current_stock, "purchase",
                     "Stock inicial al crear producto")
                )
            conn.commit()
    return {"ok": True, "id": new_id}


@stock_router.put("/api/admin/stock/products/{pid}")
def update_product(pid: int, body: ProductBody, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Read old stock and name to detect changes
            cur.execute("SELECT current_stock, name FROM stock_products WHERE id=%s", (pid,))
            row = cur.fetchone()
            old_stock = float(row[0]) if row else 0.0
            old_name = row[1] if row else None
            # Update all fields including current_stock
            cur.execute(
                """UPDATE stock_products
                   SET name=%s, category=%s, unit=%s, current_stock=%s, min_stock=%s,
                       cost_per_unit=%s, notes=%s, is_active=%s, updated_at=NOW()
                   WHERE id=%s""",
                (body.name, body.category, body.unit, body.current_stock,
                 body.min_stock, body.cost_per_unit, body.notes, body.is_active, pid)
            )
            # Cascade name rename to movement history snapshots and tabla catalog
            if old_name and old_name != body.name:
                cur.execute(
                    "UPDATE stock_movements SET product_name = %s WHERE product_id = %s",
                    (body.name, pid)
                )
                cur.execute(
                    "UPDATE tabla_catalog_items SET ingredient = %s WHERE LOWER(ingredient) = LOWER(%s)",
                    (body.name, old_name)
                )
            # Log only if stock actually changed
            delta = round(body.current_stock - old_stock, 4)
            if delta != 0:
                cur.execute(
                    """INSERT INTO stock_movements
                       (product_id, product_name, delta, reason, notes)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (pid, body.name, delta, "manual",
                     "Ajuste manual desde panel de administración")
                )
            conn.commit()
    return {"ok": True}


@stock_router.delete("/api/admin/stock/products/{pid}")
def delete_product(pid: int, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM stock_products WHERE id=%s", (pid,))
            conn.commit()
    return {"ok": True}


@stock_router.post("/api/admin/stock/dedup")
def dedup_products(x_admin_key: str = Header(""), apply: bool = False):
    """Merge duplicate stock_products that share the same name (case-insensitive).

    For each group of duplicates the row with the most stock is kept (ties → lowest
    id). All references in extras_bom, stock_movements and extras_visibility are
    re-pointed to the keeper BEFORE the duplicate rows are deleted (extras_bom has
    ON DELETE CASCADE, so re-pointing first prevents losing BOM links). Duplicate
    BOM rows created by the merge are then collapsed.

    Defaults to a DRY RUN: pass ?apply=true to actually perform the merge.
    Always returns the plan so it can be previewed first.
    """
    _check_auth(x_admin_key)
    plan = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Identify duplicate name groups
            cur.execute("""
                SELECT LOWER(name) AS lname
                FROM stock_products
                GROUP BY LOWER(name)
                HAVING COUNT(*) > 1
            """)
            dup_names = [r[0] for r in cur.fetchall()]

            for lname in dup_names:
                cur.execute(
                    """SELECT id, name, current_stock
                       FROM stock_products
                       WHERE LOWER(name) = %s
                       ORDER BY current_stock DESC, id ASC""",
                    (lname,),
                )
                rows = cur.fetchall()
                if len(rows) < 2:
                    continue
                keeper_id, keeper_name, keeper_stock = rows[0][0], rows[0][1], float(rows[0][2])
                dupes = [{"id": r[0], "name": r[1], "stock": float(r[2])} for r in rows[1:]]
                plan.append({
                    "name": keeper_name,
                    "keeper": {"id": keeper_id, "stock": keeper_stock},
                    "removed": dupes,
                })

                if apply:
                    dupe_ids = [d["id"] for d in dupes]
                    # Re-point all references to the keeper before deleting dupes
                    cur.execute(
                        "UPDATE extras_bom SET product_id=%s WHERE product_id = ANY(%s)",
                        (keeper_id, dupe_ids),
                    )
                    cur.execute(
                        "UPDATE stock_movements SET product_id=%s WHERE product_id = ANY(%s)",
                        (keeper_id, dupe_ids),
                    )
                    cur.execute(
                        "UPDATE extras_visibility SET stock_product_id=%s WHERE stock_product_id = ANY(%s)",
                        (keeper_id, dupe_ids),
                    )
                    cur.execute(
                        "DELETE FROM stock_products WHERE id = ANY(%s)",
                        (dupe_ids,),
                    )

            if apply:
                # Collapse duplicate BOM rows that the merge may have created
                cur.execute("""
                    DELETE FROM extras_bom a
                    USING extras_bom b
                    WHERE a.id > b.id
                      AND a.extra_slug = b.extra_slug
                      AND a.product_id = b.product_id
                      AND COALESCE(a.is_variant,FALSE) = COALESCE(b.is_variant,FALSE)
                      AND COALESCE(a.variant_label,'') = COALESCE(b.variant_label,'')
                """)
                conn.commit()

    return {
        "ok": True,
        "applied": apply,
        "groups": len(plan),
        "duplicates_removed": sum(len(g["removed"]) for g in plan),
        "plan": plan,
    }


# ─────────────────────────── Stock adjustment ───────────────────────────────

class AdjustBody(BaseModel):
    product_id: int
    delta: float
    reason: str = "manual"
    notes: str = ""


@stock_router.post("/api/admin/stock/adjust")
def adjust_stock(body: AdjustBody, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            _apply_movement(cur, body.product_id, body.delta,
                            body.reason, notes=body.notes)
            conn.commit()
        # Check low stock after adjustment
        alerts = _check_low_stock(conn)
    if alerts:
        _send_low_stock_alert(alerts)
    return {"ok": True}


# ─────────────────────────── Bill of Materials ──────────────────────────────

class BomItem(BaseModel):
    product_id: int
    quantity: float = 1
    is_variant: bool = False
    variant_label: str = ""


class BomBody(BaseModel):
    items: List[BomItem]


@stock_router.get("/api/admin/stock/bom/{extra_slug}")
def get_bom(extra_slug: str, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT b.id, b.extra_slug, b.product_id, b.quantity, b.is_variant, b.variant_label,
                       p.name AS product_name, p.unit, p.current_stock
                FROM extras_bom b
                JOIN stock_products p ON p.id=b.product_id
                WHERE b.extra_slug=%s
                ORDER BY b.is_variant, b.id
            """, (extra_slug,))
            cols = [d.name for d in cur.description]
            return {"bom": [dict(zip(cols, r)) for r in cur.fetchall()]}


@stock_router.put("/api/admin/stock/bom/{extra_slug}")
def save_bom(extra_slug: str, body: BomBody, x_admin_key: str = Header("")):
    """Replace the entire BOM for an extra (idempotent save)."""
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM extras_bom WHERE extra_slug=%s", (extra_slug,))
            for item in body.items:
                cur.execute(
                    """INSERT INTO extras_bom
                       (extra_slug, product_id, quantity, is_variant, variant_label)
                       VALUES (%s,%s,%s,%s,%s)""",
                    (extra_slug, item.product_id, item.quantity,
                     item.is_variant, item.variant_label)
                )
            conn.commit()
    return {"ok": True}


# ─────────────────────────── Booking consumption ────────────────────────────

class ConsumeItem(BaseModel):
    extra_slug: str
    quantity: int = 1
    variant_product_id: Optional[int] = None   # for variant extras


class ConsumeBody(BaseModel):
    booking_ref: str
    extras: List[ConsumeItem]
    undo: bool = False   # if True, add stock back (return)


@stock_router.post("/api/admin/stock/consume")
def consume_for_booking(body: ConsumeBody, x_admin_key: str = Header("")):
    """
    Deduct (or return) stock for extras tied to a booking.
    Idempotent: if booking_ref was already consumed, it reverses first then re-applies.
    """
    _check_auth(x_admin_key)
    ref = body.booking_ref
    direction = -1 if not body.undo else 1   # undo=True → return stock

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Remove any previous movements for this booking (full replace strategy)
            cur.execute(
                "SELECT product_id, delta FROM stock_movements WHERE booking_ref=%s",
                (ref,)
            )
            prev = cur.fetchall()
            for product_id, old_delta in prev:
                # Reverse previous movement
                cur.execute(
                    "UPDATE stock_products SET current_stock=current_stock+%s, updated_at=NOW() WHERE id=%s",
                    (-old_delta, product_id)
                )
            cur.execute("DELETE FROM stock_movements WHERE booking_ref=%s", (ref,))

            if not body.undo:
                for item in body.extras:
                    # Get BOM for this extra
                    cur.execute("""
                        SELECT product_id, quantity, is_variant, variant_label
                        FROM extras_bom WHERE extra_slug=%s
                    """, (item.extra_slug,))
                    bom_rows = cur.fetchall()

                    if not bom_rows:
                        continue

                    has_variants = any(r[2] for r in bom_rows)  # any is_variant=True

                    if has_variants:
                        # Only consume the chosen variant
                        if item.variant_product_id:
                            target = next(
                                (r for r in bom_rows if r[0] == item.variant_product_id), None
                            )
                            if target:
                                delta = -(target[1] * item.quantity) * direction * -1
                                # Simplified: direction*-1 so undo=False → negative
                                actual_delta = -(target[1] * item.quantity)
                                _apply_movement(cur, target[0], actual_delta, "booking",
                                                ref, item.extra_slug,
                                                f"Reserva {ref} — variante {target[3]}")
                    else:
                        # Consume all products in BOM
                        for product_id, qty, _, _ in bom_rows:
                            actual_delta = -(qty * item.quantity)
                            _apply_movement(cur, product_id, actual_delta, "booking",
                                            ref, item.extra_slug,
                                            f"Reserva {ref}")

            conn.commit()
        alerts = _check_low_stock(conn)

    if alerts:
        _send_low_stock_alert(alerts)
    return {"ok": True, "reverted_movements": len(prev)}


# ─────────────────────────── Low-stock alerts ───────────────────────────────

@stock_router.get("/api/admin/stock/alerts")
def get_alerts(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        return {"alerts": _check_low_stock(conn)}


# ─────────────────────────── Movement history ───────────────────────────────

@stock_router.get("/api/admin/stock/movements")
def get_movements(product_id: Optional[int] = None, limit: int = 100,
                  x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            if product_id:
                cur.execute("""
                    SELECT id, product_id, product_name, delta, reason,
                           booking_ref, extra_slug, notes, created_at
                    FROM stock_movements WHERE product_id=%s
                    ORDER BY created_at DESC LIMIT %s
                """, (product_id, limit))
            else:
                cur.execute("""
                    SELECT id, product_id, product_name, delta, reason,
                           booking_ref, extra_slug, notes, created_at
                    FROM stock_movements
                    ORDER BY created_at DESC LIMIT %s
                """, (limit,))
            cols = [d.name for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            for r in rows:
                if r.get("created_at"):
                    r["created_at"] = str(r["created_at"])
            return {"movements": rows}


# ─────────────────────────── Auto-consume past reservations ─────────────────

def _consume_booking_extras(cur, booking_ref: str, extras_json, tabla_selection=None):
    """Consume stock for one booking. Returns number of movements applied."""
    import json as _json

    # Parse extras
    if isinstance(extras_json, str):
        try:
            extras_json = _json.loads(extras_json)
        except Exception:
            extras_json = {}
    if not isinstance(extras_json, dict):
        extras_json = {}

    items = []
    extracted_tabla_ingredients = []

    for slug, val in extras_json.items():
        if slug.startswith("tabla__"):
            # Tabla keys are handled via ingredient list, not BOM.
            # If tabla_selections DB lookup failed, fall back to elige_* in the dict.
            if not tabla_selection and isinstance(val, dict):
                elig1 = val.get("elige_1")
                elig2 = val.get("elige_2") or []
                elig3 = val.get("elige_3") or []
                if isinstance(elig2, str):
                    try:
                        elig2 = _json.loads(elig2)
                    except Exception:
                        elig2 = []
                if isinstance(elig3, str):
                    try:
                        elig3 = _json.loads(elig3)
                    except Exception:
                        elig3 = []
                if elig1:
                    extracted_tabla_ingredients.append(elig1)
                extracted_tabla_ingredients.extend([x for x in elig2 if x])
                extracted_tabla_ingredients.extend([x for x in elig3 if x])
            continue  # never add tabla__ to BOM items list

        qty = val
        try:
            qty = int(qty)
        except (TypeError, ValueError):
            qty = 1
        if qty > 0:
            items.append({"extra_slug": slug, "quantity": qty, "variant_product_id": None})

    # Use DB-provided list first; fall back to what was embedded in extras_json
    all_tabla_ingredients = tabla_selection or extracted_tabla_ingredients or []

    movements = 0

    # Tabla ingredients (chosen by client)
    for ingredient_name in all_tabla_ingredients:
        name_lower = ingredient_name.lower()
        cur.execute(
            "SELECT id FROM stock_products WHERE LOWER(name)=%s LIMIT 1",
            (name_lower,)
        )
        row = cur.fetchone()
        if row:
            _apply_movement(cur, row[0], -1, "booking", booking_ref,
                            name_lower, f"Tabla — {ingredient_name}")
            movements += 1

    # BOM-based deduction for regular extras
    for item in items:
        cur.execute(
            "SELECT product_id, quantity, is_variant, variant_label FROM extras_bom WHERE extra_slug=%s",
            (item["extra_slug"],)
        )
        bom_rows = cur.fetchall()
        if not bom_rows:
            continue
        has_variants = any(r[2] for r in bom_rows)
        if has_variants:
            if item["variant_product_id"]:
                target = next((r for r in bom_rows if r[0] == item["variant_product_id"]), None)
                if target:
                    _apply_movement(cur, target[0], -(target[1] * item["quantity"]),
                                    "booking", booking_ref, item["extra_slug"],
                                    f"Reserva {booking_ref} — variante {target[3]}")
                    movements += 1
        else:
            for product_id, qty, _, _ in bom_rows:
                _apply_movement(cur, product_id, -(qty * item["quantity"]),
                                "booking", booking_ref, item["extra_slug"],
                                f"Reserva {booking_ref}")
                movements += 1
    return movements


def auto_consume_past_bookings() -> dict:
    """
    Find all confirmed reservations whose date has already passed and whose
    stock has not been consumed yet, then deduct their stock.
    Called on startup and periodically by the background scheduler.
    Returns a summary dict.
    """
    import json as _json
    from datetime import date

    today = date.today().isoformat()
    consumed = []
    skipped = []

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # hotboat_appointments uses different column names
                cur.execute("""
                    SELECT id, booking_ref, booking_date, extras, stock_consumed_at
                    FROM hotboat_appointments
                    WHERE booking_date <= %s
                      AND status IN ('confirmed', 'CONFIRMED', 'pending', 'PENDING')
                      AND stock_consumed_at IS NULL
                """, (today,))
                web_rows = cur.fetchall()

                # all_appointments: synced/historical reservations
                cur.execute("""
                    SELECT id, source_id, fecha, extras_json, stock_consumed_at
                    FROM all_appointments
                    WHERE fecha <= %s
                      AND status IN ('confirmed', 'CONFIRMED', 'pending', 'PENDING')
                      AND stock_consumed_at IS NULL
                """, (today,))
                all_rows = cur.fetchall()

            processed_refs = set()

            for table_name, rows in [("hotboat_appointments", web_rows), ("all_appointments", all_rows)]:
                for (row_id, source_id, fecha, extras_json, _) in rows:
                    ref = source_id or (f"HA-{row_id}" if table_name == "hotboat_appointments" else f"AA-{row_id}")
                    if ref in processed_refs:
                        continue
                    processed_refs.add(ref)

                    # Check if already consumed (via stock_movements)
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT COUNT(*) FROM stock_movements WHERE booking_ref=%s AND reason='booking'",
                            (ref,)
                        )
                        already = cur.fetchone()[0]
                        if already > 0:
                            # Mark as consumed so we don't check again
                            cur.execute(
                                f"UPDATE {table_name} SET stock_consumed_at=NOW() WHERE id=%s",
                                (row_id,)
                            )
                            conn.commit()
                            skipped.append(ref)
                            continue

                        # Check for tabla selection
                        cur.execute(
                            "SELECT elige_1, elige_2, elige_3 FROM tabla_selections WHERE booking_ref=%s",
                            (ref,)
                        )
                        tabla_row = cur.fetchone()
                        tabla_ingredients = []
                        if tabla_row:
                            elige_1, elige_2, elige_3 = tabla_row
                            if elige_1:
                                tabla_ingredients.append(elige_1)
                            if elige_2:
                                try:
                                    tabla_ingredients.extend(_json.loads(elige_2) if isinstance(elige_2, str) else elige_2)
                                except Exception:
                                    pass
                            if elige_3:
                                try:
                                    tabla_ingredients.extend(_json.loads(elige_3) if isinstance(elige_3, str) else elige_3)
                                except Exception:
                                    pass

                        mvts = _consume_booking_extras(cur, ref, extras_json, tabla_ingredients or None)

                        # Mark as consumed
                        cur.execute(
                            f"UPDATE {table_name} SET stock_consumed_at=NOW() WHERE id=%s",
                            (row_id,)
                        )
                        conn.commit()

                        if mvts > 0:
                            consumed.append(ref)
                        else:
                            skipped.append(ref)

            alerts = _check_low_stock(conn)

        if alerts:
            _send_low_stock_alert(alerts)

        logger.info("Stock auto-consume: %d consumed, %d skipped (no BOM)", len(consumed), len(skipped))
        return {"consumed": consumed, "skipped": skipped}

    except Exception as e:
        logger.error("auto_consume_past_bookings error: %s", e)
        return {"error": str(e), "consumed": [], "skipped": []}


_CONFIRMED = ('confirmed', 'paid', 'aprobado', 'CONFIRMED')


def check_and_alert_tabla_ingredients() -> dict:
    """
    Look at today's confirmed tabla bookings and alert if any ingredient
    is short. Called at 09:00 each morning so there's time to restock.
    """
    import json as _json
    from datetime import date

    today = date.today().isoformat()
    needed: dict[str, int] = {}   # ingredient_lower → total units needed today
    booking_count = 0

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT aa.id, aa.source_id, aa.extras_json,
                       ts.elige_1, ts.elige_2, ts.elige_3
                FROM all_appointments aa
                LEFT JOIN tabla_selections ts
                    ON ts.booking_ref = COALESCE(aa.source_id, 'AA-' || aa.id::text)
                WHERE aa.fecha = %s
                  AND aa.status = ANY(%s)
            """, (today, list(_CONFIRMED)))
            rows = cur.fetchall()

        for row_id, source_id, extras_json, elig1, elig2, elig3 in rows:
            ingredients = []

            # Primary: tabla_selections
            if elig1:
                ingredients.append(elig1)
            for field in (elig2, elig3):
                if field:
                    try:
                        parsed = _json.loads(field) if isinstance(field, str) else field
                        ingredients.extend([x for x in parsed if x])
                    except Exception:
                        pass

            # Fallback: elige_* embedded in extras_json["tabla__*"]
            if not ingredients and isinstance(extras_json, dict):
                for slug, val in extras_json.items():
                    if slug.startswith("tabla__") and isinstance(val, dict):
                        if val.get("elige_1"):
                            ingredients.append(val["elige_1"])
                        for fn in ("elige_2", "elige_3"):
                            fv = val.get(fn) or []
                            if isinstance(fv, str):
                                try:
                                    fv = _json.loads(fv)
                                except Exception:
                                    fv = []
                            ingredients.extend([x for x in fv if x])

            if ingredients:
                booking_count += 1
                for name in ingredients:
                    key = name.lower()
                    needed[key] = needed.get(key, 0) + 1

    if not needed:
        logger.info("Tabla ingredient check: no tablas today")
        return {"bookings_with_tabla": 0, "shortfalls": []}

    shortfalls = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            for name_lower, qty_needed in needed.items():
                cur.execute(
                    "SELECT name, current_stock, unit FROM stock_products WHERE LOWER(name)=%s LIMIT 1",
                    (name_lower,)
                )
                sp = cur.fetchone()
                current = sp[1] if sp else 0
                if current is None:
                    current = 0
                if current < qty_needed:
                    shortfalls.append({
                        "ingredient": sp[0] if sp else name_lower,
                        "needed":     qty_needed,
                        "current":    current,
                        "unit":       sp[2] if sp else "",
                        "falta":      qty_needed - current,
                    })

    if shortfalls:
        _send_tabla_shortfall_alert(shortfalls, booking_count, today)
    else:
        logger.info("Tabla ingredient check: all OK for %d bookings", booking_count)

    return {"bookings_with_tabla": booking_count, "shortfalls": shortfalls}


def _send_tabla_shortfall_alert(shortfalls: list, booking_count: int, today: str):
    try:
        import resend, os
        resend.api_key = os.getenv("RESEND_API_KEY", "")
        rows_html = "".join(f"""
            <tr>
              <td style="padding:8px 10px;border-bottom:1px solid #1e2d45;color:#f1f5f9">{s['ingredient']}</td>
              <td style="padding:8px 10px;border-bottom:1px solid #1e2d45;color:#fbbf24;text-align:center">{s['current']} {s['unit']}</td>
              <td style="padding:8px 10px;border-bottom:1px solid #1e2d45;color:#94a3b8;text-align:center">{s['needed']} {s['unit']}</td>
              <td style="padding:8px 10px;border-bottom:1px solid #1e2d45;color:#f87171;text-align:center;font-weight:700">-{s['falta']} {s['unit']}</td>
            </tr>""" for s in shortfalls)
        html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"></head>
<body style="font-family:Arial,sans-serif;background:#0b1120;margin:0;padding:24px">
<div style="background:#131c2e;border-radius:14px;max-width:560px;margin:auto;overflow:hidden">
  <div style="height:4px;background:linear-gradient(90deg,#f59e0b,#ef4444)"></div>
  <div style="padding:22px 26px">
    <h2 style="color:#fbbf24;margin:0 0 4px">🥗 Ingredientes insuficientes para tablas de hoy</h2>
    <p style="color:#94a3b8;margin:0 0 18px;font-size:14px">
      {today} · {booking_count} reserva(s) con tabla · {len(shortfalls)} ingrediente(s) con stock insuficiente
    </p>
    <table width="100%" cellspacing="0" style="border-collapse:collapse">
      <tr style="background:#1e2d45">
        <th style="padding:8px 10px;text-align:left;color:#64748b;font-size:11px;text-transform:uppercase">Ingrediente</th>
        <th style="padding:8px 10px;color:#64748b;font-size:11px;text-transform:uppercase">Stock</th>
        <th style="padding:8px 10px;color:#64748b;font-size:11px;text-transform:uppercase">Necesario</th>
        <th style="padding:8px 10px;color:#64748b;font-size:11px;text-transform:uppercase">Falta</th>
      </tr>
      {rows_html}
    </table>
  </div>
  <div style="padding:12px 26px 18px;color:#475569;font-size:12px;border-top:1px solid #1e2d45">
    HotBoat Chile · alerta automática de stock
  </div>
</div></body></html>"""
        resend.Emails.send({
            "from": os.getenv("RESEND_FROM_CONFIRMATIONS", os.getenv("EMAIL_FROM", "reservas@reservas.hotboat.cl")),
            "to":   [ADMIN_NOTIFICATION_EMAIL],
            "subject": f"🥗 Faltan ingredientes para tablas de hoy ({today})",
            "html": html,
        })
        logger.info("Tabla shortfall alert sent: %d shortfalls for %s", len(shortfalls), today)
    except Exception as e:
        logger.error("Tabla shortfall alert failed: %s", e)


@stock_router.post("/api/admin/stock/auto-consume-past")
def trigger_auto_consume(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    return auto_consume_past_bookings()


@stock_router.post("/api/admin/stock/check-tabla-ingredients")
def trigger_tabla_check(x_admin_key: str = Header("")):
    """Manual trigger for the morning tabla ingredient check."""
    _check_auth(x_admin_key)
    return check_and_alert_tabla_ingredients()


@stock_router.get("/api/admin/stock/debug-booking/{booking_ref}")
def debug_booking_stock(booking_ref: str, x_admin_key: str = Header("")):
    """Dry-run: show what stock movements would be applied for one booking."""
    _check_auth(x_admin_key)
    import json as _json

    with get_connection() as conn:
        with conn.cursor() as cur:
            # Fetch booking from all_appointments
            cur.execute("""
                SELECT id, source_id, nombre_cliente, fecha, status, extras_json,
                       stock_consumed_at
                FROM all_appointments
                WHERE (source_id = %s OR id::text = %s)
                ORDER BY id LIMIT 1
            """, (booking_ref, booking_ref.replace("AA-", "").lstrip("0") or "0"))
            row = cur.fetchone()
            if not row:
                raise HTTPException(404, f"Booking {booking_ref!r} not found")

            row_id, source_id, cliente, fecha, status, extras_json, consumed_at = row
            ref = source_id or f"AA-{row_id}"

            ej = extras_json
            if isinstance(ej, str):
                try:
                    ej = _json.loads(ej)
                except Exception:
                    ej = {}
            if not isinstance(ej, dict):
                ej = {}

            # Check tabla_selections
            cur.execute(
                "SELECT elige_1, elige_2, elige_3 FROM tabla_selections WHERE booking_ref=%s",
                (ref,)
            )
            tabla_row = cur.fetchone()
            tabla_ingredients_db = []
            if tabla_row:
                elig1, elig2, elig3 = tabla_row
                if elig1:
                    tabla_ingredients_db.append(elig1)
                for field in (elig2, elig3):
                    if field:
                        try:
                            tabla_ingredients_db.extend(
                                _json.loads(field) if isinstance(field, str) else field
                            )
                        except Exception:
                            pass

            # Extract from extras_json as fallback
            tabla_ingredients_json = []
            tabla_keys = []
            for slug, val in ej.items():
                if slug.startswith("tabla__") and isinstance(val, dict):
                    tabla_keys.append(slug)
                    for field_name in ("elige_1", "elige_2", "elige_3"):
                        fv = val.get(field_name) or []
                        if isinstance(fv, str) and field_name != "elige_1":
                            try:
                                fv = _json.loads(fv)
                            except Exception:
                                fv = []
                        if isinstance(fv, str):
                            fv = [fv]
                        tabla_ingredients_json.extend([x for x in fv if x])

            all_ingredients = tabla_ingredients_db or tabla_ingredients_json

            # Check which ingredients have stock products
            ingredient_results = []
            for name in all_ingredients:
                cur.execute(
                    "SELECT id, name, current_stock FROM stock_products WHERE LOWER(name)=%s LIMIT 1",
                    (name.lower(),)
                )
                sp = cur.fetchone()
                ingredient_results.append({
                    "ingredient": name,
                    "stock_product_found": sp is not None,
                    "stock_product_id": sp[0] if sp else None,
                    "stock_product_name": sp[1] if sp else None,
                    "current_stock": sp[2] if sp else None,
                    "would_deduct": sp is not None,
                })

            # Check regular extras BOM
            bom_results = []
            for slug, val in ej.items():
                if slug.startswith("tabla__"):
                    continue
                cur.execute(
                    "SELECT product_id, quantity FROM extras_bom WHERE extra_slug=%s",
                    (slug,)
                )
                bom = cur.fetchall()
                bom_results.append({
                    "extra_slug": slug,
                    "bom_found": len(bom) > 0,
                    "bom_products": [{"product_id": r[0], "qty": r[1]} for r in bom],
                })

            already_consumed_count = 0
            cur.execute(
                "SELECT COUNT(*) FROM stock_movements WHERE booking_ref=%s AND reason='booking'",
                (ref,)
            )
            already_consumed_count = cur.fetchone()[0]

    return {
        "booking_ref": ref,
        "cliente": cliente,
        "fecha": str(fecha),
        "status": status,
        "already_consumed": already_consumed_count > 0,
        "consumed_at": str(consumed_at) if consumed_at else None,
        "tabla_keys_in_extras_json": tabla_keys,
        "tabla_ingredients_from_db": tabla_ingredients_db,
        "tabla_ingredients_from_json": tabla_ingredients_json,
        "ingredients_used": all_ingredients,
        "ingredient_stock_check": ingredient_results,
        "regular_extras_bom": bom_results,
        "verdict": (
            "OK — se descontaría el stock de los ingredientes encontrados"
            if any(r["would_deduct"] for r in ingredient_results)
            else ("SIN TABLA en extras_json ni en tabla_selections"
                  if not all_ingredients
                  else "PROBLEMA — ingredientes encontrados pero ninguno tiene stock_product coincidente")
        ),
    }
