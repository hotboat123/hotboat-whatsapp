"""Persist booking-site visitor funnel for analytics."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from psycopg import errors as pg_errors
from psycopg.types.json import Jsonb as PgJson

from app.db.connection import get_connection

_log = logging.getLogger(__name__)


def persist_booking_visitor_event(
    session_id: str,
    event_type: str,
    *,
    extra_date: Optional[str],
    time_label: str,
    lang: str,
    referrer: str,
    is_returning: bool,
    recorded_at: datetime,
    link_token: Optional[str] = None,
    visitor_id: Optional[str] = None,
    utm_source: Optional[str] = None,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None,
    utm_content: Optional[str] = None,
    fbclid: Optional[str] = None,
    parametro_url: Optional[str] = None,
) -> None:
    """Append one tracking event (one row per /api/booking/track call).
    link_token (if present) ties this visit's whole funnel back to a specific
    per-client tracked link (see app/booking/link_tracking_router.py).
    visitor_id (if present) is the persistent hb_uid set by hotboat-marketing-web's
    tracker.js on hotboat.cl — the same column that repo already writes to on the
    shared Postgres, so a person's landing + booking browsing share one id.
    The utm_*/fbclid/parametro_url ad-attribution fields are only ever
    non-empty on the first event or two of a session (they come from the
    landing URL's query string), but are stored on every row for simplicity —
    _close_stale_visitor_sessions picks the first non-null value per session
    when rebuilding it for the summary email."""
    sid = (session_id or "").strip()[:64]
    et = (event_type or "").strip()[:96]
    if not sid or not et:
        return
    extra = (extra_date or "").strip()[:120] if extra_date else None
    lt = (link_token or "").strip()[:16] or None
    vid = (visitor_id or "").strip()[:64] or None
    utm_s = (utm_source or "").strip()[:200] or None
    utm_m = (utm_medium or "").strip()[:200] or None
    utm_c = (utm_campaign or "").strip()[:200] or None
    utm_ct = (utm_content or "").strip()[:200] or None
    fbc = (fbclid or "").strip()[:200] or None
    param_url = (parametro_url or "").strip()[:500] or None

    sql = """
        INSERT INTO booking_visitor_events (
            session_id, event_type, extra_date, time_label,
            lang, referrer, is_returning, recorded_at, link_token, visitor_id,
            utm_source, utm_medium, utm_campaign, utm_content, fbclid, parametro_url
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        sid, et, extra, (time_label or "")[:16], (lang or "es")[:8],
        (referrer or "")[:500], bool(is_returning), recorded_at, lt, vid,
        utm_s, utm_m, utm_c, utm_ct, fbc, param_url,
    )
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
    except pg_errors.UndefinedColumn:
        # Self-heal: the startup migration that adds these columns may not
        # have run yet on this deployment. Add them once, then retry.
        _log.warning("booking_visitor_events missing columns — adding now")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "ALTER TABLE booking_visitor_events ADD COLUMN IF NOT EXISTS link_token VARCHAR(16);"
                    "ALTER TABLE booking_visitor_events ADD COLUMN IF NOT EXISTS visitor_id VARCHAR(64);"
                    "ALTER TABLE booking_visitor_events ADD COLUMN IF NOT EXISTS utm_source TEXT;"
                    "ALTER TABLE booking_visitor_events ADD COLUMN IF NOT EXISTS utm_medium TEXT;"
                    "ALTER TABLE booking_visitor_events ADD COLUMN IF NOT EXISTS utm_campaign TEXT;"
                    "ALTER TABLE booking_visitor_events ADD COLUMN IF NOT EXISTS utm_content TEXT;"
                    "ALTER TABLE booking_visitor_events ADD COLUMN IF NOT EXISTS fbclid TEXT;"
                    "ALTER TABLE booking_visitor_events ADD COLUMN IF NOT EXISTS parametro_url TEXT;"
                )
            conn.commit()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()


