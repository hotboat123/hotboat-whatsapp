"""Booking confirmation emails after payment (WooCommerce webhook / MercadoPago return)."""
import logging
import re
from typing import Any, Dict, Optional

from app.config import get_settings
from app.booking.db import get_booking_by_ref, mark_confirmation_email_sent
from app.booking.operator_settings import get_email_booking_config
from app.email.resend_booking import send_booking_html

logger = logging.getLogger(__name__)

EMAIL_SUBJECT_FALLBACK = "Reserva confirmada — {{booking_ref}}"

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def _fmt_clp(n: Any) -> str:
    try:
        v = int(float(n or 0))
    except (TypeError, ValueError):
        v = 0
    s = f"{v:,}".replace(",", ".")
    return f"${s} CLP"


def _booking_template_context(booking: dict) -> Dict[str, str]:
    s = get_settings()
    bd = booking.get("booking_date") or ""
    bt = booking.get("booking_time") or ""
    if isinstance(bt, str) and len(bt) >= 5:
        bt = bt[:5]
    return {
        "booking_ref": str(booking.get("booking_ref") or ""),
        "customer_name": str(booking.get("customer_name") or "").strip() or "Cliente",
        "customer_email": str(booking.get("customer_email") or "").strip(),
        "customer_phone": str(booking.get("customer_phone") or "").strip(),
        "booking_date": str(bd),
        "booking_time": str(bt),
        "num_people": str(booking.get("num_people") or ""),
        "total_price": str(booking.get("total_price") or ""),
        "total_price_fmt": _fmt_clp(booking.get("total_price")),
        "subtotal_fmt": _fmt_clp(booking.get("subtotal")),
        "extras_total_fmt": _fmt_clp(booking.get("extras_total")),
        "business_name": getattr(s, "business_name", "Hot Boat"),
        "business_phone": getattr(s, "business_phone", ""),
        "business_email": getattr(s, "business_email", ""),
        "business_website": getattr(s, "business_website", ""),
    }


def _apply_template(template: str, ctx: Dict[str, str]) -> str:
    def repl(m: re.Match) -> str:
        key = m.group(1)
        return ctx.get(key, "")

    return _PLACEHOLDER.sub(repl, template)


def default_confirmation_html(ctx: Dict[str, str]) -> str:
    return f"""<!DOCTYPE html>
<html><body style="margin:0;background:#f0f2f5;font-family:Georgia,'Times New Roman',serif;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="background:#f0f2f5;padding:28px 16px;">
<tr><td align="center">
  <table role="presentation" width="560" cellspacing="0" cellpadding="0" style="max-width:560px;background:#ffffff;border-radius:14px;overflow:hidden;box-shadow:0 8px 32px rgba(15,23,42,.08);">
    <tr><td style="background:linear-gradient(135deg,#0f172a,#1e3a5f);color:#fefce8;padding:22px 26px;font-size:18px;font-weight:700;">
      {ctx.get('business_name', 'Hot Boat')} — Reserva confirmada
    </td></tr>
    <tr><td style="padding:26px 26px 8px;color:#0f172a;font-size:15px;line-height:1.65;">
      <p style="margin:0 0 14px;">Hola <strong>{ctx.get('customer_name', '')}</strong>,</p>
      <p style="margin:0 0 14px;">Tu pago se registró correctamente. Tu reserva <strong>{ctx.get('booking_ref', '')}</strong> está <strong>confirmada</strong>.</p>
    </td></tr>
    <tr><td style="padding:0 26px 22px;">
      <table role="presentation" width="100%" style="background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0;font-size:14px;color:#334155;">
        <tr><td style="padding:14px 16px;"><strong>Fecha</strong></td><td style="padding:14px 16px;text-align:right;">{ctx.get('booking_date', '')}</td></tr>
        <tr><td style="padding:14px 16px;border-top:1px solid #e2e8f0;"><strong>Hora</strong></td><td style="padding:14px 16px;border-top:1px solid #e2e8f0;text-align:right;">{ctx.get('booking_time', '')}</td></tr>
        <tr><td style="padding:14px 16px;border-top:1px solid #e2e8f0;"><strong>Personas</strong></td><td style="padding:14px 16px;border-top:1px solid #e2e8f0;text-align:right;">{ctx.get('num_people', '')}</td></tr>
        <tr><td style="padding:14px 16px;border-top:1px solid #e2e8f0;"><strong>Total</strong></td><td style="padding:14px 16px;border-top:1px solid #e2e8f0;text-align:right;">{ctx.get('total_price_fmt', '')}</td></tr>
      </table>
    </td></tr>
    <tr><td style="padding:0 26px 26px;font-size:13px;color:#64748b;line-height:1.6;">
      <p style="margin:0;">Cualquier duda, escríbenos por WhatsApp <strong>{ctx.get('business_phone', '')}</strong> o responde a este correo.</p>
      <p style="margin:12px 0 0;"><a href="{ctx.get('business_website', '#')}" style="color:#1e40af;">{ctx.get('business_website', '')}</a></p>
    </td></tr>
  </table>
</td></tr></table>
</body></html>"""


