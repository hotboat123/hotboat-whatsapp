"""Tracks token/usage consumption per AI provider+model+call type.

Every provider's API response already carries a usage figure — Groq/OpenAI-
compatible chat completions return response.usage.{prompt,completion,total}
_tokens, Gemini's raw REST response carries usageMetadata.{...}TokenCount,
and Whisper's verbose_json transcription carries .duration (seconds, since
Whisper is billed by audio length, not tokens). Until now every call site
read the .content/.text and silently discarded that usage data. This module
gives them a single place to record it (log_usage, called right after each
call) so the admin panel can show how close each free-tier quota is before
it actually breaks the bot during a busy period (see the "Uso de IA" card
in the Chatbot admin tab).

Phase 1 is visibility only: an operator-entered daily limit per
(provider, model, call_type) — stored via operator_settings, since the
actual free-tier limits are set by each provider and change over time, so
hard-coding them here would silently go stale. No automatic provider
switching; that's a deliberate later step once real usage numbers exist.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

_LIMITS_SETTINGS_KEY = "ai_usage_limits"


def _get_conn():
    from app.db.connection import get_connection
    return get_connection()


def _ensure_tables():
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS ai_usage_log (
                        id                 SERIAL PRIMARY KEY,
                        created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        provider           TEXT NOT NULL,
                        model              TEXT NOT NULL,
                        call_type          TEXT NOT NULL,
                        prompt_tokens      INT,
                        completion_tokens  INT,
                        total_tokens       INT,
                        audio_seconds      NUMERIC
                    )
                """)
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS ai_usage_log_created_at_idx ON ai_usage_log (created_at)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS ai_usage_log_provider_idx ON ai_usage_log (provider, model, call_type)"
                )
                conn.commit()
        logger.info("✅ ai_usage_log table ready")
    except Exception as e:
        logger.warning(f"ai_usage_log table setup skipped: {e}")


