"""
FAQ Handler - predefined responses for common questions
"""
import logging
from typing import Optional

from app.bot.translations import get_text

logger = logging.getLogger(__name__)


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
🧼 Se limpia antes de cada uso, siempre impecable

¿Te gustaría reservar tu experiencia?""",
            
            "en que consiste": "caracteristicas",  # Alias
            "incluye": "caracteristicas",  # Alias
            "info": "caracteristicas",  # Alias
            "información": "caracteristicas",  # Alias
            "dura": "caracteristicas",  # Alias
            "duración": "caracteristicas",  # Alias
            "tiempo": "caracteristicas",  # Alias


            


            # Pricing
            "precio": """💰 *Precios HotBoat:*

👥 *2 personas*
• $69.990 x persona
• Total: *$139.980*

👥 *3 personas*
• $54.990 x persona
• Total: *$164.970*

👥 *4 personas*
• $44.990 x persona
• Total: *$179.960*

👥 *5 personas*
• $38.990 x persona
• Total: *$194.950*

👥 *6 personas*
• $32.990 x persona
• Total: *$197.940*

👥 *7 personas*
• $29.990 x persona
• Total: *$209.930*

_*niños pagan desde los 6 años_

Aquí puedes reservar tu horario directo 👇
https://hotboatchile.com/es/book-hotboat/""",
            
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
            
            # Duration
            "duración": """⏱️ *Duración del tour:*

El tour Hot Boat tiene una duración aproximada de:
• 1.5 a 2 horas en el lago

Incluye:
• Briefing de seguridad
• Recorrido por puntos destacados
• Tiempo para fotos
• Experiencia completa

¿Alguna otra duda?""",
            
            "cuanto tiempo": "duración",  # Alias
            
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
    
    def get_response(self, message: str, language: str = None) -> Optional[str]:
        """
        Get FAQ response if message matches a question
        
        Args:
            message: User's message
            language: Language code (es, en, pt). If None, uses default
        
        Returns:
            FAQ response or None
        """
        lang = language or self.language
        message_lower = message.lower().strip()
        
        # Map FAQ keys to translation keys
        faq_to_translation = {
            "caracteristicas": "features",
            "precio": "pricing",
            "ubicación": "location",
            "extras": "extras_menu",
            "llamar a tomas": "call_captain",
            "duración": "duration",
            "traer": "what_to_bring",
            "clima": "weather",
            "contacto": "contact_info",
            "cancelar": "cancellation",
        }
        
        # Check for exact matches or keywords
        for keyword, response in self.faqs.items():
            if keyword in message_lower:
                # If response is an alias, resolve it
                actual_keyword = keyword
                if isinstance(response, str) and response in self.faqs:
                    actual_keyword = response
                
                # Check if we have a translation for this keyword
                if actual_keyword in faq_to_translation:
                    translation_key = faq_to_translation[actual_keyword]
                    logger.info(f"FAQ match found for keyword: {keyword} -> {translation_key}")
                    return get_text(translation_key, lang)
                else:
                    # Fallback to original response if no translation available
                    if isinstance(response, str) and response in self.faqs:
                        response = self.faqs[response]
                    logger.info(f"FAQ match found for keyword: {keyword} (no translation)")
                    return response
        
        return None
    
    def is_menu_number(self, message: str) -> Optional[int]:
        """
        Check if message is a menu number selection (1-8)
        
        Args:
            message: User's message
        
        Returns:
            Number selected (1-8) or None
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
        }
        
        # Check exact match with emoji
        if message_stripped in menu_numbers:
            return menu_numbers[message_stripped]
        
        # Check for plain numbers (just the digit, possibly with spaces)
        message_lower = message.lower().strip()
        if message_lower in ["1", "2", "3", "4", "5", "6", "7", "8"]:
            return int(message_lower)
        
        # Check if message starts with a number (e.g., "1 disponibilidad")
        first_char = message_lower[0] if message_lower else ""
        if first_char in ["1", "2", "3", "4", "5", "6", "7", "8"]:
            try:
                # Try to parse just the number
                num = int(first_char)
                if 1 <= num <= 8:
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








