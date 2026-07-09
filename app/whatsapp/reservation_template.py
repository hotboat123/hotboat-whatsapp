"""Send the 'contactar_cliente_por_reserva' WhatsApp template — a
business-initiated message that works outside the 24h session window.

Requires the customer's reservation data to fill the template body (nombre,
"HotBoat", fecha, hora) and the dynamic button parameter (booking_ref, which
builds the /mireserva/{booking_ref} link on Meta's side).

Used by:
  - app/main.py: /api/send-message fallback when a free-text send fails
    because the customer hasn't written in the last 24h.
  - app/booking/admin_router.py: the "🦜 Popeye" button in the reservation
    summary, to contact the client about a same-day reservation directly.
"""
import os
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def _fmt_fecha(d: str) -> str:
    try:
        y, m, day = (d or "").split("-")
        return f"{day}/{m}/{y}"
    except Exception:
        return d or ""


def is_24h_window_error(exc: Exception) -> bool:
    """True si el error de WhatsApp/Meta es por estar fuera de la ventana de
    24h (code 131047 / re-engagement) — es decir, que el texto libre no se
    puede enviar y hace falta una plantilla."""
    body = ""
    try:
        body = exc.response.text or ""
    except Exception:
        body = ""
    bl = body.lower()
    return ("131047" in body or "24 hours" in bl or "re-engagement" in bl
            or "reengagement" in bl or "outside the allowed window" in bl)


async def send_free_text_or_template(
    phone: str,
    message: str,
    *,
    booking_ref: str,
    customer_name: str,
    booking_date: str,
    booking_time: str,
) -> Dict[str, Any]:
    """Intenta primero un mensaje de texto libre (gratis si el cliente escribió
    en las últimas 24h). Solo si Meta lo rechaza por estar fuera de esa
    ventana, envía la plantilla de contacto (con costo). Así nunca se paga de
    más: el fallback a plantilla solo ocurre cuando es estrictamente
    necesario, sin depender de qué política de precios tenga Meta vigente.

    IMPORTANTE: WhatsApp acepta el envío de texto libre con 200 OK aunque el
    cliente esté fuera de la ventana de 24h — el rechazo real ('re-engagement',
    code 131047) llega recién después por un webhook de estado async, cuando
    el admin ya cree que el mensaje se entregó. Por eso NO confiamos en la
    respuesta síncrona de Meta para decidir: primero chequeamos en nuestra
    propia DB si el cliente escribió realmente en las últimas 24h, y solo
    intentamos texto libre si es así.

    Devuelve {"via": "text"|"template", **datos de la respuesta de Meta}.
    """
    import httpx
    from app.whatsapp.client import whatsapp_client
    from app.db.queries import has_recent_inbound_message

    if await has_recent_inbound_message(phone):
        try:
            result = await whatsapp_client.send_text_message(phone, message)
            return {"via": "text", **result}
        except httpx.HTTPStatusError as e:
            if not is_24h_window_error(e):
                raise

    result = await send_reservation_contact_template(
        phone=phone, booking_ref=booking_ref, customer_name=customer_name,
        booking_date=booking_date, booking_time=booking_time)
    return {"via": "template", **result}


async def send_reservation_contact_template(
    phone: str,
    booking_ref: str,
    customer_name: str,
    booking_date: str,
    booking_time: str,
) -> Dict[str, Any]:
    """Send the reservation-contact template to `phone`.

    Raises RuntimeError if WA_REENGAGE_TEMPLATE isn't configured, or
    httpx.HTTPStatusError if WhatsApp/Meta rejects the send — callers should
    catch and surface a clear message rather than letting it bubble raw.
    """
    from app.whatsapp.client import whatsapp_client

    tmpl = (os.getenv("WA_REENGAGE_TEMPLATE", "") or "").strip()
    if not tmpl:
        raise RuntimeError("WA_REENGAGE_TEMPLATE no está configurado (Railway → Variables).")
    # Meta rejected "es" with 132001 ("template does not exist in the
    # translation") — la plantilla se creó sin cambiar el idioma, así que
    # quedó en el default de Meta al crear plantillas: English (US).
    lang = (os.getenv("WA_REENGAGE_LANG", "") or "en_US").strip() or "en_US"

    components = [
        {"type": "body", "parameters": [
            {"type": "text", "text": customer_name or "cliente"},
            {"type": "text", "text": "HotBoat"},
            {"type": "text", "text": _fmt_fecha(booking_date)},
            {"type": "text", "text": (booking_time or "")[:5]},
        ]},
        {"type": "button", "sub_type": "url", "index": "0",
         "parameters": [{"type": "text", "text": booking_ref or ""}]},
    ]
    logger.info("Enviando plantilla %s a %s para reserva %s", tmpl, phone, booking_ref)
    return await whatsapp_client.send_template_message(
        phone, tmpl, language_code=lang, components=components)
