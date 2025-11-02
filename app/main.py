"""
FastAPI main application
"""
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
import logging

from app.config import get_settings
from app.whatsapp.webhook import handle_webhook, verify_webhook
from app.bot.conversation import ConversationManager
from app.db.queries import get_recent_conversations

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

# Initialize conversation manager
conversation_manager = ConversationManager()


@app.get("/")
async def root():
    """Health check endpoint"""
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


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development"
    )



