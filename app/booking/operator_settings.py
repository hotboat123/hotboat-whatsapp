"""
Operator settings and vacation days management.
Centralizes vacation_days and hotboat_settings DB access.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from app.db.connection import get_connection

logger = logging.getLogger(__name__)


# ── Settings ──────────────────────────────────────────────────────────────────

def get_setting(key: str, default: str = "") -> str:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM hotboat_settings WHERE key=%s", (key,))
                row = cur.fetchone()
                return row[0] if row else default
    except Exception as e:
        logger.warning(f"get_setting({key}) failed: {e}")
        return default


def set_setting(key: str, value: str) -> bool:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO hotboat_settings (key, value, updated_at)
                    VALUES (%s, %s, NOW())
                    ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
                """, (key, value))
                conn.commit()
        return True
    except Exception as e:
        logger.error(f"set_setting({key}) failed: {e}")
        return False


def is_urgency_mode() -> bool:
    return get_setting("urgency_mode", "false").lower() == "true"


# ── Vacation days ─────────────────────────────────────────────────────────────

def get_vacation_days(from_date: Optional[date] = None, to_date: Optional[date] = None) -> list[str]:
    """Returns list of vacation dates as 'YYYY-MM-DD' strings."""
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                wheres, params = [], []
                if from_date:
                    wheres.append("fecha >= %s"); params.append(from_date)
                if to_date:
                    wheres.append("fecha <= %s"); params.append(to_date)
                where = ("WHERE " + " AND ".join(wheres)) if wheres else ""
                cur.execute(f"SELECT fecha, reason FROM vacation_days {where} ORDER BY fecha", params)
                return [{"date": str(r[0]), "reason": r[1] or ""} for r in cur.fetchall()]
    except Exception as e:
        logger.error(f"get_vacation_days failed: {e}")
        return []


def is_vacation_day(d: date) -> bool:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1 FROM vacation_days WHERE fecha=%s", (d,))
                return cur.fetchone() is not None
    except:
        return False


def add_vacation_day(d: date, reason: str = "") -> bool:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO vacation_days (fecha, reason) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (d, reason)
                )
                conn.commit()
        return True
    except Exception as e:
        logger.error(f"add_vacation_day failed: {e}")
        return False


def remove_vacation_day(d: date) -> bool:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM vacation_days WHERE fecha=%s", (d,))
                conn.commit()
        return True
    except Exception as e:
        logger.error(f"remove_vacation_day failed: {e}")
        return False


# ── Urgency filter ────────────────────────────────────────────────────────────

def apply_urgency_filter(available_times: list, booked_times: list) -> list:
    """
    Apply 'genera urgencia' algorithm to limit visible slots to max 2.

    Pool logic:
      - Seed pool: slot nearest to 10:00 + slot nearest to 18:00
      - For each booking at time X: add nearest-available slots to X-3h and X+3h
      - Remove booked slots from pool
      - Return up to 2 from remaining pool (sorted chronologically)

    Args:
        available_times: Real available time strings ["HH:MM", ...]
        booked_times:    Already booked time strings for that day ["HH:MM", ...]
    Returns:
        Filtered list of at most 2 time strings
    """
    if not available_times:
        return []

    def _to_min(t: str) -> int:
        h, m = map(int, t.split(":"))
        return h * 60 + m

    def _nearest(target_min: int, times: list) -> Optional[str]:
        if not times:
            return None
        return min(times, key=lambda t: abs(_to_min(t) - target_min))

    booked_set = set(booked_times)
    free_times = [t for t in available_times if t not in booked_set]

    if not free_times:
        return []

    pool = set()

    # Seed: nearest to 10:00 and 18:00
    m = _nearest(10 * 60, free_times)
    e = _nearest(18 * 60, free_times)
    if m:
        pool.add(m)
    if e and e != m:
        pool.add(e)

    # Expand pool based on existing bookings
    for bt in booked_times:
        bt_min = _to_min(bt)
        for delta_h in (-3, 3):
            target_min = bt_min + delta_h * 60
            n = _nearest(target_min, free_times)
            if n:
                pool.add(n)

    # Result: pool ∩ free_times, sorted, max 2
    result = sorted([t for t in free_times if t in pool], key=_to_min)
    return result[:2]
