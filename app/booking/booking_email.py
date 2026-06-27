"""Booking email workflows — send transactional emails via Resend for each trigger."""
import logging
import re
from typing import Any, Dict, List, Optional

from app.config import get_settings
from app.booking.db import (
    get_booking_by_ref, mark_confirmation_email_sent,
    get_bookings_for_followup, mark_followup_email_sent,
    mark_followup_sent_after_manual_send,
    get_customers_for_birthday_email, mark_birthday_email_sent,
    get_bookings_pending_payment_email, mark_pending_email_sent,
)
from app.booking.operator_settings import get_email_workflow, TRIGGER_META
from app.email.resend_booking import send_booking_html

logger = logging.getLogger(__name__)

_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def _extras_rows_html(extras_raw, border_color: str = "#e2e8f0") -> str:
    """Parse the extras field (list / dict / JSON string) → HTML <tr> rows for
    admin email tables. ALWAYS returns at least one row ("Sin extras" when empty)
    so the operator can always see the extras status in lead/pending emails."""
    import json as _json
    items = extras_raw
    if isinstance(items, str):
        try:
            items = _json.loads(items)
        except Exception:
            items = []
    if isinstance(items, dict) and isinstance(items.get("extras"), list):
        items = items["extras"]
    if not isinstance(items, list):
        items = []

    def _cell(left: str, right: str) -> str:
        return (
            f"<tr>"
            f"<td style='padding:10px 16px;border-top:1px solid {border_color}'>"
            f"<strong>{left}</strong></td>"
            f"<td style='padding:10px 16px;border-top:1px solid {border_color};text-align:right'>"
            f"{right}</td></tr>"
        )

    valid = [e for e in items if isinstance(e, dict)]
    if not valid:
        return _cell("Extras", "Sin extras")

    rows = ""
    for i, e in enumerate(valid):
        name  = str(e.get("name") or "Extra")
        qty   = int(e.get("quantity") or e.get("qty") or 1)
        price = float(e.get("price") or e.get("unit_price") or 0)
        label = name + (f" ×{qty}" if qty > 1 else "")
        price_str = f"  {_fmt_clp(price * qty)}" if price else ""
        rows += _cell("Extras" if i == 0 else "", f"{label}{price_str}")
    return rows


def _extras_card_rows_html(extras_raw) -> str:
    """Extras as dark-card rows (matching _hotboat_email_card details) for the
    customer confirmation/created emails. Returns '' when there are no extras."""
    import json as _json
    items = extras_raw
    if isinstance(items, str):
        try:
            items = _json.loads(items)
        except Exception:
            items = []
    if isinstance(items, dict) and isinstance(items.get("extras"), list):
        items = items["extras"]
    if not isinstance(items, list):
        items = []
    valid = [e for e in items if isinstance(e, dict)]
    if not valid:
        return ""
    rows = ""
    for e in valid:
        name  = str(e.get("name") or "Extra")
        qty   = int(e.get("quantity") or e.get("qty") or 1)
        price = float(e.get("price") or e.get("unit_price") or 0)
        label = name + (f" ×{qty}" if qty > 1 else "")
        amount = _fmt_clp(price * qty) if price else ""
        rows += (
            '<tr><td style="padding:14px 20px;border-bottom:1px solid #1a2e28;">'
            '<table width="100%" cellspacing="0" cellpadding="0"><tr>'
            f'<td style="color:#64748b;font-size:11px;text-transform:uppercase;'
            f'letter-spacing:1.2px;font-weight:600;">{label}</td>'
            f'<td align="right" style="color:#e2e8f0;font-size:14px;font-weight:600;">{amount}</td>'
            '</tr></table></td></tr>'
        )
    return rows

# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_clp(n: Any) -> str:
    try:
        v = int(float(n or 0))
    except (TypeError, ValueError):
        v = 0
    return f"${v:,}".replace(",", ".")  # e.g. $179.970


def _apply_template(template: str, ctx: Dict[str, str]) -> str:
    return _PLACEHOLDER.sub(lambda m: ctx.get(m.group(1), ""), template)


def _get_base_url() -> str:
    """Return the public base URL of this deployment (no trailing slash)."""
    import os as _os
    domain = _os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
    if domain:
        return f"https://{domain}"
    s = get_settings()
    website = (getattr(s, "business_website", "") or "").rstrip("/")
    return website or ""