def persist_booking_visitor_session_closed(
    session: Dict[str, Any],
    classification: str,
    classification_desc: str,
    email_sent: bool,
    ended_at: datetime,
) -> None:
    """
    Persist one closed browsing session (after inactivity timer), with full event list
    and whether the admin notification email was sent.
    """
    sid = str(session.get("session_id") or "")[:64]
    events = session.get("events") or []
    if not sid:
        return
    start_time = session.get("start_time")
    if start_time is None:
        _log.warning("persist_booking_visitor_session_closed: missing start_time")
        return

    lang = str(session.get("lang") or "es")[:8]
    referrer = str(session.get("referrer") or "")[:500]
    is_ret = bool(session.get("is_returning"))
    cnt = len(events)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO booking_visitor_sessions (
                    session_id,
                    started_at,
                    ended_at,
                    lang,
                    referrer,
                    is_returning,
                    classification,
                    classification_desc,
                    event_count,
                    events_json,
                    email_sent
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    sid,
                    start_time,
                    ended_at,
                    lang,
                    referrer,
                    is_ret,
                    (classification or "")[:200],
                    (classification_desc or "")[:500],
                    cnt,
                    PgJson(events),
                    bool(email_sent),
                ),
            )
        conn.commit()


def persist_booking_visitor_identity(
    session_id: str,
    *,
    visitor_id: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    name: Optional[str] = None,
    booking_ref: Optional[str] = None,
) -> None:
    """Link an anonymous browsing session (and its persistent visitor_id, if any)
    to the identity captured at booking time, so booking_visitor_events — landing
    (hotboat.cl) and booking (booking-soft.html), same table — can be joined back
    to a phone for people who never went through a tracked_quote_links link."""
    sid = (session_id or "").strip()[:64]
    if not sid:
        return
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO booking_visitor_identity (
                    session_id, visitor_id, phone, email, name, booking_ref
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    sid,
                    (visitor_id or "").strip()[:64] or None,
                    (phone or "").strip()[:32] or None,
                    (email or "").strip()[:200] or None,
                    (name or "").strip()[:200] or None,
                    (booking_ref or "").strip()[:50] or None,
                ),
            )
        conn.commit()


