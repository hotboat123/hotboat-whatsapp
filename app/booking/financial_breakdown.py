"""
Split ingreso_extras / costo_operativo_variable into Alojamiento, Experiencia, Extra
using extras_json + extras_visibility unit costs. Structural daily cost and
per-booking fixed costs are surfaced for P&L / cash-flow reporting.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import date, timedelta
from typing import Any, Dict, List, Set, Tuple

from app.db.connection import get_connection
from app.booking.operator_settings import get_setting

logger = logging.getLogger(__name__)

TOL = 0.5  # pesos / rounding

FIN_STRUCTURE_KEY = "financial_structure"


def _slugify(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


def get_financial_structure() -> Dict[str, Any]:
    raw = get_setting(FIN_STRUCTURE_KEY, "")
    default: Dict[str, Any] = {
        "costo_fijo_diario_prorrateado": 0,
        "experience_slug_whitelist": [],
    }
    if not raw:
        return default.copy()
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return default.copy()
        out = default.copy()
        out.update(data)
        wl = out.get("experience_slug_whitelist") or []
        out["experience_slug_whitelist"] = [str(x).lower() for x in wl]
        return out
    except Exception:
        return default.copy()


def load_extra_cost_catalog() -> Dict[str, float]:
    """Normalized keys -> unit cost (extras_visibility.costo)."""
    out: Dict[str, float] = {}
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT extra_name_lower, COALESCE(name, ''), COALESCE(costo, 0)
                    FROM extras_visibility
                """)
                for el, name, cost in cur.fetchall():
                    c = float(cost or 0)
                    el = str(el or "").lower()
                    if el:
                        out[el] = c
                        out[_slugify(el)] = c
                    if name:
                        out[str(name).lower()] = c
                        out[_slugify(name)] = c
    except Exception as e:
        logger.warning("load_extra_cost_catalog: %s", e)
    return out


def _extras_json_as_dict(raw: Any) -> Dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        s = raw.strip()
        if not s:
            return {}
        try:
            j = json.loads(s)
            return j if isinstance(j, dict) else {}
        except Exception:
            return {}
    return {}


def _line_qty(val: Any) -> float:
    if isinstance(val, dict):
        return float(val.get("qty") or val.get("quantity") or 1)
    if isinstance(val, (int, float)) and val:
        return float(val)
    return 1.0


def _line_revenue(val: Any) -> float:
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        q = _line_qty(val)
        up = val.get("unit_price")
        if up is not None:
            return q * float(up or 0)
        for k in ("amount", "total"):
            if val.get(k) is not None:
                return float(val[k] or 0)
        return 0.0
    return 0.0


def _dict_category_override(val: Any) -> str | None:
    if not isinstance(val, dict):
        return None
    t = str(val.get("tipo") or val.get("type") or val.get("category") or "").lower()
    if t in ("experiencia", "experience"):
        return "exp"
    if t in ("alojamiento", "aloj", "lodging"):
        return "aloj"
    if t in ("extra", "consumo", "retail"):
        return "extra"
    return None


def _classify_line(key: str, val: Any, wl: Set[str]) -> str:
    ov = _dict_category_override(val)
    if ov:
        return ov
    lk = str(key).lower()
    if lk in wl:
        return "exp"
    if lk.startswith("aloj"):
        return "aloj"
    if lk.startswith("experiencia") or lk.startswith("pack_exp") or lk.startswith("exp__"):
        return "exp"
    if lk.startswith("exp"):
        return "exp"
    return "extra"


def _catalog_cost_for_key(key: str, val: Any, cmap: Dict[str, float]) -> float | None:
    lk = str(key).lower()
    candidates = [
        lk,
        _slugify(key),
        lk.split("__", 1)[-1] if "__" in lk else lk,
    ]
    for c in candidates:
        if c in cmap:
            return float(cmap[c])
    if isinstance(val, dict) and val.get("unit_cost") is not None:
        return float(val["unit_cost"])
    return None


def _reconcile_three(inc: float, a: float, e: float, x: float) -> Tuple[float, float, float]:
    """Reconcile (a,e,x) to sum to inc when JSON is incomplete."""
    parsed = a + e + x
    if inc <= TOL:
        return 0.0, 0.0, 0.0
    if parsed >= inc - TOL:
        if parsed > inc + TOL and parsed > 0:
            s = inc / parsed
            return a * s, e * s, x * s
        return a, e, x
    rem = inc - parsed
    present = []
    if a > TOL:
        present.append("a")
    if e > TOL:
        present.append("e")
    if x > TOL:
        present.append("x")
    if len(present) == 1:
        if present[0] == "a":
            return a + rem, e, x
        if present[0] == "e":
            return a, e + rem, x
        return a, e, x + rem
    if parsed > TOL:
        return a + rem * a / parsed, e + rem * e / parsed, x + rem * x / parsed
    return rem / 3, rem / 3, rem / 3


