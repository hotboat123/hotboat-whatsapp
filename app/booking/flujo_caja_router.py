"""Flujo de Caja ledger — parallel bank-movement book (Fecha/Abonos/Cargos/
Origen/Categoría 1/Categoría 2/Descripción/Observaciones/Facturado o IVA),
synced bidirectionally with a Google Sheet (see sheets_sync.py). Additive
only: does not touch gastos/gastos_categorias or financial_router.py.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.db.connection import get_connection

logger = logging.getLogger(__name__)
flujo_caja_router = APIRouter()


def _check_auth(key: str):
    pass  # Auth disabled (same as admin_router / gastos_router)


def _ensure_tables():
    sql = """
    CREATE TABLE IF NOT EXISTS flujo_caja_movimientos (
        id SERIAL PRIMARY KEY,
        fecha DATE,
        abonos INTEGER,
        cargos INTEGER,
        origen TEXT DEFAULT '',
        categoria_1 TEXT DEFAULT '',
        categoria_2 TEXT DEFAULT '',
        descripcion TEXT DEFAULT '',
        observaciones TEXT DEFAULT '',
        facturado_o_iva TEXT DEFAULT '',
        gasto_id INTEGER REFERENCES gastos(id) ON DELETE SET NULL,
        sheet_row INTEGER,
        sheet_snapshot JSONB DEFAULT '{}',
        pushed_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE INDEX IF NOT EXISTS idx_flujo_caja_fecha ON flujo_caja_movimientos(fecha);
    CREATE INDEX IF NOT EXISTS idx_flujo_caja_sheet_row ON flujo_caja_movimientos(sheet_row);

    CREATE TABLE IF NOT EXISTS flujo_caja_producto_defaults (
        id SERIAL PRIMARY KEY,
        producto TEXT UNIQUE NOT NULL,
        categoria_1 TEXT DEFAULT '',
        categoria_2 TEXT DEFAULT '',
        descripcion TEXT DEFAULT '',
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
    except Exception as e:
        logger.error(f"flujo_caja _ensure_tables: {e}")


def learn_producto_default(producto: str, categoria_1: str, categoria_2: str, descripcion: str) -> None:
    """Upsert the producto→categoría mapping whenever a movimiento is saved
    with both a producto text and non-empty categories — this is how the
    "viene por defecto la próxima vez" behavior is built, no manual setup
    required (though it's also editable by hand via the endpoints below)."""
    key = (producto or "").strip().lower()
    if not key or not (categoria_1 or categoria_2):
        return
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO flujo_caja_producto_defaults (producto, categoria_1, categoria_2, descripcion, updated_at) "
                    "VALUES (%s,%s,%s,%s,NOW()) "
                    "ON CONFLICT (producto) DO UPDATE SET categoria_1=EXCLUDED.categoria_1, "
                    "categoria_2=EXCLUDED.categoria_2, descripcion=EXCLUDED.descripcion, updated_at=NOW()",
                    (key, categoria_1 or "", categoria_2 or "", descripcion or ""),
                )
            conn.commit()
    except Exception as e:
        logger.error(f"learn_producto_default({producto}): {e}")


def lookup_producto_default(producto: str) -> Optional[dict]:
    """Exact match first, then substring (either direction) — same
    tolerance as gastos_router._match_category."""
    key = (producto or "").strip().lower()
    if not key:
        return None
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT categoria_1, categoria_2, descripcion FROM flujo_caja_producto_defaults WHERE producto=%s",
                    (key,),
                )
                r = cur.fetchone()
                if r:
                    return {"categoria_1": r[0], "categoria_2": r[1], "descripcion": r[2]}
                cur.execute("SELECT producto, categoria_1, categoria_2, descripcion FROM flujo_caja_producto_defaults")
                for prod, c1, c2, desc in cur.fetchall():
                    if prod and (prod in key or key in prod):
                        return {"categoria_1": c1, "categoria_2": c2, "descripcion": desc}
    except Exception as e:
        logger.error(f"lookup_producto_default({producto}): {e}")
    return None


def create_movimiento_from_gasto(gasto_id: int, fecha: str, monto: int, comercio: str,
                                  notas: str, tipo_documento: str) -> Optional[int]:
    """Called from gastos_router.create_gasto() right after a gasto is
    inserted — additive companion row, never blocks/rolls back the gasto
    itself if this fails."""
    suggestion = lookup_producto_default(comercio) or {}
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO flujo_caja_movimientos "
                    "(fecha, cargos, descripcion, observaciones, facturado_o_iva, "
                    "categoria_1, categoria_2, gasto_id) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                    (fecha, monto, comercio, notas, tipo_documento,
                     suggestion.get("categoria_1", ""), suggestion.get("categoria_2", ""), gasto_id),
                )
                (new_id,) = cur.fetchone()
            conn.commit()
        try:
            from app.booking.sheets_sync import push_row
            push_row(new_id)
        except Exception as e:
            logger.warning(f"Sheets push skipped for movimiento {new_id}: {e}")
        return new_id
    except Exception as e:
        logger.error(f"create_movimiento_from_gasto(gasto_id={gasto_id}): {e}")
        return None


