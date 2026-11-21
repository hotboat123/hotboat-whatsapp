"""Daily "conversations about to close" digest — sent ~21:00 Santiago time.

Pulls every WhatsApp conversation that had activity today, drops anyone who
already has a confirmed booking or was manually tagged as a customer/bad
lead in whatsapp_leads, and asks the bot's own Groq model to read each
remaining transcript and flag the ones that show real booking intent but
went cold (unanswered, a question left hanging, the customer just stopped
replying) — so the operator can jump back in before the conversation is
gone for good.

There is no stored lead-score anywhere in the schema — whatsapp_leads.
lead_status is a manual 4-value operator tag, not an automatic signal —
so this is the first thing that actually reads the day's transcripts to
judge intent, rather than just time-since-last-message (see webhook.py's
run_unanswered_alert_scheduler, which flags *any* unanswered message,
not just promising ones)."""
import json
import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

ADMIN_NOTIFICATION_EMAIL = "hotboatnotification@gmail.com"
CHILE_TZ = ZoneInfo("America/Santiago")
UTC_TZ = ZoneInfo("UTC")

# whatsapp_leads.lead_status values that mean "not going cold" — already
# converted, or already judged not worth chasing.
_EXCLUDED_LEAD_STATUSES = {"customer", "bad_lead"}


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
        trigger="whatsapp_daily_digest",
    )
    if not result["sent"]:
        logger.warning("daily_digest: send failed: %s", result["reason"])


def _today_conversations() -> dict:
    """Today's (Santiago calendar day) whatsapp_conversations rows, grouped
    by phone_number, with each conversation's lead_status attached.
    created_at is stored as a naive UTC timestamp (confirmed against NOW()),
    so the Santiago midnight boundary is converted to UTC before filtering."""
    from app.db.connection import get_connection

    midnight_cl = datetime.now(CHILE_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    midnight_utc_naive = midnight_cl.astimezone(UTC_TZ).replace(tzinfo=None)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT phone_number, customer_name, message_text, response_text,
                       direction, created_at
                FROM whatsapp_conversations
                WHERE created_at >= %s
                ORDER BY phone_number, created_at
            """, (midnight_utc_naive,))
            rows = cur.fetchall()

            cur.execute("SELECT phone_number, lead_status FROM whatsapp_leads")
            lead_status_by_phone = {r[0]: r[1] for r in cur.fetchall()}

    conversations: dict = {}
    for phone, name, msg, resp, direction, created_at in rows:
        c = conversations.setdefault(phone, {"phone": phone, "name": None, "turns": [], "last_at": created_at})
        if name:
            c["name"] = name
        c["last_at"] = created_at
        if direction == "incoming" and msg:
            c["turns"].append(("cliente", msg))
        if resp:
            c["turns"].append(("bot", resp))

    for phone, c in conversations.items():
        c["lead_status"] = lead_status_by_phone.get(phone)
    return conversations


def _phones_with_confirmed_booking(phones: list) -> set:
    """Phones (matched on the trailing 9 digits, to absorb +56/leading-0
    formatting differences) that already have a non-cancelled, non-pending
    booking — these already closed, not going cold."""
    from app.db.connection import get_connection

    if not phones:
        return set()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT DISTINCT regexp_replace(telefono, '[^0-9]', '', 'g')
                FROM all_appointments
                WHERE status NOT IN ('cancelled', 'cancelada', 'solicitud', 'pending_payment')
            """)
            booked_suffixes = {d[-9:] for (d,) in cur.fetchall() if d and len(d) >= 6}

    result = set()
    for p in phones:
        digits = re.sub(r"\D", "", p or "")
        if len(digits) >= 6 and digits[-9:] in booked_suffixes:
            result.add(p)
    return result


