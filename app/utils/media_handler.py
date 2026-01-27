"""
Media handler for managing images and files
"""
import os
import logging
from typing import Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)

# Base directory for media storage
MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "media")
RECEIVED_DIR = os.path.join(MEDIA_DIR, "received")
UPLOADED_DIR = os.path.join(MEDIA_DIR, "uploaded")
ACCOMMODATION_DIR = os.path.join(MEDIA_DIR, "accommodations")
AUDIO_DIR = os.path.join(MEDIA_DIR, "audio")
DOCUMENTS_DIR = os.path.join(MEDIA_DIR, "documents")

# Create directories if they don't exist
for directory in [MEDIA_DIR, RECEIVED_DIR, UPLOADED_DIR, ACCOMMODATION_DIR, AUDIO_DIR, DOCUMENTS_DIR]:
    os.makedirs(directory, exist_ok=True)


def get_received_media_path(media_id: str, extension: str = "jpg", media_type: str = "image") -> str:
    """
    Get path for a received media file
    
    Args:
        media_id: WhatsApp media ID
        extension: File extension (default: jpg)
        media_type: Type of media (image, audio, video, etc.)
    
    Returns:
        Path to save the file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{media_id}_{timestamp}.{extension}"
    
    # Save audio files in dedicated audio directory
    if media_type == "audio":
        return os.path.join(AUDIO_DIR, filename)
    
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


def get_audio_path(audio_id: str, extension: str = "ogg") -> str:
    """
    Get path for an audio file
    
    Args:
        audio_id: Audio file ID
        extension: File extension (default: ogg for WhatsApp)
    
    Returns:
        Path to the audio file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{audio_id}_{timestamp}.{extension}"
    return os.path.join(AUDIO_DIR, filename)


def list_audio_files() -> List[str]:
    """
    List all audio files in the audio directory
    
    Returns:
        List of audio file paths
    """
    if not os.path.exists(AUDIO_DIR):
        return []
    
    return [
        os.path.join(AUDIO_DIR, f)
        for f in os.listdir(AUDIO_DIR)
        if f.lower().endswith(('.ogg', '.mp3', '.wav', '.m4a', '.aac'))
    ]


def get_accommodations_pdf_path() -> Optional[str]:
    """
    Get path to the accommodations PDF file
    
    Returns:
        Path to the PDF if it exists, None otherwise
    """
    pdf_path = os.path.join(DOCUMENTS_DIR, "alojamientos.pdf")
    if os.path.exists(pdf_path):
        return pdf_path
    return None


def get_package_pdf_path(pdf_name: str) -> Optional[str]:
    """
    Get path to a specific package PDF file
    
    Args:
        pdf_name: Name of the PDF file (e.g., "pack_1_noche.pdf")
    
    Returns:
        Path to the PDF if it exists, None otherwise
    """
    pdf_path = os.path.join(DOCUMENTS_DIR, pdf_name)
    if os.path.exists(pdf_path):
        return pdf_path
    return None


def get_experiences_pdf_path() -> Optional[str]:
    """
    Get path to the experiences PDF file
    
    Returns:
        Path to the PDF if it exists, None otherwise
    """
    pdf_path = os.path.join(DOCUMENTS_DIR, "experiencias.pdf")
    if os.path.exists(pdf_path):
        return pdf_path
    return None