def try_send_booking_confirmation_after_payment(booking_ref: str) -> Dict[str, Any]:
    """
    Send confirmation email once per booking (checks confirmation_email_sent_at).
    Safe to call from webhook retries.
    """
    out: Dict[str, Any] = {"sent": False, "reason": ""}
    settings = get_settings()
    if not getattr(settings, "resend_api_key", ""):
        out["reason"] = "no_resend_key"
        return out

    cfg = get_email_booking_config()
    if not cfg.get("confirmation_enabled"):
        out["reason"] = "disabled"
        return out
    if not cfg.get("on_payment_confirmed", True):
        out["reason"] = "trigger_off"
        return out

    booking = get_booking_by_ref(booking_ref)
    if not booking:
        out["reason"] = "not_found"
        return out
    if str(booking.get("status") or "") != "confirmed":
        out["reason"] = "not_confirmed"
        return out
    if booking.get("confirmation_email_sent_at"):
        out["reason"] = "already_sent"
        return out

    to_addr = (booking.get("customer_email") or "").strip()
    if not to_addr:
        out["reason"] = "no_customer_email"
        return out

    ctx = _booking_template_context(booking)
    raw_html = (cfg.get("body_html") or "").strip()
    html = _apply_template(raw_html, ctx) if raw_html else default_confirmation_html(ctx)
    subject = _apply_template((cfg.get("subject") or "").strip() or EMAIL_SUBJECT_FALLBACK, ctx)

    from_addr = (getattr(settings, "resend_from_confirmations", "") or "").strip()
    if not from_addr:
        from_addr = (getattr(settings, "email_from", "") or "").strip() or "onboarding@resend.dev"

    bcc_raw = (getattr(settings, "resend_bcc_booking", "") or "").strip()
    bcc_list = [e.strip() for e in bcc_raw.split(",") if e.strip()] if bcc_raw else None

    try:
        send_booking_html(
            to=to_addr,
            subject=subject,
            html=html,
            from_address=from_addr,
            api_key=settings.resend_api_key,
            bcc=bcc_list,
        )
    except Exception as e:
        logger.exception("Booking confirmation email failed for %s: %s", booking_ref, e)
        out["reason"] = f"send_error:{e}"
        return out

    if mark_confirmation_email_sent(booking_ref):
        out["sent"] = True
        out["reason"] = "ok"
    else:
        out["reason"] = "mark_failed"
    return out


def send_test_booking_email(to_address: str) -> Dict[str, Any]:
    """Send a sample confirmation to verify Resend + templates (does not touch DB)."""
    out: Dict[str, Any] = {"sent": False, "reason": ""}
    to_address = (to_address or "").strip()
    if not to_address:
        out["reason"] = "no_to"
        return out

    settings = get_settings()
    if not getattr(settings, "resend_api_key", ""):
        out["reason"] = "no_resend_key"
        return out

    cfg = get_email_booking_config()
    sample = {
        "booking_ref": "HB-2026-DEMO1",
        "customer_name": "Cliente de prueba",
        "customer_email": to_address,
        "customer_phone": "+56 9 0000 0000",
        "booking_date": "2026-04-15",
        "booking_time": "10:00",
        "num_people": "4",
        "total_price": "200000",
        "total_price_fmt": _fmt_clp(200000),
        "subtotal_fmt": _fmt_clp(180000),
        "extras_total_fmt": _fmt_clp(20000),
        "business_name": getattr(settings, "business_name", "Hot Boat"),
        "business_phone": getattr(settings, "business_phone", ""),
        "business_email": getattr(settings, "business_email", ""),
        "business_website": getattr(settings, "business_website", ""),
    }
    raw_html = (cfg.get("body_html") or "").strip()
    html = _apply_template(raw_html, sample) if raw_html else default_confirmation_html(sample)
    subject = "[Prueba] " + _apply_template(
        (cfg.get("subject") or "").strip() or EMAIL_SUBJECT_FALLBACK, sample
    )

    from_addr = (getattr(settings, "resend_from_confirmations", "") or "").strip()
    if not from_addr:
        from_addr = (getattr(settings, "email_from", "") or "").strip() or "onboarding@resend.dev"

    bcc_raw = (getattr(settings, "resend_bcc_booking", "") or "").strip()
    bcc_list = [e.strip() for e in bcc_raw.split(",") if e.strip()] if bcc_raw else None

    try:
        send_booking_html(
            to=to_address,
            subject=subject,
            html=html,
            from_address=from_addr,
            api_key=settings.resend_api_key,
            bcc=bcc_list,
        )
        out["sent"] = True
        out["reason"] = "ok"
    except Exception as e:
        logger.exception("Test booking email failed: %s", e)
        out["reason"] = str(e)
    return out
