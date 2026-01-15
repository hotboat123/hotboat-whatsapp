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
    
    async def upload_media(self, file_path: str, mime_type: str = "image/jpeg") -> Optional[str]:
        """
        Upload media file to WhatsApp and get media_id
        
        Args:
            file_path: Path to the file to upload
            mime_type: MIME type of the file (default: image/jpeg)
        
        Returns:
            media_id if successful, None otherwise
        """
        url = f"{self.BASE_URL}/{self.phone_number_id}/media"
        
        try:
            import os
            if not os.path.exists(file_path):
                logger.error(f"❌ File not found: {file_path}")
                return None
            
            # Prepare headers without Content-Type (httpx will set it for multipart)
            headers = {
                "Authorization": f"Bearer {self.token}",
            }
            
            with open(file_path, "rb") as f:
                files = {
                    "file": (os.path.basename(file_path), f, mime_type),
                    "messaging_product": (None, "whatsapp"),
                    "type": (None, mime_type),
                }
                
                async with httpx.AsyncClient() as client:
                    response = await client.post(url, files=files, headers=headers, timeout=60)
                    response.raise_for_status()
                    result = response.json()
                    media_id = result.get("id")
                    logger.info(f"✅ Media uploaded successfully: {media_id}")
                    return media_id
        except Exception as e:
            logger.error(f"❌ Error uploading media: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def send_image_message(self, to: str, image_url: str = None, caption: Optional[str] = None, media_id: str = None) -> Dict[str, Any]:
        """
        Send an image message using either URL or media_id
        
        Args:
            to: Recipient phone number (with country code, no + or spaces)
            image_url: URL of the image (must be publicly accessible) - Optional if media_id is provided
            caption: Optional caption text
            media_id: WhatsApp media ID from upload_media() - Optional if image_url is provided
        """
        url = f"{self.BASE_URL}/{self.phone_number_id}/messages"
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to,
            "type": "image",
            "image": {}
        }
        
        # Use media_id if provided, otherwise use image_url
        if media_id:
            payload["image"]["id"] = media_id
        elif image_url:
            payload["image"]["link"] = image_url
        else:
            logger.error("❌ Either image_url or media_id must be provided")
            raise ValueError("Either image_url or media_id must be provided")
        
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
    
    async def download_media(self, media_id: str, save_path: str) -> bool:
        """
        Download media from WhatsApp and save locally
        
        Args:
            media_id: WhatsApp media ID
            save_path: Local path to save the file
        
        Returns:
            True if successful, False otherwise
        """
        try:
            # Get media URL (this already includes access_token as parameter)
            media_url = await self.get_media_url(media_id)
            if not media_url:
                logger.error(f"❌ Could not get media URL for {media_id}")
                return False
            
            # Download the file WITH authorization header
            # WhatsApp requires both the token in URL AND in headers for lookaside.fbsbx.com
            download_headers = {
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "HotBoat-WhatsApp-Bot/1.0"
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(media_url, headers=download_headers, timeout=30)
                response.raise_for_status()
                
                # Create directory if it doesn't exist
                import os
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                
                # Save file
                with open(save_path, "wb") as f:
                    f.write(response.content)
                
                logger.info(f"✅ Media downloaded successfully: {save_path}")
                return True
        except Exception as e:
            logger.error(f"❌ Error downloading media {media_id}: {e}")
            return False
    
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








