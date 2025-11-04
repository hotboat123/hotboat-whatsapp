"""
Accommodations handler - manages accommodation information with images
"""
import logging
from typing import Dict, List, Optional, Any

from app.config.accommodations_config import ACCOMMODATION_IMAGES

logger = logging.getLogger(__name__)


class AccommodationInfo:
    """Information about an accommodation option"""
    
    def __init__(
        self,
        name: str,
        description: str,
        price_per_night: int,
        capacity: int,
        image_url: Optional[str] = None,
        features: Optional[List[str]] = None
    ):
        self.name = name
        self.description = description
        self.price_per_night = price_per_night
        self.capacity = capacity
        self.image_url = image_url
        self.features = features or []


class AccommodationsHandler:
    """Handle accommodation-related queries with images"""
    
    def __init__(self):
        # Open Sky - Para parejas románticas
        self.open_sky_domo_bath = AccommodationInfo(
            name="Open Sky - Domo con Tina de Baño",
            description="Domo transparente con vista a las estrellas, perfecto para parejas románticas 🌌",
            price_per_night=100000,
            capacity=2,
            image_url=ACCOMMODATION_IMAGES.get("open_sky_domo_bath"),
            features=["Domo transparente", "Tina de baño interior", "Vista a las estrellas", "Experiencia romántica"]
        )
        
        self.open_sky_domo_hydromassage = AccommodationInfo(
            name="Open Sky - Domo con Hidromasaje",
            description="Domo transparente con hidromasaje interior, la experiencia más exclusiva 🌟",
            price_per_night=120000,
            capacity=2,
            image_url=ACCOMMODATION_IMAGES.get("open_sky_domo_hydromassage"),
            features=["Domo transparente", "Hidromasaje interior", "Vista a las estrellas", "Experiencia premium"]
        )
        
        # Raíces de Relikura - Familiar
        self.relikura_cabin_2 = AccommodationInfo(
            name="Raíces de Relikura - Cabaña 2 personas",
            description="Cabaña junto al río, con tinaja y entorno natural perfecto para parejas 🌿",
            price_per_night=60000,
            capacity=2,
            image_url=ACCOMMODATION_IMAGES.get("relikura_cabin_2"),
            features=["Cabaña junto al río", "Tinaja exterior", "Entorno natural", "Ideal para parejas"]
        )
        
        self.relikura_cabin_4 = AccommodationInfo(
            name="Raíces de Relikura - Cabaña 4 personas",
            description="Cabaña espaciosa junto al río, ideal para familias pequeñas 🏡",
            price_per_night=80000,
            capacity=4,
            image_url=ACCOMMODATION_IMAGES.get("relikura_cabin_4"),
            features=["Cabaña junto al río", "Tinaja exterior", "Entorno natural", "Ideal para familias"]
        )
        
        self.relikura_cabin_6 = AccommodationInfo(
            name="Raíces de Relikura - Cabaña 6 personas",
            description="Cabaña grande junto al río, perfecta para grupos y familias grandes 👨‍👩‍👧‍👦",
            price_per_night=100000,
            capacity=6,
            image_url=ACCOMMODATION_IMAGES.get("relikura_cabin_6"),
            features=["Cabaña junto al río", "Tinaja exterior", "Entorno natural", "Ideal para grupos"]
        )
        
        self.relikura_hostel = AccommodationInfo(
            name="Raíces de Relikura - Hostal",
            description="Hostal económico junto al río, con tinaja y actividades 🎒",
            price_per_night=20000,
            capacity=1,  # Por persona
            image_url=ACCOMMODATION_IMAGES.get("relikura_hostel"),
            features=["Hostal económico", "Tinaja compartida", "Entorno natural", "Actividades disponibles"]
        )
    
    def get_all_accommodations(self) -> List[AccommodationInfo]:
        """Get all available accommodations"""
        return [
            self.open_sky_domo_bath,
            self.open_sky_domo_hydromassage,
            self.relikura_cabin_2,
            self.relikura_cabin_4,
            self.relikura_cabin_6,
            self.relikura_hostel,
        ]
    
    def get_text_response(self) -> str:
        """Get text response about accommodations"""
        return """🌊🔥 **HotBoat + Alojamiento en Pucón**

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

📲 Responde este mensaje con la fecha y alojamiento que prefieras"""
    
    def get_accommodations_with_images(self) -> List[Dict[str, Any]]:
        """
        Get accommodations formatted for sending with images
        
        Returns:
            List of dicts with text and image_url for each accommodation
        """
        accommodations = self.get_all_accommodations()
        result = []
        
        # Group by type
        open_sky = [self.open_sky_domo_bath, self.open_sky_domo_hydromassage]
        relikura_cabins = [self.relikura_cabin_2, self.relikura_cabin_4, self.relikura_cabin_6]
        relikura_hostel = [self.relikura_hostel]
        
        # Open Sky header
        result.append({
            "type": "text",
            "content": "⭐ *Open Sky* – Para parejas románticas\nDomos transparentes con vista a las estrellas 🌌"
        })
        
        # Open Sky accommodations with images
        for acc in open_sky:
            price_text = f"💰 ${acc.price_per_night:,} / noche ({acc.capacity} pers.)"
            result.append({
                "type": "image",
                "image_url": acc.image_url,
                "caption": f"*{acc.name}*\n\n{acc.description}\n\n{price_text}\n\n" + "\n".join([f"• {f}" for f in acc.features])
            })
        
        # Raíces de Relikura header
        result.append({
            "type": "text",
            "content": "\n🌿 *Raíces de Relikura* – Familiar con actividades\nHostal y cabañas junto al río, con tinaja y entorno natural 🍃"
        })
        
        # Relikura cabins with images
        for acc in relikura_cabins:
            price_text = f"💰 ${acc.price_per_night:,} / noche ({acc.capacity} pers.)"
            result.append({
                "type": "image",
                "image_url": acc.image_url,
                "caption": f"*{acc.name}*\n\n{acc.description}\n\n{price_text}\n\n" + "\n".join([f"• {f}" for f in acc.features])
            })
        
        # Hostel with image
        acc = self.relikura_hostel
        price_text = f"💰 ${acc.price_per_night:,} / noche por persona"
        result.append({
            "type": "image",
            "image_url": acc.image_url,
            "caption": f"*{acc.name}*\n\n{acc.description}\n\n{price_text}\n\n" + "\n".join([f"• {f}" for f in acc.features])
        })
        
        # Footer
        result.append({
            "type": "text",
            "content": "\n📌 *Cómo funciona:*\n1. Me dices la fecha y la opción de alojamiento\n2. Te confirmo disponibilidad\n3. Pagas todo en un solo link y quedas reservado\n\n📲 Responde este mensaje con la fecha y alojamiento que prefieras"
        })
        
        return result


# Global instance
accommodations_handler = AccommodationsHandler()

