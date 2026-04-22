"""Financial module: P&L dashboard and Cash Flow statement."""
import json
import logging
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from app.db.connection import get_connection
from app.booking.operator_settings import get_setting, set_setting

logger = logging.getLogger(__name__)
financial_router = APIRouter()

CHILE_TZ = __import__("zoneinfo").ZoneInfo("America/Santiago")

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
    """Return confirmed/pending bookings with pagos and descuentos for a date range."""
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
                    COALESCE(num_personas::text, '0')
                FROM all_appointments
                WHERE fecha BETWEEN %s AND %s
                  AND status NOT IN ('cancelled', 'no_show')
                ORDER BY fecha, id
            """, (date_from, date_to))
            cols = ["id", "fecha", "ingreso_reserva", "ingreso_extras",
                    "ingreso_total", "costo_fijo", "costo_variable", "costo_total",
                    "pagos", "descuentos", "nombre_cliente", "status", "num_personas"]
            rows = []
            for r in cur.fetchall():
                d = dict(zip(cols, r))
                d["ingreso_total"]  = float(d["ingreso_total"])
                d["ingreso_reserva"]= float(d["ingreso_reserva"])
                d["ingreso_extras"] = float(d["ingreso_extras"])
                d["costo_total"]    = float(d["costo_total"])
                d["costo_fijo"]     = float(d["costo_fijo"])
                d["costo_variable"] = float(d["costo_variable"])
                pagos = d["pagos"]
                if isinstance(pagos, str):
                    pagos = json.loads(pagos)
                d["pagos"] = pagos if isinstance(pagos, list) else []
                desc = d["descuentos"]
                if isinstance(desc, str):
                    desc = json.loads(desc)
                d["descuentos"] = desc if isinstance(desc, list) else []
                rows.append(d)
            return rows


def _get_marketing_costs_range(date_from: date, date_to: date) -> List[Dict]:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, fecha::text, amount, category, notes
                FROM marketing_costs
                WHERE fecha BETWEEN %s AND %s
                ORDER BY fecha
            """, (date_from, date_to))
            return [{"id": r[0], "fecha": r[1], "amount": float(r[2]),
                     "category": r[3], "notes": r[4]} for r in cur.fetchall()]


