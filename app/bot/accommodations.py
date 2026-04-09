"""
Accommodations handler - manages accommodation information with images.
All accommodations are loaded dynamically from the `alojamientos` DB table.
Each row is a single accommodation option (flat structure, no JSONB variants).
"""
import logging
from typing import Dict, List, Optional, Any

from app.config.accommodations_config import ACCOMMODATION_IMAGES
from app.bot.translations import get_text
from app.utils.media_handler import get_accommodation_image_path

logger = logging.getLogger(__name__)

# Fallback data used if DB is unavailable at startup
_FALLBACK_ROWS = [
    {"slug": "open-sky-domo-tina",  "name": "Open Sky – Domo con Tina de Baño",
     "group_name": "Open Sky",          "price_from": 100000, "cost_from": 0, "capacity": 2,
     "description": "Domo transparente con tina de baño interior, vista a las estrellas.",
     "image_path": None, "is_active": True, "display_order": 10},
    {"slug": "open-sky-domo-hidro",  "name": "Open Sky – Domo con Hidromasaje",
     "group_name": "Open Sky",          "price_from": 120000, "cost_from": 0, "capacity": 2,
     "description": "Domo transparente con hidromasaje interior, la experiencia más exclusiva.",
     "image_path": None, "is_active": True, "display_order": 11},
    {"slug": "relikura-cabana-2",    "name": "Raíces de Relikura – Cabaña 2 personas",
     "group_name": "Raíces de Relikura","price_from": 60000,  "cost_from": 0, "capacity": 2,
     "description": "Cabaña junto al río con tinaja, ideal para parejas.",
     "image_path": None, "is_active": True, "display_order": 20},
    {"slug": "relikura-cabana-4",    "name": "Raíces de Relikura – Cabaña 4 personas",
     "group_name": "Raíces de Relikura","price_from": 80000,  "cost_from": 0, "capacity": 4,
     "description": "Cabaña espaciosa junto al río, ideal para familias.",
     "image_path": None, "is_active": True, "display_order": 21},
    {"slug": "relikura-cabana-6",    "name": "Raíces de Relikura – Cabaña 6 personas",
     "group_name": "Raíces de Relikura","price_from": 100000, "cost_from": 0, "capacity": 6,
     "description": "Cabaña grande junto al río, perfecta para grupos.",
     "image_path": None, "is_active": True, "display_order": 22},
    {"slug": "relikura-hostal",      "name": "Raíces de Relikura – Hostal",
     "group_name": "Raíces de Relikura","price_from": 20000,  "cost_from": 0, "capacity": 1,
     "description": "Hostal económico por persona, tinaja compartida.",
     "image_path": None, "is_active": True, "display_order": 23},
]

# Legacy image-key mapping (for get_accommodation_image_path)
_SLUG_TO_IMAGE_KEY = {
    "open-sky-domo-tina":  "open_sky_domo_bath",
    "open-sky-domo-hidro": "open_sky_domo_hydromassage",
    "relikura-cabana-2":   "relikura_cabin_2",
    "relikura-cabana-4":   "relikura_cabin_4",
    "relikura-cabana-6":   "relikura_cabin_6",
    "relikura-hostal":     "relikura_hostel",
}


def _load_db_rows() -> List[dict]:
    """Load all active accommodations from DB as list of dicts."""
    try:
        from app.db.connection import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT slug, name, group_name, price_from, cost_from, capacity,"
                    "       description, image_path, is_active, display_order"
                    " FROM alojamientos WHERE is_active=TRUE ORDER BY display_order, id"
                )
                cols = [d[0] for d in cur.description]
                return [dict(zip(cols, row)) for row in cur.fetchall()]
    except Exception as e:
        logger.warning(f"_load_db_rows failed, using fallback: {e}")
        return []


class AccommodationInfo:
    """Information about a single accommodation option."""

    def __init__(self, row: dict):
        self.slug         = row["slug"]
        self.name         = row["name"]
        self.group_name   = row.get("group_name", "")
        self.price_per_night = row.get("price_from", 0)
        self.cost_per_night  = row.get("cost_from", 0)
        self.capacity     = row.get("capacity", 2)
        self.description  = row.get("description", "")
        self.image_path_db = row.get("image_path")  # admin-uploaded image

        # Resolve local image: prefer admin-uploaded, fall back to legacy path
        img_key = _SLUG_TO_IMAGE_KEY.get(self.slug)
        self.image_url  = ACCOMMODATION_IMAGES.get(img_key) if img_key else None
        self._local_img = self.image_path_db or (
            get_accommodation_image_path(img_key) if img_key else None
        )

    # Kept for backward compatibility
    @property
    def features(self) -> List[str]:
        parts = []
        if self.group_name:
            parts.append(self.group_name)
        if self.capacity:
            parts.append(f"Hasta {self.capacity} persona{'s' if self.capacity > 1 else ''}")
        return parts


class AccommodationsHandler:
    """Loads all active accommodations from DB and provides bot display methods."""

    def __init__(self):
        rows = _load_db_rows() or _FALLBACK_ROWS
        self._accommodations: List[AccommodationInfo] = [AccommodationInfo(r) for r in rows]

        # Build grouped dict: {group_name: [AccommodationInfo, ...]}
        self._groups: Dict[str, List[AccommodationInfo]] = {}
        for acc in self._accommodations:
            self._groups.setdefault(acc.group_name, []).append(acc)

    # ── public API ────────────────────────────────────────────────────────────

    def get_all_accommodations(self) -> List[AccommodationInfo]:
        return list(self._accommodations)

    def get_text_response(self, language: str = "es") -> str:
        return get_text("accommodations", language)

    def get_accommodations_with_images(self) -> List[Dict[str, Any]]:
        """
        Format accommodations for WhatsApp: group headers + per-option image cards.
        """
        result = []

        for group_name, accs in self._groups.items():
            # Group header
            icon = "⭐" if "sky" in group_name.lower() or "open" in group_name.lower() else "🌿"
            result.append({
                "type": "text",
                "content": f"{icon} *{group_name}*"
            })

            for acc in accs:
                price_text = f"💰 ${acc.price_per_night:,} / noche ({acc.capacity} pers.)"
                caption = (
                    f"*{acc.name}*\n\n"
                    f"{acc.description}\n\n"
                    f"{price_text}"
                )
                result.append({
                    "type": "image",
                    "image_url":  acc.image_url,
                    "image_path": acc._local_img,
                    "caption":    caption,
                })

        result.append({
            "type": "text",
            "content": (
                "\n📌 *Cómo funciona:*\n"
                "1. Me dices la fecha y la opción de alojamiento\n"
                "2. Te confirmo disponibilidad\n"
                "3. Pagas y quedas reservado\n\n"
                "📲 Responde con la fecha y alojamiento que prefieras"
            )
        })
        return result


def get_accommodations_handler() -> AccommodationsHandler:
    """Return a fresh handler loaded from DB."""
    return AccommodationsHandler()


# Keep backward-compatible name
accommodations_handler = AccommodationsHandler()
