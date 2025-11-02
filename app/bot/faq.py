"""
FAQ Handler - predefined responses for common questions
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class FAQHandler:
    """Handle frequently asked questions with predefined answers"""
    
    def __init__(self):
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
            "precio": """💰 **Precios HotBoat:**

Personas | Precio x Persona | Total
———————————————————
2        | $69.990          | $139.980
3        | $54.990          | $164.970
4        | $44.990          | $179.960
5        | $38.990          | $194.950
6        | $32.990          | $197.940
7        | $29.990          | $209.930

*niños pagan desde los 6 años

Aquí puedes reservar tu horario directo 👇
https://hotboatchile.com/es/book-hotboat/""",
            
            "valor": "precio",  # Alias
            "valores": "precio",  # Alias
            "cuanto cuesta": "precio",  # Alias
            


            
            # Location
            "ubicación": """📍 **Ubicación HotBoat:**

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
            "duración": """⏱️ **Duración del tour:**

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
            "traer": """🎒 **¿Qué traer?**

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
            "clima": """🌤️ **Mejor época:**

Operamos principalmente en temporada alta:
• Diciembre - Marzo (verano)
• Octubre - Noviembre (primavera)

El lago Villarrica es hermoso todo el año, pero el mejor clima es en verano.

❄️ En invierno: consultar disponibilidad

¿Para qué fecha te interesa?""",
            
            "temporada": "clima",  # Alias
            
            # Contact
            "contacto": """📞 **Contáctanos:**

📱 WhatsApp: +56 9 1234 5678
📧 Email: info@hotboatchile.com
🌐 Web: https://hotboatchile.com

📍 Villarrica, Región de La Araucanía, Chile

¡Escríbenos para reservar! 🚤""",
            
            # Cancelation policy
            "cancelar": """🔄 **Política de cancelación:**

• Cancelación gratuita hasta 48h antes
• Entre 24-48h: 50% de reembolso
• Menos de 24h: No reembolsable

⛈️ Mal clima: Reprogramamos sin costo

💳 Política de pago: Se requiere anticipo del 30% para reservar

¿Necesitas más información?""",
            
            # Extras
            "extras": """✨ **Servicios Extra:**

¿Quieres agregar algo especial a tu HotBoat?

🍇 **Tablas de Picoteo**
$25.000 → Tabla grande (4 personas): jamón serrano, queso crema con mermelada de pimentón, y más
$20.000 → Tabla pequeña (2 personas): queso crema con mermelada de pimentón, jamón serrano y más

🥤 **Bebidas y Jugos** (sin alcohol)
$10.000 → Jugo natural 1L (piña o naranja)
$2.900 → Lata bebida (Coca-Cola o Fanta)
$2.500 → Agua mineral 1,5 L
🍦 $3.500 → Helado individual (Cookies & Cream 🍪 o Frambuesa a la Crema con Chocolate Belga 🍫)

🌹 **Modo Romántico**
$25.000 → pétalos de rosas y decoración especial 💕

🌙 **Decoración Nocturna Extra**
$10.000 → Velas LED decorativas 💡
$15.000 → Letras luminosas "Te Amo" / "Love" ❤️
$20.000 → Pack completo (velas + letras iluminadas) 💍

✨🎥 **Video personalizado**
15 s → $30.000 / 60 s → $40.000

🚐 **Transporte** ida y vuelta
$50.000 desde Pucón

🧻 **Toallas**
Toalla normal $9.000
Toalla poncho $10.000

🩴 **Chalas de ducha**
$10.000

🔒 **Reserva FLEX +10%** → cancela/reprograma cuando quieras

¿Qué extra te gustaría agregar?""",
            
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
            
            # Alojamientos
            "alojamiento": """🌊🔥 **HotBoat + Alojamiento en Pucón**

Arma tu experiencia a tu medida con HotBoat y nuestros alojamientos recomendados.

⭐ **Open Sky** – Para parejas románticas
Domos transparentes con vista a las estrellas 🌌

💰 $100.000 / noche – Domo con tina de baño interior (2 pers.)
💰 $120.000 / noche – Domo con hidromasaje interior (2 pers.)

🌿 **Raíces de Relikura** – Familiar con actividades
Hostal y cabañas junto al río, con tinaja y entorno natural 🍃

**Cabañas:**
💰 $60.000 / noche (2 pers.)
💰 $80.000 / noche (4 pers.)
💰 $100.000 / noche (6 pers.)

**Hostal:**
💰 $20.000 / noche por persona

📌 **Cómo funciona:**
1. Me dices la fecha y la opción de alojamiento
2. Te confirmo disponibilidad
3. Pagas todo en un solo link y quedas reservado

📲 Responde este mensaje con la fecha y alojamiento que prefieras""",
            
            "alojamientos": "alojamiento",  # Alias
            "hotel": "alojamiento",  # Alias
            "hoteles": "alojamiento",  # Alias
            "cabañas": "alojamiento",  # Alias
            "cabanas": "alojamiento",  # Alias
            "donde quedarse": "alojamiento",  # Alias
            "donde hospedarse": "alojamiento",  # Alias
            "hospedaje": "alojamiento",  # Alias
            "hostal": "alojamiento",  # Alias
        }
    
    def get_response(self, message: str) -> Optional[str]:
        """
        Get FAQ response if message matches a question
        
        Args:
            message: User's message
        
        Returns:
            FAQ response or None
        """
        message_lower = message.lower().strip()
        
        # Check for exact matches or keywords
        for keyword, response in self.faqs.items():
            if keyword in message_lower:
                # If response is an alias, get the actual response
                if isinstance(response, str) and response in self.faqs:
                    response = self.faqs[response]
                
                logger.info(f"FAQ match found for keyword: {keyword}")
                return response
        
        return None



