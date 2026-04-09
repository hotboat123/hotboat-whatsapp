"""Admin dashboard router — uses all_appointments as single source of truth."""
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

from app.booking.operator_settings import (
    get_vacation_days, add_vacation_day, remove_vacation_day,
    get_setting, set_setting, is_urgency_mode,
    get_operating_hours, set_operating_hours,
)


# ── Auth ──────────────────────────────────────────────────────────────────────

def _check_auth(key: str):
    expected = os.getenv("ADMIN_PASSWORD", "hotboat2024")
    if key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


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
                              "costo_operativo_fijo", "costo_operativo_variable", "costo_operativo_total"):
                        if r.get(k) is not None: r[k] = float(r[k])
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


@admin_router.put("/api/admin/reservas/{rid}")
async def update_reserva(rid: int, body: UpdateReservaRequest, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
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
                    updates["pagos"] = PgJson(updates["pagos"])
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
                            f"SELECT email, nombre_cliente, telefono, fecha, hora, "
                            f"num_personas, ingreso_total, ingreso_reserva, ingreso_extras, "
                            f"source_id, source FROM {TABLE} WHERE id=%s",
                            (rid,)
                        )
                        rr = cur3.fetchone()
                if rr:
                    email_to = (rr[0] or "").strip()
                    row_data = {
                        "nombre_cliente": rr[1], "telefono": rr[2],
                        "fecha": str(rr[3]) if rr[3] else "",
                        "hora": str(rr[4])[:5] if rr[4] else "",
                        "num_personas": rr[5],
                        "ingreso_total": rr[6], "ingreso_reserva": rr[7], "ingreso_extras": rr[8],
                        "source_id": rr[9], "source": rr[10],
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


# ── Settings ──────────────────────────────────────────────────────────────────

@admin_router.get("/api/admin/settings")
async def get_all_settings(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    from app.booking.operator_settings import get_urgency_config, get_dp_config
    return {
        "urgency_mode": is_urgency_mode(),
        "urgency_config": get_urgency_config(),
        "dynamic_pricing": get_dp_config(),
    }


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
                    # Check existing: first by sheets source_id, then by appointment_id (any source)
                    existing = None
                    cur.execute(f"SELECT id, source FROM {TABLE} WHERE source='sheets' AND source_id=%s", (str(rid),))
                    existing = cur.fetchone()
                    if not existing and appt_id:
                        cur.execute(f"SELECT id, source FROM {TABLE} WHERE appointment_id=%s LIMIT 1", (str(appt_id),))
                        existing = cur.fetchone()

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

                # Remove duplicates (old Reservas_Con_Extras_Sheets rows replaced by reservas_con_extras)
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


# ── Precios Extras catalog ─────────────────────────────────────────────────────

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
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Join with extras_visibility for persistent show_in_booking flag
                # (survives Google Sheets re-sync of "Precios Extras")
                cur.execute("""
                    SELECT DISTINCT ON (LOWER(pe.raw->>'Extra'))
                           pe.id,
                           pe.raw->>'Extra' AS name,
                           pe.raw->>'Precio' AS precio,
                           pe.raw->>'costo' AS costo,
                           COALESCE(pe.raw->>'icon', '') AS icon,
                           COALESCE(pe.raw->>'description', '') AS description,
                           COALESCE(ev.show_in_booking, TRUE) AS show_in_booking,
                           COALESCE(ev.sort_order, 999) AS sort_order
                    FROM "Precios Extras" pe
                    LEFT JOIN extras_visibility ev
                           ON ev.extra_name_lower = LOWER(pe.raw->>'Extra')
                    WHERE pe.raw->>'Extra' IS NOT NULL
                    ORDER BY LOWER(pe.raw->>'Extra'), pe.updated_at DESC
                """)
                extras = []
                seen_keys: set = set()
                for row_id, name, precio, costo, icon, description, show_in_booking, sort_order in cur.fetchall():
                    key = _slugify_extra(name)
                    if key in seen_keys:
                        continue
                    seen_keys.add(key)
                    extras.append({
                        "id": row_id,
                        "key": key,
                        "name": name,
                        "price": _parse_clp(precio),
                        "cost": _parse_clp(costo) if costo else 0,
                        "icon": icon or "",
                        "description": description or "",
                        "show_in_booking": bool(show_in_booking),
                        "sort_order": int(sort_order),
                    })
        extras.sort(key=lambda x: (x["sort_order"], x["name"]))
        return {"extras": extras}
    except Exception as e:
        logger.error(f"Error fetching precios extras: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.put("/api/admin/precios-extras/{extra_id}")
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
        margen = f"{round(price / cost * 100)}%" if cost else ""
        utilidad = price - cost
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Fetch old name before overwriting (to detect renames)
                cur.execute('SELECT raw->>\'Extra\' FROM "Precios Extras" WHERE id = %s', (extra_id,))
                old_row = cur.fetchone()
                old_name = old_row[0] if old_row else None

                cur.execute("""
                    UPDATE "Precios Extras"
                    SET raw = raw
                        || jsonb_build_object('Extra', %s::text)
                        || jsonb_build_object('Precio', %s::text)
                        || jsonb_build_object('costo', %s::text)
                        || jsonb_build_object('margen', %s::text)
                        || jsonb_build_object('Utilidad', %s::text)
                        || jsonb_build_object('icon', %s::text)
                        || jsonb_build_object('description', %s::text),
                        updated_at = NOW()
                    WHERE id = %s
                """, (name, str(price), str(cost), margen, str(utilidad), icon, description, extra_id))

                # If the name changed, hide the old name so Sheets doesn't resurrect it
                if old_name and old_name.lower() != name.lower():
                    cur.execute("""
                        INSERT INTO extras_visibility (extra_name_lower, show_in_booking, updated_at)
                        VALUES (LOWER(%s), FALSE, NOW())
                        ON CONFLICT (extra_name_lower) DO UPDATE
                            SET show_in_booking = FALSE, updated_at = NOW()
                    """, (old_name,))

                # Persist visibility for the new name
                cur.execute("""
                    INSERT INTO extras_visibility (extra_name_lower, show_in_booking, updated_at)
                    VALUES (LOWER(%s), %s, NOW())
                    ON CONFLICT (extra_name_lower) DO UPDATE
                        SET show_in_booking = EXCLUDED.show_in_booking,
                            updated_at = NOW()
                """, (name, show_in_booking))
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
        import hashlib, time
        body = await request.json()
        name = body.get("name", "").strip()
        price = int(body.get("price") or 0)
        cost = int(body.get("cost") or 0)
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        description = body.get("description", "").strip()
        show_in_booking = body.get("show_in_booking", True)
        margen = f"{round(price / cost * 100)}%" if cost else ""
        utilidad = price - cost
        new_id = hashlib.sha1(f"{name}{time.time()}".encode()).hexdigest()
        raw = {"id": new_id, "Extra": name, "Precio": str(price),
               "costo": str(cost), "margen": margen, "Utilidad": str(utilidad),
               "description": description,
               "show_in_booking": "false" if not show_in_booking else "true"}
        with get_connection() as conn:
            with conn.cursor() as cur:
                from psycopg.types.json import Jsonb as PgJson
                cur.execute(
                    'INSERT INTO "Precios Extras" (id, raw, source, created_at, updated_at) VALUES (%s, %s, %s, NOW(), NOW())',
                    (new_id, PgJson(raw), "admin")
                )
                conn.commit()
        return {"ok": True, "id": new_id, "key": _slugify_extra(name)}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating extra: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.post("/api/admin/precios-extras/reorder")
async def reorder_extras(x_admin_key: str = Header(""), request: Request = None):
    """Save new sort order for all extras. Body: [{name_lower, sort_order}, ...]"""
    _check_auth(x_admin_key)
    try:
        items = await request.json()  # list of {name_lower, sort_order}
        with get_connection() as conn:
            with conn.cursor() as cur:
                for item in items:
                    cur.execute("""
                        INSERT INTO extras_visibility (extra_name_lower, show_in_booking, sort_order, updated_at)
                        VALUES (%s, TRUE, %s, NOW())
                        ON CONFLICT (extra_name_lower) DO UPDATE
                            SET sort_order = EXCLUDED.sort_order,
                                updated_at = NOW()
                    """, (item["name_lower"], item["sort_order"]))
                conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error reordering extras: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@admin_router.delete("/api/admin/precios-extras/{extra_id}")
async def delete_precio_extra(extra_id: str, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # "Precios Extras" is synced from Google Sheets so physical deletes come back.
                # We hide the entry persistently via extras_visibility instead.
                cur.execute('SELECT raw->>\'Extra\' FROM "Precios Extras" WHERE id = %s', (extra_id,))
                row = cur.fetchone()
                if row and row[0]:
                    extra_name = row[0]
                    cur.execute("""
                        INSERT INTO extras_visibility (extra_name_lower, show_in_booking, updated_at)
                        VALUES (LOWER(%s), FALSE, NOW())
                        ON CONFLICT (extra_name_lower) DO UPDATE
                            SET show_in_booking = FALSE,
                                updated_at = NOW()
                    """, (extra_name,))
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

        paid_date = data.get("date_paid", "")[:10] if data.get("date_paid") else ""

        def _add_pago(pagos: list, amount: float, method: str) -> list:
            """Add a payment entry if not already present for this WC order."""
            already = any(p.get("wc_order_id") == wc_id for p in pagos)
            if not already:
                pagos.append({
                    "amount":      amount,
                    "method":      method,
                    "wc_order_id": wc_id,
                    "date":        paid_date,
                    "status":      status,
                })
            return pagos

        # ── 1. Update all_appointments (admin-created reservations) ──────────
        res_id = None
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT id, nombre_cliente, COALESCE(pagos,'[]'::jsonb) FROM {TABLE} WHERE payment_id=%s",
                    (str(wc_id),)
                )
                row = cur.fetchone()
                if row:
                    res_id, nombre, pagos_raw = row
                    pagos = _add_pago(list(pagos_raw) if pagos_raw else [], total, "Transbank")
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
                                        f"SELECT id, COALESCE(pagos,'[]'::jsonb) FROM {TABLE} "
                                        f"WHERE source='hotboat_web' AND source_id=%s",
                                        (booking_ref_wc,)
                                    )
                                    all_row = cur2.fetchone()
                                    if all_row:
                                        all_id, pagos_raw2 = all_row
                                        pagos2 = _add_pago(
                                            list(pagos_raw2) if pagos_raw2 else [],
                                            total, "Transbank"
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
                "capacity,owner_whatsapp,image_path,is_active,display_order FROM alojamientos ORDER BY display_order,id"
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
    owner_whatsapp: str = ""
    image_path: Optional[str] = None
    is_active: bool = True
    display_order: int = 0


@admin_router.post("/api/admin/alojamientos")
async def admin_create_alojamiento(body: AlojamientoBody, x_admin_key: str = Header(...)):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO alojamientos"
                " (slug,name,group_name,icon,description,price_from,cost_from,capacity,owner_whatsapp,image_path,is_active,display_order)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (body.slug, body.name, body.group_name, body.icon, body.description,
                 body.price_from, body.cost_from, body.capacity, body.owner_whatsapp,
                 body.image_path, body.is_active, body.display_order),
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
                "price_from=%s,cost_from=%s,capacity=%s,owner_whatsapp=%s,image_path=%s,is_active=%s,"
                "display_order=%s WHERE id=%s",
                (body.slug, body.name, body.group_name, body.icon, body.description,
                 body.price_from, body.cost_from, body.capacity, body.owner_whatsapp,
                 body.image_path, body.is_active, body.display_order, aloj_id),
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
    ext = os.path.splitext(file.filename or "img.jpg")[1].lower() or ".jpg"
    dest_dir = os.path.join(MEDIA_ROOT, "images", "alojamientos", f"aloj_{aloj_id}")
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"main{ext}")
    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)
    rel = f"/media/images/alojamientos/aloj_{aloj_id}/main{ext}"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE alojamientos SET image_path=%s,updated_at=NOW() WHERE id=%s", (rel, aloj_id))
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
