"""Persist booking-site visitor funnel for analytics."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

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
) -> None:
    """Append one tracking event (one row per /api/booking/track call)."""
    sid = (session_id or "").strip()[:64]
    et = (event_type or "").strip()[:96]
    if not sid or not et:
        return
    extra = (extra_date or "").strip()[:120] if extra_date else None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO booking_visitor_events (
                    session_id, event_type, extra_date, time_label,
                    lang, referrer, is_returning, recorded_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    sid,
                    et,
                    extra,
                    (time_label or "")[:16],
                    (lang or "es")[:8],
                    (referrer or "")[:500],
                    bool(is_returning),
                    recorded_at,
                ),
            )
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
