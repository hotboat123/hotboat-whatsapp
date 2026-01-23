"""
Conversation manager - handles message flow and context
"""
import asyncio
import logging
import re
import unicodedata
from typing import Dict, Optional, Union, List
from datetime import datetime, timedelta

from app.bot.availability import AvailabilityChecker, SPANISH_MONTHS, CHILE_TZ
from app.bot.faq import FAQHandler
from app.bot.accommodations import accommodations_handler
from app.bot.cart import CartManager
from app.bot.translations import (
    get_text,
    detect_language_command,
    get_language_code_from_text,
    LANGUAGES
)
from app.config import get_settings
from app.db.leads import get_or_create_lead, get_conversation_history
from app.whatsapp.client import WhatsAppClient

try:
    import resend
    RESEND_AVAILABLE = True
except ImportError:
    RESEND_AVAILABLE = False
    logging.warning("Resend not installed - email notifications will be disabled")

logger = logging.getLogger(__name__)

# Número del Capitán Tomás para notificaciones
CAPITAN_TOMAS_PHONE = "56974950762"  # Tu número personal

# Mapeo de números a extras
EXTRAS_NUMBER_MAP = {
    "1": "tabla grande",
    "2": "tabla pequeña",
    "3": "jugo natural",
    "4": "lata bebida",
    "5": "agua mineral",
    "6": "helado",  # Needs flavor selection
    "7": "modo romántico",
    "8": "velas",
    "9": "letras",
    "10": "pack completo",
    "11": "video 15",
    "12": "video 60",
    "13": "transporte",
    "14": "toalla normal",
    "15": "toalla poncho",
    "16": "chalas",
    "17": "reserva flex",
}

# Frases que activan el modo de entrega manual (silencian al bot)
MANUAL_HANDOVER_TRIGGERS = [
    "Tomás de HotBoat por Aquí",
    "hola tomas de hotboat por aqui",
]


class ConversationManager:
    """Manages conversations with users"""
    
    def __init__(self):
        self.availability_checker = AvailabilityChecker()
        self.faq_handler = FAQHandler()
        self.cart_manager = CartManager()
        self.whatsapp_client = WhatsAppClient()
        self.settings = get_settings()
        notification_emails = getattr(self.settings, "notification_emails", "")
        self.notification_email_recipients = [
            email.strip()
            for email in notification_emails.split(",")
            if email and email.strip()
        ]
        self.email_sender = self.settings.email_from or self.settings.business_email
        # Precompute extra keywords sorted by length to prioritize specific matches
        self.extra_keywords = sorted(self.cart_manager.EXTRAS_CATALOG.keys(), key=len, reverse=True)
        # In-memory conversation storage (use Redis or DB in production)
        self.conversations: Dict[str, dict] = {}
        # Track scheduled summary emails per phone number
        self.conversation_summary_tasks: Dict[str, asyncio.Task] = {}
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text by removing accents and lowercasing for comparisons.
        """
        if not text:
            return ""
        normalized = unicodedata.normalize("NFKD", text)
        stripped = "".join(ch for ch in normalized if not unicodedata.combining(ch))
        return stripped.lower().strip()
    
    def is_manual_handover_trigger(self, message: str) -> bool:
        """
        Check if a message activates manual handover (silences the bot).
        """
        normalized_message = self._normalize_text(message)
        return any(normalized_message.startswith(trigger) for trigger in MANUAL_HANDOVER_TRIGGERS)
    
    async def activate_manual_handover(self, phone_number: str, contact_name: Optional[str] = None) -> None:
        """
        Enable manual handover for a conversation so the bot stops replying.
        """
        conversation = await self.get_conversation(phone_number, contact_name or phone_number)
        metadata = conversation.setdefault("metadata", {})
        metadata["manual_override_active"] = True
        metadata["manual_override_set_at"] = datetime.now(CHILE_TZ).isoformat()
        metadata["manual_override_reason"] = "manual_trigger"
        conversation["last_interaction"] = datetime.now(CHILE_TZ).isoformat()
        logger.info(f"Manual handover enabled for {phone_number}")
    
    async def _notify_capitan_tomas(self, customer_name: str, customer_phone: str, cart: list, reason: str = "reservation") -> None:
        """
        Send WhatsApp notification to Capitán Tomás
        
        Args:
            customer_name: Name of the customer
            customer_phone: Customer's phone number
            cart: Cart items
            reason: 'reservation' or 'call_request'
        """
        try:
            email_subject: Optional[str] = None
            email_body: Optional[str] = None
            email_priority = "high"
            
            if reason == "reservation" and cart:
                # Notification for confirmed reservation
                reservation = next((item for item in cart if item.item_type == "reservation"), None)
                total = self.cart_manager.calculate_total(cart)
                
                # Prepare WhatsApp link with pre-filled message
                date_str = reservation.metadata.get('date', '') if reservation else ''
                time_str = reservation.metadata.get('time', '') if reservation else ''
                people_str = str(reservation.quantity) if reservation else ''
                
                # Create pre-filled message for WhatsApp link
                prefilled_msg = f"Hola {customer_name}! 👋\n\n"
                prefilled_msg += f"Tu reserva para el {date_str} a las {time_str} está confirmada ✅\n\n"
                prefilled_msg += f"Detalles:\n"
                prefilled_msg += f"• {people_str} personas\n"
                prefilled_msg += f"• Total: ${total:,}\n\n"
                prefilled_msg += f"Nos vemos pronto! 🚤"
                
                # URL encode the message
                import urllib.parse
                encoded_msg = urllib.parse.quote(prefilled_msg)
                whatsapp_link = f"https://wa.me/{customer_phone}?text={encoded_msg}"
                
                message = f"🚨 *Nueva Reserva Confirmada*\n\n"
                message += f"👤 *Cliente:* {customer_name}\n"
                message += f"📱 *Teléfono:* +{customer_phone}\n\n"
                
                if reservation:
                    message += f"📅 *Fecha:* {date_str}\n"
                    message += f"🕐 *Hora:* {time_str}\n"
                    message += f"👥 *Personas:* {people_str}\n\n"
                
                extras = [item for item in cart if item.item_type == "extra"]
                if extras:
                    message += f"✨ *Extras:*\n"
                    for item in extras:
                        message += f"   • {item.name} (${item.price:,})\n"
                    message += "\n"
                
                message += f"💰 *Total:* ${total:,}\n\n"
                message += f"🔗 *Responder al cliente:*\n"
                message += whatsapp_link
                
                email_subject = f"Nueva reserva confirmada - {customer_name}"
                email_body = self._format_plain_text(message)
                email_priority = "high"
                
            elif reason == "call_request":
                # Notification for call request (option 6)
                
                # Create pre-filled message for WhatsApp link
                import urllib.parse
                prefilled_msg = f"Hola {customer_name}! 👋\n\nSoy Tomás, Capitán de HotBoat.\n\n¿En qué puedo ayudarte? 😊"
                encoded_msg = urllib.parse.quote(prefilled_msg)
                whatsapp_link = f"https://wa.me/{customer_phone}?text={encoded_msg}"
                
                message = f"📞 *Solicitud de Contacto*\n\n"
                message += f"👤 *Cliente:* {customer_name}\n"
                message += f"📱 *Teléfono:* +{customer_phone}\n\n"
                message += f"El cliente solicitó hablar con el Capitán Tomás 👨‍✈️\n\n"
                message += f"🔗 *Contactar al cliente:*\n"
                message += whatsapp_link
                
                email_subject = f"Solicitud de contacto - {customer_name}"
                email_body = self._format_plain_text(message)
                email_priority = "critical"
            
            else:
                return
            
            # Send notification
            await self.whatsapp_client.send_text_message(CAPITAN_TOMAS_PHONE, message)
            logger.info(f"Notification sent to Capitán Tomás for {reason}: {customer_name}")
            
            if email_subject and email_body:
                await self._send_notification_email(email_subject, email_body, priority=email_priority)
            
        except Exception as e:
            logger.error(f"Error sending notification to Capitán Tomás: {e}")
            import traceback
            traceback.print_exc()
    
    async def process_message(
        self,
        from_number: str,
        message_text: str,
        contact_name: str,
        message_id: str
    ) -> Union[Optional[str], Dict]:
        """
        Process incoming message and generate response
        
        Args:
            from_number: Sender's phone number
            message_text: Message text
            contact_name: Sender's name
            message_id: WhatsApp message ID
        
        Returns:
            Response text or None
        """
        try:
            # Get or create conversation context (loads history from DB)
            conversation = await self.get_conversation(from_number, contact_name)
            processed_ids: set = conversation.setdefault("processed_message_ids", set())
            if message_id and message_id in processed_ids:
                logger.info(f"Duplicate message detected (ID: {message_id}), skipping processing.")
                return None
            if message_id:
                processed_ids.add(message_id)
            
            logger.info(f"Processing message from {contact_name}: {message_text}")
            logger.info(f"Current metadata state: {conversation.get('metadata', {})}")
            metadata = conversation.setdefault("metadata", {})
            
            # Check if it's the first message - send welcome message
            # Check BEFORE adding the message to history
            is_first = self._is_first_message(conversation)
            
            # Add message to history
            conversation["messages"].append({
                "role": "user",
                "content": message_text,
                "timestamp": datetime.now(CHILE_TZ).isoformat(),
                "message_id": message_id
            })
            
            # NOTE: Email notifications are now sent in the webhook handler (webhook.py)
            # to ensure they're always sent even when the bot is disabled for a user
            
            # If manual handover is active, skip bot responses
            if metadata.get("manual_override_active"):
                logger.info(f"Manual handover active for {from_number} - skipping bot reply")
                conversation["last_interaction"] = datetime.now(CHILE_TZ).isoformat()
                return {"type": "manual_override"}
            
            # Activate manual handover when the trigger phrase is received
            if self.is_manual_handover_trigger(message_text):
                logger.info(f"Manual handover activated by trigger phrase for {from_number}")
                metadata["manual_override_active"] = True
                metadata["manual_override_set_at"] = datetime.now(CHILE_TZ).isoformat()
                metadata["manual_override_reason"] = "manual_trigger"
                conversation["last_interaction"] = datetime.now(CHILE_TZ).isoformat()
                return {"type": "manual_override"}
            
            if is_first:
                self._schedule_conversation_summary_email(from_number, conversation)
            
            requested_language = get_language_code_from_text(message_text)
            if requested_language:
                if requested_language in LANGUAGES:
                    logger.info(f"Language change requested: {requested_language}")
                    response = self._switch_language(conversation, requested_language)
                else:
                    logger.info(f"Unsupported language requested: {requested_language}")
                    response = self._language_not_supported_response(conversation)
            # Always show welcome message on first interaction
            elif is_first:
                logger.info("First message - sending welcome menu")
                metadata["language_selected"] = True
                language = metadata.get("language", "es")
                response = self._get_main_menu_message(language)
            elif self._is_thanks_message(message_text):
                logger.info("Gratitude detected - sending friendly reply")
                language = metadata.get("language", "es")
                response = get_text("thanks_response", language)
            # PRIORITY 0.8: Allow users to restart availability flow at any step
            elif self._should_interrupt_with_new_availability(message_text, conversation):
                logger.info("Priority availability question detected - restarting flow")
                self._prepare_reservation_flow(conversation, reset=True)
                response = await self._handle_reservation_date_response(
                    message_text, from_number, contact_name, conversation
                )
            # PRIORITY 1: Check if user is responding with number of people (after selecting date/time)
            # This MUST come before menu options to avoid confusion when user types a number
            elif conversation.get("metadata", {}).get("awaiting_party_size"):
                logger.info("User responding with party size")
                response = await self._handle_party_size_response(message_text, from_number, contact_name, conversation)
            # PRIORITY 1.2: Sequential reservation flow - awaiting date selection
            elif conversation.get("metadata", {}).get("awaiting_reservation_date"):
                logger.info("User responding with reservation date")
                response = await self._handle_reservation_date_response(message_text, from_number, contact_name, conversation)
            # PRIORITY 1.3: Sequential reservation flow - awaiting time selection
            elif conversation.get("metadata", {}).get("awaiting_reservation_time"):
                logger.info("User responding with reservation time")
                response = await self._handle_reservation_time_response(message_text, from_number, contact_name, conversation)
            # PRIORITY 1.5: Check if user is responding with ice cream flavor choice
            elif conversation.get("metadata", {}).get("awaiting_ice_cream_flavor"):
                logger.info("User responding with ice cream flavor")
                response = await self._handle_ice_cream_flavor_response(message_text, from_number, contact_name, conversation)
            # PRIORITY 1.6: Check if user is selecting an extra by number (after viewing extras menu)
            elif conversation.get("metadata", {}).get("awaiting_extra_selection"):
                logger.info(f"User awaiting extra selection, processing: {message_text}")
                extra_response = await self._handle_extra_number_selection(message_text, from_number, contact_name, conversation)
                if extra_response:
                    response = extra_response
                else:
                    # If not a valid extra number, try to parse with text/AI (e.g., "2 jugos")
                    logger.info("Not a pure ID selection, trying text-based parsing")
                    text_response = await self._try_parse_extra_with_ai(message_text, from_number, contact_name, conversation)
                    if text_response:
                        response = text_response
                    else:
                        # If still can't parse, tell them what's expected
                        conversation["metadata"]["awaiting_extra_selection"] = False
                        response = f"""❌ Por favor escribe un número válido del 1 al 17 para seleccionar un extra.

O elige:
1️⃣8️⃣ Ver extras (menú completo de nuevo)
1️⃣9️⃣ Menu principal
2️⃣0️⃣ Proceder con el pago

