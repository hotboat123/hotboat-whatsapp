"""
FastAPI main application - Updated 2026-03-08
"""
from fastapi import FastAPI, Request, Response, HTTPException, Query, UploadFile, Form
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import asyncio
import logging
import httpx

from app.booking.router import router as booking_router
from app.booking.admin_router import admin_router
from app.config import get_settings
from app.whatsapp.webhook import handle_webhook, verify_webhook
from app.whatsapp.client import whatsapp_client
from app.bot.conversation import ConversationManager
from app.db.queries import get_recent_conversations, get_appointments_between_dates, save_conversation, search_conversations_by_phone, search_messages_in_all_conversations_sync
from app.db.leads import (
    get_or_create_lead, 
    update_lead_status, 
    get_leads_by_status,
    get_conversation_history,
    import_conversation_batch,
    mark_conversation_as_read,
    update_lead_priority
)
from app.notifications import push_notifier
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pydantic import BaseModel
from typing import List, Optional, Dict

# Chilean timezone
CHILE_TZ = ZoneInfo("America/Santiago")
import os

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Reduce httpx logging noise (403 errors from expired media)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Get settings
settings = get_settings()

# ── Auto-sync background task ──────────────────────────────────────────────────
SYNC_INTERVAL_MINUTES = 30

async def _run_auto_sync():
    """Run all_appointments sync every SYNC_INTERVAL_MINUTES minutes."""
    from app.db.connection import get_connection
    from app.booking.admin_router import TABLE
    import re

    await asyncio.sleep(60)  # Wait 1 min after startup before first sync
    while True:
        try:
            logger.info(f"🔄 Auto-sync: sincronizando all_appointments...")
            from psycopg.types.json import Jsonb as PgJson

            def normalize_phone(ph):
                if not ph: return None
                ph = re.sub(r"[^\d+]", "", str(ph))
                if ph.startswith("+"): return ph
                if len(ph) == 9: return f"+56{ph}"
                if len(ph) == 11 and ph.startswith("56"): return f"+{ph}"
                return ph

            inserted_reservas = 0
            updated_reservas = 0
            inserted_book = 0
            inserted_hb = 0
            status_updated = 0

            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT MAX(fecha) FROM reservas_con_extras")
                    cutoff = cur.fetchone()[0]
                    if not cutoff:
                        logger.warning("Auto-sync: reservas_con_extras is empty, skipping")
                        await asyncio.sleep(SYNC_INTERVAL_MINUTES * 60)
                        continue

                    # Sync reservas_con_extras → all_appointments (upsert)
                    cur.execute("""
                        SELECT id, appointment_id, fecha, hora, nombre_cliente, email, telefono,
                               servicio, num_personas, num_adultos, num_ninos,
                               ingreso_reserva, ingreso_extras, ingreso_total,
                               costo_operativo_fijo, costo_operativo_variable, costo_operativo_total,
                               ciudad_origen, como_supieron, clima_del_dia, categoria_clientes,
                               tipo_clientes, tiene_cruce, status, extras_json, created_at
                        FROM reservas_con_extras
                        ORDER BY fecha
                    """)
                    for row in cur.fetchall():
                        (rid, appt_id, fecha, hora, nombre, email, telefono,
                         servicio, num_p, num_adultos, num_ninos,
                         ing_res, ing_ext, ing_total, costo_fijo, costo_var, costo_total,
                         ciudad, como_sup, clima, categoria, tipo_cli, tiene_cruce,
                         status, extras, created) = row
                        cur.execute(f"SELECT id FROM {TABLE} WHERE source='sheets' AND source_id=%s", (str(rid),))
                        existing = cur.fetchone()
                        if existing:
                            cur.execute(f"""
                                UPDATE {TABLE}
                                SET extras_json=%s, ingreso_extras=%s, ingreso_total=%s,
                                    num_adultos=%s, num_ninos=%s, ciudad_origen=%s,
                                    como_supieron=%s, clima_del_dia=%s, categoria_clientes=%s,
                                    tipo_clientes=%s, tiene_cruce=%s, status=%s, updated_at=NOW()
                                WHERE id=%s
                            """, (PgJson(extras or {}), float(ing_ext or 0), float(ing_total or 0),
                                  num_adultos, num_ninos, ciudad, como_sup, clima, categoria,
                                  tipo_cli, tiene_cruce, status, existing[0]))
                            updated_reservas += 1
                        else:
                            cur.execute(f"""
                                INSERT INTO {TABLE}
                                (source, source_id, appointment_id, fecha, hora,
                                 nombre_cliente, email, telefono, servicio, num_personas,
                                 num_adultos, num_ninos,
                                 ingreso_reserva, ingreso_extras, ingreso_total,
                                 costo_operativo_fijo, costo_operativo_variable, costo_operativo_total,
                                 ciudad_origen, como_supieron, clima_del_dia,
                                 categoria_clientes, tipo_clientes, tiene_cruce,
                                 status, extras_json, created_at, updated_at)
                                VALUES ('sheets',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                                ON CONFLICT DO NOTHING
                            """, (str(rid), str(appt_id) if appt_id else None,
                                  fecha, hora, nombre, email,
                                  re.sub(r"[^\d+]", "", str(telefono)) if telefono else None,
                                  servicio or "HotBoat", str(num_p) if num_p else None,
                                  num_adultos, num_ninos,
                                  float(ing_res or 0), float(ing_ext or 0), float(ing_total or 0),
                                  float(costo_fijo or 0), float(costo_var or 0), float(costo_total or 0),
                                  ciudad, como_sup, clima, categoria, tipo_cli, tiene_cruce,
                                  status, PgJson(extras or {}), created))
                            inserted_reservas += 1

                    # Remove duplicates (old Reservas_Con_Extras_Sheets rows replaced by reservas_con_extras)
                    cur.execute("""
                        DELETE FROM all_appointments
                        WHERE source = 'sheets' AND appointment_id IS NOT NULL
                        AND id NOT IN (
                            SELECT MAX(id) FROM all_appointments
                            WHERE source = 'sheets' AND appointment_id IS NOT NULL
                            GROUP BY appointment_id
                        )
                    """)
                    dedup_deleted = cur.rowcount

                    # Sync booknetic
                    cur.execute("""
                        SELECT id, customer_name, customer_email, starts_at, status, raw, created_at
                        FROM booknetic_appointments WHERE starts_at::date > %s
                    """, (cutoff,))
                    for row in cur.fetchall():
                        bid, nombre, email, starts_at, status, raw, created = row
                        raw = raw or {}
                        cur.execute(f"SELECT id, status FROM {TABLE} WHERE source='booknetic' AND source_id=%s", (str(bid),))
                        existing = cur.fetchone()
                        if existing:
                            if status and status != existing[1]:
                                cur.execute(f"UPDATE {TABLE} SET status=%s, updated_at=NOW() WHERE id=%s", (status, existing[0]))
                                status_updated += 1
                        else:
                            phone = normalize_phone(raw.get("phone") or raw.get("customer_phone") or raw.get("cf_phone"))
                            fecha = starts_at.date() if hasattr(starts_at, 'date') else starts_at
                            hora = starts_at.strftime("%H:%M") if hasattr(starts_at, 'strftime') else "10:00"
                            num_p = raw.get("num_people") or raw.get("persons") or 2
                            total = float(raw.get("total_price") or raw.get("total") or 0)
                            cur.execute(f"""
                                INSERT INTO {TABLE}
                                (source,source_id,booking_ref,fecha,hora,nombre_cliente,email,telefono,servicio,num_personas,ingreso_total,status,created_at)
                                VALUES ('booknetic',%s,%s,%s,%s,%s,%s,%s,'HotBoat Booknetic',%s,%s,%s,NOW())
                                ON CONFLICT DO NOTHING
                            """, (str(bid), f"BK-{bid}", fecha, hora, nombre, email, phone, str(num_p), total, status or "confirmed"))
                            inserted_book += 1

                    # Sync hotboat_web
                    cur.execute("""
                        SELECT booking_ref, customer_name, customer_email, customer_phone,
                               booking_date, booking_time, num_people,
                               subtotal, extras_total, total_price, extras, status,
                               payment_id, payment_status, notes, created_at
                        FROM hotboat_appointments
                        WHERE booking_date > %s AND status != 'solicitud'
                    """, (cutoff,))
                    for row in cur.fetchall():
                        (ref, nombre, email, phone, fecha, hora, num_p,
                         sub, ext, total, extras, status, pay_id, pay_st, notes, created) = row
                        cur.execute(f"SELECT id, status FROM {TABLE} WHERE source='hotboat_web' AND source_id=%s", (ref,))
                        existing = cur.fetchone()
                        if existing:
                            if status and status != existing[1]:
                                cur.execute(f"UPDATE {TABLE} SET status=%s, payment_status=%s, updated_at=NOW() WHERE id=%s",
                                            (status, pay_st, existing[0]))
                                status_updated += 1
                        else:
                            cur.execute(f"""
                                INSERT INTO {TABLE}
                                (source,source_id,booking_ref,fecha,hora,nombre_cliente,email,telefono,
                                 servicio,num_personas,ingreso_base,ingreso_extras,ingreso_total,
                                 status,extras_json,observaciones,payment_id,payment_status,created_at)
                                VALUES ('hotboat_web',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                                ON CONFLICT DO NOTHING
                            """, (ref, ref, fecha, hora, nombre, email, normalize_phone(phone),
                                  f"HotBoat Web ({num_p}p)", str(num_p),
                                  float(sub or 0), float(ext or 0), float(total or 0),
                                  status, PgJson(extras or {}), notes, pay_id, pay_st))
                            inserted_hb += 1

                    conn.commit()

            logger.info(f"✅ Auto-sync OK: reservas({inserted_reservas} nuevas/{updated_reservas} actualizadas/{dedup_deleted} dedup), +{inserted_book} booknetic, +{inserted_hb} web, {status_updated} estados")
        except Exception as e:
            logger.error(f"❌ Auto-sync error: {e}")

        await asyncio.sleep(SYNC_INTERVAL_MINUTES * 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start background tasks on startup, cancel on shutdown."""
    sync_task = asyncio.create_task(_run_auto_sync())
    logger.info(f"🕐 Auto-sync iniciado: cada {SYNC_INTERVAL_MINUTES} minutos")
    yield
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass
    logger.info("🛑 Auto-sync detenido")


# Create FastAPI app
app = FastAPI(
    title="HotBoat WhatsApp Bot",
    description="Bot de WhatsApp para Hot Boat Chile",
    version="1.0.0",
    lifespan=lifespan,
)

# Add middleware to prevent caching of static files
@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Mount static files for Kia-Ai interface
static_dir = os.path.join(os.path.dirname(__file__), "static")
logger.info(f"📁 Static directory expected at: {static_dir}")
if os.path.exists(static_dir):
    logger.info(f"✅ Static directory found with files: {os.listdir(static_dir)}")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")
else:
    logger.warning("⚠️ Static directory not found – Kia-Ai UI will not be served.")

# Serve media files (images, PDFs, docs) for booking platform
media_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media")
if os.path.exists(media_dir):
    app.mount("/media", StaticFiles(directory=media_dir), name="media")
    logger.info("✅ Media directory mounted at /media")

# Initialize conversation manager
conversation_manager = ConversationManager()
app.include_router(booking_router)
app.include_router(admin_router)


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
            environment_status = "🚀 PRODUCTION" if settings.is_production else "🧪 STAGING" if settings.is_staging else "💻 DEVELOPMENT"
            return {
                "status": "ok",
                "service": "HotBoat WhatsApp Bot",
                "version": "1.0.0",
                "environment": settings.environment,
                "environment_status": environment_status,
                "note": "Kia-Ai interface not found. API is working."
            }
    except Exception as e:
        logger.error(f"Error serving index: {e}")
        environment_status = "🚀 PRODUCTION" if settings.is_production else "🧪 STAGING" if settings.is_staging else "💻 DEVELOPMENT"
        return {
            "status": "ok",
            "service": "HotBoat WhatsApp Bot",
            "version": "1.0.0",
            "environment": settings.environment,
            "environment_status": environment_status
        }


@app.get("/health")
async def health():
    """Detailed health check"""
    environment_status = "🚀 PRODUCTION" if settings.is_production else "🧪 STAGING" if settings.is_staging else "💻 DEVELOPMENT"
    return {
        "status": "healthy",
        "environment": settings.environment,
        "environment_status": environment_status,
        "bot_name": settings.bot_name,
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


class BotToggleUpdate(BaseModel):
    bot_enabled: bool


@app.put("/leads/{phone_number}/bot-toggle")
async def toggle_bot_for_lead_endpoint(phone_number: str, update: BotToggleUpdate):
    """Enable or disable automatic bot responses for a specific lead"""
    try:
        from app.db.leads import toggle_bot_for_lead
        
        success = await toggle_bot_for_lead(
            phone_number=phone_number,
            bot_enabled=update.bot_enabled
        )
        
        if success:
            return {
                "status": "updated",
                "phone_number": phone_number,
                "bot_enabled": update.bot_enabled,
                "message": f"Bot {'enabled' if update.bot_enabled else 'disabled'} for {phone_number}"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to toggle bot for lead")
    except Exception as e:
        logger.error(f"Error toggling bot for lead: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.put("/api/conversations/{phone_number}/mark-read")
async def mark_conversation_read(phone_number: str):
    """Mark a conversation as read (reset unread counter)"""
    try:
        success = await mark_conversation_as_read(phone_number)
        
        if success:
            return {
                "status": "success",
                "phone_number": phone_number,
                "message": "Conversation marked as read"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to mark conversation as read")
    except Exception as e:
        logger.error(f"Error marking conversation as read: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class PriorityUpdate(BaseModel):
    priority: int  # 0 = none, 1 = high, 2 = medium, 3 = low


@app.put("/api/conversations/{phone_number}/priority")
async def update_conversation_priority(phone_number: str, update: PriorityUpdate):
    """Update conversation priority level"""
    try:
        success = await update_lead_priority(
            phone_number=phone_number,
            priority=update.priority
        )
        
        if success:
            return {
                "status": "success",
                "phone_number": phone_number,
                "priority": update.priority,
                "message": f"Priority updated to {update.priority}"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to update priority")
    except Exception as e:
        logger.error(f"Error updating priority: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class QuickReplyRequest(BaseModel):
    menu_option: int  # 1-5 for menu options


@app.post("/api/conversations/{phone_number}/quick-reply")
async def send_quick_reply(phone_number: str, request: QuickReplyRequest):
    """Send automatic menu response to conversation"""
    try:
        # Import here to avoid circular imports
        from app.bot.conversation import ConversationManager
        from app.bot.faq import FAQHandler
        from app.bot.translations import get_text
        
        # Initialize managers
        conv_manager = ConversationManager()
        faq_handler = FAQHandler()
        
        # Get lead info first (without updating name)
        lead = await get_or_create_lead(phone_number)
        customer_name = lead.get('customer_name', phone_number)
        
        # Get or create conversation with the correct customer name
        conversation = await conv_manager.get_conversation(phone_number, customer_name)
        language = conversation.get("metadata", {}).get("language", "es")
        
        # Determine response based on menu option
        response_text = ""
        menu_option = request.menu_option

        if menu_option == 0:
            # Saludo de Tomás — secuencia de 4 mensajes con pequeño delay entre cada uno
            import asyncio
            first_name = customer_name.split()[0] if customer_name else customer_name
            sequence = [
                f"Hola {first_name}! 👋",
                "Cómo estas?",
                "soy Tomás de Hotboat, soy humano 🙂",
                "Cualquier duda aquí estamos para ayudar 🙌",
            ]
            for i, msg in enumerate(sequence):
                if i > 0:
                    await asyncio.sleep(1.5)
                await whatsapp_client.send_text_message(to=phone_number, message=msg)
                await save_conversation(
                    phone_number=phone_number,
                    customer_name=customer_name,
                    message_text="",
                    response_text=msg,
                    message_type="text",
                    direction="outgoing"
                )
                conversation["messages"].append({
                    "role": "assistant",
                    "content": msg,
                    "timestamp": datetime.now(CHILE_TZ).isoformat()
                })
            conversation["last_interaction"] = datetime.now(CHILE_TZ).isoformat()
            return {
                "status": "success",
                "phone_number": phone_number,
                "menu_option": menu_option,
                "message_sent": f"Secuencia de {len(sequence)} mensajes enviada",
                "whatsapp_response": {}
            }
        elif menu_option == 1:
            # Disponibilidad y horarios
            response_text = conv_manager._ask_for_reservation_date(conversation, language)
        elif menu_option == 2:
            # Precios por persona
            response_text = faq_handler.get_response("precio", language)
        elif menu_option == 3:
            # Características del HotBoat
            response_text = faq_handler.get_response("caracteristicas", language)
        elif menu_option == 4:
            # Extras y promociones
            conversation["metadata"]["awaiting_extra_selection"] = True
            response_text = faq_handler.get_response("extras", language)
        elif menu_option == 5:
            # Ubicación y reseñas
            response_text = faq_handler.get_response("ubicación", language)
        elif menu_option == 9:
            # Solo alojamientos — equivale al flujo menú 7 → 2
            import asyncio
            from app.utils.media_handler import get_alojamientos_images
            text_intro = get_text("accommodations_only_intro", language)
            # Send text intro
            await whatsapp_client.send_text_message(to=phone_number, message=text_intro)
            await save_conversation(
                phone_number=phone_number,
                customer_name=customer_name,
                message_text="",
                response_text=text_intro,
                message_type="text",
                direction="outgoing"
            )
            conversation["messages"].append({
                "role": "assistant",
                "content": text_intro,
                "timestamp": datetime.now(CHILE_TZ).isoformat()
            })
            # Send accommodation images
            image_paths = get_alojamientos_images()
            for idx, image_path in enumerate(image_paths, 1):
                try:
                    media_id_img = await whatsapp_client.upload_media(image_path, mime_type="image/jpeg")
                    if media_id_img:
                        caption = "📄 Información completa de alojamientos" if idx == 1 else None
                        await whatsapp_client.send_image_message(
                            to=phone_number,
                            media_id=media_id_img,
                            caption=caption
                        )
                        await asyncio.sleep(0.5)
                except Exception as img_err:
                    logger.warning(f"Could not send alojamiento image {idx}: {img_err}")
            conversation["last_interaction"] = datetime.now(CHILE_TZ).isoformat()
            return {
                "status": "success",
                "phone_number": phone_number,
                "menu_option": menu_option,
                "message_sent": f"Alojamientos: texto + {len(image_paths)} imágenes enviadas",
                "whatsapp_response": {}
            }
        else:
            raise HTTPException(status_code=400, detail="Invalid menu option (must be 0-5 or 9)")
        
        # Send message via WhatsApp
        result = await whatsapp_client.send_text_message(
            to=phone_number,
            message=response_text
        )
        
        # Save to database
        await save_conversation(
            phone_number=phone_number,
            customer_name=customer_name,
            message_text="",  # No incoming message, this is an outgoing response
            response_text=response_text,
            message_type="text",
            direction="outgoing"
        )
        
        # Add to conversation history (in-memory)
        conversation["messages"].append({
            "role": "assistant",
            "content": response_text,
            "timestamp": datetime.now(CHILE_TZ).isoformat()
        })
        
        # Update last interaction
        conversation["last_interaction"] = datetime.now(CHILE_TZ).isoformat()
        
        return {
            "status": "success",
            "phone_number": phone_number,
            "menu_option": menu_option,
            "message_sent": response_text[:100] + "..." if len(response_text) > 100 else response_text,
            "whatsapp_response": result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error sending quick reply: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# PUSH NOTIFICATIONS ENDPOINTS
# ============================================================================

class PushTokenRegister(BaseModel):
    token: str  # Expo push token
    device_info: Optional[Dict] = None


class PushTokenUnregister(BaseModel):
    token: str


class PushTestNotification(BaseModel):
    title: str
    body: str


@app.post("/api/push/register")
async def register_push_token(request: PushTokenRegister):
    """Register a device for push notifications"""
    try:
        success = await push_notifier.register_push_token(
            token=request.token,
            device_info=request.device_info
        )
        
        if success:
            return {
                "status": "success",
                "message": "Push token registered successfully"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to register push token")
            
    except Exception as e:
        logger.error(f"Error registering push token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/push/unregister")
async def unregister_push_token(request: PushTokenUnregister):
    """Unregister a device from push notifications"""
    try:
        success = await push_notifier.unregister_push_token(token=request.token)
        
        if success:
            return {
                "status": "success",
                "message": "Push token unregistered successfully"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to unregister push token")
            
    except Exception as e:
        logger.error(f"Error unregistering push token: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/push/test")
async def send_test_notification(request: PushTestNotification):
    """Send a test push notification to all registered devices"""
    try:
        success = await push_notifier.send_notification(
            title=request.title,
            body=request.body,
            priority="high"
        )
        
        if success:
            return {
                "status": "success",
                "message": "Test notification sent"
            }
        else:
            return {
                "status": "warning",
                "message": "No devices registered or notification failed"
            }
            
    except Exception as e:
        logger.error(f"Error sending test notification: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# MESSAGE REACTIONS ENDPOINT
# ============================================================================

class MessageReaction(BaseModel):
    emoji: str
    phone_number: str


@app.post("/api/messages/{message_id}/react")
async def react_to_message(message_id: int, reaction: MessageReaction):
    """Send a reaction to a WhatsApp message"""
    try:
        logger.info(f"📨 Received reaction request: message_id={message_id}, emoji={reaction.emoji}, phone={reaction.phone_number}")
        
        from app.db.connection import get_connection
        from app.whatsapp.client import WhatsAppClient

        # Get the WhatsApp message ID from database
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT message_id, phone_number
                    FROM whatsapp_conversations
                    WHERE id = %s
                """, (message_id,))

                result = cur.fetchone()
                logger.info(f"🔍 Database query result: {result}")
                
                if not result:
                    logger.error(f"❌ Message {message_id} not found in database")
                    raise HTTPException(status_code=404, detail="Message not found")

                whatsapp_message_id = result[0]
                phone_number = result[1]
                
                logger.info(f"📱 WhatsApp message_id: {whatsapp_message_id}, phone: {phone_number}")

                if not whatsapp_message_id:
                    logger.error(f"❌ Message {message_id} has no WhatsApp message ID")
                    raise HTTPException(status_code=400, detail="Message does not have a WhatsApp message ID")

        # Send reaction via WhatsApp API
        client = WhatsAppClient()
        logger.info(f"📤 Sending reaction to WhatsApp API...")
        response = await client.send_reaction(
            to=reaction.phone_number,
            message_id=whatsapp_message_id,
            emoji=reaction.emoji
        )

        logger.info(f"✅ Reaction {reaction.emoji} sent to message {whatsapp_message_id}")

        return {
            "status": "success",
            "message_id": message_id,
            "whatsapp_message_id": whatsapp_message_id,
            "emoji": reaction.emoji,
            "whatsapp_response": response
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Error sending reaction: {e}")
        logger.error(f"❌ Error type: {type(e).__name__}")
        logger.error(f"❌ Error details: {str(e)}", exc_info=True)
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
async def get_conversations_list(limit: int = Query(50, ge=1, le=1000)):
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


@app.get("/api/conversations/search")
async def search_conversations(q: str = Query(..., min_length=3)):
    """Search conversations by phone number (partial match). Finds conversations even if not in recent list."""
    try:
        results = await search_conversations_by_phone(q, limit=20)
        return {
            "conversations": results,
            "total": len(results)
        }
    except Exception as e:
        logger.error(f"Error searching conversations: {e}")
        return {
            "conversations": [],
            "total": 0,
            "error": str(e)
        }


@app.get("/api/conversations/search-messages")
async def search_messages(q: str = Query(..., min_length=2)):
    """Search for text across ALL messages in the database. Returns conversations that contain the search term."""
    import asyncio
    try:
        logger.info(f"Searching messages for: '{q}'")
        # Run blocking DB query in thread pool to avoid blocking event loop
        results = await asyncio.to_thread(search_messages_in_all_conversations_sync, q, 50)
        logger.info(f"Search found {len(results)} conversations")
        return {
            "conversations": results,
            "total": len(results)
        }
    except Exception as e:
        logger.error(f"Error searching messages: {e}", exc_info=True)
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
        from PIL import Image as PILImage
        import tempfile
        
        # Validate inputs
        if not to:
            raise HTTPException(status_code=400, detail="Phone number is required")
        
        if not image:
            raise HTTPException(status_code=400, detail="Image file is required")
        
        # Validate file type
        if not image.content_type or not image.content_type.startswith('image/'):
            raise HTTPException(status_code=400, detail="File must be an image")
        
        # Read file contents
        contents = await image.read()
        original_size_mb = len(contents) / (1024 * 1024)
        logger.info(f"📥 Processing image {image.filename} ({original_size_mb:.2f} MB) from {to}")
        
        # Save to temporary file for processing
        with tempfile.NamedTemporaryFile(delete=False, suffix='_original') as temp_file:
            temp_file.write(contents)
            original_path = temp_file.name
        
        # Process image with Pillow to ensure WhatsApp compatibility and compress if needed
        try:
            img = PILImage.open(original_path)
            
            logger.info(f"🎨 Original image format: {img.format}, mode: {img.mode}, size: {img.size}")
            
            # Convert to RGB if needed (removes alpha channel, converts CMYK, P3, etc.)
            if img.mode not in ('RGB', 'L'):  # L is grayscale
                logger.info(f"🔄 Converting image from {img.mode} to RGB")
                # If image has transparency, paste on white background
                if img.mode in ('RGBA', 'LA', 'PA'):
                    background = PILImage.new('RGB', img.size, (255, 255, 255))
                    if img.mode == 'P':
                        img = img.convert('RGBA')
                    background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                    img = background
                else:
                    img = img.convert('RGB')
            
            # WhatsApp has a 5MB limit, so we need to compress intelligently
            MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB in bytes
            
            # Start with reasonable dimensions
            max_dimension = 1600
            quality = 85
            
            # If the image is huge, reduce dimensions more aggressively
            if original_size_mb > 10:
                max_dimension = 1200
                quality = 75
            elif original_size_mb > 20:
                max_dimension = 1000
                quality = 70
            
            # Resize if too large
            if img.width > max_dimension or img.height > max_dimension:
                logger.info(f"📏 Resizing image from {img.size} to fit {max_dimension}x{max_dimension}")
                img.thumbnail((max_dimension, max_dimension), PILImage.Resampling.LANCZOS)
                logger.info(f"✅ Resized to {img.size}")
            
            # Try to compress until file size is acceptable
            processed_path = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg').name
            attempts = 0
            max_attempts = 5
            
            while attempts < max_attempts:
                # Save with current settings
                img.save(processed_path, 'JPEG', quality=quality, optimize=True)
                file_size = os.path.getsize(processed_path)
                file_size_mb = file_size / (1024 * 1024)
                
                logger.info(f"🔄 Attempt {attempts + 1}: quality={quality}, size={file_size_mb:.2f}MB")
                
                if file_size <= MAX_FILE_SIZE:
                    logger.info(f"✅ Image compressed successfully: {file_size_mb:.2f}MB (from {original_size_mb:.2f}MB)")
                    break
                
                # If still too large, reduce quality or dimensions
                if quality > 60:
                    quality -= 10
                else:
                    # If quality is already low, reduce dimensions
                    current_max = max(img.width, img.height)
                    new_max = int(current_max * 0.8)  # Reduce by 20%
                    logger.info(f"📏 Further reducing dimensions to {new_max}x{new_max}")
                    img.thumbnail((new_max, new_max), PILImage.Resampling.LANCZOS)
                    quality = 70  # Reset quality a bit
                
                attempts += 1
            
            # Check final size
            final_size = os.path.getsize(processed_path)
            if final_size > MAX_FILE_SIZE:
                logger.warning(f"⚠️ Image still large after compression: {final_size / (1024 * 1024):.2f}MB")
                # We'll try to send it anyway, WhatsApp will reject if truly too large
            
            # Clean up original
            os.unlink(original_path)
            
            temp_path = processed_path
            
        except Exception as img_error:
            logger.error(f"❌ Error processing image: {img_error}")
            # If processing fails, try with original
            temp_path = original_path
        
        try:
            # Upload to WhatsApp (always use image/jpeg after processing)
            logger.info(f"📤 Uploading processed image to WhatsApp...")
            media_id = await whatsapp_client.upload_media(temp_path, 'image/jpeg')
            
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


@app.post("/api/upload-and-send-audio")
async def upload_and_send_audio(
    audio: UploadFile,
    to: str = Form(...)
):
    """
    Upload an audio file and send it via WhatsApp
    
    Args:
        audio: Audio file to upload
        to: Recipient phone number
    """
    try:
        import tempfile
        import shutil
        
        # Validate inputs
        if not to:
            raise HTTPException(status_code=400, detail="Phone number is required")
        
        if not audio:
            raise HTTPException(status_code=400, detail="Audio file is required")
        
        # Validate file type (accept audio files)
        if not audio.content_type or not audio.content_type.startswith('audio/'):
            # Also accept webm video (often used for audio recording)
            if not (audio.content_type and 'webm' in audio.content_type):
                raise HTTPException(status_code=400, detail="File must be an audio file")
        
        # Read file contents
        contents = await audio.read()
        file_size_mb = len(contents) / (1024 * 1024)
        logger.info(f"📥 Processing audio {audio.filename} ({file_size_mb:.2f} MB) from {to}")
        
        # Save to temporary file for upload
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ogg') as temp_file:
            temp_file.write(contents)
            temp_path = temp_file.name
        
        try:
            # Determine MIME type and extension
            mime_type = "audio/ogg"
            extension = "ogg"
            if audio.content_type:
                if "mp3" in audio.content_type or "mpeg" in audio.content_type:
                    mime_type = "audio/mpeg"
                    extension = "mp3"
                elif "mp4" in audio.content_type or "m4a" in audio.content_type:
                    mime_type = "audio/mp4"
                    extension = "m4a"
                elif "wav" in audio.content_type:
                    mime_type = "audio/wav"
                    extension = "wav"
                elif "webm" in audio.content_type:
                    mime_type = "audio/ogg"  # WhatsApp prefers OGG
                    extension = "ogg"
            
            # Upload to WhatsApp
            logger.info(f"📤 Uploading audio to WhatsApp (MIME: {mime_type})...")
            media_id = await whatsapp_client.upload_media(temp_path, mime_type)
            
            if not media_id:
                raise HTTPException(status_code=500, detail="Failed to upload audio to WhatsApp")
            
            logger.info(f"✅ Audio uploaded successfully, media_id: {media_id}")
            
            # Save audio permanently to media/audio directory
            audio_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media", "audio")
            os.makedirs(audio_dir, exist_ok=True)
            
            timestamp = datetime.now(CHILE_TZ).strftime("%Y%m%d_%H%M%S")
            permanent_filename = f"{media_id}_{timestamp}.{extension}"
            permanent_path = os.path.join(audio_dir, permanent_filename)
            
            # Copy the temporary file to permanent location
            shutil.copy2(temp_path, permanent_path)
            logger.info(f"💾 Audio saved locally: {permanent_path}")
            
            # Send audio message
            result = await whatsapp_client.send_audio_message(
                to=to,
                media_id=media_id
            )
            
            message_id = result.get('messages', [{}])[0].get('id', '')
            
            # Get lead info
            lead = None
            try:
                lead = await get_or_create_lead(to)
            except Exception as lead_error:
                logger.error(f"Error loading lead: {lead_error}")
            
            # Log in database with media_id so it can be served from local storage
            try:
                media_url = f"/api/media/{media_id}"
                await save_conversation(
                    phone_number=to,
                    customer_name=lead.get('customer_name', to) if lead else to,
                    message_text='[Audio]',
                    response_text=media_url,
                    message_type="audio",
                    message_id=message_id or None,
                    direction='outgoing'
                )
            except Exception as db_error:
                logger.error(f"Error storing audio message in DB: {db_error}")
            
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
        logger.error(f"Error uploading and sending audio: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Failed to send audio: {str(e)}")


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
        
        # Get absolute path to media directories
        base_dir = Path(__file__).parent.parent  # Go up to project root
        media_received_dir = base_dir / "media" / "received"
        media_audio_dir = base_dir / "media" / "audio"
        
        logger.debug(f"Looking for media {media_id} in media directories")
        
        # Content type mapping
        content_type_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
            ".gif": "image/gif",
            ".mp4": "video/mp4",
            ".ogg": "audio/ogg",
            ".oga": "audio/ogg",
            ".mp3": "audio/mpeg",
            ".m4a": "audio/mp4",
            ".wav": "audio/wav",
            ".aac": "audio/aac",
            ".webm": "audio/webm",
        }
        
        # Try to find the file in received directory first, then audio directory
        for media_dir in [media_received_dir, media_audio_dir]:
            if media_dir.exists():
                # Look for files that start with the media_id
                for file_path in media_dir.glob(f"{media_id}_*.*"):
                    if file_path.is_file():
                        logger.info(f"✅ Serving media from local file: {file_path}")
                        
                        # Determine content type from extension
                        ext = file_path.suffix.lower()
                        content_type = content_type_map.get(ext, "application/octet-stream")
                        
                        # Log serving audio files
                        if ext in [".ogg", ".mp3", ".m4a", ".wav", ".webm"]:
                            logger.info(f"🎤 Serving audio file: {file_path.name}, type: {content_type}")
                        
                        # Return the file with headers for audio playback
                        return FileResponse(
                            path=str(file_path),
                            media_type=content_type,
                            filename=file_path.name,
                            headers={
                                "Accept-Ranges": "bytes",
                                "Cache-Control": "no-cache"
                            }
                        )
            else:
                logger.warning(f"Media directory does not exist: {media_dir}")
                # Create it
                media_dir.mkdir(parents=True, exist_ok=True)
        
        # If not found locally, try to download it from WhatsApp first
        logger.debug(f"📥 Media not found locally, attempting to download from WhatsApp: {media_id}")
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
                ".ogg": "audio/ogg",
                ".oga": "audio/ogg",
                ".mp3": "audio/mpeg",
                ".m4a": "audio/mp4",
                ".wav": "audio/wav",
                ".aac": "audio/aac",
                ".webm": "audio/webm",
            }
            content_type = content_type_map.get(ext, "application/octet-stream")
            
            # Log serving audio files
            if ext in [".ogg", ".mp3", ".m4a", ".wav", ".webm"]:
                logger.info(f"🎤 Serving downloaded audio file: {os.path.basename(local_path)}, type: {content_type}")
            
            return FileResponse(
                path=local_path,
                media_type=content_type,
                filename=os.path.basename(local_path),
                headers={
                    "Accept-Ranges": "bytes",
                    "Cache-Control": "no-cache"
                }
            )
        
        # Last resort: try to proxy directly from WhatsApp (legacy behavior)
        logger.debug(f"Attempting direct proxy from WhatsApp for media: {media_id}")
        media_url = await whatsapp_client.get_media_url(media_id)
        if not media_url:
            logger.debug(f"Media URL not available for {media_id} (likely expired)")
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








