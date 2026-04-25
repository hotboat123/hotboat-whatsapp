"""Admin dashboard router — uses all_appointments as single source of truth."""
import asyncio
import json
import logging
import os
import re
import shutil
from typing import List, Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Header, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.db.connection import get_connection

logger = logging.getLogger(__name__)
admin_router = APIRouter()
CHILE_TZ = ZoneInfo("America/Santiago")
TABLE = "all_appointments"


def _normalize_pagos_for_db(pagos: list) -> list:
    """Store pago['date'] as YYYY-MM-DD or '' (uses paid_on if date missing; strips paid_on after merge)."""
    if not pagos:
        return pagos
    out: list = []
    for p in pagos:
        if not isinstance(p, dict):
            out.append(p)
            continue
        row = dict(p)
        raw = row.get("date")
        if raw is None or (isinstance(raw, str) and not str(raw).strip()):
            raw = row.get("paid_on")
        if hasattr(raw, "strftime"):
            norm = raw.strftime("%Y-%m-%d")
        elif raw is None:
            norm = ""
        else:
            s = str(raw).strip()
            m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
            if m:
                norm = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
            else:
                m2 = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", s)
                if m2:
                    norm = f"{m2.group(3)}-{m2.group(2).zfill(2)}-{m2.group(1).zfill(2)}"
                else:
                    norm = ""
        row["date"] = norm
        row.pop("paid_on", None)
        out.append(row)
    return out


from app.booking.operator_settings import (
    get_vacation_days, add_vacation_day, remove_vacation_day,
    get_setting, set_setting, is_urgency_mode,
    get_operating_hours, set_operating_hours,
    get_urgency_days, set_urgency_day, remove_urgency_day,
)


# ── Auth ──────────────────────────────────────────────────────────────────────

def _check_auth(key: str):
    pass  # Auth temporarily disabled


# ── HTML page ─────────────────────────────────────────────────────────────────

@admin_router.get("/admin/reservas", response_class=HTMLResponse)
async def admin_page():
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "admin-bookings.html")
    try:
        with open(path, encoding="utf-8") as f:
            return HTMLResponse(f.read())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="admin-bookings.html not found")


# ── List reservations ─────────────────────────────────────────────────────────

