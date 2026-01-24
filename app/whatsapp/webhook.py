"""
WhatsApp webhook handler
"""
import logging
from typing import Dict, Any, Optional

from app.whatsapp.client import whatsapp_client
from app.db.queries import save_conversation
from app.db.leads import increment_unread_count

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
            
            # ALWAYS send email notification for incoming messages (even if bot is disabled)
            try:
                await conversation_manager._send_incoming_message_email(
                    contact_name=contact_name,
                    phone_number=from_number,
                    message_text=text_body,
                    message_id=message_id
                )
            except Exception as email_error:
                logger.warning(f"Could not send email notification: {email_error}")
            
            # Check if bot is enabled for this user
            from app.db.leads import get_or_create_lead
            lead = await get_or_create_lead(from_number, contact_name)
            bot_enabled = lead.get("bot_enabled", True) if lead else True
            
            if not bot_enabled:
                logger.info(f"🤐 Bot disabled for {from_number}, saving message but not responding")
                # Save incoming message only, no bot response
                try:
                    await save_conversation(
                        phone_number=from_number,
                        customer_name=contact_name,
                        message_text=text_body,
                        response_text="",
                        message_type="text",
                        message_id=message_id,
                        direction="incoming"
                    )
                    # Increment unread counter for incoming message
                    await increment_unread_count(from_number)
                except Exception as e:
                    logger.warning(f"Could not save conversation: {e}")
                return  # Exit early, no bot response
            
            # Process the message with conversation manager
            try:
                response = await conversation_manager.process_message(
                    from_number=from_number,
                    message_text=text_body,
                    contact_name=contact_name,
                    message_id=message_id
                )
            except Exception as e:
                logger.error(f"Error in conversation_manager.process_message: {e}")
                import traceback
                traceback.print_exc()
                # Send error message to user
                response = "🥬 ¡Ahoy, grumete! ⚓ Disculpa, estoy teniendo problemas técnicos. ¿Podrías intentar de nuevo en un momento?"
            
            response_text = None
            manual_handover_only = False
            
            # Send response (handle both text and accommodations with images)
            if isinstance(response, dict) and response.get("type") == "manual_override":
                logger.info(f"Manual handover active for {from_number}; skipping bot reply")
                manual_handover_only = True
            elif isinstance(response, dict) and response.get("type") == "accommodations":
                # Send accommodations with images
                logger.info("Sending accommodations response with images")
                
                # First send the text introduction
                await whatsapp_client.send_text_message(from_number, response["text"])
                
                # Then send images with captions
                import asyncio
                for item in response["images"]:
                    if item["type"] == "text":
                        await whatsapp_client.send_text_message(from_number, item["content"])
                    elif item["type"] == "image":
                        caption = item.get("caption", "")
                        image_path = item.get("image_path")
                        image_url = item.get("image_url")
                        
                        # Try to send using local file first (more reliable)
                        if image_path and image_path.startswith("http"):
                            # It's a URL, not a path
                            image_path = None
                        
                        sent = False
                        if image_path:
                            try:
                                # Upload to WhatsApp and send
                                logger.info(f"Uploading image from local path: {image_path}")
                                media_id = await whatsapp_client.upload_media(image_path)
                                if media_id:
                                    await whatsapp_client.send_image_message(
                                        from_number,
                                        media_id=media_id,
                                        caption=caption
                                    )
                                    sent = True
                                    logger.info(f"✅ Image sent successfully using media_id")
                            except Exception as e:
                                logger.warning(f"Failed to send image via upload: {e}, trying URL fallback")
                        
                        # Fallback to URL if local upload failed or not available
                        if not sent and image_url and not image_url.startswith("https://example.com"):
                            try:
                                await whatsapp_client.send_image_message(
                                    from_number,
                                    image_url=image_url,
                                    caption=caption
                                )
                                sent = True
                                logger.info(f"✅ Image sent successfully using URL")
                            except Exception as e:
                                logger.warning(f"Failed to send image via URL: {e}")
                        
                        # If both failed, send caption as text
                        if not sent:
                            logger.warning("Could not send image, sending caption as text")
                            await whatsapp_client.send_text_message(from_number, caption)
                        
                        # Small delay between images to avoid rate limiting
                        await asyncio.sleep(0.5)
                
                # Store text response for database
                response_text = response["text"]
            elif response:
                # Regular text response
                await whatsapp_client.send_text_message(from_number, response)
                response_text = response
            
            # Save conversation to database when we either responded or explicitly skipped due to manual handover
            if response_text is not None or manual_handover_only:
                try:
                    text_to_save = response_text if response_text is not None else ""
                    await save_conversation(
                        phone_number=from_number,
                        customer_name=contact_name,
                        message_text=text_body,
                        response_text=text_to_save,
                        message_type=message_type,
                        message_id=message_id,
                        direction="incoming"
                    )
                    # Increment unread counter for incoming message
                    await increment_unread_count(from_number)
                except Exception as e:
                    logger.warning(f"Could not save conversation: {e}")
        
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
        
        elif message_type == "image":
            image_obj = message.get("image", {}) or {}
            caption = (image_obj.get("caption") or "").strip()
            media_id = image_obj.get("id")
            logger.info(f"🖼️ Image message received (media_id={media_id}) caption='{caption}'")
            media_url = None
            local_image_path = None
            
            try:
                if media_id:
                    # Try to download and save the image locally
                    from app.utils.media_handler import get_received_media_path
                    local_image_path = get_received_media_path(media_id)
                    download_success = await whatsapp_client.download_media(media_id, local_image_path)
                    if download_success:
                        logger.info(f"✅ Image downloaded and saved: {local_image_path}")
                    else:
                        local_image_path = None
                    
                    # Also get the URL for fallback
                    media_url = await whatsapp_client.get_media_url(media_id)
                    logger.info(f"Media URL fetched for {media_id}: {bool(media_url)}")
            except Exception as e:
                logger.warning(f"Could not fetch/download media for {media_id}: {e}")
            
            display_url = None
            if local_image_path:
                # Use API endpoint, not local path (frontend can't access local: prefix)
                display_url = f"/api/media/{media_id}"
            elif media_id:
                display_url = f"/api/media/{media_id}"
            elif media_url:
                display_url = media_url
            
            text_body = caption if caption else "[Imagen sin texto]"
            
            # ALWAYS send email notification for incoming images (even if bot is disabled)
            try:
                await conversation_manager._send_incoming_message_email(
                    contact_name=contact_name,
                    phone_number=from_number,
                    message_text=f"🖼️ [Imagen] {text_body}",
                    message_id=message_id
                )
            except Exception as email_error:
                logger.warning(f"Could not send email notification for image: {email_error}")
            
            # Check if bot is enabled for this user
            from app.db.leads import get_or_create_lead
            lead = await get_or_create_lead(from_number, contact_name)
            bot_enabled = lead.get("bot_enabled", True) if lead else True
            
            if not bot_enabled:
                logger.info(f"🤐 Bot disabled for {from_number}, saving image but not responding")
                try:
                    if display_url:
                        await save_conversation(
                            phone_number=from_number,
                            customer_name=contact_name,
                            message_text=text_body,
                            response_text=display_url,
                            message_type="image",
                            message_id=message_id,
                            direction="incoming"
                        )
                        # Increment unread counter for incoming image
                        await increment_unread_count(from_number)
                except Exception as e:
                    logger.warning(f"Could not save image conversation: {e}")
                return  # Exit early, no bot response
            
            try:
                response = await conversation_manager.process_message(
                    from_number=from_number,
                    message_text=text_body,
                    contact_name=contact_name,
                    message_id=message_id
                )
            except Exception as e:
                logger.error(f"Error in conversation_manager.process_message for image: {e}")
                import traceback
                traceback.print_exc()
                response = "📸 ¡Recibimos tu imagen! Gracias 🙌"
            
            response_text = None
            manual_handover_only = False
            
            if isinstance(response, dict) and response.get("type") == "manual_override":
                logger.info(f"Manual handover active for {from_number}; skipping bot reply (image)")
                manual_handover_only = True
            elif isinstance(response, dict) and response.get("type") == "accommodations":
                logger.info("Sending accommodations response with images (triggered by image message)")
                
                await whatsapp_client.send_text_message(from_number, response["text"])
                
                import asyncio
                for item in response["images"]:
                    if item["type"] == "text":
                        await whatsapp_client.send_text_message(from_number, item["content"])
                    elif item["type"] == "image":
                        caption = item.get("caption", "")
                        image_path = item.get("image_path")
                        image_url = item.get("image_url")
                        
                        # Try to send using local file first (more reliable)
                        if image_path and image_path.startswith("http"):
                            # It's a URL, not a path
                            image_path = None
                        
                        sent = False
                        if image_path:
                            try:
                                # Upload to WhatsApp and send
                                logger.info(f"Uploading image from local path: {image_path}")
                                media_id = await whatsapp_client.upload_media(image_path)
                                if media_id:
                                    await whatsapp_client.send_image_message(
                                        from_number,
                                        media_id=media_id,
                                        caption=caption
                                    )
                                    sent = True
                                    logger.info(f"✅ Image sent successfully using media_id")
                            except Exception as e:
                                logger.warning(f"Failed to send image via upload: {e}, trying URL fallback")
                        
                        # Fallback to URL if local upload failed or not available
                        if not sent and image_url and not image_url.startswith("https://example.com"):
                            try:
                                await whatsapp_client.send_image_message(
                                    from_number,
                                    image_url=image_url,
                                    caption=caption
                                )
                                sent = True
                                logger.info(f"✅ Image sent successfully using URL")
                            except Exception as e:
                                logger.warning(f"Failed to send image via URL: {e}")
                        
                        # If both failed, send caption as text
                        if not sent:
                            logger.warning("Could not send image, sending caption as text")
                            await whatsapp_client.send_text_message(from_number, caption)
                        
                        await asyncio.sleep(0.5)
                
                response_text = response["text"]
            elif response:
                await whatsapp_client.send_text_message(from_number, response)
                response_text = response
            
            if response_text is not None or manual_handover_only:
                try:
                    text_to_save = response_text if response_text is not None else ""
                    if display_url:
                        text_to_save = display_url
                    await save_conversation(
                        phone_number=from_number,
                        customer_name=contact_name,
                        message_text=text_body,
                        response_text=text_to_save,
                        message_type="image",
                        message_id=message_id,
                        direction="incoming"
                    )
                    # Increment unread counter for incoming image
                    await increment_unread_count(from_number)
                except Exception as e:
                    logger.warning(f"Could not save image conversation: {e}")
        
        elif message_type == "audio":
            audio_obj = message.get("audio", {}) or {}
            media_id = audio_obj.get("id")
            mime_type = audio_obj.get("mime_type", "audio/ogg")
            logger.info(f"🎤 Audio message received (media_id={media_id}) mime_type='{mime_type}'")
            
            media_url = None
            local_audio_path = None
            
            try:
                if media_id:
                    # Try to download and save the audio locally
                    from app.utils.media_handler import get_received_media_path
                    
                    # Determine extension from mime_type
                    extension = "ogg"  # Default for WhatsApp
                    if "mp3" in mime_type:
                        extension = "mp3"
                    elif "mp4" in mime_type or "m4a" in mime_type:
                        extension = "m4a"
                    elif "wav" in mime_type:
                        extension = "wav"
                    
                    local_audio_path = get_received_media_path(media_id, extension=extension, media_type="audio")
                    download_success = await whatsapp_client.download_media(media_id, local_audio_path)
                    if download_success:
                        logger.info(f"✅ Audio downloaded and saved: {local_audio_path}")
                    else:
                        local_audio_path = None
                    
                    # Also get the URL for fallback
                    media_url = await whatsapp_client.get_media_url(media_id)
                    logger.info(f"Media URL fetched for audio {media_id}: {bool(media_url)}")
            except Exception as e:
                logger.warning(f"Could not fetch/download audio for {media_id}: {e}")
            
            display_url = None
            if local_audio_path:
                display_url = f"/api/media/{media_id}"
            elif media_id:
                display_url = f"/api/media/{media_id}"
            elif media_url:
                display_url = media_url
            
            text_body = "[Audio recibido]"
            
            # ALWAYS send email notification for incoming audios (even if bot is disabled)
            try:
                await conversation_manager._send_incoming_message_email(
                    contact_name=contact_name,
                    phone_number=from_number,
                    message_text=f"🎤 {text_body}",
                    message_id=message_id
                )
            except Exception as email_error:
                logger.warning(f"Could not send email notification for audio: {email_error}")
            
            # Check if bot is enabled for this user
            from app.db.leads import get_or_create_lead
            lead = await get_or_create_lead(from_number, contact_name)
            bot_enabled = lead.get("bot_enabled", True) if lead else True
            
            if not bot_enabled:
                logger.info(f"🤐 Bot disabled for {from_number}, saving audio but not responding")
                try:
                    if display_url:
                        await save_conversation(
                            phone_number=from_number,
                            customer_name=contact_name,
                            message_text=text_body,
                            response_text=display_url,
                            message_type="audio",
                            message_id=message_id,
                            direction="incoming"
                        )
                        # Increment unread counter for incoming audio
                        await increment_unread_count(from_number)
                except Exception as e:
                    logger.warning(f"Could not save audio conversation: {e}")
                return  # Exit early, no bot response
            
            # Process the audio message
            try:
                # For now, respond acknowledging the audio
                response = await conversation_manager.process_message(
                    from_number=from_number,
                    message_text="[El usuario envió un audio]",
                    contact_name=contact_name,
                    message_id=message_id
                )
            except Exception as e:
                logger.error(f"Error in conversation_manager.process_message for audio: {e}")
                import traceback
                traceback.print_exc()
                response = "🎤 ¡Recibimos tu audio! Gracias por tu mensaje 🙌"
            
            response_text = None
            manual_handover_only = False
            
            if isinstance(response, dict) and response.get("type") == "manual_override":
                logger.info(f"Manual handover active for {from_number}; skipping bot reply (audio)")
                manual_handover_only = True
            elif isinstance(response, dict) and response.get("type") == "accommodations":
                logger.info("Sending accommodations response with images (triggered by audio message)")
                
                await whatsapp_client.send_text_message(from_number, response["text"])
                
                import asyncio
                for item in response["images"]:
                    if item["type"] == "text":
                        await whatsapp_client.send_text_message(from_number, item["content"])
                    elif item["type"] == "image":
                        caption = item.get("caption", "")
                        image_path = item.get("image_path")
                        image_url = item.get("image_url")
                        
                        if image_path and image_path.startswith("http"):
                            image_path = None
                        
                        sent = False
                        if image_path:
                            try:
                                logger.info(f"Uploading image from local path: {image_path}")
                                media_id = await whatsapp_client.upload_media(image_path)
                                if media_id:
                                    await whatsapp_client.send_image_message(
                                        from_number,
                                        media_id=media_id,
                                        caption=caption
                                    )
                                    sent = True
                                    logger.info(f"✅ Image sent successfully using media_id")
                            except Exception as e:
                                logger.warning(f"Failed to send image via upload: {e}, trying URL fallback")
                        
                        if not sent and image_url and not image_url.startswith("https://example.com"):
                            try:
                                await whatsapp_client.send_image_message(
                                    from_number,
                                    image_url=image_url,
                                    caption=caption
                                )
                                sent = True
                                logger.info(f"✅ Image sent successfully using URL")
                            except Exception as e:
                                logger.warning(f"Failed to send image via URL: {e}")
                        
                        if not sent:
                            logger.warning("Could not send image, sending caption as text")
                            await whatsapp_client.send_text_message(from_number, caption)
                        
                        await asyncio.sleep(0.5)
                
                response_text = response["text"]
            elif response:
                await whatsapp_client.send_text_message(from_number, response)
                response_text = response
            
            if response_text is not None or manual_handover_only:
                try:
                    text_to_save = response_text if response_text is not None else ""
                    if display_url:
                        text_to_save = display_url
                    await save_conversation(
                        phone_number=from_number,
                        customer_name=contact_name,
                        message_text=text_body,
                        response_text=text_to_save,
                        message_type="audio",
                        message_id=message_id,
                        direction="incoming"
                    )
                    # Increment unread counter for incoming audio
                    await increment_unread_count(from_number)
                except Exception as e:
                    logger.warning(f"Could not save audio conversation: {e}")
        
        else:
            logger.info(f"ℹ️ Unsupported message type: {message_type}")
            await whatsapp_client.send_text_message(
                from_number,
                "Disculpa, solo puedo procesar mensajes de texto, imágenes y audios por ahora. ¿En qué puedo ayudarte?"
            )
    
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        import traceback
        traceback.print_exc()








