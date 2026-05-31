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
    menu_option: Optional[int] = None
    active: Optional[bool] = None
    button_label: Optional[str] = None
    show_in_menu: Optional[bool] = None
    menu_description: Optional[str] = None


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
                        response_key     TEXT PRIMARY KEY,
                        label            TEXT NOT NULL DEFAULT '',
                        content_es       TEXT,
                        content_en       TEXT,
                        content_pt       TEXT,
                        menu_option      INT,
                        active           BOOLEAN NOT NULL DEFAULT TRUE,
                        button_label     TEXT,
                        show_in_menu     BOOLEAN NOT NULL DEFAULT FALSE,
                        menu_description TEXT,
                        updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                # Add columns that may be missing in existing tables
                for col_def in [
                    "menu_option      INT",
                    "active           BOOLEAN NOT NULL DEFAULT TRUE",
                    "button_label     TEXT",
                    "show_in_menu     BOOLEAN NOT NULL DEFAULT FALSE",
                    "menu_description TEXT",
                ]:
                    try:
                        cur.execute(f"ALTER TABLE bot_responses ADD COLUMN IF NOT EXISTS {col_def}")
                    except Exception:
                        pass
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
                    SELECT response_key, label, content_es, content_en, content_pt,
                           menu_option, active, button_label,
                           show_in_menu, menu_description, updated_at
                    FROM bot_responses ORDER BY
                        CASE WHEN menu_option IS NULL THEN 9999 ELSE menu_option END,
                        response_key
                """)
                rows = cur.fetchall()
        return {"responses": [
            {
                "response_key": r[0],
                "label": r[1],
                "content_es": r[2],
                "content_en": r[3],
                "content_pt": r[4],
                "menu_option": r[5],
                "active": r[6],
                "button_label": r[7],
                "show_in_menu": r[8],
                "menu_description": r[9],
                "updated_at": r[10].isoformat() if r[10] else None,
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
                    INSERT INTO bot_responses
                        (response_key, label, content_es, content_en, content_pt,
                         menu_option, active, button_label, show_in_menu, menu_description)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (response_key) DO UPDATE
                    SET content_es       = COALESCE(EXCLUDED.content_es,   bot_responses.content_es),
                        content_en       = COALESCE(EXCLUDED.content_en,   bot_responses.content_en),
                        content_pt       = COALESCE(EXCLUDED.content_pt,   bot_responses.content_pt),
                        menu_option      = EXCLUDED.menu_option,
                        active           = EXCLUDED.active,
                        button_label     = EXCLUDED.button_label,
                        show_in_menu     = EXCLUDED.show_in_menu,
                        menu_description = EXCLUDED.menu_description,
                        updated_at       = NOW()
                """, (
                    key, key,
                    data.content_es, data.content_en, data.content_pt,
                    data.menu_option,
                    data.active if data.active is not None else True,
                    data.button_label,
                    data.show_in_menu if data.show_in_menu is not None else False,
                    data.menu_description,
                ))
                conn.commit()
        return {"status": "ok", "key": key}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Quick-reply list (used by chat UI) ────────────────────────────────────────

@bot_config_router.get("/quick-replies")
async def get_quick_replies():
    """Return active quick-reply buttons sorted by menu_option."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT menu_option, button_label, response_key, label
                    FROM bot_responses
                    WHERE menu_option IS NOT NULL AND active = TRUE
                    ORDER BY menu_option
                """)
                rows = cur.fetchall()
        return {"buttons": [
            {
                "menu_option": r[0],
                "button_label": r[1] or r[3] or r[2],
                "response_key": r[2],
            }
            for r in rows
        ]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Shared helper (importable by other modules) ───────────────────────────────

def get_bot_response(key: str, lang: str = "es") -> Optional[str]:
    """Return bot response content from DB for the given key and language, or None."""
    try:
        col = {"es": "content_es", "en": "content_en", "pt": "content_pt"}.get(lang, "content_es")
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT {col}, content_es FROM bot_responses WHERE response_key = %s",
                    (key,)
                )
                row = cur.fetchone()
        if row:
            return row[0] or row[1]
    except Exception:
        pass
    return None


_EMOJI_NUMS = {
    0: "0️⃣", 1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣",
    5: "5️⃣", 6: "6️⃣", 7: "7️⃣", 8: "8️⃣", 9: "9️⃣",
}


