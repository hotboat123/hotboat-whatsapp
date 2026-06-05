"""Gastos (expenses) router — receipt tracking with AI scan via Gemini Flash."""
import base64
import json
import logging
import os
import time
from typing import Optional

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from app.config import get_settings
from app.db.connection import get_connection

logger = logging.getLogger(__name__)
gastos_router = APIRouter()

STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
GASTOS_IMG_DIR = os.path.join(STATIC_DIR, "images", "gastos")


def _check_auth(key: str):
    pass  # Auth disabled (same as admin_router)


def _ensure_tables():
    os.makedirs(GASTOS_IMG_DIR, exist_ok=True)
    sql = """
    CREATE TABLE IF NOT EXISTS gastos_categorias (
        id SERIAL PRIMARY KEY,
        nombre TEXT NOT NULL,
        nivel INTEGER NOT NULL DEFAULT 1,
        parent_id INTEGER REFERENCES gastos_categorias(id) ON DELETE CASCADE,
        keywords JSONB DEFAULT '[]',
        color TEXT DEFAULT '#6b7280',
        icono TEXT DEFAULT '📌',
        created_at TIMESTAMPTZ DEFAULT NOW()
    );
    CREATE TABLE IF NOT EXISTS gastos (
        id SERIAL PRIMARY KEY,
        fecha DATE NOT NULL DEFAULT CURRENT_DATE,
        monto INTEGER NOT NULL DEFAULT 0,
        descripcion TEXT DEFAULT '',
        comercio TEXT DEFAULT '',
        imagen_path TEXT DEFAULT '',
        categoria1_id INTEGER REFERENCES gastos_categorias(id) ON DELETE SET NULL,
        categoria2_id INTEGER REFERENCES gastos_categorias(id) ON DELETE SET NULL,
        tipo_documento VARCHAR(20) DEFAULT 'boleta',
        incluir_en_utilidad BOOLEAN DEFAULT TRUE,
        notas TEXT DEFAULT '',
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW()
    );
    ALTER TABLE gastos ADD COLUMN IF NOT EXISTS tipo_documento VARCHAR(20) DEFAULT 'boleta';
    ALTER TABLE gastos ADD COLUMN IF NOT EXISTS incluir_en_utilidad BOOLEAN DEFAULT TRUE;
    CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos(fecha);
    CREATE INDEX IF NOT EXISTS idx_gastos_cat1 ON gastos(categoria1_id);
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql)
            conn.commit()
        _seed_default_categories()
    except Exception as e:
        logger.error(f"gastos _ensure_tables: {e}")


def _seed_default_categories():
    defaults = [
        ("Combustible",  1, "#ef4444", "⛽", ["bencina", "combustible", "copec", "shell", "petrobras", "axion", "gasolinera"]),
        ("Mantenimiento",1, "#f97316", "🔧", ["mantención", "reparación", "taller", "repuesto", "ferretería", "herramienta"]),
        ("Marketing",    1, "#8b5cf6", "📣", ["publicidad", "instagram", "facebook", "google", "meta", "diseño", "imprenta", "flyer"]),
        ("Alimentación", 1, "#22c55e", "🍽️", ["supermercado", "restaurant", "comida", "almuerzo", "jumbo", "lider", "unimarc", "santa isabel", "colación"]),
        ("Servicios",    1, "#0ea5e9", "💡", ["agua", "luz", "electricidad", "internet", "teléfono", "básico", "sanitario"]),
        ("Suministros",  1, "#f59e0b", "🛒", ["materiales", "insumos", "limpieza", "útiles", "papelería", "producto"]),
        ("Otros",        1, "#6b7280", "📌", []),
    ]
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM gastos_categorias WHERE nivel=1")
                (count,) = cur.fetchone()
                if count > 0:
                    return
                for nombre, nivel, color, icono, kws in defaults:
                    cur.execute(
                        "INSERT INTO gastos_categorias (nombre, nivel, color, icono, keywords) VALUES (%s,%s,%s,%s,%s)",
                        (nombre, nivel, color, icono, json.dumps(kws, ensure_ascii=False)),
                    )
            conn.commit()
    except Exception as e:
        logger.error(f"gastos seed categories: {e}")


def _match_category(text: str, categorias: list) -> Optional[int]:
    txt = text.lower()
    for cat in categorias:
        if cat["nivel"] != 1:
            continue
        kws = cat.get("keywords") or []
        if isinstance(kws, str):
            kws = json.loads(kws)
        for kw in kws:
            if kw and kw.lower() in txt:
                return cat["id"]
    return None


# ── Models ─────────────────────────────────────────────────────────────────────

IVA = 1.19

def monto_neto(monto: int, tipo_documento: str) -> int:
    """Net amount after IVA. Facturas give IVA credit → neto = monto/1.19. Boleta/sin doc: neto = monto."""
    if tipo_documento == "factura":
        return round(monto / IVA)
    return monto


class GastoCreate(BaseModel):
    fecha: str
    monto: int
    descripcion: str = ""
    comercio: str = ""
    imagen_base64: str = ""
    imagen_mime: str = "image/jpeg"
    categoria1_id: Optional[int] = None
    categoria2_id: Optional[int] = None
    tipo_documento: str = "boleta"  # boleta | factura | sin_documento
    incluir_en_utilidad: bool = True
    notas: str = ""


class CategoriaCreate(BaseModel):
    nombre: str
    nivel: int = 1
    parent_id: Optional[int] = None
    keywords: list = []
    color: str = "#6b7280"
    icono: str = "📌"


class ScanRequest(BaseModel):
    imagen_base64: str
    mime_type: str = "image/jpeg"


# ── Categorías ─────────────────────────────────────────────────────────────────

@gastos_router.get("/api/admin/gastos/categorias")
async def list_categorias(x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nombre, nivel, parent_id, keywords, color, icono "
                "FROM gastos_categorias ORDER BY nivel, nombre"
            )
            rows = cur.fetchall()
    return {"ok": True, "categorias": [
        {"id": r[0], "nombre": r[1], "nivel": r[2], "parent_id": r[3],
         "keywords": r[4] if isinstance(r[4], list) else json.loads(r[4] or "[]"),
         "color": r[5], "icono": r[6]}
        for r in rows
    ]}


@gastos_router.post("/api/admin/gastos/categorias")
async def create_categoria(body: CategoriaCreate, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    kws_json = json.dumps(body.keywords, ensure_ascii=False)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO gastos_categorias (nombre, nivel, parent_id, keywords, color, icono) "
                "VALUES (%s,%s,%s,%s,%s,%s) RETURNING id",
                (body.nombre, body.nivel, body.parent_id, kws_json, body.color, body.icono),
            )
            (new_id,) = cur.fetchone()
        conn.commit()
    return {"ok": True, "id": new_id}


@gastos_router.put("/api/admin/gastos/categorias/{cat_id}")
async def update_categoria(cat_id: int, body: CategoriaCreate, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    kws_json = json.dumps(body.keywords, ensure_ascii=False)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE gastos_categorias SET nombre=%s, nivel=%s, parent_id=%s, "
                "keywords=%s, color=%s, icono=%s WHERE id=%s",
                (body.nombre, body.nivel, body.parent_id, kws_json, body.color, body.icono, cat_id),
            )
        conn.commit()
    return {"ok": True}


@gastos_router.delete("/api/admin/gastos/categorias/{cat_id}")
async def delete_categoria(cat_id: int, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM gastos_categorias WHERE id=%s", (cat_id,))
        conn.commit()
    return {"ok": True}


# ── AI Scan ────────────────────────────────────────────────────────────────────

@gastos_router.post("/api/admin/gastos/scan")
async def scan_receipt(body: ScanRequest, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    settings = get_settings()
    api_key = settings.gemini_api_key
    if not api_key:
        raise HTTPException(status_code=503, detail="GEMINI_API_KEY no configurado")

    prompt = (
        "Analiza esta boleta o ticket de Chile. Extrae: "
        "1) monto total pagado en CLP (número entero, sin puntos ni símbolo $), "
        "2) nombre del comercio o negocio, "
        "3) fecha de la boleta en formato YYYY-MM-DD (null si no es visible). "
        "Responde SOLO con JSON válido sin texto ni comillas adicionales: "
        '{"monto": 12500, "comercio": "Copec Av. Principal", "fecha": "2024-01-15"}'
    )

    payload = {
        "contents": [{"parts": [
            {"inline_data": {"mime_type": body.mime_type, "data": body.imagen_base64}},
            {"text": prompt},
        ]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 300},
    }

    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-1.5-flash:generateContent?key={api_key}"
    )
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.post(url, json=payload)
        resp.raise_for_status()
        raw_text = resp.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
        extracted = json.loads(raw_text)
    except Exception as e:
        logger.error(f"Gemini scan error: {e}")
        raise HTTPException(status_code=502, detail=f"Error al escanear la boleta: {e}")

    # Keyword-based category matching
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, nombre, nivel, keywords FROM gastos_categorias WHERE nivel=1")
            cats = [{"id": r[0], "nombre": r[1], "nivel": r[2], "keywords": r[3]} for r in cur.fetchall()]

    search_text = f"{extracted.get('comercio', '')} {extracted.get('descripcion', '')}".lower()
    cat1_id = _match_category(search_text, cats)

    return {
        "ok": True,
        "monto": extracted.get("monto"),
        "comercio": extracted.get("comercio", ""),
        "fecha": extracted.get("fecha"),
        "categoria1_id": cat1_id,
    }


# ── Gastos CRUD ────────────────────────────────────────────────────────────────

@gastos_router.get("/api/admin/gastos")
async def list_gastos(year: int = 0, month: int = 0, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    conditions, params = [], []
    if year:
        conditions.append("EXTRACT(YEAR FROM g.fecha) = %s")
        params.append(year)
    if month:
        conditions.append("EXTRACT(MONTH FROM g.fecha) = %s")
        params.append(month)
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    sql = f"""
        SELECT g.id, g.fecha, g.monto, g.descripcion, g.comercio, g.imagen_path,
               g.categoria1_id, c1.nombre, c1.color, c1.icono,
               g.categoria2_id, c2.nombre, c2.color, c2.icono,
               g.notas, g.created_at, COALESCE(g.tipo_documento, 'boleta'),
               COALESCE(g.incluir_en_utilidad, TRUE)
        FROM gastos g
        LEFT JOIN gastos_categorias c1 ON g.categoria1_id = c1.id
        LEFT JOIN gastos_categorias c2 ON g.categoria2_id = c2.id
        {where}
        ORDER BY g.fecha DESC, g.id DESC
    """
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    def _build_row(r):
        m = r[2] or 0
        tdoc = r[16] or "boleta"
        neto = monto_neto(m, tdoc)
        return {
            "id": r[0], "fecha": str(r[1]), "monto": m,
            "monto_neto": neto,
            "iva_credito": (m - neto) if tdoc == "factura" else 0,
            "tipo_documento": tdoc,
            "incluir_en_utilidad": r[17] if r[17] is not None else True,
            "descripcion": r[3] or "", "comercio": r[4] or "",
            "imagen_path": r[5] or "",
            "categoria1_id": r[6],
            "categoria1_nombre": r[7] or "",
            "categoria1_color": r[8] or "#6b7280",
            "categoria1_icono": r[9] or "📌",
            "categoria2_id": r[10],
            "categoria2_nombre": r[11] or "",
            "categoria2_color": r[12] or "#6b7280",
            "categoria2_icono": r[13] or "📌",
            "notas": r[14] or "",
            "created_at": r[15].isoformat() if r[15] else "",
        }

    return {"ok": True, "gastos": [_build_row(r) for r in rows]}


@gastos_router.post("/api/admin/gastos")
async def create_gasto(body: GastoCreate, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    imagen_path = ""
    if body.imagen_base64:
        try:
            os.makedirs(GASTOS_IMG_DIR, exist_ok=True)
            img_data = base64.b64decode(body.imagen_base64)
            ext = ".png" if "png" in body.imagen_mime else ".jpg"
            filename = f"gasto_{int(time.time() * 1000)}{ext}"
            with open(os.path.join(GASTOS_IMG_DIR, filename), "wb") as fh:
                fh.write(img_data)
            imagen_path = f"/static/images/gastos/{filename}"
        except Exception as e:
            logger.error(f"Error saving gasto image: {e}")

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO gastos (fecha, monto, descripcion, comercio, imagen_path, "
                "categoria1_id, categoria2_id, tipo_documento, incluir_en_utilidad, notas) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (body.fecha, body.monto, body.descripcion, body.comercio,
                 imagen_path, body.categoria1_id, body.categoria2_id,
                 body.tipo_documento, body.incluir_en_utilidad, body.notas),
            )
            (new_id,) = cur.fetchone()
        conn.commit()
    return {"ok": True, "id": new_id, "imagen_path": imagen_path}


@gastos_router.delete("/api/admin/gastos/{gasto_id}")
async def delete_gasto(gasto_id: int, x_admin_key: str = Header("")):
    _check_auth(x_admin_key)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT imagen_path FROM gastos WHERE id=%s", (gasto_id,))
            row = cur.fetchone()
            if row and row[0]:
                rel = row[0].replace("/static/", "", 1)
                full_path = os.path.join(STATIC_DIR, rel)
                if os.path.exists(full_path):
                    try:
                        os.remove(full_path)
                    except Exception:
                        pass
            cur.execute("DELETE FROM gastos WHERE id=%s", (gasto_id,))
        conn.commit()
    return {"ok": True}
