"""
FAQ Handler - predefined responses for common questions
"""
import logging
import re
import unicodedata
from typing import Optional

from app.bot.translations import get_text

logger = logging.getLogger(__name__)


def _strip_accents(text: str) -> str:
    """Fold accents so 'características' matches the unaccented key 'caracteristicas'."""
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("ascii")


def _lookup_all_db_keywords(message_lower: str, lang: str) -> list:
    """Return all distinct DB keyword responses that match the message.

    Deduplicates by response_key so the same answer isn't included twice
    even if multiple keywords point to it.
    """
    try:
        from app.db.connection import get_connection
        col = {"en": "content_en", "pt": "content_pt"}.get(lang, "content_es")
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT k.keyword, k.response_key, COALESCE(r.{col}, r.content_es) "
                    "FROM bot_keywords k "
                    "JOIN bot_responses r ON r.response_key = k.response_key "
                    "WHERE r.active = TRUE",
                )
                rows = cur.fetchall()
                message_norm = _strip_accents(message_lower)
                seen_keys: set = set()
                results = []
                for keyword, resp_key, content in rows:
                    if _strip_accents(keyword.lower()) in message_norm and resp_key not in seen_keys:
                        seen_keys.add(resp_key)
                        if content:
                            logger.info(f"DB keyword match: '{keyword}' → {resp_key}")
                            results.append((resp_key, content))
                return results
    except Exception as e:
        logger.warning(f"DB keyword lookup failed: {e}")
    return []


