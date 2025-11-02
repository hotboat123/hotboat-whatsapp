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
            # Pricing
            "precio": """💰 **Precios Hot Boat Trip:**

👥 2 personas: $69.990 por persona
👥 3 personas: $54.990 por persona  
👥 4 personas: $44.990 por persona
👥 5+ personas: $38.990 por persona

✨ Incluye:
• Tour guiado por el lago
• Vista al volcán Villarrica
• Todas las medidas de seguridad
• Experiencia inolvidable

¿Te gustaría reservar?""",
            
            # Location
            "ubicación": f"""📍 **Ubicación:**

Estamos en Villarrica, Región de La Araucanía, Chile.

🚗 Fácil acceso desde:
• Pucón: 20 min
• Villarrica centro: 5 min
• Temuco: 1 hora

Te enviaremos la ubicación exacta al confirmar tu reserva.

🌐 Más info: https://hotboatchile.com""",
            
            "donde": "ubicación",  # Alias
            
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

¿Necesitas más información?"""
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


