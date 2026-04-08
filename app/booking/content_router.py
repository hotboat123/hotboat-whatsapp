"""Public content API – experiences, packs & extras booking submission."""
import logging
import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.db.connection import get_connection

logger = logging.getLogger(__name__)
content_router = APIRouter()

MEDIA_BASE = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "media")


# ── Public endpoints ──────────────────────────────────────────────────────────

@content_router.get("/api/content/experiencias")
def list_experiencias(active_only: bool = True):
    with get_connection() as conn:
        with conn.cursor() as cur:
            q = "SELECT id,slug,name,icon,description,price_per_person,cost_per_person,image_path,is_active,display_order FROM experiences"
            if active_only:
                q += " WHERE is_active=TRUE"
            q += " ORDER BY display_order,id"
            cur.execute(q)
            cols = [d.name for d in cur.description]
            return {"experiences": [dict(zip(cols, r)) for r in cur.fetchall()]}


@content_router.get("/api/content/packs")
def list_packs(active_only: bool = True):
    with get_connection() as conn:
        with conn.cursor() as cur:
            q = "SELECT id,slug,name,icon,description,personas,price_from,cost_from,image_path,includes,is_active,display_order FROM packs"
            if active_only:
                q += " WHERE is_active=TRUE"
            q += " ORDER BY display_order,id"
            cur.execute(q)
            cols = [d.name for d in cur.description]
            rows = []
            for r in cur.fetchall():
                row = dict(zip(cols, r))
                if isinstance(row.get("includes"), str):
                    import json
                    row["includes"] = json.loads(row["includes"])
                rows.append(row)
            return {"packs": rows}


# ── Public menu visibility settings (read-only) ───────────────────────────────

@content_router.get("/api/content/menu-settings")
def public_menu_settings():
    from app.booking.operator_settings import get_menu_settings
    return get_menu_settings()


# ── Public extras booking submission (from booking page) ──────────────────────

class PublicExtrasBookingBody(BaseModel):
    customer_name: str
    customer_phone: Optional[str] = None
    item_type: str
    item_slug: str
    item_name: str
    start_date: str
    end_date: Optional[str] = None
    num_people: int = 1
    total_price: int = 0
    deposit_paid: int = 0
    status: str = "pendiente"
    notes: Optional[str] = None
    booking_ref: Optional[str] = None


# ── Sync helpers for the WhatsApp bot ────────────────────────────────────────

def get_active_experiences_db():
    """Returns list of active experience dicts (sync, safe to call from bot)."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT slug,name,icon,description,price_per_person FROM experiences"
                    " WHERE is_active=TRUE ORDER BY display_order,id"
                )
                cols = [d.name for d in cur.description]
                return [dict(zip(cols, r)) for r in cur.fetchall()]
    except Exception as e:
        logger.warning(f"get_active_experiences_db failed: {e}")
        return []


def get_active_packs_db():
    """Returns list of active pack dicts (sync, safe to call from bot)."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT slug,name,icon,description,personas,price_from,includes FROM packs"
                    " WHERE is_active=TRUE ORDER BY display_order,id"
                )
                cols = [d.name for d in cur.description]
                rows = []
                for r in cur.fetchall():
                    row = dict(zip(cols, r))
                    if isinstance(row.get("includes"), str):
                        import json
                        row["includes"] = json.loads(row["includes"])
                    rows.append(row)
                return rows
    except Exception as e:
        logger.warning(f"get_active_packs_db failed: {e}")
        return []


def build_packs_menu_text_es(packs=None):
    """Build a dynamic WhatsApp-friendly packs menu text in Spanish."""
    if packs is None:
        packs = get_active_packs_db()
    if not packs:
        return "🎁 Por el momento no hay packs disponibles. Escríbenos para más información."
    nums = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣"]
    lines = ["🎁 *Packs Completos - Todo Incluido*\n\nElige tu pack ideal:\n"]
    for i, p in enumerate(packs):
        n = nums[i] if i < len(nums) else f"{i+1}."
        desc = (p.get("includes") or [])
        desc_txt = ", ".join(desc[:2]) if desc else p.get("description", "")
        lines.append(f"{n} {p['icon']} *{p['name']}*\n{p.get('personas','')} · {desc_txt}\n")
    lines.append("📸 Cuéntame tu pack preferido y te envío los detalles.")
    names = " | ".join([f"*{p['name'].split()[-1]}*" for p in packs])
    lines.append(f"\nEscribe el número o el nombre ({names}) 🎒")
    return "\n".join(lines)


@content_router.post("/api/content/extras-booking")
async def public_create_extras_booking(body: PublicExtrasBookingBody):
    """Public endpoint so booking.html can submit extras without admin key."""
    import os, httpx as _httpx
    try:
        # 1. Save to DB
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO extras_bookings"
                    " (booking_ref,customer_name,customer_phone,item_type,item_slug,item_name,"
                    "  start_date,end_date,num_people,total_price,deposit_paid,status,notes)"
                    " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (body.booking_ref, body.customer_name, body.customer_phone,
                     body.item_type, body.item_slug, body.item_name,
                     body.start_date, body.end_date,
                     body.num_people, body.total_price, body.deposit_paid,
                     body.status, body.notes),
                )
                new_id = cur.fetchone()[0]
                conn.commit()

        # 2. Notify admin via WhatsApp
        try:
            token    = os.getenv("WHATSAPP_API_TOKEN", "")
            phone_id = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
            admin    = os.getenv("ADMIN_PHONE", "56974950762")
            if token and phone_id:
                tipo_label = {
                    "alojamiento": "🏠 Alojamiento",
                    "experiencia": "🏔️ Experiencia",
                    "pack": "🎁 Pack Completo",
                }.get(body.item_type, body.item_type.title())
                fechas = body.start_date
                if body.end_date:
                    fechas += f" al {body.end_date}"
                precio_txt = f"${body.total_price:,}".replace(",", ".") if body.total_price else "a coordinar"
                msg = (
                    f"📋 *Nueva Solicitud Web* (extras-{new_id})\n\n"
                    f"*Tipo:* {tipo_label}\n"
                    f"*Servicio:* {body.item_name}\n"
                    f"*Cliente:* {body.customer_name}\n"
                    f"*Teléfono:* {body.customer_phone or '-'}\n"
                    f"*Fechas:* {fechas}\n"
                    f"*Personas:* {body.num_people}\n"
                    f"*Precio total:* {precio_txt}\n"
                    f"*Notas:* {body.notes or '-'}\n\n"
                    f"Responde directamente al cliente por WhatsApp 👇\n"
                    f"https://wa.me/{(body.customer_phone or '').replace('+','').replace(' ','')}"
                )
                async with _httpx.AsyncClient() as client:
                    await client.post(
                        f"https://graph.facebook.com/v17.0/{phone_id}/messages",
                        headers={"Authorization": f"Bearer {token}"},
                        json={"messaging_product": "whatsapp", "to": admin,
                              "type": "text", "text": {"body": msg}},
                        timeout=10,
                    )
        except Exception as notify_err:
            logger.warning(f"extras-booking WhatsApp notify failed: {notify_err}")

        return {"ok": True, "id": new_id}
    except Exception as e:
        logger.error(f"public extras booking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
