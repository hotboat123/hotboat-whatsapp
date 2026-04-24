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

def _default_extra_icon(key: str) -> str:
    k = (key or "").lower()
    if "roman" in k or "flores" in k or "rosas" in k:  return "🌹"
    if "tabla" in k or "picot" in k:                   return "🧺"
    if "video" in k or "gopro" in k or "camara" in k:  return "🎥"
    if "traslado" in k or "transporte" in k or "trans" in k: return "🚗"
    if "toalla" in k or "poncho" in k:                 return "🏖️"
    if "espumante" in k or "champa" in k or "vino" in k or "botella" in k: return "🍾"
    if "cocktail" in k or "trago" in k or "pisco" in k: return "🍹"
    if "cerveza" in k:                                 return "🍺"
    if "foto" in k:                                    return "📸"
    if "kayak" in k:                                   return "🛶"
    if "sup" in k:                                     return "🏄"
    if "musica" in k or "dj" in k:                     return "🎵"
    if "deco" in k:                                    return "🎊"
    if "pack" in k:                                    return "📦"
    if "flex" in k:                                    return "🔒"
    return "🎁"


@content_router.get("/api/content/extras")
def list_extras():
    """Public endpoint: returns extras visible in the booking app (show_in_booking = TRUE)."""
    try:
        from app.booking.admin_router import _slugify_extra
        # Ensure name column exists before querying (may not exist on first deploy)
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    ALTER TABLE extras_visibility
                    ADD COLUMN IF NOT EXISTS name TEXT
                """)
                conn.commit()

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT extra_name_lower,
                           COALESCE(name, extra_name_lower) AS name,
                           COALESCE(precio_venta, 0)        AS price,
                           COALESCE(icon, '')               AS icon,
                           COALESCE(description, '')        AS description,
                           COALESCE(sort_order, 999)        AS sort_order
                    FROM extras_visibility
                    WHERE show_in_booking = TRUE
                    ORDER BY sort_order, extra_name_lower
                """)
                extras = []
                for (name_lower, name, price, icon, description, sort_order) in cur.fetchall():
                    key = _slugify_extra(name)
                    resolved_icon = icon or _default_extra_icon(key)
                    extras.append({
                        "id": name_lower,
                        "key": key,
                        "name": name,
                        "price": price,
                        "icon": resolved_icon,
                        "description": description,
                        "sort_order": int(sort_order),
                    })
        # already sorted by DB ORDER BY
        return {"extras": extras}
    except Exception as e:
        logger.error(f"Error fetching public extras: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@content_router.get("/api/content/alojamientos")
def list_alojamientos(active_only: bool = True):
    with get_connection() as conn:
        with conn.cursor() as cur:
            q = ("SELECT id,slug,name,group_name,icon,description,"
                 "price_from,cost_from,capacity,image_path,"
                 "COALESCE(extra_images,'[]'::jsonb) AS extra_images,"
                 "is_active,display_order"
                 " FROM alojamientos")
            if active_only:
                q += " WHERE is_active=TRUE"
            q += " ORDER BY display_order,id"
            cur.execute(q)
            cols = [d.name for d in cur.description]
            return {"alojamientos": [dict(zip(cols, r)) for r in cur.fetchall()]}


@content_router.get("/api/content/accommodation-availability/{slug}")
def get_accommodation_availability(slug: str):
    """
    Returns occupied date ranges (confirmed bookings — disabled in calendar)
    and admin-blocked date ranges (solicitud flow — look normal in calendar).
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM alojamientos WHERE slug=%s AND is_active=TRUE",
                (slug,)
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Alojamiento no encontrado")
            aloj_id = row[0]

            cur.execute(
                "SELECT check_in::text, check_out::text FROM accommodation_bookings"
                " WHERE accommodation_id=%s AND status NOT IN ('cancelled') AND check_out >= CURRENT_DATE"
                " ORDER BY check_in",
                (aloj_id,)
            )
            occupied = [{"start": r[0], "end": r[1]} for r in cur.fetchall()]

            cur.execute(
                "SELECT start_date::text, end_date::text, reason"
                " FROM accommodation_blocked_dates"
                " WHERE accommodation_id=%s AND end_date >= CURRENT_DATE"
                " ORDER BY start_date",
                (aloj_id,)
            )
            blocked = [{"start": r[0], "end": r[1], "reason": r[2]} for r in cur.fetchall()]

            return {"alojamiento_id": aloj_id, "occupied": occupied, "blocked": blocked}


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


def _send_accommodation_email(
    customer_name: str,
    customer_phone: str,
    item_name: str,
    item_slug: str,
    start_date: str,
    end_date: str,
    num_people: int,
    notes: str,
    booking_id: int,
):
    """Send email to Tomás with WhatsApp links to contact the accommodation owner."""
    import os, urllib.parse
    from app.bot.accommodations_contacts import ACCOMMODATION_CONTACTS, generate_whatsapp_link

    # Map slug → property key
    slug_lower = (item_slug or "").lower()
    if "open" in slug_lower or "sky" in slug_lower:
        prop_key = "open_sky"
    elif "relikura" in slug_lower:
        prop_key = "relikura"
    else:
        prop_key = None

    contact = ACCOMMODATION_CONTACTS.get(prop_key) if prop_key else None

    fechas = start_date
    if end_date:
        fechas += f" al {end_date}"

    # WhatsApp pre-filled message to the accommodation owner
    owner_msg = (
        f"Hola! Tengo una consulta de disponibilidad:\n\n"
        f"🏠 *Alojamiento:* {item_name}\n"
        f"👥 *Personas:* {num_people}\n"
        f"📅 *Fechas:* {fechas}\n\n"
        f"¿Tienen disponibilidad para estas fechas?\n\n"
        f"Cliente: {customer_name} ({customer_phone})"
    )

    # WhatsApp link to contact the CLIENT directly
    clean_client = (customer_phone or "").replace("+", "").replace(" ", "").replace("-", "")
    client_link = f"https://wa.me/{clean_client}" if clean_client else None

    # Build email HTML
    owner_section = ""
    if contact:
        owner_wa_link = generate_whatsapp_link(contact["whatsapp"], owner_msg)
        owner_section = f"""
        <div style="background:#ecfdf5;padding:20px;border-radius:8px;margin:16px 0">
          <h3 style="margin-top:0;color:#065f46">📞 Consultar disponibilidad con {contact['name']}</h3>
          <p>Haz click para abrir WhatsApp con el mensaje pre-escrito al propietario:</p>
          <a href="{owner_wa_link}"
             style="display:inline-block;background:#25D366;color:#fff;padding:12px 24px;
                    text-decoration:none;border-radius:6px;font-weight:bold">
            💬 Consultar con {contact['name']}
          </a>
        </div>"""

    client_section = ""
    if client_link:
        client_section = f"""
        <div style="background:#eff6ff;padding:20px;border-radius:8px;margin:16px 0">
          <h3 style="margin-top:0;color:#1e40af">📱 Contactar al cliente directamente</h3>
          <a href="{client_link}"
             style="display:inline-block;background:#25D366;color:#fff;padding:12px 24px;
                    text-decoration:none;border-radius:6px;font-weight:bold">
            💬 WhatsApp a {customer_name}
          </a>
        </div>"""

    html = f"""
<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
  <h2 style="color:#1d4ed8">🏠 Nueva Solicitud de Alojamiento — Web #{booking_id}</h2>
  <div style="background:#f3f4f6;padding:20px;border-radius:8px;margin:16px 0">
    <h3 style="margin-top:0">Detalles</h3>
    <p><strong>🏠 Alojamiento:</strong> {item_name}</p>
    <p><strong>📅 Fechas:</strong> {fechas}</p>
    <p><strong>👥 Personas:</strong> {num_people}</p>
    <p><strong>👤 Cliente:</strong> {customer_name}</p>
    <p><strong>📱 Teléfono:</strong> {customer_phone or '-'}</p>
    <p><strong>📝 Notas:</strong> {notes or '-'}</p>
  </div>
  {owner_section}
  {client_section}
  <p style="color:#9ca3af;font-size:12px;margin-top:24px">
    Solicitud automática desde la app de reservas HotBoat.
  </p>
</div>"""

    try:
        from app.config import get_settings
        settings = get_settings()
        resend_key  = (getattr(settings, "resend_api_key", "") or "").strip()
        from_addr   = (getattr(settings, "resend_from_confirmations", "") or "onboarding@resend.dev").strip()
        admin_email = os.getenv("ADMIN_EMAIL", "hotboatchile@gmail.com")
        if not resend_key:
            logger.warning("_send_accommodation_email: no RESEND_API_KEY, skipping email")
            return
        from app.email.resend_booking import send_booking_html
        send_booking_html(
            to=admin_email,
            subject=f"🏠 Nueva solicitud: {item_name} ({fechas})",
            html=html,
            from_address=from_addr,
            api_key=resend_key,
        )
        logger.info(f"Accommodation availability email sent for booking #{booking_id}")
    except Exception as e:
        logger.warning(f"_send_accommodation_email send failed: {e}")


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
                msg = (
                    f"📋 *Nueva Solicitud Web* (extras-{new_id})\n\n"
                    f"*Tipo:* {tipo_label}\n"
                    f"*Servicio:* {body.item_name}\n"
                    f"*Cliente:* {body.customer_name}\n"
                    f"*Teléfono:* {body.customer_phone or '-'}\n"
                    f"*Fechas:* {fechas}\n"
                    f"*Personas:* {body.num_people}\n"
                    f"*Notas:* {body.notes or '-'}\n\n"
                    f"Responde al cliente 👇\n"
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

        # 3. For accommodations: send email with WhatsApp links to owner + client
        if body.item_type == "alojamiento":
            try:
                import asyncio
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    None,
                    lambda: _send_accommodation_email(
                        customer_name=body.customer_name,
                        customer_phone=body.customer_phone or "",
                        item_name=body.item_name,
                        item_slug=body.item_slug,
                        start_date=body.start_date,
                        end_date=body.end_date or "",
                        num_people=body.num_people,
                        notes=body.notes or "",
                        booking_id=new_id,
                    )
                )
            except Exception as email_err:
                logger.warning(f"extras-booking accommodation email failed: {email_err}")

        return {"ok": True, "id": new_id}
    except Exception as e:
        logger.error(f"public extras booking error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Public coupon validation ────────────────────────────────────────────────

@content_router.get("/api/booking/coupon/{code}")
def validate_coupon(code: str):
    """Validate a coupon code and return its discount info (public endpoint)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, code, name, discount_percent, discount_fixed,
                       extra_description, max_uses, uses_count, expires_at
                FROM coupons
                WHERE UPPER(code)=UPPER(%s) AND is_active=TRUE
            """, (code.strip(),))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Cupón no válido o inactivo")
            cols = ["id","code","name","discount_percent","discount_fixed",
                    "extra_description","max_uses","uses_count","expires_at"]
            c = dict(zip(cols, row))
            # Check expiry
            from datetime import date
            if c["expires_at"] and c["expires_at"] < date.today():
                raise HTTPException(status_code=410, detail="Este cupón ha expirado")
            # Check max uses
            if c["max_uses"] and c["uses_count"] >= c["max_uses"]:
                raise HTTPException(status_code=410, detail="Este cupón ya alcanzó el límite de usos")
            return {
                "valid": True,
                "code": c["code"],
                "name": c["name"],
                "discount_percent": float(c["discount_percent"] or 0),
                "discount_fixed": float(c["discount_fixed"] or 0),
                "extra_description": c["extra_description"] or "",
            }