¿Qué número eliges? 🚤"""
            # PRIORITY 2: Check for global shortcuts (18, 19, 20) - work anywhere
            elif message_text.strip() == "18":
                logger.info("Global shortcut 18: Ver extras")
                conversation["metadata"]["awaiting_extra_selection"] = True
                language = conversation.get("metadata", {}).get("language", "es")
                response = self.faq_handler.get_response("extras", language)
            elif message_text.strip() == "19":
                logger.info("Global shortcut 19: Menu principal")
                conversation["metadata"]["awaiting_extra_selection"] = False
                language = conversation.get("metadata", {}).get("language", "es")
                response = self._get_main_menu_message(language)
            elif message_text.strip() == "20":
                logger.info("Global shortcut 20: Ver/proceder con carrito")
                conversation["metadata"]["awaiting_extra_selection"] = False
                cart = await self.cart_manager.get_cart(from_number)
                language = conversation.get("metadata", {}).get("language", "es")
                if not cart:
                    response = get_text("cart_empty", language)
                else:
                    # Check if has reservation to proceed with payment
                    has_reservation = any(item.item_type == "reservation" for item in cart)
                    if has_reservation:
                        # Proceed with payment
                        total = self.cart_manager.calculate_total(cart)
                        reservation = next((item for item in cart if item.item_type == "reservation"), None)
                        
                        confirm_message = "✅ *Solicitud de Reserva Recibida*\n\n"
                        confirm_message += f"📅 *Detalles de tu Solicitud:*\n"
                        confirm_message += f"   Fecha: {reservation.metadata.get('date')}\n"
                        confirm_message += f"   Horario: {reservation.metadata.get('time')}\n"
                        confirm_message += f"   Personas: {reservation.quantity}\n\n"
                        
                        if len(cart) > 1:
                            confirm_message += f"✨ *Extras solicitados:*\n"
                            for item in cart:
                                if item.item_type == "extra":
                                    confirm_message += f"   • {item.name}\n"
                            confirm_message += "\n"
                        
                        confirm_message += f"💰 *Total estimado: ${total:,}*\n\n"
                        confirm_message += f"📞 *El Capitán Tomás se comunicará contigo pronto por WhatsApp o teléfono para confirmar tu reserva y coordinar el pago* 👨‍✈️\n\n"
                        confirm_message += f"Por mientras, envíanos tu *email* y *nombre completo* por favor 📝\n\n"
                        confirm_message += f"¡Gracias por elegir HotBoat! 🚤🌊"
                        
                        # Send confirmation immediately to user and trigger notifications in background
                        notification_cart = list(cart)
                        asyncio.create_task(
                            self._notify_capitan_tomas(contact_name, from_number, notification_cart, reason="reservation")
                        )
                        
                        # Clear cart after confirmation
                        await self.cart_manager.clear_cart(from_number)
                        
                        response = confirm_message
                    else:
                        # Just show cart
                        response = f"{self.cart_manager.format_cart_message(cart)}\n\n{self._cart_needs_reservation_message(conversation)}"
            # PRIORITY 2.5: Check if user wants to change language
            elif detect_language_command(message_text):
                logger.info("User requesting language change instructions")
                current_language = metadata.get("language", "es")
                response = get_text("change_language", current_language)
            # PRIORITY 3: Check if it's a cart option (1-3) when cart has items
            elif await self._is_cart_option_selection(message_text, from_number, conversation):
                logger.info(f"Cart option selected: {message_text}")
                response = await self._handle_cart_option_selection(message_text, from_number, contact_name, conversation)
            # Check if it's MULTIPLE menu number selections (e.g., "1,2,3" or "1 2 3")
            # BUT ONLY if we're in a menu context (early in conversation or user just asked for menu)
            elif (menu_numbers := self.faq_handler.is_multiple_menu_numbers(message_text)) and self._should_interpret_as_menu(message_text, conversation):
                logger.info(f"Multiple menu numbers selected: {menu_numbers}")
                language = conversation.get("metadata", {}).get("language", "es")
                response = await self._handle_multiple_menu_selections(menu_numbers, conversation, language, from_number, contact_name)
            # Check if it's a single menu number selection (1-6)
            # BUT ONLY if we're in a menu context (early in conversation or user just asked for menu)
            elif (menu_number := self.faq_handler.is_menu_number(message_text)) and self._should_interpret_as_menu(message_text, conversation):
                logger.info(f"Menu number selected: {menu_number}")
                language = conversation.get("metadata", {}).get("language", "es")
                if menu_number == 1:
                    # Option 1: Disponibilidad y horarios
                    response = self._ask_for_reservation_date(conversation, language)
                elif menu_number == 2:
                    # Option 2: Precios por persona
                    response = self.faq_handler.get_response("precio", language)
                elif menu_number == 3:
                    # Option 3: Características del HotBoat
                    response = self.faq_handler.get_response("caracteristicas", language)
                elif menu_number == 4:
                    # Option 4: Extras y promociones
                    conversation["metadata"]["awaiting_extra_selection"] = True
                    logger.info(f"Set awaiting_extra_selection=True for {from_number}")
                    logger.info(f"Metadata: {conversation.get('metadata', {})}")
                    response = self.faq_handler.get_response("extras", language)
                elif menu_number == 5:
                    # Option 5: Ubicación y reseñas
                    response = self.faq_handler.get_response("ubicación", language)
                elif menu_number == 6:
                    # Option 6: Llamar a Tomás
                    # Send notification to Capitán Tomás
                    await self._notify_capitan_tomas(contact_name, from_number, [], reason="call_request")
                    response = self.faq_handler.get_response("llamar a tomas", language)
                else:
                    response = "No entendí esa opción. Por favor elige un número del 1 al 6, grumete ⚓"
            # Check if asking about accommodations (special handling with images)
            elif self._is_accommodation_query(message_text):
                logger.info("User asking about accommodations - will send with images")
                # Return special response object that indicates images should be sent
                return {
                    "type": "accommodations",
                    "text": accommodations_handler.get_text_response(),
                    "images": accommodations_handler.get_accommodations_with_images()
                }
            # Check if user wants to make a reservation (but didn't specify date/time yet)
            # THIS MUST BE EARLY to catch "quiero reservar", "reservar" before other parsers
            elif self._is_reservation_intent(message_text):
                logger.info("User wants to make a reservation - showing availability")
                response = self._ask_for_reservation_date(conversation)
            
            # Check cart commands (before FAQ)
            elif cart_response := await self._handle_cart_command(message_text, from_number, contact_name):
                logger.info("Cart command processed")
                response = cart_response
            # Check if user is requesting help or Capitán Tomás directly
            elif self._is_help_request(message_text):
                logger.info("Help request detected - notifying Capitán Tomás")
                await self._notify_capitan_tomas(contact_name, from_number, [], reason="call_request")
                faq_response = self.faq_handler.get_response(message_text)
                if not faq_response:
                    faq_response = self.faq_handler.get_response("llamar a tomas")
                response = faq_response or "👨‍✈️ ¡Entendido! El Capitán Tomás te contactará a la brevedad."
            # Check if it's a FAQ question
            elif self.faq_handler.get_response(message_text):
                logger.info("Responding with FAQ answer")
                response = self.faq_handler.get_response(message_text)
            
            # PRIORITY: Check if user is making a complete reservation (date, time, AND party size)
            # This should happen BEFORE AI handler to catch reservation intents
            elif reservation_item := await self._try_parse_reservation_from_message(message_text, from_number, conversation):
                logger.info("User making a reservation - adding to cart")
                try:
                    await self._add_reservation_with_flex(from_number, contact_name, reservation_item)
                    cart = await self.cart_manager.get_cart(from_number)
                    response = self._format_cart_with_flex_options(cart)
                except Exception as cart_error:
                    logger.error(f"Error adding to cart: {cart_error}")
                    import traceback
                    traceback.print_exc()
                    # If cart fails, still acknowledge the reservation
                    response = f"✅ Entendido, quieres reservar para {reservation_item.quantity} personas.\n\nPor favor, confirma los detalles y el Capitán Tomás se comunicará contigo pronto 👨‍✈️"
            
            # Check if user is selecting a date/time (without specifying party size)
            elif date_time_selection := await self._try_parse_date_time_only(message_text, conversation):
                logger.info(f"User selecting date/time: {date_time_selection}")
                # Store the selection and ask for party size
                conversation["metadata"]["pending_reservation"] = date_time_selection
                conversation["metadata"]["awaiting_party_size"] = True
                conversation["metadata"]["awaiting_date_time_selection"] = False
                response = f"""✅ Perfecto, grumete ⚓

📅 Fecha: {date_time_selection['date']}
🕐 Horario: {date_time_selection['time']}

¿Para cuántas personas? (2-7 personas) 🚤"""
            
            # Check if user is confirming a reservation (after seeing availability from AI)
            elif await self._is_confirming_reservation_from_availability(message_text, conversation):
                logger.info("User confirming reservation from availability check")
                response = await self._handle_reservation_confirmation(message_text, from_number, contact_name, conversation)
            
            # Check if asking about availability
            elif self.is_availability_query(message_text):
                logger.info("Checking availability (guided reservation flow)")
                self._prepare_reservation_flow(conversation, reset=True)
                response = await self._handle_reservation_date_response(message_text, from_number, contact_name, conversation)
            
            # Check if user is asking how to add to cart (after seeing availability)
            elif self._is_asking_how_to_add_to_cart(message_text, conversation):
                logger.info("User asking how to add to cart")
                response = """🛒 *Cómo agregar al carrito:*

Es muy sencillo, grumete ⚓

Solo dime la *fecha*, *hora* y *número de personas* que quieres reservar.

Por ejemplo:
• *"El martes a las 16 para 3 personas"*
• *"4 de noviembre a las 15 para 2 personas"*
• *"Miércoles a las 12 para 4 personas"*

Yo lo agrego automáticamente al carrito y luego puedes:
• Agregar extras (tablas, bebidas, etc.)
• Confirmar la reserva