_DEFAULT_HEADERS = {
    "es": "🥬 ¡Ahoy, grumete! ⚓\n\nSoy *Popeye el Marino*, cabo segundo del *HotBoat Chile* 🚤🔥\n\nPuedes preguntarme por:",
    "en": "🥬 Ahoy, sailor! ⚓\n\nI'm *Popeye the Sailor*, second mate of *HotBoat Chile* 🚤🔥\n\nYou can ask me about:",
    "pt": "🥬 Ahoy, marujo! ⚓\n\nEu sou *Popeye o Marinheiro*, segundo imediato do *HotBoat Chile* 🚤🔥\n\nVocê pode me perguntar sobre:",
}

_DEFAULT_FOOTERS = {
    "es": "Si prefieres hablar con el *Capitán Tomás*, escribe *\"Llamar a Tomás\"*, *\"Ayuda\"*, o simplemente *7️⃣* 👨‍✈️🌿\n\n¿Listo para zarpar, grumete? ⛵\n\n*¿Qué número eliges?*",
    "en": "If you'd rather talk to *Captain Tomás*, write *\"Call Tomás\"*, *\"Help\"*, or simply *7️⃣* 👨‍✈️🌿\n\nReady to set sail, sailor? ⛵\n\n*Which number do you choose?*",
    "pt": "Se preferir falar com o *Capitão Tomás*, escreva *\"Ligar para Tomás\"*, *\"Ajuda\"*, ou simplesmente *7️⃣* 👨‍✈️🌿\n\nPronto para zarpar, marujo? ⛵\n\n*Qual número você escolhe?*",
}


