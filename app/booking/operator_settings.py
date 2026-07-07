"""
Operator settings: vacation days, urgency mode config, dynamic pricing.
All settings stored in hotboat_settings (key/value) table.
"""
import json
import logging
import time as _time
from datetime import date, timedelta
from typing import Optional, Tuple

from app.db.connection import get_connection

logger = logging.getLogger(__name__)


# ── Generic settings store ─────────────────────────────────────────────────────

# Short-lived cache so a single request that reads the same setting multiple
# times (schedule types, urgency modes, operating hours, dp config, etc. are
# each read several times while building the availability calendar) doesn't
# hit the DB once per read. TTL kept short so admin edits apply almost
# immediately; invalidated outright on write.
_SETTINGS_CACHE: dict = {}
_SETTINGS_CACHE_TTL = 15  # seconds


def get_setting(key: str, default: str = "") -> str:
    now = _time.time()
    cached = _SETTINGS_CACHE.get(key)
    if cached and (now - cached[1]) < _SETTINGS_CACHE_TTL:
        return cached[0]
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM hotboat_settings WHERE key=%s", (key,))
                row = cur.fetchone()
                if row:
                    _SETTINGS_CACHE[key] = (row[0], now)
                    return row[0]
                return default
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
        _SETTINGS_CACHE.pop(key, None)
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


def _time_str_sort_key(t: str) -> int:
    h, m = map(int, t.split(":"))
    return h * 60 + m


def _normalize_seed_time(t: str) -> Optional[str]:
    """Accept 'H:MM' or 'HH:MM' → 'HH:MM', or None if invalid."""
    if not t or not str(t).strip():
        return None
    parts = str(t).strip().split(":")
    if len(parts) < 2:
        return None
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return f"{h:02d}:{m:02d}"


def get_effective_urgency_seed_times(config: Optional[dict] = None) -> list:
    """
    Semillas HH:MM para el filtro de urgencia (y slots grises).

    - Si `urgency_config.seed_times` tiene entradas válidas: **solo** esas horas
      actúan como semillas (escasez), más la lógica ±gap alrededor de reservas.
    - Si seed_times está vacío: se usan todos los `operating_hours` HotBoat.

    No se hace unión con operating_hours cuando ya hay seed_times: unir ambos
    hacía que casi todo el grid libre coincidiera con una semilla y se mostraran
    demasiados horarios «disponibles».
    """
    cfg = config if config is not None else get_urgency_config()
    oh = get_operating_hours()
    raw = cfg.get("seed_times") or []
    normalized: list = []
    for x in raw:
        s = _normalize_seed_time(str(x))
        if s:
            normalized.append(s)
    if normalized:
        return sorted(set(normalized), key=_time_str_sort_key)
    return sorted(oh, key=_time_str_sort_key)


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


# ── Per-day urgency overrides ─────────────────────────────────────────────────


def normalize_urgency_entity(entity_type: str, entity_slug: str) -> Tuple[str, str]:
    """Canonical scope for urgency_days rows (also used by admin APIs)."""
    et = (entity_type or "hotboat").strip().lower()
    if et not in ("hotboat", "experience", "pack", "alojamiento"):
        et = "hotboat"
    slug = (entity_slug or "").strip()
    if len(slug) > 160:
        slug = slug[:160]
    return et, slug


_URGENCY_DAYS_CACHE: dict = {}
_URGENCY_DAYS_CACHE_TTL = 20  # seconds — corta, solo para deduplicar ráfagas de llamadas
                              # (get_available_slots/check_availability llaman a esto
                              # varias veces por cada mensaje de WhatsApp).


def _clear_urgency_days_cache():
    _URGENCY_DAYS_CACHE.clear()


def get_urgency_days(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
    *,
    entity_type: str = "hotboat",
    entity_slug: str = "",
) -> list:
    """Return list of {date, enabled, reason, entity_type, entity_slug} for the given scope."""
    et, slug = normalize_urgency_entity(entity_type, entity_slug)

    import time as _time
    cache_key = (from_date, to_date, et, slug)
    cached = _URGENCY_DAYS_CACHE.get(cache_key)
    if cached and (_time.time() - cached[0]) < _URGENCY_DAYS_CACHE_TTL:
        return cached[1]

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                wheres, params = ["entity_type = %s", "entity_slug = %s"], [et, slug]
                if from_date:
                    wheres.append("fecha >= %s")
                    params.append(from_date)
                if to_date:
                    wheres.append("fecha <= %s")
                    params.append(to_date)
                where = "WHERE " + " AND ".join(wheres)
                cur.execute(
                    f"SELECT fecha, enabled, reason, entity_type, entity_slug, profile_key, COALESCE(ghost_times, '[]'::jsonb) FROM urgency_days {where} ORDER BY fecha",
                    params,
                )
                result = [
                    {
                        "date": str(r[0]),
                        "enabled": r[1],
                        "reason": r[2] or "",
                        "entity_type": r[3],
                        "entity_slug": r[4] or "",
                        "profile_key": r[5] or None,
                        "ghost_times": r[6] if isinstance(r[6], list) else (json.loads(r[6]) if isinstance(r[6], str) else []),
                    }
                    for r in cur.fetchall()
                ]
                _URGENCY_DAYS_CACHE[cache_key] = (_time.time(), result)
                return result
    except Exception as e:
        logger.error(f"get_urgency_days failed: {e}")
        return []