_PROMPT_INSTRUCTIONS = (
    "Eres el asistente de un operador de tours en bote (HotBoat) que no quiere dejar pasar ventas. "
    "Abajo hay transcripciones de conversaciones de WhatsApp de HOY con clientes que todavía NO reservaron "
    "(ya se excluyeron quienes ya reservaron o fueron marcados como mal lead). "
    "Identifica cuáles muestran intención real de reservar — preguntaron fecha/hora, precio, disponibilidad, "
    "pidieron el link de pago, dijeron que querían ir — pero la conversación quedó sin cerrar: sin responder, "
    "con una pregunta pendiente, o el cliente dejó de escribir antes de confirmar. "
    "Ignora saludos genéricos, preguntas ya resueltas sin intención de compra, spam, o clientes que dijeron "
    "explícitamente que no les interesa.\n\n"
    "Responde SOLO con JSON (sin texto extra, sin markdown): una lista de objetos "
    '{"phone": "...", "reason": "motivo breve en español, 1 frase", "urgency": "alta"|"media"}. '
    "Si ninguna conversación aplica, responde [].\n\n"
)

# Groq's openai/gpt-oss-120b on-demand tier caps at 8000 tokens/minute
# (prompt + completion combined) — found 2026-11-20 hitting a 413 "Request
# too large" with 30 same-day conversations in one call (~9.3k tokens).
# Truncating each conversation and splitting into token-budgeted chunks,
# paced a minute apart, keeps every single request under that ceiling.
_MAX_TURNS_PER_CONVERSATION = 8
_MAX_CHARS_PER_MESSAGE = 220
_MAX_PROMPT_TOKENS_PER_CHUNK = 4500  # leaves headroom for completion tokens
_CHARS_PER_TOKEN = 3.5  # rough heuristic for Spanish text


def _estimate_tokens(text: str) -> int:
    return int(len(text) / _CHARS_PER_TOKEN)


def _conversation_block(c: dict) -> str:
    lines = [
        f"[{who}] {text[:_MAX_CHARS_PER_MESSAGE]}"
        for who, text in c["turns"][-_MAX_TURNS_PER_CONVERSATION:]
    ]
    return f"### Teléfono {c['phone']} ({c['name'] or 'sin nombre'})\n" + "\n".join(lines)


def _chunk_conversations(conversations: list) -> list:
    """Groups conversation blocks so each chunk's estimated prompt tokens
    stay under _MAX_PROMPT_TOKENS_PER_CHUNK."""
    base_tokens = _estimate_tokens(_PROMPT_INSTRUCTIONS)
    chunks, current, current_tokens = [], [], base_tokens
    for c in conversations:
        block = _conversation_block(c)
        block_tokens = _estimate_tokens(block)
        if current and current_tokens + block_tokens > _MAX_PROMPT_TOKENS_PER_CHUNK:
            chunks.append(current)
            current, current_tokens = [], base_tokens
        current.append(block)
        current_tokens += block_tokens
    if current:
        chunks.append(current)
    return chunks


def _classify_chunk(client, blocks: list) -> list:
    prompt = _PROMPT_INSTRUCTIONS + "\n\n".join(blocks)
    resp = client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
    )
    text = (resp.choices[0].message.content or "[]").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    parsed = json.loads(text)
    return parsed if isinstance(parsed, list) else []


def _classify_with_llm(conversations: list) -> list:
    """Ask the bot's own Groq model which of today's still-open
    conversations look close to closing. Returns [{phone, reason, urgency}].
    Splits into token-budgeted chunks (see constants above), pacing calls a
    minute apart to stay under Groq's per-minute token cap. A chunk that
    still fails is skipped — never blocks the rest of the digest."""
    import time
    from openai import OpenAI
    from app.config import get_settings

    settings = get_settings()
    client = OpenAI(api_key=settings.groq_api_key, base_url="https://api.groq.com/openai/v1")

    chunks = _chunk_conversations(conversations)
    results = []
    for i, chunk in enumerate(chunks):
        if i > 0:
            time.sleep(61)  # stay under the per-minute token cap between chunks
        try:
            results.extend(_classify_chunk(client, chunk))
        except Exception as e:
            logger.error("daily_digest: LLM classification failed for chunk %d/%d: %s", i + 1, len(chunks), e)
    return results