def _booking_ctx(booking: dict, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    s = get_settings()
    bt = str(booking.get("booking_time") or "")
    if len(bt) >= 5:
        bt = bt[:5]
    booking_ref = str(booking.get("booking_ref") or "")
    base_url = _get_base_url()
    firma_url = f"{base_url}/firma/{booking_ref}" if booking_ref and base_url else ""
    tabla_url = f"{base_url}/tabla/{booking_ref}" if booking_ref and base_url else ""
    lang = str(booking.get("customer_language") or "es").strip().lower()
    if lang not in ("es", "en", "pt"):
        lang = "es"
    ctx = {
        "booking_ref":        booking_ref,
        "customer_name":      str(booking.get("customer_name") or "").strip() or "Cliente",
        "customer_email":     str(booking.get("customer_email") or "").strip(),
        "customer_phone":     str(booking.get("customer_phone") or "").strip(),
        "booking_date":       str(booking.get("booking_date") or ""),
        "booking_time":       bt,
        "num_people":         str(booking.get("num_people") or ""),
        "total_price":        str(booking.get("total_price") or ""),
        "total_price_fmt":    _fmt_clp(booking.get("total_price")),
        "deposit_fmt":        _fmt_clp(round(float(booking.get("total_price") or 0) * 0.5)),
        "subtotal_fmt":       _fmt_clp(booking.get("subtotal")),
        "extras_total_fmt":   _fmt_clp(booking.get("extras_total")),
        "status":             str(booking.get("status") or ""),
        "business_name":      getattr(s, "business_name", "Hot Boat"),
        "business_phone":     getattr(s, "business_phone", ""),
        "business_email":     getattr(s, "business_email", ""),
        "business_website":   getattr(s, "business_website", ""),
        "firma_url":          firma_url,
        "tabla_url":          tabla_url,
        "customer_language":  lang,
        "utm_source":   str(booking.get("utm_source") or ""),
        "utm_medium":   str(booking.get("utm_medium") or ""),
        "utm_campaign": str(booking.get("utm_campaign") or ""),
        "utm_content":  str(booking.get("utm_content") or ""),
        "parametro_url": str(booking.get("parametro_url") or ""),
    }
    ctx["ad_source_label"] = ctx["utm_campaign"] or ctx["parametro_url"] or ctx["utm_source"]
    _extras_raw = booking.get("extras") or []
    ctx["extras_html"]         = _extras_rows_html(_extras_raw, "#e2e8f0")   # light border (new_lead)
    ctx["extras_html_pending"] = _extras_rows_html(_extras_raw, "#fde68a")  # yellow border (pending)
    ctx["extras_card_rows"]    = _extras_card_rows_html(_extras_raw)         # dark card (customer confirmed/created)
    if extra:
        ctx.update(extra)
    return ctx


def _sample_ctx(to_addr: str) -> Dict[str, str]:
    s = get_settings()
    base_url = _get_base_url()
    demo_ref = "HB-2026-DEMO1"
    return {
        "booking_ref":      demo_ref,
        "customer_name":    "Cliente de prueba",
        "customer_email":   to_addr,
        "customer_phone":   "+56 9 0000 0000",
        "booking_date":     "2026-04-15",
        "booking_time":     "10:00",
        "num_people":       "4",
        "total_price":      "200000",
        "total_price_fmt":  _fmt_clp(200000),
        "deposit_fmt":      _fmt_clp(100000),
        "subtotal_fmt":     _fmt_clp(180000),
        "extras_total_fmt": _fmt_clp(20000),
        "status":           "confirmed",
        "business_name":    getattr(s, "business_name", "Hot Boat"),
        "business_phone":   getattr(s, "business_phone", ""),
        "business_email":   getattr(s, "business_email", ""),
        "business_website": getattr(s, "business_website", ""),
        "firma_url":         f"{base_url}/firma/{demo_ref}" if base_url else "",
        "tabla_url":         f"{base_url}/tabla/{demo_ref}" if base_url else "",
        "customer_language": "es",
    }


# ── i18n strings ─────────────────────────────────────────────────────────────

_I18N: Dict[str, Dict[str, str]] = {
    "es": {
        "label_ref":    "Referencia",
        "label_date":   "📅 \u00a0Fecha",
        "label_time":   "⏰ \u00a0Hora",
        "label_people": "👥 \u00a0Personas",
        "label_paid":           "✅ \u00a0Pagado",
        "label_deposit_due":    "💳 \u00a0Depósito a pagar (50%)",
        "label_total":  "💰 \u00a0Total",
        "hrs":          "hrs",
        "footer_questions": "¿Tienes preguntas? Escríbenos por WhatsApp",
        "footer_note":  "Recibiste este correo porque realizaste una reserva en Hot Boat.<br>Puedes responder este email si tienes alguna consulta.",
        "footer_contact": "Consultas: WhatsApp <strong>{phone}</strong> o responde este correo.",
        # booking_created
        "created_title":         "¡Reserva recibida!",
        "created_subtitle":      "Hola <strong style=\"color:#e2e8f0;\">{name}</strong>, recibimos tu solicitud.<br>Completa el pago para confirmar tu lugar en el agua.",
        "created_payment_title": "💳 Se pide el 50% del total para reservar.",
        "created_payment_body":  "El resto se paga después de vivir la Experiencia HotBoat,<br>con efectivo, tarjeta o transferencia.",
        "tc_title": "✍️ Todos los mayores de 18 años deben firmar los Términos y Condiciones",
        "tc_body":  "Antes de subir al HotBoat, cada integrante adulto del grupo debe aceptar<br>los T&amp;C a través del siguiente link:",
        # booking_confirmed
        "confirmed_title":         "¡Reserva confirmada! ✅",
        "confirmed_subtitle":      "Hola <strong style=\"color:#e2e8f0;\">{name}</strong>, tu pago fue recibido correctamente.<br>¡Todo listo para tu experiencia HotBoat!",
        "confirmed_payment_title": "✅ Tu pago fue confirmado.",
        "confirmed_payment_body":  "Tu reserva está asegurada. ¡Nos vemos en el agua!<br>El resto del pago se hace después de la experiencia.",
        # CTAs
        "cta_summary": "📋 Resumen de reserva",
        "cta_sign_tc": "✍️ Firmar T&C",
        "cta_video":   "🎬 Video instructivo",
        "cta_menu":    "🍹 Tablas y bebestibles",
        # booking_cancelled
        "cancelled_title": "Reserva cancelada",
        "cancelled_hello": "Hola <strong>{name}</strong>,",
        "cancelled_body":  "Te informamos que tu reserva <strong>{ref}</strong> ha sido <strong>cancelada</strong>. Si tienes dudas o quieres reagendar, contáctanos.",
        # booking_status_changed
        "status_title": "Actualización de reserva",
        "status_hello": "Hola <strong>{name}</strong>,",
        "status_body":  "El estado de tu reserva <strong>{ref}</strong> ha sido actualizado a <strong>{status}</strong>.",
        # booking_followup
        "followup_title":  "¡Gracias por navegar con nosotros!",
        "followup_hello":  "Hola <strong>{name}</strong>,",
        "followup_body1":  "¡Fue un placer tenerte a bordo! Esperamos que hayas disfrutado tu experiencia en el agua el día de hoy 🌊",
        "followup_body2":  "Tu opinión es muy importante para nosotros. Te pedimos dos pequeños favores:",
        "followup_review_label": "⭐ Déjanos una reseña en TripAdvisor",
        "followup_survey_label": "📋 Completa nuestra encuesta de satisfacción",
        # customer_birthday
        "birthday_title": "¡Feliz cumpleaños! 🎂",
        "birthday_hello": "Hola <strong>{name}</strong>,",
        "birthday_body1": "El equipo de <strong>{biz}</strong> te desea un maravilloso cumpleaños. 🎉",
        "birthday_body2": "¡Gracias por ser parte de nuestra comunidad! Esperamos verte de nuevo pronto en el agua.",
        "birthday_cta":   "¿Listo para un nuevo paseo? Escríbenos al <strong>{phone}</strong>.",
    },
    "en": {
        "label_ref":    "Reference",
        "label_date":   "📅 \u00a0Date",
        "label_time":   "⏰ \u00a0Time",
        "label_people": "👥 \u00a0People",
        "label_paid":           "✅ \u00a0Paid (50%)",
        "label_deposit_due":    "💳 \u00a0Deposit due (50%)",
        "label_total":  "💰 \u00a0Total",
        "hrs":          "h",
        "footer_questions": "Any questions? Message us on WhatsApp",
        "footer_note":  "You received this email because you made a booking with Hot Boat.<br>You can reply to this email if you have any questions.",
        "footer_contact": "Questions? WhatsApp <strong>{phone}</strong> or reply to this email.",
        "created_title":         "Booking received!",
        "created_subtitle":      "Hi <strong style=\"color:#e2e8f0;\">{name}</strong>, we've received your request.<br>Complete the payment to secure your spot on the water.",
        "created_payment_title": "💳 A 50% deposit is required to confirm your booking.",
        "created_payment_body":  "The balance is due after your HotBoat experience,<br>payable by cash, card or bank transfer.",
        "tc_title": "✍️ All adults (18+) must sign the Terms &amp; Conditions",
        "tc_body":  "Before boarding the HotBoat, every adult in your group must accept<br>the T&amp;C through the following link:",
        "confirmed_title":         "Booking confirmed! ✅",
        "confirmed_subtitle":      "Hi <strong style=\"color:#e2e8f0;\">{name}</strong>, your payment was received.<br>All set for your HotBoat experience!",
        "confirmed_payment_title": "✅ Payment confirmed.",
        "confirmed_payment_body":  "Your booking is secured. See you on the water!<br>The balance is due after the experience.",
        "cta_summary": "📋 Booking summary",
        "cta_sign_tc": "✍️ Sign T&C",
        "cta_video":   "🎬 Instructional video",
        "cta_menu":    "🍹 Food &amp; drinks menu",
        "cancelled_title": "Booking cancelled",
        "cancelled_hello": "Hi <strong>{name}</strong>,",
        "cancelled_body":  "We're letting you know that your booking <strong>{ref}</strong> has been <strong>cancelled</strong>. If you have questions or want to reschedule, please contact us.",
        "status_title": "Booking update",
        "status_hello": "Hi <strong>{name}</strong>,",
        "status_body":  "The status of your booking <strong>{ref}</strong> has been updated to <strong>{status}</strong>.",
        "followup_title":  "Thanks for sailing with us!",
        "followup_hello":  "Hi <strong>{name}</strong>,",
        "followup_body1":  "It was a pleasure having you on board! We hope you enjoyed your experience on the water today 🌊",
        "followup_body2":  "Your feedback means a lot to us. We'd love to ask two small favours:",
        "followup_review_label": "⭐ Leave us a review on TripAdvisor",
        "followup_survey_label": "📋 Fill out our satisfaction survey",
        "birthday_title": "Happy Birthday! 🎂",
        "birthday_hello": "Hi <strong>{name}</strong>,",
        "birthday_body1": "The <strong>{biz}</strong> team wishes you a wonderful birthday. 🎉",
        "birthday_body2": "Thank you for being part of our community! We hope to see you back on the water soon.",
        "birthday_cta":   "Ready for another trip? Message us at <strong>{phone}</strong>.",
    },
    "pt": {
        "label_ref":    "Referência",
        "label_date":   "📅 \u00a0Data",
        "label_time":   "⏰ \u00a0Hora",
        "label_people": "👥 \u00a0Pessoas",
        "label_paid":           "✅ \u00a0Pago (50%)",
        "label_deposit_due":    "💳 \u00a0Sinal de reserva (50%)",
        "label_total":  "💰 \u00a0Total",
        "hrs":          "h",
        "footer_questions": "Tem dúvidas? Fale conosco pelo WhatsApp",
        "footer_note":  "Você recebeu este e-mail porque fez uma reserva no Hot Boat.<br>Pode responder este e-mail se tiver alguma dúvida.",
        "footer_contact": "Dúvidas? WhatsApp <strong>{phone}</strong> ou responda este e-mail.",
        "created_title":         "Reserva recebida!",
        "created_subtitle":      "Olá <strong style=\"color:#e2e8f0;\">{name}</strong>, recebemos seu pedido.<br>Conclua o pagamento para confirmar seu lugar na água.",
        "created_payment_title": "💳 É necessário 50% do total para confirmar a reserva.",
        "created_payment_body":  "O restante é pago após a Experiência HotBoat,<br>em dinheiro, cartão ou transferência bancária.",
        "tc_title": "✍️ Todos os adultos (18+) devem assinar os Termos e Condições",
        "tc_body":  "Antes de embarcar no HotBoat, cada adulto do grupo deve aceitar<br>os T&amp;C pelo link abaixo:",
        "confirmed_title":         "Reserva confirmada! ✅",
        "confirmed_subtitle":      "Olá <strong style=\"color:#e2e8f0;\">{name}</strong>, seu pagamento foi recebido.<br>Tudo pronto para sua experiência HotBoat!",
        "confirmed_payment_title": "✅ Pagamento confirmado.",
        "confirmed_payment_body":  "Sua reserva está garantida. Até logo na água!<br>O saldo restante é pago após a experiência.",
        "cta_summary": "📋 Resumo da reserva",
        "cta_sign_tc": "✍️ Assinar T&C",
        "cta_video":   "🎬 Vídeo instrucional",
        "cta_menu":    "🍹 Cardápio e bebidas",
        "cancelled_title": "Reserva cancelada",
        "cancelled_hello": "Olá <strong>{name}</strong>,",
        "cancelled_body":  "Informamos que sua reserva <strong>{ref}</strong> foi <strong>cancelada</strong>. Se tiver dúvidas ou quiser remarcar, entre em contato.",
        "status_title": "Atualização da reserva",
        "status_hello": "Olá <strong>{name}</strong>,",
        "status_body":  "O status da sua reserva <strong>{ref}</strong> foi atualizado para <strong>{status}</strong>.",
        "followup_title":  "Obrigado por navegar conosco!",
        "followup_hello":  "Olá <strong>{name}</strong>,",
        "followup_body1":  "Foi um prazer tê-lo a bordo! Esperamos que tenha aproveitado sua experiência na água hoje 🌊",
        "followup_body2":  "Sua opinião é muito importante para nós. Gostaríamos de pedir dois pequenos favores:",
        "followup_review_label": "⭐ Deixe uma avaliação no TripAdvisor",
        "followup_survey_label": "📋 Preencha nossa pesquisa de satisfação",
        "birthday_title": "Feliz Aniversário! 🎂",
        "birthday_hello": "Olá <strong>{name}</strong>,",
        "birthday_body1": "A equipe da <strong>{biz}</strong> deseja a você um aniversário maravilhoso. 🎉",
        "birthday_body2": "Obrigado por fazer parte da nossa comunidade! Esperamos vê-lo novamente na água em breve.",
        "birthday_cta":   "Pronto para uma nova aventura? Fale conosco pelo <strong>{phone}</strong>.",
    },
}


def _t(lang: str, key: str, **fmt) -> str:
    """Return translated string for lang/key, falling back to 'es'.
    Optional keyword args are formatted into the string."""
    strings = _I18N.get(lang) or _I18N["es"]
    text = strings.get(key) or _I18N["es"].get(key, "")
    if fmt:
        try:
            text = text.format(**fmt)
        except (KeyError, IndexError):
            pass
    return text


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
    lang = ctx.get("customer_language", "es")
    rows = [
        (_t(lang, "label_ref"),    ctx.get("booking_ref", "")),
        (_t(lang, "label_date"),   ctx.get("booking_date", "")),
        (_t(lang, "label_time"),   ctx.get("booking_time", "")),
        (_t(lang, "label_people"), ctx.get("num_people", "")),
        (_t(lang, "label_total"),  ctx.get("total_price_fmt", "")),
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
    lang = ctx.get("customer_language", "es")
    contact = _t(lang, "footer_contact", phone=ctx.get("business_phone", ""))
    return f"""<tr><td style="padding:18px 26px 26px;font-size:13px;color:#64748b;line-height:1.6;">
  <p style="margin:0;">{contact}</p>
  <p style="margin:10px 0 0;"><a href="{ctx.get('business_website','#')}"
     style="color:#235e58;">{ctx.get('business_website','')}</a></p>
</td></tr></table></td></tr></table></body></html>"""


def _hotboat_email_card(
    ctx: Dict[str, str],
    hero_title: str,
    hero_subtitle: str,
    accent_bar: str,
    extra_body: str,
    cta_rows: str,
    *,
    deposit_row_i18n_key: str = "label_paid",
    extra_detail_rows_html: str = "",
    after_total_rows_html: str = "",
) -> str:
    """Shared dark-card layout used by booking_created and booking_confirmed."""
    phone   = ctx.get("business_phone", "")
    website = ctx.get("business_website", "#")
    biz     = ctx.get("business_name", "HotBoat")
    wa_num  = phone.replace(" ", "").replace("+", "")
    # Logo: EMAIL_LOGO_URL env var > auto-detect Railway domain > text fallback
    import os as _os
    logo_url = _os.environ.get("EMAIL_LOGO_URL", "").strip()
    if not logo_url:
        railway_domain = _os.environ.get("RAILWAY_PUBLIC_DOMAIN", "").strip()
        if railway_domain:
            logo_url = f"https://{railway_domain}/static/Logo%20sin%20Fondo%20sin%20Chile%20Blanco.png"

    lang   = ctx.get("customer_language", "es")
    ref    = ctx.get("booking_ref", "")
    date   = ctx.get("booking_date", "")
    time_  = ctx.get("booking_time", "")
    people = ctx.get("num_people", "")
    total   = ctx.get("total_price_fmt", "")
    deposit = ctx.get("deposit_fmt", "")

    return f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{hero_title} — {biz}</title></head>
<body style="margin:0;padding:0;background:#07120f;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">

<table role="presentation" width="100%" cellspacing="0" cellpadding="0" bgcolor="#07120f">
<tr><td align="center" style="padding:36px 16px 48px;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:560px;width:100%;">

  <!-- Main card -->
  <tr><td style="background:#102220;border-radius:20px;overflow:hidden;box-shadow:0 24px 64px rgba(0,0,0,.55);">

    <!-- Accent bar -->
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr>{accent_bar}</tr>
    </table>

    <!-- Logo + Hero -->
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr><td align="center" style="padding:36px 32px 24px;">
      {'<img src="' + logo_url + '" alt="' + biz + '" width="160" style="display:block;margin:0 auto 20px;max-width:160px;height:auto;">' if logo_url else '<div style="color:#e8b86d;font-size:13px;font-weight:700;letter-spacing:2px;margin-bottom:20px;">' + biz + '</div>'}
      <h1 style="margin:0 0 10px;color:#f8fafc;font-size:26px;font-weight:800;
                 letter-spacing:-0.5px;line-height:1.2;">{hero_title}</h1>
      <p style="margin:0;color:#94a3b8;font-size:15px;line-height:1.55;">{hero_subtitle}</p>
    </td></tr>
    </table>

    <!-- Booking details -->
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr><td style="padding:0 28px 24px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="background:#07120f;border-radius:14px;border:1px solid #20352e;overflow:hidden;">

        <tr><td style="padding:14px 20px;border-bottom:1px solid #1a2e28;">
          <table width="100%" cellspacing="0" cellpadding="0"><tr>
            <td style="color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:1.2px;font-weight:600;">{_t(lang,"label_ref")}</td>
            <td align="right" style="color:#e8b86d;font-size:13px;font-weight:700;font-family:'Courier New',monospace;">{ref}</td>
          </tr></table>
        </td></tr>

        <tr><td style="padding:14px 20px;border-bottom:1px solid #1a2e28;">
          <table width="100%" cellspacing="0" cellpadding="0"><tr>
            <td style="color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:1.2px;font-weight:600;">{_t(lang,"label_date")}</td>
            <td align="right" style="color:#e2e8f0;font-size:14px;font-weight:600;">{date}</td>
          </tr></table>
        </td></tr>

        <tr><td style="padding:14px 20px;border-bottom:1px solid #1a2e28;">
          <table width="100%" cellspacing="0" cellpadding="0"><tr>
            <td style="color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:1.2px;font-weight:600;">{_t(lang,"label_time")}</td>
            <td align="right" style="color:#e2e8f0;font-size:14px;font-weight:600;">{time_} {_t(lang,"hrs")}</td>
          </tr></table>
        </td></tr>

        <tr><td style="padding:14px 20px;border-bottom:1px solid #1a2e28;">
          <table width="100%" cellspacing="0" cellpadding="0"><tr>
            <td style="color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:1.2px;font-weight:600;">{_t(lang,"label_people")}</td>
            <td align="right" style="color:#e2e8f0;font-size:14px;font-weight:600;">{people}</td>
          </tr></table>
        </td></tr>

        {extra_detail_rows_html}

        <tr><td style="padding:14px 20px;border-bottom:1px solid #1a2e28;">
          <table width="100%" cellspacing="0" cellpadding="0"><tr>
            <td style="color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:1.2px;font-weight:600;">{_t(lang, deposit_row_i18n_key)}</td>
            <td align="right" style="color:#e8b86d;font-size:14px;font-weight:700;">{deposit}</td>
          </tr></table>
        </td></tr>

        <tr><td style="padding:16px 20px;background:rgba(44,122,114,.06);">
          <table width="100%" cellspacing="0" cellpadding="0"><tr>
            <td style="color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:1.2px;font-weight:600;">{_t(lang,"label_total")}</td>
            <td align="right" style="color:#34a394;font-size:18px;font-weight:800;">{total}</td>
          </tr></table>
        </td></tr>

        {after_total_rows_html}

      </table>
    </td></tr>
    </table>

    {extra_body}

    <!-- CTA Buttons -->
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr><td style="padding:0 28px 32px;">{cta_rows}</td></tr>
    </table>

    <!-- Divider -->
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr><td style="padding:0 28px;"><hr style="border:none;border-top:1px solid #20352e;margin:0;"></td></tr>
    </table>

    <!-- Footer contact -->
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr><td align="center" style="padding:22px 28px 30px;">
      <p style="margin:0 0 6px;color:#94a3b8;font-size:13px;">{_t(lang,"footer_questions")}</p>
      <a href="https://wa.me/{wa_num}" style="color:#e8b86d;font-size:15px;font-weight:700;text-decoration:none;">{phone}</a>
    </td></tr>
    </table>

  </td></tr>

  <!-- Bottom note -->
  <tr><td align="center" style="padding-top:18px;">
    <p style="margin:0;color:#94a3b8;font-size:11px;line-height:1.7;">
      {_t(lang,"footer_note")}
    </p>
  </td></tr>

</table>
</td></tr>
</table>
</body>
</html>"""


def _cta_btn(label: str, url: str, solid: bool = True) -> str:
    if solid:
        style = ("display:block;text-align:center;background:#2c7a72;color:#ffffff;"
                 "text-decoration:none;padding:13px 10px;border-radius:11px;"
                 "font-size:13px;font-weight:700;letter-spacing:0.3px;"
                 "box-shadow:0 4px 14px rgba(44,122,114,.35);")
    else:
        style = ("display:block;text-align:center;background:rgba(44,122,114,.12);color:#5fb8ae;"
                 "text-decoration:none;padding:13px 10px;border-radius:11px;"
                 "font-size:13px;font-weight:700;letter-spacing:0.3px;"
                 "border:1px solid rgba(95,184,174,.35);")
    return f'<a href="{url}" style="{style}">{label}</a>'


def _default_html_booking_created(ctx: Dict[str, str]) -> str:
    lang      = ctx.get("customer_language", "es")
    name      = ctx.get("customer_name", "")
    website   = ctx.get("business_website", "#")
    firma_url = ctx.get("firma_url", "") or website
    tabla_url = ctx.get("tabla_url", "") or "https://hotboatchile.com/tablas/"

    accent = (
        '<td width="33%" height="4" bgcolor="#e8b86d" style="line-height:4px;font-size:0;">&nbsp;</td>'
        '<td width="34%" height="4" bgcolor="#2c7a72" style="line-height:4px;font-size:0;">&nbsp;</td>'
        '<td width="33%" height="4" bgcolor="#34a394" style="line-height:4px;font-size:0;">&nbsp;</td>'
    )

    payment_note = f"""
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr><td style="padding:0 28px 16px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="background:rgba(59,130,246,.08);border:1px solid rgba(59,130,246,.25);border-radius:12px;">
      <tr><td style="padding:15px 20px;">
        <p style="margin:0;color:#93c5fd;font-size:13px;line-height:1.65;">
          <strong>{_t(lang,"created_payment_title")}</strong><br>
          {_t(lang,"created_payment_body")}
        </p>
      </td></tr>
      </table>
    </td></tr>
    </table>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr><td style="padding:0 28px 24px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="background:rgba(251,191,36,.07);border:1px solid rgba(251,191,36,.3);border-radius:12px;">
      <tr><td style="padding:15px 20px;">
        <p style="margin:0 0 8px;color:#fcd34d;font-size:13px;font-weight:700;">
          {_t(lang,"tc_title")}
        </p>
        <p style="margin:0;color:#fde68a;font-size:12px;line-height:1.6;">
          {_t(lang,"tc_body")}
        </p>
        <p style="margin:10px 0 0;">
          <a href="{firma_url}" style="color:#fbbf24;font-weight:700;font-size:12px;word-break:break-all;">{firma_url}</a>
        </p>
      </td></tr>
      </table>
    </td></tr>
    </table>"""

    cta_rows = f"""
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:10px;">
    <tr>
      <td width="50%" style="padding-right:6px;">{_cta_btn(_t(lang,"cta_summary"), "https://srv1080-files.hstgr.io/2f0792bfa7cfcf2b/files/public_html/images/Resumen_reserva_espa%C3%B1ol.png", solid=True)}</td>
      <td width="50%" style="padding-left:6px;">{_cta_btn(_t(lang,"cta_sign_tc"), firma_url, solid=False)}</td>
    </tr>
    </table>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr>
      <td width="50%" style="padding-right:6px;">{_cta_btn(_t(lang,"cta_video"), "https://www.youtube.com/shorts/-9Y23l40oSQ?si=_mZrnTlw33qhf2bb", solid=False)}</td>
      <td width="50%" style="padding-left:6px;">{_cta_btn(_t(lang,"cta_menu"), tabla_url, solid=False)}</td>
    </tr>
    </table>"""

    return _hotboat_email_card(
        ctx,
        hero_title=_t(lang, "created_title"),
        hero_subtitle=_t(lang, "created_subtitle", name=name),
        accent_bar=accent,
        extra_body=payment_note,
        cta_rows=cta_rows,
        deposit_row_i18n_key="label_deposit_due",
        extra_detail_rows_html=ctx.get("extras_card_rows", ""),
    )


def _default_html_booking_confirmed(ctx: Dict[str, str]) -> str:
    lang      = ctx.get("customer_language", "es")
    name      = ctx.get("customer_name", "")
    website   = ctx.get("business_website", "#")
    firma_url = ctx.get("firma_url", "") or website
    tabla_url = ctx.get("tabla_url", "") or "https://hotboatchile.com/tablas/"

    accent = (
        '<td width="50%" height="4" bgcolor="#34a394" style="line-height:4px;font-size:0;">&nbsp;</td>'
        '<td width="50%" height="4" bgcolor="#e8b86d" style="line-height:4px;font-size:0;">&nbsp;</td>'
    )

    confirmed_note = f"""
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr><td style="padding:0 28px 16px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="background:rgba(44,122,114,.08);border:1px solid rgba(44,122,114,.3);border-radius:12px;">
      <tr><td style="padding:15px 20px;">
        <p style="margin:0;color:#8fd3c9;font-size:13px;line-height:1.65;">
          <strong>{_t(lang,"confirmed_payment_title")}</strong><br>
          {_t(lang,"confirmed_payment_body")}
        </p>
      </td></tr>
      </table>
    </td></tr>
    </table>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr><td style="padding:0 28px 24px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="background:rgba(251,191,36,.07);border:1px solid rgba(251,191,36,.3);border-radius:12px;">
      <tr><td style="padding:15px 20px;">
        <p style="margin:0 0 8px;color:#fcd34d;font-size:13px;font-weight:700;">
          {_t(lang,"tc_title")}
        </p>
        <p style="margin:0;color:#fde68a;font-size:12px;line-height:1.6;">
          {_t(lang,"tc_body")}
        </p>
        <p style="margin:10px 0 0;">
          <a href="{firma_url}" style="color:#fbbf24;font-weight:700;font-size:12px;word-break:break-all;">{firma_url}</a>
        </p>
      </td></tr>
      </table>
    </td></tr>
    </table>"""

    cta_rows = f"""
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:10px;">
    <tr>
      <td width="50%" style="padding-right:6px;">{_cta_btn(_t(lang,"cta_summary"), "https://srv1080-files.hstgr.io/2f0792bfa7cfcf2b/files/public_html/images/Resumen_reserva_espa%C3%B1ol.png", solid=True)}</td>
      <td width="50%" style="padding-left:6px;">{_cta_btn(_t(lang,"cta_sign_tc"), firma_url, solid=False)}</td>
    </tr>
    </table>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr>
      <td width="50%" style="padding-right:6px;">{_cta_btn(_t(lang,"cta_video"), "https://www.youtube.com/shorts/-9Y23l40oSQ?si=_mZrnTlw33qhf2bb", solid=False)}</td>
      <td width="50%" style="padding-left:6px;">{_cta_btn(_t(lang,"cta_menu"), tabla_url, solid=False)}</td>
    </tr>
    </table>"""

    return _hotboat_email_card(
        ctx,
        hero_title=_t(lang, "confirmed_title"),
        hero_subtitle=_t(lang, "confirmed_subtitle", name=name),
        accent_bar=accent,
        extra_body=confirmed_note,
        cta_rows=cta_rows,
        extra_detail_rows_html=ctx.get("extras_card_rows", ""),
    )


def _default_html_booking_created_OLD(ctx: Dict[str, str]) -> str:
    """Legacy — kept only if someone references it directly."""
    return _default_html_booking_created(ctx)




def _default_html_booking_cancelled(ctx: Dict[str, str]) -> str:
    lang = ctx.get("customer_language", "es")
    name = ctx.get("customer_name", "")
    ref  = ctx.get("booking_ref", "")
    return (
        _header(ctx, _t(lang, "cancelled_title"), "#7f1d1d")
        + f"""<tr><td style="padding:26px 26px 8px;color:#0f172a;font-size:15px;line-height:1.65;">
  <p style="margin:0 0 12px;">{_t(lang,"cancelled_hello",name=name)}</p>
  <p style="margin:0 0 12px;">{_t(lang,"cancelled_body",ref=ref)}</p>
</td></tr>
<tr><td style="padding:0 26px 20px;">{_details_table(ctx)}</td></tr>"""
        + _footer(ctx)
    )


def _default_html_booking_status_changed(ctx: Dict[str, str]) -> str:
    lang   = ctx.get("customer_language", "es")
    name   = ctx.get("customer_name", "")
    ref    = ctx.get("booking_ref", "")
    status = ctx.get("status", "")
    return (
        _header(ctx, _t(lang, "status_title"), "#235e58")
        + f"""<tr><td style="padding:26px 26px 8px;color:#0f172a;font-size:15px;line-height:1.65;">
  <p style="margin:0 0 12px;">{_t(lang,"status_hello",name=name)}</p>
  <p style="margin:0 0 12px;">{_t(lang,"status_body",ref=ref,status=status)}</p>
</td></tr>
<tr><td style="padding:0 26px 20px;">{_details_table(ctx)}</td></tr>"""
        + _footer(ctx)
    )


_TRIPADVISOR_URL = "https://www.tripadvisor.cl/UserReviewEdit-g294297-d33038747-HotBoat-Pucon_Araucania_Region.html"
_SURVEY_URL      = "https://docs.google.com/forms/d/e/1FAIpQLSd0ZsxvVMKa1sMg7JRaKBIMpe__2xwCwswscDGTTFIvlJcOIQ/viewform?usp=sharing"

def _default_html_booking_followup(ctx: Dict[str, str]) -> str:
    lang = ctx.get("customer_language", "es")
    name = ctx.get("customer_name", "")

    accent = (
        '<td width="33%" height="4" bgcolor="#34a394" style="line-height:4px;font-size:0;">&nbsp;</td>'
        '<td width="34%" height="4" bgcolor="#34d399" style="line-height:4px;font-size:0;">&nbsp;</td>'
        '<td width="33%" height="4" bgcolor="#2c7a72" style="line-height:4px;font-size:0;">&nbsp;</td>'
    )

    extra_body = f"""
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr><td style="padding:0 28px 24px;">
      <p style="margin:0 0 10px;color:#cbd5e1;font-size:15px;line-height:1.65;">
        {_t(lang,"followup_body1")}
      </p>
      <p style="margin:0;color:#94a3b8;font-size:14px;line-height:1.65;">
        {_t(lang,"followup_body2")}
      </p>
    </td></tr>
    </table>"""

    cta_rows = f"""
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:10px;">
    <tr>
      <td style="padding-right:6px;">{_cta_btn(_t(lang,"followup_review_label"), _TRIPADVISOR_URL, solid=True)}</td>
    </tr>
    </table>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr>
      <td>{_cta_btn(_t(lang,"followup_survey_label"), _SURVEY_URL, solid=False)}</td>
    </tr>
    </table>"""

    return _hotboat_email_card(
        ctx,
        hero_title=_t(lang, "followup_title"),
        hero_subtitle=_t(lang, "followup_hello", name=name),
        accent_bar=accent,
        extra_body=extra_body,
        cta_rows=cta_rows,
    )


def _default_html_admin_new_lead(ctx: Dict[str, str]) -> str:
    name  = ctx.get("customer_name", "el cliente")
    date  = ctx.get("booking_date", "")
    time_ = ctx.get("booking_time", "")
    phone = ctx.get("customer_phone", "")
    wa_msg = (
        f"Hola {name}! Vimos que intentaste hacer una reserva en Hot Boat Chile "
        f"para el {date} a las {time_}, pero parece que hubo un problema con el pago. "
        f"¿Te podemos ayudar a completar tu reserva? 😊"
    )
    wa_url  = _wa_link(phone, wa_msg)
    wa_btn  = "" if not phone else (
        f"""<tr><td style="padding:4px 26px 24px;text-align:center;">
  <a href="{wa_url}" target="_blank"
     style="display:inline-block;background:#25d366;color:#ffffff;font-size:15px;
            font-weight:600;text-decoration:none;padding:13px 32px;border-radius:8px;">
    💬 Contactar por WhatsApp
  </a>
  <p style="margin:10px 0 0;font-size:12px;color:#64748b;">
    Mensaje pre-cargado: problema con el pago de la reserva {date} {time_}
  </p>
</td></tr>"""
    )
    _ad = ctx.get("ad_source_label", "")
    _ad_row = (
        "<tr><td colspan='2' style='padding:0 26px 8px;'>"
        "<table role='presentation' width='100%' style='background:#eff6ff;border-radius:8px;"
        "border:1px solid #bfe3dd;font-size:14px;color:#235e58;'>"
        "<tr><td style='padding:10px 16px'><strong>Anuncio (origen)</strong></td>"
        "<td style='padding:10px 16px;text-align:right;font-weight:600'>\U0001f4e2 " + _ad + "</td>"
        "</tr></table></td></tr>"
        if _ad else ""
    )
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
        <td style="padding:12px 16px;border-top:1px solid #e2e8f0;text-align:right">{phone}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #e2e8f0"><strong>Email</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #e2e8f0;text-align:right">{ctx.get('customer_email','—')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #e2e8f0"><strong>Fecha</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #e2e8f0;text-align:right">{date} {time_}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #e2e8f0"><strong>Personas</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #e2e8f0;text-align:right">{ctx.get('num_people','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #e2e8f0"><strong>Total</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #e2e8f0;text-align:right">{ctx.get('total_price_fmt','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #e2e8f0"><strong>Ref</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #e2e8f0;text-align:right;font-family:monospace">{ctx.get('booking_ref','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #e2e8f0"><strong>Estado</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #e2e8f0;text-align:right;color:#b45309">pendiente de pago</td></tr>
    {ctx.get('extras_html','')}
  </table>
</td></tr>"""
        + _ad_row
        + wa_btn
        + _footer(ctx)
    )


def _default_html_admin_pending_payment(ctx: Dict[str, str]) -> str:
    name  = ctx.get("customer_name", "el cliente")
    date  = ctx.get("booking_date", "")
    time_ = ctx.get("booking_time", "")
    phone = ctx.get("customer_phone", "")
    wa_msg = (
        f"Hola {name}! Vimos que intentaste hacer una reserva en Hot Boat Chile "
        f"para el {date} a las {time_}, pero parece que hubo un problema con el pago. "
        f"¿Te podemos ayudar a completar tu reserva? 😊"
    )
    wa_url = _wa_link(phone, wa_msg)
    wa_btn = "" if not phone else (
        f"""<tr><td style="padding:4px 26px 24px;text-align:center;">
  <a href="{wa_url}" target="_blank"
     style="display:inline-block;background:#25d366;color:#ffffff;font-size:15px;
            font-weight:600;text-decoration:none;padding:13px 32px;border-radius:8px;">
    💬 Contactar por WhatsApp
  </a>
  <p style="margin:10px 0 0;font-size:12px;color:#64748b;">
    Mensaje pre-cargado: problema con el pago de la reserva {date} {time_}
  </p>
</td></tr>"""
    )
    return (
        _header(ctx, "⚠️ Pago pendiente — sin completar", "#d97706")
        + f"""<tr><td style="padding:22px 26px 6px;color:#0f172a;font-size:15px;line-height:1.65;">
  <p style="margin:0 0 10px;">Han pasado 5 minutos y el cliente <strong>no completó el pago</strong>.
  Puedes contactarle directamente por WhatsApp.</p>
</td></tr>
<tr><td style="padding:0 26px 20px;">
  <table role="presentation" width="100%" style="background:#fffbeb;border-radius:10px;
         border:1px solid #fde68a;font-size:14px;color:#334155;">
    <tr><td style="padding:12px 16px"><strong>Nombre</strong></td>
        <td style="padding:12px 16px;text-align:right">{name}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #fde68a"><strong>Teléfono</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #fde68a;text-align:right">{phone}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #fde68a"><strong>Email</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #fde68a;text-align:right">{ctx.get('customer_email','—')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #fde68a"><strong>Fecha</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #fde68a;text-align:right">{date} {time_}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #fde68a"><strong>Personas</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #fde68a;text-align:right">{ctx.get('num_people','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #fde68a"><strong>Total</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #fde68a;text-align:right">{ctx.get('total_price_fmt','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #fde68a"><strong>Ref</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #fde68a;text-align:right;font-family:monospace">{ctx.get('booking_ref','')}</td></tr>
    {ctx.get('extras_html_pending','')}
  </table>
</td></tr>"""
        + wa_btn
        + _footer(ctx)
    )


def _default_html_admin_booking_confirmed(ctx: Dict[str, str]) -> str:
    return (
        _header(ctx, "✅ Reserva confirmada y pagada", "#16a34a")
        + f"""<tr><td style="padding:22px 26px 6px;color:#0f172a;font-size:15px;line-height:1.65;">
  <p style="margin:0 0 10px;">El cliente completó el pago. Aquí están los detalles:</p>
</td></tr>
<tr><td style="padding:0 26px 20px;">
  <table role="presentation" width="100%" style="background:#f0fdf4;border-radius:10px;
         border:1px solid #bbf7d0;font-size:14px;color:#166534;">
    <tr><td style="padding:12px 16px"><strong>Nombre</strong></td>
        <td style="padding:12px 16px;text-align:right">{ctx.get('customer_name','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #bbf7d0"><strong>Teléfono</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #bbf7d0;text-align:right">{ctx.get('customer_phone','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #bbf7d0"><strong>Email</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #bbf7d0;text-align:right">{ctx.get('customer_email','—')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #bbf7d0"><strong>Fecha</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #bbf7d0;text-align:right">{ctx.get('booking_date','')} {ctx.get('booking_time','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #bbf7d0"><strong>Personas</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #bbf7d0;text-align:right">{ctx.get('num_people','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #bbf7d0"><strong>Total</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #bbf7d0;text-align:right;font-weight:bold">{ctx.get('total_price_fmt','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #bbf7d0"><strong>Ref</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #bbf7d0;text-align:right;font-family:monospace">{ctx.get('booking_ref','')}</td></tr>
    <tr><td style="padding:12px 16px;border-top:1px solid #bbf7d0"><strong>Estado</strong></td>
        <td style="padding:12px 16px;border-top:1px solid #bbf7d0;text-align:right;color:#16a34a;font-weight:bold">✅ confirmada</td></tr>
  </table>
</td></tr>"""
        + _footer(ctx)
    )


def _default_html_customer_birthday(ctx: Dict[str, str]) -> str:
    lang  = ctx.get("customer_language", "es")
    name  = ctx.get("customer_name", "")
    biz   = ctx.get("business_name", "Hot Boat")
    phone = ctx.get("business_phone", "")
    return (
        _header(ctx, _t(lang, "birthday_title"), "linear-gradient(135deg,#7c3aed,#db2777)")
        + f"""<tr><td style="padding:26px 26px 8px;color:#0f172a;font-size:15px;line-height:1.65;">
  <p style="margin:0 0 14px;">{_t(lang,"birthday_hello",name=name)}</p>
  <p style="margin:0 0 14px;">{_t(lang,"birthday_body1",biz=biz)}</p>
  <p style="margin:0 0 14px;">{_t(lang,"birthday_body2")}</p>
</td></tr>
<tr><td style="padding:0 26px 26px;font-size:13px;color:#64748b;line-height:1.6;">
  <p style="margin:0;">{_t(lang,"birthday_cta",phone=phone)}</p>
  <p style="margin:10px 0 0;"><a href="{ctx.get('business_website','#')}"
     style="color:#7c3aed;">{ctx.get('business_website','')}</a></p>
</td></tr></table></td></tr></table></body></html>"""
    )


_DEFAULT_TEMPLATES = {
    "booking_created":           _default_html_booking_created,
    "booking_confirmed":         _default_html_booking_confirmed,
    "booking_cancelled":         _default_html_booking_cancelled,
    "booking_status_changed":    _default_html_booking_status_changed,
    "booking_followup":          _default_html_booking_followup,
    "admin_new_lead":            _default_html_admin_new_lead,
    "admin_pending_payment":     _default_html_admin_pending_payment,
    "admin_booking_confirmed":   _default_html_admin_booking_confirmed,
    "customer_birthday":         _default_html_customer_birthday,
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

    from_addr = _get_from_addr(settings)
    # For customer-facing emails, set reply_to to the admin email so replies land in a real inbox
    is_admin_trigger = (TRIGGER_META.get(trigger) or {}).get("recipient") == "admin"
    reply_to_addr = None if is_admin_trigger else (_get_admin_email(settings) or None)
    logger.info("Sending email trigger=%s to=%s from=%s reply_to=%s", trigger, to_addr, from_addr, reply_to_addr)
    try:
        send_booking_html(
            to=to_addr,
            subject=subject,
            html=html,
            from_address=from_addr,
            api_key=api_key,
            bcc=_get_bcc(settings),
            reply_to=reply_to_addr,
        )
        out["sent"] = True
        out["reason"] = "ok"
    except Exception as e:
        # Log the full Resend error so it appears in Railway logs
        error_detail = str(e)
        try:
            # ResendError usually has a response body with more info
            if hasattr(e, "response"):
                error_detail += f" | response: {e.response}"
            if hasattr(e, "body"):
                error_detail += f" | body: {e.body}"
        except Exception:
            pass
        logger.error(
            "Email send FAILED trigger=%s to=%s from=%s | %s",
            trigger, to_addr, from_addr, error_detail,
        )
        out["reason"] = error_detail
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
    # Derive booking_ref (for display) and firma_ref (for the signing URL).
    # firma_ref must be resolvable by the /firma/ system:
    #   HB-xxx → hotboat_appointments
    #   AA-{int} → all_appointments
    # MANUAL-xxx / source_id-only refs use AA-{id} for the signing link.
    apt_id = data.get("id") or data.get("appointment_id_int")
    raw_ref = str(data.get("booking_ref") or "").strip()
    source_id = str(data.get("source_id") or "").strip()

    # Display ref (shown in the email body)
    booking_ref = raw_ref or source_id or (f"AA-{apt_id}" if apt_id else "")

    # Firma ref: web bookings keep HB-xxx, everything else uses AA-{id}
    if source_id and not raw_ref.startswith("MANUAL"):
        firma_ref = source_id          # HB-xxx
    elif apt_id:
        firma_ref = f"AA-{apt_id}"    # universal ref for all_appointments
    elif raw_ref and not raw_ref.startswith("MANUAL"):
        firma_ref = raw_ref
    else:
        firma_ref = ""

    base_url = _get_base_url()
    firma_url = f"{base_url}/firma/{firma_ref}" if firma_ref and base_url else ""

    raw_lang = str(data.get("customer_language") or "es").strip().lower()
    if raw_lang not in ("es", "en", "pt"):
        raw_lang = "es"
    ctx: Dict[str, str] = {
        "booking_ref":       booking_ref,
        "customer_name":     str(data.get("customer_name") or data.get("nombre_cliente") or "Cliente"),
        "customer_email":    to_addr,
        "customer_phone":    str(data.get("customer_phone") or data.get("telefono") or ""),
        "booking_date":      str(data.get("booking_date") or data.get("fecha") or ""),
        "booking_time":      bt,
        "num_people":        str(data.get("num_people") or data.get("num_personas") or ""),
        "total_price":       str(data.get("total_price") or data.get("ingreso_total") or ""),
        "total_price_fmt":   _fmt_clp(data.get("total_price") or data.get("ingreso_total")),
        "subtotal_fmt":      _fmt_clp(data.get("subtotal") or data.get("ingreso_reserva")),
        "extras_total_fmt":  _fmt_clp(data.get("extras_total") or data.get("ingreso_extras")),
        "status":            str(data.get("status") or ""),
        "business_name":     getattr(s, "business_name", "Hot Boat"),
        "business_phone":    getattr(s, "business_phone", ""),
        "business_email":    getattr(s, "business_email", ""),
        "business_website":  getattr(s, "business_website", ""),
        "firma_url":         firma_url,
        "customer_language": raw_lang,
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
    return _render_and_send(trigger, effective_to, ctx)


# ── Daily follow-up sweep ────────────────────────────────────────────────────

def send_manual_followup_email(rid: int) -> Dict[str, Any]:
    """
    Send booking_followup (TripAdvisor / survey) for one all_appointments row from the admin UI.
    Does not require workflow enabled (same templates/subject as auto sweep); needs Resend API key.
    """
    out: Dict[str, Any] = {"sent": False, "reason": ""}
    settings = get_settings()
    if not (getattr(settings, "resend_api_key", "") or "").strip():
        out["reason"] = "no_resend_key"
        return out

    from app.db.connection import get_connection

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nombre_cliente, telefono, email, fecha, hora, num_personas, "
                "ingreso_reserva, ingreso_extras, ingreso_total, status, "
                "COALESCE(customer_language,'es'), source, source_id "
                "FROM all_appointments WHERE id=%s",
                (rid,),
            )
            row = cur.fetchone()

    if not row:
        out["reason"] = "not_found"
        return out

    (
        _id,
        nombre,
        telefono,
        email,
        fecha,
        hora,
        num_p,
        ing_res,
        ing_ext,
        ing_total,
        status,
        lang,
        source,
        source_id,
    ) = row

    to_addr = (email or "").strip()
    if not to_addr:
        out["reason"] = "no_customer_email"
        return out

    src = str(source or "")
    sid = str(source_id or "").strip()
    if src == "hotboat_web" and sid:
        booking_ref = sid
    else:
        booking_ref = f"AA-{rid}"

    booking: Dict[str, Any] = {
        "booking_ref": booking_ref,
        "customer_name": nombre or "Cliente",
        "customer_email": to_addr,
        "customer_phone": telefono or "",
        "booking_date": str(fecha) if fecha else "",
        "booking_time": str(hora)[:5] if hora else "",
        "num_people": str(num_p) if num_p not in (None, "") else "",
        "total_price": ing_total,
        "subtotal": ing_res,
        "extras_total": ing_ext,
        "status": status or "",
        "customer_language": lang or "es",
    }
    ctx = _booking_ctx(booking)
    result = _render_and_send("booking_followup", to_addr, ctx)
    if result.get("sent"):
        mark_followup_sent_after_manual_send(rid)
        out["sent"] = True
        out["reason"] = "ok"
        logger.info("Manual follow-up email sent rid=%s to=%s", rid, to_addr)
    else:
        out["reason"] = result.get("reason") or "send_failed"
        logger.warning("Manual follow-up email failed rid=%s reason=%s", rid, out["reason"])
    return out


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

    hours_after = int(cfg.get("hours_after") or cfg.get("days_after") or 2)
    bookings = get_bookings_for_followup(hours_after)
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

    logger.info("Followup sweep: hours_after=%s checked=%s sent=%s", hours_after, out["checked"], out["sent"])
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


# ── Pending-payment reminder sweep ───────────────────────────────────────────

def run_pending_payment_email_sweep(delay_minutes: int = 5) -> dict:
    """
    Runs every few minutes: find bookings still in 'pending_payment' status
    that were created >{delay_minutes} minutes ago and haven't received the
    booking_created reminder email yet. Sends once, marks sent.
    """
    out: Dict[str, Any] = {"checked": 0, "sent": 0, "errors": []}
    settings = get_settings()
    if not (getattr(settings, "resend_api_key", "") or "").strip():
        out["reason"] = "no_resend_key"
        return out

    bookings = get_bookings_pending_payment_email(delay_minutes)
    out["checked"] = len(bookings)
    for b in bookings:
        to_addr = (b.get("customer_email") or "").strip()
        if not to_addr:
            continue
        ctx = _booking_ctx(b)

        # Notify customer with booking reminder
        result = _render_and_send("booking_created", to_addr, ctx)
        if result.get("sent"):
            mark_pending_email_sent(b["booking_ref"])
            out["sent"] += 1
        else:
            out["errors"].append({"ref": b["booking_ref"], "reason": result.get("reason")})

        # Notify admin with WhatsApp contact button (fire-and-forget, don't block on failure)
        if _can_send("admin_pending_payment"):
            admin_email = _get_admin_email(settings)
            if admin_email:
                try:
                    _render_and_send("admin_pending_payment", admin_email, ctx)
                except Exception as _e:
                    logger.warning("admin_pending_payment email failed ref=%s: %s", b["booking_ref"], _e)

    if out["checked"]:
        logger.info("Pending-payment email sweep: checked=%s sent=%s", out["checked"], out["sent"])
    return out


# ── Legacy aliases (backwards compat) ─────────────────────────────────────────

def send_confirmation_admin_force(booking_id: int) -> Dict[str, Any]:
    """
    Force-send booking_confirmed email for any all_appointments row by integer id.
    Shows real extras, flex, coupon, and actual paid/balance amounts from the DB.
    Bypasses status/idempotency guards and any custom body_html template.
    """
    import json as _json
    from app.booking.db import get_connection, _legacy_booking_from_aa
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, source_id, nombre_cliente, telefono, email,
                          fecha, hora, num_personas,
                          ingreso_reserva, ingreso_extras, ingreso_total,
                          extras_json, has_flex, COALESCE(flex_amount,0),
                          status, payment_id, payment_order_id, payment_status,
                          paid_at, observaciones, created_at, confirmation_email_sent_at,
                          COALESCE(customer_language,'es'), coupon_code,
                          COALESCE(coupon_discount,0),
                          coupon_extra_benefit, customer_birthday, source,
                          COALESCE(utm_source,''), COALESCE(utm_medium,''),
                          COALESCE(utm_campaign,''), COALESCE(utm_content,''),
                          COALESCE(parametro_url,''),
                          COALESCE(pagos,'[]'::jsonb),
                          COALESCE(descuentos,'[]'::jsonb)
                   FROM all_appointments WHERE id=%s""",
                (booking_id,),
            )
            row = cur.fetchone()
    if not row:
        return {"sent": False, "reason": "not_found"}
    cols = [
        "id", "source_id", "nombre_cliente", "telefono", "email",
        "fecha", "hora", "num_personas",
        "ingreso_reserva", "ingreso_extras", "ingreso_total",
        "extras_json", "has_flex", "flex_amount",
        "status", "payment_id", "payment_order_id", "payment_status",
        "paid_at", "observaciones", "created_at", "confirmation_email_sent_at",
        "customer_language", "coupon_code", "coupon_discount",
        "coupon_extra_benefit", "customer_birthday", "source",
        "utm_source", "utm_medium", "utm_campaign", "utm_content", "parametro_url",
        "pagos", "descuentos",
    ]
    d = dict(zip(cols, row))

    # Parse JSON fields (psycopg may return them already as dicts/lists)
    def _parse_json(v):
        if v is None:
            return []
        if isinstance(v, (list, dict)):
            return v
        try:
            return _json.loads(v)
        except Exception:
            return []

    pagos = _parse_json(d.get("pagos"))
    descuentos = _parse_json(d.get("descuentos"))

    # Normalize extras_json to dict {key: {qty, unit_price, name}}
    # Three formats exist:
    #   1. dict  {key: {qty, unit_price, name?, ...}}  — admin-saved
    #   2. list  [{name, price, quantity}]              — web booking
    #   3. dict  {extras: [{name, price, quantity}], price_per_person: N}  — web HotBoat envelope
    raw_ej = _parse_json(d.get("extras_json")) if d.get("extras_json") else {}
    if isinstance(raw_ej, dict) and isinstance(raw_ej.get("extras"), list):
        raw_ej = raw_ej["extras"]  # unwrap envelope → now a list
    if isinstance(raw_ej, list):
        converted: dict = {}
        for i, e in enumerate(raw_ej):
            if not isinstance(e, dict):
                continue
            raw_name = str(e.get("name") or f"extra_{i}")
            key = raw_name.lower().replace(" ", "_")[:40] or f"extra_{i}"
            converted[key] = {
                "qty": int(e.get("quantity") or e.get("qty") or 1),
                "unit_price": float(e.get("price") or e.get("unit_price") or 0),
                "name": raw_name,
            }
        extras_dict: dict = converted
    else:
        extras_dict = raw_ej if isinstance(raw_ej, dict) else {}

    booking = _legacy_booking_from_aa(d)
    to_addr = (booking.get("customer_email") or "").strip()
    if not to_addr:
        return {"sent": False, "reason": "no_customer_email"}

    ctx = _booking_ctx(booking)

    # ── Load extras catalog for name lookup ──────────────────────────────────
    import unicodedata as _unicodedata
    def _slug(s: str) -> str:
        s = _unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

    catalog_by_key: Dict[str, Dict] = {}
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT extra_name_lower, name, COALESCE(precio_venta,0) FROM extras_visibility WHERE COALESCE(user_hidden,FALSE)=FALSE"
                )
                for (name_lower, name, price) in cur.fetchall():
                    display = name or name_lower
                    catalog_by_key[_slug(display)] = {"name": display, "price": float(price)}
                    catalog_by_key[name_lower]     = {"name": display, "price": float(price)}
    except Exception as _ce:
        logger.warning("Could not load extras_visibility for email: %s", _ce)

    # ── Compute real amounts ────────────────────────────────────────────────
    ingreso_reserva   = float(d.get("ingreso_reserva") or 0)
    ingreso_extras    = float(d.get("ingreso_extras") or 0)
    ingreso_total     = float(d.get("ingreso_total") or 0)
    has_flex          = bool(d.get("has_flex"))
    flex_amount       = float(d.get("flex_amount") or 0)
    coupon_discount   = float(d.get("coupon_discount") or 0)
    manual_discounts  = sum(float(dc.get("amount") or 0) for dc in descuentos if isinstance(dc, dict))
    total_paid        = sum(float(p.get("amount") or 0) for p in pagos if isinstance(p, dict))
    balance_due       = max(0.0, ingreso_total - total_paid)

    # Override deposit to show real paid
    ctx["deposit_fmt"] = _fmt_clp(total_paid)

    # ── Build extras detail rows ─────────────────────────────────────────────
    ROW = (
        '<tr><td style="padding:10px 20px;border-bottom:1px solid #1a2e28;">'
        '<table width="100%" cellspacing="0" cellpadding="0"><tr>'
        '<td style="color:#94a3b8;font-size:12px;">{label}</td>'
        '<td align="right" style="color:{color};font-size:13px;font-weight:600;">{value}</td>'
        '</tr></table></td></tr>'
    )

    extra_rows = []
    # Base reservation
    extra_rows.append(ROW.format(
        label="Experiencia HotBoat",
        color="#e2e8f0",
        value=_fmt_clp(ingreso_reserva),
    ))
    # Individual extras — show all items with qty > 0, resolve names from catalog
    extras_itemized_total = 0.0
    has_any_extra = False
    for key, val in extras_dict.items():
        # val can be: {qty, unit_price, name?}  OR  a plain number (qty)
        if isinstance(val, (int, float)):
            qty = int(val)
            unit_price = 0.0
            stored_name = ""
        elif isinstance(val, dict):
            qty = int(val.get("qty") or val.get("nights") or val.get("cantidad") or 1)
            unit_price = float(val.get("unit_price") or 0)
            stored_name = str(val.get("name") or "").strip()
        else:
            continue
        if qty <= 0:
            continue
        has_any_extra = True
        # Price: stored value → catalog fallback
        if unit_price <= 0:
            unit_price = float((catalog_by_key.get(key) or {}).get("price") or 0)
        # Name: stored → catalog → humanise key
        cat_name = (catalog_by_key.get(key) or {}).get("name") or ""
        raw_name = stored_name or cat_name or key.replace("_", " ").title()
        name = raw_name.replace("<", "&lt;")
        label = f"{name} ×{qty}" if qty > 1 else name
        line_total = qty * unit_price
        extras_itemized_total += line_total
        value_str = _fmt_clp(line_total) if unit_price > 0 else "—"
        extra_rows.append(ROW.format(label=label, color="#e2e8f0", value=value_str))
    # Fallback: no items resolved at all but ingreso_extras > 0
    if not has_any_extra and ingreso_extras > 0:
        extra_rows.append(ROW.format(
            label="Extras",
            color="#e2e8f0",
            value=_fmt_clp(ingreso_extras),
        ))
    # Flex
    if has_flex and flex_amount > 0:
        extra_rows.append(ROW.format(
            label="🔒 Reserva Flex",
            color="#5fb8ae",
            value=_fmt_clp(flex_amount),
        ))
    # Coupon discount
    if coupon_discount > 0:
        code = d.get("coupon_code") or ""
        label = f"Descuento cupón{' ' + code if code else ''}"
        extra_rows.append(ROW.format(
            label=label,
            color="#f87171",
            value=f"-{_fmt_clp(coupon_discount)}",
        ))
    # Manual discounts
    for dc in descuentos:
        if not isinstance(dc, dict):
            continue
        amt = float(dc.get("amount") or 0)
        if amt <= 0:
            continue
        desc_label = (dc.get("description") or "Descuento").replace("<", "&lt;")
        extra_rows.append(ROW.format(
            label=desc_label,
            color="#f87171",
            value=f"-{_fmt_clp(amt)}",
        ))

    extra_detail_rows_html = "".join(extra_rows)

    # ── Payment rows (after total) ────────────────────────────────────────────
    after_rows = []
    PAID_ROW = (
        '<tr><td style="padding:10px 20px;border-bottom:1px solid #1a2e28;">'
        '<table width="100%" cellspacing="0" cellpadding="0"><tr>'
        '<td style="color:#94a3b8;font-size:12px;">{label}</td>'
        '<td align="right" style="color:#4ade80;font-size:13px;font-weight:600;">{value}</td>'
        '</tr></table></td></tr>'
    )
    for p in pagos:
        if not isinstance(p, dict):
            continue
        amt = float(p.get("amount") or 0)
        if amt <= 0:
            continue
        method = (p.get("method") or p.get("tipo") or "Pago").replace("<", "&lt;")
        pdate  = p.get("date") or ""
        label  = f"✅ {method}{' · ' + pdate if pdate else ''}"
        after_rows.append(PAID_ROW.format(label=label, value=_fmt_clp(amt)))

    if balance_due > 0:
        after_rows.append(
            '<tr><td style="padding:14px 20px;background:rgba(251,191,36,.07);">'
            '<table width="100%" cellspacing="0" cellpadding="0"><tr>'
            '<td style="color:#fcd34d;font-size:12px;font-weight:700;">💳 Saldo pendiente</td>'
            '<td align="right" style="color:#fbbf24;font-size:15px;font-weight:800;">'
            + _fmt_clp(balance_due)
            + '</td></tr></table></td></tr>'
        )

    after_total_rows_html = "".join(after_rows)

    # ── Build and send email ──────────────────────────────────────────────────
    # Clear idempotency flag so resend is not blocked
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE all_appointments SET confirmation_email_sent_at=NULL WHERE id=%s",
                (booking_id,),
            )
            conn.commit()

    s = get_settings()
    api_key = (getattr(s, "resend_api_key", "") or "").strip()
    if not api_key:
        return {"sent": False, "reason": "no_resend_key"}

    cfg = get_email_workflow("booking_confirmed")
    raw_subject = (cfg.get("subject") or "").strip()
    if not raw_subject:
        raw_subject = (TRIGGER_META.get("booking_confirmed") or {}).get(
            "default_subject", "Confirmación de reserva"
        )
    subject = _apply_template(raw_subject, ctx)

    lang = ctx.get("customer_language", "es")
    name = ctx.get("customer_name", "")
    website  = ctx.get("business_website", "#")
    firma_url = ctx.get("firma_url", "") or website
    tabla_url = ctx.get("tabla_url", "") or "https://hotboatchile.com/tablas/"
    accent = (
        '<td width="50%" height="4" bgcolor="#34a394" style="line-height:4px;font-size:0;">&nbsp;</td>'
        '<td width="50%" height="4" bgcolor="#e8b86d" style="line-height:4px;font-size:0;">&nbsp;</td>'
    )
    confirmed_note = f"""
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr><td style="padding:0 28px 16px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="background:rgba(44,122,114,.08);border:1px solid rgba(44,122,114,.3);border-radius:12px;">
      <tr><td style="padding:15px 20px;">
        <p style="margin:0;color:#8fd3c9;font-size:13px;line-height:1.65;">
          <strong>{_t(lang,"confirmed_payment_title")}</strong><br>
          {_t(lang,"confirmed_payment_body")}
        </p>
      </td></tr>
      </table>
    </td></tr>
    </table>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr><td style="padding:0 28px 24px;">
      <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
             style="background:rgba(251,191,36,.07);border:1px solid rgba(251,191,36,.3);border-radius:12px;">
      <tr><td style="padding:15px 20px;">
        <p style="margin:0 0 8px;color:#fcd34d;font-size:13px;font-weight:700;">
          {_t(lang,"tc_title")}
        </p>
        <p style="margin:0;color:#fde68a;font-size:12px;line-height:1.6;">
          {_t(lang,"tc_body")}
        </p>
        <p style="margin:10px 0 0;">
          <a href="{firma_url}" style="color:#fbbf24;font-weight:700;font-size:12px;word-break:break-all;">{firma_url}</a>
        </p>
      </td></tr>
      </table>
    </td></tr>
    </table>"""
    cta_rows = f"""
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="margin-bottom:10px;">
    <tr>
      <td width="50%" style="padding-right:6px;">{_cta_btn(_t(lang,"cta_summary"), "https://srv1080-files.hstgr.io/2f0792bfa7cfcf2b/files/public_html/images/Resumen_reserva_espa%C3%B1ol.png", solid=True)}</td>
      <td width="50%" style="padding-left:6px;">{_cta_btn(_t(lang,"cta_sign_tc"), firma_url, solid=False)}</td>
    </tr>
    </table>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
    <tr>
      <td width="50%" style="padding-right:6px;">{_cta_btn(_t(lang,"cta_video"), "https://www.youtube.com/shorts/-9Y23l40oSQ?si=_mZrnTlw33qhf2bb", solid=False)}</td>
      <td width="50%" style="padding-left:6px;">{_cta_btn(_t(lang,"cta_menu"), tabla_url, solid=False)}</td>
    </tr>
    </table>"""

    html = _hotboat_email_card(
        ctx,
        hero_title=_t(lang, "confirmed_title"),
        hero_subtitle=_t(lang, "confirmed_subtitle", name=name),
        accent_bar=accent,
        extra_body=confirmed_note,
        cta_rows=cta_rows,
        deposit_row_i18n_key="label_paid",
        extra_detail_rows_html=extra_detail_rows_html,
        after_total_rows_html=after_total_rows_html,
    )

    from_addr = _get_from_addr(s)
    reply_to_addr = _get_admin_email(s) or None
    out: Dict[str, Any] = {"sent": False, "reason": ""}
    try:
        send_booking_html(
            to=to_addr,
            subject=subject,
            html=html,
            from_address=from_addr,
            api_key=api_key,
            bcc=_get_bcc(s),
            reply_to=reply_to_addr,
        )
        out["sent"] = True
        out["reason"] = "ok"
    except Exception as e:
        out["reason"] = str(e)
        logger.error("send_confirmation_admin_force failed booking_id=%s to=%s: %s", booking_id, to_addr, e)
    return out


def try_send_booking_confirmation_after_payment(booking_ref: str) -> Dict[str, Any]:
    """
    Send the booking_confirmed email after a successful web payment.
    Uses send_confirmation_admin_force (same as the admin panel button) so the
    email always contains real DB data — never template/sample placeholders.
    """
    # Look up the booking to get the integer ID and check idempotency
    booking = get_booking_by_ref(booking_ref)
    if not booking:
        logger.warning("try_send_booking_confirmation_after_payment: booking not found ref=%s", booking_ref)
        return {"sent": False, "reason": "not_found"}

    if booking.get("confirmation_email_sent_at"):
        logger.info("try_send_booking_confirmation_after_payment: already sent ref=%s", booking_ref)
        return {"sent": False, "reason": "already_sent"}

    booking_id = booking.get("id")
    if not booking_id:
        logger.warning("try_send_booking_confirmation_after_payment: no id for ref=%s", booking_ref)
        return {"sent": False, "reason": "no_id"}

    # Use the same rich-email builder the admin panel uses — always real data
    result = send_confirmation_admin_force(booking_id)

    # Mark idempotency flag so the pending-payment sweep doesn't re-send
    if result.get("sent"):
        mark_confirmation_email_sent(booking_ref)

    # Also notify the operator
    try:
        send_email_for_trigger("admin_booking_confirmed", booking_ref)
    except Exception as _e:
        logger.warning("admin_booking_confirmed email: %s", _e)

    return result


def send_test_booking_email(to_address: str) -> Dict[str, Any]:
    return send_test_email_for_trigger("booking_confirmed", to_address)


# ── Daily morning summary ─────────────────────────────────────────────────────

_MAPS_URL = "https://maps.app.goo.gl/jVYVHRzekkmFRjEH7"
_MAPS_EMBED = "https://www.google.com/maps/embed?pb=!1m18!1m12!1m3!1d3071.0!2d-71.85!3d-39.28!2m3!1f0!2f0!3f0!3m2!1i1024!2i768!4f13.1!3m3!1m2!1s0x0%3A0x0!2sHotBoat!5e0!3m2!1ses!2scl!4v1"


def _wa_link(phone: str, message: str) -> str:
    """Build a wa.me deep-link with a pre-filled message."""
    import urllib.parse
    # Normalise phone: keep only digits, strip leading 0, ensure country code
    digits = "".join(c for c in (phone or "") if c.isdigit())
    if digits.startswith("0"):
        digits = digits[1:]
    if digits and not digits.startswith("56"):
        digits = "56" + digits
    if not digits:
        return "#"
    return f"https://wa.me/{digits}?text={urllib.parse.quote(message)}"


def _extras_summary_html(extras_json: Any) -> str:
    """Return a compact HTML list of extras, or empty string."""
    if not extras_json:
        return ""
    items: List[str] = []
    if isinstance(extras_json, dict):
        for k, v in extras_json.items():
            if v and k not in ("", None):
                items.append(f"{k}: {v}")
    elif isinstance(extras_json, list):
        for item in extras_json:
            if isinstance(item, dict):
                name = item.get("name") or item.get("key") or ""
                qty  = item.get("qty") or item.get("quantity") or ""
                if name:
                    items.append(f"{name}{' ×'+str(qty) if qty else ''}")
            else:
                items.append(str(item))
    if not items:
        return ""
    li = "".join(f"<li style='margin:2px 0'>{i}</li>" for i in items)
    return f"<ul style='margin:4px 0 0 16px;padding:0;font-size:12px;color:#64748b'>{li}</ul>"


def _build_daily_summary_html(today_str: str, bookings: List[dict], settings) -> str:
    business = getattr(settings, "business_name", "Hot Boat")
    n = len(bookings)
    total_rev = sum(float(b.get("ingreso_total") or 0) for b in bookings)
    total_pax = sum(int(b.get("num_personas") or 0) for b in bookings)

    def fmt_clp(v):
        try:
            return f"${int(float(v or 0)):,}".replace(",", ".")
        except Exception:
            return str(v)

    # Header
    html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Resumen del día — {business}</title></head>
<body style="margin:0;padding:0;background:#0f172a;font-family:'Segoe UI',Arial,sans-serif;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
  style="background:#0f172a;padding:28px 12px;">
<tr><td align="center">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
  style="max-width:600px;width:100%;background:#1e293b;border-radius:16px;overflow:hidden;
         box-shadow:0 8px 40px rgba(0,0,0,.5);">

<!-- HEADER -->
<tr><td style="background:linear-gradient(135deg,#235e58,#34897f);
               padding:28px 28px 20px;text-align:center;">
  <p style="margin:0 0 6px;font-size:13px;color:#bae6fd;letter-spacing:2px;
             text-transform:uppercase">Resumen del día</p>
  <h1 style="margin:0;font-size:28px;color:#fff;font-weight:800">{today_str}</h1>
  <p style="margin:10px 0 0;font-size:14px;color:#e0f2fe">{business}</p>
</td></tr>

<!-- STATS BAR -->
<tr><td style="padding:16px 28px">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0">
  <tr>
    <td style="text-align:center;background:#0f172a;border-radius:10px;padding:14px 8px;width:33%">
      <p style="margin:0;font-size:28px;font-weight:800;color:#38bdf8">{n}</p>
      <p style="margin:4px 0 0;font-size:11px;color:#94a3b8;text-transform:uppercase">Reservas</p>
    </td>
    <td width="8"></td>
    <td style="text-align:center;background:#0f172a;border-radius:10px;padding:14px 8px;width:33%">
      <p style="margin:0;font-size:28px;font-weight:800;color:#34d399">{total_pax}</p>
      <p style="margin:4px 0 0;font-size:11px;color:#94a3b8;text-transform:uppercase">Personas</p>
    </td>
    <td width="8"></td>
    <td style="text-align:center;background:#0f172a;border-radius:10px;padding:14px 8px;width:33%">
      <p style="margin:0;font-size:22px;font-weight:800;color:#a78bfa">{fmt_clp(total_rev)}</p>
      <p style="margin:4px 0 0;font-size:11px;color:#94a3b8;text-transform:uppercase">Total día</p>
    </td>
  </tr>
  </table>
</td></tr>"""

    if not bookings:
        html += """<tr><td style="padding:28px;text-align:center;color:#94a3b8;font-size:15px">
  😴 No hay reservas para hoy.
</td></tr>"""
    else:
        # One card per booking
        for b in bookings:
            hora   = str(b.get("hora") or "")[:5]
            nombre = (b.get("nombre_cliente") or "Cliente").strip()
            first  = nombre.split()[0]
            tel    = (b.get("telefono") or "").strip()
            email  = (b.get("email") or "").strip()
            pax    = b.get("num_personas") or ""
            total  = fmt_clp(b.get("ingreso_total"))
            status = (b.get("status") or "").lower()
            obs    = (b.get("observaciones") or "").strip()
            extras_html = _extras_summary_html(b.get("extras_json"))

            status_color = "#34d399" if status == "confirmed" else "#f59e0b" if status else "#94a3b8"
            status_label = status.upper() if status else "SIN ESTADO"

            # WhatsApp reminder message
            reminder_msg = (
                f"Hola {first} 👋, te recordamos tu reserva en HotBoat para *hoy {today_str}* "
                f"a las *{hora}*. ¡Te esperamos! 🚤\n\n"
                f"📍 Cómo llegar: {_MAPS_URL}"
            )
            wa_url = _wa_link(tel, reminder_msg)

            html += f"""
<!-- BOOKING CARD -->
<tr><td style="padding:0 16px 16px">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0"
  style="background:#0f172a;border-radius:12px;overflow:hidden;border:1px solid #334155">

  <!-- time + status bar -->
  <tr>
    <td style="background:#1e3a5f;padding:10px 16px">
      <span style="font-size:22px;font-weight:800;color:#38bdf8">{hora}</span>
      <span style="font-size:14px;color:#94a3b8;margin-left:6px">hs</span>
    </td>
    <td style="background:#1e3a5f;padding:10px 16px;text-align:right">
      <span style="background:{status_color};color:#0f172a;padding:3px 10px;border-radius:20px;
                   font-size:11px;font-weight:700">{status_label}</span>
    </td>
  </tr>

  <!-- client details -->
  <tr><td colspan="2" style="padding:14px 16px 0">
    <p style="margin:0;font-size:18px;font-weight:700;color:#f1f5f9">{nombre}</p>
    {"<p style='margin:4px 0 0;font-size:13px;color:#94a3b8'>📞 "+tel+"</p>" if tel else ""}
    {"<p style='margin:2px 0 0;font-size:13px;color:#94a3b8'>✉ "+email+"</p>" if email else ""}
  </td></tr>

  <!-- stats row -->
  <tr><td colspan="2" style="padding:10px 16px">
    <table role="presentation" cellspacing="0" cellpadding="0">
    <tr>
      {"<td style='font-size:13px;color:#cbd5e1;margin-right:20px;padding-right:20px'>👥 <strong style=color:#f1f5f9>"+str(pax)+"</strong> personas</td>" if pax else ""}
      <td style="font-size:13px;color:#cbd5e1;padding-right:20px">💰 <strong style="color:#34d399">{total}</strong></td>
    </tr>
    </table>
    {extras_html}
    {"<p style='margin:6px 0 0;font-size:12px;color:#f59e0b'>📝 "+obs+"</p>" if obs else ""}
  </td></tr>

  <!-- action buttons -->
  <tr><td colspan="2" style="padding:12px 16px 14px">
    {"<a href='"+wa_url+"' style='display:inline-block;background:#25d366;color:#fff;text-decoration:none;padding:9px 18px;border-radius:8px;font-size:13px;font-weight:700;margin-right:8px'>💬 WhatsApp recordatorio</a>" if wa_url != "#" else ""}
    <a href="{_MAPS_URL}" style="display:inline-block;background:#2c7a72;color:#fff;text-decoration:none;
       padding:9px 18px;border-radius:8px;font-size:13px;font-weight:700">📍 Cómo llegar</a>
  </td></tr>

</table>
</td></tr>"""

    # Footer with maps link
    html += f"""
<!-- FOOTER MAP -->
<tr><td style="padding:8px 16px 24px">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0"
    style="background:#0f172a;border-radius:12px;border:1px solid #334155;overflow:hidden">
    <tr><td style="padding:16px">
      <p style="margin:0 0 10px;font-size:14px;font-weight:700;color:#f1f5f9">📍 Ubicación HotBoat</p>
      <p style="margin:0 0 10px;font-size:13px;color:#94a3b8">Entre Pucón y Curarrehue, corazón de La Araucanía</p>
      <a href="{_MAPS_URL}" style="display:inline-block;background:#2c7a72;color:#fff;
         text-decoration:none;padding:10px 20px;border-radius:8px;font-size:13px;font-weight:700">
        🗺️ Abrir en Google Maps
      </a>
    </td></tr>
  </table>
</td></tr>

<!-- BOTTOM -->
<tr><td style="padding:16px 28px 24px;text-align:center;font-size:12px;color:#475569">
  {business} · Resumen automático del día · {today_str}
</td></tr>

</table></td></tr></table></body></html>"""

    return html


def send_daily_summary_email() -> Dict[str, Any]:
    """
    Send the daily morning summary of today's bookings to the operator email.
    Returns a dict with sent/reason/count keys.
    """
    from zoneinfo import ZoneInfo
    from datetime import date
    out: Dict[str, Any] = {"sent": False, "reason": "", "count": 0}

    settings = get_settings()
    api_key = (getattr(settings, "resend_api_key", "") or "").strip()
    if not api_key:
        out["reason"] = "no_resend_key"
        return out

    to_addr = _get_admin_email(settings) or ""
    if not to_addr:
        out["reason"] = "no_admin_email"
        return out

    chile_tz = ZoneInfo("America/Santiago")
    today = date.today()  # already called at Santiago time from the scheduler
    today_str = today.strftime("%d/%m/%Y")
    today_iso = today.isoformat()

    # Fetch today's bookings (with status) from all_appointments
    try:
        from app.db.connection import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT nombre_cliente, email, telefono, hora, num_personas,
                           ingreso_total, status, extras_json, observaciones
                    FROM all_appointments
                    WHERE fecha = %s AND status IS NOT NULL
                    ORDER BY hora ASC NULLS LAST
                """, (today_iso,))
                cols = [d[0] for d in cur.description]
                bookings = [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as db_err:
        out["reason"] = f"db_error: {db_err}"
        logger.error("daily_summary: DB error: %s", db_err)
        return out

    out["count"] = len(bookings)

    # Always send even if 0 bookings (so the operator knows the day is free)
    html = _build_daily_summary_html(today_str, bookings, settings)

    n_label = f"{len(bookings)} reserva{'s' if len(bookings)!=1 else ''}" if bookings else "sin reservas"
    subject = f"📅 HotBoat hoy {today_str} — {n_label}"

    from_addr = _get_from_addr(settings)
    try:
        result = send_booking_html(
            to=to_addr,
            subject=subject,
            html=html,
            from_address=from_addr,
            api_key=api_key,
        )
        out["sent"] = True
        out["resend_id"] = result.get("id") if isinstance(result, dict) else str(result)
        logger.info("daily_summary: sent to %s (%s bookings)", to_addr, len(bookings))
    except Exception as send_err:
        out["reason"] = f"send_error: {send_err}"
        logger.error("daily_summary: send error: %s", send_err)

    return out

    return out


# ── Yesterday & Weekly summary emails ─────────────────────────────────────────

_NOTIF_TO = "hotboatnotification@gmail.com"


def _fmt_clp_local(v) -> str:
    try:
        return f"${int(float(v or 0)):,}".replace(",", ".")
    except Exception:
        return "$0"


def _build_booking_card_html(b: dict, is_weekly: bool = False) -> str:
    """Render one booking as a dark HTML card with full detail + missing-data alerts."""
    import json as _json

    def _p(v) -> str:
        return str(v or "").strip()

    nombre   = _p(b.get("nombre_cliente")) or "Sin nombre"
    fecha    = _p(b.get("fecha"))
    hora     = _p(b.get("hora"))[:5] if b.get("hora") else "-"
    personas = _p(b.get("num_personas")) or "-"
    total    = float(b.get("ingreso_total") or 0)
    ciudad   = _p(b.get("ciudad_origen"))
    como     = _p(b.get("como_supieron"))
    quien    = _p(b.get("quien_atendio"))
    obs      = _p(b.get("observaciones"))
    telefono = _p(b.get("telefono"))
    email_c  = _p(b.get("email"))
    status   = _p(b.get("status"))

    # Payments
    raw_pagos = b.get("pagos") or []
    if isinstance(raw_pagos, str):
        try:
            raw_pagos = _json.loads(raw_pagos)
        except Exception:
            raw_pagos = []
    pagos = [p for p in raw_pagos if isinstance(p, dict)]
    total_paid = sum(float(p.get("amount") or 0) for p in pagos)
    flex       = float(b.get("flex_amount") or 0)
    balance    = max(0.0, total + flex - total_paid)

    # Extras
    raw_ej = b.get("extras_json") or {}
    if isinstance(raw_ej, str):
        try:
            raw_ej = _json.loads(raw_ej)
        except Exception:
            raw_ej = {}
    if isinstance(raw_ej, dict) and isinstance(raw_ej.get("extras"), list):
        raw_ej = raw_ej["extras"]

    # Load catalog for proper names
    catalog = {}
    try:
        from app.db.connection import get_connection as _gc
        with _gc() as _conn:
            with _conn.cursor() as _cur:
                _cur.execute("SELECT extra_name_lower, COALESCE(name, extra_name_lower) FROM extras_visibility WHERE COALESCE(user_hidden,FALSE)=FALSE")
                for _k, _n in _cur.fetchall():
                    catalog[_k.lower()] = _n
    except Exception:
        pass

    extras_items = []
    if isinstance(raw_ej, list):
        for e in raw_ej:
            if not isinstance(e, dict):
                continue
            name = str(e.get("name") or "Extra").strip()
            qty  = int(e.get("quantity") or 1)
            extras_items.append(f"{name}{' ×'+str(qty) if qty > 1 else ''}")
    elif isinstance(raw_ej, dict):
        for k, v in raw_ej.items():
            if isinstance(v, (int, float)):
                qty = int(v)
            elif isinstance(v, dict):
                qty = int(v.get("qty") or v.get("cantidad") or 1)
            else:
                continue
            if qty <= 0:
                continue
            name = ""
            if isinstance(v, dict):
                name = str(v.get("name") or "").strip()
            name = name or catalog.get(k.lower()) or k.replace("_", " ").title()
            extras_items.append(f"{name}{' ×'+str(qty) if qty > 1 else ''}")

    if extras_items:
        badges = "".join(
            f'<span style="display:inline-block;margin:2px 3px 2px 0;background:rgba(99,102,241,.15);'
            f'color:#a5b4fc;border:1px solid rgba(99,102,241,.3);border-radius:6px;'
            f'padding:2px 8px;font-size:11px;white-space:normal;word-break:break-word;">{e}</span>'
            for e in extras_items
        )
        extras_html = f'<div style="display:flex;flex-wrap:wrap;gap:0;">{badges}</div>'
    else:
        extras_html = ""

    # Missing data detection
    alerts = []
    if not ciudad:
        alerts.append("🔴 <strong>Ciudad de origen</strong> no registrada")
    if not como:
        alerts.append("🔴 <strong>Cómo supieron</strong> de HotBoat no registrado")
    if not quien:
        alerts.append("🟡 <strong>Quién atendió</strong> no registrado")
    if balance > 0:
        alerts.append(f"🔴 <strong>Saldo pendiente</strong>: {_fmt_clp_local(balance)}")
    if not email_c:
        alerts.append("🟡 <strong>Email del cliente</strong> no registrado")

    status_color = {"confirmed": "#10b981", "pending_payment": "#f59e0b", "cancelled": "#ef4444"}.get(status, "#64748b")
    status_label = {"confirmed": "Confirmada", "pending_payment": "Pago pendiente", "cancelled": "Cancelada"}.get(status, status or "Sin estado")

    alerts_html = ""
    if alerts:
        items = "".join(f'<li style="margin:4px 0;color:#fca5a5;font-size:12px;">{a}</li>' for a in alerts)
        alerts_html = f"""
        <div style="background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.35);border-radius:8px;padding:10px 14px;margin:10px 0;">
          <p style="margin:0 0 6px;color:#f87171;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:1px;">⚠️ Datos faltantes</p>
          <ul style="margin:0;padding-left:16px;">{items}</ul>
        </div>"""

    pagos_html = ""
    if pagos:
        rows = "".join(
            f'<span style="display:inline-block;margin:2px 4px 2px 0;background:rgba(16,185,129,.15);color:#6ee7b7;'
            f'border-radius:6px;padding:3px 8px;font-size:11px;">'
            f'💳 {p.get("method") or p.get("tipo") or "Pago"} · {_fmt_clp_local(p.get("amount"))}'
            f'{" · " + str(p.get("date",""))[:10] if p.get("date") else ""}</span>'
            for p in pagos
        )
        pagos_html = f'<div style="margin:6px 0;">{rows}</div>'
    else:
        pagos_html = '<p style="margin:4px 0;color:#94a3b8;font-size:12px;">Sin pagos registrados</p>'

    def row(label, val, urgent=False):
        if not val:
            return ""
        color = "#fca5a5" if urgent else "#e2e8f0"
        return (
            f'<tr><td style="color:#64748b;font-size:11px;padding:4px 8px 4px 0;white-space:nowrap;vertical-align:top;">{label}</td>'
            f'<td style="color:{color};font-size:12px;padding:4px 0;font-weight:500;">{val}</td></tr>'
        )

    date_header = f"{fecha} · {hora} hs · " if is_weekly else f"{hora} hs · "

    return f"""
    <div style="background:#1e293b;border:1px solid #334155;border-radius:12px;padding:16px 20px;margin:12px 0;">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px;flex-wrap:wrap;">
        <span style="color:#f8fafc;font-size:15px;font-weight:700;">{date_header}{nombre}</span>
        <span style="background:{status_color}22;color:{status_color};border:1px solid {status_color}55;
               border-radius:6px;padding:2px 8px;font-size:11px;font-weight:600;">{status_label}</span>
        <span style="margin-left:auto;color:#10b981;font-size:15px;font-weight:800;">{_fmt_clp_local(total)}</span>
      </div>
      {alerts_html}
      <table cellspacing="0" cellpadding="0" style="width:100%;margin:8px 0;">
        {row("👥 Personas", personas)}
        {row("📍 Ciudad origen", ciudad or ('<span style="color:#f87171">—</span>' if not ciudad else ""), urgent=not ciudad)}
        {row("📣 Cómo supieron", como or ('<span style="color:#f87171">—</span>' if not como else ""), urgent=not como)}
        {row("🙋 Atendió", quien or "")}
        {row("📦 Extras", extras_html) if extras_html else ""}
        {row("📞 Teléfono", telefono)}
        {row("📧 Email", email_c)}
        {row("📝 Observaciones", obs)}
      </table>
      <div style="border-top:1px solid #334155;padding-top:8px;margin-top:4px;">
        <p style="margin:0 0 4px;color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:1px;">PAGOS</p>
        {pagos_html}
        {f'<p style="margin:6px 0 0;color:#fbbf24;font-size:12px;font-weight:700;">💳 Saldo pendiente: {_fmt_clp_local(balance)}</p>' if balance > 0 else ""}
      </div>
    </div>"""


def send_yesterday_summary_email() -> Dict[str, Any]:
    """Send yesterday's booking summary to hotboatnotification@gmail.com at 09:00."""
    from datetime import date, timedelta
    from app.db.connection import get_connection

    out: Dict[str, Any] = {"sent": False, "reason": "", "count": 0}
    s = get_settings()
    api_key = (getattr(s, "resend_api_key", "") or "").strip()
    if not api_key:
        out["reason"] = "no_resend_key"
        return out

    yesterday = date.today() - timedelta(days=1)
    yesterday_str = yesterday.strftime("%d/%m/%Y")
    weekday_name = yesterday.strftime("%A")
    weekday_es = {"Monday":"Lunes","Tuesday":"Martes","Wednesday":"Miércoles",
                  "Thursday":"Jueves","Friday":"Viernes","Saturday":"Sábado","Sunday":"Domingo"}.get(weekday_name, weekday_name)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT nombre_cliente, email, telefono, fecha, hora, num_personas,
                          ingreso_total, status, extras_json, observaciones,
                          ciudad_origen, como_supieron, quien_atendio,
                          COALESCE(pagos,'[]'::jsonb),
                          COALESCE(flex_amount,0)
                   FROM all_appointments
                   WHERE fecha = %s AND status NOT IN ('cancelled','rejected')
                   ORDER BY hora ASC NULLS LAST""",
                (yesterday,),
            )
            cols = ["nombre_cliente","email","telefono","fecha","hora","num_personas",
                    "ingreso_total","status","extras_json","observaciones",
                    "ciudad_origen","como_supieron","quien_atendio","pagos","flex_amount"]
            bookings = [dict(zip(cols, r)) for r in cur.fetchall()]

    out["count"] = len(bookings)
    n_alerts = sum(
        1 for b in bookings
        if not b.get("ciudad_origen") or not b.get("como_supieron")
        or max(0.0, float(b.get("ingreso_total") or 0)
               + float(b.get("flex_amount") or 0)
               - sum(float(p.get("amount") or 0) for p in (b.get("pagos") or []) if isinstance(p, dict))) > 0
    )

    urgency_banner = ""
    if n_alerts > 0:
        urgency_banner = f"""
        <div style="background:rgba(239,68,68,.15);border:2px solid #ef4444;border-radius:12px;
                    padding:14px 20px;margin:0 0 20px;">
          <p style="margin:0;color:#f87171;font-size:14px;font-weight:700;">
            🚨 {n_alerts} reserva{'s' if n_alerts!=1 else ''} {'tienen' if n_alerts!=1 else 'tiene'} datos incompletos — completar hoy
          </p>
        </div>"""

    if bookings:
        cards = "".join(_build_booking_card_html(b) for b in bookings)
        total_rev = sum(float(b.get("ingreso_total") or 0) for b in bookings)
        total_pax = sum(int(b.get("num_personas") or 0) for b in bookings)
        stats = f"""
        <div style="display:flex;gap:12px;margin:0 0 16px;flex-wrap:wrap;">
          <div style="flex:1;min-width:100px;background:#1e293b;border-radius:10px;padding:12px 16px;text-align:center;">
            <div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:1px;">Reservas</div>
            <div style="color:#f8fafc;font-size:22px;font-weight:800;">{len(bookings)}</div>
          </div>
          <div style="flex:1;min-width:100px;background:#1e293b;border-radius:10px;padding:12px 16px;text-align:center;">
            <div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:1px;">Personas</div>
            <div style="color:#f8fafc;font-size:22px;font-weight:800;">{total_pax}</div>
          </div>
          <div style="flex:1;min-width:100px;background:#1e293b;border-radius:10px;padding:12px 16px;text-align:center;">
            <div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:1px;">Total</div>
            <div style="color:#10b981;font-size:20px;font-weight:800;">{_fmt_clp_local(total_rev)}</div>
          </div>
        </div>"""
        body_content = stats + urgency_banner + cards
    else:
        body_content = '<p style="color:#94a3b8;text-align:center;padding:32px 0;font-size:15px;">😴 Sin reservas el día anterior</p>'

    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Resumen {yesterday_str}</title></head>
<body style="margin:0;padding:0;background:#0b1120;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
<table width="100%" cellspacing="0" cellpadding="0" bgcolor="#0b1120">
<tr><td align="center" style="padding:28px 16px 40px;">
<table width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;">
  <tr><td style="background:#131c2e;border-radius:16px;overflow:hidden;padding:28px;">
    <h1 style="margin:0 0 4px;color:#f8fafc;font-size:20px;font-weight:800;">
      📋 Resumen {weekday_es} {yesterday_str}
    </h1>
    <p style="margin:0 0 20px;color:#64748b;font-size:13px;">Reservas del día anterior · HotBoat</p>
    {body_content}
    <p style="margin:24px 0 0;color:#475569;font-size:11px;text-align:center;">
      Enviado automáticamente por HotBoat · 09:00 Santiago
    </p>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""

    subject = f"📋 Ayer ({weekday_es} {yesterday_str}) — {len(bookings)} reserva{'s' if len(bookings)!=1 else ''}"
    if n_alerts > 0:
        subject = f"🚨 " + subject[2:] + f" · {n_alerts} con datos faltantes"

    from_addr = _get_from_addr(s)
    try:
        result = send_booking_html(
            to=_NOTIF_TO,
            subject=subject,
            html=html,
            from_address=from_addr,
            api_key=api_key,
        )
        out["sent"] = True
        out["resend_id"] = result.get("id") if isinstance(result, dict) else str(result)
        logger.info("yesterday_summary: sent %s bookings, %s alerts", len(bookings), n_alerts)
    except Exception as e:
        out["reason"] = str(e)
        logger.error("yesterday_summary send error: %s", e)
    return out


def send_weekly_summary_email() -> Dict[str, Any]:
    """Send this week's booking overview to hotboatnotification@gmail.com (sent on Mondays)."""
    from datetime import date, timedelta
    from app.db.connection import get_connection

    out: Dict[str, Any] = {"sent": False, "reason": "", "count": 0}
    s = get_settings()
    api_key = (getattr(s, "resend_api_key", "") or "").strip()
    if not api_key:
        out["reason"] = "no_resend_key"
        return out

    today = date.today()
    week_end   = today - timedelta(days=1)   # yesterday = last Sunday
    week_start = today - timedelta(days=7)   # last Monday

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT nombre_cliente, email, telefono, fecha, hora, num_personas,
                          ingreso_total, status, extras_json, observaciones,
                          ciudad_origen, como_supieron, quien_atendio,
                          COALESCE(pagos,'[]'::jsonb),
                          COALESCE(flex_amount,0)
                   FROM all_appointments
                   WHERE fecha BETWEEN %s AND %s
                     AND status NOT IN ('cancelled','rejected')
                   ORDER BY fecha ASC, hora ASC NULLS LAST""",
                (week_start, week_end),
            )
            cols = ["nombre_cliente","email","telefono","fecha","hora","num_personas",
                    "ingreso_total","status","extras_json","observaciones",
                    "ciudad_origen","como_supieron","quien_atendio","pagos","flex_amount"]
            bookings = [dict(zip(cols, r)) for r in cur.fetchall()]

    out["count"] = len(bookings)

    week_start_str = week_start.strftime("%d/%m")
    week_end_str   = week_end.strftime("%d/%m/%Y")

    if bookings:
        cards = "".join(_build_booking_card_html(b, is_weekly=True) for b in bookings)
        total_rev = sum(float(b.get("ingreso_total") or 0) for b in bookings)
        total_pax = sum(int(b.get("num_personas") or 0) for b in bookings)
        stats = f"""
        <div style="display:flex;gap:12px;margin:0 0 16px;flex-wrap:wrap;">
          <div style="flex:1;min-width:100px;background:#1e293b;border-radius:10px;padding:12px 16px;text-align:center;">
            <div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:1px;">Reservas</div>
            <div style="color:#f8fafc;font-size:22px;font-weight:800;">{len(bookings)}</div>
          </div>
          <div style="flex:1;min-width:100px;background:#1e293b;border-radius:10px;padding:12px 16px;text-align:center;">
            <div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:1px;">Personas</div>
            <div style="color:#f8fafc;font-size:22px;font-weight:800;">{total_pax}</div>
          </div>
          <div style="flex:1;min-width:100px;background:#1e293b;border-radius:10px;padding:12px 16px;text-align:center;">
            <div style="color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:1px;">Total semana</div>
            <div style="color:#10b981;font-size:20px;font-weight:800;">{_fmt_clp_local(total_rev)}</div>
          </div>
        </div>"""
        body_content = stats + cards
    else:
        body_content = '<p style="color:#94a3b8;text-align:center;padding:32px 0;font-size:15px;">📭 Sin reservas esta semana</p>'

    html = f"""<!DOCTYPE html><html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Semana {week_start_str}–{week_end_str}</title></head>
<body style="margin:0;padding:0;background:#0b1120;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Arial,sans-serif;">
<table width="100%" cellspacing="0" cellpadding="0" bgcolor="#0b1120">
<tr><td align="center" style="padding:28px 16px 40px;">
<table width="100%" cellspacing="0" cellpadding="0" style="max-width:600px;">
  <tr><td style="background:#131c2e;border-radius:16px;overflow:hidden;padding:28px;">
    <h1 style="margin:0 0 4px;color:#f8fafc;font-size:20px;font-weight:800;">
      📆 Semana {week_start_str} – {week_end_str}
    </h1>
    <p style="margin:0 0 20px;color:#64748b;font-size:13px;">Reservas de la semana · HotBoat</p>
    {body_content}
    <p style="margin:24px 0 0;color:#475569;font-size:11px;text-align:center;">
      Enviado automáticamente cada lunes · 09:00 Santiago
    </p>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""

    subject = f"📆 Semana {week_start_str}–{week_end_str} — {len(bookings)} reserva{'s' if len(bookings)!=1 else ''}"

    from_addr = _get_from_addr(s)
    try:
        result = send_booking_html(
            to=_NOTIF_TO,
            subject=subject,
            html=html,
            from_address=from_addr,
            api_key=api_key,
        )
        out["sent"] = True
        out["resend_id"] = result.get("id") if isinstance(result, dict) else str(result)
        logger.info("weekly_summary: sent %s bookings for week %s–%s", len(bookings), week_start_str, week_end_str)
    except Exception as e:
        out["reason"] = str(e)
        logger.error("weekly_summary send error: %s", e)
    return out
