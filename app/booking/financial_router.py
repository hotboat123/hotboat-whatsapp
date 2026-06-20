"""Financial module: P&L dashboard and Cash Flow statement."""
import json
import logging
import calendar as _cal
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel

from app.db.connection import get_connection
from app.booking.operator_settings import get_setting, set_setting
from app.booking.financial_breakdown import (
    aggregate_breakdown_into_week_month,
    apply_structural_to_days,
    booking_discount_total_clp,
    finalize_pnl_day,
    get_financial_structure,
    iso_dates_inclusive,
    load_aloj_cost_catalog,
    load_extra_cost_catalog,
    merge_day_breakdown,
    merge_day_discount,
    new_empty_day,
    split_booking_financials,
)

logger = logging.getLogger(__name__)
financial_router = APIRouter()

CHILE_TZ = __import__("zoneinfo").ZoneInfo("America/Santiago")

# Statuses that count as revenue in P&L and cash-flow reports
CONFIRMED_STATUSES = ('confirmed', 'paid', 'aprobado')

# ── Default commission config ─────────────────────────────────────────────────

DEFAULT_COMMISSIONS = {
    "transbank_credito": {"rate": 0.028, "iva_included": True},
    "transbank_debito":  {"rate": 0.012, "iva_included": False},
    "transbank":         {"rate": 0.028, "iva_included": True},
    "mercadopago":       {"rate": 0.035, "iva_included": False},
    "transferencia":     {"rate": 0.0,   "iva_included": False},
    "efectivo":          {"rate": 0.0,   "iva_included": False},
    "cheque":            {"rate": 0.0,   "iva_included": False},
    "otro":              {"rate": 0.0,   "iva_included": False},
}

IVA_RATE = 0.19


def _get_commissions() -> Dict[str, Dict]:
    raw = get_setting("financial_commissions", "")
    if raw:
        try:
            return {**DEFAULT_COMMISSIONS, **json.loads(raw)}
        except Exception:
            pass
    return DEFAULT_COMMISSIONS


def _net_amount(amount: float, method: str, commissions: Dict) -> float:
    """Return net amount after IVA deduction and commission for a payment method."""
    cfg = commissions.get(method, {"rate": 0.0, "iva_included": False})
    base = amount / (1 + IVA_RATE) if cfg["iva_included"] else amount
    return base * (1 - cfg["rate"])


def _fmt_int(v: Any) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


# ── DB helpers ────────────────────────────────────────────────────────────────

def _get_bookings_range(date_from: date, date_to: date) -> List[Dict]:
    """Return bookings with pagos and descuentos for a date range."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    COALESCE(fecha::text, ''),
                    COALESCE(ingreso_reserva, 0),
                    COALESCE(ingreso_extras, 0),
                    COALESCE(ingreso_total, 0),
                    COALESCE(costo_operativo_fijo, 0),
                    COALESCE(costo_operativo_variable, 0),
                    COALESCE(costo_operativo_total, 0),
                    COALESCE(pagos,      '[]'::jsonb),
                    COALESCE(descuentos, '[]'::jsonb),
                    COALESCE(coupon_discount, 0),
                    COALESCE(nombre_cliente, ''),
                    COALESCE(status, ''),
                    COALESCE(num_personas::text, '0'),
                    COALESCE(extras_json, '{}'::jsonb)
                FROM all_appointments
                WHERE fecha BETWEEN %s AND %s
                  AND status = ANY(%s)
                ORDER BY fecha, id
            """, (date_from, date_to, list(CONFIRMED_STATUSES)))
            cols = ["id", "fecha", "ingreso_reserva", "ingreso_extras",
                    "ingreso_total", "costo_fijo", "costo_variable", "costo_total",
                    "pagos", "descuentos", "coupon_discount", "nombre_cliente", "status", "num_personas",
                    "extras_json"]
            rows = []
            for r in cur.fetchall():
                d = dict(zip(cols, r))
                d["ingreso_total"]  = float(d["ingreso_total"])
                d["ingreso_reserva"]= float(d["ingreso_reserva"])
                d["ingreso_extras"] = float(d["ingreso_extras"])
                d["costo_total"]    = float(d["costo_total"])
                d["costo_fijo"]     = float(d["costo_fijo"])
                d["costo_variable"] = float(d["costo_variable"])
                d["coupon_discount"] = float(d.get("coupon_discount") or 0)
                pagos = d["pagos"]
                if isinstance(pagos, str):
                    pagos = json.loads(pagos)
                d["pagos"] = pagos if isinstance(pagos, list) else []
                desc = d["descuentos"]
                if isinstance(desc, str):
                    desc = json.loads(desc)
                d["descuentos"] = desc if isinstance(desc, list) else []
                ex = d["extras_json"]
                if isinstance(ex, str):
                    try:
                        ex = json.loads(ex) if ex.strip() else {}
                    except Exception:
                        ex = {}
                d["extras_json"] = ex if isinstance(ex, dict) else {}
                rows.append(d)
            return rows


def _get_bookings_cashflow_range(date_from: date, date_to: date) -> List[Dict]:
    """
    Return bookings relevant for cashflow/inflows in a date range.
    Includes:
    - bookings whose `fecha` is within range (needed for opex + no-pagos fallback)
    - bookings with any pago `date` within range (anticipos/abonos for other booking dates)
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    id,
                    COALESCE(fecha::text, ''),
                    COALESCE(ingreso_reserva, 0),
                    COALESCE(ingreso_extras, 0),
                    COALESCE(ingreso_total, 0),
                    COALESCE(costo_operativo_fijo, 0),
                    COALESCE(costo_operativo_variable, 0),
                    COALESCE(costo_operativo_total, 0),
                    COALESCE(pagos,      '[]'::jsonb),
                    COALESCE(descuentos, '[]'::jsonb),
                    COALESCE(nombre_cliente, ''),
                    COALESCE(status, ''),
                    COALESCE(num_personas::text, '0'),
                    COALESCE(extras_json, '{}'::jsonb)
                FROM all_appointments
                WHERE status = ANY(%s)
                  AND (
                    fecha BETWEEN %s AND %s
                    OR EXISTS (
                        SELECT 1
                        FROM jsonb_array_elements(COALESCE(pagos, '[]'::jsonb)) AS p
                        WHERE (p->>'date') ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                          AND LEFT(p->>'date', 10)::date BETWEEN %s AND %s
                    )
                  )
                ORDER BY fecha, id
            """, (list(CONFIRMED_STATUSES), date_from, date_to, date_from, date_to))
            cols = ["id", "fecha", "ingreso_reserva", "ingreso_extras",
                    "ingreso_total", "costo_fijo", "costo_variable", "costo_total",
                    "pagos", "descuentos", "nombre_cliente", "status", "num_personas",
                    "extras_json"]
            rows = []
            for r in cur.fetchall():
                d = dict(zip(cols, r))
                d["ingreso_total"] = float(d["ingreso_total"])
                d["ingreso_reserva"] = float(d["ingreso_reserva"])
                d["ingreso_extras"] = float(d["ingreso_extras"])
                d["costo_total"] = float(d["costo_total"])
                d["costo_fijo"] = float(d["costo_fijo"])
                d["costo_variable"] = float(d["costo_variable"])
                pagos = d["pagos"]
                if isinstance(pagos, str):
                    pagos = json.loads(pagos)
                d["pagos"] = pagos if isinstance(pagos, list) else []
                desc = d["descuentos"]
                if isinstance(desc, str):
                    desc = json.loads(desc)
                d["descuentos"] = desc if isinstance(desc, list) else []
                ex = d["extras_json"]
                if isinstance(ex, str):
                    try:
                        ex = json.loads(ex) if ex.strip() else {}
                    except Exception:
                        ex = {}
                d["extras_json"] = ex if isinstance(ex, dict) else {}
                rows.append(d)
            return rows


_DATE_COL_CANDIDATES   = ("fecha", "date", "day", "dia", "cost_date", "fecha_costo", "report_date", "cost_day")
# total_spent first: marketing_costs_daily view (Meta ads rollup)
_AMOUNT_COL_CANDIDATES = (
    "total_spent",
    "amount",
    "total_amount",
    "monto",
    "costo",
    "cost",
    "total",
    "sum_amount",
    "total_cost",
)


def _detect_col(available: set, candidates) -> Optional[str]:
    """Return the first matching column name (case-insensitive) from candidates."""
    lowered = {c.lower(): c for c in available}
    for cand in candidates:
        if cand in lowered:
            return lowered[cand]
    return None


