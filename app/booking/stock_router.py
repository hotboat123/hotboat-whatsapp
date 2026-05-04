"""
Stock management router — /api/admin/stock/...
Handles: products CRUD, bill-of-materials per extra, stock adjustments,
         booking consumption (auto-deduct when extras are saved), low-stock alerts.
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
    """Return list of products at or below min_stock."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, name, category, unit, current_stock, min_stock
            FROM stock_products
            WHERE is_active AND current_stock <= min_stock AND min_stock > 0
            ORDER BY (current_stock - min_stock), name
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
            # Read old stock to compute delta for the movement log
            cur.execute("SELECT current_stock, name FROM stock_products WHERE id=%s", (pid,))
            row = cur.fetchone()
            old_stock = float(row[0]) if row else 0.0
            # Update all fields including current_stock
            cur.execute(
                """UPDATE stock_products
                   SET name=%s, category=%s, unit=%s, current_stock=%s, min_stock=%s,
                       cost_per_unit=%s, notes=%s, is_active=%s, updated_at=NOW()
                   WHERE id=%s""",
                (body.name, body.category, body.unit, body.current_stock,
                 body.min_stock, body.cost_per_unit, body.notes, body.is_active, pid)
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
