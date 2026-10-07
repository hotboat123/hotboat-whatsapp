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