¿Qué fecha y horario te gustaría? 🚤"""
            
            # Final fallback: return main menu to keep flow deterministic
            else:
                logger.info("No handler matched, returning main menu message")
                # Reset transient states to avoid being stuck in partial flows
                if conversation.get("metadata"):
                    conversation["metadata"].pop("awaiting_party_size", None)
                    conversation["metadata"].pop("awaiting_reservation_date", None)
                    conversation["metadata"].pop("awaiting_reservation_time", None)
                    conversation["metadata"].pop("awaiting_extra_selection", None)
                    conversation["metadata"].pop("awaiting_ice_cream_flavor", None)
                    conversation["metadata"].pop("pending_reservation", None)
                    conversation["metadata"].pop("available_times_for_date", None)
                    conversation["metadata"].pop("pending_extras", None)
                    conversation["metadata"].pop("pending_ice_cream_quantity", None)
                    conversation["metadata"].pop("awaiting_date_time_selection", None)
                language = conversation.get("metadata", {}).get("language", "es")
                response = self._get_main_menu_message(language)
            
            
            # Add response to history
            conversation["messages"].append({
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now(CHILE_TZ).isoformat()
            })
            
            # Update last interaction
            conversation["last_interaction"] = datetime.now(CHILE_TZ).isoformat()
            
            return response
            
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            import traceback
            traceback.print_exc()
            return "Disculpa, tuve un problema procesando tu mensaje. ¿Podrías intentar de nuevo?"
    
    async def get_conversation(self, phone_number: str, contact_name: str) -> dict:
        """
        Get or create conversation context, loading history from database if available
        """
        # Check if already in memory
        if phone_number not in self.conversations:
            # Load lead info and conversation history from database
            try:
                lead = await get_or_create_lead(phone_number, contact_name)
            except Exception as e:
                logger.warning(f"Error loading lead for {phone_number}: {e}")
                lead = None
            
            try:
                history = await get_conversation_history(phone_number, limit=50)
            except Exception as e:
                logger.warning(f"Error loading history for {phone_number}: {e}")
                history = []
            
            # Detect language from history if available, otherwise default to Spanish
            detected_language = "es"  # Default
            if history:
                # If there's history, user already selected language
                detected_language = "es"  # Could be enhanced to detect from history
            
            self.conversations[phone_number] = {
                "phone": phone_number,
                "name": contact_name,
                "messages": history if history else [],
                "created_at": datetime.now(CHILE_TZ).isoformat(),
                "last_interaction": datetime.now(CHILE_TZ).isoformat(),
                "metadata": {
                    "lead_status": lead.get("lead_status") if lead else "unknown",
                    "lead_id": lead.get("id") if lead else None,
                    "language": detected_language,
                    "language_selected": len(history) > 0  # True if has history
                },
                "processed_message_ids": set()
            }
            
            if history:
                logger.info(f"Loaded {len(history)} messages from history for {phone_number}")
        
        # Update name if different
        if contact_name and self.conversations[phone_number]["name"] != contact_name:
            self.conversations[phone_number]["name"] = contact_name
        
        return self.conversations[phone_number]
    
    def _is_asking_how_to_add_to_cart(self, message: str, conversation: dict) -> bool:
        """
        Check if user is asking how to add items to cart
        
        Args:
            message: User message
            conversation: Conversation context
        
        Returns:
            True if user is asking about cart process
        """
        message_lower = message.lower().strip()
        
        # Keywords that indicate user is asking how to add to cart
        cart_help_keywords = [
            "cómo agregar", "como agregar", "agregar al carro", "agregar al carrito",
            "cómo reservar", "como reservar", "cómo hacer", "como hacer",
            "qué tengo que hacer", "que tengo que hacer", "qué hago", "que hago",
            "no entiendo", "no entiendo que", "cómo funciona", "como funciona",
            "cómo es", "como es", "explicame", "explícame", "explica"
        ]
        
        # Check if message contains cart-related help keywords
        if any(keyword in message_lower for keyword in cart_help_keywords):
            # Check if last bot message was about availability (context)
            if conversation and conversation.get("messages"):
                last_messages = conversation["messages"][-3:]  # Check last 3 messages
                for msg in reversed(last_messages):
                    if msg.get("role") == "assistant":
                        content = msg.get("content", "").lower()
                        # If bot recently showed availability, user is likely asking how to proceed
                        if "disponibilidad" in content or "disponible" in content or "horario" in content:
                            return True
            # Only return True if message has BOTH a help keyword AND cart/reservation word
            # This prevents "quiero reservar" from being caught here
            if any(word in message_lower for word in ["carro", "carrito"]):
                return True
        
        return False
    
    def _is_reservation_intent(self, message: str) -> bool:
        """
        Check if user wants to make a reservation (without specific date/time)
        
        Args:
            message: User message
        
        Returns:
            True if user expresses intent to reserve
        """
        message_lower = message.lower().strip()
        
        # Exclude if asking HOW to reserve (that's handled by _is_asking_how_to_add_to_cart)
        if any(word in message_lower for word in ["cómo", "como", "explicar", "qué tengo", "que tengo"]):
            return False
        
        # Keywords that indicate user wants to reserve (but hasn't given details)
        reservation_intent_keywords = [
            "quiero reservar", "quisiera reservar", "me gustaría reservar",
            "puedo reservar", "se puede reservar", "podría reservar",
            "quiero hacer una reserva", "quisiera hacer una reserva", 
            "me gustaría hacer una reserva", "hacer una reserva",
            "puedo hacer una reserva", "podría hacer una reserva",
            "reservar por acá", "reservar por aca", "reservar aquí", "reservar aqui",
            "me gustaría una reserva", "quisiera una reserva", "quiero una reserva"
        ]
        
        # Check if message contains reservation intent keywords
        if any(keyword in message_lower for keyword in reservation_intent_keywords):
            return True
        
        # Also catch simple "reservar" or "reserva" (without asking how)
        if message_lower in ["reservar", "reserva", "una reserva"]:
            return True
        
        return False
    
    def _get_main_menu_message(self, language: str = "es") -> str:
        """
        Return the standard main menu message in the specified language.
        
        Args:
            language: Language code (es, en, pt)
        
        Returns:
            Main menu message
        """
        return get_text("main_menu", language)
    
    def _is_greeting_message(self, message: str) -> bool:
        """
        Check if message is a greeting or first contact
        
        Args:
            message: User message
        
        Returns:
            True if message is a greeting
        """
        message_lower = message.lower().strip()
        greetings = [
            "hola", "hi", "hey", "hello", "buenos días", "buenas tardes", 
            "buenas noches", "buen día", "saludos", "qué tal", "que tal",
            "ahoy", "buen día", "día", "hey", "hi", "buenas"
        ]
        
        # Check if message is just a greeting
        if message_lower in greetings:
            return True
        
        # Check if message starts with a greeting
        for greeting in greetings:
            if message_lower.startswith(greeting):
                return True
        
        return False
    
    def _is_thanks_message(self, message: str) -> bool:
        """Return True when user sends a gratitude message."""
        if not message:
            return False
        message_lower = message.lower().strip()
        thanks_patterns = [
            r"\bmuchas gracias\b",
            r"\bmil gracias\b",
            r"\bgracias\b",
            r"\bthank you\b",
            r"\bthanks\b",
            r"\bthx\b",
            r"\bty\b",
            r"\bobrigad[ao]\b",
            r"\bobg\b",
            r"\bvaleu\b",
            r"\bvale\b",
        ]
        return any(re.search(pattern, message_lower) for pattern in thanks_patterns)
    
    def _is_first_message(self, conversation: dict) -> bool:
        """
        Check if this is the first message in the conversation.
        We check BEFORE adding the new message, so we look for empty history.
        """
        messages = conversation.get("messages", [])
        
        # If no messages in history, it's definitely the first
        if len(messages) == 0:
            return True
        
        # Count only user messages (not bot responses)
        user_messages = [msg for msg in messages if msg.get("role") == "user"]
        
        # If no user messages yet (only bot responses or empty), it's the first user message
        return len(user_messages) == 0
    
    def _cart_needs_reservation_message(self, conversation: dict) -> str:
        """Return a localized message explaining that a reservation is required."""
        language = conversation.get("metadata", {}).get("language", "es")
        return get_text("cart_needs_reservation", language)
    
    async def _require_reservation_for_extras(self, phone_number: str, conversation: dict) -> Optional[str]:
        """
        Ensure there is a reservation in the cart before allowing extras.
        Returns a localized message if reservation is missing, otherwise None.
        """
        cart = await self.cart_manager.get_cart(phone_number)
        has_reservation = any(item.item_type == "reservation" for item in cart)
        
        if has_reservation:
            return None
        
        metadata = conversation.setdefault("metadata", {})
        metadata["awaiting_extra_selection"] = False
        metadata.pop("awaiting_ice_cream_flavor", None)
        metadata.pop("pending_ice_cream_quantity", None)
        metadata.pop("pending_extras", None)
        
        return self._cart_needs_reservation_message(conversation)
    
    def _switch_language(self, conversation: dict, language_code: str) -> str:
        """Set the conversation language and return confirmation + menu."""
        metadata = conversation.setdefault("metadata", {})
        metadata["language"] = language_code
        metadata["language_selected"] = True
        confirmation = get_text("language_changed", language_code)
        menu = self._get_main_menu_message(language_code)
        return f"{confirmation}\n\n{menu}"
    
    def _language_not_supported_response(self, conversation: dict) -> str:
        """Return a localized message when user requests an unsupported language."""
        language = conversation.get("metadata", {}).get("language", "es")
        return get_text("language_not_supported", language)
    
    def _schedule_conversation_summary_email(self, phone_number: str, conversation: dict) -> None:
        """
        Schedule an email with the conversation transcript 1 minute after it starts.
        Avoid scheduling if already sent or if no notification recipients exist.
        """
        metadata = conversation.setdefault("metadata", {})
        if metadata.get("summary_email_scheduled") or metadata.get("summary_email_sent"):
            return
        if not self.notification_email_recipients:
            return
        
        try:
            task = asyncio.create_task(self._send_conversation_summary_email(phone_number))
            self.conversation_summary_tasks[phone_number] = task
            metadata["summary_email_scheduled"] = True
            metadata["summary_email_delay_seconds"] = 60
        except RuntimeError as exc:
            logger.warning(f"Could not schedule conversation summary email: {exc}")
    
    def _format_conversation_transcript(self, conversation: dict) -> str:
        """Build a plain-text transcript combining user and Popeye messages."""
        lines = []
        customer_name = conversation.get("name") or "Cliente"
        phone_number = conversation.get("phone") or "N/A"
        started_at = conversation.get("created_at", "Sin registro")
        lines.append(f"📞 Cliente: {customer_name} (+{phone_number})")
        lines.append(f"🕒 Inicio de la conversación: {started_at}")
        lines.append("")
        
        messages = conversation.get("messages", [])
        if not messages:
            lines.append("Sin mensajes registrados.")
            return "\n".join(lines)
        
        for msg in messages:
            role = msg.get("role", "")
            speaker = "Cliente" if role == "user" else "Popeye"
            timestamp = msg.get("timestamp", "")
            content = msg.get("content", "").strip()
            lines.append(f"[{timestamp}] {speaker}: {content}")
        
        return "\n".join(lines)
    
    async def _send_incoming_message_email(
        self,
        contact_name: str,
        phone_number: str,
        message_text: str,
        message_id: Optional[str] = None
    ) -> None:
        """Send an immediate email notification for each inbound user message."""
        try:
            customer_name = contact_name or "Cliente HotBoat"
            subject = f"Nuevo mensaje de {customer_name} (+{phone_number})"
            timestamp = datetime.now(CHILE_TZ).strftime("%Y-%m-%d %H:%M:%S %Z")
            
            body_lines = [
                f"📞 Cliente: {customer_name} (+{phone_number})",
                f"🕒 Recibido: {timestamp}",
                "",
                "Mensaje:",
                self._format_plain_text(message_text or "(sin texto)"),
            ]
            
            body = "\n".join(body_lines)
            await self._send_notification_email(subject, body, priority="high")
        except Exception as exc:
            logger.warning(f"Error sending incoming message email: {exc}")
            import traceback
            traceback.print_exc()
    
    async def _send_conversation_summary_email(self, phone_number: str) -> None:
        """
        Wait the configured delay, then email the conversation transcript.
        """
        try:
            await asyncio.sleep(60)
            conversation = self.conversations.get(phone_number)
            if not conversation:
                return
            metadata = conversation.setdefault("metadata", {})
            if metadata.get("summary_email_sent"):
                return
            if not conversation.get("messages"):
                return
            
            customer_name = conversation.get("name") or "Cliente HotBoat"
            subject = f"Nuevo chat con {customer_name}"
            body = self._format_conversation_transcript(conversation)
            await self._send_notification_email(subject, body, priority="high")
            metadata["summary_email_sent"] = True
        except asyncio.CancelledError:
            logger.info(f"Conversation summary email cancelled for {phone_number}")
            raise
        except Exception as exc:
            logger.error(f"Error sending conversation summary email for {phone_number}: {exc}")
        finally:
            self.conversation_summary_tasks.pop(phone_number, None)
    
    def _contains_date(self, message: str) -> bool:
        """
        Check if message contains a date pattern (even without 'disponibilidad')
        
        Args:
            message: User message
        
        Returns:
            True if message contains a date pattern
        """
        message_lower = message.lower()
        
        # Pattern 1: "14 de febrero", "18 de noviembre"
        pattern1 = r'(\d{1,2})\s+de\s+(' + '|'.join(SPANISH_MONTHS.keys()) + r')'
        if re.search(pattern1, message_lower):
            return True
        
        # Pattern 2: "febrero 14", "noviembre 18"
        pattern2 = r'(' + '|'.join(SPANISH_MONTHS.keys()) + r')\s+(\d{1,2})'
        if re.search(pattern2, message_lower):
            return True
        
        # Pattern 3: "14 febrero"
        pattern3 = r'(\d{1,2})\s+(' + '|'.join(SPANISH_MONTHS.keys()) + r')'
        if re.search(pattern3, message_lower):
            return True
        
        # Pattern 4: "14/02", "18/11", "14-02"
        pattern4 = r'(\d{1,2})[/-](\d{1,2})'
        if re.search(pattern4, message_lower):
            return True
        
        return False
    
    def _is_in_reservation_flow(self, conversation: dict) -> bool:
        """Return True if user is mid reservation flow (date, time or party size)."""
        metadata = conversation.get("metadata", {})
        return any([
            metadata.get("awaiting_reservation_date"),
            metadata.get("awaiting_reservation_time"),
            metadata.get("awaiting_party_size"),
            metadata.get("awaiting_date_time_selection")
        ])
    
    def _should_interrupt_with_new_availability(self, message: str, conversation: dict) -> bool:
        """
        Determine if a new availability request should interrupt the current flow.
        Prioritize messages that mention 'disponibilidad' or provide a new date.
        """
        if not message:
            return False
        if not self._is_in_reservation_flow(conversation):
            return False
        message_lower = message.lower()
        if "disponibilidad" in message_lower or "disponible" in message_lower:
            return True
        return self._contains_date(message)
    
    def is_availability_query(self, message: str) -> bool:
        """
        Check if message is asking about availability.
        Now also detects dates even without keywords like 'disponibilidad'.
        """
        message_lower = message.lower()
        
        # First check: traditional keywords (including time references)
        keywords = [
            "disponibilidad", "disponible", "horario", "cuándo", "cuando",
            "fecha", "día", "reservar", "reserva", "agendar",
            "mañana", "tomorrow", "hoy", "today"  # Time references
        ]
        if any(keyword in message_lower for keyword in keywords):
            return True
        
        # Second check: if message contains a date pattern, treat it as availability query
        if self._contains_date(message):
            logger.info(f"Date pattern detected in message, treating as availability query")
            return True
        
        return False
    
    def _is_accommodation_query(self, message: str) -> bool:
        """
        Check if message is asking about accommodations
        
        Args:
            message: User message
        
        Returns:
            True if message is about accommodations
        """
        message_lower = message.lower()
        
        keywords = [
            "alojamiento", "alojamientos", "hotel", "hoteles", 
            "cabaña", "cabañas", "cabanas", "donde quedarse",
            "donde hospedarse", "hospedaje", "hostal", "domo",
            "open sky", "relikura", "donde dormir"
        ]
        
        return any(keyword in message_lower for keyword in keywords)
    
    async def _handle_cart_command(self, message: str, phone_number: str, contact_name: str) -> Optional[str]:
        """
        Handle cart-related commands
        
        Args:
            message: User message
            phone_number: User's phone number
            contact_name: User's name
        
        Returns:
            Response text or None if not a cart command
        """
        import re
        message_lower = message.lower().strip()
        
        # View cart
        if any(cmd in message_lower for cmd in ["carrito", "ver carrito", "mi carrito", "qué tengo"]):
            cart = await self.cart_manager.get_cart(phone_number)
            cart_message = self.cart_manager.format_cart_message(cart)
            
            # If cart has items, add options
            if cart:
                cart_message += "\n\n📋 *¿Qué deseas hacer?*\n\n"
                cart_message += "• Escribe 1-17 para agregar más extras\n"
                cart_message += "• 1️⃣8️⃣ Ver menú de extras completo\n"
                cart_message += "• 1️⃣9️⃣ Menú principal\n"
                cart_message += "• 2️⃣0️⃣ Proceder con el pago\n"
                cart_message += "• Escribe *vaciar* para vaciar el carrito\n\n"
                cart_message += "¿Qué opción eliges, grumete?"
            
            return cart_message
        
        # Clear cart
        if any(cmd in message_lower for cmd in ["vaciar", "limpiar", "borrar carrito", "eliminar todo"]):
            await self.cart_manager.clear_cart(phone_number)
            return """🛒 *Carrito vaciado*, grumete ⚓

¿Listo para zarpar de nuevo? Elige una opción:

1️⃣ *Disponibilidad y horarios*

2️⃣ *Precios por persona*

3️⃣ *Características del HotBoat*

4️⃣ *Extras y promociones*

5️⃣ *Ubicación y reseñas*

6️⃣ *Hablar con el Capitán Tomás*

¿Qué número eliges? 🚤"""

        # Remove Reserva FLEX via text command
        if "quitar flex" in message_lower or "sacar flex" in message_lower or "remover flex" in message_lower:
            cart = await self.cart_manager.get_cart(phone_number)
            flex_index = next((i for i, item in enumerate(cart) if item.name == "Reserva FLEX (+10%)"), None)
            if flex_index is None:
                return "⚓ No tienes Reserva FLEX en tu carrito actualmente."
            
            await self.cart_manager.remove_item(phone_number, contact_name, flex_index)
            cart = await self.cart_manager.get_cart(phone_number)
            cart_message = self.cart_manager.format_cart_message(cart)
            return f"""✅ *Reserva FLEX removida del carrito*

{cart_message}

📋 *¿Qué deseas hacer ahora?*

• Escribe 1-17 para agregar más extras
• 1️⃣8️⃣ Ver menú de extras completo
• 1️⃣9️⃣ Menú principal
• 2️⃣0️⃣ Proceder con el pago
• Escribe *vaciar* para vaciar el carrito

¿Qué opción eliges, grumete?"""
        
        # Remove item
        remove_match = re.search(r'eliminar\s+(\d+)', message_lower)
        if remove_match:
            item_index = int(remove_match.group(1)) - 1  # Convert to 0-based
            cart = await self.cart_manager.get_cart(phone_number)
            if 0 <= item_index < len(cart):
                await self.cart_manager.remove_item(phone_number, contact_name, item_index)
                cart = await self.cart_manager.get_cart(phone_number)
                return f"✅ Item eliminado del carrito\n\n{self.cart_manager.format_cart_message(cart)}"
            else:
                return "❌ Número de item inválido. Usa *carrito* para ver los números."
        
        # Add extra - Check if message mentions extras (with or without action words)
        # First check if there are extra keywords in the message
        has_extra_keywords = any(word in message_lower for word in ["tabla", "jugo", "bebida", "agua", "helado", "modo", "romantico", "romántico", "velas", "letras", "pack", "video", "transporte", "toalla", "chalas", "flex", "picoteo", "cookies", "frambuesa", "poncho", "sandalias"])
        
        # Check if message has action words or just mentions extras directly
        has_action_words = any(cmd in message_lower for cmd in ["agregar", "quiero", "necesito", "dame", "pon", "agrega"])
        
        # Detect if this is a direct extras request (e.g., "1 jugo y 2 helados")
        is_direct_extras_request = False
        if has_extra_keywords and not has_action_words:
            # Check if it contains numbers (quantities) and extra keywords
            has_numbers = bool(re.search(r'\d+', message_lower))
            # Make sure it's not just a simple menu number (1-6) or just "X helados" without other context
            is_simple_menu_number = message_lower.strip() in ['1', '2', '3', '4', '5', '6']
            # More strict check: must have number + "y" or comma (indicating multiple items)
            has_multiple_items_pattern = bool(re.search(r'\d+.*(y|,).*\d*', message_lower))
            if has_numbers and not is_simple_menu_number and has_multiple_items_pattern:
                is_direct_extras_request = True
        
        if (has_action_words and has_extra_keywords) or is_direct_extras_request:
            # If it's a direct request with numbers, try to parse multiple extras first
            if is_direct_extras_request:
                try:
                    multiple_extras_response = await self._try_parse_multiple_extras(message, phone_number, contact_name, conversation)
                    if multiple_extras_response:
                        return multiple_extras_response
                except Exception as e:
                    logger.error(f"Error in _try_parse_multiple_extras: {e}")
                    import traceback
                    traceback.print_exc()
                    # Continue to try single item parsing
            
            # Check for special cases that need clarification
            if "helado" in message_lower and not any(flavor in message_lower for flavor in ["cookies", "cream", "frambuesa", "chocolate"]):
                # Extract quantity if present
                quantity_match = re.search(r'(\d+)\s*helado', message_lower)
                quantity = int(quantity_match.group(1)) if quantity_match else 1
                
                # Ask for ice cream flavor
                conversation["metadata"]["awaiting_ice_cream_flavor"] = True
                conversation["metadata"]["pending_ice_cream_quantity"] = quantity
                
                quantity_text = f"los {quantity} helados" if quantity > 1 else "el helado"
                return f"""🍦 *Tenemos 2 sabores de helado:*

1️⃣ Cookies & Cream 🍪
2️⃣ Frambuesa a la Crema con Chocolate Belga 🍫

Precio: $3,500 c/u

¿Cuál sabor prefieres para {quantity_text}? (escribe el número) 🚤"""
            
            extra_item = self.cart_manager.parse_extra_from_message(message)
            if extra_item:
                warning_message = await self._require_reservation_for_extras(phone_number, conversation)
                if warning_message:
                    return warning_message
                
                await self.cart_manager.add_item(phone_number, contact_name, extra_item)
                cart = await self.cart_manager.get_cart(phone_number)
                return (
                    f"✅ *{extra_item.name} agregado al carrito*\n\n"
                    f"{self.cart_manager.format_cart_message(cart)}\n\n"
                    "📋 *¿Qué deseas hacer?*\n\n"
                    "• Escribe 1-17 para agregar más extras\n"
                    "• 1️⃣8️⃣ Ver menú de extras completo\n"
                    "• 1️⃣9️⃣ Menú principal\n"
                    "• 2️⃣0️⃣ Proceder con el pago\n"
                    "• Escribe *vaciar* para vaciar el carrito\n\n"
                    "¿Qué opción eliges, grumete?"
                )
            else:
                # Try to use AI to understand what they want
                conversation = await self.get_conversation(phone_number, contact_name)
                ai_response = await self._try_parse_extra_with_ai(message, phone_number, contact_name, conversation)
                if ai_response:
                    return ai_response
                
                # User tried to add something but we didn't recognize it
                return """❌ *No reconocí ese extra*, grumete ⚓