def _get_marketing_costs_range(date_from: date, date_to: date) -> List[Dict]:
    """
    Read marketing costs for a date range. Tries the `marketing_costs_daily`
    view first (auto-detects date column and amount: e.g. `total_spent`);
    if the view is missing or has no recognizable columns, falls back to the
    base `marketing_costs` table.
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'marketing_costs_daily'
            """)
            view_cols = {r[0] for r in cur.fetchall()}

            source_table = None
            date_col     = None
            amount_col   = None

            if view_cols:
                date_col   = _detect_col(view_cols, _DATE_COL_CANDIDATES)
                amount_col = _detect_col(view_cols, _AMOUNT_COL_CANDIDATES)
                if date_col and amount_col:
                    source_table = "marketing_costs_daily"
                    source_cols  = view_cols

            if source_table is None:
                # Fallback to the base table
                cur.execute("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = 'marketing_costs'
                """)
                base_cols = {r[0] for r in cur.fetchall()}
                if not base_cols:
                    logger.warning("No marketing_costs source available; returning empty")
                    return []
                date_col   = _detect_col(base_cols, _DATE_COL_CANDIDATES) or "fecha"
                amount_col = _detect_col(base_cols, _AMOUNT_COL_CANDIDATES) or "amount"
                source_table = "marketing_costs"
                source_cols  = base_cols

            has_id       = "id"       in source_cols
            has_category = "category" in source_cols
            has_notes    = "notes"    in source_cols

            select_parts = []
            if has_id: select_parts.append("id")
            select_parts.append(f"{date_col}::text AS fecha")
            select_parts.append(f"{amount_col} AS amount")
            if has_category: select_parts.append("category")
            if has_notes:    select_parts.append("notes")

            try:
                cur.execute(
                    f"""
                    SELECT {', '.join(select_parts)}
                    FROM {source_table}
                    WHERE {date_col} BETWEEN %s AND %s
                    ORDER BY {date_col}
                    """,
                    (date_from, date_to),
                )
                rows = cur.fetchall()
            except Exception as e:
                logger.warning("marketing costs query failed on %s: %s — returning empty",
                               source_table, e)
                return []

            results = []
            for r in rows:
                idx = 0
                row: Dict = {}
                if has_id: row["id"] = r[idx]; idx += 1
                else:      row["id"] = None
                row["fecha"]    = r[idx]; idx += 1
                row["amount"]   = float(r[idx] or 0); idx += 1
                row["category"] = r[idx] if has_category else None
                if has_category: idx += 1
                row["notes"]    = r[idx] if has_notes else None
                results.append(row)
            return results


def _get_budget(year: int, month: int) -> Dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Idempotent migration — adds zone columns if they don't exist yet
            for col in ("aloj_budget", "exp_budget", "extra_budget", "reserva_budget"):
                cur.execute(
                    f"ALTER TABLE financial_budget ADD COLUMN IF NOT EXISTS {col} NUMERIC DEFAULT 0"
                )
            conn.commit()
            cur.execute("""
                SELECT income_budget, costs_budget, marketing_budget, notes,
                       COALESCE(aloj_budget,0), COALESCE(exp_budget,0),
                       COALESCE(extra_budget,0), COALESCE(reserva_budget,0)
                FROM financial_budget WHERE year=%s AND month=%s
            """, (year, month))
            r = cur.fetchone()
            if r:
                return {"income_budget": float(r[0]), "costs_budget": float(r[1]),
                        "marketing_budget": float(r[2]), "notes": r[3] or "",
                        "aloj_budget": float(r[4]), "exp_budget": float(r[5]),
                        "extra_budget": float(r[6]), "reserva_budget": float(r[7])}
            return {"income_budget": 0, "costs_budget": 0, "marketing_budget": 0, "notes": "",
                    "aloj_budget": 0, "exp_budget": 0, "extra_budget": 0, "reserva_budget": 0}


# ── P&L calculation core ──────────────────────────────────────────────────────

def _calc_booking_pnl(
    booking: Dict,
    commissions: Dict,
    gross_override: Optional[float] = None,
    costo_override: Optional[float] = None,
) -> Dict:
    """Calculate P&L fields for a single booking."""
    gross = float(gross_override if gross_override is not None else booking["ingreso_total"])
    # Commission deduction based on pagos methods
    total_pago_amount = sum(float(p.get("amount", 0) or 0) for p in booking["pagos"])
    commission_deduction = 0.0
    for p in booking["pagos"]:
        amt = float(p.get("amount", 0) or 0)
        method = p.get("method", "otro")
        net = _net_amount(amt, method, commissions)
        commission_deduction += amt - net

    # If there are no pagos yet, assume transferencia (no commission)
    net_income = gross - commission_deduction
    costo = float(costo_override if costo_override is not None else booking["costo_total"])
    return {
        "gross":                _fmt_int(gross),
        "commission_deduction": _fmt_int(commission_deduction),
        "net_income":           _fmt_int(net_income),
        "costo_operacional":    _fmt_int(costo),
        "pagos_received":       _fmt_int(total_pago_amount),
    }


def _build_pnl_days(
    bookings: List[Dict],
    marketing: List[Dict],
    commissions: Dict,
    d_from: date,
    d_to: date,
) -> Dict[str, Dict]:
    """Build per-day P&L dict with income/cost breakdown and structural daily cost."""
    structure = get_financial_structure()
    daily_struct = float(structure.get("costo_fijo_diario_prorrateado") or 0)
    costo_por_reserva = float(structure.get("costo_operativo_por_reserva") or 18000)
    wl = set(structure.get("experience_slug_whitelist") or [])
    cost_catalog = load_extra_cost_catalog()
    aloj_cost_catalog = load_aloj_cost_catalog()

    mkt_by_day: Dict[str, float] = defaultdict(float)
    for m in marketing:
        mkt_by_day[m["fecha"]] += m["amount"]

    days: Dict[str, Dict] = {}
    for b in bookings:
        day = b["fecha"]
        if day not in days:
            days[day] = new_empty_day(day)
        sp = split_booking_financials(b, cost_catalog, wl, aloj_cost_catalog)
        # Use ingreso_total as authoritative gross (coupon already baked in); only deduct manual descuentos
        gross_total  = float(b.get("ingreso_total") or 0)
        manual_disc  = _sum_descuentos(b.get("descuentos") or [])
        disc_applied = min(max(0, int(round(manual_disc))), max(0, int(round(gross_total))))
        gross_split  = gross_total - float(disc_applied)

        pnl = _calc_booking_pnl(
            b,
            commissions,
            gross_override=gross_split,
            costo_override=costo_por_reserva,
        )
        d = days[day]
        d["n_reservas"] += 1
        d["gross"] += pnl["gross"]
        d["commission_deduction"] += pnl["commission_deduction"]
        d["net_income"] += pnl["net_income"]
        d["costo_operacional"] += pnl["costo_operacional"]
        merge_day_breakdown(d, sp)
        merge_day_discount(d, disc_applied)
        d["bookings"].append({
            "id":               b["id"],
            "nombre_cliente":   b["nombre_cliente"],
            "ingreso_total":    pnl["gross"],
            "commission":       pnl["commission_deduction"],
            "net_income":       pnl["net_income"],
            "costo":            pnl["costo_operacional"],
            "pagos":            b["pagos"],
            "ingreso_reserva":  sp["ingreso_reserva"],
            "ingreso_aloj":     sp["ingreso_aloj"],
            "ingreso_exp":      sp["ingreso_exp"],
            "ingreso_extra":    sp["ingreso_extra"],
            "descuentos_aplicados": disc_applied,
            "cv_aloj":          sp["cv_aloj"],
            "cv_exp":           sp["cv_exp"],
            "cv_extra":         sp["cv_extra"],
        })

    # Apply structural cost over full calendar months so partial-range filters still
    # get the complete month's fixed cost (not just the days inside the filter window).
    _struct_from = date(d_from.year, d_from.month, 1)
    _struct_to   = date(d_to.year, d_to.month, _cal.monthrange(d_to.year, d_to.month)[1])
    apply_structural_to_days(days, _struct_from, _struct_to, daily_struct)

    all_days_with_mkt = set(days.keys()) | set(mkt_by_day.keys())
    for day in all_days_with_mkt:
        if day not in days:
            days[day] = new_empty_day(day)
        days[day]["marketing"] = _fmt_int(mkt_by_day.get(day, 0))
        finalize_pnl_day(days[day])

    return days


def _aggregate_weeks(days: Dict[str, Dict]) -> List[Dict]:
    weeks: Dict[str, Dict] = {}
    for day_str, d in sorted(days.items()):
        dt = date.fromisoformat(day_str)
        # ISO week key: YYYY-Www
        week_key = dt.strftime("%G-W%V")
        week_start = (dt - timedelta(days=dt.weekday())).isoformat()
        week_end = (dt - timedelta(days=dt.weekday()) + timedelta(days=6)).isoformat()
        if week_key not in weeks:
            weeks[week_key] = {
                "week": week_key, "week_start": week_start, "week_end": week_end,
                "n_reservas": 0, "gross": 0, "commission_deduction": 0,
                "net_income": 0, "costo_operacional": 0, "marketing": 0, "resultado": 0,
                "costo_estructural": 0,
                "ingreso_reserva": 0, "ingreso_aloj": 0, "ingreso_exp": 0, "ingreso_extra": 0,
                "total_descuentos": 0,
                "cv_aloj": 0, "cv_exp": 0, "cv_extra": 0,
                "days": [],
            }
        w = weeks[week_key]
        w["n_reservas"]           += d["n_reservas"]
        w["gross"]                += d["gross"]
        w["commission_deduction"] += d["commission_deduction"]
        w["net_income"]           += d["net_income"]
        w["costo_operacional"]    += d["costo_operacional"]
        w["marketing"]            += d["marketing"]
        w["resultado"]            += d["resultado"]
        aggregate_breakdown_into_week_month(w, d)
        w["days"].append(d)
    return list(weeks.values())


def _aggregate_months(days: Dict[str, Dict]) -> List[Dict]:
    months: Dict[str, Dict] = {}
    for day_str, d in sorted(days.items()):
        month_key = day_str[:7]  # YYYY-MM
        if month_key not in months:
            months[month_key] = {
                "month": month_key,
                "n_reservas": 0, "gross": 0, "commission_deduction": 0,
                "net_income": 0, "costo_operacional": 0, "marketing": 0, "resultado": 0,
                "costo_estructural": 0,
                "ingreso_reserva": 0, "ingreso_aloj": 0, "ingreso_exp": 0, "ingreso_extra": 0,
                "total_descuentos": 0,
                "cv_aloj": 0, "cv_exp": 0, "cv_extra": 0,
                "days": [],
            }
        m = months[month_key]
        m["n_reservas"]           += d["n_reservas"]
        m["gross"]                += d["gross"]
        m["commission_deduction"] += d["commission_deduction"]
        m["net_income"]           += d["net_income"]
        m["costo_operacional"]    += d["costo_operacional"]
        m["marketing"]            += d["marketing"]
        m["resultado"]            += d["resultado"]
        aggregate_breakdown_into_week_month(m, d)
        m["days"].append(d)
    return list(months.values())


# ── Cash Flow calculation core ────────────────────────────────────────────────

def _build_cashflow_days(
    bookings: List[Dict],
    marketing: List[Dict],
    commissions: Dict,
    d_from: date,
    d_to: date,
) -> Dict[str, Dict]:
    """Build per-day cash flow based on actual payment dates."""
    structure = get_financial_structure()
    daily_struct = float(structure.get("costo_fijo_diario_prorrateado") or 0)
    costo_por_reserva = float(structure.get("costo_operativo_por_reserva") or 18000)
    wl = set(structure.get("experience_slug_whitelist") or [])
    cost_catalog = load_extra_cost_catalog()
    aloj_cost_catalog = load_aloj_cost_catalog()

    # Outflows: operational costs on booking date (total) + breakdown
    opex_by_day: Dict[str, float] = defaultdict(float)
    cf_opex_detail: Dict[str, Dict[str, int]] = defaultdict(
        lambda: {"cv_aloj": 0, "cv_exp": 0, "cv_extra": 0, "costo_fijo": 0}
    )
    for b in bookings:
        opex_by_day[b["fecha"]] += costo_por_reserva
        sp = split_booking_financials(b, cost_catalog, wl, aloj_cost_catalog)
        od = cf_opex_detail[b["fecha"]]
        od["cv_aloj"] += sp["cv_aloj"]
        od["cv_exp"] += sp["cv_exp"]
        od["cv_extra"] += sp["cv_extra"]
        od["costo_fijo"] = 0

    # Outflows: marketing
    mkt_by_day: Dict[str, float] = defaultdict(float)
    for m in marketing:
        mkt_by_day[m["fecha"]] += m["amount"]

    # Inflows: pagos by payment date (net of commission).
    # If a booking has no pagos, fall back to ingreso_total on the booking date.
    inflows_by_day: Dict[str, List[Dict]] = defaultdict(list)
    for b in bookings:
        pagos = b["pagos"]
        if not pagos:
            # No payment records — treat the full ingreso_total as received on booking date
            amt = b["ingreso_total"]
            if amt and b["fecha"]:
                net = _net_amount(amt, "transferencia", commissions)
                inflows_by_day[b["fecha"]].append({
                    "booking_id":     b["id"],
                    "nombre_cliente": b["nombre_cliente"],
                    "amount_bruto":   _fmt_int(amt),
                    "commission":     0,
                    "amount_neto":    _fmt_int(net),
                    "method":         "sin registro",
                })
        else:
            for p in pagos:
                pago_date = p.get("date") or b["fecha"]
                if not pago_date:
                    continue
                amt = float(p.get("amount", 0) or 0)
                method = p.get("method", "otro")
                net = _net_amount(amt, method, commissions)
                commission = amt - net
                inflows_by_day[pago_date].append({
                    "booking_id":     b["id"],
                    "nombre_cliente": b["nombre_cliente"],
                    "amount_bruto":   _fmt_int(amt),
                    "commission":     _fmt_int(commission),
                    "amount_neto":    _fmt_int(net),
                    "method":         method,
                })

    all_days = (
        set(opex_by_day.keys())
        | set(mkt_by_day.keys())
        | set(inflows_by_day.keys())
        | set(iso_dates_inclusive(d_from, d_to))
    )

    days: Dict[str, Dict] = {}
    struct_int = int(round(daily_struct))
    for day in all_days:
        try:
            dt = date.fromisoformat(day)
            in_range = d_from <= dt <= d_to
        except ValueError:
            in_range = False
        out_struct = struct_int if in_range else 0

        total_inflow_neto = sum(p["amount_neto"] for p in inflows_by_day[day])
        total_inflow_bruto = sum(p["amount_bruto"] for p in inflows_by_day[day])
        total_commission = sum(p["commission"] for p in inflows_by_day[day])
        outflow_opex = _fmt_int(opex_by_day[day])
        outflow_mkt = _fmt_int(mkt_by_day[day])
        det = cf_opex_detail[day]
        total_outflow = outflow_opex + outflow_mkt + out_struct
        days[day] = {
            "fecha":              day,
            "inflow_bruto":       _fmt_int(total_inflow_bruto),
            "inflow_commission":  _fmt_int(total_commission),
            "inflow_neto":        _fmt_int(total_inflow_neto),
            "outflow_opex":       outflow_opex,
            "outflow_marketing":  outflow_mkt,
            "outflow_estructural": out_struct,
            "outflow_cv_aloj":    int(det["cv_aloj"]),
            "outflow_cv_exp":     int(det["cv_exp"]),
            "outflow_cv_extra":   int(det["cv_extra"]),
            "outflow_costo_fijo_reservas": int(det["costo_fijo"]),
            "total_outflow":      total_outflow,
            "net_cashflow":       _fmt_int(total_inflow_neto) - total_outflow,
            "pagos_detail":       inflows_by_day[day],
        }
    return days


def _add_running_balance(days: Dict[str, Dict], opening_balance: float = 0) -> List[Dict]:
    """Sort days and add beginning/ending balance."""
    result = []
    balance = opening_balance
    for day_str in sorted(days.keys()):
        d = dict(days[day_str])
        d["beginning_balance"] = _fmt_int(balance)
        balance += d["net_cashflow"]
        d["ending_balance"] = _fmt_int(balance)
        result.append(d)
    return result


def _normalize_payment_method(method: Any) -> str:
    m = str(method or "otro").strip().lower()
    aliases = {
        "mp": "mercadopago",
        "mercado_pago": "mercadopago",
        "tbk": "transbank",
        "transbank_credito": "transbank",
        "transbank_debito": "transbank",
        "cash": "efectivo",
        "transfer": "transferencia",
        "sin registro": "sin_registro",
        "sin_registro": "sin_registro",
    }
    return aliases.get(m, m if m else "otro")


def _parse_pago_date(raw_date: Any, fallback_date: Any) -> Optional[date]:
    val = raw_date or fallback_date
    if not val:
        return None
    try:
        return date.fromisoformat(str(val)[:10])
    except ValueError:
        return None


def _build_inflows_by_method(
    bookings: List[Dict],
    commissions: Dict,
    d_from: date,
    d_to: date,
) -> Dict[str, Dict[str, Any]]:
    """
    Aggregate inflows by payment method for a date range using payment date.
    Returns dict method -> {count, inflow_bruto, inflow_commission, inflow_neto}.
    """
    grouped: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "inflow_bruto": 0,
            "inflow_commission": 0,
            "inflow_neto": 0,
            "details": [],
        }
    )
    for b in bookings:
        pagos = b.get("pagos") or []
        if not pagos:
            pago_dt = _parse_pago_date(None, b.get("fecha"))
            if not pago_dt or not (d_from <= pago_dt <= d_to):
                continue
            amt = float(b.get("ingreso_total") or 0)
            if amt <= 0:
                continue
            method = "sin_registro"
            net = _net_amount(amt, "transferencia", commissions)
            commission = amt - net
            g = grouped[method]
            g["count"] += 1
            amt_bruto = _fmt_int(amt)
            amt_comm = _fmt_int(commission)
            amt_neto = _fmt_int(net)
            g["inflow_bruto"] += amt_bruto
            g["inflow_commission"] += amt_comm
            g["inflow_neto"] += amt_neto
            g["details"].append({
                "booking_id": b.get("id"),
                "booking_date": b.get("fecha"),
                "payment_date": pago_dt.isoformat(),
                "nombre_cliente": b.get("nombre_cliente"),
                "method_original": "sin registro",
                "inflow_bruto": amt_bruto,
                "inflow_commission": amt_comm,
                "inflow_neto": amt_neto,
            })
            continue

        for p in pagos:
            pago_dt = _parse_pago_date(p.get("date"), b.get("fecha"))
            if not pago_dt or not (d_from <= pago_dt <= d_to):
                continue
            amt = float(p.get("amount", 0) or 0)
            if amt <= 0:
                continue
            method = _normalize_payment_method(p.get("method", "otro"))
            net = _net_amount(amt, method, commissions)
            commission = amt - net
            g = grouped[method]
            g["count"] += 1
            amt_bruto = _fmt_int(amt)
            amt_comm = _fmt_int(commission)
            amt_neto = _fmt_int(net)
            g["inflow_bruto"] += amt_bruto
            g["inflow_commission"] += amt_comm
            g["inflow_neto"] += amt_neto
            g["details"].append({
                "booking_id": b.get("id"),
                "booking_date": b.get("fecha"),
                "payment_date": pago_dt.isoformat(),
                "nombre_cliente": b.get("nombre_cliente"),
                "method_original": p.get("method", "otro"),
                "inflow_bruto": amt_bruto,
                "inflow_commission": amt_comm,
                "inflow_neto": amt_neto,
            })
    return grouped


def _aggregate_cf_weeks(days_list: List[Dict]) -> List[Dict]:
    weeks: Dict[str, Dict] = {}
    for d in days_list:
        dt = date.fromisoformat(d["fecha"])
        week_key = dt.strftime("%G-W%V")
        week_start = (dt - timedelta(days=dt.weekday())).isoformat()
        week_end = (dt - timedelta(days=dt.weekday()) + timedelta(days=6)).isoformat()
        if week_key not in weeks:
            weeks[week_key] = {
                "week": week_key, "week_start": week_start, "week_end": week_end,
                "inflow_bruto": 0, "inflow_commission": 0, "inflow_neto": 0,
                "outflow_opex": 0, "outflow_marketing": 0, "outflow_estructural": 0,
                "outflow_cv_aloj": 0, "outflow_cv_exp": 0, "outflow_cv_extra": 0,
                "outflow_costo_fijo_reservas": 0,
                "total_outflow": 0, "net_cashflow": 0,
                "beginning_balance": d["beginning_balance"], "days": [],
            }
        w = weeks[week_key]
        for k in ("inflow_bruto", "inflow_commission", "inflow_neto",
                  "outflow_opex", "outflow_marketing", "outflow_estructural",
                  "outflow_cv_aloj", "outflow_cv_exp", "outflow_cv_extra",
                  "outflow_costo_fijo_reservas",
                  "total_outflow", "net_cashflow"):
            w[k] += d[k]
        w["ending_balance"] = d["ending_balance"]
        w["days"].append(d)
    return list(weeks.values())


def _aggregate_cf_months(days_list: List[Dict]) -> List[Dict]:
    months: Dict[str, Dict] = {}
    for d in days_list:
        month_key = d["fecha"][:7]
        if month_key not in months:
            months[month_key] = {
                "month": month_key,
                "inflow_bruto": 0, "inflow_commission": 0, "inflow_neto": 0,
                "outflow_opex": 0, "outflow_marketing": 0, "outflow_estructural": 0,
                "outflow_cv_aloj": 0, "outflow_cv_exp": 0, "outflow_cv_extra": 0,
                "outflow_costo_fijo_reservas": 0,
                "total_outflow": 0, "net_cashflow": 0,
                "beginning_balance": d["beginning_balance"], "days": [],
            }
        m = months[month_key]
        for k in ("inflow_bruto", "inflow_commission", "inflow_neto",
                  "outflow_opex", "outflow_marketing", "outflow_estructural",
                  "outflow_cv_aloj", "outflow_cv_exp", "outflow_cv_extra",
                  "outflow_costo_fijo_reservas",
                  "total_outflow", "net_cashflow"):
            m[k] += d[k]
        m["ending_balance"] = d["ending_balance"]
        m["days"].append(d)
    return list(months.values())


# ── P&L endpoints ─────────────────────────────────────────────────────────────

@financial_router.get("/api/admin/financial/pnl")
async def get_pnl(
    date_from: str = Query(...),
    date_to:   str = Query(...),
    view:      str = Query("daily"),  # daily | weekly | monthly
    x_admin_key: str = Header(""),
):
    try:
        d_from = date.fromisoformat(date_from)
        d_to   = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(400, "Invalid date format, use YYYY-MM-DD")

    commissions = _get_commissions()
    bookings  = _get_bookings_range(d_from, d_to)
    marketing = _get_marketing_costs_range(d_from, d_to)

    days = _build_pnl_days(bookings, marketing, commissions, d_from, d_to)
    struct = get_financial_structure()
    period_days = (d_to - d_from).days + 1

    totals = {
        "n_reservas": sum(d["n_reservas"] for d in days.values()),
        "gross": sum(d["gross"] for d in days.values()),
        "commission_deduction": sum(d["commission_deduction"] for d in days.values()),
        "net_income": sum(d["net_income"] for d in days.values()),
        "costo_operacional": sum(d["costo_operacional"] for d in days.values()),
        "marketing": sum(d["marketing"] for d in days.values()),
        "costo_estructural": sum(d.get("costo_estructural", 0) for d in days.values()),
        "ingreso_reserva": sum(d.get("ingreso_reserva", 0) for d in days.values()),
        "ingreso_aloj": sum(d.get("ingreso_aloj", 0) for d in days.values()),
        "ingreso_exp": sum(d.get("ingreso_exp", 0) for d in days.values()),
        "ingreso_extra": sum(d.get("ingreso_extra", 0) for d in days.values()),
        "total_descuentos": sum(d.get("total_descuentos", 0) for d in days.values()),
        "cv_aloj": sum(d.get("cv_aloj", 0) for d in days.values()),
        "cv_exp": sum(d.get("cv_exp", 0) for d in days.values()),
        "cv_extra": sum(d.get("cv_extra", 0) for d in days.values()),
        "resultado": sum(d["resultado"] for d in days.values()),
    }

    if view == "weekly":
        data = _aggregate_weeks(days)
    elif view == "monthly":
        data = _aggregate_months(days)
    else:
        data = sorted(days.values(), key=lambda x: x["fecha"])

    return {
        "view": view,
        "date_from": date_from,
        "date_to": date_to,
        "period_calendar_days": period_days,
        "structure": struct,
        "totals": totals,
        "data": data,
        "commissions": commissions,
    }


# ── Cash Flow endpoints ───────────────────────────────────────────────────────

@financial_router.get("/api/admin/financial/cashflow")
async def get_cashflow(
    date_from:       str   = Query(...),
    date_to:         str   = Query(...),
    view:            str   = Query("daily"),
    opening_balance: float = Query(0),
    x_admin_key:     str   = Header(""),
):
    try:
        d_from = date.fromisoformat(date_from)
        d_to   = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(400, "Invalid date format, use YYYY-MM-DD")

    commissions = _get_commissions()
    bookings  = _get_bookings_cashflow_range(d_from, d_to)
    marketing = _get_marketing_costs_range(d_from, d_to)

    days = _build_cashflow_days(bookings, marketing, commissions, d_from, d_to)
    days_list = _add_running_balance(days, opening_balance)

    if view == "weekly":
        data = _aggregate_cf_weeks(days_list)
    elif view == "monthly":
        data = _aggregate_cf_months(days_list)
    else:
        data = days_list

    return {
        "view": view,
        "date_from": date_from,
        "date_to": date_to,
        "opening_balance": opening_balance,
        "period_calendar_days": (d_to - d_from).days + 1,
        "structure": get_financial_structure(),
        "data": data,
    }


@financial_router.get("/api/admin/financial/inflows-by-method")
async def get_inflows_by_method(
    date_from: str = Query(...),
    date_to: str = Query(...),
    x_admin_key: str = Header(""),
):
    try:
        d_from = date.fromisoformat(date_from)
        d_to = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(400, "Invalid date format, use YYYY-MM-DD")

    commissions = _get_commissions()
    bookings = _get_bookings_cashflow_range(d_from, d_to)
    grouped = _build_inflows_by_method(bookings, commissions, d_from, d_to)

    ordered_methods = [
        "efectivo",
        "mercadopago",
        "transbank",
        "transferencia",
        "cheque",
        "otro",
        "sin_registro",
    ]
    methods_sorted = sorted(
        grouped.keys(),
        key=lambda m: (ordered_methods.index(m) if m in ordered_methods else len(ordered_methods), m),
    )

    totals = {"count": 0, "inflow_bruto": 0, "inflow_commission": 0, "inflow_neto": 0}
    rows = []
    for method in methods_sorted:
        row = {"method": method, **grouped[method]}
        rows.append(row)
        totals["count"] += row["count"]
        totals["inflow_bruto"] += row["inflow_bruto"]
        totals["inflow_commission"] += row["inflow_commission"]
        totals["inflow_neto"] += row["inflow_neto"]

    return {
        "date_from": date_from,
        "date_to": date_to,
        "totals": totals,
        "data": rows,
    }


# ── Forecast endpoint ─────────────────────────────────────────────────────────

@financial_router.get("/api/admin/financial/forecast")
async def get_forecast(
    months_ahead: int = Query(2),
    x_admin_key:  str = Header(""),
):
    """Return confirmed bookings in future months as forecast."""
    today = date.today()
    d_from = today
    d_to   = date(today.year + (today.month + months_ahead - 1) // 12,
                  (today.month + months_ahead - 1) % 12 + 1,
                  1) - timedelta(days=1)

    commissions = _get_commissions()

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    fecha::text,
                    COALESCE(ingreso_total, 0),
                    COALESCE(costo_operativo_total, 0),
                    COALESCE(pagos, '[]'::jsonb),
                    status,
                    COALESCE(descuentos, '[]'::jsonb)
                FROM all_appointments
                WHERE fecha BETWEEN %s AND %s
                  AND status = ANY(%s)
                ORDER BY fecha
            """, (d_from, d_to, list(CONFIRMED_STATUSES)))
            rows = cur.fetchall()

    months_data: Dict[str, Dict] = {}
    for r in rows:
        day_str, gross, costo, pagos_raw, status, desc_raw = r
        month_key = day_str[:7]
        gross = float(gross) - _sum_descuentos(desc_raw)
        costo = float(costo)
        pagos = pagos_raw if isinstance(pagos_raw, list) else json.loads(pagos_raw or "[]")

        commission = sum(
            float(p.get("amount", 0) or 0) - _net_amount(float(p.get("amount", 0) or 0),
                                                           p.get("method", "otro"), commissions)
            for p in pagos
        )
        net = gross - commission

        if month_key not in months_data:
            months_data[month_key] = {
                "month": month_key, "n_reservas": 0,
                "gross": 0, "net_income": 0, "costo": 0,
                "confirmed": 0, "pending": 0,
            }
        m = months_data[month_key]
        m["n_reservas"] += 1
        m["gross"] += _fmt_int(gross)
        m["net_income"] += _fmt_int(net)
        m["costo"] += _fmt_int(costo)
        if status == "confirmed":
            m["confirmed"] += 1
        else:
            m["pending"] += 1

    # Attach budget for each month
    for month_key, m in months_data.items():
        y, mo = int(month_key[:4]), int(month_key[5:7])
        budget = _get_budget(y, mo)
        m["budget"] = budget
        m["resultado_forecast"] = m["net_income"] - m["costo"]
        m["vs_budget"] = m["net_income"] - budget["income_budget"]

    return {"data": list(months_data.values())}


