"""
WhatsApp Business API Client
"""
import httpx
import logging
from typing import Dict, Any, Optional

from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class WhatsAppClient:
    """Client for WhatsApp Business API"""
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self):
        self.token = settings.whatsapp_api_token
        self.phone_number_id = settings.whatsapp_phone_number_id
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    async def send_text_message(self, to: str, message: str) -> Dict[str, Any]:
        """
        Send a text message
        
        Args:
            to: Recipient phone number (with country code, no + or spaces)
            message: Message text
        """
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message
            }
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=self.headers, timeout=30)
                response.raise_for_status()
                result = response.json()
                logger.info(f"✅ Message sent to {to}: {result}")
                return result
        except httpx.HTTPError as e:
            logger.error(f"❌ Error sending message to {to}: {e}")
            raise
    
    async def send_template_message(
        self,
        to: str,
        template_name: str,
        language_code: str = "es",
        components: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Send a template message (for business-initiated conversations)
        
        Args:
            to: Recipient phone number
            template_name: Name of the approved template
            language_code: Language code (default: es for Spanish)
            components: Template components with parameters
        """
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": language_code
                }
            }
        }
        
        if components:
            payload["template"]["components"] = components
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=self.headers, timeout=30)
                response.raise_for_status()
                result = response.json()
                logger.info(f"✅ Template message sent to {to}: {result}")
                return result
        except httpx.HTTPError as e:
            logger.error(f"❌ Error sending template to {to}: {e}")
            raise
    
    async def send_image_message(self, to: str, image_url: str, caption: Optional[str] = None) -> Dict[str, Any]:
        """
        Send an image message
        
        Args:
            to: Recipient phone number (with country code, no + or spaces)
            image_url: URL of the image (must be publicly accessible)
            caption: Optional caption text
        """
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": {
                "link": image_url
            }
        }
        
        if caption:
            payload["image"]["caption"] = caption
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=self.headers, timeout=30)
                response.raise_for_status()
                result = response.json()
                logger.info(f"✅ Image sent to {to}: {result}")
                return result
        except httpx.HTTPError as e:
            logger.error(f"❌ Error sending image to {to}: {e}")
            raise
    
    async def get_media_url(self, media_id: str) -> Optional[str]:
        """
        Retrieve a temporary URL for a received media object.
        """
        if not media_id:
            return None
        url = f"{self.BASE_URL}/{media_id}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.headers, timeout=15)
                response.raise_for_status()
                data = response.json()
                media_url = data.get("url")
                if media_url:
                    delimiter = "&" if "?" in media_url else "?"
                    return f"{media_url}{delimiter}access_token={self.token}"
                return None
        except httpx.HTTPError as e:
            logger.error(f"❌ Error getting media URL for {media_id}: {e}")
            return None
    
    async def mark_as_read(self, message_id: str) -> Dict[str, Any]:
        """Mark a message as read"""
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=self.headers, timeout=30)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as e:
            logger.error(f"❌ Error marking message as read: {e}")
            raise


# Global instance
whatsapp_client = WhatsAppClient()