def get_urgency_day_override_for_scope(d: date, entity_type: str, entity_slug: str) -> Optional[bool]:
    """True/False if the day has an explicit override for this scope, None if no row."""
    et, slug = normalize_urgency_entity(entity_type, entity_slug)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT enabled FROM urgency_days WHERE entity_type=%s AND entity_slug=%s AND fecha=%s",
                    (et, slug, d),
                )
                row = cur.fetchone()
                return row[0] if row else None
    except Exception:
        return None


def get_urgency_day_override(d: date) -> Optional[bool]:
    """HotBoat/global slot urgency override (entity_type=hotboat, empty slug)."""
    return get_urgency_day_override_for_scope(d, "hotboat", "")


def is_high_season_web_addon(d: date, entity_type: str, entity_slug: str) -> bool:
    """
    Temporada alta for web extras (no online payment / requires email):
    only product-scoped overrides apply (no implicit fallback to HotBoat global urgency).
    """
    et, slug = normalize_urgency_entity(entity_type, entity_slug)
    ov = get_urgency_day_override_for_scope(d, et, slug)
    return ov is True


def set_urgency_day(
    d: date,
    enabled: bool,
    reason: str = "",
    *,
    entity_type: str = "hotboat",
    entity_slug: str = "",
    profile_key: Optional[str] = None,
    ghost_times: Optional[list] = None,
) -> bool:
    et, slug = normalize_urgency_entity(entity_type, entity_slug)
    pk = (profile_key or "").strip() or None
    gt = json.dumps(ghost_times or [])
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """INSERT INTO urgency_days (entity_type, entity_slug, fecha, enabled, reason, profile_key, ghost_times)
                       VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                       ON CONFLICT (entity_type, entity_slug, fecha)
                       DO UPDATE SET enabled=EXCLUDED.enabled, reason=EXCLUDED.reason,
                                     profile_key=EXCLUDED.profile_key,
                                     ghost_times=EXCLUDED.ghost_times""",
                    (et, slug, d, enabled, reason, pk, gt),
                )
                conn.commit()
        _clear_urgency_days_cache()
        return True
    except Exception as e:
        logger.error(f"set_urgency_day failed: {e}")
        return False


def remove_urgency_day(
    d: date,
    *,
    entity_type: str = "hotboat",
    entity_slug: str = "",
) -> bool:
    et, slug = normalize_urgency_entity(entity_type, entity_slug)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM urgency_days WHERE entity_type=%s AND entity_slug=%s AND fecha=%s",
                    (et, slug, d),
                )
                conn.commit()
        _clear_urgency_days_cache()
        return True
    except Exception as e:
        logger.error(f"remove_urgency_day failed: {e}")
        return False


# ── Urgency filter ────────────────────────────────────────────────────────────

def apply_urgency_filter(
    available_times: list,
    booked_times: list,
    config: Optional[dict] = None,
) -> list:
    """
    Urgency algorithm:

    • Conjunto base de "semillas" = seed_times (si hay) o bien todos los operating_hours.
    • Sin reservas → mostrar esas semillas que estén libres (en el grid del día).
    • Con reservas → además, para cada reserva en X, sugerir X ± gap si cae en cupo libre.

    Ejemplos con seeds=[10,18,21] gap=3:
      - Sin reservas          → [10:00, 18:00, 21:00]
      - Reserva a las 18:00   → [15:00, 21:00]
      - Reserva a las 21:00   → [18:00] (24:00 fuera de rango)
      - Reservas 18:00+21:00  → [15:00, 18:00, 24:00→ignorado] = [15:00, 18:00]
    """
    if not available_times:
        return []

    cfg = config if config is not None else get_urgency_config()
    seed_times: list = get_effective_urgency_seed_times(cfg)
    gap_hours: float = float(cfg.get("gap_hours", 3))

    def _to_min(t: str) -> int:
        h, m = map(int, t.split(":"))
        return h * 60 + m

    def _from_min(total_min: int) -> str:
        return f"{total_min // 60:02d}:{total_min % 60:02d}"

    booked_set = set(booked_times)
    free_set = set(t for t in available_times if t not in booked_set)

    if not free_set:
        return []

    gap_min = int(gap_hours * 60)
    TOLERANCE = 30  # minutes — cómo de cerca debe estar el slot encontrado

    pool: set = set()

    # 1. Siempre mostrar los seeds que estén libres (no reservados)
    for st in seed_times:
        if st in free_set:
            pool.add(st)
        elif st not in booked_set:
            # Seed generado en horario no exacto → buscar dentro de tolerancia
            target = _to_min(st)
            candidates = [t for t in free_set if abs(_to_min(t) - target) <= TOLERANCE]
            if candidates:
                pool.add(min(candidates, key=lambda t: abs(_to_min(t) - target)))

    # 2. Para cada reserva, agregar reserva ± gap (reemplaza solo ese seed reservado)
    for bt in booked_times:
        bt_min = _to_min(bt)
        for delta in (-gap_min, gap_min):
            target = bt_min + delta
            candidates = [t for t in free_set if abs(_to_min(t) - target) <= TOLERANCE]
            if candidates:
                pool.add(min(candidates, key=lambda t: abs(_to_min(t) - target)))

    return sorted([t for t in free_set if t in pool], key=_to_min)