class FAQHandler:
    """Handle frequently asked questions with predefined answers"""

    def __init__(self):
        self.language = "es"  # Default language
        self.faqs = {


            # Características / Features
            "caracteristicas": """Estas son las características de la experiencia HotBoat 🚤🔥:

⚡ Motor eléctrico (silencioso y sustentable)
⏱️ Duración: 2 horas
🔥 Tú eliges la temperatura del agua (antes y durante el paseo)
🛥️ Fácil de navegar → ¡puedes manejarlo tú mismo!
🎶 Escucha tu propia música con parlante bluetooth + bolsas impermeables
🎥 Video cinematográfico de tu aventura disponible
🍹 ¡Disfruta bebestibles a bordo del HotBoat! Se mantendrán fríos en el cooler.
🧺 Opción de tablas de picoteo a bordo
🧼 Se limpia y se cambia el agua antes de cada uso, siempre impecable

¿Te gustaría reservar tu experiencia?""",
            
            "en que consiste": "caracteristicas",  # Alias
            "incluye": "caracteristicas",  # Alias
            "info": "caracteristicas",  # Alias
            "información": "caracteristicas",  # Alias


            


            # Pricing
            "precio": """💰 *Precios HotBoat:*

👥 *2 personas*
• $76.990 x persona
• Total: *$153.980*

👥 *3 personas*
• $59.990 x persona
• Total: *$179.970*

👥 *4 personas*
• $48.990 x persona
• Total: *$195.960*

👥 *5 personas*
• $42.990 x persona
• Total: *$214.950*

👥 *6 personas*
• $36.990 x persona
• Total: *$221.940*

👥 *7 personas*
• $33.990 x persona
• Total: *$237.930*

_*niños pagan desde los 6 años_

Aquí puedes reservar tu horario directo 👇
https://whatsapp.hotboat.cl/booking""",
            
            "valor": "precio",  # Alias
            "valores": "precio",  # Alias
            "cuanto cuesta": "precio",  # Alias
            


            
            # Location
            "ubicación": """📍 *Ubicación HotBoat:*

📍 Estamos entre Pucón y Curarrehue, en pleno corazón de La Araucanía 🌿

🗺️ Mira fotos, ubicación y más de 100 reseñas ⭐⭐⭐⭐⭐ de nuestros navegantes que vivieron la experiencia HotBoat!
https://maps.app.goo.gl/jVYVHRzekkmFRjEH7

🚗 Fácil acceso 100% pavimentado desde:
• Pucón: 25 min
• Villarrica centro: 50 min
• Temuco: 2 horas

¿Te gustaría reservar tu experiencia?""",
            
            "donde": "ubicación",  # Alias
            "dónde": "ubicación",  # Alias
            "donde estan": "ubicación",  # Alias
            "donde están": "ubicación",  # Alias
            
            # Duration questions → answered by características (incluye "⏱️ Duración: 2 horas")
            "cuanto tiempo": "caracteristicas",  # Alias

            # What to bring
            "traer": """🎒 *¿Qué traer?*

📋 Recomendamos:
• Protector solar ☀️
• Lentes de sol 🕶️
• Ropa cómoda
• Chaqueta (puede hacer viento)
• Cámara para fotos 📸
• Ganas de pasarlo bien 🎉

✅ Nosotros proporcionamos:
• Chalecos salvavidas
• Equipo de seguridad
• Guía experto

¿Lista para la aventura?""",
            
            # Weather/Season
            "clima": """🌤️ *Mejor época:*

Operamos principalmente en temporada alta:
• Diciembre - Marzo (verano)
• Octubre - Noviembre (primavera)

El lago Villarrica es hermoso todo el año, pero el mejor clima es en verano.

❄️ En invierno: consultar disponibilidad

¿Para qué fecha te interesa?""",
            
            "temporada": "clima",  # Alias
            
            # Contact
            "contacto": """📞 *Contáctanos:*

📱 WhatsApp: +56 9 1234 5678
📧 Email: info@hotboatchile.com
🌐 Web: https://hotboatchile.com

📍 Villarrica, Región de La Araucanía, Chile

¡Escríbenos para reservar! 🚤""",
            
            # Cancelation policy
            "cancelar": """🔄 *Política de cancelación:*

• Cancelación gratuita hasta 48h antes
• Entre 24-48h: 50% de reembolso
• Menos de 24h: No reembolsable

⛈️ Mal clima: Reprogramamos sin costo

💳 Política de pago: Se requiere anticipo del 30% para reservar

¿Necesitas más información?""",
            
            # Extras
            "extras": """✨ *Servicios Extra:*

¿Quieres agregar algo especial a tu HotBoat?

🍇 *Tablas de Picoteo*
1️⃣ Tabla grande (4 personas) - $25.000
2️⃣ Tabla pequeña (2 personas) - $20.000

🥤 *Bebidas y Jugos* (sin alcohol)
3️⃣ Jugo natural 1L (piña o naranja) - $10.000
4️⃣ Lata bebida (Coca-Cola o Fanta) - $2.900
5️⃣ Agua mineral 1,5 L - $2.500
6️⃣ Helado individual (Cookies & Cream 🍪 o Frambuesa 🍫) - $3.500

🌹 *Modo Romántico*
7️⃣ Pétalos de rosas y decoración especial - $25.000

🌙 *Decoración Nocturna Extra*
8️⃣ Velas LED decorativas - $10.000
9️⃣ Letras luminosas "Te Amo" / "Love" - $15.000
🔟 Pack completo (velas + letras) - $20.000

✨🎥 *Video personalizado*
1️⃣1️⃣ Video 15s - $30.000
1️⃣2️⃣ Video 60s - $40.000

🚐 *Transporte*
1️⃣3️⃣ Ida y vuelta desde Pucón - $50.000

🧻 *Toallas*
1️⃣4️⃣ Toalla normal - $9.000
1️⃣5️⃣ Toalla poncho - $10.000

🩴 *Otros*
1️⃣6️⃣ Chalas de ducha - $10.000
1️⃣7️⃣ Reserva FLEX (+10% - cancela/reprograma cuando quieras)

📝 *Escribe el número del extra que deseas agregar* 🚤""",
            
            "tablas": "extras",  # Alias
            "picoteo": "extras",  # Alias
            "bebestibles": "extras",  # Alias
            "alcohol": "extras",  # Alias
            "rosas": "extras",  # Alias
            "romantico": "extras",  # Alias
            "romántico": "extras",  # Alias
            "cumpleaños": "extras",  # Alias
            "cumpleanos": "extras",  # Alias
            "iluminacion": "extras",  # Alias
            "iluminación": "extras",  # Alias
            "transporte": "extras",  # Alias
            "toallas": "extras",  # Alias
            "chalas": "extras",  # Alias
            "extras disponible": "extras",  # Alias
            "servicios extra": "extras",  # Alias
            
            # Alojamientos - Nota: Las consultas de alojamiento son manejadas por ConversationManager
            # con soporte para imágenes, así que no necesitamos respuesta aquí
            # Los aliases están en _is_accommodation_query() de ConversationManager
            
            # Respuesta para llamar a Tomás
            "llamar a tomas": """👨‍✈️🌿 *Capitán Tomás al rescate*
            
¡Perfecto, grumete! He avisado al Capitán Tomás que necesita hablar contigo 👨‍✈️
            
El Capitán tomará el timón en cuanto vuelva a cubierta y se comunicará contigo pronto 📞
            
Mientras tanto, si tienes alguna consulta urgente, puedes escribirme y trataré de ayudarte lo mejor que pueda ⚓
            
¡Gracias por tu paciencia!""",
            
            "ayuda": "llamar a tomas",  # Alias
            "hablar con tomas": "llamar a tomas",  # Alias
            "capitan tomas": "llamar a tomas",  # Alias
            "capitán tomas": "llamar a tomas",  # Alias
            
            # Reseñas (ya está en ubicación, pero agregamos keyword específica)
            "reseñas": "ubicación",  # Alias - Las reseñas están en la respuesta de ubicación
            "resenas": "ubicación",  # Alias
            "reviews": "ubicación",  # Alias
            "opiniones": "ubicación",  # Alias
        }
    
    def set_language(self, language: str):
        """Set the language for responses"""
        self.language = language

    def _build_dynamic_price_response(
        self, phone: Optional[str], customer_name: Optional[str]
    ) -> Optional[str]:
        """Render the live pricing message (Precios Dinamicos config) with a
        per-client tracked link substituted for {LINK}, so the admin can see
        exactly what this specific customer did after clicking."""
        try:
            from app.booking.operator_settings import build_dynamic_price_message
            message = (build_dynamic_price_message() or {}).get("message") or ""
        except Exception as e:
            logger.warning(f"build_dynamic_price_message failed: {e}")
            return None
        if not message:
            return None

        if "{LINK}" in message:
            link_url = None
            if phone:
                try:
                    from app.booking.link_tracking_router import create_tracked_link_for_phone
                    link_url = create_tracked_link_for_phone(phone, customer_name or "").get("url")
                except Exception as e:
                    logger.warning(f"Tracked link creation failed for {phone}: {e}")
            message = message.replace("{LINK}", link_url or "https://whatsapp.hotboat.cl/booking")

        return message

    def _build_extras_from_db(self, language: str = "es") -> Optional[str]:
        """Build extras menu keeping exact structure/numbering, pulling prices from DB."""
        # Load price lookup from extras_visibility
        prices = {}
        try:
            from app.db.connection import get_connection
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT extra_name_lower, COALESCE(precio_venta, 0)
                        FROM extras_visibility
                    """)
                    for key, price in cur.fetchall():
                        prices[key.lower()] = int(price)
        except Exception:
            return None

        if not prices:
            return None

        def p(key: str, default: int) -> str:
            v = prices.get(key, default)
            return f"${v:,}".replace(",", ".")

        if language == "en":
            return f"""✨ *HotBoat Extras:*