# ── Marketing costs CRUD ──────────────────────────────────────────────────────

class MarketingCostIn(BaseModel):
    fecha:    str
    amount:   float
    category: str = "general"
    notes:    str = ""


@financial_router.get("/api/admin/financial/marketing-costs")
async def list_marketing_costs(
    year:  int = Query(...),
    month: int = Query(...),
    x_admin_key: str = Header(""),
):
    d_from = date(year, month, 1)
    if month == 12:
        d_to = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        d_to = date(year, month + 1, 1) - timedelta(days=1)
    return {"data": _get_marketing_costs_range(d_from, d_to)}


@financial_router.post("/api/admin/financial/marketing-costs")
async def create_marketing_cost(body: MarketingCostIn, x_admin_key: str = Header("")):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO marketing_costs (fecha, amount, category, notes)
                VALUES (%s, %s, %s, %s) RETURNING id
            """, (body.fecha, body.amount, body.category, body.notes))
            new_id = cur.fetchone()[0]
            conn.commit()
    return {"id": new_id, **body.dict()}


@financial_router.put("/api/admin/financial/marketing-costs/{cost_id}")
async def update_marketing_cost(cost_id: int, body: MarketingCostIn,
                                 x_admin_key: str = Header("")):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE marketing_costs SET fecha=%s, amount=%s, category=%s, notes=%s,
                    updated_at=NOW()
                WHERE id=%s
            """, (body.fecha, body.amount, body.category, body.notes, cost_id))
            conn.commit()
    return {"id": cost_id, **body.dict()}