def get_urgency_fake_slots(config: Optional[dict] = None) -> list:
    """
    Calcula los slots "fantasma" que se muestran en GRIS (deshabilitados) en la app
    cuando el modo urgencia está activo y NO hay reservas reales en el día.

    Lógica: para cada seed S, calcular S±gap_hours.
    Si el resultado NO es un seed y está dentro del rango 06:00-23:00 → slot gris.

    Ejemplo: seeds=[10:00,18:00,21:00] gap=3
      10+3=13:00 (no seed) → gris
      10-3=07:00 (no seed) → gris
      18+3=21:00 (ES seed) → omitir
      18-3=15:00 (no seed) → gris
      21+3=24:00 (fuera)   → omitir
      21-3=18:00 (ES seed) → omitir
    Resultado: [07:00, 13:00, 15:00]
    """
    cfg = config if config is not None else get_urgency_config()
    seed_times: list = get_effective_urgency_seed_times(cfg)
    gap_hours: float = float(cfg.get("gap_hours", 3))

    def _to_min(t: str) -> int:
        h, m = map(int, t.split(":"))
        return h * 60 + m

    def _from_min(total_min: int) -> str:
        return f"{total_min // 60:02d}:{total_min % 60:02d}"

    seed_set = set(seed_times)
    seed_mins = [_to_min(s) for s in seed_times]
    gap_min = int(gap_hours * 60)
    fake = set()

    for s_min in seed_mins:
        for delta in (-gap_min, gap_min):
            target = s_min + delta
            if target < 6 * 60 or target >= 24 * 60:
                continue
            candidate = _from_min(target)
            if candidate not in seed_set:
                fake.add(candidate)

    # Explicit ghost_times: always grey regardless of seed/gap calculation
    for g in (cfg.get("ghost_times") or []):
        s = _normalize_seed_time(str(g))
        if s and s not in seed_set:
            fake.add(s)

    return sorted(fake, key=_to_min)


# ── Dynamic Pricing ───────────────────────────────────────────────────────────

# Editable in the admin panel. Placeholders {PRECIO_MIN}/{PRECIO_MAX}/
# {TOTAL_MIN}/{TOTAL_MAX} are resolved live from the current config;
# {LINK} is left untouched — it's filled in later when the message is sent.
DP_MESSAGE_TEMPLATE_DEFAULT = (
    "El valor cambia según la fecha, el horario, la cantidad de personas y "
    "la anticipación de la reserva.\n"
    "\n"
    "🎁 Mientras antes reserves, mejor precio puedes obtener.\n"
    "\n"
    "💰 Valores desde {PRECIO_MIN} por persona.\n"
    "\n"
    "En menos de 20 segundos puedes ver el precio exacto para tu grupo y fecha:\n"
    "\n"
    "👉 {LINK}"
)