Want to add something special to your HotBoat?

🍇 *Charcuterie Boards*
1️⃣ Large board (4 people) - {p('tabla_4_personas', 25000)} CLP
2️⃣ Small board (2 people) - {p('tabla_2_personas', 20000)} CLP

🥤 *Drinks and Juices* (non-alcoholic)
3️⃣ Natural juice 1L (pineapple or orange) - {p('jugo_natural', 10000)} CLP
4️⃣ Canned drink (Coca-Cola or Fanta) - {p('lata_bebida', 2900)} CLP
5️⃣ Mineral water 1.5 L - {p('agua_mineral', 2500)} CLP
6️⃣ Individual ice cream (Cookies & Cream 🍪 or Raspberry 🍫) - {p('helado', 3500)} CLP

🌹 *Romantic Mode*
7️⃣ Rose petals and special decoration - {p('modo_romantico', 25000)} CLP

🌙 *Extra Night Decoration*
8️⃣ Decorative LED candles - {p('velas_led', 10000)} CLP
9️⃣ Illuminated letters "Te Amo" / "Love" - {p('letras_luminosas', 15000)} CLP
🔟 Complete pack (candles + letters) - {p('pack_velas_letras', 20000)} CLP

✨🎥 *Personalized video*
1️⃣1️⃣ 15s video - {p('video_15_seg', 30000)} CLP
1️⃣2️⃣ 60s video - {p('video_1_min', 40000)} CLP