@financial_router.delete("/api/admin/financial/marketing-costs/{cost_id}")
async def delete_marketing_cost(cost_id: int, x_admin_key: str = Header("")):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM marketing_costs WHERE id=%s", (cost_id,))
            conn.commit()
    return {"ok": True}


# ── Budget CRUD ───────────────────────────────────────────────────────────────

class BudgetIn(BaseModel):
    income_budget:    float = 0
    costs_budget:     float = 0
    marketing_budget: float = 0
    notes:            str   = ""
    aloj_budget:      float = 0
    exp_budget:       float = 0
    extra_budget:     float = 0
    reserva_budget:   float = 0


@financial_router.get("/api/admin/financial/budget/{year}/{month}")
async def get_budget_endpoint(year: int, month: int, x_admin_key: str = Header("")):
    return _get_budget(year, month)


@financial_router.put("/api/admin/financial/budget/{year}/{month}")
async def upsert_budget(year: int, month: int, body: BudgetIn,
                        x_admin_key: str = Header("")):
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Ensure zone columns exist (idempotent migration)
            cur.execute("""
                ALTER TABLE financial_budget
                    ADD COLUMN IF NOT EXISTS aloj_budget    NUMERIC DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS exp_budget     NUMERIC DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS extra_budget   NUMERIC DEFAULT 0,
                    ADD COLUMN IF NOT EXISTS reserva_budget NUMERIC DEFAULT 0
            """)
            cur.execute("""
                INSERT INTO financial_budget (year, month, income_budget, costs_budget,
                    marketing_budget, notes, aloj_budget, exp_budget, extra_budget, reserva_budget)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (year, month) DO UPDATE
                    SET income_budget=%s, costs_budget=%s, marketing_budget=%s,
                        notes=%s, aloj_budget=%s, exp_budget=%s, extra_budget=%s,
                        reserva_budget=%s, updated_at=NOW()
            """, (year, month,
                  body.income_budget, body.costs_budget, body.marketing_budget, body.notes,
                  body.aloj_budget, body.exp_budget, body.extra_budget, body.reserva_budget,
                  body.income_budget, body.costs_budget, body.marketing_budget, body.notes,
                  body.aloj_budget, body.exp_budget, body.extra_budget, body.reserva_budget))
            conn.commit()
    return {"year": year, "month": month, **body.dict()}


