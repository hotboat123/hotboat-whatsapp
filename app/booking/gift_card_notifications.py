"""Admin notification emails for the gift-card sales funnel — mirrors the
three-stage pattern already used for regular reservations (admin_new_lead /
the pending-payment abandoned-cart recovery / admin_booking_confirmed in
booking_email.py), but self-contained here since gift cards live in their
own table (gift_cards), not all_appointments:

  1. notify_admin_gift_card_lead      — fired the instant a gift card is
     created (status='pending_payment'), before the buyer has paid.
  2. run_gift_card_abandoned_sweep    — polled every 2 min; emails once per
     gift card still 'pending_payment' after GIFT_CARD_ABANDONED_MINUTES.
  3. notify_admin_gift_card_confirmed — fired when Transbank confirms the
     payment (gift_cards_router.py::confirm_gift_card_payment), alongside
     the existing customer-facing _send_gift_card_email.

Before this module, a completed gift-card sale sent an email to the buyer
only — nothing ever told the operator a sale had happened at all."""
import logging

logger = logging.getLogger(__name__)

ADMIN_NOTIFICATION_EMAIL = "hotboatnotification@gmail.com"
GIFT_CARD_ABANDONED_MINUTES = 5


def _send(to: str, subject: str, html: str) -> None:
    from app.config import get_settings
    from app.email.send_email import send_email

    settings = get_settings()
    from_addr = (
        getattr(settings, "resend_from_confirmations", "")
        or getattr(settings, "email_from", "")
        or "noreply@reservas.hotboat.cl"
    ).strip()

    result = send_email(
        to=to,
        subject=subject,
        html=html,
        from_address=from_addr,
        trigger="gift_card_admin_notif",
    )
    if not result["sent"]:
        logger.warning("gift_card_notifications: send failed: %s", result["reason"])


def _fmt_clp(amount) -> str:
    try:
        return f"${float(amount or 0):,.0f}".replace(",", ".")
    except Exception:
        return str(amount or 0)


def _card_html(headline: str, status_bg: str, status_color: str, status_text: str, gc: dict, extra_rows: str = "") -> str:
    n = gc.get("num_people") or ((gc.get("num_adultos") or 0) + (gc.get("num_ninos") or 0))
    recipient = gc.get("recipient_name") or ""
    recipient_row = f"<tr><td>Destinatario</td><td>{recipient}</td></tr>" if recipient else ""
    return f"""
<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8">
<style>
  body{{font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:20px}}
  .card{{background:#fff;border-radius:12px;max-width:520px;margin:auto;padding:28px;box-shadow:0 2px 8px rgba(0,0,0,.1)}}
  h2{{color:#1a1a2e;margin:0 0 10px;font-size:19px}}
  .status{{display:inline-block;background:{status_bg};color:{status_color};border-radius:20px;
           padding:5px 16px;font-size:13px;font-weight:700;margin-bottom:18px}}
  table{{width:100%;border-collapse:collapse}}
  td{{padding:8px 6px;border-bottom:1px solid #eee;font-size:14px}}
  td:first-child{{color:#666;width:40%}}
  .ref{{color:#888;font-size:12px;margin-top:16px}}
</style>
</head>
<body>
<div class="card">
  <h2>{headline}</h2>
  <div class="status">{status_text}</div>
  <table>
    <tr><td>Comprador</td><td><strong>{gc.get('buyer_name') or '-'}</strong></td></tr>
    <tr><td>Teléfono</td><td><a href="https://wa.me/{(gc.get('buyer_phone') or '').replace(' ','').replace('+','')}" style="color:#128C7E;text-decoration:none">{gc.get('buyer_phone') or '-'}</a></td></tr>
    <tr><td>Email</td><td>{gc.get('buyer_email') or '-'}</td></tr>
    {recipient_row}
    <tr><td>Personas</td><td>{n}</td></tr>
    <tr><td>Monto</td><td><strong>{_fmt_clp(gc.get('amount'))}</strong></td></tr>
    {extra_rows}
  </table>
  <p class="ref">Gift card: {gc.get('code') or '-'} · HotBoat Chile</p>
</div>
</body>
</html>
"""


def notify_admin_gift_card_lead(gc: dict) -> None:
    """Sent the instant a gift card purchase starts (status='pending_payment'),
    same moment admin_new_lead fires for a regular reservation."""
    code = gc.get("code") or "-"
    subject = f"🎁 Nuevo lead — gift card {code} ({_fmt_clp(gc.get('amount'))})"
    html = _card_html(
        f"🎁 Nuevo intento de compra de gift card",
        "#ede9fe", "#6d28d9", "🕐 Esperando pago",
        gc,
    )
    try:
        _send(ADMIN_NOTIFICATION_EMAIL, subject, html)
        logger.info("notify_admin_gift_card_lead sent for %s", code)
    except Exception as e:
        logger.error("notify_admin_gift_card_lead failed for %s: %s", code, e)


