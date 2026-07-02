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
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _fmt_fecha(d: str) -> str:
    try:
        y, m, day = (d or "").split("-")
        return f"{day}/{m}/{y}"
    except Exception:
        return d or ""


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
    lang = (os.getenv("WA_REENGAGE_LANG", "") or "es").strip() or "es"

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
