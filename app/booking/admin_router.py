"""Admin dashboard router — uses all_appointments as single source of truth."""
import logging
import os
import re
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Header, Request
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
                           categoria_clientes, tipo_clientes,
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
                cur.execute(f"SELECT nombre_cliente, fecha FROM {TABLE} WHERE id=%s", (rid,))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Not found")
                cur.execute(f"DELETE FROM {TABLE} WHERE id=%s", (rid,))
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
                            VALUES ('sheets',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
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

                # Sync new booknetic records
                cur.execute("""
                    SELECT id, customer_name, customer_email, starts_at, status, raw, created_at
                    FROM booknetic_appointments WHERE starts_at::date > %s
                """, (cutoff,))
                for row in cur.fetchall():
                    bid, nombre, email, starts_at, status, raw, created = row
                    raw = raw or {}
                    # Check if already in all_appointments
                    cur.execute(f"SELECT id, status FROM {TABLE} WHERE source='booknetic' AND source_id=%s", (str(bid),))
                    existing = cur.fetchone()
                    if existing:
                        # Update status if changed
                        if status and status != existing[1]:
                            cur.execute(f"UPDATE {TABLE} SET status=%s, updated_at=NOW() WHERE id=%s",
                                        (status, existing[0]))
                            updated_status += 1
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

                # Sync new hotboat_appointments
                cur.execute("""
                    SELECT booking_ref, customer_name, customer_email, customer_phone,
                           booking_date, booking_time, num_people,
                           subtotal, extras_total, total_price, extras, status,
                           payment_id, payment_status, notes, created_at
                    FROM hotboat_appointments
                    WHERE booking_date > %s AND status != 'solicitud'
                """, (cutoff,))
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
                # Deduplicate by name keeping the most recently updated row; include id
                cur.execute("""
                    SELECT DISTINCT ON (raw->>'Extra')
                           id,
                           raw->>'Extra' AS name,
                           raw->>'Precio' AS precio,
                           raw->>'costo' AS costo,
                           COALESCE(raw->>'icon', '') AS icon
                    FROM "Precios Extras"
                    WHERE raw->>'Extra' IS NOT NULL
                    ORDER BY raw->>'Extra', updated_at DESC
                """)
                extras = []
                seen_keys: set = set()
                for row_id, name, precio, costo, icon in cur.fetchall():
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
                    })
        extras.sort(key=lambda x: x["name"])
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
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        margen = f"{round(price / cost * 100)}%" if cost else ""
        utilidad = price - cost
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE "Precios Extras"
                    SET raw = raw
                        || jsonb_build_object('Extra', %s::text)
                        || jsonb_build_object('Precio', %s::text)
                        || jsonb_build_object('costo', %s::text)
                        || jsonb_build_object('margen', %s::text)
                        || jsonb_build_object('Utilidad', %s::text)
                        || jsonb_build_object('icon', %s::text),
                        updated_at = NOW()
                    WHERE id = %s
                """, (name, str(price), str(cost), margen, str(utilidad), icon, extra_id))
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
        margen = f"{round(price / cost * 100)}%" if cost else ""
        utilidad = price - cost
        new_id = hashlib.sha1(f"{name}{time.time()}".encode()).hexdigest()
        raw = {"id": new_id, "Extra": name, "Precio": str(price),
               "costo": str(cost), "margen": margen, "Utilidad": str(utilidad)}
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


@admin_router.delete("/api/admin/precios-extras/{extra_id}")
async def delete_precio_extra(extra_id: str, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM "Precios Extras" WHERE id = %s', (extra_id,))
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
        from app.whatsapp.client import send_whatsapp_message
        from psycopg.types.json import Jsonb as PgJson

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT nombre_cliente, telefono, email, ingreso_reserva, "
                    f"ingreso_extras, ingreso_total, fecha, num_personas FROM {TABLE} WHERE id=%s",
                    (rid,)
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Reserva no encontrada")
                nombre, telefono, email, ing_res, ing_ext, ing_total, fecha, num_p = row

        if not telefono:
            raise HTTPException(status_code=400, detail="La reserva no tiene teléfono")

        order = await create_order(
            reservation_id=rid,
            nombre=nombre or "Cliente",
            telefono=telefono,
            email=email,
            monto_reserva=float(ing_res or 0),
            monto_extras=float(ing_ext or 0),
            fecha=str(fecha) if fecha else None,
            num_personas=num_p,
        )

        # Build WhatsApp message
        first_name = (nombre or "").strip().split()[0]
        fecha_str  = str(fecha) if fecha else "tu reserva"
        msg = (
            f"Hola {first_name}! 🚤\n"
            f"Tu reserva HotBoat para el {fecha_str} está lista.\n\n"
            f"💳 Para confirmarla, realiza el pago aquí:\n"
            f"{order['payment_url']}\n\n"
            f"Cualquier duda estamos disponibles. ¡Nos vemos! 🙌"
        )

        phone_clean = telefono.replace("+", "").replace(" ", "")
        await send_whatsapp_message(phone_clean, msg)

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

    # WooCommerce sends an empty-body ping when the webhook is first saved — return 200 OK
    if not body or not body.strip():
        return {"ok": True, "ignored": True, "reason": "ping"}

    try:
        import json
        from psycopg.types.json import Jsonb as PgJson
        data   = json.loads(body)
        status = data.get("status", "")
        wc_id  = data.get("id")
        total  = float(data.get("total", 0) or 0)

        if status not in ("processing", "completed"):
            return {"ok": True, "ignored": True, "status": status}

        # Find reservation by payment_id
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT id, nombre_cliente, COALESCE(pagos,'[]'::jsonb) FROM {TABLE} WHERE payment_id=%s",
                    (str(wc_id),)
                )
                row = cur.fetchone()
                if not row:
                    logger.warning(f"WC webhook: no reservation found for order {wc_id}")
                    return {"ok": True, "ignored": True, "reason": "reservation not found"}

                res_id, nombre, pagos_raw = row
                pagos = list(pagos_raw) if pagos_raw else []

                # Add payment record if not already present
                already = any(p.get("wc_order_id") == wc_id for p in pagos)
                if not already:
                    pagos.append({
                        "amount":      total,
                        "method":      "WooCommerce",
                        "wc_order_id": wc_id,
                        "date":        data.get("date_paid", "")[:10] if data.get("date_paid") else "",
                        "status":      status,
                    })

                cur.execute(
                    f"UPDATE {TABLE} SET pagos=%s, payment_status=%s, updated_at=NOW() WHERE id=%s",
                    (PgJson(pagos), status, res_id)
                )
                conn.commit()

        logger.info(f"WC webhook: reservation {res_id} updated → status={status}, amount={total}")
        return {"ok": True, "reservation_id": res_id, "status": status}

    except Exception as e:
        logger.error(f"WC webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