@admin_router.get("/api/admin/reservas")
async def list_reservas(
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    x_admin_key: str = Header(""),
):
    _check_auth(x_admin_key)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                wheres, params = [], []
                if desde:
                    wheres.append("fecha >= %s"); params.append(desde)
                if hasta:
                    wheres.append("fecha <= %s"); params.append(hasta)
                if status and status != "all":
                    wheres.append("status = %s"); params.append(status)
                if source and source != "all":
                    wheres.append("source = %s"); params.append(source)
                if search:
                    wheres.append(
                        "(nombre_cliente ILIKE %s OR telefono ILIKE %s OR email ILIKE %s)"
                    )
                    s = f"%{search}%"; params += [s, s, s]
                where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""
                params.append(limit)
                cur.execute(f"""
                    SELECT id, source, source_id, appointment_id,
                           fecha, hora, nombre_cliente, email, telefono,
                           servicio, num_personas, num_adultos, num_ninos,
                           nombre_adultos, nombre_ninos,
                           ingreso_reserva, ingreso_extras, ingreso_total,
                           has_flex, COALESCE(flex_amount,0) AS flex_amount,
                           costo_operativo_fijo, costo_operativo_variable, costo_operativo_total,
                           ciudad_origen, como_supieron, clima_del_dia,
                           categoria_clientes, tipo_clientes, quien_atendio,
                           status, tiene_cruce, extras_json, observaciones,
                           payment_id, payment_status,
                           COALESCE(pagos, '[]'::jsonb) AS pagos,
                           COALESCE(descuentos, '[]'::jsonb) AS descuentos,
                           created_at, updated_at
                    FROM {TABLE}
                    {where_sql}
                    ORDER BY fecha DESC, hora DESC NULLS LAST
                    LIMIT %s
                """, params)
                cols = [d[0] for d in cur.description]
                rows = []
                for row in cur.fetchall():
                    r = dict(zip(cols, row))
                    for k in ("fecha", "created_at", "updated_at"):
                        if r.get(k): r[k] = r[k].isoformat()
                    if r.get("hora"): r["hora"] = str(r["hora"])
                    for k in ("ingreso_reserva", "ingreso_extras", "ingreso_total",
                              "flex_amount",
                              "costo_operativo_fijo", "costo_operativo_variable", "costo_operativo_total"):
                        if r.get(k) is not None: r[k] = float(r[k])
                    if isinstance(r.get("pagos"), list):
                        r["pagos"] = _normalize_pagos_for_db(r["pagos"])
                    rows.append(r)
        return {"reservas": rows, "total": len(rows)}
    except Exception as e:
        logger.error(f"Error listing reservas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Single reservation ────────────────────────────────────────────────────────

@admin_router.get("/api/admin/reservas/{rid}")
async def get_reserva(rid: int, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT *, COALESCE(pagos,'[]'::jsonb) AS pagos, COALESCE(descuentos,'[]'::jsonb) AS descuentos FROM {TABLE} WHERE id=%s", (rid,))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Not found")
                cols = [d[0] for d in cur.description]
                r = dict(zip(cols, row))
                for k in ("fecha", "created_at", "updated_at"):
                    if r.get(k): r[k] = r[k].isoformat()
                if r.get("hora"): r["hora"] = str(r["hora"])
                for k in ("ingreso_reserva", "ingreso_extras", "ingreso_total",
                          "costo_operativo_fijo", "costo_operativo_variable", "costo_operativo_total"):
                    if r.get(k) is not None: r[k] = float(r[k])
                # Ensure every reservation has a usable booking_ref for T&C firma links.
                # hotboat_web bookings: source_id IS the booking_ref (HB-xxxx).
                # All others: AA-{id} is a stable universal ref.
                if not r.get("booking_ref"):
                    if r.get("source") == "hotboat_web" and r.get("source_id"):
                        r["booking_ref"] = r["source_id"]
                    else:
                        r["booking_ref"] = f"AA-{r['id']}"
                if isinstance(r.get("pagos"), list):
                    r["pagos"] = _normalize_pagos_for_db(r["pagos"])
                return r
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Update reservation (editable fields) ──────────────────────────────────────

class UpdateReservaRequest(BaseModel):
    status: Optional[str] = None
    nombre_cliente: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    observaciones: Optional[str] = None
    ciudad_origen: Optional[str] = None
    como_supieron: Optional[str] = None
    clima_del_dia: Optional[str] = None
    categoria_clientes: Optional[str] = None
    tipo_clientes: Optional[str] = None
    quien_atendio: Optional[str] = None
    num_personas: Optional[int] = None
    num_adultos: Optional[int] = None
    num_ninos: Optional[int] = None
    nombre_adultos: Optional[str] = None
    nombre_ninos: Optional[str] = None
    ingreso_reserva: Optional[float] = None
    ingreso_extras: Optional[float] = None
    ingreso_total: Optional[float] = None
    costo_operativo_fijo: Optional[float] = None
    costo_operativo_variable: Optional[float] = None
    costo_operativo_total: Optional[float] = None
    tiene_cruce: Optional[bool] = None
    extras_json: Optional[dict] = None
    pagos: Optional[list] = None
    descuentos: Optional[list] = None
    fecha: Optional[str] = None
    hora: Optional[str] = None
    medio_contacto: Optional[str] = None
    has_flex: Optional[bool] = None
    flex_amount: Optional[float] = None
    coupon_code: Optional[str] = None
    coupon_discount: Optional[float] = None


@admin_router.put("/api/admin/reservas/{rid}")
async def update_reserva(rid: int, body: UpdateReservaRequest, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    # coupon fields are nullable — include them if explicitly sent in the request
    if 'coupon_code' in body.model_fields_set or 'coupon_discount' in body.model_fields_set:
        _ensure_coupons_table()
    if 'coupon_code' in body.model_fields_set:
        updates['coupon_code'] = body.coupon_code
    if 'coupon_discount' in body.model_fields_set:
        updates['coupon_discount'] = body.coupon_discount or 0
    # has_flex is a boolean that can be False — include if explicitly sent
    if 'has_flex' in body.model_fields_set:
        updates['has_flex'] = body.has_flex
    if 'flex_amount' in body.model_fields_set:
        updates['flex_amount'] = body.flex_amount or 0
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    try:
        from psycopg.types.json import Jsonb as PgJson
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Convert dict/list fields for JSONB
                if "extras_json" in updates:
                    updates["extras_json"] = PgJson(updates["extras_json"])
                if "pagos" in updates:
                    updates["pagos"] = PgJson(_normalize_pagos_for_db(updates["pagos"]))
                if "descuentos" in updates:
                    updates["descuentos"] = PgJson(updates["descuentos"])

                set_parts = [f"{k}=%s" for k in updates]
                set_parts.append("updated_at=NOW()")
                params = list(updates.values()) + [rid]
                cur.execute(
                    f"UPDATE {TABLE} SET {', '.join(set_parts)} WHERE id=%s",
                    params
                )

                # Cascade status to source tables
                if "status" in updates:
                    cur.execute(f"SELECT source, source_id FROM {TABLE} WHERE id=%s", (rid,))
                    row = cur.fetchone()
                    if row:
                        src, src_id = row
                        if src == "booknetic" and src_id:
                            cur.execute(
                                "UPDATE booknetic_appointments SET status=%s, updated_at=NOW() WHERE id=%s",
                                (updates["status"], src_id)
                            )
                        elif src == "hotboat_web" and src_id:
                            cur.execute(
                                "UPDATE hotboat_appointments SET status=%s, updated_at=NOW() WHERE booking_ref=%s",
                                (updates["status"], src_id)
                            )
                        elif src == "sheets" and src_id:
                            cur.execute(
                                "UPDATE reservas_con_extras SET status=%s, updated_at=NOW() WHERE id=%s",
                                (updates["status"], int(src_id))
                            )

                conn.commit()

        # ── Trigger status-change emails ───────────────────────────────────
        if "status" in updates:
            try:
                from app.booking.booking_email import send_email_for_trigger_with_data
                with get_connection() as conn3:
                    with conn3.cursor() as cur3:
                        cur3.execute(
                            f"SELECT id, email, nombre_cliente, telefono, fecha, hora, "
                            f"num_personas, ingreso_total, ingreso_reserva, ingreso_extras, "
                            f"source_id, source FROM {TABLE} WHERE id=%s",
                            (rid,)
                        )
                        rr = cur3.fetchone()
                if rr:
                    email_to = (rr[1] or "").strip()
                    row_data = {
                        "id": rr[0],
                        "nombre_cliente": rr[2], "telefono": rr[3],
                        "fecha": str(rr[4]) if rr[4] else "",
                        "hora": str(rr[5])[:5] if rr[5] else "",
                        "num_personas": rr[6],
                        "ingreso_total": rr[7], "ingreso_reserva": rr[8], "ingreso_extras": rr[9],
                        "source_id": rr[10], "source": rr[11],
                        "status": updates["status"],
                    }
                    new_status = updates["status"]
                    trigger = "booking_cancelled" if new_status == "cancelled" else "booking_status_changed"
                    if email_to:
                        em = send_email_for_trigger_with_data(trigger, email_to, row_data)
                        logger.info("Status-change email trigger=%s result=%s", trigger, em)
            except Exception as em_err:
                logger.warning("Status-change email error: %s", em_err)

        return {"ok": True}
    except Exception as e:
        logger.error(f"Error updating reserva {rid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Create reservation ────────────────────────────────────────────────────────

@admin_router.post("/api/admin/reservas")
async def create_reserva(x_admin_key: str = Header(""), request: Request = None):
    _check_auth(x_admin_key)
    try:
        from psycopg.types.json import Jsonb as PgJson
        body = await request.json()
        fecha = body.get("fecha")
        hora = body.get("hora")
        nombre = (body.get("nombre_cliente") or "").strip()
        if not fecha or not nombre:
            raise HTTPException(status_code=400, detail="fecha y nombre_cliente son obligatorios")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"""
                    INSERT INTO {TABLE}
                    (source, fecha, hora, nombre_cliente, telefono, email,
                     servicio, num_personas, ingreso_reserva, ingreso_extras, ingreso_total,
                     costo_operativo_fijo, status, extras_json, descuentos, pagos, created_at, updated_at)
                    VALUES ('manual', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '{{}}', '[]', '[]', NOW(), NOW())
                    RETURNING id
                """, (fecha, hora or None, nombre,
                      body.get("telefono") or None, body.get("email") or None,
                      body.get("servicio") or "HotBoat Trip",
                      body.get("num_personas") or None,
                      float(body.get("ingreso_reserva") or 0),
                      float(body.get("ingreso_extras") or 0),
                      float(body.get("ingreso_total") or body.get("ingreso_reserva") or 0),
                      float(body.get("costo_operativo_fijo") or 18000),
                      body.get("status") or "confirmed"))
                new_id = cur.fetchone()[0]
                conn.commit()

        # Optionally send confirmation email using raw data
        send_confirmation = body.get("send_confirmation", False)
        customer_email = (body.get("email") or "").strip()
        if send_confirmation and customer_email:
            try:
                from app.booking.booking_email import send_email_for_trigger_with_data
                row_data = {
                    "id": new_id,
                    "booking_ref": f"MANUAL-{new_id}",
                    "customer_name": nombre,
                    "customer_phone": body.get("telefono") or "",
                    "customer_email": customer_email,
                    "booking_date": str(fecha),
                    "booking_time": str(hora or ""),
                    "num_people": body.get("num_personas") or "",
                    "subtotal": float(body.get("ingreso_reserva") or 0),
                    "extras_total": 0,
                    "total_price": float(body.get("ingreso_total") or body.get("ingreso_reserva") or 0),
                    "status": body.get("status") or "confirmed",
                    "source": "manual",
                }
                em = send_email_for_trigger_with_data("booking_created", customer_email, row_data)
                logger.info(f"Manual booking confirmation email: {em}")
            except Exception as em_err:
                logger.warning(f"Manual booking confirmation email failed: {em_err}")

        return {"ok": True, "id": new_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating reserva: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Delete reservation ────────────────────────────────────────────────────────

@admin_router.delete("/api/admin/reservas/{rid}")
async def delete_reserva(rid: int, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT nombre_cliente, fecha, source, source_id FROM {TABLE} WHERE id=%s", (rid,))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Not found")
                _, _, source, source_id = row
                cur.execute(f"DELETE FROM {TABLE} WHERE id=%s", (rid,))
                # If this was a web booking, also cancel it in hotboat_appointments
                # so the auto-sync doesn't re-insert it on the next run
                if source == "hotboat_web" and source_id:
                    cur.execute(
                        "UPDATE hotboat_appointments SET status='cancelled' WHERE booking_ref=%s",
                        (source_id,)
                    )
                conn.commit()
        return {"ok": True, "deleted": rid}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting reserva {rid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Stats ──────────────────────────────────────────────────────────────────────

@admin_router.get("/api/admin/reports/cash")
async def get_cash_report(
    days: int = Query(7, ge=1, le=365),
    method: str = Query(""),
    x_admin_key: str = Header(""),
):
    """Daily cash/payment breakdown from all_appointments.pagos JSONB array."""
    _check_auth(x_admin_key)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                method_filter = ""
                params: list = [days]
                if method:
                    method_filter = "AND LOWER(pago->>'method') = %s"
                    params.append(method.lower())

                cur.execute(f"""
                    SELECT
                        (pago->>'date')::date           AS dia,
                        COUNT(*)::int                   AS cnt,
                        SUM((pago->>'amount')::numeric) AS total,
                        LOWER(pago->>'method')          AS met
                    FROM all_appointments,
                         jsonb_array_elements(COALESCE(pagos, '[]'::jsonb)) AS pago
                    WHERE (pago->>'date')::date >= CURRENT_DATE - (%s || ' days')::interval
                      AND (pago->>'amount') IS NOT NULL
                      AND (pago->>'amount')::numeric > 0
                      {method_filter}
                    GROUP BY dia, met
                    ORDER BY dia ASC, met
                """, params)
                rows_raw = cur.fetchall()

        from collections import defaultdict
        by_day: dict = defaultdict(lambda: {"count": 0, "total": 0.0, "by_method": {}})
        for dia, cnt, total, met in rows_raw:
            key = str(dia)
            by_day[key]["count"] += cnt
            by_day[key]["total"] = round(by_day[key]["total"] + float(total or 0), 0)
            by_day[key]["by_method"][met or "otro"] = round(
                by_day[key]["by_method"].get(met or "otro", 0) + float(total or 0), 0
            )

        rows = [
            {"fecha": k, "count": v["count"], "total": v["total"], "by_method": v["by_method"]}
            for k, v in sorted(by_day.items())
        ]
        return {"rows": rows}
    except Exception as e:
        logger.exception("cash report error")
        raise HTTPException(500, str(e))


@admin_router.get("/api/admin/stats")
async def get_stats(
    year: int = Query(2026),
    x_admin_key: str = Header(""),
):
    _check_auth(x_admin_key)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Monthly revenue
                cur.execute(f"""
                    SELECT EXTRACT(MONTH FROM fecha)::int AS mes,
                           COUNT(*) AS n_reservas,
                           SUM(ingreso_total) AS ingresos,
                           SUM(ingreso_extras) AS extras,
                           SUM(costo_operativo_total) AS costos,
                           SUM(ingreso_total - COALESCE(costo_operativo_total,0)) AS margen
                    FROM {TABLE}
                    WHERE EXTRACT(YEAR FROM fecha)=%s
                      AND (status IS NULL OR status NOT IN ('cancelled','rejected','cancelada','rechazada'))
                    GROUP BY mes ORDER BY mes
                """, (year,))
                monthly = [{"mes": int(r[0]), "n_reservas": int(r[1]),
                            "ingresos": float(r[2] or 0), "extras": float(r[3] or 0),
                            "costos": float(r[4] or 0), "margen": float(r[5] or 0)}
                           for r in cur.fetchall()]

                # Status breakdown
                cur.execute(f"""
                    SELECT status, COUNT(*) FROM {TABLE}
                    WHERE EXTRACT(YEAR FROM fecha)=%s GROUP BY status
                """, (year,))
                by_status = {(r[0] or "sin estado"): int(r[1]) for r in cur.fetchall()}

                # Source breakdown
                cur.execute(f"""
                    SELECT source, COUNT(*) FROM {TABLE}
                    WHERE EXTRACT(YEAR FROM fecha)=%s GROUP BY source
                """, (year,))
                by_source = {(r[0] or "desconocido"): int(r[1]) for r in cur.fetchall()}

                # Totals
                cur.execute(f"""
                    SELECT COUNT(*), SUM(ingreso_total), AVG(ingreso_total), AVG(num_personas::float)
                    FROM {TABLE}
                    WHERE EXTRACT(YEAR FROM fecha)=%s
                      AND (status IS NULL OR status NOT IN ('cancelled','rejected','cancelada','rechazada'))
                """, (year,))
                r = cur.fetchone()
                totals = {
                    "total_reservas": int(r[0] or 0),
                    "total_ingresos": float(r[1] or 0),
                    "avg_reserva": float(r[2] or 0),
                    "avg_personas": float(r[3] or 0) if r[3] else 0,
                }

        return {"monthly": monthly, "by_status": by_status, "by_source": by_source, **totals}
    except Exception as e:
        logger.error(f"Stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Log viewer ───────────────────────────────────────────────────────────────

@admin_router.get("/api/admin/logs")
async def get_logs(
    n:      int = Query(200, ge=1, le=500),
    level:  str = Query(""),
    search: str = Query(""),
    x_admin_key: str = Header(""),
):
    """Return the last N in-memory log lines, optionally filtered."""
    from app.log_buffer import log_buffer
    lines = list(log_buffer)[-n:]
    if level:
        lines = [l for l in lines if l["level"] == level.upper()]
    if search:
        s = search.lower()
        lines = [l for l in lines if s in l["message"].lower() or s in l["logger"].lower()]
    return {"count": len(lines), "lines": lines}


# ── Clients ───────────────────────────────────────────────────────────────────

@admin_router.get("/api/admin/clients")
async def list_clients(
    search: Optional[str] = Query(None),
    limit: int = Query(200),
    x_admin_key: str = Header(""),
):
    _check_auth(x_admin_key)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                where, params = "", []
                if search:
                    where = "WHERE nombre_cliente ILIKE %s OR telefono ILIKE %s OR email ILIKE %s"
                    s = f"%{search}%"; params = [s, s, s]
                params.append(limit)
                cur.execute(f"""
                    SELECT telefono,
                           MAX(nombre_cliente) AS nombre,
                           MAX(email) AS email,
                           COUNT(*) AS total_reservas,
                           SUM(ingreso_total) AS total_gastado,
                           MAX(fecha) AS ultima_reserva,
                           MIN(fecha) AS primera_reserva
                    FROM {TABLE}
                    {where}
                    GROUP BY telefono
                    ORDER BY total_reservas DESC, ultima_reserva DESC
                    LIMIT %s
                """, params)
                cols = [d[0] for d in cur.description]
                clients = []
                for row in cur.fetchall():
                    c = dict(zip(cols, row))
                    for k in ("ultima_reserva", "primera_reserva"):
                        if c.get(k): c[k] = c[k].isoformat()
                    if c.get("total_gastado"): c["total_gastado"] = float(c["total_gastado"])
                    clients.append(c)
        return {"clients": clients}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Vacation days ─────────────────────────────────────────────────────────────

@admin_router.get("/api/admin/vacation-days")
async def list_vacation_days(
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    x_admin_key: str = Header(""),
):
    _check_auth(x_admin_key)
    from datetime import date as _date
    fd = _date.fromisoformat(desde) if desde else None
    td = _date.fromisoformat(hasta) if hasta else None
    return {"vacation_days": get_vacation_days(fd, td)}


class VacationDayRequest(BaseModel):
    date: str
    reason: Optional[str] = ""


@admin_router.post("/api/admin/vacation-days")
async def add_vacation(body: VacationDayRequest, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    from datetime import date as _date
    d = _date.fromisoformat(body.date)
    ok = add_vacation_day(d, body.reason or "")
    if not ok:
        raise HTTPException(status_code=500, detail="Error adding vacation day")
    return {"ok": True, "date": body.date}


@admin_router.delete("/api/admin/vacation-days/{fecha}")
async def delete_vacation(fecha: str, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    from datetime import date as _date
    d = _date.fromisoformat(fecha)
    ok = remove_vacation_day(d)
    return {"ok": ok, "date": fecha}


# ── Per-day urgency overrides ─────────────────────────────────────────────────

@admin_router.get("/api/admin/urgency-days")
async def list_urgency_days(
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    x_admin_key: str = Header(""),
):
    _check_auth(x_admin_key)
    from datetime import date as _date
    fd = _date.fromisoformat(desde) if desde else None
    td = _date.fromisoformat(hasta) if hasta else None
    return {"urgency_days": get_urgency_days(fd, td)}


class UrgencyDayRequest(BaseModel):
    date: str
    enabled: bool = True
    reason: Optional[str] = ""


@admin_router.post("/api/admin/urgency-days")
async def add_urgency_day_route(body: UrgencyDayRequest, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    from datetime import date as _date
    d = _date.fromisoformat(body.date)
    ok = set_urgency_day(d, body.enabled, body.reason or "")
    if not ok:
        raise HTTPException(status_code=500, detail="Error setting urgency day")
    return {"ok": True, "date": body.date, "enabled": body.enabled}


@admin_router.delete("/api/admin/urgency-days/{fecha}")
async def delete_urgency_day_route(fecha: str, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    from datetime import date as _date
    d = _date.fromisoformat(fecha)
    ok = remove_urgency_day(d)
    return {"ok": ok, "date": fecha}


# ── Settings ──────────────────────────────────────────────────────────────────

@admin_router.get("/api/admin/settings")
async def get_all_settings(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    from app.booking.operator_settings import get_urgency_config, get_dp_config
    return {
        "urgency_mode": is_urgency_mode(),
        "urgency_config": get_urgency_config(),
        "dynamic_pricing": get_dp_config(),
        "booking_visitor_notif": get_setting("booking_visitor_notif", "false") == "true",
    }


@admin_router.put("/api/admin/settings/visitor-notif")
async def set_visitor_notif(x_admin_key: str = Header(""), enabled: bool = True):
    _check_auth(x_admin_key)
    set_setting("booking_visitor_notif", "true" if enabled else "false")
    return {"ok": True, "booking_visitor_notif": enabled}


class SettingsRequest(BaseModel):
    urgency_mode: Optional[bool] = None


@admin_router.put("/api/admin/settings")
async def update_settings(body: SettingsRequest, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    if body.urgency_mode is not None:
        set_setting("urgency_mode", "true" if body.urgency_mode else "false")
    return {"ok": True, "urgency_mode": is_urgency_mode()}


# ── Operating hours ────────────────────────────────────────────────────────────

@admin_router.get("/api/admin/operating-hours")
async def get_op_hours(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    return {"hours": get_operating_hours()}


class OperatingHoursRequest(BaseModel):
    hours: list  # list of "HH:MM" strings


@admin_router.put("/api/admin/operating-hours")
async def update_op_hours(body: OperatingHoursRequest, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    if not body.hours:
        raise HTTPException(status_code=400, detail="Debe haber al menos un horario")
    set_operating_hours(body.hours)
    return {"ok": True, "hours": get_operating_hours()}


# ── Urgency config ─────────────────────────────────────────────────────────────

@admin_router.get("/api/admin/urgency-config")
async def get_urgency_cfg(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    from app.booking.operator_settings import get_urgency_config
    return get_urgency_config()


class UrgencyConfigRequest(BaseModel):
    seed_times: Optional[list] = None
    gap_hours: Optional[float] = None


@admin_router.put("/api/admin/urgency-config")
async def update_urgency_cfg(body: UrgencyConfigRequest, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    from app.booking.operator_settings import get_urgency_config, set_urgency_config
    cfg = get_urgency_config()
    if body.seed_times is not None:
        cfg["seed_times"] = [t for t in body.seed_times if t]
    if body.gap_hours is not None:
        cfg["gap_hours"] = max(0.5, float(body.gap_hours))
    set_urgency_config(cfg)
    return {"ok": True, "config": cfg}


# ── Dynamic pricing config ─────────────────────────────────────────────────────

@admin_router.get("/api/admin/dynamic-pricing")
async def get_dp(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    from app.booking.operator_settings import get_dp_config
    return get_dp_config()


@admin_router.put("/api/admin/dynamic-pricing")
async def update_dp(request: Request, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    from app.booking.operator_settings import set_dp_config
    body = await request.json()
    set_dp_config(body)
    return {"ok": True}


# ── T&C Signatures ────────────────────────────────────────────────────────────

@admin_router.get("/api/admin/reservas/{booking_ref}/firmas")
async def get_firmas(booking_ref: str, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    from app.booking.db import get_signatures_by_booking_ref, ensure_signatures_table
    try:
        ensure_signatures_table()
    except Exception:
        pass
    sigs = get_signatures_by_booking_ref(booking_ref)
    return {"booking_ref": booking_ref, "signatures": sigs, "count": len(sigs)}


@admin_router.post("/api/admin/reservas/{booking_ref}/firmas/summary-email")
async def send_firmas_summary(booking_ref: str, x_admin_key: str = Header("")):
    """Manually trigger the signature summary email for a booking."""
    _check_auth(x_admin_key)
    from app.booking.db import get_signatures_by_booking_ref
    from app.booking.signatures_router import _resolve_booking
    from app.booking.signatures_email import send_booking_signature_summary
    booking = _resolve_booking(booking_ref)
    if not booking:
        raise HTTPException(status_code=404, detail="Reserva no encontrada")
    sigs = get_signatures_by_booking_ref(booking_ref)
    send_booking_signature_summary(booking_ref, booking, sigs)
    return {"ok": True, "sent_to": "hotboatnotification@gmail.com", "signatures": len(sigs)}


# ── Email workflows (Booknetic-style multi-trigger, Resend) ──────────────────

@admin_router.get("/api/admin/email-workflows")
async def get_email_workflows_endpoint(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    from app.booking.operator_settings import get_email_workflows, TRIGGER_META
    from app.config import get_settings
    s = get_settings()
    return {
        "workflows": get_email_workflows(),
        "trigger_meta": TRIGGER_META,
        "from_hint": (getattr(s, "resend_from_confirmations", "") or getattr(s, "email_from", "") or "").strip(),
        "bcc_configured": bool((getattr(s, "resend_bcc_booking", "") or "").strip()),
        "has_resend_key": bool((getattr(s, "resend_api_key", "") or "").strip()),
    }


class EmailWorkflowBody(BaseModel):
    enabled: Optional[bool] = None
    subject: Optional[str] = None
    body_html: Optional[str] = None
    days_after: Optional[int] = None  # booking_followup


@admin_router.put("/api/admin/email-workflows/{trigger}")
async def put_email_workflow(trigger: str, body: EmailWorkflowBody,
                              x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    from app.booking.operator_settings import set_email_workflow, TRIGGER_META
    if trigger not in TRIGGER_META:
        raise HTTPException(status_code=404, detail=f"Trigger '{trigger}' no existe")
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    set_email_workflow(trigger, data)
    from app.booking.operator_settings import get_email_workflow
    return {"ok": True, "trigger": trigger, "config": get_email_workflow(trigger)}


class EmailWorkflowTestBody(BaseModel):
    to: Optional[str] = None


@admin_router.get("/api/admin/email-workflows/{trigger}/default-html")
async def get_workflow_default_html(trigger: str, x_admin_key: str = Header("")):
    """Return the built-in HTML template rendered with sample booking data."""
    _check_auth(x_admin_key)
    from app.booking.operator_settings import TRIGGER_META
    if trigger not in TRIGGER_META:
        raise HTTPException(status_code=404, detail=f"Trigger '{trigger}' no existe")
    from app.booking.booking_email import get_default_html_for_trigger
    return {"trigger": trigger, "html": get_default_html_for_trigger(trigger)}


@admin_router.post("/api/admin/email-workflows/{trigger}/test")
async def post_email_workflow_test(trigger: str, body: EmailWorkflowTestBody,
                                    x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    from app.booking.operator_settings import TRIGGER_META
    if trigger not in TRIGGER_META:
        raise HTTPException(status_code=404, detail=f"Trigger '{trigger}' no existe")
    from app.config import get_settings
    from app.booking.booking_email import send_test_email_for_trigger
    to_addr = (body.to or "").strip() or (get_settings().business_email or "").strip()
    if not to_addr:
        raise HTTPException(status_code=400, detail="Indica un correo de prueba")
    result = send_test_email_for_trigger(trigger, to_addr)
    if not result.get("sent"):
        reason = result.get("reason") or "send failed"
        logger.error("Test email failed trigger=%s to=%s: %s", trigger, to_addr, reason)
        raise HTTPException(status_code=500, detail=reason)
    return {"ok": True, **result}


@admin_router.post("/api/admin/pre-booking-notif/test")
async def test_pre_booking_notif(x_admin_key: str = Header("")):
    """Send a test pre-booking notification using a fake booking (for visual preview)."""
    _check_auth(x_admin_key)
    from app.booking.signatures_email import send_pre_booking_notification
    fake_booking = {
        "booking_ref":   "HB-2026-TEST1",
        "customer_name": "Cliente de Prueba",
        "customer_phone": "+56 9 1234 5678",
        "customer_email": "cliente@ejemplo.com",
        "booking_date":  "2026-04-05",
        "booking_time":  "15:00:00",
        "num_people":    4,
        "total_price":   179990,
        "extras_total":  29990,
        "extras": [
            {"name": "Tabla de quesos", "price": 19990, "quantity": 1},
            {"name": "Botella de vino", "price": 9990,  "quantity": 1},
        ],
        "notes":         "Celebran cumpleaños. Llevan torta.",
        "status":        "confirmed",
        "source":        "hotboat_web",
        "customer_language": "es",
    }
    try:
        await asyncio.to_thread(send_pre_booking_notification, fake_booking, prev_bookings=2)
        return {"ok": True, "message": "Notificación de prueba enviada a hotboatnotification@gmail.com"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ReciboSendBody(BaseModel):
    to: str
    subject: str
    html: str


@admin_router.post("/api/admin/recibo/send")
async def send_recibo_email(body: ReciboSendBody, x_admin_key: str = Header("")):
    """Send the receipt HTML to the client's email via Resend."""
    _check_auth(x_admin_key)
    to_addr = body.to.strip()
    if not to_addr or "@" not in to_addr:
        raise HTTPException(status_code=400, detail="Email del cliente no válido")

    from app.config import get_settings
    from app.email.resend_booking import send_booking_html

    settings = get_settings()
    api_key = (getattr(settings, "resend_api_key", "") or "").strip()
    if not api_key:
        raise HTTPException(status_code=500, detail="RESEND_API_KEY no configurado")

    from_addr = (
        getattr(settings, "resend_from_confirmations", "")
        or getattr(settings, "email_from", "")
        or "noreply@reservas.hotboat.cl"
    ).strip()

    try:
        await asyncio.to_thread(
            send_booking_html,
            to=to_addr,
            subject=body.subject,
            html=body.html,
            from_address=from_addr,
            api_key=api_key,
        )
        logger.info("Recibo enviado a %s — %s", to_addr, body.subject)
        return {"ok": True, "to": to_addr}
    except Exception as e:
        error_detail = str(e)
        try:
            if hasattr(e, "body"):
                error_detail += f" | {e.body}"
        except Exception:
            pass
        logger.error("send_recibo_email failed to=%s: %s", to_addr, error_detail)
        raise HTTPException(status_code=500, detail=error_detail)


@admin_router.post("/api/admin/daily-summary/send")
async def send_daily_summary_now(x_admin_key: str = Header("")):
    """Manually trigger the daily morning summary email (same as the 08:00 job)."""
    _check_auth(x_admin_key)
    from app.booking.booking_email import send_daily_summary_email
    result = await asyncio.to_thread(send_daily_summary_email)
    if not result.get("sent"):
        raise HTTPException(status_code=500, detail=result.get("reason", "send failed"))
    return {"ok": True, **result}


@admin_router.post("/api/admin/email-workflows/booking_followup/run")
async def run_followup_sweep(x_admin_key: str = Header("")):
    """Manually trigger the follow-up email sweep (same as the daily job)."""
    _check_auth(x_admin_key)
    import asyncio
    from app.booking.booking_email import run_followup_email_sweep
    result = await asyncio.to_thread(run_followup_email_sweep)
    return {"ok": True, **result}


@admin_router.post("/api/admin/email-workflows/customer_birthday/run")
async def run_birthday_sweep(x_admin_key: str = Header("")):
    """Manually trigger the birthday email sweep."""
    _check_auth(x_admin_key)
    import asyncio
    from app.booking.booking_email import run_birthday_email_sweep
    result = await asyncio.to_thread(run_birthday_email_sweep)
    return {"ok": True, **result}


# ── Legacy email-booking shim (backwards compat) ─────────────────────────────

@admin_router.get("/api/admin/email-booking")
async def get_email_booking_legacy(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    from app.booking.operator_settings import get_email_booking_config
    from app.config import get_settings
    s = get_settings()
    return {
        "config": get_email_booking_config(),
        "from_hint": (getattr(s, "resend_from_confirmations", "") or getattr(s, "email_from", "") or "").strip(),
        "bcc_configured": bool((getattr(s, "resend_bcc_booking", "") or "").strip()),
        "has_resend_key": bool((getattr(s, "resend_api_key", "") or "").strip()),
    }


# ── Incremental sync ──────────────────────────────────────────────────────────
# Syncs reservas_con_extras → all_appointments (full upsert)
# Then pulls NEW records from booknetic + hotboat into all_appointments

@admin_router.post("/api/admin/sync")
async def sync_tables(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    try:
        from psycopg.types.json import Jsonb as PgJson

        def normalize_phone(ph):
            if not ph: return None
            ph = re.sub(r"[^\d+]", "", str(ph))
            if ph.startswith("+"): return ph
            if len(ph) == 9 and ph.startswith("9"): return "+56" + ph
            return ph

        def parse_clp(s):
            if not s: return 0.0
            return float(re.sub(r"[^0-9]", "", str(s)) or 0)

        with get_connection() as conn:
            with conn.cursor() as cur:
                # Get cutoff date from reservas_con_extras (authoritative source)
                cur.execute("SELECT MAX(fecha) FROM reservas_con_extras")
                cutoff = cur.fetchone()[0]
                if not cutoff:
                    raise HTTPException(status_code=500, detail="No records found in reservas_con_extras")

                inserted_reservas = 0
                updated_reservas = 0
                inserted_book = 0
                inserted_hb = 0
                updated_status = 0

                # Sync reservas_con_extras → all_appointments (upsert by source_id)
                cur.execute("""
                    SELECT id, appointment_id, fecha, hora, nombre_cliente, email, telefono,
                           servicio, num_personas, num_adultos, num_ninos,
                           ingreso_reserva, ingreso_extras, ingreso_total,
                           costo_operativo_fijo, costo_operativo_variable, costo_operativo_total,
                           ciudad_origen, como_supieron, clima_del_dia, categoria_clientes,
                           tipo_clientes, tiene_cruce, status, extras_json, created_at
                    FROM reservas_con_extras
                    ORDER BY fecha
                """)
                for row in cur.fetchall():
                    (rid, appt_id, fecha, hora, nombre, email, telefono,
                     servicio, num_p, num_adultos, num_ninos,
                     ing_res, ing_ext, ing_total, costo_fijo, costo_var, costo_total,
                     ciudad, como_sup, clima, categoria, tipo_cli, tiene_cruce,
                     status, extras, created) = row
                    # Check existing: 1) sheets source_id, 2) appointment_id, 3) name+fecha+hora fallback
                    existing = None
                    cur.execute(f"SELECT id, source FROM {TABLE} WHERE source='sheets' AND source_id=%s", (str(rid),))
                    existing = cur.fetchone()
                    if not existing and appt_id:
                        cur.execute(f"SELECT id, source FROM {TABLE} WHERE appointment_id=%s LIMIT 1", (str(appt_id),))
                        existing = cur.fetchone()
                    if not existing and nombre and fecha and hora:
                        cur.execute(
                            f"SELECT id, source FROM {TABLE} WHERE nombre_cliente=%s AND fecha=%s AND hora=%s ORDER BY updated_at DESC NULLS LAST LIMIT 1",
                            (nombre, fecha, hora)
                        )
                        existing = cur.fetchone()
                        if existing and existing[1] in ('sheets', 'manual', None):
                            # Only stamp source_id on sheets/manual rows — never overwrite booknetic/hotboat_web source
                            cur.execute(f"UPDATE {TABLE} SET source='sheets', source_id=%s WHERE id=%s", (str(rid), existing[0]))

                    if existing:
                        # Update rich fields regardless of source
                        cur.execute(f"""
                            UPDATE {TABLE}
                            SET extras_json=COALESCE(%s, extras_json),
                                ingreso_extras=COALESCE(%s, ingreso_extras),
                                ingreso_total=COALESCE(%s, ingreso_total),
                                num_adultos=COALESCE(%s, num_adultos),
                                num_ninos=COALESCE(%s, num_ninos),
                                ciudad_origen=COALESCE(%s, ciudad_origen),
                                como_supieron=COALESCE(%s, como_supieron),
                                clima_del_dia=COALESCE(%s, clima_del_dia),
                                categoria_clientes=COALESCE(%s, categoria_clientes),
                                tipo_clientes=COALESCE(%s, tipo_clientes),
                                tiene_cruce=COALESCE(%s, tiene_cruce),
                                costo_operativo_variable=COALESCE(%s, costo_operativo_variable),
                                costo_operativo_total=COALESCE(%s, costo_operativo_total),
                                updated_at=NOW()
                            WHERE id=%s
                        """, (PgJson(extras) if extras else None,
                              float(ing_ext) if ing_ext else None,
                              float(ing_total) if ing_total else None,
                              num_adultos, num_ninos, ciudad, como_sup, clima, categoria,
                              tipo_cli, tiene_cruce,
                              float(costo_var) if costo_var else None,
                              float(costo_total) if costo_total else None,
                              existing[0]))
                        updated_reservas += 1
                    else:
                        cur.execute(f"""
                            INSERT INTO {TABLE}
                            (source, source_id, appointment_id, fecha, hora,
                             nombre_cliente, email, telefono, servicio, num_personas,
                             num_adultos, num_ninos,
                             ingreso_reserva, ingreso_extras, ingreso_total,
                             costo_operativo_fijo, costo_operativo_variable, costo_operativo_total,
                             ciudad_origen, como_supieron, clima_del_dia,
                             categoria_clientes, tipo_clientes, tiene_cruce,
                             status, extras_json, created_at, updated_at)
                            VALUES ('sheets',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                            ON CONFLICT DO NOTHING
                        """, (str(rid), str(appt_id) if appt_id else None,
                              fecha, hora, nombre, email, normalize_phone(telefono),
                              servicio or "HotBoat", str(num_p) if num_p else None,
                              num_adultos, num_ninos,
                              float(ing_res or 0), float(ing_ext or 0), float(ing_total or 0),
                              float(costo_fijo or 0), float(costo_var or 0), float(costo_total or 0),
                              ciudad, como_sup, clima, categoria, tipo_cli, tiene_cruce,
                              status, PgJson(extras or {}), created))
                        inserted_reservas += 1

                # Remove duplicates by appointment_id (old sheets rows)
                cur.execute("""
                    DELETE FROM all_appointments
                    WHERE source = 'sheets' AND appointment_id IS NOT NULL
                    AND id NOT IN (
                        SELECT MAX(id) FROM all_appointments
                        WHERE source = 'sheets' AND appointment_id IS NOT NULL
                        GROUP BY appointment_id
                    )
                """)
                dedup_deleted = cur.rowcount

                # Remove orphan sheets rows superseded by a confirmed booknetic/hotboat_web record
                # for the same (nombre_cliente + fecha + hora). Only removes source='sheets' rows
                # when a non-sheets record with a real status already exists.
                cur.execute(f"""
                    DELETE FROM {TABLE} a
                    WHERE a.source = 'sheets'
                      AND a.nombre_cliente IS NOT NULL
                      AND a.fecha IS NOT NULL
                      AND a.hora IS NOT NULL
                      AND EXISTS (
                          SELECT 1 FROM {TABLE} b
                          WHERE b.id <> a.id
                            AND b.nombre_cliente = a.nombre_cliente
                            AND b.fecha = a.fecha
                            AND b.hora = a.hora
                            AND b.source <> 'sheets'
                            AND b.status IS NOT NULL
                      )
                """)
                dedup_deleted += cur.rowcount

                # Sync booknetic — do not use MAX(reservas_con_extras.fecha) as lower bound (it is often
                # a future date and would skip all earlier appointments, e.g. April when June exists in DB)
                cur.execute("""
                    SELECT id, customer_name, customer_email, starts_at, status, raw, created_at
                    FROM booknetic_appointments
                    WHERE starts_at IS NOT NULL
                      AND starts_at::date >= (CURRENT_DATE - INTERVAL '3 years')
                      AND starts_at::date <= (CURRENT_DATE + INTERVAL '3 years')
                """)
                for row in cur.fetchall():
                    bid, nombre, email, starts_at, status, raw, created = row
                    raw = raw or {}
                    sid = str(bid)
                    # Already synced as booknetic, OR reservas_con_extras already created a sheets row with this appointment_id
                    cur.execute(
                        f"""SELECT id, source, status FROM {TABLE}
                            WHERE (source = 'booknetic' AND source_id = %s)
                               OR (appointment_id IS NOT NULL AND TRIM(appointment_id::text) = %s)
                            LIMIT 1""",
                        (sid, sid),
                    )
                    existing = cur.fetchone()
                    if existing:
                        ex_id, ex_src, ex_st = existing[0], existing[1], existing[2]
                        if ex_src == "booknetic":
                            if status and status != ex_st:
                                cur.execute(f"UPDATE {TABLE} SET status=%s, updated_at=NOW() WHERE id=%s",
                                            (status, ex_id))
                                updated_status += 1
                        # sheets (or other) row already represents this Booknetic ID — do not insert a 2nd row
                        continue
                    # Insert new
                    phone = normalize_phone(raw.get("customer_phone_number"))
                    service = raw.get("service") or ""
                    ingreso = parse_clp(raw.get("payment"))
                    hora = starts_at.time() if starts_at else None
                    fecha = starts_at.date() if starts_at else None
                    m = re.search(r"(\d+)\s*people", service, re.I)
                    num_p = m.group(1) if m else None
                    cur.execute(f"""
                        INSERT INTO {TABLE}
                        (source, source_id, appointment_id, fecha, hora, nombre_cliente, email, telefono,
                         servicio, num_personas, ingreso_reserva, ingreso_total,
                         costo_operativo_fijo, costo_operativo_total, status, extras_json, created_at, updated_at)
                        VALUES ('booknetic',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,18000,18000,%s,'{{}}', %s,NOW())
                    """, (str(bid), str(bid), fecha, hora, nombre, email, phone,
                          service, num_p, ingreso, ingreso, status, created))
                    inserted_book += 1

                # Sync hotboat_appointments (no reservas MAX fecha cutoff — see booknetic comment above)
                cur.execute("""
                    SELECT booking_ref, customer_name, customer_email, customer_phone,
                           booking_date, booking_time, num_people,
                           subtotal, extras_total, total_price, extras, status,
                           payment_id, payment_status, notes, created_at
                    FROM hotboat_appointments
                    WHERE booking_date IS NOT NULL
                      AND booking_date >= (CURRENT_DATE - INTERVAL '3 years')
                      AND booking_date <= (CURRENT_DATE + INTERVAL '3 years')
                      AND status != 'solicitud'
                """)
                for row in cur.fetchall():
                    (ref, nombre, email, phone, fecha, hora, num_p,
                     sub, ext, total, extras, status, pay_id, pay_st, notes, created) = row
                    cur.execute(f"SELECT id, status FROM {TABLE} WHERE source='hotboat_web' AND source_id=%s", (ref,))
                    existing = cur.fetchone()
                    if existing:
                        if status and status != existing[1]:
                            cur.execute(f"UPDATE {TABLE} SET status=%s, payment_status=%s, updated_at=NOW() WHERE id=%s",
                                        (status, pay_st, existing[0]))
                            updated_status += 1
                        continue
                    cur.execute(f"""
                        INSERT INTO {TABLE}
                        (source, source_id, appointment_id, fecha, hora, nombre_cliente, email, telefono,
                         servicio, num_personas, ingreso_reserva, ingreso_extras, ingreso_total,
                         costo_operativo_fijo, costo_operativo_total,
                         status, extras_json, observaciones, payment_id, payment_status, created_at, updated_at)
                        VALUES ('hotboat_web',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,18000,18000,%s,%s,%s,%s,%s,%s,NOW())
                    """, (ref, ref, fecha, hora, nombre, email, normalize_phone(phone),
                          f"HotBoat Web ({num_p}p)", str(num_p),
                          float(sub or 0), float(ext or 0), float(total or 0),
                          status, PgJson(extras or {}), notes, pay_id, pay_st, created))
                    inserted_hb += 1

                conn.commit()

        return {
            "ok": True,
            "reservas_con_extras_inserted": inserted_reservas,
            "reservas_con_extras_updated": updated_reservas,
            "duplicates_removed": dedup_deleted,
            "inserted_booknetic": inserted_book,
            "inserted_hotboat": inserted_hb,
            "status_updated": updated_status,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Extras catalog (extras_visibility is the single source of truth) ──────────

import unicodedata as _unicodedata

def _slugify_extra(s: str) -> str:
    s = _unicodedata.normalize("NFKD", str(s)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")

def _parse_clp(s) -> int:
    if not s:
        return 0
    return int(re.sub(r"[^0-9]", "", str(s)) or 0)


@admin_router.get("/api/admin/precios-extras")
async def get_precios_extras(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    try:
        # Ensure all required columns exist (safe to run every time)
        with get_connection() as conn:
            with conn.cursor() as cur:
                for col_def in [
                    "name TEXT",
                    "description TEXT",
                    "precio_venta INTEGER",
                    "costo INTEGER",
                    "icon TEXT",
                ]:
                    cur.execute(f"ALTER TABLE extras_visibility ADD COLUMN IF NOT EXISTS {col_def}")
                conn.commit()

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT extra_name_lower, name, show_in_booking,
                           COALESCE(sort_order, 999) AS sort_order,
                           COALESCE(description, '') AS description,
                           COALESCE(precio_venta, 0) AS price,
                           COALESCE(costo, 0)        AS cost,
                           COALESCE(icon, '')        AS icon
                    FROM extras_visibility
                    ORDER BY sort_order, extra_name_lower
                """)
                extras = []
                for (name_lower, name, show_in_booking, sort_order,
                     description, price, cost, icon) in cur.fetchall():
                    display_name = name or name_lower
                    extras.append({
                        "id": name_lower,
                        "key": _slugify_extra(display_name),
                        "name": display_name,
                        "price": price,
                        "cost": cost,
                        "icon": icon,
                        "description": description,
                        "show_in_booking": bool(show_in_booking),
                        "sort_order": int(sort_order),
                    })
        return {"extras": extras}
    except Exception as e:
        logger.error(f"Error fetching extras: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.put("/api/admin/precios-extras/{extra_id:path}")
async def update_precio_extra(extra_id: str, x_admin_key: str = Header(""), request: Request = None):
    _check_auth(x_admin_key)
    try:
        body = await request.json()
        name = body.get("name", "").strip()
        price = int(body.get("price") or 0)
        cost = int(body.get("cost") or 0)
        icon = body.get("icon", "").strip()
        description = body.get("description", "").strip()
        show_in_booking = bool(body.get("show_in_booking", True))
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        new_name_lower = name.lower()
        with get_connection() as conn:
            with conn.cursor() as cur:
                # If key changed (rename), update the PK
                if extra_id != new_name_lower:
                    cur.execute("""
                        UPDATE extras_visibility
                        SET extra_name_lower = %s, name = %s,
                            show_in_booking = %s, description = %s,
                            precio_venta = %s, costo = %s, icon = %s,
                            updated_at = NOW()
                        WHERE extra_name_lower = %s
                    """, (new_name_lower, name, show_in_booking,
                          description or None, price or None, cost or None, icon or None,
                          extra_id))
                    if cur.rowcount == 0:
                        # Row didn't exist under old key — upsert under new key
                        cur.execute("""
                            INSERT INTO extras_visibility
                                (extra_name_lower, name, show_in_booking, description, precio_venta, costo, icon, updated_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                            ON CONFLICT (extra_name_lower) DO UPDATE
                                SET name = EXCLUDED.name,
                                    show_in_booking = EXCLUDED.show_in_booking,
                                    description = EXCLUDED.description,
                                    precio_venta = EXCLUDED.precio_venta,
                                    costo = EXCLUDED.costo,
                                    icon = EXCLUDED.icon,
                                    updated_at = NOW()
                        """, (new_name_lower, name, show_in_booking,
                              description or None, price or None, cost or None, icon or None))
                else:
                    cur.execute("""
                        INSERT INTO extras_visibility
                            (extra_name_lower, name, show_in_booking, description, precio_venta, costo, icon, updated_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (extra_name_lower) DO UPDATE
                            SET name = EXCLUDED.name,
                                show_in_booking = EXCLUDED.show_in_booking,
                                description = EXCLUDED.description,
                                precio_venta = EXCLUDED.precio_venta,
                                costo = EXCLUDED.costo,
                                icon = EXCLUDED.icon,
                                updated_at = NOW()
                    """, (new_name_lower, name, show_in_booking,
                          description or None, price or None, cost or None, icon or None))
                conn.commit()
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating extra {extra_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.post("/api/admin/precios-extras")
async def create_precio_extra(x_admin_key: str = Header(""), request: Request = None):
    _check_auth(x_admin_key)
    try:
        body = await request.json()
        name = body.get("name", "").strip()
        price = int(body.get("price") or 0)
        cost = int(body.get("cost") or 0)
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        description = body.get("description", "").strip()
        show_in_booking = bool(body.get("show_in_booking", True))
        name_lower = name.lower()
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO extras_visibility
                        (extra_name_lower, name, show_in_booking, description, precio_venta, costo, icon,
                         sort_order, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, '', 999, NOW())
                    ON CONFLICT (extra_name_lower) DO UPDATE
                        SET name = EXCLUDED.name,
                            show_in_booking = EXCLUDED.show_in_booking,
                            description = EXCLUDED.description,
                            precio_venta = EXCLUDED.precio_venta,
                            costo = EXCLUDED.costo,
                            updated_at = NOW()
                """, (name_lower, name, show_in_booking,
                      description or None, price or None, cost or None))
                conn.commit()
        return {"ok": True, "id": name_lower, "key": _slugify_extra(name)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating extra: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.post("/api/admin/precios-extras/reorder")
async def reorder_extras(x_admin_key: str = Header(""), request: Request = None):
    """Save new sort order. Body: [{name_lower, sort_order}, ...]"""
    _check_auth(x_admin_key)
    try:
        items = await request.json()
        with get_connection() as conn:
            with conn.cursor() as cur:
                for item in items:
                    cur.execute("""
                        INSERT INTO extras_visibility (extra_name_lower, show_in_booking, sort_order, updated_at)
                        VALUES (%s, TRUE, %s, NOW())
                        ON CONFLICT (extra_name_lower) DO UPDATE
                            SET sort_order = EXCLUDED.sort_order, updated_at = NOW()
                    """, (item["name_lower"], item["sort_order"]))
                conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error reordering extras: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.delete("/api/admin/precios-extras/{extra_id:path}")
async def delete_precio_extra(extra_id: str, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Physical delete — extras_visibility is our own table, not Sheets-synced
                cur.execute("DELETE FROM extras_visibility WHERE extra_name_lower = %s", (extra_id,))
                conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error deleting extra {extra_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── WooCommerce: send payment link ────────────────────────────────────────────

@admin_router.post("/api/admin/reservas/{rid}/send-payment-link")
async def send_payment_link(rid: int, x_admin_key: str = Header("")):
    """Create a WooCommerce order and send the payment link via WhatsApp."""
    _check_auth(x_admin_key)
    try:
        from app.payment.woocommerce import create_order
        from app.whatsapp.client import whatsapp_client
        from psycopg.types.json import Jsonb as PgJson

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT nombre_cliente, telefono, email, ingreso_reserva, "
                    f"ingreso_extras, ingreso_total, fecha, num_personas, "
                    f"COALESCE(pagos, '[]'::jsonb) FROM {TABLE} WHERE id=%s",
                    (rid,)
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Reserva no encontrada")
                nombre, telefono, email, ing_res, ing_ext, ing_total, fecha, num_p, pagos_raw = row

        if not telefono:
            raise HTTPException(status_code=400, detail="La reserva no tiene teléfono")

        # Charge only the remaining balance (pago faltante), not the full total
        ya_pagado = sum(float(p.get("amount", 0)) for p in (pagos_raw or []))
        ing_total_f = float(ing_total or 0)
        pago_faltante = max(0, ing_total_f - ya_pagado)

        # If nothing is owed, error out
        if pago_faltante <= 0:
            raise HTTPException(status_code=400, detail="La reserva ya está pagada en su totalidad")

        order = await create_order(
            reservation_id=rid,
            nombre=nombre or "Cliente",
            telefono=telefono,
            email=email,
            monto_reserva=pago_faltante,
            monto_extras=0,
            fecha=str(fecha) if fecha else None,
            num_personas=num_p,
        )

        # Build WhatsApp message
        first_name = (nombre or "").strip().split()[0]
        fecha_str  = str(fecha) if fecha else "tu reserva"
        monto_str  = f"${int(pago_faltante):,}".replace(",", ".")
        msg = (
            f"Hola {first_name}! 🚤\n"
            f"Te recordamos tu reserva HotBoat para el {fecha_str}.\n\n"
            f"💳 Pago pendiente: *{monto_str} CLP*\n"
            f"{order['payment_url']}\n\n"
            f"Cualquier duda estamos disponibles. ¡Nos vemos! 🙌"
        )

        phone_clean = telefono.replace("+", "").replace(" ", "")
        await whatsapp_client.send_text_message(to=phone_clean, message=msg)

        # Save the order_id in the reservation for tracking
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"UPDATE {TABLE} SET payment_id=%s, payment_status='pending', updated_at=NOW() WHERE id=%s",
                    (str(order["order_id"]), rid)
                )
                conn.commit()

        logger.info(f"Payment link sent for reservation {rid} → WC order {order['order_id']}")
        return {
            "ok": True,
            "order_id":    order["order_id"],
            "payment_url": order["payment_url"],
            "message_sent_to": telefono,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending payment link for {rid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── WooCommerce: receive payment webhook ──────────────────────────────────────

@admin_router.post("/api/woo-webhook")
async def woo_webhook(request: Request):
    """
    Receives WooCommerce order.updated / order.completed webhooks.
    Marks the reservation as paid when the order status becomes 'processing' or 'completed'.
    """
    body = await request.body()

    sig = request.headers.get("x-wc-webhook-signature", "")
    from app.payment.woocommerce import verify_webhook_signature
    if not verify_webhook_signature(body, sig):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    logger.info(f"WC webhook body ({len(body)} bytes): {body[:200]!r}")

    # Accept empty / non-JSON bodies (WooCommerce ping on webhook save)
    if not body or not body.strip():
        return {"ok": True, "ignored": True, "reason": "ping"}

    try:
        import json
        from psycopg.types.json import Jsonb as PgJson
        try:
            data = json.loads(body)
        except json.JSONDecodeError as je:
            logger.warning(f"WC webhook non-JSON body (ignored): {je} | body: {body[:300]!r}")
            return {"ok": True, "ignored": True, "reason": "non_json"}

        status = data.get("status", "")
        wc_id  = data.get("id")
        total  = float(data.get("total", 0) or 0)

        if status not in ("processing", "completed"):
            return {"ok": True, "ignored": True, "status": status}

        # Extract HotBoat metadata from the order
        meta_map = {m["key"]: m["value"] for m in data.get("meta_data", [])}
        booking_ref_wc = meta_map.get("hotboat_booking_ref", "")

        # Parse WooCommerce date_paid; accept only plausible ISO dates (>=2024).
        # Otherwise fall back to the reservation's created_at (see below).
        raw_date_paid = (data.get("date_paid") or "")[:10] or ""
        paid_date_wc = raw_date_paid if raw_date_paid >= "2024-01-01" else ""

        def _add_pago(pagos: list, amount: float, method: str, fallback_date: str = "") -> list:
            """Add a payment entry if not already present for this WC order.
            If the WooCommerce date_paid is missing/invalid, use fallback_date
            (typically the reservation's created_at)."""
            already = any(p.get("wc_order_id") == wc_id for p in pagos)
            if not already:
                pagos.append({
                    "amount":      amount,
                    "method":      method,
                    "wc_order_id": wc_id,
                    "date":        paid_date_wc or fallback_date,
                    "status":      status,
                })
            return pagos

        # ── 1. Update all_appointments (admin-created reservations) ──────────
        res_id = None
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT id, nombre_cliente, COALESCE(pagos,'[]'::jsonb), created_at::date::text FROM {TABLE} WHERE payment_id=%s",
                    (str(wc_id),)
                )
                row = cur.fetchone()
                if row:
                    res_id, nombre, pagos_raw, created_at_str = row
                    pagos = _add_pago(list(pagos_raw) if pagos_raw else [], total, "transbank", created_at_str or "")
                    cur.execute(
                        f"UPDATE {TABLE} SET pagos=%s, payment_status=%s, updated_at=NOW() WHERE id=%s",
                        (PgJson(pagos), status, res_id)
                    )
                    conn.commit()

        # ── 2. Update hotboat_appointments (web booking flow) ────────────────
        if booking_ref_wc:
            try:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "SELECT id, customer_name, customer_phone, customer_email, "
                            "booking_date, booking_time, num_people, subtotal, extras_total, "
                            "total_price, has_flex, flex_amount, extras, notes "
                            "FROM hotboat_appointments WHERE booking_ref=%s",
                            (booking_ref_wc,)
                        )
                        ha_row = cur.fetchone()
                        if ha_row:
                            (ha_id, ha_name, ha_phone, ha_email,
                             ha_date, ha_time, ha_people, ha_sub,
                             ha_ext, ha_total, ha_flex, ha_flex_amt,
                             ha_extras_json, ha_notes) = ha_row

                            cur.execute(
                                "UPDATE hotboat_appointments "
                                "SET status='confirmed', payment_order_id=%s, payment_status=%s, "
                                "paid_at=NOW(), updated_at=NOW() WHERE booking_ref=%s",
                                (str(wc_id), status, booking_ref_wc)
                            )
                            conn.commit()

                            # Sync confirmed booking into all_appointments
                            from app.booking.router import _sync_hotboat_to_all
                            import json as _json
                            booking_data = {
                                "customer_name":  ha_name,
                                "customer_phone": ha_phone,
                                "customer_email": ha_email,
                                "booking_date":   str(ha_date),
                                "booking_time":   str(ha_time)[:5],
                                "num_people":     ha_people,
                                "subtotal":       float(ha_sub or 0),
                                "extras_total":   float(ha_ext or 0),
                                "total_price":    float(ha_total or 0),
                                "has_flex":       ha_flex,
                                "flex_amount":    float(ha_flex_amt or 0),
                                "extras":         _json.loads(ha_extras_json) if isinstance(ha_extras_json, str) else (ha_extras_json or []),
                                "notes":          ha_notes,
                            }
                            _sync_hotboat_to_all(booking_ref_wc, booking_data, "confirmed")

                            # Register payment in all_appointments.pagos
                            with get_connection() as conn2:
                                with conn2.cursor() as cur2:
                                    cur2.execute(
                                        f"SELECT id, COALESCE(pagos,'[]'::jsonb), created_at::date::text FROM {TABLE} "
                                        f"WHERE source='hotboat_web' AND source_id=%s",
                                        (booking_ref_wc,)
                                    )
                                    all_row = cur2.fetchone()
                                    if all_row:
                                        all_id, pagos_raw2, created_at_str2 = all_row
                                        pagos2 = _add_pago(
                                            list(pagos_raw2) if pagos_raw2 else [],
                                            total, "transbank",
                                            created_at_str2 or ""
                                        )
                                        cur2.execute(
                                            f"UPDATE {TABLE} SET pagos=%s, payment_status=%s, updated_at=NOW() WHERE id=%s",
                                            (PgJson(pagos2), status, all_id)
                                        )
                                        conn2.commit()

                            logger.info(f"WC webhook: hotboat_appointments {booking_ref_wc} confirmed + synced")
                            try:
                                from app.booking.booking_email import (
                                    try_send_booking_confirmation_after_payment,
                                )
                                em = try_send_booking_confirmation_after_payment(booking_ref_wc)
                                logger.info("WC webhook: confirmation email %s", em)
                            except Exception as em_err:
                                logger.warning("WC webhook: confirmation email error: %s", em_err)
            except Exception as he:
                logger.error(f"WC webhook: error updating hotboat_appointments {booking_ref_wc}: {he}")

        # ── 3. Update accommodation_bookings ─────────────────────────────────
        aloj_ref_wc = meta_map.get("accommodation_booking_ref", "") or (
            booking_ref_wc if booking_ref_wc.startswith("HA-") else ""
        )
        if aloj_ref_wc:
            try:
                with get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE accommodation_bookings"
                            " SET status='confirmed', payment_order_id=%s, payment_status=%s,"
                            "     paid_at=NOW(), updated_at=NOW()"
                            " WHERE booking_ref=%s RETURNING hotboat_ref",
                            (str(wc_id), status, aloj_ref_wc)
                        )
                        ab_row = cur.fetchone()
                        conn.commit()
                        if ab_row:
                            logger.info("WC webhook: accommodation_bookings %s confirmed", aloj_ref_wc)
                            combined_hb_ref = ab_row[0]
                            # If combined with HotBoat, confirm that booking too
                            if combined_hb_ref:
                                cur.execute(
                                    "UPDATE hotboat_appointments"
                                    " SET status='confirmed', payment_order_id=%s, payment_status=%s,"
                                    "     paid_at=NOW(), updated_at=NOW()"
                                    " WHERE booking_ref=%s",
                                    (str(wc_id), status, combined_hb_ref)
                                )
                                conn.commit()
                                logger.info("WC webhook: combined hotboat_appointments %s confirmed", combined_hb_ref)
            except Exception as ae:
                logger.error("WC webhook: error updating accommodation_bookings %s: %s", aloj_ref_wc, ae)

        logger.info(f"WC webhook: order {wc_id} processed → status={status}, amount={total}")
        return {"ok": True, "reservation_id": res_id, "booking_ref": booking_ref_wc, "status": status}

    except Exception as e:
        logger.error(f"WC webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# EXPERIENCES (Otras Experiencias)
# ═══════════════════════════════════════════════════════════════════════════════

MEDIA_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "media")


def _exp_row(r, cols):
    row = dict(zip(cols, r))
    return row


@admin_router.get("/api/admin/experiencias")
async def admin_list_experiencias(x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id,slug,name,icon,description,price_per_person,cost_per_person,"
                "image_path,is_active,display_order FROM experiences ORDER BY display_order,id"
            )
            cols = [d.name for d in cur.description]
            return {"experiences": [_exp_row(r, cols) for r in cur.fetchall()]}


class ExperienceBody(BaseModel):
    slug: str
    name: str
    icon: str = "🚣"
    description: str = ""
    price_per_person: int = 0
    cost_per_person: int = 0
    image_path: Optional[str] = None
    is_active: bool = True
    display_order: int = 0


@admin_router.post("/api/admin/experiencias")
async def admin_create_experiencia(body: ExperienceBody, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO experiences (slug,name,icon,description,price_per_person,cost_per_person,image_path,is_active,display_order)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (body.slug, body.name, body.icon, body.description,
                 body.price_per_person, body.cost_per_person,
                 body.image_path, body.is_active, body.display_order),
            )
            new_id = cur.fetchone()[0]
            conn.commit()
    return {"ok": True, "id": new_id}


@admin_router.put("/api/admin/experiencias/{exp_id}")
async def admin_update_experiencia(exp_id: int, body: ExperienceBody, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE experiences SET slug=%s,name=%s,icon=%s,description=%s,"
                "price_per_person=%s,cost_per_person=%s,image_path=%s,is_active=%s,"
                "display_order=%s,updated_at=NOW() WHERE id=%s",
                (body.slug, body.name, body.icon, body.description,
                 body.price_per_person, body.cost_per_person,
                 body.image_path, body.is_active, body.display_order, exp_id),
            )
            conn.commit()
    return {"ok": True}


@admin_router.delete("/api/admin/experiencias/{exp_id}")
async def admin_delete_experiencia(exp_id: int, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM experiences WHERE id=%s", (exp_id,))
            conn.commit()
    return {"ok": True}


@admin_router.post("/api/admin/experiencias/{exp_id}/image")
async def admin_upload_exp_image(exp_id: int, file: UploadFile = File(...), x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    ext = os.path.splitext(file.filename or "img.jpg")[1].lower() or ".jpg"
    dest_dir = os.path.join(MEDIA_ROOT, "images", "experiencias", f"exp_{exp_id}")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"main{ext}")
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    rel = f"/media/images/experiencias/exp_{exp_id}/main{ext}"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE experiences SET image_path=%s,updated_at=NOW() WHERE id=%s", (rel, exp_id))
            conn.commit()
    return {"ok": True, "image_path": rel}


# ═══════════════════════════════════════════════════════════════════════════════
# ALOJAMIENTOS
# ═══════════════════════════════════════════════════════════════════════════════

def _aloj_row(r, cols):
    row = dict(zip(cols, r))
    return row


@admin_router.get("/api/admin/alojamientos")
async def admin_list_alojamientos(x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id,slug,name,group_name,icon,description,price_from,cost_from,"
                "capacity,owner_whatsapp,image_path,is_active,display_order,"
                "COALESCE(extra_images,'[]'::jsonb) AS extra_images"
                " FROM alojamientos ORDER BY display_order,id"
            )
            cols = [d.name for d in cur.description]
            return {"alojamientos": [_aloj_row(r, cols) for r in cur.fetchall()]}


class AlojamientoBody(BaseModel):
    slug: str
    name: str
    group_name: str = ""
    icon: str = "🏠"
    description: str = ""
    price_from: int = 0
    cost_from: int = 0
    capacity: int = 2
    total_units: int = 1
    owner_whatsapp: str = ""
    image_path: Optional[str] = None
    extra_images: List[str] = []
    is_active: bool = True
    display_order: int = 0


@admin_router.post("/api/admin/alojamientos")
async def admin_create_alojamiento(body: AlojamientoBody, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO alojamientos"
                " (slug,name,group_name,icon,description,price_from,cost_from,capacity,total_units,owner_whatsapp,"
                "  image_path,extra_images,is_active,display_order)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s) RETURNING id",
                (body.slug, body.name, body.group_name, body.icon, body.description,
                 body.price_from, body.cost_from, body.capacity, body.total_units, body.owner_whatsapp,
                 body.image_path, json.dumps(body.extra_images),
                 body.is_active, body.display_order),
            )
            new_id = cur.fetchone()[0]
            conn.commit()
    return {"ok": True, "id": new_id}


@admin_router.put("/api/admin/alojamientos/{aloj_id}")
async def admin_update_alojamiento(aloj_id: int, body: AlojamientoBody, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE alojamientos SET slug=%s,name=%s,group_name=%s,icon=%s,description=%s,"
                "price_from=%s,cost_from=%s,capacity=%s,total_units=%s,owner_whatsapp=%s,image_path=%s,"
                "extra_images=%s::jsonb,is_active=%s,display_order=%s WHERE id=%s",
                (body.slug, body.name, body.group_name, body.icon, body.description,
                 body.price_from, body.cost_from, body.capacity, body.total_units, body.owner_whatsapp,
                 body.image_path, json.dumps(body.extra_images),
                 body.is_active, body.display_order, aloj_id),
            )
            conn.commit()
    return {"ok": True}


@admin_router.delete("/api/admin/alojamientos/{aloj_id}")
async def admin_delete_alojamiento(aloj_id: int, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM alojamientos WHERE id=%s", (aloj_id,))
            conn.commit()
    return {"ok": True}


@admin_router.post("/api/admin/alojamientos/{aloj_id}/image")
async def admin_upload_aloj_image(aloj_id: int, file: UploadFile = File(...), x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    import time as _time
    ext = os.path.splitext(file.filename or "img.jpg")[1].lower() or ".jpg"
    # Save inside app/static so it's served at /static/... and survives Railway restarts
    # (as long as the image is committed to git or re-uploaded)
    static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "images", "alojamientos", f"aloj_{aloj_id}")
    os.makedirs(static_dir, exist_ok=True)
    ts = int(_time.time())
    filename = f"img_{ts}{ext}"
    dest = os.path.join(static_dir, filename)
    with open(dest, "wb") as fh:
        shutil.copyfileobj(file.file, fh)
    rel = f"/static/images/alojamientos/aloj_{aloj_id}/{filename}"
    with get_connection() as conn:
        with conn.cursor() as cur:
            # If no main image set yet, make this the primary
            cur.execute("SELECT image_path, COALESCE(extra_images,'[]'::jsonb) FROM alojamientos WHERE id=%s", (aloj_id,))
            row = cur.fetchone()
            if row:
                existing_main = row[0]
                existing_extra = list(row[1]) if row[1] else []
                if not existing_main:
                    cur.execute("UPDATE alojamientos SET image_path=%s,updated_at=NOW() WHERE id=%s", (rel, aloj_id))
                else:
                    existing_extra.append(rel)
                    cur.execute("UPDATE alojamientos SET extra_images=%s::jsonb,updated_at=NOW() WHERE id=%s",
                                (json.dumps(existing_extra), aloj_id))
            conn.commit()
    return {"ok": True, "image_path": rel}


# ═══════════════════════════════════════════════════════════════════════════════
# PACKS COMPLETOS
# ═══════════════════════════════════════════════════════════════════════════════

@admin_router.get("/api/admin/packs")
async def admin_list_packs(x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id,slug,name,icon,description,personas,price_from,cost_from,"
                "image_path,includes,is_active,display_order FROM packs ORDER BY display_order,id"
            )
            cols = [d.name for d in cur.description]
            rows = []
            for r in cur.fetchall():
                row = dict(zip(cols, r))
                if isinstance(row.get("includes"), str):
                    row["includes"] = json.loads(row["includes"])
                rows.append(row)
            return {"packs": rows}


class PackBody(BaseModel):
    slug: str
    name: str
    icon: str = "🎁"
    description: str = ""
    personas: str = "2 personas"
    price_from: int = 0
    cost_from: int = 0
    image_path: Optional[str] = None
    includes: List[str] = []
    is_active: bool = True
    display_order: int = 0


@admin_router.post("/api/admin/packs")
async def admin_create_pack(body: PackBody, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO packs (slug,name,icon,description,personas,price_from,cost_from,image_path,includes,is_active,display_order)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s) RETURNING id",
                (body.slug, body.name, body.icon, body.description, body.personas,
                 body.price_from, body.cost_from, body.image_path,
                 json.dumps(body.includes, ensure_ascii=False),
                 body.is_active, body.display_order),
            )
            new_id = cur.fetchone()[0]
            conn.commit()
    return {"ok": True, "id": new_id}


@admin_router.put("/api/admin/packs/{pack_id}")
async def admin_update_pack(pack_id: int, body: PackBody, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE packs SET slug=%s,name=%s,icon=%s,description=%s,personas=%s,"
                "price_from=%s,cost_from=%s,image_path=%s,includes=%s::jsonb,"
                "is_active=%s,display_order=%s,updated_at=NOW() WHERE id=%s",
                (body.slug, body.name, body.icon, body.description, body.personas,
                 body.price_from, body.cost_from, body.image_path,
                 json.dumps(body.includes, ensure_ascii=False),
                 body.is_active, body.display_order, pack_id),
            )
            conn.commit()
    return {"ok": True}


@admin_router.delete("/api/admin/packs/{pack_id}")
async def admin_delete_pack(pack_id: int, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM packs WHERE id=%s", (pack_id,))
            conn.commit()
    return {"ok": True}


@admin_router.post("/api/admin/packs/{pack_id}/image")
async def admin_upload_pack_image(pack_id: int, file: UploadFile = File(...), x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    ext = os.path.splitext(file.filename or "img.jpg")[1].lower() or ".jpg"
    dest_dir = os.path.join(MEDIA_ROOT, "images", "packs", f"pack_{pack_id}")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"main{ext}")
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    rel = f"/media/images/packs/pack_{pack_id}/main{ext}"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE packs SET image_path=%s,updated_at=NOW() WHERE id=%s", (rel, pack_id))
            conn.commit()
    return {"ok": True, "image_path": rel}


# ═══════════════════════════════════════════════════════════════════════════════
# EXTRAS BOOKINGS (Calendario de Extras)
# ═══════════════════════════════════════════════════════════════════════════════

class ExtrasBookingBody(BaseModel):
    customer_name: str
    customer_phone: Optional[str] = None
    item_type: str          # 'experience' | 'pack' | 'alojamiento'
    item_slug: str
    item_name: str
    start_date: str         # YYYY-MM-DD
    end_date: Optional[str] = None
    num_people: int = 1
    total_price: int = 0
    deposit_paid: int = 0
    status: str = "pendiente"
    notes: Optional[str] = None
    booking_ref: Optional[str] = None


@admin_router.get("/api/admin/extras-bookings")
async def admin_list_extras_bookings(
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    x_admin_key: str = Header(...),
):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            q = (
                "SELECT id,booking_ref,customer_name,customer_phone,item_type,item_slug,item_name,"
                "start_date,end_date,num_people,total_price,deposit_paid,status,notes,created_at"
                " FROM extras_bookings"
            )
            params = []
            conds = []
            if desde:
                conds.append("start_date >= %s")
                params.append(desde)
            if hasta:
                conds.append("start_date <= %s")
                params.append(hasta)
            if conds:
                q += " WHERE " + " AND ".join(conds)
            q += " ORDER BY start_date,id"
            cur.execute(q, params)
            cols = [d.name for d in cur.description]
            rows = []
            for r in cur.fetchall():
                row = dict(zip(cols, r))
                for k in ("start_date", "end_date", "created_at"):
                    if row.get(k):
                        row[k] = str(row[k])
                rows.append(row)
            return {"bookings": rows}


@admin_router.post("/api/admin/extras-bookings")
async def admin_create_extras_booking(body: ExtrasBookingBody, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO extras_bookings"
                " (booking_ref,customer_name,customer_phone,item_type,item_slug,item_name,"
                "  start_date,end_date,num_people,total_price,deposit_paid,status,notes)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (body.booking_ref, body.customer_name, body.customer_phone,
                 body.item_type, body.item_slug, body.item_name,
                 body.start_date, body.end_date,
                 body.num_people, body.total_price, body.deposit_paid,
                 body.status, body.notes),
            )
            new_id = cur.fetchone()[0]
            conn.commit()
    return {"ok": True, "id": new_id}


@admin_router.put("/api/admin/extras-bookings/{eb_id}")
async def admin_update_extras_booking(eb_id: int, body: ExtrasBookingBody, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE extras_bookings SET customer_name=%s,customer_phone=%s,"
                "item_type=%s,item_slug=%s,item_name=%s,start_date=%s,end_date=%s,"
                "num_people=%s,total_price=%s,deposit_paid=%s,status=%s,notes=%s"
                " WHERE id=%s",
                (body.customer_name, body.customer_phone,
                 body.item_type, body.item_slug, body.item_name,
                 body.start_date, body.end_date,
                 body.num_people, body.total_price, body.deposit_paid,
                 body.status, body.notes, eb_id),
            )
            conn.commit()
    return {"ok": True}


@admin_router.delete("/api/admin/extras-bookings/{eb_id}")
async def admin_delete_extras_booking(eb_id: int, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM extras_bookings WHERE id=%s", (eb_id,))
            conn.commit()
    return {"ok": True}


# ═══════════════════════════════════════════════════════════════════════════════
# MENU VISIBILITY (WhatsApp + booking page)
# ═══════════════════════════════════════════════════════════════════════════════

@admin_router.get("/api/admin/menu-settings")
async def admin_get_menu_settings(x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    from app.booking.operator_settings import get_menu_settings
    return get_menu_settings()


class MenuSettingsBody(BaseModel):
    show_experiencias: bool = True
    show_alojamientos: bool = True
    show_packs: bool = True
    show_arma_pack: bool = True


@admin_router.put("/api/admin/menu-settings")
async def admin_put_menu_settings(body: MenuSettingsBody, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    from app.booking.operator_settings import set_menu_settings
    set_menu_settings(body.dict())
    return {"ok": True}


# ── HotBoat prices per person ──────────────────────────────────────────────────

PRICES_DEFAULT = {2: 69990, 3: 54990, 4: 44990, 5: 38990, 6: 32990, 7: 29990}


@admin_router.get("/api/admin/prices-config")
async def get_prices_config(x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    raw = get_setting("prices_per_person", "")
    if raw:
        try:
            stored = json.loads(raw)
            # Merge with defaults so all people counts are present
            prices = {**PRICES_DEFAULT, **{int(k): int(v) for k, v in stored.items()}}
        except Exception:
            prices = PRICES_DEFAULT.copy()
    else:
        prices = PRICES_DEFAULT.copy()
    return {"prices": prices}


@admin_router.put("/api/admin/prices-config")
async def put_prices_config(request: Request, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    body = await request.json()
    prices = body.get("prices", {})
    if not isinstance(prices, dict):
        raise HTTPException(status_code=400, detail="prices debe ser un objeto")
    # Validate: keys 2-7, values positive numbers
    validated = {}
    for k, v in prices.items():
        try:
            ki = int(k)
            vi = int(v)
            if 1 <= ki <= 20 and vi >= 0:
                validated[ki] = vi
        except (ValueError, TypeError):
            pass
    if not validated:
        raise HTTPException(status_code=400, detail="Sin precios válidos")
    set_setting("prices_per_person", json.dumps(validated))
    # Refresh live PRICES constant used by the booking engine
    try:
        from app.booking import db as booking_db
        booking_db.PRICES.clear()
        booking_db.PRICES.update(validated)
    except Exception as e:
        logger.warning(f"Could not refresh live PRICES: {e}")
    return {"ok": True, "prices": validated}


# ═══════════════════════════════════════════════════════════════════════════════
# 🎟️  COUPONS
# ═══════════════════════════════════════════════════════════════════════════════

def _ensure_coupons_table():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS coupons (
                    id                SERIAL PRIMARY KEY,
                    code              TEXT NOT NULL UNIQUE,
                    name              TEXT DEFAULT '',
                    discount_percent  NUMERIC DEFAULT 0,
                    discount_fixed    NUMERIC DEFAULT 0,
                    extra_description TEXT DEFAULT '',
                    max_uses          INT DEFAULT 0,
                    uses_count        INT DEFAULT 0,
                    expires_at        DATE DEFAULT NULL,
                    is_active         BOOLEAN DEFAULT TRUE,
                    created_at        TIMESTAMPTZ DEFAULT NOW(),
                    updated_at        TIMESTAMPTZ DEFAULT NOW()
                );
                ALTER TABLE coupons ADD COLUMN IF NOT EXISTS rules JSONB DEFAULT NULL;
                ALTER TABLE hotboat_appointments
                    ADD COLUMN IF NOT EXISTS coupon_code TEXT DEFAULT NULL;
                ALTER TABLE hotboat_appointments
                    ADD COLUMN IF NOT EXISTS coupon_discount NUMERIC DEFAULT 0;
                ALTER TABLE all_appointments
                    ADD COLUMN IF NOT EXISTS coupon_code TEXT DEFAULT NULL;
                ALTER TABLE all_appointments
                    ADD COLUMN IF NOT EXISTS coupon_discount NUMERIC DEFAULT 0;
            """)
            conn.commit()


class CouponBody(BaseModel):
    code: str
    name: str = ""
    discount_percent: float = 0
    discount_fixed: float = 0
    extra_description: str = ""
    max_uses: int = 0
    expires_at: Optional[str] = None   # ISO date string or None
    is_active: bool = True
    rules: list = []  # per-people-count overrides: [{num_people, discount_percent, discount_fixed}]


@admin_router.get("/api/admin/coupons")
def list_coupons(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    _ensure_coupons_table()
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, code, name, discount_percent, discount_fixed,
                       extra_description, max_uses, uses_count, expires_at,
                       is_active, created_at, rules
                FROM coupons ORDER BY created_at DESC
            """)
            cols = [d.name for d in cur.description]
            rows = [dict(zip(cols, r)) for r in cur.fetchall()]
            for r in rows:
                for k in ("expires_at", "created_at"):
                    if r.get(k):
                        r[k] = str(r[k])
                if r.get("rules") is None:
                    r["rules"] = []
            return {"coupons": rows}


@admin_router.post("/api/admin/coupons")
def create_coupon(body: CouponBody, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    _ensure_coupons_table()
    import json as _json
    expires = body.expires_at or None
    rules_json = _json.dumps(body.rules) if body.rules else None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO coupons
                   (code, name, discount_percent, discount_fixed,
                    extra_description, max_uses, expires_at, is_active, rules)
                   VALUES (UPPER(%s),%s,%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING id""",
                (body.code.strip(), body.name, body.discount_percent, body.discount_fixed,
                 body.extra_description, body.max_uses, expires, body.is_active, rules_json)
            )
            new_id = cur.fetchone()[0]
            conn.commit()
    return {"ok": True, "id": new_id}


@admin_router.put("/api/admin/coupons/{cid}")
def update_coupon(cid: int, body: CouponBody, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    import json as _json
    expires = body.expires_at or None
    rules_json = _json.dumps(body.rules) if body.rules else None
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE coupons
                   SET code=UPPER(%s), name=%s, discount_percent=%s, discount_fixed=%s,
                       extra_description=%s, max_uses=%s, expires_at=%s,
                       is_active=%s, rules=%s::jsonb, updated_at=NOW()
                   WHERE id=%s""",
                (body.code.strip(), body.name, body.discount_percent, body.discount_fixed,
                 body.extra_description, body.max_uses, expires, body.is_active, rules_json, cid)
            )
            conn.commit()
    return {"ok": True}


@admin_router.delete("/api/admin/coupons/{cid}")
def delete_coupon(cid: int, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM coupons WHERE id=%s", (cid,))
            conn.commit()
    return {"ok": True}


# ── Fix empty/invalid pago dates: replace with reservation's created_at ───────

@admin_router.post("/api/admin/fix-pago-dates")
def fix_pago_dates(x_admin_key: str = Header("")):
    """
    Scan all reservations whose pagos array has entries with empty, missing,
    or implausible date (< 2024-01-01). Replace those dates with the
    reservation's created_at::date. Returns how many rows were fixed.
    """
    _check_auth(x_admin_key)
    from psycopg.types.json import Jsonb as PgJson
    fixed = 0
    examples = []
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT id, nombre_cliente, created_at::date::text, pagos "
                f"FROM {TABLE} "
                f"WHERE pagos IS NOT NULL AND jsonb_array_length(pagos) > 0"
            )
            for rid, nombre, created_at_str, pagos_raw in cur.fetchall():
                pagos = list(pagos_raw) if pagos_raw else []
                changed = False
                for p in pagos:
                    d = (p.get("date") or "")
                    # Bad date: empty, pre-2024, or "YYYY-01-01" when reservation wasn't in January
                    bad = (
                        not d
                        or d < "2024-01-01"
                        or (d[5:] == "01-01" and created_at_str and created_at_str[5:7] != "01")
                    )
                    if bad:
                        p["date"] = created_at_str or ""
                        changed = True
                if changed:
                    cur.execute(
                        f"UPDATE {TABLE} SET pagos=%s, updated_at=NOW() WHERE id=%s",
                        (PgJson(pagos), rid)
                    )
                    fixed += 1
                    if len(examples) < 10:
                        examples.append({"id": rid, "nombre": nombre, "created_at": created_at_str})
            conn.commit()
    return {"fixed": fixed, "examples": examples}


# ── Accommodation: blocked dates management ───────────────────────────────────

class BlockedDateBody(BaseModel):
    start_date: str   # YYYY-MM-DD
    end_date:   str   # YYYY-MM-DD
    reason:     str   = "Temporada alta"


@admin_router.get("/api/admin/accommodation-blocked-dates/{aloj_id}")
def admin_list_blocked_dates(aloj_id: int, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, start_date::text, end_date::text, reason, created_at::text"
                " FROM accommodation_blocked_dates WHERE accommodation_id=%s ORDER BY start_date",
                (aloj_id,)
            )
            cols = [d.name for d in cur.description]
            return {"blocked": [dict(zip(cols, r)) for r in cur.fetchall()]}


@admin_router.post("/api/admin/accommodation-blocked-dates/{aloj_id}")
def admin_add_blocked_date(aloj_id: int, body: BlockedDateBody, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO accommodation_blocked_dates (accommodation_id, start_date, end_date, reason)"
                " VALUES (%s,%s,%s,%s) RETURNING id",
                (aloj_id, body.start_date, body.end_date, body.reason)
            )
            new_id = cur.fetchone()[0]
            conn.commit()
    return {"ok": True, "id": new_id}


@admin_router.delete("/api/admin/accommodation-blocked-dates/entry/{block_id}")
def admin_delete_blocked_date(block_id: int, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM accommodation_blocked_dates WHERE id=%s", (block_id,))
            conn.commit()
    return {"ok": True}


# ── Accommodation: booking list & management ──────────────────────────────────

@admin_router.get("/api/admin/accommodation-bookings")
def admin_list_accommodation_bookings(
    limit: int = Query(100, ge=1, le=500),
    x_admin_key: str = Header(...)
):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, booking_ref, accommodation_id, accommodation_name,"
                "       customer_name, customer_phone, customer_email,"
                "       check_in::text, check_out::text, num_people,"
                "       price_per_night, total_price, deposit_amount,"
                "       status, payment_status, hotboat_ref,"
                "       created_at::text"
                " FROM accommodation_bookings ORDER BY created_at DESC LIMIT %s",
                (limit,)
            )
            cols = [d.name for d in cur.description]
            return {"bookings": [dict(zip(cols, r)) for r in cur.fetchall()]}


@admin_router.put("/api/admin/accommodation-bookings/{bid}")
def admin_update_accommodation_booking(bid: int, body: dict, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    allowed = {"status", "notes"}
    updates = {k: v for k, v in body.items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    set_clause = ", ".join(f"{k}=%s" for k in updates)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE accommodation_bookings SET {set_clause}, updated_at=NOW() WHERE id=%s",
                (*updates.values(), bid)
            )
            conn.commit()
    return {"ok": True}
