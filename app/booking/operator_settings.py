"""
Operator settings: vacation days, urgency mode config, dynamic pricing.
All settings stored in hotboat_settings (key/value) table.
"""
import json
import logging
from datetime import date, timedelta
from typing import Optional

from app.db.connection import get_connection

logger = logging.getLogger(__name__)


# ── Generic settings store ─────────────────────────────────────────────────────

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


def _json_setting(key: str, default: dict) -> dict:
    raw = get_setting(key, "")
    if not raw:
        return default.copy()
    try:
        return json.loads(raw)
    except Exception:
        return default.copy()


# ── Urgency mode ───────────────────────────────────────────────────────────────

URGENCY_CONFIG_DEFAULT = {
    "seed_times": ["10:00", "18:00"],
    "gap_hours": 3,
}


def is_urgency_mode() -> bool:
    return get_setting("urgency_mode", "false").lower() == "true"


def get_urgency_config() -> dict:
    return _json_setting("urgency_config", URGENCY_CONFIG_DEFAULT)


def set_urgency_config(cfg: dict) -> bool:
    return set_setting("urgency_config", json.dumps(cfg))


# ── Vacation days ─────────────────────────────────────────────────────────────

def get_vacation_days(from_date: Optional[date] = None, to_date: Optional[date] = None) -> list:
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
    except Exception:
        return False


def add_vacation_day(d: date, reason: str = "") -> bool:
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO vacation_days (fecha, reason) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                    (d, reason),
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

def apply_urgency_filter(
    available_times: list,
    booked_times: list,
    config: Optional[dict] = None,
) -> list:
    """
    Limit visible slots to max 2 using urgency algorithm.

    - Seed pool = slots nearest to each seed_time in config
    - For each booking at X: add nearest-available slots at X±gap_hours
    - Remove booked slots; return up to 2 sorted chronologically
    """
    if not available_times:
        return []

    cfg = config if config is not None else get_urgency_config()
    seed_times: list = cfg.get("seed_times", ["10:00", "18:00"])
    gap_hours: float = float(cfg.get("gap_hours", 3))

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

    pool: set = set()

    # Seed pool from configured seed times
    for st in seed_times:
        n = _nearest(_to_min(st), free_times)
        if n:
            pool.add(n)

    # Expand based on existing bookings (±gap_hours)
    gap_min = int(gap_hours * 60)
    for bt in booked_times:
        bt_min = _to_min(bt)
        for delta in (-gap_min, gap_min):
            n = _nearest(bt_min + delta, free_times)
            if n:
                pool.add(n)

    result = sorted([t for t in free_times if t in pool], key=_to_min)
    return result[:2]


# ── Dynamic Pricing ───────────────────────────────────────────────────────────

DP_CONFIG_DEFAULT = {
    "enabled": False,
    # Each entry: {min_bookings, multiplier}  (sorted descending to find first match)
    "fill_rate": [
        {"min_bookings": 2, "multiplier": 1.18, "label": "2+ reservas"},
        {"min_bookings": 1, "multiplier": 1.08, "label": "1 reserva"},
    ],
    # Each entry: {min_days, multiplier, label}  (sorted descending → first match wins)
    "advance_booking": [
        {"min_days": 14, "multiplier": 0.90, "label": "14+ días (anticipado)"},
        {"min_days":  7, "multiplier": 0.95, "label": "7-13 días"},
        {"min_days":  3, "multiplier": 1.00, "label": "3-6 días (normal)"},
        {"min_days":  0, "multiplier": 1.12, "label": "0-2 días (última hora)"},
    ],
    # Python weekday: 0=Mon … 6=Sun
    "weekday": {
        "0": 1.00, "1": 1.00, "2": 1.00,
        "3": 1.00, "4": 1.05, "5": 1.18, "6": 1.22,
    },
    "min_mult": 0.80,
    "max_mult": 1.60,
}


def get_dp_config() -> dict:
    return _json_setting("dynamic_pricing", DP_CONFIG_DEFAULT)


def set_dp_config(cfg: dict) -> bool:
    return set_setting("dynamic_pricing", json.dumps(cfg))


def calculate_dynamic_multiplier(
    booking_date: date,
    bookings_on_day: int,
    days_advance: int,
    config: Optional[dict] = None,
) -> float:
    """
    Returns the price multiplier for a given date based on demand signals.

    Factors (multiplicative):
      1. Fill rate  – how booked is the day already
      2. Advance    – how far ahead the customer is booking
      3. Weekday    – base demand by day of week

    Returns 1.0 if dynamic pricing is disabled.
    """
    cfg = config if config is not None else get_dp_config()
    if not cfg.get("enabled"):
        return 1.0

    mult = 1.0

    # ── 1. Fill rate ──────────────────────────────────────────────────────────
    fill_rules = sorted(
        cfg.get("fill_rate", []),
        key=lambda r: r["min_bookings"],
        reverse=True,
    )
    for rule in fill_rules:
        if bookings_on_day >= rule["min_bookings"]:
            mult *= float(rule["multiplier"])
            break

    # ── 2. Advance booking ────────────────────────────────────────────────────
    adv_rules = sorted(
        cfg.get("advance_booking", []),
        key=lambda r: r["min_days"],
        reverse=True,
    )
    for rule in adv_rules:
        if days_advance >= rule["min_days"]:
            mult *= float(rule["multiplier"])
            break

    # ── 3. Day of week (0=Mon, 6=Sun in Python) ───────────────────────────────
    weekday = booking_date.weekday()
    wk = cfg.get("weekday", {})
    mult *= float(wk.get(str(weekday), 1.0))

    # ── Clamp ─────────────────────────────────────────────────────────────────
    lo = float(cfg.get("min_mult", 0.8))
    hi = float(cfg.get("max_mult", 1.6))
    return round(max(lo, min(hi, mult)), 4)
