"""A/B test overrides for Popeye's messages.

An operator can define N "variants" (bot_ab_variants) and, per variant,
write an alternate text for specific message keys (bot_message_overrides) —
the same keys used throughout the bot as `get_text(key, ...)` translation
keys or `bot_responses.response_key` values. A lead is randomly assigned one
active variant at creation time (see app/db/leads.py) and keeps it for the
whole conversation.

The current lead's variant is threaded through a contextvar rather than an
extra parameter on every call site: `process_message()` sets it once at the
top of each incoming message, and every `get_text()` / `get_bot_response()`
/ `build_main_menu_text()` call downstream picks it up transparently. Each
asyncio task (one per incoming webhook request) gets its own isolated copy,
so concurrent messages for different leads never leak into each other.
"""
import logging
import time
import contextvars
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

_current_variant: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "bot_variant", default=None
)

_CACHE_TTL_SECONDS = 60
_cache: dict[tuple[str, str], str] = {}
_cache_loaded_at: float = 0.0

# Separate cache for the (ai_provider, ai_model) a variant opts into for the
# final "nothing else matched" fallback — see get_current_ai_model().
_ai_model_cache: dict[str, tuple[str, str]] = {}
_ai_model_cache_loaded_at: float = 0.0


def set_current_variant(variant_key: Optional[str]) -> None:
    _current_variant.set(variant_key)


def get_current_variant() -> Optional[str]:
    return _current_variant.get()


def _reload_cache() -> None:
    global _cache, _cache_loaded_at
    from app.db.connection import get_connection

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT variant_key, message_key, content_es FROM bot_message_overrides"
                )
                rows = cur.fetchall()
        _cache = {(r[0], r[1]): r[2] for r in rows}
        _cache_loaded_at = time.monotonic()
    except Exception as e:
        # Table may not exist yet on a fresh environment, or a transient DB
        # issue — fail open (no overrides) rather than breaking the bot.
        logger.warning(f"Failed to load bot_message_overrides cache: {e}")
        _cache = {}
        _cache_loaded_at = time.monotonic()


def invalidate_cache() -> None:
    """Force the next get_override()/get_current_ai_model() call to reload
    from DB. Called by the admin save/delete endpoints so edits are visible
    on the very next message instead of waiting out the TTL."""
    global _cache_loaded_at, _ai_model_cache_loaded_at
    _cache_loaded_at = 0.0
    _ai_model_cache_loaded_at = 0.0


def _reload_ai_model_cache() -> None:
    global _ai_model_cache, _ai_model_cache_loaded_at
    from app.db.connection import get_connection

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT variant_key, ai_provider, ai_model FROM bot_ab_variants "
                    "WHERE ai_model IS NOT NULL AND ai_model != ''"
                )
                rows = cur.fetchall()
        _ai_model_cache = {r[0]: (r[1] or "groq", r[2]) for r in rows}
        _ai_model_cache_loaded_at = time.monotonic()
    except Exception as e:
        logger.warning(f"Failed to load bot_ab_variants AI-model cache: {e}")
        _ai_model_cache = {}
        _ai_model_cache_loaded_at = time.monotonic()


def get_current_ai_model() -> Optional[Tuple[str, str]]:
    """Return (provider, model) the current lead's variant opted into for
    the live-AI fallback, or None if this variant doesn't set one (the
    normal case — most variants only override message text). Only
    consumed by ConversationManager's final "nothing else matched"
    fallback; never overrides any of the bot's deterministic logic."""
    variant_key = _current_variant.get()
    if not variant_key:
        return None
    if time.monotonic() - _ai_model_cache_loaded_at > _CACHE_TTL_SECONDS:
        _reload_ai_model_cache()
    return _ai_model_cache.get(variant_key)


def get_override(message_key: str) -> Optional[str]:
    """Return the current lead's variant override for this message key, or
    None if there's no active variant for this lead or no override defined
    for this key — callers should fall back to their normal text."""
    variant_key = _current_variant.get()
    if not variant_key:
        return None

    if time.monotonic() - _cache_loaded_at > _CACHE_TTL_SECONDS:
        _reload_cache()

    return _cache.get((variant_key, message_key))
