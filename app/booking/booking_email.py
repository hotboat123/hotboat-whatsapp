"""Booking email workflows — send transactional emails via Resend for each trigger."""
import logging
import re
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.booking.db import (
    get_booking_by_ref, mark_confirmation_email_sent,
    get_bookings_for_followup, mark_followup_email_sent,
    get_customers_for_birthday_email, mark_birthday_email_sent,
)
from app.booking.operator_settings import get_email_workflow, TRIGGER_META
from app.email.resend_booking import send_booking_html

logger = logging.getLogger(__name__)

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_clp(n: Any) -> str:
    try:
        v = int(float(n or 0))
    except (TypeError, ValueError):
        v = 0
    return f"${v:,}".replace(",", ".")  # e.g. $179.970


def _apply_template(template: str, ctx: Dict[str, str]) -> str:
    return _PLACEHOLDER.sub(lambda m: ctx.get(m.group(1), ""), template)


def _booking_ctx(booking: dict, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    s = get_settings()
    bt = str(booking.get("booking_time") or "")
    if len(bt) >= 5:
        bt = bt[:5]
    ctx = {
        "booking_ref":      str(booking.get("booking_ref") or ""),
        "customer_name":    str(booking.get("customer_name") or "").strip() or "Cliente",
        "customer_email":   str(booking.get("customer_email") or "").strip(),
        "customer_phone":   str(booking.get("customer_phone") or "").strip(),
        "booking_date":     str(booking.get("booking_date") or ""),
        "booking_time":     bt,
        "num_people":       str(booking.get("num_people") or ""),
        "total_price":      str(booking.get("total_price") or ""),
        "total_price_fmt":  _fmt_clp(booking.get("total_price")),
        "subtotal_fmt":     _fmt_clp(booking.get("subtotal")),
        "extras_total_fmt": _fmt_clp(booking.get("extras_total")),
        "status":           str(booking.get("status") or ""),
        "business_name":    getattr(s, "business_name", "Hot Boat"),
        "business_phone":   getattr(s, "business_phone", ""),
        "business_email":   getattr(s, "business_email", ""),
        "business_website": getattr(s, "business_website", ""),
    }
    if extra:
        ctx.update(extra)
    return ctx


def _sample_ctx(to_addr: str) -> Dict[str, str]:
    s = get_settings()
    return {
        "booking_ref":      "HB-2026-DEMO1",
        "customer_name":    "Cliente de prueba",
        "customer_email":   to_addr,
        "customer_phone":   "+56 9 0000 0000",
        "booking_date":     "2026-04-15",
        "booking_time":     "10:00",
        "num_people":       "4",
        "total_price":      "200000",
        "total_price_fmt":  _fmt_clp(200000),
        "subtotal_fmt":     _fmt_clp(180000),
        "extras_total_fmt": _fmt_clp(20000),
        "status":           "confirmed",
        "business_name":    getattr(s, "business_name", "Hot Boat"),
        "business_phone":   getattr(s, "business_phone", ""),
        "business_email":   getattr(s, "business_email", ""),
        "business_website": getattr(s, "business_website", ""),
    }


# ── Default HTML templates ────────────────────────────────────────────────────

def _header(ctx: Dict[str, str], title: str, accent: str = "#0f172a") -> str:
    return f"""<!DOCTYPE html>
<html><body style="margin:0;background:#f0f2f5;font-family:Georgia,'Times New Roman',serif;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
  style="background:#f0f2f5;padding:28px 16px;">
<tr><td align="center">
<table role="presentation" width="560" cellspacing="0" cellpadding="0"
  style="max-width:560px;background:#fff;border-radius:14px;overflow:hidden;
         box-shadow:0 8px 32px rgba(15,23,42,.08);">
<tr><td style="background:{accent};color:#fefce8;padding:22px 26px;
               font-size:18px;font-weight:700;">
  {ctx.get('business_name','Hot Boat')} — {title}
</td></tr>"""


def _details_table(ctx: Dict[str, str]) -> str:
    rows = [
        ("Referencia", ctx.get("booking_ref", "")),
        ("Fecha",      ctx.get("booking_date", "")),
        ("Hora",       ctx.get("booking_time", "")),
        ("Personas",   ctx.get("num_people", "")),
        ("Total",      ctx.get("total_price_fmt", "")),
    ]
    trs = ""
    for i, (label, val) in enumerate(rows):
        border = "border-top:1px solid #e2e8f0;" if i else ""
        trs += (f'<tr><td style="padding:12px 16px;{border}"><strong>{label}</strong></td>'
                f'<td style="padding:12px 16px;{border}text-align:right;">{val}</td></tr>')
    return (f'<table role="presentation" width="100%"'
            f' style="background:#f8fafc;border-radius:10px;border:1px solid #e2e8f0;'
            f'font-size:14px;color:#334155;">{trs}</table>')


def _footer(ctx: Dict[str, str]) -> str:
    return f"""<tr><td style="padding:18px 26px 26px;font-size:13px;color:#64748b;line-height:1.6;">
  <p style="margin:0;">Consultas: WhatsApp <strong>{ctx.get('business_phone','')}</strong>
     o responde este correo.</p>
  <p style="margin:10px 0 0;"><a href="{ctx.get('business_website','#')}"
     style="color:#1e40af;">{ctx.get('business_website','')}</a></p>
</td></tr></table></td></tr></table></body></html>"""


def _default_html_booking_created(ctx: Dict[str, str]) -> str:
    return (
        _header(ctx, "Recibimos tu solicitud", "#1e3a5f")
        + f"""<tr><td style="padding:26px 26px 8px;color:#0f172a;font-size:15px;line-height:1.65;">
  <p style="margin:0 0 12px;">Hola <strong>{ctx.get('customer_name','')}</strong>,</p>
  <p style="margin:0 0 12px;">Recibimos tu solicitud de reserva
     <strong>{ctx.get('booking_ref','')}</strong>.
     Completa el pago para confirmarla.</p>
</td></tr>
<tr><td style="padding:0 26px 20px;">{_details_table(ctx)}</td></tr>"""
        + _footer(ctx)
    )


def _default_html_booking_confirmed(ctx: Dict[str, str]) -> str:
    return (
        _header(ctx, "Reserva confirmada ✓", "linear-gradient(135deg,#0f172a,#1e3a5f)")
        + f"""<tr><td style="padding:26px 26px 8px;color:#0f172a;font-size:15px;line-height:1.65;">
  <p style="margin:0 0 12px;">Hola <strong>{ctx.get('customer_name','')}</strong>,</p>
  <p style="margin:0 0 12px;">Tu pago se registró correctamente.
     Tu reserva <strong>{ctx.get('booking_ref','')}</strong> está
     <strong style="color:#15803d;">confirmada</strong>. ¡Nos vemos en el agua!</p>
</td></tr>
<tr><td style="padding:0 26px 20px;">{_details_table(ctx)}</td></tr>"""
        + _footer(ctx)
    )


def _default_html_booking_cancelled(ctx: Dict[str, str]) -> str:
    return (
        _header(ctx, "Reserva cancelada", "#7f1d1d")
        + f"""<tr><td style="padding:26px 26px 8px;color:#0f172a;font-size:15px;line-height:1.65;">
  <p style="margin:0 0 12px;">Hola <strong>{ctx.get('customer_name','')}</strong>,</p>
  <p style="margin:0 0 12px;">Te informamos que tu reserva
     <strong>{ctx.get('booking_ref','')}</strong> ha sido <strong>cancelada</strong>.
     Si tienes dudas o quieres reagendar, contáctanos.</p>
</td></tr>
<tr><td style="padding:0 26px 20px;">{_details_table(ctx)}</td></tr>"""
        + _footer(ctx)
    )


def _default_html_booking_status_changed(ctx: Dict[str, str]) -> str:
    return (
        _header(ctx, "Actualización de reserva", "#1e40af")
        + f"""<tr><td style="padding:26px 26px 8px;color:#0f172a;font-size:15px;line-height:1.65;">
  <p style="margin:0 0 12px;">Hola <strong>{ctx.get('customer_name','')}</strong>,</p>
  <p style="margin:0 0 12px;">El estado de tu reserva
     <strong>{ctx.get('booking_ref','')}</strong> ha sido actualizado a
     <strong>{ctx.get('status','')}</strong>.</p>
</td></tr>
<tr><td style="padding:0 26px 20px;">{_details_table(ctx)}</td></tr>"""
        + _footer(ctx)
    )


def _default_html_booking_followup(ctx: Dict[str, str]) -> str:
    return (
        _header(ctx, "¡Gracias por navegar con nosotros!", "#0f4c35")
        + f"""<tr><td style="padding:26px 26px 8px;color:#0f172a;font-size:15px;line-height:1.65;">
  <p style="margin:0 0 12px;">Hola <strong>{ctx.get('customer_name','')}</strong>,</p>
  <p style="margin:0 0 12px;">¡Fue un placer tenerte a bordo! Esperamos que hayas disfrutado
     tu experiencia en el agua el pasado <strong>{ctx.get('booking_date','')}</strong>.</p>
  <p style="margin:0 0 12px;">Si tienes un momento, nos ayudaría mucho que dejaras una reseña.
     ¡Y estaremos encantados de verte de nuevo pronto! 🌊</p>
</td></tr>
<tr><td style="padding:0 26px 20px;">{_details_table(ctx)}</td></tr>"""
        + _footer(ctx)
    )


def _default_html_admin_new_lead(ctx: Dict[str, str]) -> str:
    return (
        _header(ctx, "Nuevo lead en formulario", "#7c3aed")
        + f"""<tr><td style="padding:22px 26px 6px;color:#0f172a;font-size:15px;line-height:1.65;">
  <p style="margin:0 0 10px;">Un cliente acaba de completar sus datos y avanzó al pago.</p>
</td></tr>
<tr><td style="padding:0 26px 20px;">
  <table role="presentation" width="100%" style="background:#f8fafc;border-radius:10px;
         border:1px solid #e2e8f0;font-size:14px;color:#334155;">
    <tr><td style="padding:12px 16px"><strong>Nombre</strong></td>
        <td style="padding:12px 16px;text-align:right">{ctx.get('customer_name','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #e2e8f0"><strong>Teléfono</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #e2e8f0;text-align:right">{ctx.get('customer_phone','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #e2e8f0"><strong>Email</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #e2e8f0;text-align:right">{ctx.get('customer_email','—')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #e2e8f0"><strong>Fecha</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #e2e8f0;text-align:right">{ctx.get('booking_date','')} {ctx.get('booking_time','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #e2e8f0"><strong>Personas</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #e2e8f0;text-align:right">{ctx.get('num_people','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #e2e8f0"><strong>Total</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #e2e8f0;text-align:right">{ctx.get('total_price_fmt','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #e2e8f0"><strong>Ref</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #e2e8f0;text-align:right;font-family:monospace">{ctx.get('booking_ref','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #e2e8f0"><strong>Estado</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #e2e8f0;text-align:right;color:#b45309">pendiente de pago</td></tr>
  </table>
</td></tr>"""
        + _footer(ctx)
    )


def _default_html_customer_birthday(ctx: Dict[str, str]) -> str:
    return (
        _header(ctx, "¡Feliz cumpleaños! 🎂", "linear-gradient(135deg,#7c3aed,#db2777)")
        + f"""<tr><td style="padding:26px 26px 8px;color:#0f172a;font-size:15px;line-height:1.65;">
  <p style="margin:0 0 14px;">Hola <strong>{ctx.get('customer_name','')}</strong>,</p>
  <p style="margin:0 0 14px;">El equipo de <strong>{ctx.get('business_name','Hot Boat')}</strong>
     te desea un maravilloso cumpleaños. 🎉</p>
  <p style="margin:0 0 14px;">¡Gracias por ser parte de nuestra comunidad! Esperamos verte
     de nuevo pronto en el agua.</p>
</td></tr>
<tr><td style="padding:0 26px 26px;font-size:13px;color:#64748b;line-height:1.6;">
  <p style="margin:0;">¿Listo para un nuevo paseo? Escríbenos al
     <strong>{ctx.get('business_phone','')}</strong>.</p>
  <p style="margin:10px 0 0;"><a href="{ctx.get('business_website','#')}"
     style="color:#7c3aed;">{ctx.get('business_website','')}</a></p>
</td></tr></table></td></tr></table></body></html>"""
    )


_DEFAULT_TEMPLATES = {
    "booking_created":        _default_html_booking_created,
    "booking_confirmed":      _default_html_booking_confirmed,
    "booking_cancelled":      _default_html_booking_cancelled,
    "booking_status_changed": _default_html_booking_status_changed,
    "booking_followup":       _default_html_booking_followup,
    "admin_new_lead":         _default_html_admin_new_lead,
    "customer_birthday":      _default_html_customer_birthday,
}


def default_confirmation_html(ctx: Dict[str, str]) -> str:
    """Legacy alias used by old call sites."""
    return _default_html_booking_confirmed(ctx)


# ── Core send logic ───────────────────────────────────────────────────────────

def _get_admin_email(settings) -> Optional[str]:
    """Return the first admin notification email, or business_email as fallback."""
    raw = (getattr(settings, "notification_emails", "") or "").strip()
    if raw:
        return raw.split(",")[0].strip()
    return (getattr(settings, "business_email", "") or "").strip() or None


def _get_from_addr(settings) -> str:
    addr = (getattr(settings, "resend_from_confirmations", "") or "").strip()
    if not addr:
        addr = (getattr(settings, "email_from", "") or "").strip()
    return addr or "onboarding@resend.dev"


def _get_bcc(settings) -> Optional[List[str]]:
    raw = (getattr(settings, "resend_bcc_booking", "") or "").strip()
    lst = [e.strip() for e in raw.split(",") if e.strip()]
    return lst if lst else None


def _render_and_send(trigger: str, to_addr: str, ctx: Dict[str, str],
                     subject_prefix: str = "") -> Dict[str, Any]:
    """Render subject+HTML for trigger and send via Resend. Returns {sent, reason}."""
    out: Dict[str, Any] = {"sent": False, "reason": ""}
    settings = get_settings()
    api_key = (getattr(settings, "resend_api_key", "") or "").strip()
    if not api_key:
        out["reason"] = "no_resend_key"
        return out

    cfg = get_email_workflow(trigger)
    raw_subject = (cfg.get("subject") or "").strip()
    if not raw_subject:
        raw_subject = (TRIGGER_META.get(trigger) or {}).get("default_subject", "Mensaje de HotBoat")
    subject = subject_prefix + _apply_template(raw_subject, ctx)

    raw_html = (cfg.get("body_html") or "").strip()
    if raw_html:
        html = _apply_template(raw_html, ctx)
    else:
        builder = _DEFAULT_TEMPLATES.get(trigger, _default_html_booking_confirmed)
        html = builder(ctx)

    try:
        send_booking_html(
            to=to_addr,
            subject=subject,
            html=html,
            from_address=_get_from_addr(settings),
            api_key=api_key,
            bcc=_get_bcc(settings),
        )
        out["sent"] = True
        out["reason"] = "ok"
    except Exception as e:
        logger.exception("Email trigger=%s to=%s failed: %s", trigger, to_addr, e)
        out["reason"] = f"send_error:{e}"
    return out


def _can_send(trigger: str) -> bool:
    cfg = get_email_workflow(trigger)
    return bool(cfg.get("enabled"))


# ── Public trigger functions ──────────────────────────────────────────────────

def send_email_for_trigger(trigger: str, booking_ref: str,
                            extra_ctx: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """
    Generic: fetch booking by ref, build context, send email for trigger.
    - admin_new_lead → sends to admin email (not customer)
    - booking_confirmed → idempotent via confirmation_email_sent_at
    """
    out: Dict[str, Any] = {"sent": False, "reason": ""}
    if not _can_send(trigger):
        out["reason"] = "disabled"
        return out

    booking = get_booking_by_ref(booking_ref)
    if not booking:
        out["reason"] = "not_found"
        return out

    if trigger == "booking_confirmed":
        if str(booking.get("status") or "") != "confirmed":
            out["reason"] = "not_confirmed"
            return out
        if booking.get("confirmation_email_sent_at"):
            out["reason"] = "already_sent"
            return out

    # Determine recipient: admin triggers go to the operator, not the customer
    is_admin_trigger = (TRIGGER_META.get(trigger) or {}).get("recipient") == "admin"
    settings = get_settings()
    if is_admin_trigger:
        to_addr = _get_admin_email(settings) or ""
        if not to_addr:
            out["reason"] = "no_admin_email"
            return out
    else:
        to_addr = (booking.get("customer_email") or "").strip()
        if not to_addr:
            out["reason"] = "no_customer_email"
            return out

    ctx = _booking_ctx(booking, extra_ctx)
    out = _render_and_send(trigger, to_addr, ctx)

    if out.get("sent") and trigger == "booking_confirmed":
        mark_confirmation_email_sent(booking_ref)

    return out


def send_email_for_trigger_with_data(trigger: str, to_addr: str,
                                      data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Send trigger email when you already have the data (no DB lookup).
    Used by admin update_reserva hook (all_appointments flow).
    """
    if not _can_send(trigger):
        return {"sent": False, "reason": "disabled"}
    if not to_addr:
        return {"sent": False, "reason": "no_customer_email"}

    s = get_settings()
    bt = str(data.get("booking_time") or data.get("hora") or "")
    if len(bt) >= 5:
        bt = bt[:5]
    ctx: Dict[str, str] = {
        "booking_ref":      str(data.get("booking_ref") or data.get("source_id") or ""),
        "customer_name":    str(data.get("customer_name") or data.get("nombre_cliente") or "Cliente"),
        "customer_email":   to_addr,
        "customer_phone":   str(data.get("customer_phone") or data.get("telefono") or ""),
        "booking_date":     str(data.get("booking_date") or data.get("fecha") or ""),
        "booking_time":     bt,
        "num_people":       str(data.get("num_people") or data.get("num_personas") or ""),
        "total_price":      str(data.get("total_price") or data.get("ingreso_total") or ""),
        "total_price_fmt":  _fmt_clp(data.get("total_price") or data.get("ingreso_total")),
        "subtotal_fmt":     _fmt_clp(data.get("subtotal") or data.get("ingreso_reserva")),
        "extras_total_fmt": _fmt_clp(data.get("extras_total") or data.get("ingreso_extras")),
        "status":           str(data.get("status") or ""),
        "business_name":    getattr(s, "business_name", "Hot Boat"),
        "business_phone":   getattr(s, "business_phone", ""),
        "business_email":   getattr(s, "business_email", ""),
        "business_website": getattr(s, "business_website", ""),
    }
    return _render_and_send(trigger, to_addr, ctx)


def get_default_html_for_trigger(trigger: str) -> str:
    """Return the built-in HTML template for a trigger rendered with sample data."""
    ctx = _sample_ctx("preview@hotboat.cl")
    builder = _DEFAULT_TEMPLATES.get(trigger, _default_html_booking_confirmed)
    return builder(ctx)


def send_test_email_for_trigger(trigger: str, to_addr: str) -> Dict[str, Any]:
    """Send test email for any trigger (uses sample data, does not touch DB)."""
    if trigger not in TRIGGER_META:
        return {"sent": False, "reason": "unknown_trigger"}
    settings = get_settings()
    # For admin triggers, if no to_addr given use admin email
    is_admin_trigger = (TRIGGER_META.get(trigger) or {}).get("recipient") == "admin"
    effective_to = to_addr.strip() if to_addr else ""
    if not effective_to:
        if is_admin_trigger:
            effective_to = _get_admin_email(settings) or ""
        if not effective_to:
            return {"sent": False, "reason": "no_to"}
    ctx = _sample_ctx(effective_to)
    return _render_and_send(trigger, effective_to, ctx, subject_prefix="[Prueba] ")


# ── Daily follow-up sweep ────────────────────────────────────────────────────

def run_followup_email_sweep() -> dict:
    """
    Run once per day: find confirmed bookings where booking_date = today - days_after
    that haven't received the follow-up email yet, and send it.
    Returns {"checked": N, "sent": N, "errors": [...]}
    """
    out = {"checked": 0, "sent": 0, "errors": []}
    cfg = get_email_workflow("booking_followup")
    if not cfg.get("enabled"):
        out["reason"] = "disabled"
        return out

    settings = get_settings()
    if not (getattr(settings, "resend_api_key", "") or "").strip():
        out["reason"] = "no_resend_key"
        return out

    days_after = int(cfg.get("days_after") or 5)
    bookings = get_bookings_for_followup(days_after)
    out["checked"] = len(bookings)

    for b in bookings:
        to_addr = (b.get("customer_email") or "").strip()
        if not to_addr:
            continue
        ctx = _booking_ctx(b)
        result = _render_and_send("booking_followup", to_addr, ctx)
        if result.get("sent"):
            mark_followup_email_sent(b["booking_ref"])
            out["sent"] += 1
        else:
            out["errors"].append({"ref": b["booking_ref"], "reason": result.get("reason")})

    logger.info("Followup sweep: days_after=%s checked=%s sent=%s", days_after, out["checked"], out["sent"])
    return out


# ── Birthday sweep ───────────────────────────────────────────────────────────

def run_birthday_email_sweep() -> dict:
    """Run once per day: find customers whose birthday is today and send them the email."""
    out = {"checked": 0, "sent": 0, "errors": []}
    cfg = get_email_workflow("customer_birthday")
    if not cfg.get("enabled"):
        out["reason"] = "disabled"
        return out

    settings = get_settings()
    if not (getattr(settings, "resend_api_key", "") or "").strip():
        out["reason"] = "no_resend_key"
        return out

    customers = get_customers_for_birthday_email()
    out["checked"] = len(customers)

    for c in customers:
        to_addr = (c.get("customer_email") or "").strip()
        if not to_addr:
            continue
        ctx = {
            "booking_ref":      str(c.get("booking_ref") or ""),
            "customer_name":    str(c.get("customer_name") or "Cliente"),
            "customer_email":   to_addr,
            "customer_phone":   str(c.get("customer_phone") or ""),
            "booking_date":     str(c.get("booking_date") or ""),
            "booking_time":     str(c.get("booking_time") or "")[:5],
            "num_people":       str(c.get("num_people") or ""),
            "total_price":      str(c.get("total_price") or ""),
            "total_price_fmt":  _fmt_clp(c.get("total_price")),
            "subtotal_fmt":     _fmt_clp(c.get("subtotal")),
            "extras_total_fmt": _fmt_clp(c.get("extras_total")),
            "status":           "confirmed",
            **{k: getattr(get_settings(), k, "") for k in
               ("business_name", "business_phone", "business_email", "business_website")},
        }
        result = _render_and_send("customer_birthday", to_addr, ctx)
        if result.get("sent"):
            mark_birthday_email_sent(to_addr)
            out["sent"] += 1
        else:
            out["errors"].append({"email": to_addr, "reason": result.get("reason")})

    logger.info("Birthday sweep: checked=%s sent=%s", out["checked"], out["sent"])
    return out


# ── Legacy aliases (backwards compat) ─────────────────────────────────────────

def try_send_booking_confirmation_after_payment(booking_ref: str) -> Dict[str, Any]:
    return send_email_for_trigger("booking_confirmed", booking_ref)


def send_test_booking_email(to_address: str) -> Dict[str, Any]:
    return send_test_email_for_trigger("booking_confirmed", to_address)
