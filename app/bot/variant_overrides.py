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
from typing import Optional, Tuple, FrozenSet

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

# Separate cache for which FAQ trigger keys (app/bot/faq.py response_keys) a
# variant skips — see get_disabled_triggers().
_disabled_triggers_cache: dict[str, FrozenSet[str]] = {}
_disabled_triggers_cache_loaded_at: float = 0.0

# Separate cache for a variant's custom AI system-prompt body — see
# get_current_system_prompt().
_system_prompt_cache: dict[str, str] = {}
_system_prompt_cache_loaded_at: float = 0.0

# Separate cache for which variants have the canned welcome menu turned off
# on first contact — see get_current_show_welcome_menu(). Only variants with
# show_welcome_menu=FALSE are stored (the common case is TRUE/default).
_menu_disabled_cache: FrozenSet[str] = frozenset()
_menu_disabled_cache_loaded_at: float = 0.0

# Separate cache for a variant's display label (e.g. "IA 1", "Control",
# "Tomás") — see get_label_for_variant(). Unlike the getters above this one
# takes an explicit variant_key instead of reading the contextvar: it's used
# from webhook.py to label the "new message" push notification, at a point
# before set_current_variant() has necessarily been called for that message.
_label_cache: dict[str, str] = {}
_label_cache_loaded_at: float = 0.0

# Separate cache for a variant's working-hours schedule (Chile time,
# schedule_start_hour/schedule_end_hour — both NULL = unrestricted, the
# default) — see is_variant_in_hours(). Only variants with BOTH set are
# stored (see the CHECK-equivalent validation in bot_config_router.py:
# they're always written together, never just one).
_schedule_cache: dict[str, tuple[int, int]] = {}
_schedule_cache_loaded_at: float = 0.0


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
    """Force the next get_override()/get_current_ai_model()/
    get_disabled_triggers() call to reload from DB. Called by the admin save/
    delete endpoints so edits are visible on the very next message instead of
    waiting out the TTL."""
    global _cache_loaded_at, _ai_model_cache_loaded_at, _disabled_triggers_cache_loaded_at, _system_prompt_cache_loaded_at, _menu_disabled_cache_loaded_at, _label_cache_loaded_at, _schedule_cache_loaded_at
    _cache_loaded_at = 0.0
    _ai_model_cache_loaded_at = 0.0
    _disabled_triggers_cache_loaded_at = 0.0
    _system_prompt_cache_loaded_at = 0.0
    _menu_disabled_cache_loaded_at = 0.0
    _label_cache_loaded_at = 0.0
    _schedule_cache_loaded_at = 0.0


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


def _reload_disabled_triggers_cache() -> None:
    global _disabled_triggers_cache, _disabled_triggers_cache_loaded_at
    from app.db.connection import get_connection

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT variant_key, disabled_triggers FROM bot_ab_variants "
                    "WHERE disabled_triggers IS NOT NULL AND array_length(disabled_triggers, 1) > 0"
                )
                rows = cur.fetchall()
        _disabled_triggers_cache = {r[0]: frozenset(r[1]) for r in rows}
        _disabled_triggers_cache_loaded_at = time.monotonic()
    except Exception as e:
        logger.warning(f"Failed to load bot_ab_variants disabled_triggers cache: {e}")
        _disabled_triggers_cache = {}
        _disabled_triggers_cache_loaded_at = time.monotonic()


def get_disabled_triggers() -> FrozenSet[str]:
    """FAQ trigger response_keys (app/bot/faq.py) the current lead's variant
    skips, so a matching free-text question falls through the bot's priority
    chain instead of being answered by the canned FAQ text — e.g. to let it
    reach the live-AI fallback instead. Empty set (the normal case) means
    "don't skip anything," unchanged behavior."""
    variant_key = _current_variant.get()
    if not variant_key:
        return frozenset()
    if time.monotonic() - _disabled_triggers_cache_loaded_at > _CACHE_TTL_SECONDS:
        _reload_disabled_triggers_cache()
    return _disabled_triggers_cache.get(variant_key, frozenset())


def _reload_system_prompt_cache() -> None:
    global _system_prompt_cache, _system_prompt_cache_loaded_at
    from app.db.connection import get_connection

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT variant_key, system_prompt FROM bot_ab_variants "
                    "WHERE system_prompt IS NOT NULL AND system_prompt != ''"
                )
                rows = cur.fetchall()
        _system_prompt_cache = {r[0]: r[1] for r in rows}
        _system_prompt_cache_loaded_at = time.monotonic()
    except Exception as e:
        logger.warning(f"Failed to load bot_ab_variants system_prompt cache: {e}")
        _system_prompt_cache = {}
        _system_prompt_cache_loaded_at = time.monotonic()


def get_current_system_prompt() -> Optional[str]:
    """The current lead's variant's custom AI system-prompt body, or None
    to use the default (app/bot/ai_handler.py's _default_editable_prompt).
    Only the editable body — the safety footer is applied separately and
    unconditionally by build_system_prompt(), never stored here."""
    variant_key = _current_variant.get()
    if not variant_key:
        return None
    if time.monotonic() - _system_prompt_cache_loaded_at > _CACHE_TTL_SECONDS:
        _reload_system_prompt_cache()
    return _system_prompt_cache.get(variant_key)