def _wa_link(phone: str) -> str:
    digits = (phone or "").replace("+", "").replace(" ", "").replace("-", "")
    return f"https://wa.me/{digits}"


def _popeye_link(phone: str) -> str:
    import urllib.parse
    digits = (phone or "").replace("+", "").replace(" ", "").replace("-", "")
    return f"https://whatsapp.hotboat.cl/?phone={urllib.parse.quote(digits)}"


def _digest_html(items: list, total_reviewed: int) -> str:
    if items:
        rows = "".join(f"""
    <div style="border:1px solid #eee;border-radius:10px;padding:14px 16px;margin-bottom:12px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <strong style="font-size:15px">{it.get('name') or 'Sin nombre'}</strong>
        <span style="background:{'#ffebee' if it.get('urgency') == 'alta' else '#fff3e0'};
                     color:{'#c62828' if it.get('urgency') == 'alta' else '#e65100'};
                     border-radius:14px;padding:3px 10px;font-size:11px;font-weight:700;text-transform:uppercase">
          {'🔥 alta' if it.get('urgency') == 'alta' else '🟡 media'}
        </span>
      </div>
      <div style="color:#444;font-size:14px;margin-bottom:10px">{it.get('reason') or '-'}</div>
      <a href="{_popeye_link(it.get('phone'))}" style="display:inline-block;margin-right:8px;background:#25D366;color:#fff;
         text-decoration:none;padding:8px 14px;border-radius:8px;font-size:13px;font-weight:700">🦜 Abrir en Popeye</a>
      <a href="{_wa_link(it.get('phone'))}" style="display:inline-block;background:#128C7E;color:#fff;text-decoration:none;
         padding:8px 14px;border-radius:8px;font-size:13px;font-weight:700">💬 Abrir en mi WhatsApp</a>
    </div>""" for it in items)
        status_bg, status_color = "#ffebee", "#c62828"
        status_text = f"🔥 {len(items)} por retomar"
    else:
        rows = '<p style="color:#666;font-size:14px">Ninguna conversación de hoy parece estar cerca de cerrar y sin responder — nada urgente que retomar.</p>'
        status_bg, status_color = "#e8f5e9", "#2e7d32"
        status_text = "✅ Nada urgente"

    return f"""
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
</style>
</head>
<body>
<div class="card">
  <h2>📲 Resumen WhatsApp del día</h2>
  <div class="sub">{total_reviewed} conversación(es) abiertas sin reserva revisadas hoy</div>
  <div class="status">{status_text}</div>
  {rows}
  <p style="color:#888;font-size:12px;margin-top:18px">HotBoat Chile · aviso automático 21:00 — conversaciones del día sin reserva que parecen cerca de cerrar</p>
</div>
</body>
</html>
"""


def run_whatsapp_daily_digest() -> dict:
    """Build and send the 21:00 Santiago digest. Runs once a day; always
    sends an email (even with zero flagged conversations) so the operator
    knows the check ran."""
    result = {"reviewed": 0, "flagged": 0}
    try:
        conversations = _today_conversations()
        open_phones = [
            p for p, c in conversations.items()
            if c.get("lead_status") not in _EXCLUDED_LEAD_STATUSES and c["turns"]
        ]
        booked = _phones_with_confirmed_booking(open_phones)
        candidates = [conversations[p] for p in open_phones if p not in booked]
        result["reviewed"] = len(candidates)

        items = []
        if candidates:
            flagged = _classify_with_llm(candidates)
            by_phone = {c["phone"]: c for c in candidates}
            for f in flagged:
                c = by_phone.get(f.get("phone"))
                if not c:
                    continue
                items.append({**f, "name": c["name"]})
        result["flagged"] = len(items)

        subject = f"📲 WhatsApp 21:00 — {len(items)} por retomar" if items else "📲 WhatsApp 21:00 — nada urgente"
        _send(ADMIN_NOTIFICATION_EMAIL, subject, _digest_html(items, result["reviewed"]))
        logger.info("whatsapp_daily_digest sent: %s", result)
    except Exception as e:
        logger.error("run_whatsapp_daily_digest failed: %s", e)
    return result