🚐 *Transportation*
1️⃣3️⃣ Round trip from Pucón - {p('transporte', 50000)} CLP

🧻 *Towels*
1️⃣4️⃣ Regular towel - {p('toalla_normal', 9000)} CLP
1️⃣5️⃣ Poncho towel - {p('toalla_poncho', 10000)} CLP

🩴 *Other*
1️⃣6️⃣ Shower sandals - {p('chalas', 10000)} CLP
1️⃣7️⃣ FLEX Booking (+10% - cancel/reschedule anytime)

📝 *Write the number of the extra you want to add* 🚤"""

        elif language == "pt":
            return f"""✨ *Extras HotBoat:*

Quer adicionar algo especial ao seu HotBoat?

🍇 *Tábuas de Frios*
1️⃣ Tábua grande (4 pessoas) - {p('tabla_4_personas', 25000)} CLP
2️⃣ Tábua pequena (2 pessoas) - {p('tabla_2_personas', 20000)} CLP

🥤 *Bebidas e Sucos* (sem álcool)
3️⃣ Suco natural 1L (abacaxi ou laranja) - {p('jugo_natural', 10000)} CLP
4️⃣ Lata de refrigerante (Coca-Cola ou Fanta) - {p('lata_bebida', 2900)} CLP
5️⃣ Água mineral 1,5 L - {p('agua_mineral', 2500)} CLP
6️⃣ Sorvete individual (Cookies & Cream 🍪 ou Framboesa 🍫) - {p('helado', 3500)} CLP

🌹 *Modo Romântico*
7️⃣ Pétalas de rosas e decoração especial - {p('modo_romantico', 25000)} CLP

🌙 *Decoração Noturna Extra*
8️⃣ Velas LED decorativas - {p('velas_led', 10000)} CLP
9️⃣ Letras luminosas "Te Amo" / "Love" - {p('letras_luminosas', 15000)} CLP
🔟 Pack completo (velas + letras) - {p('pack_velas_letras', 20000)} CLP

✨🎥 *Vídeo personalizado*
1️⃣1️⃣ Vídeo 15s - {p('video_15_seg', 30000)} CLP
1️⃣2️⃣ Vídeo 60s - {p('video_1_min', 40000)} CLP

🚐 *Transporte*
1️⃣3️⃣ Ida e volta de Pucón - {p('transporte', 50000)} CLP

🧻 *Toalhas*
1️⃣4️⃣ Toalha normal - {p('toalla_normal', 9000)} CLP
1️⃣5️⃣ Toalha poncho - {p('toalla_poncho', 10000)} CLP

🩴 *Outros*
1️⃣6️⃣ Chinelos de banho - {p('chalas', 10000)} CLP
1️⃣7️⃣ Reserva FLEX (+10% - cancele/remarque quando quiser)

📝 *Escreva o número do extra que deseja adicionar* 🚤"""

        else:  # es
            return f"""✨ *Extras HotBoat:*

¿Quieres agregar algo especial a tu HotBoat?

🍇 *Tablas de Picoteo*
1️⃣ Tabla grande (4 personas) - {p('tabla_4_personas', 25000)}
2️⃣ Tabla pequeña (2 personas) - {p('tabla_2_personas', 20000)}