def log_usage(
    provider: str,
    model: str,
    call_type: str,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    audio_seconds: Optional[float] = None,
) -> None:
    """Best-effort usage record — never raises, so a logging/DB hiccup can
    never break the AI call it's describing. Call this right after reading
    a response's usage data, from every provider call site."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO ai_usage_log "
                    "(provider, model, call_type, prompt_tokens, completion_tokens, total_tokens, audio_seconds) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (provider, model, call_type, prompt_tokens, completion_tokens, total_tokens, audio_seconds),
                )
            conn.commit()
    except Exception as e:
        logger.warning(f"ai_usage log_usage failed (non-fatal): {e}")
        return
    _check_and_alert_usage_threshold(provider, model, call_type)


_USAGE_ALERT_THRESHOLD = 0.5  # owner asked for a heads-up at 50% of the configured daily limit


def _check_and_alert_usage_threshold(provider: str, model: str, call_type: str) -> None:
    """Email the owner once per calendar day the first time this
    (provider, model, call_type) crosses _USAGE_ALERT_THRESHOLD of its
    operator-entered daily limit (same limits as get_usage_limits(), set
    from the "Uso de IA" admin card). A dedup flag in hotboat_settings,
    keyed by today's date, is what keeps a busy afternoon from sending one
    email per call once past the threshold — never raises, same
    best-effort contract as log_usage() itself."""
    try:
        key = f"{provider}:{model}:{call_type}"
        limit_cfg = get_usage_limits().get(key)
        if not limit_cfg:
            return
        tokens_limit = limit_cfg.get("daily_tokens")
        seconds_limit = limit_cfg.get("daily_seconds")
        requests_limit = limit_cfg.get("daily_requests")
        if not tokens_limit and not seconds_limit and not requests_limit:
            return

        from app.booking.operator_settings import get_setting, set_setting
        from datetime import date

        dedup_key = f"ai_usage_alert_50pct:{key}:{date.today().isoformat()}"
        if get_setting(dedup_key, ""):
            return  # already alerted today for this exact model

        with _get_conn() as conn:
            with conn.cursor() as cur:
                if tokens_limit:
                    cur.execute(
                        "SELECT COALESCE(SUM(total_tokens),0) FROM ai_usage_log "
                        "WHERE provider=%s AND model=%s AND call_type=%s "
                        "AND created_at >= date_trunc('day', NOW())",
                        (provider, model, call_type),
                    )
                    used = cur.fetchone()[0]
                    pct = used / tokens_limit if tokens_limit else 0
                    usage_line = f"{used:,} / {tokens_limit:,} tokens".replace(",", ".")
                elif seconds_limit:
                    cur.execute(
                        "SELECT COALESCE(SUM(audio_seconds),0) FROM ai_usage_log "
                        "WHERE provider=%s AND model=%s AND call_type=%s "
                        "AND created_at >= date_trunc('day', NOW())",
                        (provider, model, call_type),
                    )
                    used = float(cur.fetchone()[0])
                    pct = used / seconds_limit if seconds_limit else 0
                    usage_line = f"{used:,.0f} / {seconds_limit:,.0f} segundos".replace(",", ".")
                else:
                    cur.execute(
                        "SELECT COUNT(*) FROM ai_usage_log "
                        "WHERE provider=%s AND model=%s AND call_type=%s "
                        "AND created_at >= date_trunc('day', NOW())",
                        (provider, model, call_type),
                    )
                    used = cur.fetchone()[0]
                    pct = used / requests_limit if requests_limit else 0
                    usage_line = f"{used:,} / {requests_limit:,} llamadas".replace(",", ".")

        if pct < _USAGE_ALERT_THRESHOLD:
            return

        set_setting(dedup_key, "1")
        _send_usage_threshold_email(provider, model, call_type, pct, usage_line)
    except Exception as e:
        logger.warning(f"ai_usage 50% threshold check failed (non-fatal): {e}")


def _send_usage_threshold_email(provider: str, model: str, call_type: str, pct: float, usage_line: str) -> None:
    try:
        from app.config import get_settings
        from app.email.send_email import send_email

        settings = get_settings()
        from_addr = (
            getattr(settings, "resend_from_confirmations", "")
            or getattr(settings, "email_from", "")
            or "noreply@reservas.hotboat.cl"
        ).strip()
        pct_display = round(pct * 100)
        subject = f"⚠️ {provider}/{model} llegó al {pct_display}% de su cuota diaria"
        html = (
            f"<p><strong>{provider} — {model}</strong> ({call_type}) lleva <strong>{usage_line}</strong> "
            f"hoy — el {pct_display}% del límite diario que configuraste en el panel.</p>"
            f"<p>Revisa el panel admin → Chatbot → \"📊 Uso de IA (tokens)\" para más detalle, "
            f"o ajusta el reparto de pesos entre variantes si quieres bajarle tráfico a este modelo.</p>"
        )
        result = send_email(
            to="hotboatnotification@gmail.com",
            subject=subject,
            html=html,
            from_address=from_addr,
            trigger="ai_usage_threshold",
        )
        if not result.get("sent"):
            logger.warning("ai_usage threshold email failed: %s", result.get("reason"))
    except Exception as e:
        logger.warning(f"ai_usage threshold email failed (non-fatal): {e}")


def get_usage_summary(days: int = 30) -> list:
    """Aggregate usage grouped by (provider, model, call_type): calls/tokens/
    audio-seconds for today and for the trailing `days` days. Feeds the
    admin 'Uso de IA' card."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        provider, model, call_type,
                        COUNT(*) FILTER (WHERE created_at >= date_trunc('day', NOW())) AS calls_today,
                        COALESCE(SUM(total_tokens) FILTER (WHERE created_at >= date_trunc('day', NOW())), 0) AS tokens_today,
                        COALESCE(SUM(audio_seconds) FILTER (WHERE created_at >= date_trunc('day', NOW())), 0) AS audio_seconds_today,
                        COUNT(*) FILTER (WHERE created_at >= NOW() - (%s || ' days')::interval) AS calls_period,
                        COALESCE(SUM(total_tokens) FILTER (WHERE created_at >= NOW() - (%s || ' days')::interval), 0) AS tokens_period,
                        COALESCE(SUM(audio_seconds) FILTER (WHERE created_at >= NOW() - (%s || ' days')::interval), 0) AS audio_seconds_period
                    FROM ai_usage_log
                    GROUP BY provider, model, call_type
                    ORDER BY provider, model, call_type
                    """,
                    (days, days, days),
                )
                rows = cur.fetchall()
        return [
            {
                "provider": r[0], "model": r[1], "call_type": r[2],
                "calls_today": r[3], "tokens_today": int(r[4]), "audio_seconds_today": float(r[5]),
                "calls_period": r[6], "tokens_period": int(r[7]), "audio_seconds_period": float(r[8]),
            }
            for r in rows
        ]
    except Exception as e:
        logger.warning(f"ai_usage get_usage_summary failed: {e}")
        return []


def get_usage_limits() -> dict:
    """{"<provider>:<model>:<call_type>": {"daily_tokens": N} | {"daily_seconds": N}}
    — operator-entered free-tier daily limits, keyed per (provider, model,
    call_type) since each has its own quota and unit (tokens for chat,
    seconds of audio for Whisper transcription)."""
    import json
    from app.booking.operator_settings import get_setting
    raw = get_setting(_LIMITS_SETTINGS_KEY, "")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def set_usage_limits(limits: dict) -> bool:
    import json
    from app.booking.operator_settings import set_setting
    return set_setting(_LIMITS_SETTINGS_KEY, json.dumps(limits or {}))