class MovimientoCreate(BaseModel):
    fecha: Optional[str] = None
    abonos: Optional[int] = None
    cargos: Optional[int] = None
    origen: str = ""
    categoria_1: str = ""
    categoria_2: str = ""
    descripcion: str = ""
    observaciones: str = ""
    facturado_o_iva: str = ""


class ProductoDefaultUpsert(BaseModel):
    producto: str
    categoria_1: str = ""
    categoria_2: str = ""
    descripcion: str = ""


def _row_to_dict(r) -> dict:
    return {
        "id": r[0], "fecha": str(r[1]) if r[1] else None,
        "abonos": r[2], "cargos": r[3], "origen": r[4] or "",
        "categoria_1": r[5] or "", "categoria_2": r[6] or "",
        "descripcion": r[7] or "", "observaciones": r[8] or "",
        "facturado_o_iva": r[9] or "", "gasto_id": r[10],
        "created_at": r[11].isoformat() if r[11] else "",
    }


_SELECT_COLS = ("id, fecha, abonos, cargos, origen, categoria_1, categoria_2, "
                "descripcion, observaciones, facturado_o_iva, gasto_id, created_at")


@flujo_caja_router.get("/api/admin/flujo-caja")
async def list_movimientos(year: int = 0, month: int = 0, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    conditions, params = [], []
    if year:
        conditions.append("EXTRACT(YEAR FROM fecha) = %s")
        params.append(year)
    if month:
        conditions.append("EXTRACT(MONTH FROM fecha) = %s")
        params.append(month)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"SELECT {_SELECT_COLS} FROM flujo_caja_movimientos {where} ORDER BY fecha DESC NULLS LAST, id DESC", params)
            rows = cur.fetchall()
    return {"ok": True, "movimientos": [_row_to_dict(r) for r in rows]}


@flujo_caja_router.post("/api/admin/flujo-caja")
async def create_movimiento(body: MovimientoCreate, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO flujo_caja_movimientos "
                "(fecha, abonos, cargos, origen, categoria_1, categoria_2, descripcion, observaciones, facturado_o_iva) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (body.fecha, body.abonos, body.cargos, body.origen, body.categoria_1,
                 body.categoria_2, body.descripcion, body.observaciones, body.facturado_o_iva),
            )
            (new_id,) = cur.fetchone()
        conn.commit()
    learn_producto_default(body.descripcion, body.categoria_1, body.categoria_2, body.descripcion)
    try:
        from app.booking.sheets_sync import push_row
        push_row(new_id)
    except Exception as e:
        logger.warning(f"Sheets push skipped for movimiento {new_id}: {e}")
    return {"ok": True, "id": new_id}


@flujo_caja_router.put("/api/admin/flujo-caja/{mov_id}")
async def update_movimiento(mov_id: int, body: MovimientoCreate, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE flujo_caja_movimientos SET fecha=%s, abonos=%s, cargos=%s, origen=%s, "
                "categoria_1=%s, categoria_2=%s, descripcion=%s, observaciones=%s, "
                "facturado_o_iva=%s, updated_at=NOW() WHERE id=%s",
                (body.fecha, body.abonos, body.cargos, body.origen, body.categoria_1,
                 body.categoria_2, body.descripcion, body.observaciones, body.facturado_o_iva, mov_id),
            )
        conn.commit()
    learn_producto_default(body.descripcion, body.categoria_1, body.categoria_2, body.descripcion)
    try:
        from app.booking.sheets_sync import push_row
        push_row(mov_id)
    except Exception as e:
        logger.warning(f"Sheets push skipped for movimiento {mov_id}: {e}")
    return {"ok": True}


@flujo_caja_router.delete("/api/admin/flujo-caja/{mov_id}")
async def delete_movimiento(mov_id: int, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    try:
        from app.booking.sheets_sync import clear_row
        clear_row(mov_id)
    except Exception as e:
        logger.warning(f"Sheets clear skipped for movimiento {mov_id}: {e}")
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM flujo_caja_movimientos WHERE id=%s", (mov_id,))
        conn.commit()
    return {"ok": True}


@flujo_caja_router.get("/api/admin/flujo-caja/producto-defaults")
async def list_producto_defaults(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, producto, categoria_1, categoria_2, descripcion FROM flujo_caja_producto_defaults ORDER BY producto")
            rows = cur.fetchall()
    return {"ok": True, "defaults": [
        {"id": r[0], "producto": r[1], "categoria_1": r[2] or "", "categoria_2": r[3] or "", "descripcion": r[4] or ""}
        for r in rows
    ]}


@flujo_caja_router.put("/api/admin/flujo-caja/producto-defaults")
async def upsert_producto_default(body: ProductoDefaultUpsert, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    learn_producto_default(body.producto, body.categoria_1, body.categoria_2, body.descripcion)
    return {"ok": True}


@flujo_caja_router.delete("/api/admin/flujo-caja/producto-defaults/{default_id}")
async def delete_producto_default(default_id: int, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM flujo_caja_producto_defaults WHERE id=%s", (default_id,))
        conn.commit()
    return {"ok": True}
