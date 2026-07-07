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
) -> None:
    """Append one tracking event (one row per /api/booking/track call).
    link_token (if present) ties this visit's whole funnel back to a specific
    per-client tracked link (see app/booking/link_tracking_router.py)."""
    sid = (session_id or "").strip()[:64]
    et = (event_type or "").strip()[:96]
    if not sid or not et:
        return
    extra = (extra_date or "").strip()[:120] if extra_date else None
    lt = (link_token or "").strip()[:16] or None

    sql = """
        INSERT INTO booking_visitor_events (
            session_id, event_type, extra_date, time_label,
            lang, referrer, is_returning, recorded_at, link_token
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        sid, et, extra, (time_label or "")[:16], (lang or "es")[:8],
        (referrer or "")[:500], bool(is_returning), recorded_at, lt,
    )
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
            conn.commit()
    except pg_errors.UndefinedColumn:
        # Self-heal: the startup migration that adds this column may not have
        # run yet on this deployment. Add it once, then retry the insert.
        _log.warning("booking_visitor_events.link_token missing — adding it now")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "ALTER TABLE booking_visitor_events ADD COLUMN IF NOT EXISTS link_token VARCHAR(16)"
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