DP_CONFIG_DEFAULT = {
    "enabled": False,
    "message_template": DP_MESSAGE_TEMPLATE_DEFAULT,
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
    # Meses (1=Ene … 12=Dic) que caen en temporada alta; el resto es temporada
    # baja. Cada temporada tiene su propio multiplicador. day_overrides fuerza
    # una fecha puntual ("YYYY-MM-DD" -> "high"|"low") sin importar su mes —
    # tiene prioridad sobre high_months (útil para fines de semana largos).
    "season": {
        "high_months": [12, 1, 2, 3],
        "high_multiplier": 1.15,
        "low_multiplier": 0.92,
        "day_overrides": {},
    },
    # Each entry: {min_hour, multiplier, label}  (sorted descending → first match wins)
    # Ej: 16:00-17:59 (tarde) más caro, 00:00-11:59 (mañana) más barato.
    "hour_of_day": [
        {"min_hour": 18, "multiplier": 1.00, "label": "Noche (18-23h)"},
        {"min_hour": 16, "multiplier": 1.15, "label": "Tarde (16-17h)"},
        {"min_hour": 12, "multiplier": 1.00, "label": "Mediodía (12-15h)"},
        {"min_hour":  0, "multiplier": 0.92, "label": "Mañana (0-11h)"},
    ],
    "min_mult": 0.80,
    "max_mult": 1.60,
    # Permite activar/desactivar cada factor por separado (independiente del
    # interruptor maestro "enabled"). Todos ON por defecto.
    "factors_enabled": {
        "fill_rate": True,
        "advance_booking": True,
        "season": True,
        "hour_of_day": True,
    },
}


def get_dp_config() -> dict:
    """Config de precios dinámicos, con merge sobre los defaults para que
    configuraciones guardadas antes de agregar un factor nuevo (p. ej.
    hour_of_day o factors_enabled) lo reciban con su valor por defecto en
    vez de quedar vacío/ausente."""
    stored = _json_setting("dynamic_pricing", DP_CONFIG_DEFAULT)
    merged = {**DP_CONFIG_DEFAULT, **stored}
    merged["factors_enabled"] = {
        **DP_CONFIG_DEFAULT["factors_enabled"],
        **(stored.get("factors_enabled") or {}),
    }
    return merged


def set_dp_config(cfg: dict) -> bool:
    return set_setting("dynamic_pricing", json.dumps(cfg))


def is_high_season(booking_date: date, season_cfg: dict) -> bool:
    """True if booking_date falls in high season. A per-day override in
    season_cfg['day_overrides'] (e.g. a specific long weekend) always wins
    over the month-based classification."""
    override = (season_cfg.get("day_overrides") or {}).get(str(booking_date))
    if override == "high":
        return True
    if override == "low":
        return False
    high_months = {int(m) for m in season_cfg.get("high_months", [])}
    return booking_date.month in high_months


def calculate_dynamic_multiplier(
    booking_date: date,
    bookings_on_day: int,
    days_advance: int,
    config: Optional[dict] = None,
    booking_hour: Optional[int] = None,
) -> float:
    """
    Returns the price multiplier for a given date (and optionally hour) based
    on demand signals.

    Factors (multiplicative):
      1. Fill rate   – how booked is the day already
      2. Advance     – how far ahead the customer is booking
      3. Season      – high season vs low season (by month)
      4. Hour of day – time slot of the trip (only if booking_hour is given)

    Returns 1.0 if dynamic pricing is disabled.
    """
    cfg = config if config is not None else get_dp_config()
    if not cfg.get("enabled"):
        return 1.0

    factors_on = cfg.get("factors_enabled") or {}
    def _factor_on(key: str) -> bool:
        return factors_on.get(key, True)

    mult = 1.0

    # ── 1. Fill rate ──────────────────────────────────────────────────────────
    if _factor_on("fill_rate"):
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
    if _factor_on("advance_booking"):
        adv_rules = sorted(
            cfg.get("advance_booking", []),
            key=lambda r: r["min_days"],
            reverse=True,
        )
        for rule in adv_rules:
            if days_advance >= rule["min_days"]:
                mult *= float(rule["multiplier"])
                break

    # ── 3. Season (high vs low, by calendar month — or a per-day override) ────
    if _factor_on("season"):
        season_cfg = cfg.get("season") or {}
        if is_high_season(booking_date, season_cfg):
            mult *= float(season_cfg.get("high_multiplier", 1.0))
        else:
            mult *= float(season_cfg.get("low_multiplier", 1.0))

    # ── 4. Hour of day (solo si se conoce la hora del paseo) ──────────────────
    if booking_hour is not None and _factor_on("hour_of_day"):
        hour_rules = sorted(
            cfg.get("hour_of_day", []),
            key=lambda r: r["min_hour"],
            reverse=True,
        )
        for rule in hour_rules:
            if booking_hour >= rule["min_hour"]:
                mult *= float(rule["multiplier"])
                break

    # ── Clamp ─────────────────────────────────────────────────────────────────
    lo = float(cfg.get("min_mult", 0.8))
    hi = float(cfg.get("max_mult", 1.6))
    return round(max(lo, min(hi, mult)), 4)