# ── Forecast table (actuals + pipeline + manual + suggested) ─────────────────

def _calc_net(gross: float, pagos_raw, commissions: Dict) -> float:
    pagos = pagos_raw if isinstance(pagos_raw, list) else json.loads(pagos_raw or "[]")
    commission = sum(
        (float(p.get("amount") or 0)) - _net_amount(
            float(p.get("amount") or 0), p.get("method", "otro"), commissions)
        for p in pagos
    )
    return gross - commission


def _sum_descuentos(raw: Any) -> float:
    """Sum manual descuentos[] amounts (coupon_discount already baked into ingreso_total)."""
    try:
        items = raw if isinstance(raw, list) else json.loads(raw or "[]")
        return max(0.0, sum(float(d.get("amount") or 0) for d in items if isinstance(d, dict)))
    except Exception:
        return 0.0


def _load_plan() -> Dict:
    raw = get_setting("financial_plan", "")
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        return {}


@financial_router.put("/api/admin/financial/plan-entry")
async def save_plan_entry(request: Request, x_admin_key: str = Header("")):
    """Save a single budget or forecast entry (week or month)."""
    body = await request.json()
    entry_type = body.get("type")  # "week_budget" | "week_forecast" | "month_forecast" | "week_cost_forecast" | "month_cost_forecast"
    key        = body.get("key")   # "2026-W22" or "2026-06"
    amount     = int(body.get("amount") or 0)
    if entry_type not in ("week_budget", "week_forecast", "month_forecast",
                          "week_cost_forecast", "month_cost_forecast"):
        raise HTTPException(400, "type must be week_budget, week_forecast, month_forecast, week_cost_forecast, or month_cost_forecast")
    if not key:
        raise HTTPException(400, "key required")
    plan = _load_plan()
    if entry_type not in plan:
        plan[entry_type] = {}
    plan[entry_type][key] = amount
    set_setting("financial_plan", json.dumps(plan))
    return {"ok": True}


