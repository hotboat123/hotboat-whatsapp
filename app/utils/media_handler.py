"""
Media handler for managing images and files
"""
import os
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# Base directory for media storage
MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "media")
RECEIVED_DIR = os.path.join(MEDIA_DIR, "received")
UPLOADED_DIR = os.path.join(MEDIA_DIR, "uploaded")
ACCOMMODATION_DIR = os.path.join(MEDIA_DIR, "accommodations")

# Create directories if they don't exist
for directory in [MEDIA_DIR, RECEIVED_DIR, UPLOADED_DIR, ACCOMMODATION_DIR]:
    os.makedirs(directory, exist_ok=True)


def get_received_media_path(media_id: str, extension: str = "jpg") -> str:
    """
    Get path for a received media file
    
    Args:
        media_id: WhatsApp media ID
        extension: File extension (default: jpg)
    
    Returns:
        Path to save the file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{media_id}_{timestamp}.{extension}"
    return os.path.join(RECEIVED_DIR, filename)


def get_uploaded_media_path(filename: str) -> str:
    """
    Get path for an uploaded media file
    
    Args:
        filename: Name of the file
    
    Returns:
        Path to save the file
    """
    return os.path.join(UPLOADED_DIR, filename)


def get_accommodation_image_path(accommodation_name: str) -> Optional[str]:
    """
    Get path for an accommodation image
    
    Args:
        accommodation_name: Name of the accommodation (key from config)
    
    Returns:
        Path to the image if it exists, None otherwise
    """
    # Try different extensions
    for ext in ["jpg", "jpeg", "png", "webp"]:
        path = os.path.join(ACCOMMODATION_DIR, f"{accommodation_name}.{ext}")
        if os.path.exists(path):
            return path
    return None


def list_accommodation_images() -> dict:
    """
    List all available accommodation images
    
    Returns:
        Dict mapping accommodation names to their file paths
    """
    result = {}
    if not os.path.exists(ACCOMMODATION_DIR):
        return result
    
    for filename in os.listdir(ACCOMMODATION_DIR):
        if filename.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
            name = os.path.splitext(filename)[0]
            result[name] = os.path.join(ACCOMMODATION_DIR, filename)
    
    return result


def save_accommodation_image(accommodation_name: str, file_path: str) -> bool:
    """
    Save an accommodation image
    
    Args:
        accommodation_name: Name/key for the accommodation
        file_path: Path to the source image file
    
    Returns:
        True if successful, False otherwise
    """
    try:
        import shutil
        ext = os.path.splitext(file_path)[1]
        dest_path = os.path.join(ACCOMMODATION_DIR, f"{accommodation_name}{ext}")
        shutil.copy2(file_path, dest_path)
        logger.info(f"✅ Accommodation image saved: {dest_path}")
        return True
    except Exception as e:
        logger.error(f"❌ Error saving accommodation image: {e}")
        return False