def build_main_menu_text(lang: str = "es") -> Optional[str]:
    """Auto-build the welcome menu from show_in_menu=true items."""
    try:
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT menu_option, menu_description
                    FROM bot_responses
                    WHERE show_in_menu = TRUE AND active = TRUE
                      AND menu_option IS NOT NULL AND menu_description IS NOT NULL
                    ORDER BY menu_option
                """)
                items = cur.fetchall()
        if not items:
            return None
        header = get_bot_response("menu_header", lang) or _DEFAULT_HEADERS.get(lang, _DEFAULT_HEADERS["es"])
        footer = get_bot_response("menu_footer", lang) or _DEFAULT_FOOTERS.get(lang, _DEFAULT_FOOTERS["es"])
        lines = [header, ""]
        for (opt, desc) in items:
            emoji = _EMOJI_NUMS.get(opt, f"{opt}.")
            lines.append(f"{emoji} *{desc}*")
            lines.append("")
        lines.append(footer)
        text = "\n".join(lines)
        if lang == "es":
            text += "\n\n_🌍 ¿Hablas otro idioma? Escribe *\"inglés\"* o *\"português\"*_"
        return text
    except Exception as e:
        logger.warning("build_main_menu_text failed: %s", e)
        return None


@bot_config_router.get("/build-menu")
async def build_menu_preview(lang: str = "es"):
    """Return the auto-generated welcome menu text (preview, does not save)."""
    text = build_main_menu_text(lang)
    if text is None:
        raise HTTPException(status_code=404, detail="No show_in_menu items found")
    return {"text": text, "lang": lang}


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
        "menu_option": 0,
        "button_label": "👋 Tomás",
        "content_es": "¡Hola {name}! 👋\nSoy Capitán HotBoat 🚤\n¿En qué puedo ayudarte hoy?",
    },
    "menu_header": {
        "label": "Encabezado del menú de bienvenida",
        "content_es": "🥬 ¡Ahoy, grumete! ⚓\n\nSoy *Popeye el Marino*, cabo segundo del *HotBoat Chile* 🚤🔥\n\nPuedes preguntarme por:",
        "content_en": "🥬 Ahoy, sailor! ⚓\n\nI'm *Popeye the Sailor*, second mate of *HotBoat Chile* 🚤🔥\n\nYou can ask me about:",
        "content_pt": "🥬 Ahoy, marujo! ⚓\n\nEu sou *Popeye o Marinheiro*, segundo imediato do *HotBoat Chile* 🚤🔥\n\nVocê pode me perguntar sobre:",
    },
    "menu_footer": {
        "label": "Pie del menú de bienvenida",
        "content_es": "Si prefieres hablar con el *Capitán Tomás*, escribe *\"Llamar a Tomás\"*, *\"Ayuda\"*, o simplemente *7️⃣* 👨‍✈️🌿\n\n¿Listo para zarpar, grumete? ⛵\n\n*¿Qué número eliges?*",
        "content_en": "If you'd rather talk to *Captain Tomás*, write *\"Call Tomás\"*, *\"Help\"*, or simply *7️⃣* 👨‍✈️🌿\n\nReady to set sail, sailor? ⛵\n\n*Which number do you choose?*",
        "content_pt": "Se preferir falar com o *Capitão Tomás*, escreva *\"Ligar para Tomás\"*, *\"Ajuda\"*, ou simplesmente *7️⃣* 👨‍✈️🌿\n\nPronto para zarpar, marujo? ⛵\n\n*Qual número você escolhe?*",
    },
    "main_menu": {
        "label": "Mensaje de bienvenida (menú completo — referencia)",
        "content_es": (
            "🥬 ¡Ahoy, grumete! ⚓\n\n"
            "Soy *Popeye el Marino*, cabo segundo del *HotBoat Chile* 🚤🔥\n\n"
            "Puedes preguntarme por:\n\n"
            "1️⃣ *Disponibilidad y horarios HotBoat*\n\n"
            "2️⃣ *Precios por persona HotBoat*\n\n"
            "3️⃣ *Características Experiencia HotBoat*\n\n"
            "4️⃣ *Extras HotBoat (toallas, videos, tablas, etc.)*\n\n"
            "5️⃣ *Ubicación y Reseñas HotBoat*\n\n"
            "6️⃣ *Alojamientos Pucón (Domos · Cabañas · Hostal)*\n\n"
            "Si prefieres hablar con el *Capitán Tomás*, escribe *\"Llamar a Tomás\"*, *\"Ayuda\"*, o simplemente *7️⃣* 👨‍✈️🌿\n\n"
            "¿Listo para zarpar, grumete? ⛵\n\n"
            "*¿Qué número eliges?*"
        ),
        "content_en": (
            "🥬 Ahoy, sailor! ⚓\n\n"
            "I'm *Popeye the Sailor*, second mate of *HotBoat Chile* 🚤🔥\n\n"
            "You can ask me about:\n\n"
            "1️⃣ *HotBoat Availability and schedules*\n\n"
            "2️⃣ *HotBoat Prices per person*\n\n"
            "3️⃣ *HotBoat Experience Features*\n\n"
            "4️⃣ *HotBoat Extras (towels, videos, boards, etc.)*\n\n"
            "5️⃣ *HotBoat Location and reviews*\n\n"
            "6️⃣ *Pucón Accommodations (Domes · Cabins · Hostel)*\n\n"
            "If you'd rather talk to *Captain Tomás*, write *\"Call Tomás\"*, *\"Help\"*, or simply *7️⃣* 👨‍✈️🌿\n\n"
            "Ready to set sail, sailor? ⛵\n\n"
            "*Which number do you choose?*"
        ),
        "content_pt": (
            "🥬 Ahoy, marujo! ⚓\n\n"
            "Eu sou *Popeye o Marinheiro*, segundo imediato do *HotBoat Chile* 🚤🔥\n\n"
            "Você pode me perguntar sobre:\n\n"
            "1️⃣ *Disponibilidade e horários HotBoat*\n\n"
            "2️⃣ *Preços por pessoa HotBoat*\n\n"
            "3️⃣ *Características Experiência HotBoat*\n\n"
            "4️⃣ *Extras HotBoat (toalhas, vídeos, tábuas, etc.)*\n\n"
            "5️⃣ *Localização e avaliações HotBoat*\n\n"
            "6️⃣ *Hospedagens Pucón (Domos · Cabanas · Hostel)*\n\n"
            "Se preferir falar com o *Capitão Tomás*, escreva *\"Ligar para Tomás\"*, *\"Ajuda\"*, ou simplesmente *7️⃣* 👨‍✈️🌿\n\n"
            "Pronto para zarpar, marujo? ⛵\n\n"
            "*Qual número você escolhe?*"
        ),
    },
    "reservar": {
        "label": "Disponibilidad y horarios (opción 1)",
        "menu_option": 1,
        "button_label": "📅 Reservar",
        "show_in_menu": True,
        "menu_description": "Disponibilidad y horarios HotBoat",
        "content_es": (
            "📅 *¿Para qué fecha te gustaría reservar?*\n\n"
            "Escríbeme la fecha, por ejemplo:\n"
            "• \"15 de enero\"\n"
            "• \"martes 23\"\n"
            "• \"próximo sábado\"\n\n"
            "¿Qué fecha prefieres, grumete? ⚓\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 *Tip:* Escribe *\"menú\"* si quieres volver al menú principal"
        ),
        "content_en": (
            "📅 *What date would you like to book?*\n\n"
            "Write me the date, for example:\n"
            "• \"January 15\"\n"
            "• \"Tuesday 23rd\"\n"
            "• \"next Saturday\"\n\n"
            "What date do you prefer, sailor? ⚓\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 *Tip:* Write *\"menu\"* if you want to go back to the main menu"
        ),
        "content_pt": (
            "📅 *Para qual data você gostaria de reservar?*\n\n"
            "Escreva-me a data, por exemplo:\n"
            "• \"15 de janeiro\"\n"
            "• \"terça-feira 23\"\n"
            "• \"próximo sábado\"\n\n"
            "Que data você prefere, marujo? ⚓\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "💡 *Dica:* Escreva *\"menu\"* se quiser voltar ao menu principal"
        ),
    },
    "precio": {
        "label": "Precios por persona (opción 2)",
        "menu_option": 2,
        "button_label": "💰 Precio",
        "show_in_menu": True,
        "menu_description": "Precios por persona HotBoat",
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
    "caracteristicas": {
        "label": "Características del HotBoat (opción 3)",
        "menu_option": 3,
        "button_label": "🚤 HotBoat",
        "show_in_menu": True,
        "menu_description": "Características Experiencia HotBoat",
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
    "extras": {
        "label": "Extras y promociones (opción 4)",
        "menu_option": 4,
        "button_label": "🎁 Extras",
        "show_in_menu": True,
        "menu_description": "Extras HotBoat (toallas, videos, tablas, etc.)",
        "content_es": (
            "✨ *Extras HotBoat:*\n\n"
            "¿Quieres agregar algo especial a tu HotBoat?\n\n"
            "🍇 *Tablas de Picoteo*\n"
            "1️⃣ Tabla grande (4 personas) - $25.000\n"
            "2️⃣ Tabla pequeña (2 personas) - $20.000\n\n"
            "🥤 *Bebidas y Jugos* (sin alcohol)\n"
            "3️⃣ Jugo natural 1L (piña o naranja) - $10.000\n"
            "4️⃣ Lata bebida (Coca-Cola o Fanta) - $2.900\n"
            "5️⃣ Agua mineral 1,5 L - $2.500\n"
            "6️⃣ Helado individual (Cookies & Cream 🍪 o Frambuesa 🍫) - $3.500\n\n"
            "🌹 *Modo Romántico*\n"
            "7️⃣ Pétalos de rosas y decoración especial - $25.000\n\n"
            "🌙 *Decoración Nocturna Extra*\n"
            "8️⃣ Velas LED decorativas - $10.000\n"
            "9️⃣ Letras luminosas \"Te Amo\" / \"Love\" - $15.000\n"
            "🔟 Pack completo (velas + letras) - $20.000\n\n"
            "✨🎥 *Video personalizado*\n"
            "1️⃣1️⃣ Video 15s - $30.000\n"
            "1️⃣2️⃣ Video 60s - $40.000\n\n"
            "🚐 *Transporte*\n"
            "1️⃣3️⃣ Ida y vuelta desde Pucón - $50.000\n\n"
            "🧻 *Toallas*\n"
            "1️⃣4️⃣ Toalla normal - $9.000\n"
            "1️⃣5️⃣ Toalla poncho - $10.000\n\n"
            "🩴 *Otros*\n"
            "1️⃣6️⃣ Chalas de ducha - $10.000\n"
            "1️⃣7️⃣ Reserva FLEX (+10% - cancela/reprograma cuando quieras)\n\n"
            "📝 *Escribe el número del extra que deseas agregar* 🚤"
        ),
        "content_en": (
            "✨ *HotBoat Extras:*\n\n"
            "Want to add something special to your HotBoat?\n\n"
            "🍇 *Charcuterie Boards*\n"
            "1️⃣ Large board (4 people) - $25,000 CLP\n"
            "2️⃣ Small board (2 people) - $20,000 CLP\n\n"
            "🥤 *Drinks and Juices* (non-alcoholic)\n"
            "3️⃣ Natural juice 1L (pineapple or orange) - $10,000 CLP\n"
            "4️⃣ Canned drink (Coca-Cola or Fanta) - $2,900 CLP\n"
            "5️⃣ Mineral water 1.5 L - $2,500 CLP\n"
            "6️⃣ Individual ice cream (Cookies & Cream 🍪 or Raspberry 🍫) - $3,500 CLP\n\n"
            "🌹 *Romantic Mode*\n"
            "7️⃣ Rose petals and special decoration - $25,000 CLP\n\n"
            "🌙 *Extra Night Decoration*\n"
            "8️⃣ Decorative LED candles - $10,000 CLP\n"
            "9️⃣ Illuminated letters \"Te Amo\" / \"Love\" - $15,000 CLP\n"
            "🔟 Complete pack (candles + letters) - $20,000 CLP\n\n"
            "✨🎥 *Personalized video*\n"
            "1️⃣1️⃣ 15s video - $30,000 CLP\n"
            "1️⃣2️⃣ 60s video - $40,000 CLP\n\n"
            "🚐 *Transportation*\n"
            "1️⃣3️⃣ Round trip from Pucón - $50,000 CLP\n\n"
            "🧻 *Towels*\n"
            "1️⃣4️⃣ Regular towel - $9,000 CLP\n"
            "1️⃣5️⃣ Poncho towel - $10,000 CLP\n\n"
            "🩴 *Other*\n"
            "1️⃣6️⃣ Shower flip-flops - $10,000 CLP\n"
            "1️⃣7️⃣ FLEX Reservation (+10% - cancel/reschedule anytime)\n\n"
            "📝 *Type the number of the extra you want to add* 🚤"
        ),
        "content_pt": (
            "✨ *Extras HotBoat:*\n\n"
            "Quer adicionar algo especial ao seu HotBoat?\n\n"
            "🍇 *Tábuas de Frios*\n"
            "1️⃣ Tábua grande (4 pessoas) - $25.000 CLP\n"
            "2️⃣ Tábua pequena (2 pessoas) - $20.000 CLP\n\n"
            "🥤 *Bebidas e Sucos* (sem álcool)\n"
            "3️⃣ Suco natural 1L (abacaxi ou laranja) - $10.000 CLP\n"
            "4️⃣ Lata de bebida (Coca-Cola ou Fanta) - $2.900 CLP\n"
            "5️⃣ Água mineral 1,5 L - $2.500 CLP\n"
            "6️⃣ Sorvete individual (Cookies & Cream 🍪 ou Framboesa 🍫) - $3.500 CLP\n\n"
            "🌹 *Modo Romântico*\n"
            "7️⃣ Pétalas de rosas e decoração especial - $25.000 CLP\n\n"
            "🌙 *Decoração Noturna Extra*\n"
            "8️⃣ Velas LED decorativas - $10.000 CLP\n"
            "9️⃣ Letras iluminadas \"Te Amo\" / \"Love\" - $15.000 CLP\n"
            "🔟 Pacote completo (velas + letras) - $20.000 CLP\n\n"
            "✨🎥 *Vídeo personalizado*\n"
            "1️⃣1️⃣ Vídeo 15s - $30.000 CLP\n"
            "1️⃣2️⃣ Vídeo 60s - $40.000 CLP\n\n"
            "🚐 *Transporte*\n"
            "1️⃣3️⃣ Ida e volta desde Pucón - $50.000 CLP\n\n"
            "🧻 *Toalhas*\n"
            "1️⃣4️⃣ Toalha normal - $9.000 CLP\n"
            "1️⃣5️⃣ Toalha poncho - $10.000 CLP\n\n"
            "🩴 *Outros*\n"
            "1️⃣6️⃣ Chinelos de banho - $10.000 CLP\n"
            "1️⃣7️⃣ Reserva FLEX (+10% - cancele/reagende quando quiser)\n\n"
            "📝 *Digite o número do extra que deseja adicionar* 🚤"
        ),
    },
    "ubicación": {
        "label": "Ubicación y cómo llegar (opción 5)",
        "menu_option": 5,
        "button_label": "📍 Ubicación",
        "show_in_menu": True,
        "menu_description": "Ubicación y Reseñas HotBoat",
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
    "packs": {
        "label": "Packs Completos (opción 8)",
        "menu_option": 8,
        "button_label": "📦 Packs",
    },
    "alojamientos": {
        "label": "Solo Alojamientos (opción 9)",
        "menu_option": 9,
        "button_label": "🏠 Alojam.",
        "show_in_menu": True,
        "menu_description": "Alojamientos Pucón (Domos · Cabañas · Hostal)",
    },
    "bebestibles": {
        "label": "Bebestibles / bebidas (opción 🍷)",
        "menu_option": 10,
        "button_label": "🍷 Bebidas",
        "content_es": (
            "🍷 *Opciones para celebrar* (solo adultos)\n\n"
            "$6.000 → Cerveza artesanal 330ml\n"
            "$6.000 → Cerveza Corona 330ml\n"
            "$15.000 → Vino tinto o blanco (botella)\n"
            "$26.000 → Champagne\n"
            "$20.000 → Pack 4 cervezas artesanales"
        ),
    },
    "comida": {
        "label": "Política de comida (opción 🍽️)",
        "menu_option": 11,
        "button_label": "🍽️ Comida",
        "content_es": "Pueden traer lo que quieran para comer o tomar 🍕🥗\n---\no pueden pedir aquí 🙂",
    },
    "lluvia": {
        "label": "Respuesta sobre lluvia (opción 🌧️)",
        "menu_option": 12,
        "button_label": "🌧️ Lluvia",
        "content_es": "Con lluvia la experiencia es aún mejor ☔🔥\n---\n¡El HotBoat es una tina de agua caliente! La lluvia se siente increíble desde adentro 🌧️🛁\n---\nTe pasamos sombreros para que no te llegue el agua en la cara todo el tiempo 🎩😄",
    },
    "niños": {
        "label": "Info sobre niños (opción 👶)",
        "menu_option": 13,
        "button_label": "👶 Niños",
        "content_es": "Sí!, los niños lo pasan increíble 🎉\n---\nPagan desde los 6 años, a los menores no los consideres en el número de personas de la reserva 👍",
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
                        INSERT INTO bot_responses
                            (response_key, label, content_es, content_en, content_pt,
                             menu_option, active, button_label, show_in_menu, menu_description)
                        VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s, %s, %s)
                        ON CONFLICT (response_key) DO UPDATE
                        SET label            = EXCLUDED.label,
                            content_es       = COALESCE(bot_responses.content_es, EXCLUDED.content_es),
                            content_en       = COALESCE(bot_responses.content_en, EXCLUDED.content_en),
                            content_pt       = COALESCE(bot_responses.content_pt, EXCLUDED.content_pt),
                            menu_option      = COALESCE(bot_responses.menu_option, EXCLUDED.menu_option),
                            button_label     = COALESCE(bot_responses.button_label, EXCLUDED.button_label),
                            show_in_menu     = COALESCE(bot_responses.show_in_menu, EXCLUDED.show_in_menu),
                            menu_description = COALESCE(bot_responses.menu_description, EXCLUDED.menu_description)
                    """, (
                        key,
                        val.get("label", key),
                        val.get("content_es"),
                        val.get("content_en"),
                        val.get("content_pt"),
                        val.get("menu_option"),
                        val.get("button_label"),
                        val.get("show_in_menu", False),
                        val.get("menu_description"),
                    ))

                # Fix rows that still have menu_description=NULL (never customized):
                # fill in show_in_menu and menu_description from seed defaults.
                for key, val in _DEFAULT_RESPONSES.items():
                    if val.get("show_in_menu") and val.get("menu_description"):
                        cur.execute("""
                            UPDATE bot_responses
                            SET show_in_menu = TRUE, menu_description = %s
                            WHERE response_key = %s AND menu_description IS NULL
                        """, (val["menu_description"], key))

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