@financial_router.get("/api/admin/financial/forecast-table")
async def get_forecast_table(
    months_back: int = Query(3),
    months_ahead: int = Query(9),
    view: str = Query("monthly"),
    weeks_back: int = Query(4),
    weeks_ahead: int = Query(34),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    x_admin_key: str = Header(""),
):
    """Rolling view: actuals + budget + forecast + suggested. Supports monthly and weekly views."""
    try:
        import calendar as _calendar
        today = date.today()
        cy, cm = today.year, today.month
        commissions = _get_commissions()
        plan = _load_plan()
        week_budget_plan       = plan.get("week_budget", {})
        week_forecast_plan     = plan.get("week_forecast", {})
        month_forecast_plan    = plan.get("month_forecast", {})
        week_cost_fc_plan      = plan.get("week_cost_forecast", {})
        month_cost_fc_plan     = plan.get("month_cost_forecast", {})
        structure          = get_financial_structure()
        daily_struct       = float(structure.get("costo_fijo_diario_prorrateado") or 0)
        costo_por_reserva_fc = float(structure.get("costo_operativo_por_reserva") or 18000)
        cost_pct           = float(structure.get("costo_pct_forecast") or 0)  # % of income for forecast/budget costs

        # ── WEEKLY VIEW ───────────────────────────────────────────────────────
        if view == "weekly":
            mon0 = today - timedelta(days=today.weekday())
            weeks_list = []
            if date_from and date_to:
                try:
                    df = date.fromisoformat(date_from)
                    dt = date.fromisoformat(date_to)
                    cur_mon = df - timedelta(days=df.weekday())
                    end_mon = dt - timedelta(days=dt.weekday())
                    while cur_mon <= end_mon:
                        ws = cur_mon
                        we = ws + timedelta(days=6)
                        iso = ws.isocalendar()
                        weeks_list.append({
                            "key": f"{iso.year}-W{iso.week:02d}",
                            "ws": ws, "we": we,
                            "iso_year": iso.year, "iso_week": iso.week,
                            "is_past": we < today,
                            "is_current": ws <= today <= we,
                        })
                        cur_mon += timedelta(weeks=1)
                except ValueError:
                    pass
            if not weeks_list:
                for i in range(-weeks_back, weeks_ahead + 1):
                    ws = mon0 + timedelta(weeks=i)
                    we = ws + timedelta(days=6)
                    iso = ws.isocalendar()
                    weeks_list.append({
                        "key": f"{iso.year}-W{iso.week:02d}",
                        "ws": ws, "we": we,
                        "iso_year": iso.year, "iso_week": iso.week,
                        "is_past": we < today,
                        "is_current": ws <= today <= we,
                    })

            d_from_w = weeks_list[0]["ws"] - timedelta(weeks=104)
            d_to_w   = weeks_list[-1]["we"]

            # Load marketing spend aggregated by ISO week key
            _mkt_raw_w = _get_marketing_costs_range(d_from_w, d_to_w)
            mkt_by_week: Dict[str, float] = {}
            for _mr in _mkt_raw_w:
                try:
                    _dobj = date.fromisoformat(_mr["fecha"][:10])
                    _iso  = _dobj.isocalendar()
                    _wk   = f"{_iso.year}-W{_iso.week:02d}"
                    mkt_by_week[_wk] = mkt_by_week.get(_wk, 0.0) + float(_mr["amount"])
                except Exception:
                    pass

            by_week: Dict = {}
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT COALESCE(fecha::text,''), COALESCE(ingreso_total,0),
                               COALESCE(costo_operativo_total,0), COALESCE(pagos,'[]'::jsonb),
                               COALESCE(descuentos,'[]'::jsonb)
                        FROM all_appointments
                        WHERE fecha BETWEEN %s AND %s AND status = ANY(%s)
                        ORDER BY fecha
                    """, (d_from_w, d_to_w, list(CONFIRMED_STATUSES)))
                    for fecha_str, gross, costo, pagos_raw, desc_raw in cur.fetchall():
                        if not fecha_str:
                            continue
                        dobj = datetime.strptime(fecha_str[:10], "%Y-%m-%d")
                        iso = dobj.isocalendar()
                        wk = f"{iso.year}-W{iso.week:02d}"
                        adj_gross = float(gross) - _sum_descuentos(desc_raw)
                        net = _calc_net(adj_gross, pagos_raw, commissions)
                        if wk not in by_week:
                            by_week[wk] = {"income": 0, "costs": 0, "bookings": 0}
                        by_week[wk]["income"]   += int(net)
                        by_week[wk]["costs"]    += int(float(costo))
                        by_week[wk]["bookings"] += 1

            # Monthly budgets as fallback when no per-week budget set
            months_needed = set((w["ws"].year, w["ws"].month) for w in weeks_list)
            month_budgets = {m: _get_budget(m[0], m[1]) for m in months_needed}

            def _week_budget_fallback(ws):
                y, m = ws.year, ws.month
                b = month_budgets.get((y, m), {})
                inc = b.get("income_budget", 0)
                if not inc:
                    return None
                _, days = _cal.monthrange(y, m)
                return int(inc / (days / 7.0))

            def _week_cost_budget_fallback(ws):
                y, m = ws.year, ws.month
                b = month_budgets.get((y, m), {})
                costs = (b.get("costs_budget", 0) or 0) + (b.get("marketing_budget", 0) or 0)
                if not costs:
                    return None
                _, days = _cal.monthrange(y, m)
                return int(costs / (days / 7.0))

            def _week_suggested(iso_year, iso_week, is_past):
                if is_past:
                    return None, None
                yoy = f"{iso_year - 1}-W{iso_week:02d}"
                if by_week.get(yoy, {}).get("income", 0) > 0:
                    t_this = sum(by_week.get(
                        f"{(mon0 - timedelta(weeks=i+1)).isocalendar().year}"
                        f"-W{(mon0 - timedelta(weeks=i+1)).isocalendar().week:02d}", {}).get("income", 0)
                        for i in range(4))
                    t_last = sum(by_week.get(
                        f"{(mon0 - timedelta(weeks=i+53)).isocalendar().year}"
                        f"-W{(mon0 - timedelta(weeks=i+53)).isocalendar().week:02d}", {}).get("income", 0)
                        for i in range(4))
                    trend = max(0.5, min(2.0, t_this / t_last)) if t_last > 0 else 1.0
                    return int(by_week[yoy]["income"] * trend), "sem. ant."
                trailing = [
                    by_week[f"{(mon0 - timedelta(weeks=i+1)).isocalendar().year}"
                            f"-W{(mon0 - timedelta(weeks=i+1)).isocalendar().week:02d}"]["income"]
                    for i in range(3)
                    if f"{(mon0 - timedelta(weeks=i+1)).isocalendar().year}"
                       f"-W{(mon0 - timedelta(weeks=i+1)).isocalendar().week:02d}" in by_week
                ]
                if trailing:
                    return int(sum(trailing) / len(trailing)), "prom. 3sem"
                return None, None

            _MES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]
            result = []
            for w in weeks_list:
                ws, we = w["ws"], w["we"]
                if ws.month == we.month:
                    lbl = f"{ws.day}–{we.day} {_MES[ws.month-1]}"
                else:
                    lbl = f"{ws.day} {_MES[ws.month-1]} – {we.day} {_MES[we.month-1]}"
                data = by_week.get(w["key"])
                # Per-week budget; fall back to distributed monthly if not explicitly set
                wbval = week_budget_plan.get(w["key"])
                if wbval is None:
                    wbval = _week_budget_fallback(ws)
                    bval_is_override = False
                else:
                    wbval = int(wbval)
                    bval_is_override = True
                # Per-week forecast (manual)
                wfval = week_forecast_plan.get(w["key"])
                wfval = int(wfval) if wfval is not None else None
                wcf_val = week_cost_fc_plan.get(w["key"])
                wcf_val = int(wcf_val) if wcf_val is not None else None
                wcb_val = _week_cost_budget_fallback(ws)
                sug_val, sug_src = _week_suggested(w["iso_year"], w["iso_week"], w["is_past"])
                actual_costs  = data["costs"]  if data else None
                week_fixed    = daily_struct * 7
                week_mkt      = int(mkt_by_week.get(w["key"], 0))
                actual_result = (data["income"] - data["costs"] - week_fixed - week_mkt) if data else None
                result.append({
                    "month":            w["key"],
                    "week_label":       lbl,
                    "month_key":        f"{ws.year:04d}-{ws.month:02d}",
                    "is_past":          w["is_past"],
                    "is_current":       w["is_current"],
                    "actual_income":    data["income"]   if data else None,
                    "actual_costs":     actual_costs,
                    "actual_result":    actual_result,
                    "actual_bookings":  data["bookings"] if data else None,
                    "manual_income":    wbval,
                    "manual_costs":     wcb_val,
                    "manual_marketing": None,
                    "manual_is_override": bval_is_override,
                    "forecast_income":  wfval,
                    "forecast_costs":   wcf_val,
                    "suggested_income": sug_val,
                    "suggested_source": sug_src,
                    "is_weekly":        True,
                })
            return {"data": result, "view": "weekly", "cost_pct": cost_pct}

        # ── MONTHLY VIEW ──────────────────────────────────────────────────────
        def _madd(y: int, m: int, delta: int):
            t = y * 12 + m - 1 + delta
            return (t // 12, t % 12 + 1)

        if date_from and date_to:
            try:
                df_m = date.fromisoformat(date_from)
                dt_m = date.fromisoformat(date_to)
                months_range = []
                y_cur, m_cur = df_m.year, df_m.month
                y_end, m_end = dt_m.year, dt_m.month
                while (y_cur, m_cur) <= (y_end, m_end):
                    months_range.append((y_cur, m_cur))
                    m_cur += 1
                    if m_cur > 12:
                        m_cur = 1
                        y_cur += 1
            except ValueError:
                months_range = []
        if not (date_from and date_to) or not months_range:
            months_range = [_madd(cy, cm, i) for i in range(-months_back, months_ahead + 1)]
        hist_y, hist_m = _madd(cy, cm, -24)
        d_from = date(hist_y, hist_m, 1)
        end_y, end_m = months_range[-1]
        nxt_y, nxt_m = _madd(end_y, end_m, 1)
        d_to = date(nxt_y, nxt_m, 1) - timedelta(days=1)

        # Load marketing spend for the full range and aggregate by YYYY-MM
        _mkt_raw_m = _get_marketing_costs_range(d_from, d_to)
        mkt_by_month: Dict[str, float] = {}
        for _mr in _mkt_raw_m:
            _mk = _mr["fecha"][:7]
            mkt_by_month[_mk] = mkt_by_month.get(_mk, 0.0) + float(_mr["amount"])

        by_month: Dict = {}
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COALESCE(fecha::text,''), COALESCE(ingreso_total,0),
                           COALESCE(pagos,'[]'::jsonb),
                           COALESCE(descuentos,'[]'::jsonb)
                    FROM all_appointments
                    WHERE fecha BETWEEN %s AND %s AND status = ANY(%s)
                    ORDER BY fecha
                """, (d_from, d_to, list(CONFIRMED_STATUSES)))
                for fecha_str, gross, pagos_raw, desc_raw in cur.fetchall():
                    if not fecha_str:
                        continue
                    dobj = datetime.strptime(fecha_str[:10], "%Y-%m-%d")
                    key = (dobj.year, dobj.month)
                    adj_gross = float(gross) - _sum_descuentos(desc_raw)
                    net = _calc_net(adj_gross, pagos_raw, commissions)
                    if key not in by_month:
                        by_month[key] = {"income": 0, "costs": 0, "result": 0, "bookings": 0}
                    by_month[key]["income"]   += int(adj_gross)           # GROSS (= P&L I.BRUTO)
                    by_month[key]["costs"]    += int(costo_por_reserva_fc)
                    by_month[key]["result"]   += int(net - costo_por_reserva_fc)  # net for correct result
                    by_month[key]["bookings"] += 1
                    by_month[key]["has_data"]  = True

        # ── Zone actuals (ingreso_aloj / exp / extra) per month ─────────────
        _wl              = set((structure.get("experience_slug_whitelist") or []))
        _costo_x_reserva = costo_por_reserva_fc
        _cc  = load_extra_cost_catalog()
        _ac  = load_aloj_cost_catalog()
        zone_by_month: Dict = {}
        _bk_for_zones = _get_bookings_range(d_from, d_to)
        for _bk in _bk_for_zones:
            _mk = str(_bk["fecha"])[:7]
            _sp = split_booking_financials(_bk, _cc, _wl, _ac)
            if _mk not in zone_by_month:
                zone_by_month[_mk] = {"actual_reserva": 0, "cv_reserva": 0,
                                       "actual_aloj": 0, "actual_exp": 0, "actual_extra": 0,
                                       "cv_aloj": 0, "cv_exp": 0, "cv_extra": 0}
            zone_by_month[_mk]["actual_reserva"] += _sp["ingreso_reserva"]
            zone_by_month[_mk]["cv_reserva"]     += _costo_x_reserva  # mismo criterio que P&L C.OP
            zone_by_month[_mk]["actual_aloj"]    += _sp["ingreso_aloj"]
            zone_by_month[_mk]["actual_exp"]     += _sp["ingreso_exp"]
            zone_by_month[_mk]["actual_extra"]   += _sp["ingreso_extra"]
            zone_by_month[_mk]["cv_aloj"]        += _sp["cv_aloj"]
            zone_by_month[_mk]["cv_exp"]         += _sp["cv_exp"]
            zone_by_month[_mk]["cv_extra"]       += _sp["cv_extra"]

        budgets: Dict = {ym: _get_budget(ym[0], ym[1]) for ym in months_range}

        def _suggested(y: int, m: int):
            yoy_key = (y - 1, m)
            if yoy_key < (cy, cm) and by_month.get(yoy_key, {}).get("income", 0) > 0:
                t_this = sum(
                    by_month.get(_madd(cy, cm, -(i + 1)), {}).get("income", 0)
                    for i in range(3) if _madd(cy, cm, -(i + 1)) < (cy, cm)
                )
                t_last = sum(
                    by_month.get(_madd(cy, cm, -(i + 13)), {}).get("income", 0)
                    for i in range(3) if _madd(cy, cm, -(i + 13)) < (cy, cm)
                )
                trend = max(0.5, min(2.0, t_this / t_last)) if t_last > 0 else 1.0
                return int(by_month[yoy_key]["income"] * trend), "año anterior"
            trailing = [
                by_month[_madd(y, m, -(i + 1))]["income"]
                for i in range(3)
                if _madd(y, m, -(i + 1)) < (cy, cm) and _madd(y, m, -(i + 1)) in by_month
            ]
            if trailing:
                return int(sum(trailing) / len(trailing)), "promedio 3m"
            return None, None

        result = []
        for y, m in months_range:
            key = (y, m)
            mk  = f"{y:04d}-{m:02d}"
            is_past    = key < (cy, cm)
            is_current = key == (cy, cm)
            data   = by_month.get(key)
            budget = budgets.get(key, {"income_budget": 0, "costs_budget": 0, "marketing_budget": 0})
            sug_val, sug_src = _suggested(y, m) if not is_past else (None, None)
            fc_val = month_forecast_plan.get(mk)
            fc_val = int(fc_val) if fc_val is not None else None
            fc_cost_val = month_cost_fc_plan.get(mk)
            fc_cost_val = int(fc_cost_val) if fc_cost_val is not None else None
            month_days   = _calendar.monthrange(y, m)[1]
            month_fixed  = int(daily_struct * month_days)
            month_mkt    = int(mkt_by_month.get(mk, 0))
            _zd          = zone_by_month.get(mk, {})
            _cv_total    = (int(_zd.get("cv_aloj", 0)) + int(_zd.get("cv_exp", 0))
                            + int(_zd.get("cv_extra", 0)))
            actual_result = int(data["result"] - month_fixed - month_mkt - _cv_total) if data else None
            result.append({
                "month":            mk,
                "week_label":       None,
                "month_key":        mk,
                "is_past":          is_past,
                "is_current":       is_current,
                "actual_income":    data["income"]   if data else None,
                "actual_costs":     data["costs"]    if data else None,
                "actual_result":    actual_result,
                "actual_bookings":  data["bookings"] if data else None,
                "manual_income":    int(budget["income_budget"])    if budget["income_budget"]    else None,
                "manual_costs":     int(budget["costs_budget"])     if budget["costs_budget"]     else None,
                "manual_marketing": int(budget["marketing_budget"]) if budget["marketing_budget"] else None,
                "manual_is_override": True,
                "forecast_income":  fc_val,
                "forecast_costs":   fc_cost_val,
                "suggested_income": sug_val,
                "suggested_source": sug_src,
                "is_weekly":        False,
                "actual_reserva":   _zd.get("actual_reserva", 0),
                "cv_reserva":       _zd.get("cv_reserva", 0),
                "actual_aloj":      _zd.get("actual_aloj", 0),
                "actual_exp":       _zd.get("actual_exp", 0),
                "actual_extra":     _zd.get("actual_extra", 0),
                "cv_aloj":          _zd.get("cv_aloj", 0),
                "cv_exp":           _zd.get("cv_exp", 0),
                "cv_extra":         _zd.get("cv_extra", 0),
                "budget_reserva":   int(budget.get("reserva_budget", 0)),
                "budget_aloj":      int(budget.get("aloj_budget", 0)),
                "budget_exp":       int(budget.get("exp_budget", 0)),
                "budget_extra":     int(budget.get("extra_budget", 0)),
            })
        return {"data": result, "view": "monthly", "cost_pct": cost_pct}
    except Exception:
        logger.exception("forecast-table error")
        raise


