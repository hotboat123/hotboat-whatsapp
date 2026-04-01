"""Admin dashboard router for HotBoat booking management."""
import logging
import os
from typing import Optional
from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.db.connection import get_connection

logger = logging.getLogger(__name__)
admin_router = APIRouter()
CHILE_TZ = ZoneInfo("America/Santiago")
SHEETS_TABLE = '"Reservas_Con_Extras_Sheets"'


# ── Auth helper ──────────────────────────────────────────────────────────────

def _check_auth(x_admin_key: str = ""):
    expected = os.getenv("ADMIN_PASSWORD", "hotboat2024")
    if x_admin_key != expected:
        raise HTTPException(status_code=401, detail="Unauthorized")


# ── HTML page ────────────────────────────────────────────────────────────────

def _admin_html() -> str:
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "admin-bookings.html")
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


@admin_router.get("/admin/reservas", response_class=HTMLResponse)
async def admin_page():
    try:
        return HTMLResponse(_admin_html())
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="admin-bookings.html not found")


# ── List reservations ────────────────────────────────────────────────────────

@admin_router.get("/api/admin/reservas")
async def list_reservas(
    desde: Optional[str] = Query(None),
    hasta: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
    x_admin_key: str = Header(""),
):
    _check_auth(x_admin_key)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                wheres = []
                params = []
                if desde:
                    wheres.append("fecha >= %s"); params.append(desde)
                if hasta:
                    wheres.append("fecha <= %s"); params.append(hasta)
                if status and status != "all":
                    wheres.append("status = %s"); params.append(status)
                if search:
                    wheres.append(
                        "(nombre_cliente ILIKE %s OR telefono ILIKE %s OR email ILIKE %s)"
                    )
                    s = f"%{search}%"
                    params += [s, s, s]
                where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""
                params.append(limit)
                cur.execute(f"""
                    SELECT id, appointment_id, reservation_id,
                           fecha, hora, nombre_cliente, email, telefono,
                           servicio, num_personas, num_adultos, num_ninos,
                           ingreso_reserva, ingreso_extras, ingreso_total,
                           costo_operativo_fijo, costo_operativo_variable, costo_operativo_total,
                           ciudad_origen, como_supieron, clima_del_dia,
                           categoria_clientes, tipo_clientes,
                           status, tiene_cruce, extras_json, source,
                           created_at, updated_at
                    FROM {SHEETS_TABLE}
                    {where_sql}
                    ORDER BY fecha DESC, hora DESC
                    LIMIT %s
                """, params)
                cols = [d[0] for d in cur.description]
                rows = []
                for row in cur.fetchall():
                    r = dict(zip(cols, row))
                    for k in ("fecha", "created_at", "updated_at"):
                        if r.get(k):
                            r[k] = r[k].isoformat()
                    if r.get("hora"):
                        r["hora"] = str(r["hora"])
                    for k in ("ingreso_reserva","ingreso_extras","ingreso_total",
                              "costo_operativo_fijo","costo_operativo_variable","costo_operativo_total"):
                        if r.get(k) is not None:
                            r[k] = float(r[k])
                    rows.append(r)
        return {"reservas": rows, "total": len(rows)}
    except Exception as e:
        logger.error(f"Error listing reservas: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Single reservation ───────────────────────────────────────────────────────

@admin_router.get("/api/admin/reservas/{rid}")
async def get_reserva(rid: int, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(f"SELECT * FROM {SHEETS_TABLE} WHERE id=%s", (rid,))
                row = cur.fetchone()
                if not row:
                    raise HTTPException(status_code=404, detail="Not found")
                cols = [d[0] for d in cur.description]
                r = dict(zip(cols, row))
                for k in ("fecha", "created_at", "updated_at"):
                    if r.get(k): r[k] = r[k].isoformat()
                if r.get("hora"): r["hora"] = str(r["hora"])
                for k in ("ingreso_reserva","ingreso_extras","ingreso_total",
                          "costo_operativo_fijo","costo_operativo_variable","costo_operativo_total"):
                    if r.get(k) is not None: r[k] = float(r[k])
                return r
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Update reservation ───────────────────────────────────────────────────────

class UpdateReservaRequest(BaseModel):
    status: Optional[str] = None
    nombre_cliente: Optional[str] = None
    telefono: Optional[str] = None
    email: Optional[str] = None
    ciudad_origen: Optional[str] = None
    como_supieron: Optional[str] = None
    clima_del_dia: Optional[str] = None
    categoria_clientes: Optional[str] = None
    tipo_clientes: Optional[str] = None
    num_adultos: Optional[int] = None
    num_ninos: Optional[int] = None
    ingreso_reserva: Optional[float] = None
    ingreso_extras: Optional[float] = None
    ingreso_total: Optional[float] = None
    costo_operativo_fijo: Optional[float] = None
    costo_operativo_variable: Optional[float] = None
    tiene_cruce: Optional[bool] = None


@admin_router.put("/api/admin/reservas/{rid}")
async def update_reserva(rid: int, body: UpdateReservaRequest, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                set_parts = [f"{k}=%s" for k in updates]
                set_parts.append("updated_at=NOW()")
                params = list(updates.values()) + [rid]
                cur.execute(
                    f"UPDATE {SHEETS_TABLE} SET {', '.join(set_parts)} WHERE id=%s",
                    params
                )
                # Also sync status to hotboat_appointments if it has appointment_id
                if "status" in updates:
                    cur.execute(f"SELECT appointment_id FROM {SHEETS_TABLE} WHERE id=%s", (rid,))
                    row = cur.fetchone()
                    if row and row[0]:
                        cur.execute(
                            "UPDATE hotboat_appointments SET status=%s, updated_at=NOW() WHERE booking_ref=%s",
                            (updates["status"], row[0])
                        )
                conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error updating reserva {rid}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Stats ────────────────────────────────────────────────────────────────────

@admin_router.get("/api/admin/stats")
async def get_stats(
    year: int = Query(2026),
    month: Optional[int] = Query(None),
    x_admin_key: str = Header(""),
):
    _check_auth(x_admin_key)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Monthly revenue for the year
                cur.execute(f"""
                    SELECT EXTRACT(MONTH FROM fecha)::int AS mes,
                           COUNT(*) AS n_reservas,
                           SUM(ingreso_total) AS ingresos,
                           SUM(ingreso_extras) AS extras,
                           SUM(costo_operativo_total) AS costos,
                           SUM(ingreso_total - COALESCE(costo_operativo_total,0)) AS margen
                    FROM {SHEETS_TABLE}
                    WHERE EXTRACT(YEAR FROM fecha) = %s
                      AND (status IS NULL OR status NOT IN ('cancelled','rejected','cancelada','rechazada'))
                    GROUP BY mes ORDER BY mes
                """, (year,))
                monthly = []
                for row in cur.fetchall():
                    monthly.append({
                        "mes": int(row[0]), "n_reservas": int(row[1]),
                        "ingresos": float(row[2] or 0),
                        "extras": float(row[3] or 0),
                        "costos": float(row[4] or 0),
                        "margen": float(row[5] or 0),
                    })

                # Status breakdown
                cur.execute(f"""
                    SELECT status, COUNT(*) FROM {SHEETS_TABLE}
                    WHERE EXTRACT(YEAR FROM fecha) = %s
                    GROUP BY status
                """, (year,))
                by_status = {(row[0] or "sin estado"): int(row[1]) for row in cur.fetchall()}

                # Totals for current year
                cur.execute(f"""
                    SELECT COUNT(*) AS total,
                           SUM(ingreso_total) AS total_ingresos,
                           AVG(ingreso_total) AS avg_reserva,
                           AVG(num_personas::float) AS avg_personas
                    FROM {SHEETS_TABLE}
                    WHERE EXTRACT(YEAR FROM fecha) = %s
                      AND (status IS NULL OR status NOT IN ('cancelled','rejected','cancelada','rechazada'))
                """, (year,))
                row = cur.fetchone()
                totals = {
                    "total_reservas": int(row[0] or 0),
                    "total_ingresos": float(row[1] or 0),
                    "avg_reserva": float(row[2] or 0),
                    "avg_personas": float(row[3] or 0),
                }

                # Source breakdown
                cur.execute(f"""
                    SELECT source, COUNT(*) FROM {SHEETS_TABLE}
                    WHERE EXTRACT(YEAR FROM fecha) = %s
                    GROUP BY source
                """, (year,))
                by_source = {(row[0] or "desconocido"): int(row[1]) for row in cur.fetchall()}

        return {"monthly": monthly, "by_status": by_status, "by_source": by_source, **totals}
    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ── Clients ──────────────────────────────────────────────────────────────────

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
                where = ""
                params = []
                if search:
                    where = "WHERE nombre_cliente ILIKE %s OR telefono ILIKE %s OR email ILIKE %s"
                    s = f"%{search}%"
                    params = [s, s, s]
                params.append(limit)
                cur.execute(f"""
                    SELECT telefono,
                           MAX(nombre_cliente) AS nombre,
                           MAX(email) AS email,
                           COUNT(*) AS total_reservas,
                           SUM(ingreso_total) AS total_gastado,
                           MAX(fecha) AS ultima_reserva,
                           MIN(fecha) AS primera_reserva
                    FROM {SHEETS_TABLE}
                    {where}
                    GROUP BY telefono
                    ORDER BY total_reservas DESC, ultima_reserva DESC
                    LIMIT %s
                """, params)
                cols = [d[0] for d in cur.description]
                clients = []
                for row in cur.fetchall():
                    c = dict(zip(cols, row))
                    for k in ("ultima_reserva","primera_reserva"):
                        if c.get(k): c[k] = c[k].isoformat()
                    if c.get("total_gastado"): c["total_gastado"] = float(c["total_gastado"])
                    clients.append(c)
        return {"clients": clients}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Sync hotboat_appointments → Reservas_Con_Extras_Sheets ──────────────────

@admin_router.post("/api/admin/sync")
async def sync_tables(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Find hotboat_appointments not yet in Reservas_Con_Extras_Sheets
                cur.execute("""
                    SELECT h.booking_ref, h.customer_name, h.customer_email,
                           h.customer_phone, h.booking_date, h.booking_time,
                           h.num_people, h.subtotal, h.extras_total, h.total_price,
                           h.extras, h.status, h.source, h.notes
                    FROM hotboat_appointments h
                    WHERE h.status NOT IN ('solicitud')
                      AND NOT EXISTS (
                          SELECT 1 FROM "Reservas_Con_Extras_Sheets" s
                          WHERE s.appointment_id = h.booking_ref
                      )
                """)
                to_insert = cur.fetchall()
                inserted = 0
                for row in to_insert:
                    (ref, nombre, email, tel, fecha, hora, npers,
                     subtotal, extras_total, total, extras_json, status, source, notes) = row
                    personas_str = str(npers) if npers else None
                    cur.execute(f"""
                        INSERT INTO {SHEETS_TABLE}
                        (appointment_id, fecha, hora, nombre_cliente, email, telefono,
                         servicio, num_personas, ingreso_reserva, ingreso_extras,
                         ingreso_total, costo_operativo_fijo, costo_operativo_total,
                         extras_json, status, source, created_at, updated_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
                    """, (
                        ref, fecha, hora, nombre, email, tel,
                        f"HotBoat Web ({npers}p)", personas_str,
                        float(subtotal or 0), float(extras_total or 0),
                        float(total or 0), 18000.0, 18000.0,
                        extras_json or {}, status, source or "web"
                    ))
                    inserted += 1

                # Sync status back: if status changed in sheets, update hotboat_appointments
                cur.execute(f"""
                    UPDATE hotboat_appointments ha
                    SET status = s.status, updated_at = NOW()
                    FROM {SHEETS_TABLE} s
                    WHERE s.appointment_id = ha.booking_ref
                      AND s.status IS DISTINCT FROM ha.status
                """)
                updated = cur.rowcount

                conn.commit()
        return {"inserted": inserted, "status_synced": updated}
    except Exception as e:
        logger.error(f"Sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
