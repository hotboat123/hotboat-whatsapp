"""
FastAPI main application
"""
from fastapi import FastAPI, Request, Response, HTTPException, Query, UploadFile, Form
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import logging
import httpx

from app.config import get_settings
from app.whatsapp.webhook import handle_webhook, verify_webhook
from app.whatsapp.client import whatsapp_client
from app.bot.conversation import ConversationManager
from app.db.queries import get_recent_conversations, get_appointments_between_dates, save_conversation
from app.db.leads import (
    get_or_create_lead, 
    update_lead_status, 
    get_leads_by_status,
    get_conversation_history,
    import_conversation_batch
)
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pydantic import BaseModel
from typing import List, Optional

# Chilean timezone
CHILE_TZ = ZoneInfo("America/Santiago")
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get settings
settings = get_settings()

# Create FastAPI app
app = FastAPI(
    title="HotBoat WhatsApp Bot",
    description="Bot de WhatsApp para Hot Boat Chile",
    version="1.0.0"
)

# Mount static files for Kia-Ai interface
static_dir = os.path.join(os.path.dirname(__file__), "static")
logger.info(f"📁 Static directory expected at: {static_dir}")
if os.path.exists(static_dir):
    logger.info(f"✅ Static directory found with files: {os.listdir(static_dir)}")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
else:
    logger.warning("⚠️ Static directory not found – Kia-Ai UI will not be served.")