# ── Debug: compare Forecast vs P&L for a single month ───────────────────────

@financial_router.get("/api/admin/financial/debug-compare/{year}/{month}")
async def debug_compare(year: int, month: int, x_admin_key: str = Header("")):
    """Return booking-level breakdown showing Forecast vs P&L calculation side by side."""
    structure    = get_financial_structure()
    commissions  = _get_commissions()
    cpr          = float(structure.get("costo_operativo_por_reserva") or 18000)
    wl           = set(structure.get("experience_slug_whitelist") or [])
    cc           = load_extra_cost_catalog()
    ac           = load_aloj_cost_catalog()

    d_from = date(year, month, 1)
    d_to   = date(year, month, _cal.monthrange(year, month)[1])
    bookings = _get_bookings_range(d_from, d_to)

    rows = []
    for b in bookings:
        # ── Forecast path ──────────────────────────────────────────────────
        ingreso_total   = float(b.get("ingreso_total") or 0)
        desc_raw        = b.get("descuentos") or []
        manual_desc     = _sum_descuentos(desc_raw)
        coupon          = float(b.get("coupon_discount") or 0)
        adj_gross_fc    = ingreso_total - manual_desc
        net_fc          = _calc_net(adj_gross_fc, b.get("pagos") or [], commissions)
        comm_fc         = adj_gross_fc - net_fc

        # ── P&L path ───────────────────────────────────────────────────────
        sp              = split_booking_financials(b, cc, wl, ac)
        base_inc        = (float(sp["ingreso_reserva"]) + float(sp["ingreso_aloj"])
                           + float(sp["ingreso_exp"])   + float(sp["ingreso_extra"]))
        disc_pnl        = booking_discount_total_clp(b)   # coupon + manual
        gross_pnl       = base_inc - disc_pnl
        pnl_r           = _calc_booking_pnl(b, commissions, gross_override=gross_pnl,
                                             costo_override=cpr)
        net_pnl         = float(pnl_r["net_income"])
        comm_pnl        = float(pnl_r["commission_deduction"])

        rows.append({
            "id":             b["id"],
            "fecha":          str(b["fecha"]),
            "cliente":        b.get("nombre_cliente", ""),
            # income components
            "ingreso_total":  int(ingreso_total),
            "ingreso_reserva":int(sp["ingreso_reserva"]),
            "ingreso_extras": int(b.get("ingreso_extras") or 0),
            "coupon":         int(coupon),
            "manual_desc":    int(manual_desc),
            "disc_pnl":       int(disc_pnl),
            "base_inc_pnl":   int(base_inc),
            # forecast
            "fc_adj_gross":   int(adj_gross_fc),
            "fc_comm":        int(comm_fc),
            "fc_net":         int(net_fc),
            # pnl
            "pnl_gross":      int(gross_pnl),
            "pnl_comm":       int(comm_pnl),
            "pnl_net":        int(net_pnl),
            # diff
            "diff_gross":     int(adj_gross_fc) - int(gross_pnl),
            "diff_net":       int(net_fc) - int(net_pnl),
            # split
            "split_aloj":     int(sp["ingreso_aloj"]),
            "split_exp":      int(sp["ingreso_exp"]),
            "split_extra":    int(sp["ingreso_extra"]),
            "cv_aloj":        int(sp["cv_aloj"]),
            "cv_exp":         int(sp["cv_exp"]),
            "cv_extra":       int(sp["cv_extra"]),
        })

    totals = {k: sum(r[k] for r in rows)
              for k in ("ingreso_total","base_inc_pnl","coupon","manual_desc","disc_pnl",
                        "fc_adj_gross","fc_comm","fc_net",
                        "pnl_gross","pnl_comm","pnl_net",
                        "diff_gross","diff_net",
                        "split_aloj","split_exp","split_extra",
                        "cv_aloj","cv_exp","cv_extra")}
    return {"year": year, "month": month, "bookings": rows, "totals": totals,
            "costo_por_reserva": cpr, "n": len(rows)}