def get_identity_phone(session_id: str, visitor_id: Optional[str] = None) -> Optional[str]:
    """Look up a phone already linked (via a previous booking) to this session or
    visitor_id, so later browsing from the same person can refresh their web
    activity summary even though this particular session never books."""
    sid = (session_id or "").strip()[:64] or None
    vid = (visitor_id or "").strip()[:64] or None
    if not sid and not vid:
        return None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT phone FROM booking_visitor_identity
                WHERE phone IS NOT NULL AND phone <> ''
                  AND (session_id = %s OR (%s::text IS NOT NULL AND visitor_id = %s::text))
                ORDER BY linked_at DESC
                LIMIT 1
                """,
                (sid, vid, vid),
            )
            row = cur.fetchone()
            return row[0] if row else None


def get_identity_info(session_id: str, visitor_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Like get_identity_phone, but returns whatever name/phone/email this
    session (or visitor_id) has ever been linked to — even a partial match
    (e.g. a booking form filled with email but abandoned before phone), so
    the visitor-session summary email can show real contact details instead
    of just a session id. Coalesces across every linked row for this
    session/visitor so a later, more complete identity fills in gaps left
    by an earlier partial one."""
    sid = (session_id or "").strip()[:64] or None
    vid = (visitor_id or "").strip()[:64] or None
    if not sid and not vid:
        return None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT name, phone, email
                FROM booking_visitor_identity
                WHERE (session_id = %s OR (%s::text IS NOT NULL AND visitor_id = %s::text))
                ORDER BY linked_at DESC
                """,
                (sid, vid, vid),
            )
            rows = cur.fetchall()
    if not rows:
        return None
    result: Dict[str, Any] = {"name": None, "phone": None, "email": None}
    for name, phone, email in rows:
        if not result["name"] and name:
            result["name"] = name
        if not result["phone"] and phone:
            result["phone"] = phone
        if not result["email"] and email:
            result["email"] = email
    if not any(result.values()):
        return None
    return result


_DEEP_INTEREST_EVENTS = {
    # booking-soft.html
    "view_prices", "view_alojamientos", "view_alojamiento_detail",
    "view_experiencias", "view_packs", "view_arma_pack",
    # hotboat-marketing-web (landing) — same booking_visitor_events table
    "view_precio", "faq_open",
}

_BOOKING_INTENT_EVENTS = {"view_reservar", "click_reservar", "click_whatsapp"}


def _classify_event_types(types: set) -> tuple:
    """Mirrors _classify_visitor() in app/booking/router.py (duplicated here on
    purpose: router.py imports from this module, not the reverse, so importing
    back would be circular), extended to also recognize the landing-page event
    vocabulary from hotboat-marketing-web's tracker.js (page_visit, view_precio,
    click_whatsapp, click_reservar, faq_open, etc — same booking_visitor_events
    table, different site). Keep in sync with _classify_visitor if it changes."""
    if "booking_completed" in types:
        return "✅ Reservó", "Completó una reserva en la página"
    if "solicitud_form" in types:
        return "🎯 Listo para reservar", "Abrió el formulario de solicitud de reserva"
    if "date_selected" in types:
        return "⭐ Muy interesado", "Seleccionó una fecha en el calendario"
    deep = types & _DEEP_INTEREST_EVENTS
    if (types & _BOOKING_INTENT_EVENTS) or len(deep) >= 2:
        return "🔍 Explorando activamente", "Visitó varias secciones y mostró interés real"
    if deep:
        return "🔍 Explorando", "Revisó algunas secciones de la página"
    return "👀 Solo mirando", "Entró a la página pero no interactuó mucho"


def _referrer_short_label(referrer: str) -> str:
    if not referrer:
        return ""
    r = referrer.lower()
    if "instagram" in r:
        return "📸 Instagram"
    if "facebook" in r or "fb.com" in r:
        return "👥 Facebook"
    if "tiktok" in r:
        return "🎵 TikTok"
    if "google" in r:
        return "🔍 Google"
    if "whatsapp" in r or "wa.me" in r:
        return "💬 WhatsApp"
    return referrer[:80]


def upsert_visitor_summary(phone: str) -> None:
    """Aggregate everything we know about this phone's site browsing — landing
    (hotboat.cl) and booking (booking-soft.html), across every session/visitor_id
    linked to it via booking_visitor_identity — into a single summary row, so the
    CRM 'Llamadas' dashboard (hotboat-email-marketing-spec) can show a rich
    classification without joining raw events on every sync."""
    raw_phone = (phone or "").strip()
    if not raw_phone:
        return
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        COUNT(DISTINCT bve.session_id) AS session_count,
                        COUNT(bve.id)                   AS event_count,
                        MIN(bve.recorded_at)             AS first_seen_at,
                        MAX(bve.recorded_at)             AS last_seen_at,
                        array_agg(DISTINCT bve.event_type) AS event_types,
                        (array_agg(bve.referrer ORDER BY bve.recorded_at DESC))[1] AS last_referrer,
                        (array_agg(bvi.visitor_id ORDER BY bve.recorded_at DESC))[1] AS visitor_id
                    FROM booking_visitor_identity bvi
                    JOIN booking_visitor_events bve
                      ON bve.session_id = bvi.session_id
                         OR (bvi.visitor_id IS NOT NULL AND bve.visitor_id = bvi.visitor_id)
                    WHERE bvi.phone = %s
                    """,
                    (raw_phone,),
                )
                row = cur.fetchone()
                if not row or not row[0]:
                    return
                (session_count, event_count, first_seen_at, last_seen_at,
                 event_types, last_referrer, visitor_id) = row
                classification, classification_desc = _classify_event_types(set(event_types or []))
                referrer_label = _referrer_short_label(last_referrer or "")

                cur.execute(
                    """
                    INSERT INTO booking_visitor_summary (
                        phone, visitor_id, session_count, event_count,
                        first_seen_at, last_seen_at, classification, classification_desc,
                        referrer_label, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (phone) DO UPDATE SET
                        visitor_id           = EXCLUDED.visitor_id,
                        session_count        = EXCLUDED.session_count,
                        event_count          = EXCLUDED.event_count,
                        first_seen_at        = EXCLUDED.first_seen_at,
                        last_seen_at         = EXCLUDED.last_seen_at,
                        classification       = EXCLUDED.classification,
                        classification_desc  = EXCLUDED.classification_desc,
                        referrer_label       = EXCLUDED.referrer_label,
                        updated_at           = NOW()
                    """,
                    (
                        raw_phone, visitor_id, session_count, event_count,
                        first_seen_at, last_seen_at, classification, classification_desc,
                        referrer_label,
                    ),
                )
            conn.commit()
    except Exception as e:
        _log.warning("upsert_visitor_summary failed for %s: %s", raw_phone, e)
