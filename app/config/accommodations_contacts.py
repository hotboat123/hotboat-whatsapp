"""
Accommodation contacts configuration
Maps each accommodation to its WhatsApp contact
"""

# WhatsApp contacts for each accommodation property
ACCOMMODATION_CONTACTS = {
    # Open Sky - All domos
    "open_sky": {
        "name": "Alex (Open Sky)",
        "whatsapp": "+56964634691",
        "property_name": "Open Sky"
    },
    
    # Raíces de Relikura - All cabins and hostel
    "relikura": {
        "name": "Raíces de Relikura",
        "whatsapp": "+56990508175",
        "property_name": "Raíces de Relikura"
    }
}


def get_accommodation_contact(property_key: str) -> dict:
    """
    Get contact information for an accommodation property
    
    Args:
        property_key: "open_sky" or "relikura"
    
    Returns:
        Dict with name, whatsapp, and property_name
    """
    return ACCOMMODATION_CONTACTS.get(property_key, {})


def generate_whatsapp_link(phone: str, message: str) -> str:
    """
    Generate a WhatsApp Web link with pre-filled message
    
    Args:
        phone: Phone number with country code (e.g., "+56964634691")
        message: Pre-filled message text
    
    Returns:
        WhatsApp Web URL
    """
    import urllib.parse
    # Remove any spaces, dashes, or + from phone number
    clean_phone = phone.replace("+", "").replace(" ", "").replace("-", "")
    encoded_message = urllib.parse.quote(message)
    return f"https://wa.me/{clean_phone}?text={encoded_message}"