¿Qué te gustaría hacer?

1️⃣ Ver todos los extras disponibles
2️⃣ Proceder con el pago (sin agregar más)
3️⃣ Vaciar el carrito

Escribe el número que prefieras 🚤"""
        
        # Show cart with options (don't auto-confirm, let user choose)
        if any(cmd in message_lower for cmd in ["confirmar", "confirmo", "pagar", "comprar", "finalizar"]):
            cart = await self.cart_manager.get_cart(phone_number)
            if not cart:
                return "🛒 Tu carrito está vacío. Agrega items antes de confirmar."
            
            # Check if reservation exists
            has_reservation = any(item.item_type == "reservation" for item in cart)
            if not has_reservation:
                return self._cart_needs_reservation_message(conversation)
            
            # Show cart with options (don't auto-confirm)
            return self._format_cart_with_flex_options(cart)
        
        # Add reservation (if user specifies date and time after checking availability)
        # This will be handled when user confirms a specific slot
        if self._is_reservation_confirm(message_lower):
            # Try to parse reservation from message
            reservation_item = await self._parse_reservation_from_message(message, phone_number)
            if reservation_item:
                await self._add_reservation_with_flex(phone_number, contact_name, reservation_item)
                cart = await self.cart_manager.get_cart(phone_number)
                return self._format_cart_with_flex_options(cart)
        
        return None
    
    async def _add_reservation_with_flex(self, phone_number: str, contact_name: str, reservation_item):
        """
        Agrega una reserva al carrito e incluye automáticamente la opción Reserva FLEX
        """
        # Agregar la reserva
        await self.cart_manager.add_item(phone_number, contact_name, reservation_item)
        
        # Verificar si ya existe un FLEX en el carrito
        cart = await self.cart_manager.get_cart(phone_number)
        has_flex = any(item.name == "Reserva FLEX (+10%)" for item in cart)
        
        # Agregar Reserva FLEX automáticamente solo si no existe ya
        if not has_flex:
            flex_item = self.cart_manager.parse_extra_from_message("reserva flex")
            if flex_item:
                await self.cart_manager.add_item(phone_number, contact_name, flex_item)
                logger.info(f"Reserva FLEX agregada automáticamente para {phone_number}")
        else:
            logger.info(f"Reserva FLEX ya existe en el carrito de {phone_number}, no se agrega duplicado")
    
    def _format_cart_with_flex_options(self, cart: list) -> str:
        """
        Formatea el carrito con opciones específicas cuando incluye Reserva FLEX por defecto
        """
        cart_message = self.cart_manager.format_cart_message(cart)
        
        # Verificar si hay Reserva FLEX en el carrito
        has_flex = any(item.name == "Reserva FLEX (+10%)" for item in cart)
        
        if has_flex:
            return f"""✅ *Reserva agregada al carrito*

{cart_message}

💡 *Hemos incluido la Reserva FLEX* que te permite cancelar o reprogramar cuando quieras (+10% del costo de pasajeros)

📋 *¿Qué deseas hacer ahora?*

• Escribe 1-17 para agregar más extras
• 1️⃣8️⃣ Ver menú de extras completo
• 1️⃣9️⃣ Menú principal
• 2️⃣0️⃣ Proceder con el pago
• Escribe *quitar flex* para remover la Reserva FLEX
• Escribe *vaciar* para vaciar el carrito

¿Qué opción eliges, grumete?"""
        else:
            return f"""✅ *Reserva agregada al carrito*

{cart_message}

📋 *¿Qué deseas hacer ahora?*

• Escribe 1-17 para agregar más extras
• 1️⃣8️⃣ Ver menú de extras completo
• 1️⃣9️⃣ Menú principal
• 2️⃣0️⃣ Proceder con el pago
• Escribe *vaciar* para vaciar el carrito

¿Qué opción eliges, grumete?"""
    
    async def _is_cart_option_selection(self, message: str, phone_number: str, conversation: dict = None) -> bool:
        """
        Check if user is selecting a cart option (1-4 when Reserva FLEX present, 1-3 otherwise)
        Only returns True if the cart is not empty AND we're not awaiting other inputs
        """
        # If we're awaiting other inputs, this is NOT a cart option
        if conversation and conversation.get("metadata", {}).get("awaiting_extra_selection"):
            logger.info("Not a cart option: awaiting_extra_selection is True")
            return False
        if conversation and conversation.get("metadata", {}).get("awaiting_ice_cream_flavor"):
            return False
        if conversation and conversation.get("metadata", {}).get("awaiting_party_size"):
            return False
            
        message_stripped = message.strip()
        cart = await self.cart_manager.get_cart(phone_number)
        if len(cart) == 0:
            return False
        
        # Check if Reserva FLEX is in cart to determine valid options
        has_flex = any(item.name == "Reserva FLEX (+10%)" for item in cart)
        
        if has_flex:
            return message_stripped in ['1', '2', '3', '4']
        else:
            return message_stripped in ['1', '2', '3']
    
    async def _handle_cart_option_selection(self, message: str, phone_number: str, contact_name: str, conversation: dict) -> str:
        """
        Handle cart option selection (1-4 when Reserva FLEX present, 1-3 otherwise)
        
        Args:
            message: User's message
            phone_number: User's phone number
            contact_name: User's name
            conversation: Conversation context
        
        Returns:
            Response message
        """
        option = message.strip()
        language = conversation.get("metadata", {}).get("language", "es")
        cart = await self.cart_manager.get_cart(phone_number)
        has_flex = any(item.name == "Reserva FLEX (+10%)" for item in cart)
        
        # Si hay Reserva FLEX, las opciones son diferentes
        if has_flex:
            if option == '1':
                # Option 1: Agregar más extras
                conversation["metadata"]["awaiting_extra_selection"] = True
                return self.faq_handler.get_response("extras", language)
            
            elif option == '2':
                # Option 2: Proceder con el pago
                pass  # Continúa al código de pago abajo
            
            elif option == '3':
                # Option 3: Quitar Reserva FLEX
                # Buscar el índice de Reserva FLEX en el carrito
                flex_index = next((i for i, item in enumerate(cart) if item.name == "Reserva FLEX (+10%)"), None)
                if flex_index is not None:
                    await self.cart_manager.remove_item(phone_number, contact_name, flex_index)
                    cart = await self.cart_manager.get_cart(phone_number)
                    cart_message = self.cart_manager.format_cart_message(cart)
                    return f"""✅ *Reserva FLEX removida del carrito*

{cart_message}

📋 *¿Qué deseas hacer ahora?*

• Escribe 1-17 para agregar más extras
• 1️⃣8️⃣ Ver menú de extras completo
• 1️⃣9️⃣ Menú principal
• 2️⃣0️⃣ Proceder con el pago
• Escribe *vaciar* para vaciar el carrito

¿Qué opción eliges, grumete?"""
            
            elif option == '4':
                # Option 4: Vaciar el carrito
                await self.cart_manager.clear_cart(phone_number)
                return """🛒 *Carrito vaciado*, grumete ⚓

¿Listo para zarpar de nuevo? Elige una opción:

1️⃣ *Disponibilidad y horarios*
2️⃣ *Precios por persona*
3️⃣ *Características del HotBoat*
4️⃣ *Extras y promociones*
5️⃣ *Ubicación y reseñas*
6️⃣ *Hablar con el Capitán Tomás*

¿Qué número eliges? 🚤"""
        
        else:
            # Sin Reserva FLEX, opciones normales (1-3)
            if option == '1':
                # Option 1: Agregar un extra - mostrar menú con números
                conversation["metadata"]["awaiting_extra_selection"] = True
                return self.faq_handler.get_response("extras", language)
            
            elif option == '3':
                # Option 3: Vaciar el carrito
                await self.cart_manager.clear_cart(phone_number)
                return """🛒 *Carrito vaciado*, grumete ⚓

¿Listo para zarpar de nuevo? Elige una opción:

1️⃣ *Disponibilidad y horarios*
2️⃣ *Precios por persona*
3️⃣ *Características del HotBoat*
4️⃣ *Extras y promociones*
5️⃣ *Ubicación y reseñas*
6️⃣ *Hablar con el Capitán Tomás*

¿Qué número eliges? 🚤"""
            
            # Option 2: Proceder con el pago (aplica para ambos casos)
        
        if option == '2':
            # Proceder con el pago
            if not cart:
                return "🛒 Tu carrito está vacío. Agrega items antes de confirmar."
            
            # Check if reservation exists
            has_reservation = any(item.item_type == "reservation" for item in cart)
            if not has_reservation:
                return self._cart_needs_reservation_message(conversation)
            
            total = self.cart_manager.calculate_total(cart)
            reservation = next((item for item in cart if item.item_type == "reservation"), None)
            
            confirm_message = "✅ *Solicitud de Reserva Recibida*\n\n"
            confirm_message += f"📅 *Detalles de tu Solicitud:*\n"
            confirm_message += f"   Fecha: {reservation.metadata.get('date')}\n"
            confirm_message += f"   Horario: {reservation.metadata.get('time')}\n"
            confirm_message += f"   Personas: {reservation.quantity}\n\n"
            
            if len(cart) > 1:
                confirm_message += f"✨ *Extras solicitados:*\n"
                for item in cart:
                    if item.item_type == "extra":
                        confirm_message += f"   • {item.name}\n"
                confirm_message += "\n"
            
            confirm_message += f"💰 *Total estimado: ${total:,}*\n\n"
            confirm_message += f"📞 *El Capitán Tomás se comunicará contigo pronto por WhatsApp o teléfono para confirmar tu reserva y coordinar el pago* 👨‍✈️\n\n"
            confirm_message += f"Por mientras, envíanos tu *email* y *nombre completo* por favor 📝\n\n"
            confirm_message += f"¡Gracias por elegir HotBoat! 🚤🌊"
            
            notification_cart = list(cart)
            asyncio.create_task(
                self._notify_capitan_tomas(contact_name, phone_number, notification_cart, reason="reservation")
            )
            
            # Clear cart after confirmation
            await self.cart_manager.clear_cart(phone_number)
            
            return confirm_message
        
        return "No entendí esa opción. Por favor elige las opciones indicadas."
    
    async def _is_confirming_reservation_from_availability(self, message: str, conversation: dict) -> bool:
        """
        Check if user is confirming a reservation after seeing availability
        """
        message_lower = message.lower().strip()
        
        # Confirmation keywords
        confirmation_words = ['si', 'sí', 'claro', 'dale', 'ok', 'okay', 'confirmo', 'confirmar', 'hagamosla', 'hagámosla', 'yes']
        
        if message_lower not in confirmation_words:
            return False
        
        # Check if recent messages show availability was checked
        if not conversation or not conversation.get("messages"):
            return False
        
        recent_messages = conversation["messages"][-5:]  # Check last 5 messages
        
        for msg in reversed(recent_messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", "").lower()
                # Check if the message contains availability info and reservation intent
                if ("disponibilidad" in content or "precio" in content) and ("personas" in content) and ("reserva" in content or "hacer" in content or "decides" in content):
                    return True
        
        return False
    
    async def _handle_reservation_confirmation(self, message: str, phone_number: str, contact_name: str, conversation: dict) -> str:
        """
        Handle user confirming a reservation after seeing availability
        Extract reservation details from recent conversation
        """
        try:
            # Look for reservation details in recent messages
            recent_messages = conversation["messages"][-10:]  # Check last 10 messages
            
            date = None
            time = None
            party_size = None
            
            import re
            
            for msg in reversed(recent_messages):
                content = msg.get("content", "")
                
                # Look for "martes a las 16 para 3 personas" pattern in user messages
                if msg.get("role") == "user":
                    # Try to extract date/time/party size
                    match = re.search(r'(lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)\s+a\s+las\s+(\d{1,2})\s+para\s+(\d+)\s+personas?', content.lower())
                    if match:
                        day_name = match.group(1)
                        hour = int(match.group(2))
                        party_size = int(match.group(3))
                        
                        # Calculate date from day name
                        from datetime import datetime, timedelta
                        import pytz
                        
                        CHILE_TZ = pytz.timezone('America/Santiago')
                        now = datetime.now(CHILE_TZ)
                        
                        spanish_days = {
                            'lunes': 0, 'martes': 1, 'miercoles': 2, 'miércoles': 2,
                            'jueves': 3, 'viernes': 4, 'sabado': 5, 'sábado': 5,
                            'domingo': 6
                        }
                        
                        target_dow = spanish_days.get(day_name)
                        if target_dow is not None:
                            current_dow = now.weekday()
                            days_ahead = target_dow - current_dow
                            if days_ahead <= 0:
                                days_ahead += 7
                            target_date = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
                            
                            spanish_months = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                                             'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
                            date = f"{target_date.day} de {spanish_months[target_date.month - 1]} {target_date.year}"
                            
                            # Convert hour to operating hours
                            if hour == 16:
                                hour = 15
                            elif hour == 10:
                                hour = 9
                            elif hour in [9, 12, 15, 18, 21]:
                                pass
                            else:
                                available_slots = [9, 12, 15, 18, 21]
                                hour = min(available_slots, key=lambda x: abs(x - hour))
                            
                            time = f"{hour:02d}:00"
                            break
            
            if not date or not time or not party_size:
                return "No pude encontrar los detalles de la reserva. Por favor, dime la fecha, hora y número de personas nuevamente. Por ejemplo: 'El martes a las 16 para 3 personas' 🚤"
            
            # Validate minimum 4 hours advance booking
            from datetime import datetime
            import pytz
            
            CHILE_TZ = pytz.timezone('America/Santiago')
            now = datetime.now(CHILE_TZ)
            
            # Parse the reservation datetime
            hour = int(time.split(':')[0])
            reservation_datetime = target_date.replace(hour=hour, minute=0, second=0, microsecond=0)
            
            hours_ahead = (reservation_datetime - now).total_seconds() / 3600
            if hours_ahead < 4:
                logger.info(f"Reservation too soon: {hours_ahead:.1f} hours ahead (minimum 4 hours required)")
                return f"""⏰ *Lo siento, grumete*

Las reservas deben hacerse con un mínimo de *4 horas de anticipación*.

Tu horario solicitado es en {hours_ahead:.1f} horas, necesitas reservar para más adelante.