def get_dynamic_multiplier_for_booking(booking_date: date, booking_time: Optional[str] = None) -> float:
    """
    Single source of truth for the dynamic-price multiplier of a HotBoat
    booking: counts same-day web bookings, days of advance, and (if given)
    the hour of the slot. Used by BOTH the price-preview endpoint (shown to
    the customer before they pay) and the booking-creation endpoint (what
    they're actually charged) — so the two can never drift apart.
    """
    cfg = get_dp_config()
    if not cfg.get("enabled"):
        return 1.0

    today = date.today()
    days_advance = max(0, (booking_date - today).days)

    bookings_on_day = 0
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """SELECT COUNT(*) FROM all_appointments
                       WHERE source = 'hotboat_web'
                         AND fecha = %s
                         AND status NOT IN ('cancelled','rejected','solicitud')""",
                    (booking_date,),
                )
                bookings_on_day = cur.fetchone()[0]
    except Exception as e:
        logger.warning(f"get_dynamic_multiplier_for_booking: could not count bookings: {e}")

    booking_hour = None
    if booking_time:
        try:
            booking_hour = int(str(booking_time).split(":")[0])
        except (ValueError, IndexError):
            booking_hour = None

    return calculate_dynamic_multiplier(
        booking_date, bookings_on_day, days_advance, cfg, booking_hour=booking_hour
    )


def build_dynamic_price_message(cfg: Optional[dict] = None) -> dict:
    """
    Computes the true min/max price (per person and per full boat) reachable
    under the given dynamic-pricing config — considering ONLY the factors
    whose factors_enabled flag is on — and renders a ready-to-send customer
    message quoting the lowest per-person price. Pass a draft (unsaved)
    config to preview edits live; omit to use the config currently stored
    in settings.
    """
    from app.booking.db import PRICES

    cfg = cfg if cfg is not None else get_dp_config()
    factors_on = cfg.get("factors_enabled") or {}

    def _on(key: str) -> bool:
        return factors_on.get(key, True)

    min_mult = 1.0
    max_mult = 1.0

    if cfg.get("enabled"):
        if _on("fill_rate"):
            mults = [1.0] + [float(r["multiplier"]) for r in (cfg.get("fill_rate") or [])]
            min_mult *= min(mults)
            max_mult *= max(mults)

        if _on("advance_booking"):
            rules = cfg.get("advance_booking") or []
            if rules:
                min_mult *= min(float(r["multiplier"]) for r in rules)
                max_mult *= max(float(r["multiplier"]) for r in rules)

        if _on("season"):
            season_cfg = cfg.get("season") or {}
            vals = [
                float(season_cfg.get("high_multiplier", 1.0)),
                float(season_cfg.get("low_multiplier", 1.0)),
            ]
            min_mult *= min(vals)
            max_mult *= max(vals)

        if _on("hour_of_day"):
            rules = cfg.get("hour_of_day") or []
            if rules:
                min_mult *= min(float(r["multiplier"]) for r in rules)
                max_mult *= max(float(r["multiplier"]) for r in rules)

        lo_clamp = float(cfg.get("min_mult", 0.80))
        hi_clamp = float(cfg.get("max_mult", 1.60))
        min_mult = max(lo_clamp, min(min_mult, hi_clamp))
        max_mult = max(lo_clamp, min(max_mult, hi_clamp))

    def _round_pp(base: float, mult: float) -> int:
        return int(round(base * mult / 1000) * 1000)

    pp_min_vals = [_round_pp(p, min_mult) for p in PRICES.values()]
    pp_max_vals = [_round_pp(p, max_mult) for p in PRICES.values()]
    total_min_vals = [_round_pp(p, min_mult) * n for n, p in PRICES.items()]
    total_max_vals = [_round_pp(p, max_mult) * n for n, p in PRICES.items()]

    pp_min = min(pp_min_vals + pp_max_vals)
    pp_max = max(pp_min_vals + pp_max_vals)
    total_min = min(total_min_vals + total_max_vals)
    total_max = max(total_min_vals + total_max_vals)

    def _clp(n: int) -> str:
        return f"${n:,.0f}".replace(",", ".")

    template = cfg.get("message_template") or DP_MESSAGE_TEMPLATE_DEFAULT
    message = (
        template
        .replace("{PRECIO_MIN}", _clp(pp_min))
        .replace("{PRECIO_MAX}", _clp(pp_max))
        .replace("{TOTAL_MIN}", _clp(total_min))
        .replace("{TOTAL_MAX}", _clp(total_max))
    )

    return {
        "enabled": bool(cfg.get("enabled")),
        "min_mult": round(min_mult, 4),
        "max_mult": round(max_mult, 4),
        "price_per_person_min": pp_min,
        "price_per_person_max": pp_max,
        "price_total_min": total_min,
        "price_total_max": total_max,
        "message_template": template,
        "message": message,
    }