# Initialize conversation manager
conversation_manager = ConversationManager()


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve Kia-Ai chat interface"""
    try:
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        index_path = os.path.join(static_dir, "index.html")
        
        if os.path.exists(index_path):
            logger.info(f"🖥️ Serving Kia-Ai interface from {index_path}")
            with open(index_path, 'r', encoding='utf-8') as f:
                return HTMLResponse(content=f.read())
        else:
            logger.warning("⚠️ Kia-Ai interface not found, returning default health response.")
            return {
                "status": "ok",
                "service": "HotBoat WhatsApp Bot",
                "version": "1.0.0",
                "note": "Kia-Ai interface not found. API is working."
            }
    except Exception as e:
        logger.error(f"Error serving index: {e}")
        return {
            "status": "ok",
            "service": "HotBoat WhatsApp Bot",
            "version": "1.0.0"
        }


@app.get("/health")
async def health():
    """Detailed health check"""
    return {
        "status": "healthy",
        "database": "connected",  # TODO: Add real DB check
        "whatsapp_api": "configured"
    }


@app.get("/webhook")
async def webhook_verify(request: Request):
    """
    Webhook verification endpoint for WhatsApp
    Meta will call this to verify the webhook
    """
    try:
        # Get query parameters
        mode = request.query_params.get("hub.mode")
        token = request.query_params.get("hub.verify_token")
        challenge = request.query_params.get("hub.challenge")
        
        logger.info(f"Webhook verification request: mode={mode}, token={'***' if token else None}")
        
        # Verify the request
        if verify_webhook(mode, token, settings.whatsapp_verify_token):
            logger.info("✅ Webhook verified successfully")
            return Response(content=challenge, media_type="text/plain")
        else:
            logger.warning("❌ Webhook verification failed")
            raise HTTPException(status_code=403, detail="Verification failed")
            
    except Exception as e:
        logger.error(f"Error in webhook verification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/webhook")
async def webhook_receive(request: Request):
    """
    Webhook endpoint to receive WhatsApp messages
    """
    try:
        # Get the request body
        body = await request.json()
        
        logger.info(f"📩 Received webhook: {body}")
        
        # Process the webhook
        result = await handle_webhook(body, conversation_manager)
        
        # WhatsApp expects a 200 OK response quickly
        return JSONResponse(content={"status": "ok"}, status_code=200)
        
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        # Still return 200 to WhatsApp to avoid retries
        return JSONResponse(content={"status": "error", "message": str(e)}, status_code=200)


@app.get("/conversations")
async def list_conversations(limit: int = 50):
    """List recent conversations (for admin dashboard)"""
    try:
        conversations = await get_recent_conversations(limit=limit)
        return {
            "conversations": conversations,
            "total": len(conversations)
        }
    except Exception as e:
        logger.error(f"Error listing conversations: {e}")
        return {
            "conversations": [],
            "total": 0,
            "error": str(e)
        }


@app.get("/appointments")
async def list_appointments(days_ahead: int = 30):
    """List appointments for the next N days"""
    try:
        start_date = datetime.now(CHILE_TZ)
        end_date = start_date + timedelta(days=days_ahead)
        appointments = await get_appointments_between_dates(start_date, end_date)
        return {
            "appointments": appointments,
            "total": len(appointments),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat()
        }
    except Exception as e:
        logger.error(f"Error listing appointments: {e}")
        return {
            "appointments": [],
            "total": 0,
            "error": str(e)
        }


# Leads Management Endpoints

@app.get("/leads")
async def list_leads(lead_status: Optional[str] = None, limit: int = 50):
    """List leads, optionally filtered by status"""
    try:
        leads = await get_leads_by_status(lead_status=lead_status, limit=limit)
        return {
            "leads": leads,
            "total": len(leads),
            "filter": lead_status if lead_status else "all"
        }
    except Exception as e:
        logger.error(f"Error listing leads: {e}")
        return {
            "leads": [],
            "total": 0,
            "error": str(e)
        }


@app.get("/leads/{phone_number}")
async def get_lead_info(phone_number: str):
    """Get lead information and conversation history"""
    try:
        lead = await get_or_create_lead(phone_number)
        history = await get_conversation_history(phone_number, limit=100)
        
        return {
            "lead": lead,
            "conversation_count": len(history),
            "recent_messages": history[-10:] if history else []  # Last 10 messages
        }
    except Exception as e:
        logger.error(f"Error getting lead info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class LeadStatusUpdate(BaseModel):
    lead_status: str  # 'potential_client', 'bad_lead', 'customer', 'unknown'
    notes: Optional[str] = None


@app.put("/leads/{phone_number}/status")
async def update_lead(phone_number: str, update: LeadStatusUpdate):
    """Update lead classification status"""
    try:
        success = await update_lead_status(
            phone_number=phone_number,
            lead_status=update.lead_status,
            notes=update.notes
        )
        
        if success:
            return {
                "status": "updated",
                "phone_number": phone_number,
                "lead_status": update.lead_status
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to update lead status")
    except Exception as e:
        logger.error(f"Error updating lead status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ConversationImport(BaseModel):
    phone_number: str
    customer_name: Optional[str] = None
    conversations: List[dict]  # List of {message, response, timestamp, direction, message_id}


@app.post("/import/conversations")
async def import_conversations(data: ConversationImport):
    """Import existing conversation history"""
    try:
        imported_count = await import_conversation_batch(
            conversations=data.conversations,
            phone_number=data.phone_number,
            customer_name=data.customer_name
        )
        
        return {
            "status": "success",
            "phone_number": data.phone_number,
            "imported": imported_count,
            "total": len(data.conversations)
        }
    except Exception as e:
        logger.error(f"Error importing conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Kia-Ai API Endpoints

@app.get("/api/conversations")
async def get_conversations_list(limit: int = 50):
    """Get list of all conversations with latest messages"""
    try:
        conversations = await get_recent_conversations(limit=limit)
        return {
            "conversations": conversations,
            "total": len(conversations)
        }
    except Exception as e:
        logger.error(f"Error getting conversations: {e}")
        return {
            "conversations": [],
            "total": 0,
            "error": str(e)
        }


@app.get("/api/conversations/{phone_number}")
async def get_conversation_detail(
    phone_number: str,
    limit: int = Query(50, ge=1, le=500),
    before: Optional[str] = None
):
    """Get full conversation history for a specific phone number with optional pagination"""
    try:
        lead = await get_or_create_lead(phone_number)
        
        before_dt = None
        if before:
            try:
                before_dt = datetime.fromisoformat(before)
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid 'before' timestamp format.")
        
        messages_result = await get_conversation_history(
            phone_number,
            limit=limit,
            before=before_dt,
            return_has_more=True
        )
        
        if isinstance(messages_result, tuple):
            messages, has_more, next_cursor = messages_result
        else:
            messages = messages_result
            has_more = False
            next_cursor = None
        
        return {
            "lead": lead,
            "messages": messages,
            "total_messages": len(messages),
            "has_more": has_more,
            "next_cursor": next_cursor
        }
    except Exception as e:
        logger.error(f"Error getting conversation detail: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SendMessageRequest(BaseModel):
    to: str  # Phone number with country code (no +)
    message: Optional[str] = None
    type: str = "text"  # "text" or "image"
    image_url: Optional[str] = None
    caption: Optional[str] = None


@app.post("/api/send-message")
async def send_custom_message(request: SendMessageRequest):
    """Send a custom WhatsApp message through Kia-Ai"""
    try:
        # Validate inputs
        if not request.to:
            raise HTTPException(status_code=400, detail="Phone number is required")
        
        is_image = (request.type or "text").lower() == "image" or bool(request.image_url)
        
        if is_image:
            if not request.image_url:
                raise HTTPException(status_code=400, detail="image_url is required for image messages")
            if request.message and len(request.message) > 4096:
                raise HTTPException(status_code=400, detail="Caption too long (max 4096 characters)")
        else:
            if not request.message:
                raise HTTPException(status_code=400, detail="Message is required for text messages")
            if len(request.message) > 4096:
                raise HTTPException(status_code=400, detail="Message too long (max 4096 characters)")
        
        # Preload lead info (used for logging and manual handover activation)
        lead = None
        try:
            lead = await get_or_create_lead(request.to)
        except Exception as lead_error:
            logger.error(f"Error loading lead before send: {lead_error}")
            # Continue even if lead lookup fails
        
        message_id = ""
        result = {}
        message_type = "text"
        
        if is_image:
            caption = request.caption or request.message or ""
            result = await whatsapp_client.send_image_message(request.to, request.image_url, caption=caption or None)
            message_id = result.get('messages', [{}])[0].get('id', '')
            message_type = "image"
        else:
            result = await whatsapp_client.send_text_message(request.to, request.message)
            message_id = result.get('messages', [{}])[0].get('id', '')
            message_type = "text"
        
        # If this is the manual handover trigger, silence the bot for this conversation
        try:
            trigger_text = request.message or request.caption or ""
            if trigger_text and conversation_manager.is_manual_handover_trigger(trigger_text):
                await conversation_manager.activate_manual_handover(
                    phone_number=request.to,
                    contact_name=lead.get('customer_name', request.to) if lead else request.to
                )
                logger.info(f"Manual handover activated for {request.to} via custom message trigger")
        except Exception as handover_error:
            logger.warning(f"Could not activate manual handover for {request.to}: {handover_error}")
        
        # Log in database
        try:
            await save_conversation(
                phone_number=request.to,
                customer_name=lead.get('customer_name', request.to) if lead else request.to,
                message_text=(request.caption or request.message or "") if message_type == "image" else '',
                response_text=(request.image_url or request.caption or request.message or ""),
                message_type=message_type,
                message_id=message_id or None,
                direction='outgoing'
            )
        except Exception as db_error:
            logger.error(f"Error storing message in DB: {db_error}")
            # Don't fail the request if DB logging fails
        
        return {
            "status": "sent",
            "to": request.to,
            "message_id": message_id,
            "details": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending custom message: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send message: {str(e)}")


@app.post("/api/upload-and-send-image")
async def upload_and_send_image(
    image: UploadFile,
    to: str = Form(...),
    caption: Optional[str] = Form(None)
):
    """
    Upload an image file and send it via WhatsApp
    
    Args:
        image: Image file to upload
        to: Recipient phone number
        caption: Optional caption for the image
    """
    try:
        # Validate inputs
        if not to:
            raise HTTPException(status_code=400, detail="Phone number is required")
        
        if not image:
            raise HTTPException(status_code=400, detail="Image file is required")
        
        # Validate file type
        if not image.content_type or not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Validate file size (5MB limit)
        contents = await image.read()
        if len(contents) > 5 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Image too large (max 5MB)")
        
        # Save temporarily
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(image.filename)[1]) as temp_file:
            temp_file.write(contents)
            temp_path = temp_file.name
        
        try:
            # Upload to WhatsApp
            logger.info(f"Uploading image {image.filename} to WhatsApp...")
            media_id = await whatsapp_client.upload_media(temp_path, image.content_type)
            
            if not media_id:
                raise HTTPException(status_code=500, detail="Failed to upload image to WhatsApp")
            
            logger.info(f"✅ Image uploaded successfully, media_id: {media_id}")
            
            # Send image message
            result = await whatsapp_client.send_image_message(
                to=to,
                media_id=media_id,
                caption=caption
            )
            
            message_id = result.get('messages', [{}])[0].get('id', '')
            
            # Get lead info
            lead = None
            try:
                lead = await get_or_create_lead(to)
            except Exception as lead_error:
                logger.error(f"Error loading lead: {lead_error}")
            
            # Log in database
            try:
                # Save with the media URL so it can be displayed in the interface
                media_url = f"/api/media/{media_id}"
                await save_conversation(
                    phone_number=to,
                    customer_name=lead.get('customer_name', to) if lead else to,
                    message_text=caption or '',
                    response_text=media_url,
                    message_type="image",
                    message_id=message_id or None,
                    direction='outgoing'
                )
            except Exception as db_error:
                logger.error(f"Error storing message in DB: {db_error}")
            
            return {
                "status": "sent",
                "to": to,
                "message_id": message_id,
                "media_id": media_id,
                "media_url": media_url,
                "details": result
            }
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_path)
            except Exception:
                pass
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading and sending image: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to send image: {str(e)}")


@app.get("/api/media/{media_id}")
async def proxy_media(media_id: str):
    """
    Serve media file from local storage or proxy from WhatsApp.
    Priority: Local file > Download from WhatsApp > Direct proxy
    """
    if not media_id:
        raise HTTPException(status_code=400, detail="media_id is required")
    
    try:
        from pathlib import Path
        from fastapi.responses import FileResponse
        
        # Get absolute path to media directory
        base_dir = Path(__file__).parent.parent  # Go up to project root
        media_dir = base_dir / "media" / "received"
        
        logger.info(f"Looking for media {media_id} in {media_dir}")
        
        # First, try to find the file locally in received directory
        if media_dir.exists():
            # Look for files that start with the media_id
            for file_path in media_dir.glob(f"{media_id}_*.*"):
                if file_path.is_file():
                    logger.info(f"✅ Serving media from local file: {file_path}")
                    
                    # Determine content type from extension
                    ext = file_path.suffix.lower()
                    content_type_map = {
                        ".jpg": "image/jpeg",
                        ".jpeg": "image/jpeg",
                        ".png": "image/png",
                        ".webp": "image/webp",
                        ".gif": "image/gif",
                        ".mp4": "video/mp4",
                    }
                    content_type = content_type_map.get(ext, "application/octet-stream")
                    
                    # Return the file
                    return FileResponse(
                        path=str(file_path),
                        media_type=content_type,
                        filename=file_path.name
                    )
        else:
            logger.warning(f"Media directory does not exist: {media_dir}")
            # Create it
            media_dir.mkdir(parents=True, exist_ok=True)
        
        # If not found locally, try to download it from WhatsApp first
        logger.info(f"📥 Media not found locally, attempting to download from WhatsApp: {media_id}")
        from app.utils.media_handler import get_received_media_path
        local_path = get_received_media_path(media_id)
        
        download_success = await whatsapp_client.download_media(media_id, local_path)
        if download_success and os.path.exists(local_path):
            logger.info(f"✅ Media downloaded successfully, serving from: {local_path}")
            
            # Determine content type
            ext = Path(local_path).suffix.lower()
            content_type_map = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
                ".gif": "image/gif",
                ".mp4": "video/mp4",
            }
            content_type = content_type_map.get(ext, "image/jpeg")
            
            return FileResponse(
                path=local_path,
                media_type=content_type,
                filename=os.path.basename(local_path)
            )
        
        # Last resort: try to proxy directly from WhatsApp (legacy behavior)
        logger.warning(f"⚠️ Could not download media, attempting direct proxy from WhatsApp: {media_id}")
        media_url = await whatsapp_client.get_media_url(media_id)
        if not media_url:
            logger.error(f"❌ Could not get media URL from WhatsApp for {media_id}")
            raise HTTPException(status_code=404, detail="Media not found - URL unavailable")
        
        logger.info(f"Attempting to proxy from: {media_url[:100]}...")
        async with httpx.AsyncClient() as client:
            resp = await client.get(media_url, timeout=30)
            if resp.status_code != 200:
                logger.error(f"❌ Failed to fetch media {media_id}: HTTP {resp.status_code}")
                raise HTTPException(status_code=404, detail=f"Media fetch failed: HTTP {resp.status_code}")
            
            content_type = resp.headers.get("content-type", "application/octet-stream")
            logger.info(f"✅ Successfully proxied media from WhatsApp")
            return StreamingResponse(iter([resp.content]), media_type=content_type)
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error serving media {media_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching media: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development"
    )