Por favor, elige un horario con al menos 4 horas de anticipación 🚤"""
            
            # Create reservation item
            reservation_item = self.cart_manager.create_reservation_item(
                date=date,
                time=time,
                capacity=party_size
            )
            
            # Add to cart with Reserva FLEX
            await self._add_reservation_with_flex(phone_number, contact_name, reservation_item)
            cart = await self.cart_manager.get_cart(phone_number)
            
            return self._format_cart_with_flex_options(cart)
            
        except Exception as e:
            logger.error(f"Error handling reservation confirmation: {e}")
            import traceback
            traceback.print_exc()
            return "Hubo un error procesando tu reserva. Por favor, intenta especificar la fecha, hora y número de personas nuevamente. Por ejemplo: 'El martes a las 16 para 3 personas' 🚤"
    
    async def _try_parse_date_time_only(self, message: str, conversation: dict = None) -> Optional[dict]:
        """
        Try to parse date and time from message (WITHOUT party size)
        Returns dict with 'date' and 'time' if found
        """
        try:
            from datetime import datetime, timedelta
            import pytz
            
            message_lower = message.lower().strip()
            
            # Skip if message includes party size
            if 'persona' in message_lower or any(str(i) in message_lower and ('para' in message_lower or 'somos' in message_lower) for i in range(2, 8)):
                return None
            
            # Check if message contains date/time pattern
            if not (
                'a las' in message_lower
                or any(day in message_lower for day in ['lunes', 'martes', 'miércoles', 'miercoles', 'jueves', 'viernes', 'sábado', 'sabado', 'domingo'])
                or any(month in message_lower for month in ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'])
                or re.search(r'\d{1,2}[:h]\d{0,2}', message_lower)
            ):
                return None
            
            CHILE_TZ = pytz.timezone('America/Santiago')
            now = datetime.now(CHILE_TZ)
            
            spanish_days = {
                'lunes': 0, 'martes': 1, 'miercoles': 2, 'miércoles': 2,
                'jueves': 3, 'viernes': 4, 'sabado': 5, 'sábado': 5,
                'domingo': 6
            }
            
            day_names_pattern = '(lunes|martes|miércoles|miercoles|jueves|viernes|sábado|sabado|domingo)'
            month_names_pattern = '(' + '|'.join(SPANISH_MONTHS.keys()) + ')'
            available_slots = [9, 12, 15, 18, 21]
            
            def normalize_hour(hour_value: int) -> int:
                if hour_value < available_slots[0]:
                    return available_slots[0]
                if hour_value > available_slots[-1]:
                    return available_slots[-1]
                if hour_value not in available_slots:
                    return min(available_slots, key=lambda x: abs(x - hour_value))
                return hour_value
            
            def resolve_date(day: Optional[int] = None, month: Optional[Union[int, str]] = None, day_name: Optional[str] = None):
                month_int = None
                if isinstance(month, str):
                    month_int = SPANISH_MONTHS.get(month.lower())
                elif month is not None:
                    month_int = int(month)
                
                day_index = None
                if day_name:
                    day_index = spanish_days.get(day_name.lower())
                
                # Case 1: specific month and day
                if month_int and day:
                    for year_offset in range(0, 2):
                        year_candidate = now.year + year_offset
                        try:
                            candidate = CHILE_TZ.localize(datetime(year_candidate, month_int, day, 0, 0, 0))
                        except ValueError:
                            continue
                        if candidate < now:
                            continue
                        if day_index is not None and candidate.weekday() != day_index:
                            continue
                        return candidate
                    return None
                
                # Case 2: only day number (and optionally day name)
                if day is not None:
                    for month_offset in range(0, 13):
                        month_candidate = ((now.month - 1 + month_offset) % 12) + 1
                        year_candidate = now.year + ((now.month - 1 + month_offset) // 12)
                        try:
                            candidate = CHILE_TZ.localize(datetime(year_candidate, month_candidate, day, 0, 0, 0))
                        except ValueError:
                            continue
                        if candidate < now:
                            continue
                        if day_index is not None and candidate.weekday() != day_index:
                            continue
                        return candidate
                    return None
                
                # Case 3: only day name
                if day_index is not None:
                    days_ahead = (day_index - now.weekday()) % 7
                    if days_ahead == 0:
                        days_ahead = 7
                    candidate = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
                    return candidate
                
                return None
            
            patterns = [
                ("full", re.compile(rf'\b(?:el\s+)?(?:(?P<day_name>{day_names_pattern})\s+)?(?P<day>\d{{1,2}})\s+de\s+(?P<month>{month_names_pattern})\s+a\s+las\s+(?P<hour>\d{{1,2}})(?:[:h\.](?P<minutes>\d{{2}}))?\b')),
                ("full_compact", re.compile(rf'\b(?:el\s+)?(?:(?P<day_name>{day_names_pattern})\s+)?(?P<day>\d{{1,2}})\s+de\s+(?P<month>{month_names_pattern})\s+(?P<hour>\d{{1,2}})(?:[:h\.](?P<minutes>\d{{2}}))?\b')),
                ("day_name_day", re.compile(rf'\b(?:el\s+)?(?P<day_name>{day_names_pattern})\s+(?P<day>\d{{1,2}})\s+a\s+las\s+(?P<hour>\d{{1,2}})(?:[:h\.](?P<minutes>\d{{2}}))?\b')),
                ("day_name_only", re.compile(rf'\b(?:el\s+)?(?P<day_name>{day_names_pattern})\s+a\s+las\s+(?P<hour>\d{{1,2}})(?:[:h\.](?P<minutes>\d{{2}}))?\b')),
                ("numeric", re.compile(r'\b(?P<day>\d{1,2})/(?P<month>\d{1,2})\s+a\s+las\s+(?P<hour>\d{1,2})(?:[:h\.](?P<minutes>\d{2}))?\b')),
                ("numeric_compact", re.compile(r'\b(?P<day>\d{1,2})/(?P<month>\d{1,2})\s+(?P<hour>\d{1,2})(?:[:h\.](?P<minutes>\d{2}))?\b')),
                ("day_only", re.compile(r'\b(?:el\s+)?(?P<day>\d{1,2})\s+a\s+las\s+(?P<hour>\d{1,2})(?:[:h\.](?P<minutes>\d{2}))?\b')),
            ]
            
            for pattern_type, regex in patterns:
                match = regex.search(message_lower)
                if not match:
                    continue
                
                groups = match.groupdict()
                
                hour_raw = groups.get("hour")
                if not hour_raw or not hour_raw.isdigit():
                    continue
                hour = normalize_hour(int(hour_raw))
                
                minutes_raw = groups.get("minutes")
                minutes = int(minutes_raw) if minutes_raw and minutes_raw.isdigit() else 0
                minutes = 0  # Horarios oficiales son en punto
                
                day_name = groups.get("day_name")
                if day_name:
                    day_name = day_name.lower()
                
                day_str = groups.get("day")
                day = int(day_str) if day_str and day_str.isdigit() else None
                
                month_value = groups.get("month")
                if month_value:
                    month_value = month_value.lower()
                
                target_date = None
                if month_value:
                    target_date = resolve_date(day=day, month=month_value, day_name=day_name)
                else:
                    target_date = resolve_date(day=day, day_name=day_name)
                    if not target_date and day_name:
                        target_date = resolve_date(day=None, day_name=day_name)
                
                if not target_date:
                    continue
                
                reservation_datetime = target_date.replace(hour=hour, minute=minutes, second=0, microsecond=0)
                hours_ahead = (reservation_datetime - now).total_seconds() / 3600
                
                if hours_ahead < 4:
                    logger.info(f"Date/time too soon: {hours_ahead:.1f} hours ahead (minimum 4 hours required)")
                    continue
                
                spanish_months_names = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                                        'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
                date_str = f"{reservation_datetime.day} de {spanish_months_names[reservation_datetime.month - 1]} {reservation_datetime.year}"
                time_str = f"{hour:02d}:00"
                
                logger.info(f"Parsed date/time only: date={date_str}, time={time_str}, hours_ahead={hours_ahead:.1f}")
                return {
                    "date": date_str,
                    "time": time_str,
                    "raw_message": message
                }
            
            return None
        except Exception as e:
            logger.warning(f"Error parsing date/time only: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _prepare_reservation_flow(self, conversation: dict, reset: bool = False) -> None:
        """Initialize or reset reservation-related metadata."""
        metadata = conversation.setdefault("metadata", {})
        if reset or not metadata.get("pending_reservation"):
            metadata["pending_reservation"] = {
                "date": None,
                "time": None,
                "date_obj_iso": None
            }
        metadata["available_times_for_date"] = []
        metadata["awaiting_reservation_date"] = True
        metadata["awaiting_reservation_time"] = False
        metadata["awaiting_party_size"] = False
        metadata["awaiting_date_time_selection"] = False
    
    async def _handle_multiple_menu_selections(
        self,
        menu_numbers: list,
        conversation: dict,
        language: str,
        from_number: str,
        contact_name: str
    ) -> str:
        """
        Handle multiple menu number selections and return combined response.
        
        Args:
            menu_numbers: List of menu numbers selected (1-6)
            conversation: Conversation context
            language: Language code
            from_number: User's phone number
            contact_name: User's contact name
        
        Returns:
            Combined response with all selected menu information
        """
        responses = []
        
        # Menu option titles for separators
        option_titles = {
            1: {"es": "📅 DISPONIBILIDAD Y HORARIOS", "en": "📅 AVAILABILITY AND SCHEDULES", "pt": "📅 DISPONIBILIDADE E HORÁRIOS"},
            2: {"es": "💰 PRECIOS POR PERSONA", "en": "💰 PRICES PER PERSON", "pt": "💰 PREÇOS POR PESSOA"},
            3: {"es": "🚤 CARACTERÍSTICAS DEL HOTBOAT", "en": "🚤 HOTBOAT FEATURES", "pt": "🚤 CARACTERÍSTICAS DO HOTBOAT"},
            4: {"es": "✨ EXTRAS Y PROMOCIONES", "en": "✨ EXTRAS AND PROMOTIONS", "pt": "✨ EXTRAS E PROMOÇÕES"},
            5: {"es": "📍 UBICACIÓN Y RESEÑAS", "en": "📍 LOCATION AND REVIEWS", "pt": "📍 LOCALIZAÇÃO E AVALIAÇÕES"},
            6: {"es": "📞 LLAMAR AL CAPITÁN TOMÁS", "en": "📞 CALL CAPTAIN TOMÁS", "pt": "📞 LIGAR PARA O CAPITÃO TOMÁS"}
        }
        
        for menu_number in menu_numbers:
            # Add title separator
            if menu_number in option_titles:
                title = option_titles[menu_number].get(language, option_titles[menu_number]["es"])
                responses.append(f"\n{'='*40}\n{title}\n{'='*40}\n")
            
            if menu_number == 1:
                # Option 1: Disponibilidad y horarios
                responses.append(self._ask_for_reservation_date(conversation, language))
            elif menu_number == 2:
                # Option 2: Precios por persona
                responses.append(self.faq_handler.get_response("precio", language))
            elif menu_number == 3:
                # Option 3: Características del HotBoat
                responses.append(self.faq_handler.get_response("caracteristicas", language))
            elif menu_number == 4:
                # Option 4: Extras y promociones
                conversation["metadata"]["awaiting_extra_selection"] = True
                responses.append(self.faq_handler.get_response("extras", language))
            elif menu_number == 5:
                # Option 5: Ubicación y reseñas
                responses.append(self.faq_handler.get_response("ubicación", language))
            elif menu_number == 6:
                # Option 6: Llamar a Tomás
                await self._notify_capitan_tomas(contact_name, from_number, [], reason="call_request")
                responses.append(self.faq_handler.get_response("llamar a tomas", language))
        
        # Combine all responses with a separator
        combined_response = "\n".join(responses)
        
        # Add a final note
        if language == "es":
            combined_response += "\n\n━━━━━━━━━━━━━━━━━━━━━━━━\n\n¿Necesitas información adicional? Escríbeme 'menú' para ver todas las opciones ⚓"
        elif language == "en":
            combined_response += "\n\n━━━━━━━━━━━━━━━━━━━━━━━━\n\nNeed additional information? Write 'menu' to see all options ⚓"
        elif language == "pt":
            combined_response += "\n\n━━━━━━━━━━━━━━━━━━━━━━━━\n\nPrecisa de informações adicionais? Escreva 'menu' para ver todas as opções ⚓"
        
        return combined_response

    def _ask_for_reservation_date(self, conversation: dict, language: str = "es") -> str:
        """Prompt user to choose a date as first step of reservation flow."""
        self._prepare_reservation_flow(conversation, reset=True)
        return get_text("ask_for_date", language)

    async def _handle_reservation_date_response(
        self,
        message: str,
        phone_number: str,
        contact_name: str,
        conversation: dict
    ) -> str:
        """Handle user's response when we are waiting for the reservation date."""
        metadata = conversation.setdefault("metadata", {})
        message_clean = message.strip()
        message_lower = message_clean.lower()
        
        # Allow global shortcuts while in this state
        if message_clean in ["19"] or message_lower in ["menu", "menú", "principal"]:
            self._reset_reservation_flow(conversation)
            language = conversation.get("metadata", {}).get("language", "es")
            return self._get_main_menu_message(language)
        if message_clean == "18":
            return self.faq_handler.get_response("extras", language)
        if message_clean == "20":
            cart = await self.cart_manager.get_cart(phone_number)
            if not cart:
                return "🛒 Tu carrito está vacío, grumete ⚓\n\n¿Qué te gustaría agregar? 🚤"
            has_reservation = any(item.item_type == "reservation" for item in cart)
            if has_reservation:
                total = self.cart_manager.calculate_total(cart)
                reservation = next((item for item in cart if item.item_type == "reservation"), None)
                confirm_message = "✅ *Solicitud de Reserva Recibida*\n\n"
                confirm_message += f"📅 *Detalles de tu Solicitud:*\n"
                confirm_message += f"   Fecha: {reservation.metadata.get('date')}\n"
                confirm_message += f"   Horario: {reservation.metadata.get('time')}\n"
                confirm_message += f"   Personas: {reservation.quantity}\n\n"
                extras = [item for item in cart if item.item_type == "extra"]
                if extras:
                    confirm_message += "✨ *Extras solicitados:*\n"
                    for item in extras:
                        confirm_message += f"   • {item.name}\n"
                    confirm_message += "\n"
                confirm_message += f"💰 *Total estimado: ${total:,}*\n\n"
                confirm_message += "📞 *El Capitán Tomás se comunicará contigo pronto para confirmar y coordinar el pago* 👨‍✈️\n\n"
                confirm_message += "Por mientras, envíanos tu *email* y *nombre completo* por favor 📝\n\n"
                confirm_message += "¡Gracias por elegir HotBoat! 🚤🌊"
                await self._notify_capitan_tomas(contact_name, phone_number, cart, reason="reservation")
                await self.cart_manager.clear_cart(phone_number)
                self._reset_reservation_flow(conversation)
                return confirm_message
            return f"{self.cart_manager.format_cart_message(cart)}\n\n{self._cart_needs_reservation_message(conversation)}"
        
        parsed_date = self._parse_reservation_date(message_lower)
        if not parsed_date:
            return """Necesito la fecha exacta para continuar ⚓

Por ejemplo:
• *14 de noviembre*
• *viernes*
• *mañana*

¿Qué día prefieres?"""
        
        available_slots = await self.availability_checker.get_slots_for_date(parsed_date["date_obj"])
        available_times = sorted({slot['time'] for slot in available_slots})
        
        if not available_times:
            metadata["awaiting_reservation_date"] = True
            metadata["available_times_for_date"] = []
            return f"""❌ *No tenemos horarios disponibles el {parsed_date['display']}*.

¿Te gustaría intentar con otra fecha?"""
        
        metadata["pending_reservation"] = {
            "date": parsed_date["display"],
            "time": None,
            "date_obj_iso": parsed_date["date_obj"].isoformat()
        }
        metadata["available_times_for_date"] = available_times
        metadata["awaiting_reservation_date"] = False
        metadata["awaiting_reservation_time"] = True
        metadata["awaiting_date_time_selection"] = True
        
        times_message = self._format_available_times(available_times)
        return f"""✅ *El {parsed_date['display']} tenemos cupos disponibles.*

⏰ Horarios: {times_message}

¿Qué horario prefieres? (ej: 15:00)"""

    async def _handle_reservation_time_response(
        self,
        message: str,
        phone_number: str,
        contact_name: str,
        conversation: dict
    ) -> str:
        """Handle user's response when we are waiting for the reservation time."""
        metadata = conversation.setdefault("metadata", {})
        message_clean = message.strip()
        message_lower = message_clean.lower()
        language = conversation.get("metadata", {}).get("language", "es")
        
        if message_clean in ["19"] or message_lower in ["menu", "menú", "principal"]:
            self._reset_reservation_flow(conversation)
            language = conversation.get("metadata", {}).get("language", "es")
            return self._get_main_menu_message(language)
        if message_clean == "18":
            return self.faq_handler.get_response("extras", language)
        if message_clean == "20":
            cart = await self.cart_manager.get_cart(phone_number)
            if not cart:
                return "🛒 Tu carrito está vacío, grumete ⚓\n\n¿Qué te gustaría agregar? 🚤"
            has_reservation = any(item.item_type == "reservation" for item in cart)
            if has_reservation:
                total = self.cart_manager.calculate_total(cart)
                reservation = next((item for item in cart if item.item_type == "reservation"), None)
                confirm_message = "✅ *Solicitud de Reserva Recibida*\n\n"
                confirm_message += f"📅 *Detalles de tu Solicitud:*\n"
                confirm_message += f"   Fecha: {reservation.metadata.get('date')}\n"
                confirm_message += f"   Horario: {reservation.metadata.get('time')}\n"
                confirm_message += f"   Personas: {reservation.quantity}\n\n"
                extras = [item for item in cart if item.item_type == "extra"]
                if extras:
                    confirm_message += "✨ *Extras solicitados:*\n"
                    for item in extras:
                        confirm_message += f"   • {item.name}\n"
                    confirm_message += "\n"
                confirm_message += f"💰 *Total estimado: ${total:,}*\n\n"
                confirm_message += "📞 *El Capitán Tomás se comunicará contigo pronto para confirmar y coordinar el pago* 👨‍✈️\n\n"
                confirm_message += "Por mientras, envíanos tu *email* y *nombre completo* por favor 📝\n\n"
                confirm_message += "¡Gracias por elegir HotBoat! 🚤🌊"
                await self._notify_capitan_tomas(contact_name, phone_number, cart, reason="reservation")
                await self.cart_manager.clear_cart(phone_number)
                self._reset_reservation_flow(conversation)
                conversation["metadata"]["awaiting_party_size"] = False
                return confirm_message
            return f"{self.cart_manager.format_cart_message(cart)}\n\n{self._cart_needs_reservation_message(conversation)}"
        
        pending = metadata.get("pending_reservation")
        if not pending or not pending.get("date_obj_iso"):
            self._reset_reservation_flow(conversation)
            return "Perdí la fecha seleccionada. Empecemos de nuevo, ¿para qué día te gustaría reservar?"
        
        available_times = metadata.get("available_times_for_date", [])
        normalized_time = self._normalize_time_input(message_lower)
        if not normalized_time:
            return f"""No reconocí el horario ⚓

Recuerda elegir uno de estos:
{self._format_available_times(available_times, bullet_list=True)}

Escribe por ejemplo: 15:00"""
        
        if available_times and normalized_time not in available_times:
            return f"""Ese horario no está disponible para {pending.get('date')} ⚓

Horarios disponibles:
{self._format_available_times(available_times, bullet_list=True)}

¿Cuál prefieres?"""
        
        try:
            date_obj = datetime.fromisoformat(pending["date_obj_iso"])
            hour, minute = map(int, normalized_time.split(":"))
            reservation_datetime = date_obj.replace(hour=hour, minute=minute)
            now = datetime.now(CHILE_TZ)
            hours_ahead = (reservation_datetime - now).total_seconds() / 3600
            if hours_ahead < 4:
                return "Necesitamos al menos 4 horas de anticipación. ¿Puedes elegir un horario más adelante?"
        except Exception as exc:
            logger.warning(f"Error validating reservation datetime: {exc}")
            return "No logré validar ese horario. ¿Podrías escribirlo en formato HH:MM? (ej: 15:00)"
        
        pending["time"] = normalized_time
        metadata["pending_reservation"] = pending
        metadata["awaiting_reservation_time"] = False
        metadata["awaiting_party_size"] = True
        metadata["awaiting_date_time_selection"] = False
        
        return f"""⏰ ¡Listo! El {pending.get('date')} a las {normalized_time}.

¿Para cuántas personas será la navegación? (2 a 7 personas)"""

    def _parse_reservation_date(self, message_lower: str) -> Optional[Dict[str, object]]:
        """Parse reservation date from user input."""
        now = datetime.now(CHILE_TZ)
        
        if not message_lower:
            return None
        
        if "mañana" in message_lower:
            target = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif "hoy" in message_lower:
            target = now.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            exact_date = self.availability_checker.parse_exact_date(message_lower)
            if exact_date:
                target = exact_date.replace(hour=0, minute=0, second=0, microsecond=0)
            else:
                contains_digits = any(char.isdigit() for char in message_lower)
                day_names = {
                    'lunes': 0, 'martes': 1, 'miercoles': 2, 'miércoles': 2,
                    'jueves': 3, 'viernes': 4, 'sabado': 5, 'sábado': 5,
                    'domingo': 6
                }
                matched_day = None
                if not contains_digits:
                    for name, dow in day_names.items():
                        if name in message_lower:
                            matched_day = dow
                            break
                if matched_day is None:
                    return None
                current_dow = now.weekday()
                days_ahead = matched_day - current_dow
                if days_ahead <= 0:
                    days_ahead += 7
                target = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        if target.tzinfo is None:
            target = CHILE_TZ.localize(target)
        
        display = self._format_spanish_date(target)
        return {"date_obj": target, "display": display}

    def _format_spanish_date(self, date_obj: datetime) -> str:
        """Format datetime into Spanish human-readable date."""
        spanish_months = [
            'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
            'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'
        ]
        return f"{date_obj.day} de {spanish_months[date_obj.month - 1]} {date_obj.year}"

    def _format_available_times(self, times: List[str], bullet_list: bool = False) -> str:
        """Format list of available time strings."""
        if not times:
            return ""
        if bullet_list:
            return "\n".join(f"• {time_str}" for time_str in times)
        return ", ".join(times)

    def _normalize_time_input(self, message_lower: str) -> Optional[str]:
        """Normalize user time input to HH:MM format."""
        cleaned = message_lower
        replacements = [" horas", " hora", "hrs", "hr", "h", " pm", " a. m.", " a.m.", " p. m.", " p.m."]
        for token in replacements:
            cleaned = cleaned.replace(token, "")
        cleaned = cleaned.strip()
        
        period = None
        if "pm" in message_lower or "p.m" in message_lower:
            period = "pm"
        elif "am" in message_lower or "a.m" in message_lower:
            period = "am"
        
        match = re.search(r'(\d{1,2})(?:[:.,](\d{1,2}))?', cleaned)
        if not match:
            return None
        
        hour = int(match.group(1))
        minute_str = match.group(2)
        minute = int(minute_str) if minute_str is not None else 0
        
        if minute >= 60:
            return None
        
        if period == "pm" and hour < 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0
        
        if hour > 23:
            return None
        
        return f"{hour:02d}:{minute:02d}"

    def _reset_reservation_flow(self, conversation: dict) -> None:
        """Clear reservation-related metadata flags."""
        metadata = conversation.setdefault("metadata", {})
        metadata["awaiting_reservation_date"] = False
        metadata["awaiting_reservation_time"] = False
        metadata["awaiting_party_size"] = False
        metadata["available_times_for_date"] = []
        metadata["awaiting_date_time_selection"] = False
        metadata["pending_reservation"] = None
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text removing accents for keyword matching."""
        normalized = unicodedata.normalize("NFD", text.lower())
        return "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    
    def _is_help_request(self, message: str) -> bool:
        """Detect if user is asking for help or to contact Capitán Tomás."""
        normalized = self._normalize_text(message)
        tokens = re.findall(r'\b\w+\b', normalized)
        
        if "ayuda" in tokens:
            return True
        if "tomas" in tokens and ("capitan" in tokens or "hablar" in tokens or "llamar" in tokens or len(tokens) == 1):
            return True
        if "tomas" in tokens:
            # Standalone mentions of Tomás should also trigger
            return True
        
        phrases = [
            "hablar con tomas",
            "llamar a tomas",
            "contactar a tomas",
            "necesito a tomas",
            "capitan tomas",
            "capitan tomas"
        ]
        return any(phrase in normalized for phrase in phrases)
    
    def _format_plain_text(self, text: str) -> str:
        """Convert markdown-styled text into plain text for email."""
        plain = text.replace("*", "")
        plain = plain.replace("•", "-")
        return plain
    
    async def _send_notification_email(self, subject: str, body: str, priority: str = "high") -> None:
        """Send email notification using Resend API (works on Railway/PaaS)."""
        if not getattr(self.settings, "email_enabled", False):
            logger.info("Email notifications disabled (EMAIL_ENABLED=false); skipping send.")
            return
        
        if not RESEND_AVAILABLE:
            logger.warning("Resend library not installed; cannot send email notification.")
            return
        
        if not self.notification_email_recipients:
            logger.warning("No notification emails configured (NOTIFICATION_EMAILS env variable). Skipping email send.")
            return
        
        resend_key = getattr(self.settings, "resend_api_key", "")
        if not resend_key:
            logger.warning("RESEND_API_KEY not configured; cannot send email notification.")
            return
        
        try:
            # Configure Resend API key
            resend.api_key = resend_key
            
            # Convert body to HTML (preserve line breaks)
            html_body = f"<pre style='font-family: monospace; white-space: pre-wrap;'>{body}</pre>"
            
            # Send email via Resend API
            result = resend.Emails.send({
                "from": self.email_sender,
                "to": self.notification_email_recipients,
                "subject": subject,
                "html": html_body,
            })
            
            logger.info(f"Email notification sent via Resend: {subject} (ID: {result.get('id', 'N/A')})")
        except Exception as e:
            logger.error(f"Error sending email notification via Resend: {e}")
            import traceback
            traceback.print_exc()
    
    async def send_audio_message(self, to: str, audio_path: str = None, audio_url: str = None) -> bool:
        """
        Send an audio message to a user
        
        Args:
            to: Recipient phone number
            audio_path: Local path to audio file (will be uploaded to WhatsApp)
            audio_url: URL to audio file (publicly accessible)
        
        Returns:
            True if successful, False otherwise
        """
        try:
            media_id = None
            
            # If we have a local file, upload it first
            if audio_path:
                logger.info(f"Uploading audio from local path: {audio_path}")
                # Determine MIME type based on extension
                import os
                ext = os.path.splitext(audio_path)[1].lower()
                mime_type = "audio/ogg"  # Default
                if ext == ".mp3":
                    mime_type = "audio/mpeg"
                elif ext == ".m4a":
                    mime_type = "audio/mp4"
                elif ext == ".wav":
                    mime_type = "audio/wav"
                elif ext == ".aac":
                    mime_type = "audio/aac"
                
                media_id = await self.whatsapp_client.upload_media(audio_path, mime_type)
                if not media_id:
                    logger.error(f"Failed to upload audio file: {audio_path}")
                    if not audio_url:
                        return False
            
            # Send the audio message
            if media_id:
                await self.whatsapp_client.send_audio_message(to, media_id=media_id)
                logger.info(f"✅ Audio sent successfully using media_id to {to}")
                return True
            elif audio_url:
                await self.whatsapp_client.send_audio_message(to, audio_url=audio_url)
                logger.info(f"✅ Audio sent successfully using URL to {to}")
                return True
            else:
                logger.error("No audio source provided (neither path nor URL)")
                return False
                
        except Exception as e:
            logger.error(f"Error sending audio message: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    async def _handle_party_size_response(self, message: str, phone_number: str, contact_name: str, conversation: dict) -> str:
        """Handle user's response with party size after selecting date/time"""
        try:
            # Extract number from message
            import re
            numbers = re.findall(r'\d+', message)
            
            if not numbers:
                return "Por favor indica el número de personas (entre 2 y 7) 🚤"
            
            party_size = int(numbers[0])
            
            if party_size < 2 or party_size > 7:
                return "El HotBoat tiene capacidad para 2 a 7 personas. ¿Cuántas personas son? 🚤"
            
            # Get the pending reservation from conversation
            pending = conversation.get("metadata", {}).get("pending_reservation")
            
            if not pending:
                return "Lo siento, no encontré la reserva pendiente. Por favor, inicia el proceso de nuevo."
            
            # Validate minimum 4 hours advance (this should already be validated, but double-check)
            # The pending reservation should already have been validated in _try_parse_date_time_only
            # But we add this as a safeguard
            
            # Create reservation item
            reservation_item = self.cart_manager.create_reservation_item(
                date=pending['date'],
                time=pending['time'],
                capacity=party_size
            )
            
            # Add to cart with Reserva FLEX
            await self._add_reservation_with_flex(phone_number, contact_name, reservation_item)
            cart = await self.cart_manager.get_cart(phone_number)
            
            # Clear the pending state
            self._reset_reservation_flow(conversation)
            conversation["metadata"]["awaiting_party_size"] = False
            
            return self._format_cart_with_flex_options(cart)
            
        except Exception as e:
            logger.error(f"Error handling party size response: {e}")
            import traceback
            traceback.print_exc()
            # Clear the pending state
            self._reset_reservation_flow(conversation)
            conversation["metadata"]["awaiting_party_size"] = False
            return "Hubo un error procesando tu reserva. Por favor, intenta de nuevo."
    
    async def _handle_ice_cream_flavor_response(self, message: str, phone_number: str, contact_name: str, conversation: dict) -> str:
        """Handle user's response with ice cream flavor choice"""
        try:
            message_lower = message.lower().strip()
            
            # Get the pending quantity (default to 1)
            quantity = conversation["metadata"].get("pending_ice_cream_quantity", 1)
            
            # Check if they chose by number or by name
            ice_cream_item = None
            
            if message_lower in ['1', 'uno', 'cookies', 'cream', 'cookies & cream', 'cookies and cream']:
                ice_cream_item = self.cart_manager.parse_extra_from_message("helado cookies")
            elif message_lower in ['2', 'dos', 'frambuesa', 'chocolate', 'frambuesa chocolate']:
                ice_cream_item = self.cart_manager.parse_extra_from_message("helado frambuesa")
            
            # Get pending extras (if any)
            pending_extras = conversation["metadata"].get("pending_extras", [])

            warning_message = await self._require_reservation_for_extras(phone_number, conversation)
            if warning_message:
                return warning_message
            
            # Clear the awaiting state
            conversation["metadata"]["awaiting_ice_cream_flavor"] = False
            conversation["metadata"]["pending_ice_cream_quantity"] = None
            conversation["metadata"]["pending_extras"] = []
            
            if ice_cream_item:
                # Set the quantity
                ice_cream_item.quantity = quantity
                await self.cart_manager.add_item(phone_number, contact_name, ice_cream_item)
                
                # Add any pending extras
                added_extras = [ice_cream_item.name]
                if pending_extras:
                    for number in pending_extras:
                        if number in EXTRAS_NUMBER_MAP:
                            extra_name = EXTRAS_NUMBER_MAP[number]
                            extra_item = self.cart_manager.parse_extra_from_message(extra_name)
                            if extra_item:
                                await self.cart_manager.add_item(phone_number, contact_name, extra_item)
                                added_extras.append(extra_item.name)
                                logger.info(f"Added pending extra #{number}: {extra_name}")
                
                cart = await self.cart_manager.get_cart(phone_number)
                
                # Build response based on number of items added
                if len(added_extras) == 1:
                    quantity_text = f"{quantity}x {ice_cream_item.name}" if quantity > 1 else ice_cream_item.name
                    response = f"✅ *{quantity_text} agregado al carrito*\n\n"
                else:
                    response = f"✅ *Extras agregados al carrito:*\n"
                    for extra in added_extras:
                        response += f"  • {extra}\n"
                    response += "\n"
                
                response += f"{self.cart_manager.format_cart_message(cart)}\n\n"
                response += "📋 *¿Qué deseas hacer?*\n\n"
                response += "• Escribe 1-17 para agregar más extras\n"
                response += "• 1️⃣8️⃣ Ver menú de extras completo\n"
                response += "• 1️⃣9️⃣ Menu principal\n"
                response += "• 2️⃣0️⃣ Proceder con el pago\n\n"
                response += "¿Qué opción eliges, grumete?"
                
                # Keep user in extras mode
                conversation["metadata"]["awaiting_extra_selection"] = True
                
                return response
            else:
                quantity_text = f"los {quantity} helados" if quantity > 1 else "el helado"
                return f"""Por favor elige una opción válida para {quantity_text}:

1️⃣ Cookies & Cream 🍪
2️⃣ Frambuesa a la Crema con Chocolate Belga 🍫

Escribe el número que prefieras 🚤"""
            
        except Exception as e:
            logger.error(f"Error handling ice cream flavor response: {e}")
            conversation["metadata"]["awaiting_ice_cream_flavor"] = False
            conversation["metadata"]["pending_ice_cream_quantity"] = None
            conversation["metadata"]["pending_extras"] = []
            return "Hubo un error agregando el helado. Por favor, intenta de nuevo."
    
    async def _handle_extra_number_selection(self, message: str, phone_number: str, contact_name: str, conversation: dict) -> Optional[str]:
        """Handle user's selection of an extra by number (supports multiple numbers like '5 y 7')"""
        try:
            import re
            message_clean = message.strip()
            message_lower = message_clean.lower()
            language = conversation.get("metadata", {}).get("language", "es")

            # Normalize special emoji-based numbers like 1️⃣8️⃣, 1️⃣9️⃣, 2️⃣0️⃣
            emoji_number_map = {
                "1️⃣8️⃣": "18",
                "1️⃣9️⃣": "19",
                "2️⃣0️⃣": "20",
                "1️⃣": "1",
                "2️⃣": "2",
                "3️⃣": "3",
                "4️⃣": "4",
                "5️⃣": "5",
                "6️⃣": "6",
                "7️⃣": "7",
                "8️⃣": "8",
                "9️⃣": "9",
                "0️⃣": "0",
            }
            if message_clean in emoji_number_map:
                message_clean = emoji_number_map[message_clean]
                message_lower = message_clean
            
            # Check if message contains item descriptions (like "jugo", "helado", "tabla", etc.)
            # If it does, this is NOT a pure ID selection, it's a quantity + description
            item_keywords = [
                'jugo', 'bebida', 'agua', 'lata', 'helado', 'cookies', 'frambuesa',
                'tabla', 'picoteo', 'modo', 'romantico', 'pétalos', 'petalos', 'rosa',
                'vela', 'letra', 'pack', 'video', 'transporte', 'toalla', 'chalas', 'flex'
            ]
            
            # Remove common connectors and numbers to check for item keywords
            words_only = re.sub(r'\b\d+\b', '', message_lower)  # Remove numbers
            words_only = re.sub(r'[,y]', ' ', words_only).strip()  # Remove connectors
            
            # If there are meaningful words left (item descriptions), don't treat as pure IDs
            if any(keyword in words_only for keyword in item_keywords):
                logger.info(f"Message contains item descriptions, not treating as pure IDs: {message_clean}")
                return None  # Let other handlers (like AI or text parser) handle it
            
            # Extract all numbers from the message (support formats like "5 y 7", "5, 7", "5 7", etc.)
            numbers = re.findall(r'\b(\d+)\b', message_clean)

            # If we couldn't extract numbers but the clean message is a known shortcut
            if not numbers and message_clean in ["18", "19", "20"]:
                numbers = [message_clean]
            
            # Check for special commands first (18, 19, 20)
            if "18" in numbers:
                # Ver extras - mostrar menú de nuevo
                logger.info("User selected option 18: Ver extras")
                # Don't clear awaiting_extra_selection, keep them in extras mode
                return self.faq_handler.get_response("extras", language)
            
            if "19" in numbers:
                # Menu principal
                logger.info("User selected option 19: Menu principal")
                conversation["metadata"]["awaiting_extra_selection"] = False
                language = conversation.get("metadata", {}).get("language", "es")
                return self._get_main_menu_message(language)
            
            if "20" in numbers:
                # Proceder con el pago
                logger.info("User selected option 20: Proceder con el pago")
                conversation["metadata"]["awaiting_extra_selection"] = False
                cart = await self.cart_manager.get_cart(phone_number)
                if not cart:
                    return "🛒 Tu carrito está vacío. Agrega items antes de confirmar."
                
                # Check if reservation exists
                has_reservation = any(item.item_type == "reservation" for item in cart)
                if not has_reservation:
                    return self._cart_needs_reservation_message(conversation)
                
                total = self.cart_manager.calculate_total(cart)
                reservation = next((item for item in cart if item.item_type == "reservation"), None)
                
                confirm_message = "✅ *Solicitud de Reserva Recibida*\n\n"
                confirm_message += f"📅 *Detalles de tu Solicitud:*\n"
                confirm_message += f"   Fecha: {reservation.metadata.get('date')}\n"
                confirm_message += f"   Horario: {reservation.metadata.get('time')}\n"
                confirm_message += f"   Personas: {reservation.quantity}\n\n"
                
                if len(cart) > 1:
                    confirm_message += f"✨ *Extras solicitados:*\n"
                    for item in cart:
                        if item.item_type == "extra":
                            confirm_message += f"   • {item.name}\n"
                    confirm_message += "\n"
                
                confirm_message += f"💰 *Total estimado: ${total:,}*\n\n"
                confirm_message += f"📞 *El Capitán Tomás se comunicará contigo pronto por WhatsApp o teléfono para confirmar tu reserva y coordinar el pago* 👨‍✈️\n\n"
                confirm_message += f"Por mientras, envíanos tu *email* y *nombre completo* por favor 📝\n\n"
                confirm_message += f"¡Gracias por elegir HotBoat! 🚤🌊"
                
                # Send notification to Capitán Tomás BEFORE clearing cart
                await self._notify_capitan_tomas(contact_name, phone_number, cart, reason="reservation")
                
                # Clear cart after confirmation
                await self.cart_manager.clear_cart(phone_number)
                
                return confirm_message
            
            # Filter to only valid extra numbers (1-17)
            valid_numbers = [n for n in numbers if n in EXTRAS_NUMBER_MAP]
            
            if not valid_numbers:
                logger.info(f"No valid extra numbers found in: {message_clean}")
                return None
            
            logger.info(f"User selected extras: {valid_numbers}")

            warning_message = await self._require_reservation_for_extras(phone_number, conversation)
            if warning_message:
                return warning_message
            
            # DON'T clear awaiting_extra_selection here - keep user in extras mode
            # It will be cleared when they explicitly choose to exit (option 19 or 20)
            # or when they choose a cart option
            
            # Check if any of the selections is helado (6) - needs special handling
            if "6" in valid_numbers:
                # If helado is selected (alone or with others), handle it specially
                if len(valid_numbers) == 1:
                    # Only helado selected
                    conversation["metadata"]["awaiting_ice_cream_flavor"] = True
                    conversation["metadata"]["pending_ice_cream_quantity"] = 1
                    return """🍦 *Tenemos 2 sabores de helado:*

1️⃣ Cookies & Cream 🍪
2️⃣ Frambuesa a la Crema con Chocolate Belga 🍫

Precio: $3,500 c/u

¿Cuál sabor prefieres? (escribe el número) 🚤"""
                else:
                    # Helado + other items: we'll need to ask about helado first
                    # Save the other items for later
                    other_numbers = [n for n in valid_numbers if n != "6"]
                    conversation["metadata"]["pending_extras"] = other_numbers
                    conversation["metadata"]["awaiting_ice_cream_flavor"] = True
                    conversation["metadata"]["pending_ice_cream_quantity"] = 1
                    return """🍦 *Has seleccionado helado junto con otros extras.*

Primero, elige el sabor de helado:

1️⃣ Cookies & Cream 🍪
2️⃣ Frambuesa a la Crema con Chocolate Belga 🍫

Precio: $3,500 c/u

¿Cuál sabor prefieres? (escribe el número) 🚤"""
            
            # No helado in selection - add all extras to cart
            added_extras = []
            failed_extras = []
            
            for number in valid_numbers:
                extra_name = EXTRAS_NUMBER_MAP[number]
                logger.info(f"Adding extra #{number}: {extra_name}")
                
                # Try to parse and add the extra to cart
                extra_item = self.cart_manager.parse_extra_from_message(extra_name)
                if extra_item:
                    await self.cart_manager.add_item(phone_number, contact_name, extra_item)
                    added_extras.append(extra_item.name)
                else:
                    logger.error(f"Could not parse extra: {extra_name}")
                    failed_extras.append(extra_name)
            
            # Build response message
            if added_extras:
                cart = await self.cart_manager.get_cart(phone_number)
                if len(added_extras) == 1:
                    response = f"✅ *{added_extras[0]} agregado al carrito*\n\n"
                else:
                    response = f"✅ *Extras agregados al carrito:*\n"
                    for extra in added_extras:
                        response += f"  • {extra}\n"
                    response += "\n"
                
                response += f"{self.cart_manager.format_cart_message(cart)}\n\n"
                response += "📋 *¿Qué deseas hacer?*\n\n"
                response += "• Escribe 1-17 para agregar más extras\n"
                response += "• 1️⃣8️⃣ Ver menú de extras completo\n"
                response += "• 1️⃣9️⃣ Menu principal\n"
                response += "• 2️⃣0️⃣ Proceder con el pago\n\n"
                response += "¿Qué opción eliges, grumete?"
                
                if failed_extras:
                    response += f"\n\n⚠️ No se pudieron agregar: {', '.join(failed_extras)}"
                
                return response
            else:
                return "Lo siento, hubo un error agregando esos extras. ¿Podrías intentar de nuevo?"
            
        except Exception as e:
            logger.error(f"Error handling extra number selection: {e}")
            import traceback
            traceback.print_exc()
            conversation["metadata"]["awaiting_extra_selection"] = False
            return "Hubo un error procesando tu selección. Por favor, intenta de nuevo."
    
    @staticmethod
    def _spans_overlap(span_a: tuple, span_b: tuple) -> bool:
        """Check if two spans (start, end) overlap."""
        return span_a[0] < span_b[1] and span_b[0] < span_a[1]
    
    def _build_extra_pattern(self, keyword: str) -> str:
        """Create a regex pattern for a given extra keyword."""
        escaped = re.escape(keyword).replace(r'\ ', r'\s+')
        # Optional quantity before the keyword, allowing variants like "2x jugos" or "2 por jugos"
        return rf'(?<!\w)(?:(?P<qty>\d+)\s*(?:x|por)?\s*)?(?:de\s+)?{escaped}(?!\w)'
    
    def _extract_extras_from_message(self, message: str):
        """
        Extract extras from a free-form message.
        Returns a list of dicts with keys: key (catalog synonym), quantity, order.
        """
        normalized = self._convert_written_numbers_to_digits(message)
        text = normalized.lower()
        text = text.replace('\n', ' ')
        text = re.sub(r'[.,;]', ' ', text)
        
        matches = []
        used_spans = []
        
        for keyword in self.extra_keywords:
            pattern = self._build_extra_pattern(keyword)
            for match in re.finditer(pattern, text):
                span = match.span()
                if any(self._spans_overlap(span, used) for used in used_spans):
                    continue
                
                qty_str = match.groupdict().get("qty")
                quantity = int(qty_str) if qty_str else 1
                
                matches.append({
                    "key": keyword,
                    "quantity": quantity,
                    "order": span[0]
                })
                used_spans.append(span)
        
        matches.sort(key=lambda item: item["order"])
        return matches
    
    async def _try_parse_multiple_extras(self, message: str, phone_number: str, contact_name: str, conversation: dict) -> Optional[str]:
        """Parse messages that list several extras (e.g., '1 jugo y 2 helados')."""
        try:
            extracted_extras = self._extract_extras_from_message(message)
            if not extracted_extras:
                return None
            
            warning_message = await self._require_reservation_for_extras(phone_number, conversation)
            if warning_message:
                return warning_message
            
            added_items = []
            needs_ice_cream_flavor = False
            ice_cream_quantity = 0
            
            for extra_info in extracted_extras:
                keyword = extra_info["key"]
                quantity = max(1, extra_info["quantity"])
                
                extra_item = self.cart_manager.parse_extra_from_message(keyword)
                if not extra_item:
                    continue
                
                # Generic ice cream requires flavor selection later
                if "helado individual" in extra_item.name.lower() and "(" not in extra_item.name.lower():
                    needs_ice_cream_flavor = True
                    ice_cream_quantity += quantity
                    continue
                
                extra_item.quantity = quantity
                await self.cart_manager.add_item(phone_number, contact_name, extra_item)
                if quantity > 1:
                    added_items.append(f"{quantity}x {extra_item.name}")
                else:
                    added_items.append(extra_item.name)
            
            if needs_ice_cream_flavor:
                if not conversation.get("metadata"):
                    conversation["metadata"] = {}
                conversation["metadata"]["awaiting_ice_cream_flavor"] = True
                conversation["metadata"]["pending_ice_cream_quantity"] = ice_cream_quantity or 1
                
                quantity_text = (
                    f"los {ice_cream_quantity} helados" if ice_cream_quantity > 1 else "el helado"
                )
                
                intro = ""
                if added_items:
                    intro = "✅ *Extras agregados al carrito:*\n"
                    intro += "\n".join(f"• {item}" for item in added_items) + "\n\n"
                
                return f"""{intro}🍦 *Tenemos 2 sabores de helado:*

1️⃣ Cookies & Cream 🍪
2️⃣ Frambuesa a la Crema con Chocolate Belga 🍫

Precio: $3,500 c/u

¿Cuál sabor prefieres para {quantity_text}? (escribe el número) 🚤"""
            
            if added_items:
                cart = await self.cart_manager.get_cart(phone_number)
                items_text = "\n".join([f"• {item}" for item in added_items])
                return (
                    "✅ *Items agregados al carrito:*\n\n"
                    f"{items_text}\n\n{self.cart_manager.format_cart_message(cart)}\n\n"
                    "📋 *¿Qué deseas hacer?*\n\n"
                    "• Escribe 1-17 para agregar más extras\n"
                    "• 1️⃣8️⃣ Ver menú de extras completo\n"
                    "• 1️⃣9️⃣ Menú principal\n"
                    "• 2️⃣0️⃣ Proceder con el pago\n"
                    "• Escribe *vaciar* para vaciar el carrito\n\n"
                    "¿Qué opción eliges, grumete?"
                )
            
            return None
        except Exception as e:
            logger.error(f"Error parsing multiple extras: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def _try_parse_extra_with_ai(self, message: str, phone_number: str, contact_name: str, conversation: dict = None) -> Optional[str]:
        """
        Deterministically parse a single extra from free text (e.g., '2 jugos', 'una tabla grande').
        Kept same method name for compatibility with existing calls.
        """
        if conversation is None:
            conversation = {"metadata": {}}
        
        try:
            extracted_extras = self._extract_extras_from_message(message)
            if not extracted_extras:
                return None
            
            warning_message = await self._require_reservation_for_extras(phone_number, conversation)
            if warning_message:
                return warning_message
            
            # If multiple extras detected, delegate to multi-extra handler
            if len(extracted_extras) > 1:
                return await self._try_parse_multiple_extras(message, phone_number, contact_name, conversation)
            
            extra_info = extracted_extras[0]
            keyword = extra_info["key"]
            quantity = max(1, extra_info["quantity"])
            
            extra_item = self.cart_manager.parse_extra_from_message(keyword)
            if not extra_item:
                return None
            
            # Handle generic ice cream (ask for flavor)
            if "helado individual" in extra_item.name.lower() and "(" not in extra_item.name.lower():
                if not conversation.get("metadata"):
                    conversation["metadata"] = {}
                conversation["metadata"]["awaiting_ice_cream_flavor"] = True
                conversation["metadata"]["pending_ice_cream_quantity"] = quantity
                
                quantity_text = f"los {quantity} helados" if quantity > 1 else "el helado"
                return f"""🍦 *Tenemos 2 sabores de helado:*

1️⃣ Cookies & Cream 🍪
2️⃣ Frambuesa a la Crema con Chocolate Belga 🍫

Precio: $3,500 c/u

¿Cuál sabor prefieres para {quantity_text}? (escribe el número) 🚤"""
            
            extra_item.quantity = quantity
            await self.cart_manager.add_item(phone_number, contact_name, extra_item)
            cart = await self.cart_manager.get_cart(phone_number)
            
            if conversation:
                conversation["metadata"]["awaiting_extra_selection"] = True
            
            response = f"✅ *{extra_item.name}"
            if quantity > 1:
                response += f" x{quantity}"
            response += f" agregado al carrito*\n\n{self.cart_manager.format_cart_message(cart)}\n\n"
            response += "📋 *¿Qué deseas hacer?*\n\n"
            response += "• Escribe 1-17 para agregar más extras\n"
            response += "• 1️⃣8️⃣ Ver menú de extras completo\n"
            response += "• 1️⃣9️⃣ Menu principal\n"
            response += "• 2️⃣0️⃣ Proceder con el pago\n\n"
            response += "¿Qué opción eliges, grumete?"
            return response
        except Exception as e:
            logger.error(f"Error parsing extra from text: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _is_reservation_confirm(self, message: str) -> bool:
        """Check if message is confirming a reservation"""
        keywords = ["reservar", "reserva", "quiero ese", "confirmo", "ese horario", "ese día"]
        return any(keyword in message for keyword in keywords)
    
    def _convert_written_numbers_to_digits(self, message: str) -> str:
        """
        Convert written numbers to digits in Spanish
        Example: "dos personas" -> "2 personas"
        """
        number_words = {
            'dos': '2',
            'tres': '3',
            'cuatro': '4',
            'cinco': '5',
            'seis': '6',
            'siete': '7',
            'ocho': '8',
            'nueve': '9',
            'diez': '10',
            'once': '11',
            'doce': '12',
            'trece': '13',
            'catorce': '14',
            'quince': '15',
            'dieciseis': '16',
            'dieciséis': '16',
            'diecisiete': '17',
            'dieciocho': '18',
            'diecinueve': '19',
            'veinte': '20',
            'veintiuno': '21',
            'veintiuna': '21'
        }
        
        message_lower = message.lower()
        result = message
        
        # Replace written numbers with digits
        for word, digit in number_words.items():
            # Use word boundaries to avoid replacing parts of other words
            import re
            pattern = r'\b' + word + r'\b'
            result = re.sub(pattern, digit, result, flags=re.IGNORECASE)
        
        return result
    
    async def _try_parse_reservation_from_message(self, message: str, phone_number: str, conversation: dict = None):
        """Try to parse reservation from message (date, time, capacity)"""
        try:
            # First, convert written numbers to digits
            message = self._convert_written_numbers_to_digits(message)
            
            message_lower = message.lower().strip()
            logger.info(f"Trying to parse reservation from: '{message_lower}'")
            
            # Quick exit for simple messages
            if len(message_lower) < 10 or message_lower in ['hola', 'si', 'no', 'gracias', 'ok', 'okay']:
                logger.debug(f"Message too short or simple, skipping: '{message_lower}'")
                return None
            
            # Check if this looks like a reservation intent
            # Look for patterns: "a las [hora] para [X] personas", "[día] a las [hora]", etc.
            has_person_word = 'persona' in message_lower or 'personas' in message_lower
            has_reservation_pattern = any([
                'a las' in message_lower and has_person_word,
                'para' in message_lower and has_person_word and any(c.isdigit() for c in message_lower),
                any(day in message_lower for day in ['lunes', 'martes', 'miércoles', 'miercoles', 'jueves', 'viernes', 'sábado', 'sabado', 'domingo']) and 'a las' in message_lower
            ])
            
            if not has_reservation_pattern:
                logger.debug(f"No reservation pattern detected in: '{message_lower}'")
                return None
            
            logger.info(f"Reservation pattern detected in: '{message_lower}'")
        except Exception as e:
            logger.warning(f"Error in reservation pattern check: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        try:
            # Patterns to detect reservation intent
            reservation_patterns = [
                # ORDEN: día + para + personas + a las + hora
                r'\bel\s+(\w+)\s+para\s+(\d+)\s+personas?\s+a\s+las\s+(\d{1,2}):?(\d{0,2})\b',  # "el martes para 3 personas a las 18:00"
                r'\b(\w+)\s+para\s+(\d+)\s+personas?\s+a\s+las\s+(\d{1,2}):?(\d{0,2})\b',  # "martes para 3 personas a las 18:00"
                r'\b(\w+)\s+para\s+(\d+)\s+personas?\s+a\s+las\s+(\d{1,2})\b',  # "martes para 3 personas a las 18"
                # ORDEN: día + número + a las + hora + para + personas
                r'\b(\w+)\s+(\d{1,2})\s+a\s+las\s+(\d{1,2})\s+para\s+(\d+)\s+personas?\b',  # "miércoles 5 a las 21 para 2 personas"
                # ORDEN: día + a las + hora + para + personas
                r'\bel\s+(\w+)\s+a\s+las\s+(\d{1,2}):?(\d{0,2})\s+para\s+(\d+)\s+personas?\b',  # "el martes a las 16:00 para 3 personas"
                r'\bel\s+(\w+)\s+a\s+las\s+(\d{1,2})\s+para\s+(\d+)\s+personas?\b',  # "el martes a las 16 para 3 personas"
                r'\b(\w+)\s+a\s+las\s+(\d{1,2}):?(\d{0,2})\s+para\s+(\d+)\s+personas?\b',  # "martes a las 16:00 para 3 personas"
                r'\b(\w+)\s+a\s+las\s+(\d{1,2})\s+para\s+(\d+)\s+personas?\b',  # "martes a las 16 para 3 personas"
                # ORDEN: día + hora:minutos + personas
                r'\b(\w+)\s+(\d{1,2}):(\d{2})\s+(\d+)\s+personas?\b',  # "martes 16:00 3 personas"
                # ORDEN: día del mes + de + mes + a las + hora + para + personas
                r'\b(\d{1,2})\s+de\s+(\w+)\s+a\s+las\s+(\d{1,2}):?(\d{0,2})\s+para\s+(\d+)\s+personas?\b',  # "4 de noviembre a las 16:00 para 3 personas"
                r'\b(\d{1,2})\s+de\s+(\w+)\s+a\s+las\s+(\d{1,2})\s+para\s+(\d+)\s+personas?\b',  # "4 de noviembre a las 16 para 3 personas"
                # ORDEN: a las + hora + para + personas (sin día específico)
                r'\ba\s+las\s+(\d{1,2}):?(\d{0,2})\s+para\s+(\d+)\s+personas?\b',  # "a las 16:00 para 3 personas"
                r'\ba\s+las\s+(\d{1,2})\s+para\s+(\d+)\s+personas?\b',  # "a las 16 para 3 personas"
            ]
            
            import re
            from datetime import datetime, timedelta
            import pytz
            
            CHILE_TZ = pytz.timezone('America/Santiago')
            now = datetime.now(CHILE_TZ)
            
            # Spanish day names mapping to day of week
            spanish_days = {
                'lunes': 0, 'martes': 1, 'miercoles': 2, 'miércoles': 2,
                'jueves': 3, 'viernes': 4, 'sabado': 5, 'sábado': 5,
                'domingo': 6
            }
            
            # Try each pattern
            for i, pattern in enumerate(reservation_patterns):
                match = re.search(pattern, message_lower)
                if match:
                    logger.info(f"Pattern {i} matched: {pattern}")
                    groups = match.groups()
                    logger.info(f"Groups: {groups}")
                    
                    # Extract capacity (always the last number)
                    capacity = None
                    for group in reversed(groups):
                        if group.isdigit() and int(group) >= 2 and int(group) <= 7:
                            capacity = int(group)
                            break
                    
                    if not capacity:
                        continue
                    
                    # Extract time (usually a number between 9-21)
                    # Also handle 24-hour format (16 = 4pm = 15:00 in our system)
                    time_hour = None
                    for group in groups:
                        if group.isdigit():
                            hour = int(group)
                            # Handle 24-hour format: 16 = 15:00, 18 = 18:00, etc.
                            if 9 <= hour <= 21:
                                # Convert to our operating hours format (9, 12, 15, 18, 21)
                                if hour == 16:
                                    time_hour = 15  # 16:00 = 15:00 (3pm slot)
                                elif hour == 10:
                                    time_hour = 9   # 10:00 = 09:00 (9am slot)
                                elif hour in [9, 12, 15, 18, 21]:
                                    time_hour = hour
                                else:
                                    # Round to nearest available slot
                                    available_slots = [9, 12, 15, 18, 21]
                                    time_hour = min(available_slots, key=lambda x: abs(x - hour))
                                break
                    
                    if not time_hour:
                        continue
                    
                    # Extract date
                    date_str = None
                    day_name = None
                    day_number = None
                    month_name = None
                    
                    # Check if it's a day name (lunes, martes, etc.)
                    for group in groups:
                        if group.lower() in spanish_days:
                            day_name = group.lower()
                            break
                    
                    # Check if it's "4 de noviembre" format
                    if len(groups) >= 4:
                        # Pattern: "4 de noviembre a las 16 para 3 personas"
                        if groups[0].isdigit() and groups[1] == 'de':
                            day_number = int(groups[0])
                            month_name = groups[2].lower()
                    
                    # Try to resolve the date
                    target_date = None
                    
                    if day_name:
                        # User said "martes" - find next Tuesday
                        target_dow = spanish_days[day_name]
                        current_dow = now.weekday()
                        days_ahead = target_dow - current_dow
                        if days_ahead <= 0:  # Target day already happened this week
                            days_ahead += 7
                        target_date = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
                        # Format date in Spanish
                        spanish_months = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                                         'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
                        date_str = f"{target_date.day} de {spanish_months[target_date.month - 1]} {target_date.year}"
                    
                    elif day_number and month_name:
                        # User said "4 de noviembre"
                        month_num = SPANISH_MONTHS.get(month_name)
                        if month_num:
                            year = now.year
                            try:
                                target_date = datetime(year, month_num, day_number, 0, 0, 0)
                                target_date = CHILE_TZ.localize(target_date)
                                if target_date < now:
                                    target_date = datetime(year + 1, month_num, day_number, 0, 0, 0)
                                    target_date = CHILE_TZ.localize(target_date)
                                # Format date in Spanish
                                spanish_months = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                                                 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
                                date_str = f"{target_date.day} de {spanish_months[target_date.month - 1]} {target_date.year}"
                            except ValueError:
                                continue
                    
                    if target_date and time_hour:
                        # Format time as HH:00
                        time_str = f"{time_hour:02d}:00"
                        
                        # Create full datetime for validation
                        reservation_datetime = target_date.replace(hour=time_hour, minute=0, second=0, microsecond=0)
                        
                        # Validate minimum 4 hours advance booking
                        hours_ahead = (reservation_datetime - now).total_seconds() / 3600
                        if hours_ahead < 4:
                            logger.info(f"Reservation too soon: {hours_ahead:.1f} hours ahead (minimum 4 hours required)")
                            # Return None to reject this reservation - will be caught and user notified
                            continue
                        
                        logger.info(f"Parsed reservation: date={date_str}, time={time_str}, capacity={capacity}, hours_ahead={hours_ahead:.1f}")
                        
                        # Verify the slot is available (optional check)
                        # For now, we'll trust the user and add it
                        
                        # Create reservation item
                        reservation_item = self.cart_manager.create_reservation_item(
                            date=date_str,
                            time=time_str,
                            capacity=capacity
                        )
                        
                        logger.info(f"Created reservation item: {reservation_item}")
                        return reservation_item
                    else:
                        logger.warning(f"Could not parse date or time: target_date={target_date}, time_hour={time_hour}")
            
            logger.info("No pattern matched or could not extract reservation details")
            return None
        except Exception as e:
            logger.warning(f"Error parsing reservation from message: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _should_interpret_as_menu(self, message_text: str, conversation: dict) -> bool:
        """
        Determine if a number (1-6) should be interpreted as a menu option.
        Returns True only if we're in a menu context, not in the middle of another conversation flow.
        
        Args:
            message_text: The user's message
            conversation: The conversation context
            
        Returns:
            bool: True if the number should be treated as a menu option
        """
        # If the message contains more than just a number, it's not a menu selection
        # e.g., "2 personas", "somos 3", etc.
        message_lower = message_text.lower().strip()
        
        # If message has words in addition to the number, check if they're menu-related
        words = message_lower.split()
        if len(words) > 1:
            # Check if it's just emoji numbers like "2️⃣"
            if message_text.strip() not in ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"]:
                # Allow multiple numbers (e.g., "1 2 3") - check if all words are numbers or separators
                import re
                # Remove numbers, spaces, commas, and connectors
                cleaned = re.sub(r'[1-6\s,yande]+', '', message_lower)
                # If there's minimal extra text, it's likely multiple menu numbers
                if len(cleaned) <= 2:
                    logger.info(f"Message appears to be multiple menu numbers: {message_text}")
                    # Don't return False here - let it continue to check context
                else:
                    logger.info(f"Message has multiple words, not treating as menu: {message_text}")
                    return False
        
        # If message contains words like "personas", "persona", "somos", "seremos", etc.
        # it's definitely NOT a menu selection
        person_keywords = ["persona", "personas", "somos", "seremos", "serían", "seríamos", "gente", "adultos", "niños"]
        if any(keyword in message_lower for keyword in person_keywords):
            logger.info(f"Message contains person-related keywords, not treating as menu: {message_text}")
            return False
        
        # Check conversation history length
        history = conversation.get("messages", [])
        
        # If it's the first few messages (within first 3 user messages), likely a menu selection
        user_messages = [m for m in history if m.get("sender") == "user"]
        if len(user_messages) <= 3:
            logger.info(f"Early in conversation ({len(user_messages)} user messages), treating as menu")
            return True
        
        # Check if the last bot message contained the menu
        # (user might be responding to the menu after seeing it again)
        if history:
            last_bot_message = None
            for msg in reversed(history):
                if msg.get("sender") == "bot":
                    last_bot_message = msg.get("message", "")
                    break
            
            if last_bot_message:
                # Check if menu options were shown in last bot message
                menu_indicators = [
                    "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣",
                    "qué número eliges",
                    "elige un número",
                    "número del 1 al 6",
                    "puedes preguntarme por"
                ]
                
                if any(indicator in last_bot_message.lower() for indicator in menu_indicators):
                    logger.info("Last bot message contained menu, treating number as menu option")
                    return True
        
        # Check if user recently asked for "menu"
        recent_messages = history[-5:] if len(history) >= 5 else history
        for msg in recent_messages:
            if msg.get("sender") == "user":
                msg_text = msg.get("message", "").lower()
                if "menu" in msg_text or "menú" in msg_text or "opciones" in msg_text:
                    logger.info("User recently asked for menu, treating as menu option")
                    return True
        
        # Default: if we're deep in conversation and no menu context, DON'T treat as menu
        logger.info(f"No menu context found, NOT treating as menu option (conversation has {len(user_messages)} user messages)")
        return False








