"""
WhatsApp webhook handler
"""
import logging
from typing import Dict, Any, Optional

from app.whatsapp.client import whatsapp_client

logger = logging.getLogger(__name__)


def verify_webhook(mode: Optional[str], token: Optional[str], expected_token: str) -> bool:
    """
    Verify webhook subscription request from Meta
    
    Args:
        mode: Should be "subscribe"
        token: Verification token from Meta
        expected_token: Our verification token
    
    Returns:
        True if verification successful
    """
    if mode == "subscribe" and token == expected_token:
        return True
    return False


async def handle_webhook(body: Dict[str, Any], conversation_manager) -> Dict[str, Any]:
    """
    Process incoming webhook from WhatsApp
    
    Args:
        body: Webhook payload from Meta
        conversation_manager: ConversationManager instance
    
    Returns:
        Processing result
    """
    try:
        # WhatsApp sends data in this structure
        if body.get("object") != "whatsapp_business_account":
            logger.warning(f"Unexpected webhook object: {body.get('object')}")
            return {"status": "ignored"}
        
        entries = body.get("entry", [])
        
        for entry in entries:
            changes = entry.get("changes", [])
            
            for change in changes:
                value = change.get("value", {})
                
                # Check if there are messages
                messages = value.get("messages", [])
                
                for message in messages:
                    await process_message(message, value, conversation_manager)
        
        return {"status": "processed"}
        
    except Exception as e:
        logger.error(f"Error handling webhook: {e}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "message": str(e)}


async def process_message(message: Dict[str, Any], value: Dict[str, Any], conversation_manager):
    """
    Process a single message
    
    Args:
        message: Message data
        value: Value data from webhook
        conversation_manager: ConversationManager instance
    """
    try:
        # Extract message info
        message_id = message.get("id")
        from_number = message.get("from")  # Sender's phone number
        message_type = message.get("type")
        timestamp = message.get("timestamp")
        
        # Extract contact info
        contacts = value.get("contacts", [])
        contact_name = contacts[0].get("profile", {}).get("name", "Usuario") if contacts else "Usuario"
        
        logger.info(f"📩 New message from {contact_name} ({from_number}): type={message_type}")
        
        # Mark as read
        try:
            await whatsapp_client.mark_as_read(message_id)
        except Exception as e:
            logger.warning(f"Could not mark message as read: {e}")
        
        # Handle different message types
        if message_type == "text":
            text_body = message.get("text", {}).get("body", "")
            logger.info(f"💬 Message text: {text_body}")
            
            # Process the message with conversation manager
            response = await conversation_manager.process_message(
                from_number=from_number,
                message_text=text_body,
                contact_name=contact_name,
                message_id=message_id
            )
            
            # Send response
            if response:
                await whatsapp_client.send_text_message(from_number, response)
        
        elif message_type == "interactive":
            # Handle button/list responses
            interactive = message.get("interactive", {})
            button_reply = interactive.get("button_reply", {})
            list_reply = interactive.get("list_reply", {})
            
            logger.info(f"🔘 Interactive message: button={button_reply}, list={list_reply}")
            
            # TODO: Handle interactive responses
            await whatsapp_client.send_text_message(
                from_number,
                "Gracias por tu respuesta. Estamos procesando tu solicitud."
            )
        
        else:
            logger.info(f"ℹ️ Unsupported message type: {message_type}")
            await whatsapp_client.send_text_message(
                from_number,
                "Disculpa, solo puedo procesar mensajes de texto por ahora. ¿En qué puedo ayudarte?"
            )
    
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        import traceback
        traceback.print_exc()