def _reload_menu_disabled_cache() -> None:
    global _menu_disabled_cache, _menu_disabled_cache_loaded_at
    from app.db.connection import get_connection

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT variant_key FROM bot_ab_variants WHERE show_welcome_menu = FALSE"
                )
                rows = cur.fetchall()
        _menu_disabled_cache = frozenset(r[0] for r in rows)
        _menu_disabled_cache_loaded_at = time.monotonic()
    except Exception as e:
        logger.warning(f"Failed to load bot_ab_variants show_welcome_menu cache: {e}")
        _menu_disabled_cache = frozenset()
        _menu_disabled_cache_loaded_at = time.monotonic()


def get_current_show_welcome_menu() -> bool:
    """Whether the current lead's variant should get the canned Popeye
    welcome menu on their first message. True (default) whenever there's no
    active variant or the variant hasn't turned it off — matches the bot's
    original, unconditional behavior."""
    variant_key = _current_variant.get()
    if not variant_key:
        return True
    if time.monotonic() - _menu_disabled_cache_loaded_at > _CACHE_TTL_SECONDS:
        _reload_menu_disabled_cache()
    return variant_key not in _menu_disabled_cache


def _reload_label_cache() -> None:
    global _label_cache, _label_cache_loaded_at
    from app.db.connection import get_connection

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT variant_key, label FROM bot_ab_variants")
                rows = cur.fetchall()
        _label_cache = {r[0]: r[1] for r in rows if r[1]}
        _label_cache_loaded_at = time.monotonic()
    except Exception as e:
        logger.warning(f"Failed to load bot_ab_variants label cache: {e}")
        _label_cache = {}
        _label_cache_loaded_at = time.monotonic()


def get_label_for_variant(variant_key: Optional[str]) -> Optional[str]:
    """Display label for a variant_key (e.g. "IA 1", "Control", "Tomás") —
    used to prefix the "new message" push notification with who/what is
    handling that lead's conversation (an automated variant or a specific
    person for a human-only variant). None if variant_key is falsy or not
    found — callers should just omit the prefix in that case."""
    if not variant_key:
        return None
    if time.monotonic() - _label_cache_loaded_at > _CACHE_TTL_SECONDS:
        _reload_label_cache()
    return _label_cache.get(variant_key)


def hour_in_schedule(now_hour: int, start_hour: int, end_hour: int) -> bool:
    """Pure range check, shared by is_variant_in_hours() below (webhook
    notification gating) and _pick_active_variant() in app/db/leads.py
    (new-lead routing) so both use the exact same semantics for a schedule
    window. end_hour up to 24 means "until midnight". Handles windows that
    wrap past midnight (start_hour > end_hour, e.g. 22 -> 6). A degenerate
    range (start == end) is treated as unrestricted (True) rather than
    "never" — an operator fat-fingering identical start/end shouldn't
    silently block every lead/notification for that variant."""
    if start_hour == end_hour:
        return True
    if start_hour < end_hour:
        return start_hour <= now_hour < end_hour
    return now_hour >= start_hour or now_hour < end_hour


def _reload_schedule_cache() -> None:
    global _schedule_cache, _schedule_cache_loaded_at
    from app.db.connection import get_connection

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT variant_key, schedule_start_hour, schedule_end_hour FROM bot_ab_variants "
                    "WHERE schedule_start_hour IS NOT NULL AND schedule_end_hour IS NOT NULL"
                )
                rows = cur.fetchall()
        _schedule_cache = {r[0]: (r[1], r[2]) for r in rows}
        _schedule_cache_loaded_at = time.monotonic()
    except Exception as e:
        logger.warning(f"Failed to load bot_ab_variants schedule cache: {e}")
        _schedule_cache = {}
        _schedule_cache_loaded_at = time.monotonic()


def is_variant_in_hours(variant_key: Optional[str]) -> bool:
    """True if `variant_key` has no schedule set (unrestricted — the
    default for every variant until an operator sets one) or the current
    hour in America/Santiago falls inside its working-hours window. Used
    ONLY to gate outgoing operator push notifications (new-message alert,
    unanswered-message alert — see webhook.py) — never gates whether the
    bot itself auto-replies or whether a message gets saved; a message
    outside a human variant's hours still just sits there with bot_enabled
    already FALSE, same as always, it just won't page anyone about it."""
    if not variant_key:
        return True
    if time.monotonic() - _schedule_cache_loaded_at > _CACHE_TTL_SECONDS:
        _reload_schedule_cache()
    window = _schedule_cache.get(variant_key)
    if not window:
        return True
    from datetime import datetime
    from zoneinfo import ZoneInfo
    now_hour = datetime.now(ZoneInfo("America/Santiago")).hour
    return hour_in_schedule(now_hour, window[0], window[1])


def default_welcome_message(label: str) -> str:
    """Fallback text for bot_ab_variants.welcome_message when an is_human
    variant (Tomás, Esteban, ...) doesn't have a custom one saved yet —
    sent once to a brand-new lead the moment they're assigned to that
    variant (see get_or_create_lead in app/db/leads.py). Explains that a
    person will answer, but Popeye can still help with the basics on
    request — see the "hola Popeye" pass-through gate in
    app/whatsapp/webhook.py, which this message's wording depends on:
    if that trigger phrase ever changes, update this text to match."""
    return (
        f"¡Hola! 👋 En cualquier momento llega *{label}* a responderte.\n\n"
        "Mientras tanto, si quieres resolver dudas básicas (precios, "
        "características, ubicación), puedes preguntarle a Popeye — "
        "solo escribe *Hola Popeye* y te atenderá."
    )


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