def notify_admin_gift_card_abandoned(gc: dict) -> None:
    """Sent once, GIFT_CARD_ABANDONED_MINUTES after creation, if the gift
    card is still unpaid — same idea as the "dejó el carrito" recovery
    email for a reservation, but admin-facing (no separate marketing
    system exists for gift cards)."""
    code = gc.get("code") or "-"
    subject = f"🛒 Carrito de gift card abandonado — {code}"
    html = _card_html(
        "🛒 Carrito de gift card abandonado",
        "#ffebee", "#c62828", f"⚠️ Sin pagar hace +{GIFT_CARD_ABANDONED_MINUTES} min",
        gc,
    )
    try:
        _send(ADMIN_NOTIFICATION_EMAIL, subject, html)
        logger.info("notify_admin_gift_card_abandoned sent for %s", code)
    except Exception as e:
        logger.error("notify_admin_gift_card_abandoned failed for %s: %s", code, e)


def notify_admin_gift_card_confirmed(code: str) -> None:
    """Sent the moment Transbank confirms payment — the admin-facing
    counterpart to the buyer's own _send_gift_card_email."""
    from app.booking.gift_cards_router import get_gift_card_by_code

    gc = get_gift_card_by_code(code)
    if not gc:
        logger.warning("notify_admin_gift_card_confirmed: %s not found", code)
        return

    dedication_row = ""
    if gc.get("dedication") or gc.get("sender_name"):
        parts = []
        if gc.get("sender_name"):
            parts.append(f"De: {gc['sender_name']}")
        if gc.get("dedication"):
            parts.append(f"“{gc['dedication']}”")
        dedication_row = f"<tr><td>Dedicatoria</td><td>{' · '.join(parts)}</td></tr>"

    subject = f"✅ Gift card vendida — {code} ({_fmt_clp(gc.get('amount'))})"
    html = _card_html(
        "✅ ¡Gift card vendida y pagada!",
        "#e8f5e9", "#2e7d32", "✅ Pago confirmado",
        gc,
        extra_rows=dedication_row,
    )
    try:
        _send(ADMIN_NOTIFICATION_EMAIL, subject, html)
        logger.info("notify_admin_gift_card_confirmed sent for %s", code)
    except Exception as e:
        logger.error("notify_admin_gift_card_confirmed failed for %s: %s", code, e)


def get_gift_cards_pending_abandoned_notif(stale_minutes: int = GIFT_CARD_ABANDONED_MINUTES) -> list:
    """Gift cards still unpaid after stale_minutes that haven't had the
    abandoned-cart admin email sent yet."""
    from app.db.connection import get_connection
    from app.booking.gift_cards_router import _ensure_gift_cards_table

    with get_connection() as conn:
        with conn.cursor() as cur:
            _ensure_gift_cards_table(cur)
            cur.execute("""
                ALTER TABLE gift_cards
                    ADD COLUMN IF NOT EXISTS abandoned_cart_notif_sent_at TIMESTAMPTZ
            """)
            conn.commit()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT code, num_adultos, num_ninos, amount, buyer_name, buyer_phone,
                       buyer_email, recipient_name
                FROM gift_cards
                WHERE status = 'pending_payment'
                  AND created_at < NOW() - (INTERVAL '1 minute' * %s)
                  AND abandoned_cart_notif_sent_at IS NULL
            """, (stale_minutes,))
            cols = ["code", "num_adultos", "num_ninos", "amount", "buyer_name",
                    "buyer_phone", "buyer_email", "recipient_name"]
            rows = [dict(zip(cols, row)) for row in cur.fetchall()]
            for r in rows:
                r["num_people"] = (r.get("num_adultos") or 0) + (r.get("num_ninos") or 0)
            return rows


def mark_gift_card_abandoned_notif_sent(code: str) -> None:
    from app.db.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE gift_cards SET abandoned_cart_notif_sent_at = NOW() WHERE code = %s",
                (code,),
            )
            conn.commit()


def run_gift_card_abandoned_sweep() -> dict:
    """Check for gift cards still unpaid after GIFT_CARD_ABANDONED_MINUTES
    and send the abandoned-cart admin email. Runs every 2 min."""
    result = {"checked": 0, "sent": 0, "errors": 0}
    try:
        cards = get_gift_cards_pending_abandoned_notif()
        result["checked"] = len(cards)
        for gc in cards:
            code = gc.get("code", "")
            try:
                notify_admin_gift_card_abandoned(gc)
                mark_gift_card_abandoned_notif_sent(code)
                result["sent"] += 1
            except Exception as e:
                logger.error("gift card abandoned sweep for %s: %s", code, e)
                result["errors"] += 1
    except Exception as e:
        logger.error("run_gift_card_abandoned_sweep: %s", e)
    return result
