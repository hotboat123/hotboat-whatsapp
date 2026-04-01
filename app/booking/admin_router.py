"""Admin dashboard router — uses all_appointments as single source of truth."""
import logging
import os
import re
from typing import Optional
from zoneinfo import ZoneInfo

from fastapi import APIRouter, HTTPException, Query, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.db.connection import get_connection

logger = logging.getLogger(__name__)
admin_router = APIRouter()
CHILE_TZ = ZoneInfo("America/Santiago")
TABLE = "all_appointments"


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
                           ingreso_reserva, ingreso_extras, ingreso_total,
                           costo_operativo_fijo, costo_operativo_variable, costo_operativo_total,
                           ciudad_origen, como_supieron, clima_del_dia,
                           categoria_clientes, tipo_clientes,
                           status, tiene_cruce, extras_json, observaciones,
                           payment_id, payment_status,
                           COALESCE(pagos, '[]'::jsonb) AS pagos,
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
                cur.execute(f"SELECT *, COALESCE(pagos,'[]'::jsonb) AS pagos FROM {TABLE} WHERE id=%s", (rid,))
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
    num_adultos: Optional[int] = None
    num_ninos: Optional[int] = None
    ingreso_reserva: Optional[float] = None
    ingreso_extras: Optional[float] = None
    ingreso_total: Optional[float] = None
    costo_operativo_fijo: Optional[float] = None
    costo_operativo_variable: Optional[float] = None
    costo_operativo_total: Optional[float] = None
    tiene_cruce: Optional[bool] = None
    extras_json: Optional[dict] = None
    pagos: Optional[list] = None


@admin_router.put("/api/admin/reservas/{rid}")
async def update_reserva(rid: int, body: UpdateReservaRequest, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="Nothing to update")
    try:
        from psycopg2.extras import Json as PgJson
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Convert dict/list fields for JSONB
                if "extras_json" in updates:
                    updates["extras_json"] = PgJson(updates["extras_json"])
                if "pagos" in updates:
                    updates["pagos"] = PgJson(updates["pagos"])

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
                        # Also sync back to Reservas_Con_Extras_Sheets for historical records
                        elif src == "sheets" and src_id:
                            cur.execute(
                                'UPDATE "Reservas_Con_Extras_Sheets" SET status=%s, updated_at=NOW() WHERE id=%s',
                                (updates["status"], int(src_id))
                            )

                conn.commit()
        return {"ok": True}
    except Exception as e:
        logger.error(f"Error updating reserva {rid}: {e}")
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


# ── Incremental sync ──────────────────────────────────────────────────────────
# Pulls NEW records from booknetic + hotboat into all_appointments
# Does NOT re-import historical data (fecha <= max_sheets_fecha)

@admin_router.post("/api/admin/sync")
async def sync_tables(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    try:
        from psycopg2.extras import Json as PgJson

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
                # Get cutoff date (max fecha in sheets source)
                cur.execute(f"SELECT MAX(fecha) FROM {TABLE} WHERE source='sheets'")
                cutoff = cur.fetchone()[0]
                if not cutoff:
                    raise HTTPException(status_code=500, detail="No sheets records found, run migration 013 first")

                inserted_book = 0
                inserted_hb = 0
                updated_status = 0

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
            "inserted_booknetic": inserted_book,
            "inserted_hotboat": inserted_hb,
            "status_updated": updated_status,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Sync error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