def resolve_price_message(message: str, link_url: Optional[str] = None) -> str:
    """Resolve the {LINK} placeholder left in build_dynamic_price_message()'s
    output. If link_url is given, substitutes it in place (WhatsApp bot —
    always wants a CTA link). If not, drops the whole line(s) containing the
    placeholder instead of leaving a dangling literal "{LINK}" in the text —
    used on the booking web page itself, where there's no per-client link to
    offer since the visitor is already inside the booking flow."""
    if "{LINK}" not in message:
        return message
    if link_url:
        return message.replace("{LINK}", link_url)
    lines = [ln for ln in message.split("\n") if "{LINK}" not in ln]
    cleaned = []
    prev_blank = False
    for ln in lines:
        blank = not ln.strip()
        if blank and prev_blank:
            continue
        cleaned.append(ln)
        prev_blank = blank
    return "\n".join(cleaned).strip()


# ── Booking email workflows (Booknetic-style multi-trigger) ─────────────────

TRIGGER_META: dict = {
    "booking_created": {
        "label": "Nueva reserva (pendiente pago)",
        "description": "Se envía al cliente justo al crear la reserva, antes de completar el pago.",
        "default_subject": "Recibimos tu reserva — {{booking_ref}}",
        "icon": "📋",
    },
    "booking_confirmed": {
        "label": "Pago confirmado",
        "description": "Se envía cuando el pago queda registrado correctamente (WooCommerce / Transbank).",
        "default_subject": "Reserva confirmada — {{booking_ref}}",
        "icon": "✅",
    },
    "booking_cancelled": {
        "label": "Reserva cancelada",
        "description": "Se envía cuando el estado de la reserva cambia a 'cancelled'.",
        "default_subject": "Tu reserva fue cancelada — {{booking_ref}}",
        "icon": "❌",
    },
    "booking_status_changed": {
        "label": "Estado cambiado por el admin",
        "description": "Se envía cuando el administrador cambia el estado manualmente (cualquier estado).",
        "default_subject": "Actualización de tu reserva — {{booking_ref}}",
        "icon": "🔄",
    },
    "booking_followup": {
        "label": "Seguimiento post-reserva",
        "description": (
            "Se envía automáticamente N horas después del horario de la reserva. "
            "Pide reseña en TripAdvisor y encuesta de satisfacción."
        ),
        "default_subject": "¡Gracias por navegar con nosotros! — {{booking_ref}}",
        "icon": "⭐",
        "extra_fields": [
            {
                "key": "hours_after",
                "label": "Horas después del horario de la reserva",
                "type": "number",
                "default": 2,
                "min": 1,
                "max": 72,
            }
        ],
    },
    "admin_new_lead": {
        "label": "Nuevo lead en formulario de reserva",
        "description": (
            "Se envía AL ADMINISTRADOR (no al cliente) cuando alguien completa "
            "sus datos y hace clic en 'Ir a pagar'."
        ),
        "default_subject": "🔔 Nuevo lead: {{customer_name}} — {{booking_date}} {{booking_time}}",
        "icon": "🔔",
        "recipient": "admin",
    },
    "admin_booking_confirmed": {
        "label": "Pago confirmado (notificación al operador)",
        "description": (
            "Se envía AL ADMINISTRADOR (no al cliente) cuando el pago queda confirmado. "
            "Ideal para recibir la notificación de nueva reserva pagada en tu correo."
        ),
        "default_subject": "✅ Reserva pagada: {{customer_name}} — {{booking_date}} {{booking_time}}",
        "icon": "✅",
        "recipient": "admin",
    },
    "admin_pending_payment": {
        "label": "Pago pendiente — recordatorio al operador (5 min)",
        "description": (
            "Se envía AL ADMINISTRADOR 5 minutos después de que un cliente avanzó al pago "
            "pero no lo completó. Incluye botón de WhatsApp para contactar al cliente."
        ),
        "default_subject": "⚠️ Sin pago: {{customer_name}} — {{booking_date}} {{booking_time}}",
        "icon": "⚠️",
        "recipient": "admin",
    },
    "customer_birthday": {
        "label": "Cumpleaños del cliente",
        "description": (
            "El servidor revisa cada día si algún cliente cumple años hoy. "
            "Requiere que el cliente ingrese su fecha de nacimiento al reservar."
        ),
        "default_subject": "¡Feliz cumpleaños de parte de HotBoat! 🎂",
        "icon": "🎂",
    },
}

# Triggers activos por defecto
_TRIGGERS_ENABLED_DEFAULT = {"booking_confirmed", "booking_created", "admin_new_lead", "admin_booking_confirmed", "admin_pending_payment"}


