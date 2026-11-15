"""Post-visit data-completeness check — sent ~1h after a booking ends (3h
after it starts, assuming a 2h experience), asking whether the operator
filled in the reservation's post-visit summary: payment/method, how many
people actually came, where they're from, how they heard about HotBoat,
and what type of group it was. These all live on the reservation's edit
modal in admin-bookings.html (fields: pagos, num_adultos/num_ninos,
ciudad_origen, como_supieron, categoria_clientes, quien_atendio) but nothing
reminds the operator to fill them in after the fact — this sweep does."""
import logging

logger = logging.getLogger(__name__)

ADMIN_NOTIFICATION_EMAIL = "hotboatnotification@gmail.com"


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
        trigger="post_visit_check",
    )
    if not result["sent"]:
        logger.warning("post_visit_check_email: send failed: %s", result["reason"])


def _fmt_date(d) -> str:
    if not d:
        return "-"
    try:
        parts = str(d).split("-")
        if len(parts) == 3:
            return f"{parts[2]}/{parts[1]}/{parts[0]}"
    except Exception:
        pass
    return str(d)


def _parse_pagos(raw) -> list:
    import json as _json
    if isinstance(raw, str):
        try:
            raw = _json.loads(raw)
        except Exception:
            return []
    return raw if isinstance(raw, list) else []


def _check_items(booking: dict) -> list:
    """Returns [{label, ok, detail}] — one row per thing the operator should
    fill in after the visit."""
    pagos = _parse_pagos(booking.get("pagos"))
    paid_total = sum(float(p.get("amount") or 0) for p in pagos)
    has_method = any((p.get("method") or "").strip() for p in pagos if float(p.get("amount") or 0) > 0)
    pago_ok = paid_total > 0 and has_method

    adultos = booking.get("num_adultos")
    ninos = booking.get("num_ninos")
    asistencia_ok = bool(adultos) or bool(ninos)

    ciudad_ok = bool((booking.get("ciudad_origen") or "").strip())
    como_supo_ok = bool((booking.get("como_supieron") or "").strip())
    categoria_ok = bool((booking.get("categoria_clientes") or "").strip())
    atendio_ok = bool((booking.get("quien_atendio") or "").strip())

    return [
        {"label": "Pago y método de pago", "ok": pago_ok,
         "detail": (f"${paid_total:,.0f} registrado" if paid_total > 0 else "sin pagos registrados").replace(",", ".")},
        {"label": "Nº de personas que vinieron", "ok": asistencia_ok,
         "detail": f"{adultos or 0} adultos, {ninos or 0} niños" if asistencia_ok else "no registrado"},
        {"label": "Ciudad de origen", "ok": ciudad_ok, "detail": booking.get("ciudad_origen") or "no registrado"},
        {"label": "Cómo supieron de HotBoat", "ok": como_supo_ok, "detail": booking.get("como_supieron") or "no registrado"},
        {"label": "Tipo de grupo", "ok": categoria_ok, "detail": booking.get("categoria_clientes") or "no registrado"},
        {"label": "Quién los atendió", "ok": atendio_ok, "detail": booking.get("quien_atendio") or "no registrado"},
    ]


def send_post_visit_check_notification(booking: dict) -> None:
    ref = booking.get("booking_ref") or "-"
    name = booking.get("customer_name") or "-"
    bdate = _fmt_date(booking.get("booking_date"))
    btime = str(booking.get("booking_time") or "")[:5]

    items = _check_items(booking)
    missing = [it for it in items if not it["ok"]]
    complete = not missing

    rows_html = "".join(
        f"""<tr>
          <td style="padding:8px 6px;border-bottom:1px solid #eee;font-size:14px">
            {'✅' if it['ok'] else '❌'} {it['label']}
          </td>
          <td style="padding:8px 6px;border-bottom:1px solid #eee;font-size:13px;color:{'#2e7d32' if it['ok'] else '#c62828'}">
            {it['detail']}
          </td>
        </tr>"""
        for it in items
    )

    status_color = "#2e7d32" if complete else "#c62828"
    status_bg = "#e8f5e9" if complete else "#ffebee"
    status_text = "✅ Resumen completo" if complete else f"⚠️ Faltan {len(missing)} de {len(items)} campos"

    subject = f"📋 Resumen post-reserva — {ref} ({'completo' if complete else f'{len(missing)} pendientes'})"
    html = f"""
<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8">
<style>
  body{{font-family:Arial,sans-serif;background:#f4f4f4;margin:0;padding:20px}}
  .card{{background:#fff;border-radius:12px;max-width:600px;margin:auto;padding:28px;box-shadow:0 2px 8px rgba(0,0,0,.1)}}
  h2{{color:#1a1a2e;margin:0 0 6px}}
  .sub{{color:#666;font-size:14px;margin-bottom:16px}}
  .status{{display:inline-block;background:{status_bg};color:{status_color};border-radius:20px;
           padding:5px 16px;font-size:13px;font-weight:700;margin-bottom:18px}}
  table{{width:100%;border-collapse:collapse}}
  th{{text-align:left;color:#999;font-size:11px;text-transform:uppercase;letter-spacing:.5px;padding:0 6px 8px}}
</style>
</head>
<body>
<div class="card">
  <h2>📋 Resumen post-reserva</h2>
  <div class="sub">{ref} · {name} · {bdate} {btime}</div>
  <div class="status">{status_text}</div>
  <table>
    <thead><tr><th>Campo</th><th>Valor</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
  <p style="color:#888;font-size:12px;margin-top:18px">HotBoat Chile · aviso automático 1 hora después de terminada la experiencia</p>
</div>
</body>
</html>
"""
    try:
        _send(ADMIN_NOTIFICATION_EMAIL, subject, html)
        logger.info("post_visit_check sent for %s (%d/%d missing)", ref, len(missing), len(items))
    except Exception as e:
        logger.error("send_post_visit_check_notification failed for %s: %s", ref, e)


def run_post_visit_check_sweep() -> dict:
    """Check for bookings that started ~3h ago (1h after a 2h experience ends)
    and send the post-visit data-completeness email. Runs every 10 min."""
    from app.booking.db import get_bookings_for_post_visit_check, mark_post_visit_check_notif_sent

    result = {"checked": 0, "sent": 0, "errors": 0}
    try:
        bookings = get_bookings_for_post_visit_check(window_minutes=20, target_minutes_ahead=180)
        result["checked"] = len(bookings)
        for b in bookings:
            ref = b.get("booking_ref", "")
            try:
                send_post_visit_check_notification(b)
                mark_post_visit_check_notif_sent(b["id"])
                result["sent"] += 1
            except Exception as e:
                logger.error("post_visit_check sweep for %s: %s", ref, e)
                result["errors"] += 1
    except Exception as e:
        logger.error("run_post_visit_check_sweep: %s", e)
    return result
