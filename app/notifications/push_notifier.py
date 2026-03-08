"""
Push notification system using Expo Push Notifications (Free!)
Alternative to email notifications
"""
import logging
import httpx
import json
from typing import List, Optional, Dict
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import get_settings

CHILE_TZ = ZoneInfo("America/Santiago")
logger = logging.getLogger(__name__)

# Expo Push Notification API endpoint
EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


class PushNotifier:
    """Send push notifications to mobile devices via Expo"""
    
    def __init__(self):
        self.settings = get_settings()
        self.enabled = False  # Will be enabled when tokens are registered
        
    async def send_notification(
        self,
        title: str,
        body: str,
        data: Optional[Dict] = None,
        priority: str = "high"
    ) -> bool:
        """
        Send push notification to all registered devices
        
        Args:
            title: Notification title
            body: Notification body
            data: Additional data to send with notification
            priority: 'default', 'normal', or 'high'
        
        Returns:
            True if sent successfully
        """
        try:
            # Get registered push tokens from database
            tokens = await self._get_registered_tokens()
            
            if not tokens:
                logger.warning("No push tokens registered. Skipping push notification.")
                return False
            
            # Prepare notification messages
            messages = []
            for token in tokens:
                message = {
                    "to": token,
                    "title": title,
                    "body": body,
                    "sound": "default",
                    "priority": priority,
                    "channelId": "hotboat-messages"
                }
                
                if data:
                    message["data"] = data
                    
                messages.append(message)
            
            # Send to Expo Push API
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    EXPO_PUSH_URL,
                    json=messages,
                    timeout=10.0
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"✅ Push notification sent to {len(tokens)} device(s)")
                    
                    # Check for errors in individual tokens
                    if "data" in result:
                        for idx, ticket in enumerate(result["data"]):
                            if ticket.get("status") == "error":
                                logger.error(f"Push error for token {tokens[idx]}: {ticket.get('message')}")
                    
                    return True
                else:
                    logger.error(f"Expo API error: {response.status_code} - {response.text}")
                    return False
                    
        except Exception as e:
            logger.error(f"Error sending push notification: {e}")
            return False
    
    async def send_new_message_notification(
        self,
        contact_name: str,
        phone_number: str,
        message_preview: str
    ) -> bool:
        """
        Send notification for new WhatsApp message
        
        Args:
            contact_name: Name of the contact
            phone_number: Phone number
            message_preview: Preview of the message (first 100 chars)
        
        Returns:
            True if sent successfully
        """
        title = f"💬 {contact_name}"
        body = message_preview[:100]
        
        data = {
            "type": "new_message",
            "phone_number": phone_number,
            "contact_name": contact_name,
            "timestamp": datetime.now(CHILE_TZ).isoformat()
        }
        
        return await self.send_notification(title, body, data, priority="high")
    
    async def send_high_priority_alert(
        self,
        contact_name: str,
        phone_number: str,
        reason: str
    ) -> bool:
        """
        Send high priority alert (e.g., reservation in next 3 days)
        
        Args:
            contact_name: Name of the contact
            phone_number: Phone number
            reason: Reason for high priority
        
        Returns:
            True if sent successfully
        """
        title = f"🔴 URGENTE: {contact_name}"
        body = f"Prioridad alta: {reason}"
        
        data = {
            "type": "high_priority",
            "phone_number": phone_number,
            "contact_name": contact_name,
            "reason": reason,
            "timestamp": datetime.now(CHILE_TZ).isoformat()
        }
        
        return await self.send_notification(title, body, data, priority="high")
    
    async def register_push_token(self, token: str, device_info: Optional[Dict] = None) -> bool:
        """
        Register a new push notification token
        
        Args:
            token: Expo push token (starts with ExponentPushToken[...])
            device_info: Optional device information
        
        Returns:
            True if registered successfully
        """
        try:
            from app.db.connection import get_connection
            
            # Convert device_info dict to JSON string for PostgreSQL JSONB
            device_info_json = json.dumps(device_info) if device_info else None
            
            with get_connection() as conn:
                with conn.cursor() as cur:
                    # Check if token already exists
                    cur.execute("""
                        SELECT id FROM push_tokens 
                        WHERE token = %s
                    """, (token,))
                    
                    existing = cur.fetchone()
                    
                    if existing:
                        # Update last_used
                        cur.execute("""
                            UPDATE push_tokens 
                            SET last_used_at = NOW(),
                                device_info = %s::jsonb
                            WHERE token = %s
                        """, (device_info_json, token))
                        logger.info(f"Updated existing push token")
                    else:
                        # Insert new token
                        cur.execute("""
                            INSERT INTO push_tokens (token, device_info, created_at, last_used_at)
                            VALUES (%s, %s::jsonb, NOW(), NOW())
                        """, (token, device_info_json))
                        logger.info(f"✅ Registered new push token")
                    
                    conn.commit()
                    self.enabled = True
                    return True
                    
        except Exception as e:
            logger.error(f"Error registering push token: {e}")
            return False
    
    async def unregister_push_token(self, token: str) -> bool:
        """
        Unregister a push notification token
        
        Args:
            token: Expo push token to unregister
        
        Returns:
            True if unregistered successfully
        """
        try:
            from app.db.connection import get_connection
            
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        DELETE FROM push_tokens 
                        WHERE token = %s
                    """, (token,))
                    conn.commit()
                    
                    logger.info(f"Unregistered push token")
                    return True
                    
        except Exception as e:
            logger.error(f"Error unregistering push token: {e}")
            return False
    
    async def _get_registered_tokens(self) -> List[str]:
        """
        Get all registered push tokens from database
        
        Returns:
            List of active push tokens
        """
        try:
            from app.db.connection import get_connection
            
            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT token FROM push_tokens 
                        WHERE last_used_at > NOW() - INTERVAL '30 days'
                        ORDER BY last_used_at DESC
                    """)
                    
                    rows = cur.fetchall()
                    return [row[0] for row in rows]
                    
        except Exception as e:
            logger.error(f"Error getting push tokens: {e}")
            return []


# Global instance
push_notifier = PushNotifier()