def seed_email_workflow_defaults() -> None:
    """
    Called once at startup: enable triggers that should be on by default
    but haven't been explicitly configured yet in the DB.
    This is idempotent — it never overwrites an explicitly saved setting.
    """
    try:
        raw = _json_setting("email_workflows", {})
        changed = False
        for trigger in _TRIGGERS_ENABLED_DEFAULT:
            if trigger not in raw:
                # Not yet touched by the user → seed as enabled
                raw[trigger] = {"enabled": True}
                changed = True
        if changed:
            set_setting("email_workflows", json.dumps(raw))
            logger.info("Email workflow defaults seeded: %s", _TRIGGERS_ENABLED_DEFAULT - set(raw.keys() - {k for k in raw}))
    except Exception as e:
        logger.warning(f"seed_email_workflow_defaults: {e}")


def get_email_workflows() -> dict:
    """Returns {trigger: {enabled, subject, body_html, ...extras}} for all known triggers."""
    raw = _json_setting("email_workflows", {})
    # Migrate legacy email_booking config into booking_confirmed
    legacy = _json_setting("email_booking", {})
    result = {}
    for trigger, meta in TRIGGER_META.items():
        saved = raw.get(trigger) or {}
        defaults_for_trigger: dict = {
            "enabled": trigger in _TRIGGERS_ENABLED_DEFAULT,
            "subject": meta["default_subject"],
            "body_html": "",
        }
        # Defaults for extra_fields (e.g. days_after)
        for ef in meta.get("extra_fields", []):
            defaults_for_trigger[ef["key"]] = ef["default"]
        if trigger == "booking_confirmed" and not saved and legacy:
            if "confirmation_enabled" in legacy:
                defaults_for_trigger["enabled"] = bool(legacy["confirmation_enabled"])
            if legacy.get("subject"):
                defaults_for_trigger["subject"] = legacy["subject"]
            if legacy.get("body_html"):
                defaults_for_trigger["body_html"] = legacy["body_html"]
        result[trigger] = {**defaults_for_trigger, **saved}
    return result


def get_email_workflow(trigger: str) -> dict:
    return get_email_workflows().get(trigger, {})


def set_email_workflow(trigger: str, cfg: dict) -> bool:
    if trigger not in TRIGGER_META:
        return False
    all_raw = _json_setting("email_workflows", {})
    existing = dict(all_raw.get(trigger) or {})
    for k in ("enabled", "subject", "body_html"):
        if k in cfg:
            existing[k] = cfg[k]
    # Extra fields specific to each trigger (e.g. days_after)
    for ef in TRIGGER_META[trigger].get("extra_fields", []):
        if ef["key"] in cfg:
            existing[ef["key"]] = cfg[ef["key"]]
    all_raw[trigger] = existing
    return set_setting("email_workflows", json.dumps(all_raw))


# Keep legacy alias so old call sites don't break during migration
def get_email_booking_config() -> dict:
    cfg = get_email_workflow("booking_confirmed")
    return {
        "confirmation_enabled": cfg.get("enabled", True),
        "on_payment_confirmed": True,
        "subject": cfg.get("subject", TRIGGER_META["booking_confirmed"]["default_subject"]),
        "body_html": cfg.get("body_html", ""),
    }


def set_email_booking_config(cfg: dict) -> bool:
    return set_email_workflow("booking_confirmed", {
        "enabled": cfg.get("confirmation_enabled", True),
        "subject": cfg.get("subject", ""),
        "body_html": cfg.get("body_html", ""),
    })


# ── Operating hours (available time slots for HotBoat) ───────────────────────

OPERATING_HOURS_DEFAULT = ["10:00", "18:00", "21:00"]


def get_operating_hours() -> list:
    """Return list of 'HH:MM' strings — the base available time slots."""
    raw = get_setting("operating_hours", "")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list) and parsed:
                return sorted(parsed)
        except Exception:
            pass
    return OPERATING_HOURS_DEFAULT.copy()


def set_operating_hours(hours: list) -> bool:
    """Store list of 'HH:MM' strings."""
    cleaned = sorted({h.strip() for h in hours if h.strip()})
    return set_setting("operating_hours", json.dumps(cleaned))


def get_operating_hours_as_ints() -> list:
    """Return operating hours as list of integers for compatibility."""
    result = []
    for h in get_operating_hours():
        try:
            result.append(int(h.split(":")[0]))
        except Exception:
            pass
    return result


def get_schedule_types() -> list:
    """Return the saved schedule-type profiles: [{id, name, hours:[HH:MM]}]."""
    raw = get_setting("schedule_types", "")
    if not raw:
        return []
    try:
        types = json.loads(raw)
        return types if isinstance(types, list) else []
    except Exception:
        return []


def get_urgency_modes() -> list:
    """Return the saved urgency-mode profiles: [{id, name, seed_times:[HH:MM], gap_hours:float}]."""
    raw = get_setting("urgency_modes", "")
    if not raw:
        return []
    try:
        modes = json.loads(raw)
        return modes if isinstance(modes, list) else []
    except Exception:
        return []


