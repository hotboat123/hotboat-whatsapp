"""Sistema de Remuneraciones: utilidad real estimada por mes (ingresos reales
sin IVA − costos de gastos marcados por categoría − marketing − costos
manuales como gas/leña) y el bono real por trabajador que resulta de aplicar
esa utilidad a sus tramos configurados.

Reutiliza deliberadamente el motor de ingresos/marketing ya construido en
financial_router.py (mismas funciones que alimentan el P&L) en vez de
recalcular ingresos desde cero — ver _compute_resumen().
"""
import calendar as _cal
import json
import logging
from collections import defaultdict
from datetime import date
from typing import Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel

from app.db.connection import get_connection
from app.booking.operator_settings import get_setting, set_setting

logger = logging.getLogger(__name__)
remuneraciones_router = APIRouter()


def _check_auth(key: str):
    pass  # Auth disabled (same as gastos_router/admin_router)


def _ensure_tables():
    sql = """
    CREATE TABLE IF NOT EXISTS remuneraciones_costos_manuales (
        id SERIAL PRIMARY KEY,
        mes DATE NOT NULL,
        concepto TEXT NOT NULL,
        monto INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (mes, concepto)
    );
    CREATE INDEX IF NOT EXISTS idx_remuneraciones_costos_mes ON remuneraciones_costos_manuales(mes);
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        logger.info("✅ remuneraciones_costos_manuales table ready")
    except Exception as e:
        logger.error(f"remuneraciones _ensure_tables: {e}")


# ── Categorías de gastos marcadas para remuneraciones ────────────────────────

@remuneraciones_router.get("/api/admin/remuneraciones/categorias")
async def list_categorias_flags(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nombre, nivel, parent_id, color, icono, "
                "COALESCE(incluir_en_remuneraciones, FALSE) "
                "FROM gastos_categorias ORDER BY nivel, nombre"
            )
            rows = cur.fetchall()
    return {"ok": True, "categorias": [
        {"id": r[0], "nombre": r[1], "nivel": r[2], "parent_id": r[3],
         "color": r[4] or "#6b7280", "icono": r[5] or "📌",
         "incluir_en_remuneraciones": r[6]}
        for r in rows
    ]}


class CategoriaFlag(BaseModel):
    id: int
    incluir_en_remuneraciones: bool


class CategoriaFlagsBody(BaseModel):
    flags: List[CategoriaFlag]


@remuneraciones_router.put("/api/admin/remuneraciones/categorias")
async def save_categorias_flags(body: CategoriaFlagsBody, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            for f in body.flags:
                cur.execute(
                    "UPDATE gastos_categorias SET incluir_en_remuneraciones=%s WHERE id=%s",
                    (f.incluir_en_remuneraciones, f.id),
                )
        conn.commit()
    return {"ok": True}


# ── Costos manuales (gas, leña, etc.) ────────────────────────────────────────

@remuneraciones_router.get("/api/admin/remuneraciones/costos-manuales")
async def list_costos_manuales(year: int = Query(...), x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, mes, concepto, monto FROM remuneraciones_costos_manuales "
                "WHERE EXTRACT(YEAR FROM mes) = %s ORDER BY mes, concepto",
                (year,),
            )
            rows = cur.fetchall()
    return {"ok": True, "costos": [
        {"id": r[0], "mes": str(r[1]), "concepto": r[2], "monto": r[3]} for r in rows
    ]}


class CostoManualBody(BaseModel):
    mes: str  # 'YYYY-MM' o 'YYYY-MM-DD'
    concepto: str
    monto: int = 0


@remuneraciones_router.put("/api/admin/remuneraciones/costos-manuales")
async def save_costo_manual(body: CostoManualBody, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    raw = body.mes.strip()
    try:
        mes_date = date.fromisoformat(raw if len(raw) == 10 else f"{raw}-01")
    except ValueError:
        raise HTTPException(400, "mes inválido, usar YYYY-MM o YYYY-MM-DD")
    mes_date = mes_date.replace(day=1)
    concepto = body.concepto.strip()
    if not concepto:
        raise HTTPException(400, "concepto requerido")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO remuneraciones_costos_manuales (mes, concepto, monto) "
                "VALUES (%s,%s,%s) "
                "ON CONFLICT (mes, concepto) DO UPDATE SET monto=EXCLUDED.monto, updated_at=NOW()",
                (mes_date, concepto, body.monto),
            )
        conn.commit()
    return {"ok": True}


@remuneraciones_router.delete("/api/admin/remuneraciones/costos-manuales/{costo_id}")
async def delete_costo_manual(costo_id: int, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM remuneraciones_costos_manuales WHERE id=%s", (costo_id,))
        conn.commit()
    return {"ok": True}


# ── Trabajadores (config independiente de la del Simulador) ─────────────────

def _get_workers() -> list:
    raw = get_setting("remuneraciones_workers", "")
    if not raw:
        return []
    try:
        data = json.loads(raw)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _set_workers(workers: list) -> bool:
    return set_setting("remuneraciones_workers", json.dumps(workers, ensure_ascii=False))


@remuneraciones_router.get("/api/admin/remuneraciones/workers")
async def list_workers(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    return {"ok": True, "workers": _get_workers()}


class WorkerTramo(BaseModel):
    umbral_utilidad: int = 0
    pct_utilidad: float = 0


class WorkerBody(BaseModel):
    id: Optional[str] = None
    nombre: str
    sueldo_base: int = 0
    tramos: List[WorkerTramo] = []


class WorkersBody(BaseModel):
    workers: List[WorkerBody]


@remuneraciones_router.put("/api/admin/remuneraciones/workers")
async def save_workers(body: WorkersBody, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    workers = []
    for i, w in enumerate(body.workers):
        workers.append({
            "id": w.id or f"w{i + 1}",
            "nombre": w.nombre.strip(),
            "sueldo_base": w.sueldo_base,
            "tramos": [t.dict() for t in w.tramos],
        })
    _set_workers(workers)
    return {"ok": True, "workers": workers}


# ── Cálculo de utilidad real estimada ────────────────────────────────────────

def _costos_marcados_por_mes(d_from: date, d_to: date) -> Dict[str, int]:
    """Suma gastos_items (siempre hay >=1 item por gasto, ver
    _build_items_for_gasto en gastos_router.py — nunca hace falta un camino
    aparte para gastos sin items) cuya categoría (nivel 2, o nivel 1 si no
    hay nivel 2) está marcada incluir_en_remuneraciones, agrupado por mes."""
    sql = """
        SELECT to_char(g.fecha, 'YYYY-MM') AS mes, COALESCE(SUM(gi.monto), 0)
        FROM gastos_items gi
        JOIN gastos g ON gi.gasto_id = g.id
        LEFT JOIN gastos_categorias c1 ON gi.categoria1_id = c1.id
        LEFT JOIN gastos_categorias c2 ON gi.categoria2_id = c2.id
        WHERE g.fecha BETWEEN %s AND %s
          AND COALESCE(g.incluir_en_utilidad, TRUE)
          AND COALESCE(c2.incluir_en_remuneraciones, c1.incluir_en_remuneraciones, FALSE)
        GROUP BY mes
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (d_from, d_to))
            return {r[0]: int(r[1] or 0) for r in cur.fetchall()}