def split_booking_financials(
    booking: Dict[str, Any],
    cost_catalog: Dict[str, float],
    exp_whitelist: Set[str],
) -> Dict[str, int]:
    """
    Returns integer CLP fields for one booking row.
    ingreso_* from extras reconcile to ingreso_extras; ingreso_reserva passthrough.
    Variable cost split sums to costo_variable (within tolerance); row total drift to extra.
    """
    ing_res = float(booking.get("ingreso_reserva") or 0)
    inc = float(booking.get("ingreso_extras") or 0)
    var_total = float(booking.get("costo_variable") or 0)
    c_fijo = float(booking.get("costo_fijo") or 0)
    c_total = float(booking.get("costo_total") or 0)

    j = _extras_json_as_dict(booking.get("extras_json"))

    rev_a = rev_e = rev_x = 0.0
    cv_a = cv_e = cv_x = 0.0

    for key, val in j.items():
        cat = _classify_line(key, val, exp_whitelist)
        rev = _line_revenue(val)
        qty = _line_qty(val)
        uc = _catalog_cost_for_key(key, val, cost_catalog)
        line_cost = (uc * qty) if uc is not None else 0.0

        if cat == "aloj":
            rev_a += rev
            cv_a += line_cost
        elif cat == "exp":
            rev_e += rev
            cv_e += line_cost
        else:
            rev_x += rev
            cv_x += line_cost

    rev_a, rev_e, rev_x = _reconcile_three(inc, rev_a, rev_e, rev_x)

    cat_cv = cv_a + cv_e + cv_x
    if var_total > TOL:
        if cat_cv > TOL:
            if cat_cv > var_total + TOL:
                s = var_total / cat_cv
                cv_a, cv_e, cv_x = cv_a * s, cv_e * s, cv_x * s
            else:
                rem = var_total - cat_cv
                inc_cat = rev_a + rev_e + rev_x
                if inc_cat > TOL:
                    cv_a += rem * rev_a / inc_cat
                    cv_e += rem * rev_e / inc_cat
                    cv_x += rem * rev_x / inc_cat
                else:
                    cv_x += rem
        else:
            inc_cat = rev_a + rev_e + rev_x
            if inc_cat > TOL:
                cv_a = var_total * rev_a / inc_cat
                cv_e = var_total * rev_e / inc_cat
                cv_x = var_total * rev_x / inc_cat
            else:
                cv_x = var_total

    parts = c_fijo + cv_a + cv_e + cv_x
    drift = c_total - parts
    if abs(drift) > TOL:
        cv_x += drift

    return {
        "ingreso_reserva": int(round(ing_res)),
        "ingreso_aloj": int(round(rev_a)),
        "ingreso_exp": int(round(rev_e)),
        "ingreso_extra": int(round(rev_x)),
        "costo_fijo_reserva": int(round(c_fijo)),
        "cv_aloj": int(round(cv_a)),
        "cv_exp": int(round(cv_e)),
        "cv_extra": int(round(cv_x)),
    }


def iso_dates_inclusive(d0: date, d1: date) -> List[str]:
    out: List[str] = []
    d = d0
    while d <= d1:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def new_empty_day(fecha: str) -> Dict[str, Any]:
    return {
        "fecha": fecha,
        "n_reservas": 0,
        "gross": 0,
        "commission_deduction": 0,
        "net_income": 0,
        "costo_operacional": 0,
        "marketing": 0,
        "costo_estructural": 0,
        "ingreso_reserva": 0,
        "ingreso_aloj": 0,
        "ingreso_exp": 0,
        "ingreso_extra": 0,
        "costo_fijo_reservas": 0,
        "cv_aloj": 0,
        "cv_exp": 0,
        "cv_extra": 0,
        "resultado": 0,
        "bookings": [],
    }


def merge_day_breakdown(dst: Dict[str, Any], split: Dict[str, int]) -> None:
    dst["ingreso_reserva"] = dst.get("ingreso_reserva", 0) + split["ingreso_reserva"]
    dst["ingreso_aloj"] = dst.get("ingreso_aloj", 0) + split["ingreso_aloj"]
    dst["ingreso_exp"] = dst.get("ingreso_exp", 0) + split["ingreso_exp"]
    dst["ingreso_extra"] = dst.get("ingreso_extra", 0) + split["ingreso_extra"]
    dst["costo_fijo_reservas"] = dst.get("costo_fijo_reservas", 0) + split["costo_fijo_reserva"]
    dst["cv_aloj"] = dst.get("cv_aloj", 0) + split["cv_aloj"]
    dst["cv_exp"] = dst.get("cv_exp", 0) + split["cv_exp"]
    dst["cv_extra"] = dst.get("cv_extra", 0) + split["cv_extra"]


def apply_structural_to_days(
    days: Dict[str, Dict[str, Any]],
    d_from: date,
    d_to: date,
    daily_rate: float,
) -> None:
    rate = int(round(float(daily_rate or 0)))
    for ds in iso_dates_inclusive(d_from, d_to):
        if ds not in days:
            days[ds] = new_empty_day(ds)
        days[ds]["costo_estructural"] = rate


def finalize_pnl_day(d: Dict[str, Any]) -> None:
    """resultado = net - opex reservas - marketing - estructura."""
    struct = int(d.get("costo_estructural") or 0)
    d["resultado"] = (
        int(d["net_income"])
        - int(d["costo_operacional"])
        - int(d["marketing"])
        - struct
    )


def aggregate_breakdown_into_week_month(
    agg: Dict[str, Any],
    d: Dict[str, Any],
) -> None:
    for k in (
        "ingreso_reserva",
        "ingreso_aloj",
        "ingreso_exp",
        "ingreso_extra",
        "costo_fijo_reservas",
        "cv_aloj",
        "cv_exp",
        "cv_extra",
        "costo_estructural",
    ):
        agg[k] = agg.get(k, 0) + int(d.get(k, 0))
