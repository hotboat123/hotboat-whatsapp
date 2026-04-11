"""Email notifications for T&C passenger signatures."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

ADMIN_NOTIFICATION_EMAIL = "hotboatnotification@gmail.com"


def _send(to: str, subject: str, html: str) -> None:
    from app.config import get_settings
    from app.email.resend_booking import send_booking_html

    settings = get_settings()
    api_key = (getattr(settings, "resend_api_key", "") or "").strip()
    if not api_key:
        logger.warning("signatures_email: RESEND_API_KEY not configured, skipping email")
        return

    from_addr = (
        getattr(settings, "resend_from_confirmations", "")
        or getattr(settings, "email_from", "")
        or "noreply@reservas.hotboat.cl"
    ).strip()

    send_booking_html(
        to=to,
        subject=subject,
        html=html,
        from_address=from_addr,
        api_key=api_key,
    )


def _fmt_date(d: Optional[str]) -> str:
    if not d:
        return "-"
    try:
        from datetime import date
        parts = str(d).split("-")
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
    except Exception:
        pass
    return str(d)


def notify_admin_new_signature(sig: dict, booking: dict) -> None:
    """Send a per-signature notification email to the admin."""
    name = sig.get("passenger_name") or "-"
    email = sig.get("passenger_email") or "-"
    phone = sig.get("passenger_phone") or "-"
    bday = _fmt_date(sig.get("passenger_birthday"))
    booking_ref = sig.get("booking_ref") or booking.get("booking_ref", "")
    booking_date = _fmt_date(str(booking.get("booking_date") or ""))
    booking_time = str(booking.get("booking_time") or "")[:5]
    num_people = booking.get("num_people") or "-"

    subject = f"✍️ Nueva firma T&C — {name} ({booking_ref})"
    html = f"""