🥤 *Bebidas y Jugos* (sin alcohol)
3️⃣ Jugo natural 1L (piña o naranja) - {p('jugo_natural', 10000)}
4️⃣ Lata bebida (Coca-Cola o Fanta) - {p('lata_bebida', 2900)}
5️⃣ Agua mineral 1,5 L - {p('agua_mineral', 2500)}
6️⃣ Helado individual (Cookies & Cream 🍪 o Frambuesa 🍫) - {p('helado', 3500)}

🌹 *Modo Romántico*
7️⃣ Pétalos de rosas y decoración especial - {p('modo_romantico', 25000)}

🌙 *Decoración Nocturna Extra*
8️⃣ Velas LED decorativas - {p('velas_led', 10000)}
9️⃣ Letras luminosas "Te Amo" / "Love" - {p('letras_luminosas', 15000)}
🔟 Pack completo (velas + letras) - {p('pack_velas_letras', 20000)}

✨🎥 *Video personalizado*
1️⃣1️⃣ Video 15s - {p('video_15_seg', 30000)}
1️⃣2️⃣ Video 60s - {p('video_1_min', 40000)}

🚐 *Transporte*
1️⃣3️⃣ Ida y vuelta desde Pucón - {p('transporte', 50000)}

🧻 *Toallas*
1️⃣4️⃣ Toalla normal - {p('toalla_normal', 9000)}
1️⃣5️⃣ Toalla poncho - {p('toalla_poncho', 10000)}

🩴 *Otros*
1️⃣6️⃣ Chalas de ducha - {p('chalas', 10000)}
1️⃣7️⃣ Reserva FLEX (+10% - cancela/reprograma cuando quieras)

