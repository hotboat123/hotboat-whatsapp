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
        "content_es": (
            "Estas son las características de la experiencia HotBoat 🚤🔥:\n\n"
            "⚡ Motor eléctrico (silencioso y sustentable)\n"
            "⏱️ Duración: 2 horas\n"
            "🔥 Tú eliges la temperatura del agua (antes y durante el paseo)\n"
            "🛥️ Fácil de navegar → ¡puedes manejarlo tú mismo!\n"
            "🎶 Escucha tu propia música con parlante bluetooth + bolsas impermeables\n"
            "🎥 Video cinematográfico de tu aventura disponible\n"
            "🍹 ¡Disfruta bebestibles a bordo del HotBoat! Se mantendrán fríos en el cooler.\n"
            "🧺 Opción de tablas de picoteo a bordo\n"
            "🧼 Se limpia y se cambia el agua antes de cada uso, siempre impecable\n\n"
            "¿Te gustaría reservar tu experiencia?"
        ),
        "content_en": (
            "Here are the features of the HotBoat experience 🚤🔥:\n\n"
            "⚡ Electric motor (silent and sustainable)\n"
            "⏱️ Duration: 2 hours\n"
            "🔥 You choose the water temperature (before and during the ride)\n"
            "🛥️ Easy to navigate → you can drive it yourself!\n"
            "🎶 Listen to your own music with bluetooth speaker + waterproof bags\n"
            "🎥 Cinematic video of your adventure available\n"
            "🍹 Enjoy drinks on board the HotBoat! They'll stay cold in the cooler.\n"
            "🧺 Charcuterie board option on board\n"
            "🧼 Cleaned and the water is changed before each use, always immaculate\n\n"
            "Would you like to book your experience?"
        ),
        "content_pt": (
            "Estas são as características da experiência HotBoat 🚤🔥:\n\n"
            "⚡ Motor elétrico (silencioso e sustentável)\n"
            "⏱️ Duração: 2 horas\n"
            "🔥 Você escolhe a temperatura da água (antes e durante o passeio)\n"
            "🛥️ Fácil de navegar → você pode dirigir você mesmo!\n"
            "🎶 Ouça sua própria música com alto-falante bluetooth + bolsas impermeáveis\n"
            "🎥 Vídeo cinematográfico da sua aventura disponível\n"
            "🍹 Desfrute de bebidas a bordo do HotBoat! Ficarão geladas no cooler.\n"
            "🧺 Opção de tábua de frios a bordo\n"
            "🧼 Limpo e a água é trocada antes de cada uso, sempre impecável\n\n"
            "Gostaria de reservar sua experiência?"
        ),
    },
    "precio": {
        "label": "Precios por persona (opción 2)",
        "content_es": (
            "💰 *Precios HotBoat:*\n\n"
            "👥 *2 personas*\n• $69.990 x persona\n• Total: *$139.980*\n\n"
            "👥 *3 personas*\n• $54.990 x persona\n• Total: *$164.970*\n\n"
            "👥 *4 personas*\n• $44.990 x persona\n• Total: *$179.960*\n\n"
            "👥 *5 personas*\n• $38.990 x persona\n• Total: *$194.950*\n\n"
            "👥 *6 personas*\n• $32.990 x persona\n• Total: *$197.940*\n\n"
            "👥 *7 personas*\n• $29.990 x persona\n• Total: *$209.930*\n\n"
            "_*niños pagan desde los 6 años_\n\n"
            "Aquí puedes reservar tu horario directo 👇\nhttps://whatsapp.hotboat.cl/booking"
        ),
        "content_en": (
            "💰 *HotBoat Prices:*\n\n"
            "👥 *2 people*\n• $69,990 per person\n• Total: *$139,980 CLP*\n\n"
            "👥 *3 people*\n• $54,990 per person\n• Total: *$164,970 CLP*\n\n"
            "👥 *4 people*\n• $44,990 per person\n• Total: *$179,960 CLP*\n\n"
            "👥 *5 people*\n• $38,990 per person\n• Total: *$194,950 CLP*\n\n"
            "👥 *6 people*\n• $32,990 per person\n• Total: *$197,940 CLP*\n\n"
            "👥 *7 people*\n• $29,990 per person\n• Total: *$209,930 CLP*\n\n"
            "_*children pay from 6 years old_\n\n"
            "Book your time slot here 👇\nhttps://whatsapp.hotboat.cl/booking"
        ),
        "content_pt": (
            "💰 *Preços HotBoat:*\n\n"
            "👥 *2 pessoas*\n• $69.990 por pessoa\n• Total: *$139.980 CLP*\n\n"
            "👥 *3 pessoas*\n• $54.990 por pessoa\n• Total: *$164.970 CLP*\n\n"
            "👥 *4 pessoas*\n• $44.990 por pessoa\n• Total: *$179.960 CLP*\n\n"
            "👥 *5 pessoas*\n• $38.990 por pessoa\n• Total: *$194.950 CLP*\n\n"
            "👥 *6 pessoas*\n• $32.990 por pessoa\n• Total: *$197.940 CLP*\n\n"
            "👥 *7 pessoas*\n• $29.990 por pessoa\n• Total: *$209.930 CLP*\n\n"
            "_*crianças pagam a partir dos 6 anos_\n\n"
            "Reserve seu horário aqui 👇\nhttps://whatsapp.hotboat.cl/booking"
        ),
    },
    "ubicación": {
        "label": "Ubicación y cómo llegar (opción 5)",
        "content_es": (
            "📍 *Ubicación HotBoat:*\n\n"
            "📍 Estamos entre Pucón y Curarrehue, en pleno corazón de La Araucanía 🌿\n\n"
            "🗺️ Mira fotos, ubicación y más de 100 reseñas ⭐⭐⭐⭐⭐ de nuestros navegantes que vivieron la experiencia HotBoat!\n"
            "https://maps.app.goo.gl/jVYVHRzekkmFRjEH7\n\n"
            "🚗 Fácil acceso 100% pavimentado desde:\n"
            "• Pucón: 25 min\n• Villarrica centro: 50 min\n• Temuco: 2 horas\n\n"
            "¿Te gustaría reservar tu experiencia?"
        ),
        "content_en": (
            "📍 *HotBoat Location:*\n\n"
            "📍 We're between Pucón and Curarrehue, in the heart of La Araucanía 🌿\n\n"
            "🗺️ Check out photos, location and over 100 ⭐⭐⭐⭐⭐ reviews from our sailors who lived the HotBoat experience!\n"
            "https://maps.app.goo.gl/jVYVHRzekkmFRjEH7\n\n"
            "🚗 Easy access, 100% paved from:\n"
            "• Pucón: 25 min\n• Villarrica downtown: 50 min\n• Temuco: 2 hours\n\n"
            "Would you like to book your experience?"
        ),
        "content_pt": (
            "📍 *Localização HotBoat:*\n\n"
            "📍 Estamos entre Pucón e Curarrehue, no coração de La Araucanía 🌿\n\n"
            "🗺️ Veja fotos, localização e mais de 100 avaliações ⭐⭐⭐⭐⭐ dos nossos marinheiros que viveram a experiência HotBoat!\n"
            "https://maps.app.goo.gl/jVYVHRzekkmFRjEH7\n\n"
            "🚗 Acesso fácil, 100% pavimentado desde:\n"
            "• Pucón: 25 min\n• Villarrica centro: 50 min\n• Temuco: 2 horas\n\n"
            "Gostaria de reservar sua experiência?"
        ),
    },
    "clima": {
        "label": "Temporada / mejor época",
        "content_es": (
            "🌤️ *Mejor época:*\n\n"
            "Operamos principalmente en temporada alta:\n"
            "• Diciembre - Marzo (verano)\n"
            "• Octubre - Noviembre (primavera)\n\n"
            "El lago Villarrica es hermoso todo el año, pero el mejor clima es en verano.\n\n"
            "❄️ En invierno: consultar disponibilidad\n\n"
            "¿Para qué fecha te interesa?"
        ),
        "content_en": (
            "🌤️ *Best season:*\n\n"
            "We operate mainly in high season:\n"
            "• December - March (summer)\n"
            "• October - November (spring)\n\n"
            "Lake Villarrica is beautiful year-round, but the best weather is in summer.\n\n"
            "❄️ In winter: check availability\n\n"
            "What date are you interested in?"
        ),
        "content_pt": (
            "🌤️ *Melhor época:*\n\n"
            "Operamos principalmente na alta temporada:\n"
            "• Dezembro - Março (verão)\n"
            "• Outubro - Novembro (primavera)\n\n"
            "O lago Villarrica é lindo o ano todo, mas o melhor clima é no verão.\n\n"
            "❄️ No inverno: consultar disponibilidade\n\n"
            "Para qual data você está interessado?"
        ),
    },
    "cancelar": {
        "label": "Política de cancelación",
        "content_es": (
            "🔄 *Política de cancelación:*\n\n"
            "• Cancelación gratuita hasta 48h antes\n"
            "• Entre 24-48h: 50% de reembolso\n"
            "• Menos de 24h: No reembolsable\n\n"
            "⛈️ Mal clima: Reprogramamos sin costo\n\n"
            "💳 Política de pago: Se requiere anticipo del 30% para reservar\n\n"
            "¿Necesitas más información?"
        ),
        "content_en": (
            "🔄 *Cancellation policy:*\n\n"
            "• Free cancellation up to 48h before\n"
            "• Between 24-48h: 50% refund\n"
            "• Less than 24h: Non-refundable\n\n"
            "⛈️ Bad weather: We reschedule at no cost\n\n"
            "💳 Payment policy: 30% deposit required to book\n\n"
            "Need more information?"
        ),
        "content_pt": (
            "🔄 *Política de cancelamento:*\n\n"
            "• Cancelamento gratuito até 48h antes\n"
            "• Entre 24-48h: 50% de reembolso\n"
            "• Menos de 24h: Não reembolsável\n\n"
            "⛈️ Mau tempo: Reagendamos sem custo\n\n"
            "💳 Política de pagamento: É necessário 30% de antecipação para reservar\n\n"
            "Precisa de mais informações?"
        ),
    },
    "traer": {
        "label": "Qué traer al paseo",
        "content_es": (
            "🎒 *¿Qué traer?*\n\n"
            "📋 Recomendamos:\n"
            "• Protector solar ☀️\n"
            "• Lentes de sol 🕶️\n"
            "• Ropa cómoda\n"
            "• Chaqueta (puede hacer viento)\n"
            "• Cámara para fotos 📸\n"
            "• Ganas de pasarlo bien 🎉\n\n"
            "✅ Nosotros proporcionamos:\n"
            "• Chalecos salvavidas\n"
            "• Equipo de seguridad\n\n"
            "¿Lista para la aventura?"
        ),
        "content_en": (
            "🎒 *What to bring?*\n\n"
            "📋 We recommend:\n"
            "• Sunscreen ☀️\n"
            "• Sunglasses 🕶️\n"
            "• Comfortable clothes\n"
            "• Jacket (it can be windy)\n"
            "• Camera for photos 📸\n"
            "• Ready to have fun 🎉\n\n"
            "✅ We provide:\n"
            "• Life jackets\n"
            "• Safety equipment\n\n"
            "Ready for the adventure?"
        ),
        "content_pt": (
            "🎒 *O que trazer?*\n\n"
            "📋 Recomendamos:\n"
            "• Protetor solar ☀️\n"
            "• Óculos de sol 🕶️\n"
            "• Roupa confortável\n"
            "• Jaqueta (pode ventar)\n"
            "• Câmera para fotos 📸\n"
            "• Vontade de se divertir 🎉\n\n"
            "✅ Nós fornecemos:\n"
            "• Coletes salva-vidas\n"
            "• Equipamento de segurança\n\n"
            "Pronto para a aventura?"
        ),
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
    """Upsert default responses (never overwrite admin edits) and seed keywords once."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                for key, val in _DEFAULT_RESPONSES.items():
                    cur.execute("""
                        INSERT INTO bot_responses (response_key, label, content_es, content_en, content_pt)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (response_key) DO UPDATE
                        SET label      = EXCLUDED.label,
                            content_es = COALESCE(bot_responses.content_es, EXCLUDED.content_es),
                            content_en = COALESCE(bot_responses.content_en, EXCLUDED.content_en),
                            content_pt = COALESCE(bot_responses.content_pt, EXCLUDED.content_pt)
                    """, (
                        key,
                        val.get("label", key),
                        val.get("content_es"),
                        val.get("content_en"),
                        val.get("content_pt"),
                    ))

                cur.execute("SELECT COUNT(*) FROM bot_keywords")
                if cur.fetchone()[0] == 0:
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