<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8">
<style>
  body{{font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:20px}}
  .card{{background:#fff;border-radius:12px;max-width:520px;margin:auto;padding:28px;box-shadow:0 2px 8px rgba(0,0,0,.1)}}
  h2{{color:#1a1a2e;margin:0 0 18px}}
  table{{width:100%;border-collapse:collapse}}
  td{{padding:8px 6px;border-bottom:1px solid #eee;font-size:14px}}
  td:first-child{{color:#666;width:40%}}
  .badge{{display:inline-block;background:#e8f5e9;color:#2e7d32;border-radius:20px;
          padding:3px 12px;font-size:12px;font-weight:700}}
  .ref{{color:#888;font-size:12px;margin-top:16px}}
</style>
</head>
<body>
<div class="card">
  <h2>✍️ Firma de Términos y Condiciones</h2>
  <p>Un pasajero firmó los T&amp;C para la reserva <strong>{booking_ref}</strong>.</p>
  <table>
    <tr><td>Pasajero</td><td><strong>{name}</strong></td></tr>
    <tr><td>Email</td><td>{email}</td></tr>
    <tr><td>Teléfono</td><td>{phone}</td></tr>
    <tr><td>Fecha de nacimiento</td><td>{bday}</td></tr>
    <tr><td>Acepta T&amp;C</td><td><span class="badge">✔ Sí</span></td></tr>
  </table>
  <hr style="margin:18px 0;border:none;border-top:1px solid #eee">
  <table>
    <tr><td>Fecha reserva</td><td>{booking_date} {booking_time}</td></tr>
    <tr><td>Personas en reserva</td><td>{num_people}</td></tr>
  </table>
  <p class="ref">Reserva: {booking_ref} · HotBoat Chile</p>
</div>
</body>
</html>
"""
    try:
        _send(ADMIN_NOTIFICATION_EMAIL, subject, html)
        logger.info("notify_admin_new_signature sent for %s / sig_id=%s", booking_ref, sig.get("id"))
    except Exception as e:
        logger.error("notify_admin_new_signature failed: %s", e)


def send_booking_signature_summary(booking_ref: str, booking: dict, signatures: list) -> None:
    """
    Send a summary email to the admin with all passengers who signed for a booking.
    Called by the daily sweep just before each booking.
    """
    num_people = booking.get("num_people") or "?"
    booking_date = _fmt_date(str(booking.get("booking_date") or ""))
    booking_time = str(booking.get("booking_time") or "")[:5]
    customer_name = booking.get("customer_name") or "-"
    signed = len(signatures)

    rows_html = "".join(
        f"""<tr>
          <td>{i+1}</td>
          <td><strong>{s.get('passenger_name','-')}</strong></td>
          <td>{s.get('passenger_email','-') or '-'}</td>
          <td>{s.get('passenger_phone','-') or '-'}</td>
          <td>{_fmt_date(s.get('passenger_birthday'))}</td>
        </tr>"""
        for i, s in enumerate(signatures)
    )

    subject = f"📋 Firmas T&C hoy — {booking_ref} ({signed}/{num_people} firmaron)"
    html = f"""
<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8">
<style>
  body{{font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:20px}}
  .card{{background:#fff;border-radius:12px;max-width:640px;margin:auto;padding:28px;box-shadow:0 2px 8px rgba(0,0,0,.1)}}
  h2{{color:#1a1a2e;margin:0 0 6px}}
  .sub{{color:#666;font-size:14px;margin-bottom:20px}}
  table{{width:100%;border-collapse:collapse;font-size:13px}}
  th{{background:#f5f5f5;padding:8px 6px;text-align:left;color:#444;border-bottom:2px solid #ddd}}
  td{{padding:8px 6px;border-bottom:1px solid #eee}}
  .count{{display:inline-block;background:{'#e8f5e9' if signed>=1 else '#fff3e0'};
          color:{'#2e7d32' if signed>=1 else '#e65100'};border-radius:20px;
          padding:4px 16px;font-size:13px;font-weight:700;margin-bottom:16px}}
</style>
</head>
<body>
<div class="card">
  <h2>📋 Resumen de Firmas T&amp;C</h2>
  <div class="sub">Reserva <strong>{booking_ref}</strong> · {customer_name} · {booking_date} {booking_time}</div>
  <div class="count">{signed} de {num_people} personas firmaron</div>
  <table>
    <thead>
      <tr>
        <th>#</th><th>Nombre</th><th>Email</th><th>Teléfono</th><th>Nacimiento</th>
      </tr>
    </thead>
    <tbody>
      {rows_html if rows_html else '<tr><td colspan="5" style="color:#999;text-align:center">Nadie firmó aún</td></tr>'}
    </tbody>
  </table>
  <p style="color:#888;font-size:12px;margin-top:18px">HotBoat Chile · resumen automático del día</p>
</div>
</body>
</html>
"""
    try:
        _send(ADMIN_NOTIFICATION_EMAIL, subject, html)
        logger.info("send_booking_signature_summary sent for %s (%d sigs)", booking_ref, signed)
    except Exception as e:
        logger.error("send_booking_signature_summary failed for %s: %s", booking_ref, e)


def _parse_extras(raw: object) -> list:
    """Parse extras JSON (list of {name, price, quantity}) safely."""
    import json as _json
    if not raw:
        return []
    if isinstance(raw, list):
        return raw
    try:
        parsed = _json.loads(str(raw))
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def send_pre_booking_notification(booking: dict, prev_bookings: int = 0) -> None:
    """
    Send a 1-hour pre-booking admin notification to hotboatnotification@gmail.com.
    Called by the scheduler when a booking is ~60 min away.
    prev_bookings: number of prior confirmed bookings by this customer.
    """
    ref     = booking.get("booking_ref") or "-"
    name    = booking.get("customer_name") or "-"
    phone   = booking.get("customer_phone") or "-"
    email_  = booking.get("customer_email") or "-"
    bdate   = _fmt_date(str(booking.get("booking_date") or ""))
    btime   = str(booking.get("booking_time") or "")[:5]
    people  = booking.get("num_people") or "-"
    total   = booking.get("total_price") or "-"
    status  = booking.get("status") or "-"
    source  = booking.get("source") or "-"
    notes   = (booking.get("notes") or "").strip()

    try:
        from app.booking.booking_email import _fmt_clp
        total_fmt = _fmt_clp(total)
    except Exception:
        total_fmt = str(total)

    # ── Returning customer badge ──────────────────────────────────────────────
    if prev_bookings == 0:
        returning_html = '<span style="display:inline-block;background:#7c3aed;color:#fff;border-radius:20px;padding:2px 12px;font-size:12px;font-weight:700">🆕 Primera visita</span>'
    else:
        returning_html = f'<span style="display:inline-block;background:#0284c7;color:#fff;border-radius:20px;padding:2px 12px;font-size:12px;font-weight:700">🔁 Regresa · {prev_bookings} visita{"s" if prev_bookings != 1 else ""} anterior{"es" if prev_bookings != 1 else ""}</span>'

    # ── Extras rows ───────────────────────────────────────────────────────────
    extras_list = _parse_extras(booking.get("extras"))
    extras_total = booking.get("extras_total") or 0
    if extras_list:
        try:
            from app.booking.booking_email import _fmt_clp
            extra_rows = "".join(
                f'<tr style="border-top:1px solid #1e2d45;">'
                f'<td style="padding:8px 0;color:#94a3b8;font-size:13px;">'
                f'{"x" + str(e.get("quantity","")) + " " if (e.get("quantity") or 1) > 1 else ""}'
                f'{e.get("name","")}</td>'
                f'<td style="padding:8px 0;text-align:right;color:#e2e8f0;font-size:13px;">'
                f'{_fmt_clp((e.get("price") or 0) * (e.get("quantity") or 1))}</td>'
                f'</tr>'
                for e in extras_list
            )
            extras_section = f"""
    <div style="margin-top:18px;padding-top:14px;border-top:2px solid #1e2d45;">
      <div style="color:#64748b;font-size:11px;text-transform:uppercase;letter-spacing:.8px;font-weight:600;margin-bottom:4px;">🎁 Extras</div>
      <table width="100%" cellspacing="0" cellpadding="0">{extra_rows}
        <tr><td style="padding:10px 0 0;color:#64748b;font-size:12px;">Total extras</td>
            <td style="padding:10px 0 0;text-align:right;color:#e8b86d;font-weight:700;">{_fmt_clp(extras_total)}</td></tr>
      </table>
    </div>"""
        except Exception:
            extras_section = ""
    else:
        extras_section = '<div style="margin-top:12px;color:#475569;font-size:13px;">Sin extras</div>'

    # ── Notes ─────────────────────────────────────────────────────────────────
    notes_section = ""
    if notes:
        notes_section = f'<div style="margin-top:14px;padding:10px 14px;background:rgba(251,191,36,.07);border-radius:8px;border-left:3px solid #f59e0b;color:#fde68a;font-size:13px;"><strong>📝 Notas:</strong> {notes}</div>'

    subject = f"⏰ En 1 hora — {ref} · {name} ({people} pax)"
    html = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8">
<style>
  body{{font-family:Arial,sans-serif;background:#0b1120;margin:0;padding:24px}}
  .card{{background:#131c2e;border-radius:16px;max-width:560px;margin:auto;
         overflow:hidden;box-shadow:0 8px 32px rgba(0,0,0,.5)}}
  .bar{{height:5px;background:linear-gradient(90deg,#f59e0b,#ef4444)}}
  .header{{padding:26px 28px 18px;border-bottom:1px solid #1e2d45}}
  .header h2{{margin:0;color:#f8fafc;font-size:22px;font-weight:800}}
  .header p{{margin:6px 0 0;color:#94a3b8;font-size:14px}}
  .body{{padding:22px 28px 26px}}
  table.main{{width:100%;border-collapse:collapse}}
  table.main td{{padding:10px 0;border-bottom:1px solid #1e2d45;font-size:14px;color:#cbd5e1}}
  table.main td:first-child{{color:#64748b;width:40%;font-size:11px;text-transform:uppercase;
                  letter-spacing:.8px;font-weight:600}}
  .footer{{padding:14px 28px 20px;text-align:center;color:#475569;font-size:12px;
           border-top:1px solid #1e2d45}}
</style>
</head>
<body>
<div class="card">
  <div class="bar"></div>
  <div class="header">
    <h2>⏰ Reserva en 1 hora</h2>
    <p>Notificación automática · HotBoat Chile</p>
  </div>
  <div class="body">
    <table class="main">
      <tr><td>Referencia</td>
          <td style="color:#e8b86d;font-family:monospace;font-weight:700">{ref}</td></tr>
      <tr><td>Cliente</td>
          <td style="color:#f1f5f9;font-weight:700;font-size:15px">{name}</td></tr>
      <tr><td>Historial</td>
          <td>{returning_html}</td></tr>
      <tr><td>Teléfono</td>
          <td><a href="https://wa.me/{phone.replace(' ','').replace('+','')}" style="color:#4ade80;text-decoration:none;">{phone}</a></td></tr>
      <tr><td>Email</td>
          <td style="color:#93c5fd">{email_}</td></tr>
      <tr><td>📅 Fecha</td>
          <td style="color:#e2e8f0;font-weight:600">{bdate}</td></tr>
      <tr><td>⏰ Hora</td>
          <td style="color:#fbbf24;font-weight:800;font-size:18px">{btime} hrs</td></tr>
      <tr><td>👥 Personas</td>
          <td style="color:#e2e8f0;font-weight:600;font-size:16px">{people}</td></tr>
      <tr><td>💰 Total</td>
          <td style="color:#10b981;font-weight:700;font-size:16px">{total_fmt}</td></tr>
      <tr><td>Estado</td>
          <td><span style="display:inline-block;background:#d97706;color:#fff;border-radius:20px;
                           padding:2px 12px;font-size:12px;font-weight:700">{status}</span></td></tr>
      <tr><td>Fuente</td>
          <td style="color:#64748b">{source}</td></tr>
    </table>
    {extras_section}
    {notes_section}
  </div>
  <div class="footer">HotBoat Chile · aviso automático 1 hora antes</div>
</div>
</body>
</html>"""
    try:
        _send(ADMIN_NOTIFICATION_EMAIL, subject, html)
        logger.info("pre_booking_notification sent for %s (%s %s, prev=%d)", ref, bdate, btime, prev_bookings)
    except Exception as e:
        logger.error("pre_booking_notification failed for %s: %s", ref, e)


def run_pre_booking_notif_sweep() -> dict:
    """
    Check for bookings starting in ~60 min and send admin notification if not yet sent.
    Runs every 10 minutes from the scheduler.
    """
    from app.booking.db import get_bookings_starting_soon, mark_pre_booking_notif_sent, count_previous_bookings

    result = {"checked": 0, "sent": 0, "errors": 0}
    try:
        bookings = get_bookings_starting_soon(window_minutes=20, target_minutes_ahead=60)
        result["checked"] = len(bookings)
        for b in bookings:
            ref = b.get("booking_ref", "")
            try:
                prev = count_previous_bookings(
                    customer_email=b.get("customer_email") or "",
                    customer_phone=b.get("customer_phone") or "",
                    exclude_ref=ref,
                )
                send_pre_booking_notification(b, prev_bookings=prev)
                mark_pre_booking_notif_sent(ref)
                result["sent"] += 1
            except Exception as e:
                logger.error("pre_booking sweep for %s: %s", ref, e)
                result["errors"] += 1
    except Exception as e:
        logger.error("run_pre_booking_notif_sweep: %s", e)
    return result


def run_daily_signature_summary_sweep() -> dict:
    """
    Send a summary of T&C signatures for every booking happening today.
    Runs once per day from the scheduler.
    """
    from datetime import date
    from app.booking.db import get_bookings_with_signatures_for_date, get_signatures_by_booking_ref, get_booking_by_ref

    today = date.today()
    result = {"checked": 0, "sent": 0, "errors": 0}
    try:
        bookings = get_bookings_with_signatures_for_date(today)
        result["checked"] = len(bookings)
        for b in bookings:
            ref = b["booking_ref"]
            try:
                sigs = get_signatures_by_booking_ref(ref)
                booking_detail = get_booking_by_ref(ref) or b
                send_booking_signature_summary(ref, booking_detail, sigs)
                result["sent"] += 1
            except Exception as e:
                logger.error("sweep sig summary for %s: %s", ref, e)
                result["errors"] += 1
    except Exception as e:
        logger.error("run_daily_signature_summary_sweep: %s", e)
    return result
