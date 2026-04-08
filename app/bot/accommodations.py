"""
Accommodations handler - manages accommodation information with images.
Prices and variants are loaded from the `alojamientos` DB table (admin CMS).
"""
import json
import logging
from typing import Dict, List, Optional, Any

from app.config.accommodations_config import ACCOMMODATION_IMAGES
from app.bot.translations import get_text
from app.utils.media_handler import get_accommodation_image_path

logger = logging.getLogger(__name__)


def _load_db_variants() -> Dict[str, List[dict]]:
    """Load accommodation variants from DB. Returns {slug: [variant, ...]}."""
    try:
        from app.db.connection import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT slug, variants FROM alojamientos WHERE is_active=TRUE ORDER BY display_order,id"
                )
                result = {}
                for row in cur.fetchall():
                    slug, variants = row
                    if isinstance(variants, str):
                        variants = json.loads(variants)
                    result[slug] = variants or []
                return result
    except Exception as e:
        logger.warning(f"_load_db_variants failed: {e}")
        return {}


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
    """Handle accommodation-related queries with images.
    Prices are loaded from DB if available; hardcoded values are used as fallback."""

    # Hardcoded fallback prices (used if DB is unavailable)
    _FALLBACK = {
        "open-sky": [
            {"name": "Domo con Tina de Baño",  "price_per_night": 100000, "capacity": 2},
            {"name": "Domo con Hidromasaje",    "price_per_night": 120000, "capacity": 2},
        ],
        "relikura": [
            {"name": "Cabaña 2 personas", "price_per_night": 60000,  "capacity": 2},
            {"name": "Cabaña 4 personas", "price_per_night": 80000,  "capacity": 4},
            {"name": "Cabaña 6 personas", "price_per_night": 100000, "capacity": 6},
            {"name": "Hostal",            "price_per_night": 20000,  "capacity": 1},
        ],
    }

    def __init__(self):
        db = _load_db_variants()
        os_vars  = db.get("open-sky") or self._FALLBACK["open-sky"]
        rel_vars = db.get("relikura") or self._FALLBACK["relikura"]

        def _price(variants, name_substr):
            for v in variants:
                if name_substr.lower() in v["name"].lower():
                    return v["price_per_night"], v.get("capacity", 2)
            return variants[0]["price_per_night"] if variants else 0, 2

        p_bath,  cap_bath  = _price(os_vars,  "Tina")
        p_hydro, cap_hydro = _price(os_vars,  "Hidro")
        p_c2,    cap_c2    = _price(rel_vars, "2 persona")
        p_c4,    cap_c4    = _price(rel_vars, "4 persona")
        p_c6,    cap_c6    = _price(rel_vars, "6 persona")
        p_host,  cap_host  = _price(rel_vars, "Hostal")

        # Open Sky
        self.open_sky_domo_bath = AccommodationInfo(
            name="Open Sky - Domo con Tina de Baño",
            description="Domo transparente con vista a las estrellas, perfecto para parejas románticas 🌌",
            price_per_night=p_bath, capacity=cap_bath,
            image_url=ACCOMMODATION_IMAGES.get("open_sky_domo_bath"),
            features=["Domo transparente", "Tina de baño interior", "Vista a las estrellas", "Experiencia romántica"]
        )
        self.open_sky_domo_hydromassage = AccommodationInfo(
            name="Open Sky - Domo con Hidromasaje",
            description="Domo transparente con hidromasaje interior, la experiencia más exclusiva 🌟",
            price_per_night=p_hydro, capacity=cap_hydro,
            image_url=ACCOMMODATION_IMAGES.get("open_sky_domo_hydromassage"),
            features=["Domo transparente", "Hidromasaje interior", "Vista a las estrellas", "Experiencia premium"]
        )

        # Raíces de Relikura
        self.relikura_cabin_2 = AccommodationInfo(
            name="Raíces de Relikura - Cabaña 2 personas",
            description="Cabaña junto al río, con tinaja y entorno natural perfecto para parejas 🌿",
            price_per_night=p_c2, capacity=cap_c2,
            image_url=ACCOMMODATION_IMAGES.get("relikura_cabin_2"),
            features=["Cabaña junto al río", "Tinaja exterior", "Entorno natural", "Ideal para parejas"]
        )
        self.relikura_cabin_4 = AccommodationInfo(
            name="Raíces de Relikura - Cabaña 4 personas",
            description="Cabaña espaciosa junto al río, ideal para familias pequeñas 🏡",
            price_per_night=p_c4, capacity=cap_c4,
            image_url=ACCOMMODATION_IMAGES.get("relikura_cabin_4"),
            features=["Cabaña junto al río", "Tinaja exterior", "Entorno natural", "Ideal para familias"]
        )
        self.relikura_cabin_6 = AccommodationInfo(
            name="Raíces de Relikura - Cabaña 6 personas",
            description="Cabaña grande junto al río, perfecta para grupos y familias grandes 👨‍👩‍👧‍👦",
            price_per_night=p_c6, capacity=cap_c6,
            image_url=ACCOMMODATION_IMAGES.get("relikura_cabin_6"),
            features=["Cabaña junto al río", "Tinaja exterior", "Entorno natural", "Ideal para grupos"]
        )
        self.relikura_hostel = AccommodationInfo(
            name="Raíces de Relikura - Hostal",
            description="Hostal económico junto al río, con tinaja y actividades 🎒",
            price_per_night=p_host, capacity=cap_host,
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
    
    def get_text_response(self, language: str = "es") -> str:
        """
        Get text response about accommodations
        
        Args:
            language: Language code (es, en, pt)
        
        Returns:
            Accommodations text in specified language
        """
        return get_text("accommodations", language)
    
    def get_accommodations_with_images(self) -> List[Dict[str, Any]]:
        """
        Get accommodations formatted for sending with images
        
        Returns:
            List of dicts with text, image_url, and image_path for each accommodation
        """
        # Mapping of accommodation names to their keys
        name_to_key = {
            "Open Sky - Domo con Tina de Baño": "open_sky_domo_bath",
            "Open Sky - Domo con Hidromasaje": "open_sky_domo_hydromassage",
            "Raíces de Relikura - Cabaña 2 personas": "relikura_cabin_2",
            "Raíces de Relikura - Cabaña 4 personas": "relikura_cabin_4",
            "Raíces de Relikura - Cabaña 6 personas": "relikura_cabin_6",
            "Raíces de Relikura - Hostal": "relikura_hostel",
        }
        
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
            acc_key = name_to_key.get(acc.name)
            local_path = get_accommodation_image_path(acc_key) if acc_key else None
            result.append({
                "type": "image",
                "image_url": acc.image_url,
                "image_path": local_path,
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
            acc_key = name_to_key.get(acc.name)
            local_path = get_accommodation_image_path(acc_key) if acc_key else None
            result.append({
                "type": "image",
                "image_url": acc.image_url,
                "image_path": local_path,
                "caption": f"*{acc.name}*\n\n{acc.description}\n\n{price_text}\n\n" + "\n".join([f"• {f}" for f in acc.features])
            })
        
        # Hostel with image
        acc = self.relikura_hostel
        price_text = f"💰 ${acc.price_per_night:,} / noche por persona"
        acc_key = name_to_key.get(acc.name)
        local_path = get_accommodation_image_path(acc_key) if acc_key else None
        result.append({
            "type": "image",
            "image_url": acc.image_url,
            "image_path": local_path,
            "caption": f"*{acc.name}*\n\n{acc.description}\n\n{price_text}\n\n" + "\n".join([f"• {f}" for f in acc.features])
        })
        
        # Footer
        result.append({
            "type": "text",
            "content": "\n📌 *Cómo funciona:*\n1. Me dices la fecha y la opción de alojamiento\n2. Te confirmo disponibilidad\n3. Pagas todo en un solo link y quedas reservado\n\n📲 Responde este mensaje con la fecha y alojamiento que prefieras"
        })
        
        return result


def get_accommodations_handler() -> "AccommodationsHandler":
    """Return a fresh handler with prices loaded from DB."""
    return AccommodationsHandler()

# Keep backward-compatible name (loads once at import; use get_accommodations_handler() for fresh prices)
accommodations_handler = AccommodationsHandler()