def _get_budget(year: int, month: int) -> Dict:
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT income_budget, costs_budget, marketing_budget, notes
                FROM financial_budget WHERE year=%s AND month=%s
            """, (year, month))
            r = cur.fetchone()
            if r:
                return {"income_budget": float(r[0]), "costs_budget": float(r[1]),
                        "marketing_budget": float(r[2]), "notes": r[3] or ""}
            return {"income_budget": 0, "costs_budget": 0, "marketing_budget": 0, "notes": ""}


# ── P&L calculation core ──────────────────────────────────────────────────────

def _calc_booking_pnl(booking: Dict, commissions: Dict) -> Dict:
    """Calculate P&L fields for a single booking."""
    gross = booking["ingreso_total"]
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
    costo = booking["costo_total"]
    return {
        "gross":                _fmt_int(gross),
        "commission_deduction": _fmt_int(commission_deduction),
        "net_income":           _fmt_int(net_income),
        "costo_operacional":    _fmt_int(costo),
        "pagos_received":       _fmt_int(total_pago_amount),
    }


def _build_pnl_days(bookings: List[Dict], marketing: List[Dict],
                    commissions: Dict) -> Dict[str, Dict]:
    """Build per-day P&L dict."""
    mkt_by_day: Dict[str, float] = defaultdict(float)
    for m in marketing:
        mkt_by_day[m["fecha"]] += m["amount"]

    days: Dict[str, Dict] = {}
    for b in bookings:
        day = b["fecha"]
        if day not in days:
            days[day] = {
                "fecha": day,
                "n_reservas": 0,
                "gross": 0,
                "commission_deduction": 0,
                "net_income": 0,
                "costo_operacional": 0,
                "marketing": 0,
                "resultado": 0,
                "bookings": [],
            }
        pnl = _calc_booking_pnl(b, commissions)
        d = days[day]
        d["n_reservas"]           += 1
        d["gross"]                += pnl["gross"]
        d["commission_deduction"] += pnl["commission_deduction"]
        d["net_income"]           += pnl["net_income"]
        d["costo_operacional"]    += pnl["costo_operacional"]
        d["bookings"].append({
            "id":               b["id"],
            "nombre_cliente":   b["nombre_cliente"],
            "ingreso_total":    pnl["gross"],
            "commission":       pnl["commission_deduction"],
            "net_income":       pnl["net_income"],
            "costo":            pnl["costo_operacional"],
            "pagos":            b["pagos"],
        })

    # Add marketing and compute resultado
    all_days_with_mkt = set(list(days.keys()) + list(mkt_by_day.keys()))
    for day in all_days_with_mkt:
        if day not in days:
            days[day] = {"fecha": day, "n_reservas": 0, "gross": 0,
                         "commission_deduction": 0, "net_income": 0,
                         "costo_operacional": 0, "marketing": 0, "resultado": 0, "bookings": []}
        days[day]["marketing"] = _fmt_int(mkt_by_day.get(day, 0))
        d = days[day]
        d["resultado"] = d["net_income"] - d["costo_operacional"] - d["marketing"]

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
        m["days"].append(d)
    return list(months.values())


# ── Cash Flow calculation core ────────────────────────────────────────────────

def _build_cashflow_days(bookings: List[Dict], marketing: List[Dict],
                          commissions: Dict) -> Dict[str, Dict]:
    """Build per-day cash flow based on actual payment dates."""
    # Outflows: operational costs on booking date
    opex_by_day: Dict[str, float] = defaultdict(float)
    for b in bookings:
        opex_by_day[b["fecha"]] += b["costo_total"]

    # Outflows: marketing
    mkt_by_day: Dict[str, float] = defaultdict(float)
    for m in marketing:
        mkt_by_day[m["fecha"]] += m["amount"]

    # Inflows: pagos by payment date (net of commission)
    inflows_by_day: Dict[str, List[Dict]] = defaultdict(list)
    for b in bookings:
        for p in b["pagos"]:
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

    all_days = (set(opex_by_day.keys()) | set(mkt_by_day.keys()) |
                set(inflows_by_day.keys()))

    days: Dict[str, Dict] = {}
    for day in all_days:
        total_inflow_neto = sum(p["amount_neto"] for p in inflows_by_day[day])
        total_inflow_bruto = sum(p["amount_bruto"] for p in inflows_by_day[day])
        total_commission = sum(p["commission"] for p in inflows_by_day[day])
        outflow_opex = _fmt_int(opex_by_day[day])
        outflow_mkt  = _fmt_int(mkt_by_day[day])
        total_outflow = outflow_opex + outflow_mkt
        days[day] = {
            "fecha":           day,
            "inflow_bruto":    _fmt_int(total_inflow_bruto),
            "inflow_commission": _fmt_int(total_commission),
            "inflow_neto":     _fmt_int(total_inflow_neto),
            "outflow_opex":    outflow_opex,
            "outflow_marketing": outflow_mkt,
            "total_outflow":   total_outflow,
            "net_cashflow":    _fmt_int(total_inflow_neto) - total_outflow,
            "pagos_detail":    inflows_by_day[day],
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
                "outflow_opex": 0, "outflow_marketing": 0, "total_outflow": 0,
                "net_cashflow": 0, "beginning_balance": d["beginning_balance"], "days": [],
            }
        w = weeks[week_key]
        for k in ("inflow_bruto", "inflow_commission", "inflow_neto",
                  "outflow_opex", "outflow_marketing", "total_outflow", "net_cashflow"):
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
                "outflow_opex": 0, "outflow_marketing": 0, "total_outflow": 0,
                "net_cashflow": 0, "beginning_balance": d["beginning_balance"], "days": [],
            }
        m = months[month_key]
        for k in ("inflow_bruto", "inflow_commission", "inflow_neto",
                  "outflow_opex", "outflow_marketing", "total_outflow", "net_cashflow"):
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

    days = _build_pnl_days(bookings, marketing, commissions)

    totals = {
        "n_reservas": sum(d["n_reservas"] for d in days.values()),
        "gross": sum(d["gross"] for d in days.values()),
        "commission_deduction": sum(d["commission_deduction"] for d in days.values()),
        "net_income": sum(d["net_income"] for d in days.values()),
        "costo_operacional": sum(d["costo_operacional"] for d in days.values()),
        "marketing": sum(d["marketing"] for d in days.values()),
        "resultado": sum(d["resultado"] for d in days.values()),
    }

    if view == "weekly":
        data = _aggregate_weeks(days)
    elif view == "monthly":
        data = _aggregate_months(days)
    else:
        data = sorted(days.values(), key=lambda x: x["fecha"])

    return {"view": view, "date_from": date_from, "date_to": date_to,
            "totals": totals, "data": data, "commissions": commissions}


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
    bookings  = _get_bookings_range(d_from, d_to)
    marketing = _get_marketing_costs_range(d_from, d_to)

    days = _build_cashflow_days(bookings, marketing, commissions)
    days_list = _add_running_balance(days, opening_balance)

    if view == "weekly":
        data = _aggregate_cf_weeks(days_list)
    elif view == "monthly":
        data = _aggregate_cf_months(days_list)
    else:
        data = days_list

    return {"view": view, "date_from": date_from, "date_to": date_to,
            "opening_balance": opening_balance, "data": data}


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
                    status
                FROM all_appointments
                WHERE fecha BETWEEN %s AND %s
                  AND status NOT IN ('cancelled', 'no_show')
                ORDER BY fecha
            """, (d_from, d_to))
            rows = cur.fetchall()

    months_data: Dict[str, Dict] = {}
    for r in rows:
        day_str, gross, costo, pagos_raw, status = r
        month_key = day_str[:7]
        gross = float(gross)
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


@financial_router.get("/api/admin/financial/budget/{year}/{month}")
async def get_budget_endpoint(year: int, month: int, x_admin_key: str = Header("")):
    return _get_budget(year, month)


@financial_router.put("/api/admin/financial/budget/{year}/{month}")
async def upsert_budget(year: int, month: int, body: BudgetIn,
                        x_admin_key: str = Header("")):
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO financial_budget (year, month, income_budget, costs_budget,
                    marketing_budget, notes)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (year, month) DO UPDATE
                    SET income_budget=%s, costs_budget=%s, marketing_budget=%s,
                        notes=%s, updated_at=NOW()
            """, (year, month, body.income_budget, body.costs_budget,
                  body.marketing_budget, body.notes,
                  body.income_budget, body.costs_budget,
                  body.marketing_budget, body.notes))
            conn.commit()
    return {"year": year, "month": month, **body.dict()}


# ── Commission settings ───────────────────────────────────────────────────────

@financial_router.get("/api/admin/financial/commissions")
async def get_commissions_endpoint(x_admin_key: str = Header("")):
    return _get_commissions()


@financial_router.put("/api/admin/financial/commissions")
async def update_commissions(body: Dict, x_admin_key: str = Header("")):
    set_setting("financial_commissions", json.dumps(body))
    return body