@financial_router.get("/api/admin/financial/structure")
async def get_financial_structure_endpoint(x_admin_key: str = Header("")):
    return get_financial_structure()


@financial_router.put("/api/admin/financial/structure")
async def put_financial_structure(request: Request, x_admin_key: str = Header("")):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "JSON object expected")
    merged = get_financial_structure()
    if "costo_fijo_diario_prorrateado" in body:
        merged["costo_fijo_diario_prorrateado"] = float(body["costo_fijo_diario_prorrateado"] or 0)
    if "costo_operativo_por_reserva" in body:
        merged["costo_operativo_por_reserva"] = float(body["costo_operativo_por_reserva"] or 0)
    if "experience_slug_whitelist" in body:
        wl = body["experience_slug_whitelist"]
        if isinstance(wl, str):
            merged["experience_slug_whitelist"] = [
                x.strip().lower() for x in wl.split(",") if x.strip()
            ]
        elif isinstance(wl, list):
            merged["experience_slug_whitelist"] = [str(x).lower() for x in wl]
    set_setting("financial_structure", json.dumps(merged))
    return merged



# ── Commission settings ───────────────────────────────────────────────────────

@financial_router.get("/api/admin/financial/commissions")
async def get_commissions_endpoint(x_admin_key: str = Header("")):
    return _get_commissions()


@financial_router.put("/api/admin/financial/commissions")
async def update_commissions(request: Request, x_admin_key: str = Header("")):
    body = await request.json()
    set_setting("financial_commissions", json.dumps(body))
    return body


# ── Simulator: save/load scenario + fetch actuals ────────────────────────────

_SIM_DEFAULTS = {
    "precio_por_persona": 45000,
    "personas_promedio": 4,
    "reservas_por_mes": 30,
    "extras_promedio_por_reserva": 15000,
    "costo_operativo_por_reserva": 18000,
    "costos_fijos_mensuales": 651000,   # 21,700/day × 30
    "mantenimiento_seguros": 150000,
    "otros_fijos": 0,
    "remuneracion_capitan": 800000,
    "remuneracion_personal": 0,
    "remuneracion_admin": 0,
    "marketing_mensual": 200000,
    "dias_operativos": 30,
}


@financial_router.get("/api/admin/financial/simulator")
async def get_simulator(x_admin_key: str = Header("")):
    """Return saved simulator scenario + last-90-day actuals for seeding defaults."""
    saved_raw = get_setting("financial_simulator")
    scenario = json.loads(saved_raw) if saved_raw else {}
    merged = {**_SIM_DEFAULTS, **scenario}

    # Pull actuals from last 90 days
    today = date.today()
    d_from = today - timedelta(days=89)
    actuals: Dict[str, Any] = {}
    try:
        bookings = _get_bookings_range(d_from, today)
        if bookings:
            days_in_range = max((today - d_from).days, 1)
            months_in_range = days_in_range / 30
            total_rev = sum(float(b.get("ingreso_total") or 0) for b in bookings)
            total_people = sum(int(b.get("num_personas") or b.get("num_adultos") or 0) for b in bookings)
            n = len(bookings)
            actuals = {
                "reservas_reales_mes": round(n / max(months_in_range, 1), 1),
                "ingreso_total_real": round(total_rev / max(months_in_range, 1)),
                "ingreso_por_reserva_real": round(total_rev / n) if n else 0,
                "personas_promedio_real": round(total_people / n, 1) if n else 0,
                "n_bookings": n,
                "period_days": days_in_range,
            }
    except Exception as e:
        logger.warning(f"sim actuals query failed: {e}")

    return {"scenario": merged, "actuals": actuals}


@financial_router.put("/api/admin/financial/simulator")
async def save_simulator(request: Request, x_admin_key: str = Header("")):
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(400, "JSON object expected")
    set_setting("financial_simulator", json.dumps(body))
    return body


@financial_router.get("/api/admin/financial/simulator/scenarios")
async def list_sim_scenarios(x_admin_key: str = Header("")):
    raw = get_setting("financial_simulator_scenarios", "")
    try:
        return json.loads(raw) if raw else {"scenarios": []}
    except Exception:
        return {"scenarios": []}


@financial_router.put("/api/admin/financial/simulator/scenarios")
async def save_sim_scenarios(request: Request, x_admin_key: str = Header("")):
    body = await request.json()
    if not isinstance(body, dict) or "scenarios" not in body:
        raise HTTPException(400, "Expected {scenarios: [...]}")
    set_setting("financial_simulator_scenarios", json.dumps(body))
    return body
