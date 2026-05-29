"""
Bot configuration router — CRUD for chatbot messages and keywords.
"""
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

bot_config_router = APIRouter(prefix="/api/admin/bot", tags=["bot-config"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class ResponseUpdate(BaseModel):
    content_es: Optional[str] = None
    content_en: Optional[str] = None
    content_pt: Optional[str] = None


class KeywordCreate(BaseModel):
    keyword: str
    response_key: str


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_conn():
    from app.db.connection import get_connection
    return get_connection()


def _ensure_tables():
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS bot_responses (
                        response_key TEXT PRIMARY KEY,
                        label        TEXT NOT NULL DEFAULT '',
                        content_es   TEXT,
                        content_en   TEXT,
                        content_pt   TEXT,
                        updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS bot_keywords (
                        id           SERIAL PRIMARY KEY,
                        keyword      TEXT UNIQUE NOT NULL,
                        response_key TEXT NOT NULL,
                        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                conn.commit()
        logger.info("✅ bot_responses / bot_keywords tables ready")
    except Exception as e:
        logger.warning("bot config tables setup failed: %s", e)


# ── Responses ─────────────────────────────────────────────────────────────────

@bot_config_router.get("/responses")
async def get_responses():
    """Return all bot responses from DB."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT response_key, label, content_es, content_en, content_pt, updated_at
                    FROM bot_responses ORDER BY response_key
                """)
                rows = cur.fetchall()
        return {"responses": [
            {
                "response_key": r[0],
                "label": r[1],
                "content_es": r[2],
                "content_en": r[3],
                "content_pt": r[4],
                "updated_at": r[5].isoformat() if r[5] else None,
            }
            for r in rows
        ]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@bot_config_router.put("/responses/{key}")
async def update_response(key: str, data: ResponseUpdate):
    """Create or update a bot response."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO bot_responses (response_key, label, content_es, content_en, content_pt)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (response_key) DO UPDATE
                    SET content_es = COALESCE(EXCLUDED.content_es, bot_responses.content_es),
                        content_en = COALESCE(EXCLUDED.content_en, bot_responses.content_en),
                        content_pt = COALESCE(EXCLUDED.content_pt, bot_responses.content_pt),
                        updated_at = NOW()
                """, (key, key, data.content_es, data.content_en, data.content_pt))
                conn.commit()
        return {"status": "ok", "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Keywords ──────────────────────────────────────────────────────────────────

@bot_config_router.get("/keywords")
async def get_keywords():
    """Return all bot keywords from DB."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, keyword, response_key, created_at
                    FROM bot_keywords ORDER BY response_key, keyword
                """)
                rows = cur.fetchall()
        return {"keywords": [
            {
                "id": r[0],
                "keyword": r[1],
                "response_key": r[2],
                "created_at": r[3].isoformat() if r[3] else None,
            }
            for r in rows
        ]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@bot_config_router.post("/keywords")
async def add_keyword(data: KeywordCreate):
    """Add a new keyword mapping."""
    kw = data.keyword.strip().lower()
    if not kw:
        raise HTTPException(status_code=400, detail="Keyword cannot be empty")
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO bot_keywords (keyword, response_key)
                    VALUES (%s, %s)
                    ON CONFLICT (keyword) DO UPDATE SET response_key = EXCLUDED.response_key
                """, (kw, data.response_key))
                conn.commit()
        return {"status": "ok", "keyword": kw}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@bot_config_router.delete("/keywords/{kw_id}")
async def delete_keyword(kw_id: int):
    """Delete a keyword by ID."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM bot_keywords WHERE id = %s", (kw_id,))
                conn.commit()
        return {"status": "ok"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Seed defaults (called on startup) ────────────────────────────────────────

_DEFAULT_RESPONSES = {
    "bienvenida": {
        "label": "Saludo de bienvenida (opción 0)",
        "content_es": "¡Hola {name}! 👋\nSoy Capitán HotBoat 🚤\n¿En qué puedo ayudarte hoy?",
    },
    "caracteristicas": {
        "label": "Características del HotBoat (opción 3)",
    },
    "precio": {
        "label": "Precios por persona (opción 2)",
    },
    "ubicación": {
        "label": "Ubicación y cómo llegar (opción 5)",
    },
    "clima": {
        "label": "Lluvia / clima (opción 🌧️)",
    },
    "cancelar": {
        "label": "Política de cancelación",
    },
    "traer": {
        "label": "Qué traer al paseo",
    },
    "bebestibles": {
        "label": "Bebestibles / bebidas (opción 🍷)",
        "content_es": (
            "🍷 *Opciones para celebrar* (solo adultos)\n\n"
            "$6.000 → Cerveza artesanal 330ml\n"
            "$6.000 → Cerveza Corona 330ml\n"
            "$15.000 → Vino tinto o blanco (botella)\n"
            "$26.000 → Champagne\n"
            "$20.000 → Pack 4 cervezas artesanales"
        ),
    },
    "niños": {
        "label": "Info sobre niños (opción 👶)",
        "content_es": "Sí!, los niños lo pasan increíble 🎉\n---\nPagan desde los 6 años, a los menores no los consideres en el número de personas de la reserva 👍",
    },
    "lluvia": {
        "label": "Respuesta sobre lluvia (opción 🌧️)",
        "content_es": "Con lluvia la experiencia es aún mejor ☔🔥\n---\n¡El HotBoat es una tina de agua caliente! La lluvia se siente increíble desde adentro 🌧️🛁\n---\nTe pasamos sombreros para que no te llegue el agua en la cara todo el tiempo 🎩😄",
    },
    "comida": {
        "label": "Política de comida (opción 🍽️)",
        "content_es": "Pueden traer lo que quieran para comer o tomar 🍕🥗\n---\no pueden pedir aquí 🙂",
    },
}

_DEFAULT_KEYWORDS = {
    # caracteristicas
    "en que consiste": "caracteristicas",
    "incluye": "caracteristicas",
    "info": "caracteristicas",
    "información": "caracteristicas",
    "dura": "caracteristicas",
    "duración": "caracteristicas",
    "tiempo": "caracteristicas",
    # precio
    "valor": "precio",
    "valores": "precio",
    "cuanto cuesta": "precio",
    "cuánto cuesta": "precio",
    # ubicación
    "donde": "ubicación",
    "dónde": "ubicación",
    "donde estan": "ubicación",
    "donde están": "ubicación",
    # clima
    "temporada": "clima",
    "cuando": "clima",
    "cuándo": "clima",
    # cancelar
    "reembolso": "cancelar",
    "devolver": "cancelar",
    "anular": "cancelar",
}


def seed_defaults():
    """Insert default responses/keywords only if the table is empty."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM bot_responses")
                count = cur.fetchone()[0]
                if count == 0:
                    for key, val in _DEFAULT_RESPONSES.items():
                        cur.execute("""
                            INSERT INTO bot_responses (response_key, label, content_es)
                            VALUES (%s, %s, %s)
                            ON CONFLICT DO NOTHING
                        """, (key, val.get("label", key), val.get("content_es")))

                cur.execute("SELECT COUNT(*) FROM bot_keywords")
                count = cur.fetchone()[0]
                if count == 0:
                    for kw, rk in _DEFAULT_KEYWORDS.items():
                        cur.execute("""
                            INSERT INTO bot_keywords (keyword, response_key)
                            VALUES (%s, %s)
                            ON CONFLICT DO NOTHING
                        """, (kw, rk))

                conn.commit()
        logger.info("✅ bot config defaults seeded")
    except Exception as e:
        logger.warning("bot config seed failed: %s", e)