def get_day_schedule_hours_map(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> dict:
    """
    Map of {date_str: [hour_ints]} for days whose assigned profile is a
    schedule-type (custom hours). Days assigned an urgency-mode profile or no
    profile are absent — those fall back to the global operating hours.
    """
    types_by_id = {t.get("id"): t for t in get_schedule_types() if isinstance(t, dict)}
    if not types_by_id:
        return {}
    out: dict = {}
    for v in get_urgency_days(from_date, to_date):
        pk = v.get("profile_key")
        if not pk or pk not in types_by_id:
            continue
        hours = types_by_id[pk].get("hours") or []
        # Preservar 'HH:MM' (soporta media hora), no truncar a la hora entera.
        hhmm = sorted({str(h).strip() for h in hours if str(h).strip()})
        if hhmm:
            out[v["date"]] = hhmm
    return out


def get_day_duration_map(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> dict:
    """
    Map of {date_str: duration_hours} for days whose assigned profile (schedule
    type O urgency mode) define una duración de paseo propia. Días sin perfil o
    sin duración configurada quedan ausentes → usan la duración global.
    """
    profiles = {}
    for p in get_schedule_types():
        if isinstance(p, dict) and p.get("id"):
            profiles[p["id"]] = p
    for p in get_urgency_modes():
        if isinstance(p, dict) and p.get("id"):
            profiles[p["id"]] = p
    if not profiles:
        return {}
    out: dict = {}
    for v in get_urgency_days(from_date, to_date):
        pk = v.get("profile_key")
        prof = profiles.get(pk) if pk else None
        if not prof:
            continue
        dur = prof.get("duration_hours")
        try:
            dur = float(dur)
        except (TypeError, ValueError):
            dur = None
        if dur and dur > 0:
            out[v["date"]] = dur
    return out


def get_day_schedule_ghost_map(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> dict:
    """
    Map of {date_str: [ghost HH:MM]} for days whose assigned profile is a
    schedule-type that defines extra ghost (grey, non-bookable) slots.
    """
    types_by_id = {t.get("id"): t for t in get_schedule_types() if isinstance(t, dict)}
    if not types_by_id:
        return {}
    out: dict = {}
    for v in get_urgency_days(from_date, to_date):
        pk = v.get("profile_key")
        if not pk or pk not in types_by_id:
            continue
        ghosts = types_by_id[pk].get("ghost_times") or []
        if ghosts:
            out[v["date"]] = list(ghosts)
    return out


def get_day_urgency_config_map(
    from_date: Optional[date] = None,
    to_date: Optional[date] = None,
) -> dict:
    """
    Map of {date_str: {seed_times, gap_hours}} for days with an urgency-mode
    profile assigned via profile_key. Days with no urgency profile (or a
    schedule-type profile) are absent — those fall back to the global config.
    """
    modes_by_id = {m.get("id"): m for m in get_urgency_modes() if isinstance(m, dict)}
    if not modes_by_id:
        return {}
    out: dict = {}
    for v in get_urgency_days(from_date, to_date):
        pk = v.get("profile_key")
        if not pk or pk not in modes_by_id:
            continue
        mode = modes_by_id[pk]
        mode_ghosts = mode.get("ghost_times") or []
        day_ghosts  = v.get("ghost_times") or []
        combined    = list(dict.fromkeys(mode_ghosts + day_ghosts))
        out[v["date"]] = {
            "seed_times": mode.get("seed_times") or [],
            "gap_hours": float(mode.get("gap_hours") or 3),
            "ghost_times": combined,
        }
    return out


# ── Menu visibility settings ─────────────────────────────────────────────────
# Controls which sections appear in the WhatsApp bot menu AND in booking.html.

MENU_SETTINGS_DEFAULTS = {
    "show_experiencias": True,       # WhatsApp option 6 + booking page button
    "show_alojamientos": True,       # WhatsApp option 7 (aloj branch) + booking page button
    "show_packs": True,              # WhatsApp option 7 (packs branch) + booking page button
    "show_arma_pack": True,          # booking page "Arma tu Pack" button
    # Legacy key kept for backwards-compat; ignored in new code
    "show_packs_alojamientos": True,
}


def get_menu_settings() -> dict:
    raw = get_setting("menu_visibility", "")
    if raw:
        try:
            stored = json.loads(raw)
            result = MENU_SETTINGS_DEFAULTS.copy()
            result.update(stored)
            return result
        except Exception:
            pass
    return MENU_SETTINGS_DEFAULTS.copy()


def set_menu_settings(cfg: dict) -> bool:
    current = get_menu_settings()
    current.update(cfg)
    return set_setting("menu_visibility", json.dumps(current))