📝 *Escribe el número del extra que deseas agregar* 🚤"""

    def get_response(
        self,
        message: str,
        language: str = None,
        *,
        phone: Optional[str] = None,
        customer_name: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get FAQ response if message matches a question

        Args:
            message: User's message
            language: Language code (es, en, pt). If None, uses default
            phone: Sender's WhatsApp number — used to mint a per-client
                tracked link when the pricing answer is triggered.
            customer_name: Sender's contact name, tied to the tracked link.

        Returns:
            FAQ response or None
        """
        lang = language or self.language
        message_lower = message.lower().strip()
        message_norm = _strip_accents(message_lower)

        collected: list = []
        seen_keys: set = set()

        # DB-configured keywords — collect ALL distinct matches (highest priority)
        db_hits = _lookup_all_db_keywords(message_lower, lang)
        for resp_key, content in db_hits:
            seen_keys.add(resp_key)
            if resp_key == "precio":
                collected.append(self._build_dynamic_price_response(phone, customer_name) or content)
            else:
                collected.append(content)
        # NOTE: we do NOT bail out here — hardcoded FAQ may cover additional topics
        # not present in the DB (e.g. "precio" when "horarios" DB keyword also fired).

        # Map FAQ keys to translation keys
        faq_to_translation = {
            "caracteristicas": "features",
            "precio": "pricing",
            "ubicación": "location",
            "extras": "extras_menu",
            "llamar a tomas": "call_captain",
            "traer": "what_to_bring",
            "clima": "weather",
            "contacto": "contact_info",
            "cancelar": "cancellation",
        }

        # Collect ALL distinct keyword matches from hardcoded FAQ.
        # Use accent-stripped comparison so "características" matches key "caracteristicas".
        for keyword, response in self.faqs.items():
            # "info" must be a whole word to avoid false positives with "información"
            if keyword == "info":
                matched = re.search(r"\binfo\b", message_norm) is not None
            else:
                matched = _strip_accents(keyword) in message_norm
            if not matched:
                continue

            # Resolve alias to actual keyword
            actual_keyword = keyword
            if isinstance(response, str) and response in self.faqs:
                actual_keyword = response

            # Deduplicate: skip if we already have a response for this key
            if actual_keyword in seen_keys:
                continue
            seen_keys.add(actual_keyword)

            # Build response text
            if actual_keyword in faq_to_translation:
                translation_key = faq_to_translation[actual_keyword]
                logger.info(f"FAQ match: '{keyword}' → {translation_key}")
                # Precio siempre usa el mensaje dinámico (Precios Dinamicos en el
                # admin) con un link de seguimiento propio — tiene prioridad sobre
                # lo configurado en el panel del chatbot y sobre el texto fijo.
                if actual_keyword == "precio":
                    dynamic = self._build_dynamic_price_response(phone, customer_name)
                    if dynamic:
                        collected.append(dynamic)
                        continue
                # Prioridad 1: lo que esté configurado en el panel del chatbot
                # (tabla bot_responses) para CUALQUIER respuesta del menú.
                # NADA hardcodeado si hay algo configurado.
                configured = None
                try:
                    from app.booking.bot_config_router import get_bot_response as _get_cfg
                    configured = _get_cfg(actual_keyword, lang)
                except Exception:
                    configured = None
                if configured and configured.strip():
                    collected.append(configured)
                    continue
                # Prioridad 2: extras → armar desde el catálogo (precios de BD)
                if actual_keyword == "extras":
                    dynamic = self._build_extras_from_db(lang)
                    if dynamic:
                        collected.append(dynamic)
                        continue
                # Prioridad 3 (fallback): texto por defecto (translations.py)
                collected.append(get_text(translation_key, lang))
            else:
                actual_response = self.faqs[actual_keyword] if isinstance(response, str) and response in self.faqs else response
                logger.info(f"FAQ match: '{keyword}' (no translation)")
                collected.append(actual_response)

        if not collected:
            return None
        return "\n\n".join(collected)
    
    def is_menu_number(self, message: str) -> Optional[int]:
        """
        Check if message is a menu number selection (1-9)

        Returns:
            Number selected (1-9) or None
        """
        message_stripped = message.strip()

        # Check for emoji numbers
        menu_numbers = {
            "1️⃣": 1,
            "2️⃣": 2,
            "3️⃣": 3,
            "4️⃣": 4,
            "5️⃣": 5,
            "6️⃣": 6,
            "7️⃣": 7,
            "8️⃣": 8,
            "9️⃣": 9,
        }

        # Check exact match with emoji
        if message_stripped in menu_numbers:
            return menu_numbers[message_stripped]

        # Check for plain numbers (just the digit, possibly with spaces)
        message_lower = message.lower().strip()
        if message_lower in ["1", "2", "3", "4", "5", "6", "7", "8", "9"]:
            return int(message_lower)

        # Check if message starts with a number (e.g., "1 disponibilidad")
        first_char = message_lower[0] if message_lower else ""
        if first_char in ["1", "2", "3", "4", "5", "6", "7", "8", "9"]:
            try:
                num = int(first_char)
                if 1 <= num <= 9:
                    return num
            except ValueError:
                pass

        return None
    
    def is_multiple_menu_numbers(self, message: str) -> Optional[list]:
        """
        Check if message contains multiple menu number selections (e.g., "1,2,3" or "1 2 3")
        
        Args:
            message: User's message
        
        Returns:
            List of numbers selected (1-6) or None if not multiple numbers
        """
        import re
        
        message_stripped = message.strip()
        
        # Extract all numbers from 1-6 in the message
        numbers = re.findall(r'[1-6]', message_stripped)
        
        # Convert to integers and remove duplicates while preserving order
        seen = set()
        unique_numbers = []
        for num_str in numbers:
            num = int(num_str)
            if num not in seen:
                seen.add(num)
                unique_numbers.append(num)
        
        # Check if we have at least 2 numbers and the message doesn't contain too much extra text
        # This prevents matching things like "tengo 2 personas y quiero el 3 de enero"
        # We allow: numbers, spaces, commas, "y", "and", "e"
        if len(unique_numbers) >= 2:
            # Remove numbers and allowed separators to check for extra text
            cleaned = re.sub(r'[1-6\s,yande]+', '', message_stripped.lower())
            # If there's minimal extra text (less than 3 chars), it's likely a menu selection
            if len(cleaned) <= 2:
                return unique_numbers
        
        return None








