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
    Urgency algorithm:

    • Sin reservas → mostrar las horas semilla (seed_times) que estén libres.
    • Con reservas → para CADA reserva en X, ofrecer X - gap y X + gap.
      Los seed_times ya NO se muestran; los reemplazan los slots de expansión.

    Ejemplos con seeds=[10,18,21] gap=3:
      - Sin reservas          → [10:00, 18:00, 21:00]
      - Reserva a las 18:00   → [15:00, 21:00]
      - Reserva a las 21:00   → [18:00] (24:00 fuera de rango)
      - Reservas 18:00+21:00  → [15:00, 18:00, 24:00→ignorado] = [15:00, 18:00]
    """
    if not available_times:
        return []

    cfg = config if config is not None else get_urgency_config()
    seed_times: list = cfg.get("seed_times") or get_operating_hours()
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

    if not booked_times:
        # Sin reservas: mostrar seed times disponibles
        for st in seed_times:
            if st in free_set:
                pool.add(st)
            else:
                # Buscar slot libre más cercano al seed dentro de tolerancia
                target = _to_min(st)
                candidates = [t for t in free_set if abs(_to_min(t) - target) <= TOLERANCE]
                if candidates:
                    pool.add(min(candidates, key=lambda t: abs(_to_min(t) - target)))
    else:
        # Con reservas: para cada reserva mostrar reserva ± gap
        for bt in booked_times:
            bt_min = _to_min(bt)
            for delta in (-gap_min, gap_min):
                target = bt_min + delta
                # Buscar slot libre más cercano al target dentro de tolerancia
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
    seed_times: list = cfg.get("seed_times") or get_operating_hours()
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

    return sorted(fake, key=_to_min)


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
            "El servidor revisa cada día si corresponde enviar este correo. "
            "Útil para pedir reseña, ofrecer descuento próximo viaje, etc."
        ),
        "default_subject": "¡Gracias por navegar con nosotros! — {{booking_ref}}",
        "icon": "⭐",
        "extra_fields": [
            {
                "key": "days_after",
                "label": "Días después de la reserva",
                "type": "number",
                "default": 5,
                "min": 1,
                "max": 180,
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
_TRIGGERS_ENABLED_DEFAULT = {"booking_confirmed"}


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