def _costos_manuales_por_mes(d_from: date, d_to: date) -> Dict[str, int]:
    sql = """
        SELECT to_char(mes, 'YYYY-MM'), COALESCE(SUM(monto), 0)
        FROM remuneraciones_costos_manuales
        WHERE mes >= date_trunc('month', %s::date) AND mes <= %s
        GROUP BY mes
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (d_from, d_to))
            return {r[0]: int(r[1] or 0) for r in cur.fetchall()}


def _compute_resumen(date_from: str, date_to: str) -> dict:
    """Ingresos reales (net de IVA, net de propinas) reutilizando el mismo
    motor del P&L (_build_pnl_days/_strip_iva_from_pnl_days en
    financial_router.py) + marketing ya auto-ingestado, menos costos de
    gastos marcados y costos manuales — por mes dentro del rango."""
    from app.booking.financial_router import (
        _get_commissions, _get_bookings_range, _get_marketing_costs_range,
        _get_google_ads_costs_range, _get_gift_cards_pnl_range,
        _build_pnl_days, _strip_iva_from_pnl_days,
    )

    try:
        d_from = date.fromisoformat(date_from)
        d_to = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(400, "Invalid date format, use YYYY-MM-DD")

    commissions = _get_commissions()
    bookings = _get_bookings_range(d_from, d_to)
    marketing = _get_marketing_costs_range(d_from, d_to)
    marketing_google = _get_google_ads_costs_range(d_from, d_to)
    gift_cards = _get_gift_cards_pnl_range(d_from, d_to)

    days = _build_pnl_days(bookings, marketing, commissions, d_from, d_to, gift_cards, marketing_google)
    _strip_iva_from_pnl_days(days)

    ingresos_by_month: Dict[str, int] = defaultdict(int)
    marketing_by_month: Dict[str, int] = defaultdict(int)
    for day_str, d in days.items():
        if not (date_from <= day_str <= date_to):
            continue
        month_key = day_str[:7]
        ingresos_by_month[month_key] += d["net_income"]
        marketing_by_month[month_key] += d["marketing"]

    costos_by_month = _costos_marcados_por_mes(d_from, d_to)
    manuales_by_month = _costos_manuales_por_mes(d_from, d_to)

    month_keys = sorted(
        set(ingresos_by_month) | set(costos_by_month)
        | set(manuales_by_month) | set(marketing_by_month)
    )
    meses = []
    for mk in month_keys:
        ingresos = ingresos_by_month.get(mk, 0)
        costos = costos_by_month.get(mk, 0)
        mkt = marketing_by_month.get(mk, 0)
        manual = manuales_by_month.get(mk, 0)
        meses.append({
            "mes": mk,
            "ingresos": ingresos,
            "costos_marcados": costos,
            "marketing": mkt,
            "costos_manuales": manual,
            "utilidad_estimada": ingresos - costos - mkt - manual,
        })

    totales = {
        "ingresos": sum(m["ingresos"] for m in meses),
        "costos_marcados": sum(m["costos_marcados"] for m in meses),
        "marketing": sum(m["marketing"] for m in meses),
        "costos_manuales": sum(m["costos_manuales"] for m in meses),
        "utilidad_estimada": sum(m["utilidad_estimada"] for m in meses),
    }
    return {"date_from": date_from, "date_to": date_to, "meses": meses, "totales": totales}


@remuneraciones_router.get("/api/admin/remuneraciones/resumen")
async def get_resumen(
    date_from: str = Query(...),
    date_to: str = Query(...),
    x_admin_key: str = Header(""),
):
    _check_auth(x_admin_key)
    data = _compute_resumen(date_from, date_to)
    return {"ok": True, **data}


# ── Bono real por trabajador ──────────────────────────────────────────────────

def _calc_bono(worker: dict, utilidad: int) -> dict:
    """El tramo aplicable es el de mayor umbral_utilidad que la utilidad del
    mes alcanza (tramos ordenados ascendente por umbral); su pct_utilidad se
    aplica sobre la utilidad completa del mes, no de forma progresiva por
    tramo — igual de simple que el bono por tramo de utilidad que ya existe
    en el Simulador, pero sobre la utilidad real en vez de la hipotética."""
    tramos = sorted(worker.get("tramos") or [], key=lambda t: t.get("umbral_utilidad", 0))
    pct = 0.0
    for t in tramos:
        if utilidad >= t.get("umbral_utilidad", 0):
            pct = float(t.get("pct_utilidad", 0) or 0)
    bono = max(0, round(utilidad * pct / 100)) if pct else 0
    sueldo_base = int(worker.get("sueldo_base") or 0)
    return {
        "id": worker.get("id"), "nombre": worker.get("nombre"),
        "sueldo_base": sueldo_base, "pct_aplicado": pct,
        "bono_utilidad": bono, "total": sueldo_base + bono,
    }


@remuneraciones_router.get("/api/admin/remuneraciones/bonos")
async def get_bonos(
    year: int = Query(...),
    month: int = Query(...),
    x_admin_key: str = Header(""),
):
    _check_auth(x_admin_key)
    d_from = date(year, month, 1)
    d_to = date(year, month, _cal.monthrange(year, month)[1])
    resumen = _compute_resumen(d_from.isoformat(), d_to.isoformat())
    utilidad = resumen["totales"]["utilidad_estimada"]
    workers = _get_workers()
    bonos = [_calc_bono(w, utilidad) for w in workers]
    return {
        "ok": True, "year": year, "month": month,
        "utilidad_estimada": utilidad, "bonos": bonos,
    }
