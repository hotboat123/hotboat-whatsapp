"""
Conversation manager - handles message flow and context
"""
import logging
import re
from typing import Dict, Optional, Union
from datetime import datetime

from app.bot.ai_handler import AIHandler
from app.bot.availability import AvailabilityChecker, SPANISH_MONTHS
from app.bot.faq import FAQHandler
from app.bot.accommodations import accommodations_handler
from app.bot.cart import CartManager
from app.db.leads import get_or_create_lead, get_conversation_history

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversations with users"""
    
    def __init__(self):
        self.ai_handler = AIHandler()
        self.availability_checker = AvailabilityChecker()
        self.faq_handler = FAQHandler()
        self.cart_manager = CartManager()
        # In-memory conversation storage (use Redis or DB in production)
        self.conversations: Dict[str, dict] = {}
    
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
            
            logger.info(f"Processing message from {contact_name}: {message_text}")
            
            # Check if it's the first message - send welcome message
            # Check BEFORE adding the message to history
            is_first = self._is_first_message(conversation)
            is_greeting = self._is_greeting_message(message_text)
            
            # Add message to history
            conversation["messages"].append({
                "role": "user",
                "content": message_text,
                "timestamp": datetime.now().isoformat(),
                "message_id": message_id
            })
            
            # Always show welcome message on first interaction, regardless of greeting
            if is_first:
                logger.info("First message with greeting - sending welcome message")
                response = """🥬 ¡Ahoy, grumete! ⚓  

Soy *Popeye el Marino*, cabo segundo del *HotBoat Chile* 🚤  

Estoy al mando para ayudarte con todas tus consultas sobre nuestras experiencias flotantes 🌊  

Puedes preguntarme por:  

1️⃣ *Disponibilidad y horarios*  

2️⃣ *Precios por persona*  

3️⃣ *Características del HotBoat*  

4️⃣ *Extras y promociones*  

5️⃣ *Ubicación y reseñas*  

Si prefieres hablar con el *Capitán Tomás*, escribe *Llamar a Tomás*, *Ayuda*, o simplemente *6️⃣* 👨‍✈️🌿  

¿Listo para zarpar o qué número eliges, grumete?"""
            # PRIORITY 1: Check if user is responding with number of people (after selecting date/time)
            # This MUST come before menu options to avoid confusion when user types a number
            elif conversation.get("metadata", {}).get("awaiting_party_size"):
                logger.info("User responding with party size")
                response = await self._handle_party_size_response(message_text, from_number, contact_name, conversation)
            # PRIORITY 2: Check if it's a cart option (1-3) when cart has items
            elif await self._is_cart_option_selection(message_text, from_number):
                logger.info(f"Cart option selected: {message_text}")
                response = await self._handle_cart_option_selection(message_text, from_number, contact_name)
            # Check if it's a menu number selection (1-6)
            elif menu_number := self.faq_handler.is_menu_number(message_text):
                logger.info(f"Menu number selected: {menu_number}")
                if menu_number == 1:
                    # Option 1: Disponibilidad y horarios
                    response = await self.availability_checker.check_availability("disponibilidad")
                elif menu_number == 2:
                    # Option 2: Precios por persona
                    response = self.faq_handler.get_response("precio")
                elif menu_number == 3:
                    # Option 3: Características del HotBoat
                    response = self.faq_handler.get_response("caracteristicas")
                elif menu_number == 4:
                    # Option 4: Extras y promociones
                    response = self.faq_handler.get_response("extras")
                elif menu_number == 5:
                    # Option 5: Ubicación y reseñas
                    response = self.faq_handler.get_response("ubicación")
                elif menu_number == 6:
                    # Option 6: Llamar a Tomás
                    response = self.faq_handler.get_response("llamar a tomas")
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
            # Check cart commands (before FAQ)
            elif cart_response := await self._handle_cart_command(message_text, from_number, contact_name):
                logger.info("Cart command processed")
                response = cart_response
            # Check if it's a FAQ question
            elif self.faq_handler.get_response(message_text):
                logger.info("Responding with FAQ answer")
                response = self.faq_handler.get_response(message_text)
            
            # Check if asking about availability
            elif self.is_availability_query(message_text):
                logger.info("Checking availability")
                response = await self.availability_checker.check_availability(message_text)
            
            # Check if user is confirming a reservation (after seeing availability from AI)
            elif await self._is_confirming_reservation_from_availability(message_text, conversation):
                logger.info("User confirming reservation from availability check")
                response = await self._handle_reservation_confirmation(message_text, from_number, contact_name, conversation)
            
            # Check if user is selecting a date/time (without specifying party size)
            elif date_time_selection := await self._try_parse_date_time_only(message_text, conversation):
                logger.info(f"User selecting date/time: {date_time_selection}")
                # Store the selection and ask for party size
                conversation["metadata"]["pending_reservation"] = date_time_selection
                conversation["metadata"]["awaiting_party_size"] = True
                response = f"""✅ Perfecto, grumete ⚓

📅 Fecha: {date_time_selection['date']}
🕐 Horario: {date_time_selection['time']}

¿Para cuántas personas? (2-7 personas) 🚤"""
            
            # PRIORITY: Check if user is making a complete reservation (date, time, AND party size)
            # This should happen BEFORE AI handler to catch reservation intents
            elif reservation_item := await self._try_parse_reservation_from_message(message_text, from_number, conversation):
                logger.info("User making a reservation - adding to cart")
                try:
                    await self.cart_manager.add_item(from_number, contact_name, reservation_item)
                    cart = await self.cart_manager.get_cart(from_number)
                    response = f"✅ *Reserva agregada al carrito*\n\n{self.cart_manager.format_cart_message(cart)}\n\n📋 *Elige una opción (escribe el número):*\n\n1️⃣ Agregar un extra\n2️⃣ Proceder con el pago\n3️⃣ Vaciar el carrito\n\n¿Qué opción eliges, grumete?"
                except Exception as cart_error:
                    logger.error(f"Error adding to cart: {cart_error}")
                    import traceback
                    traceback.print_exc()
                    # If cart fails, still acknowledge the reservation
                    response = f"✅ Entendido, quieres reservar para {reservation_item.quantity} personas.\n\nPor favor, confirma los detalles y el Capitán Tomás se comunicará contigo pronto 👨‍✈️"
            
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
            
            # Use AI for general conversation
            else:
                logger.info("Using AI handler for response")
                try:
                    response = await self.ai_handler.generate_response(
                        message_text=message_text,
                        conversation_history=conversation["messages"],
                        contact_name=contact_name
                    )
                except Exception as ai_error:
                    logger.error(f"Error in AI handler: {ai_error}")
                    import traceback
                    traceback.print_exc()
                    # Final fallback
                    response = "🥬 ¡Ahoy, grumete! ⚓ Disculpa, estoy teniendo problemas técnicos. ¿Podrías intentar de nuevo en un momento?"
            
            
            # Add response to history
            conversation["messages"].append({
                "role": "assistant",
                "content": response,
                "timestamp": datetime.now().isoformat()
            })
            
            # Update last interaction
            conversation["last_interaction"] = datetime.now().isoformat()
            
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
            
            self.conversations[phone_number] = {
                "phone": phone_number,
                "name": contact_name,
                "messages": history if history else [],
                "created_at": datetime.now().isoformat(),
                "last_interaction": datetime.now().isoformat(),
                "metadata": {
                    "lead_status": lead.get("lead_status") if lead else "unknown",
                    "lead_id": lead.get("id") if lead else None
                }
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
            # Also return True if message clearly asks about cart/reservation process
            if any(word in message_lower for word in ["carro", "carrito", "reservar", "reserva"]):
                return True
        
        return False
    
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
        message_lower = message.lower().strip()
        
        # View cart
        if any(cmd in message_lower for cmd in ["carrito", "ver carrito", "mi carrito", "qué tengo"]):
            cart = await self.cart_manager.get_cart(phone_number)
            cart_message = self.cart_manager.format_cart_message(cart)
            
            # If cart has items, add options
            if cart:
                cart_message += "\n\n📋 *Elige una opción (escribe el número):*\n\n1️⃣ Agregar un extra\n2️⃣ Proceder con el pago\n3️⃣ Vaciar el carrito\n\n¿Qué opción eliges, grumete?"
            
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
        
        # Add extra
        if any(cmd in message_lower for cmd in ["agregar", "quiero", "necesito", "dame", "pon", "agrega"]):
            # Check if there's actually an extra keyword in the message
            has_extra_context = any(word in message_lower for word in ["tabla", "jugo", "bebida", "agua", "helado", "modo", "romantico", "romántico", "velas", "letras", "pack", "video", "transporte", "toalla", "chalas", "flex"])
            
            if has_extra_context:
                extra_item = self.cart_manager.parse_extra_from_message(message)
                if extra_item:
                    await self.cart_manager.add_item(phone_number, contact_name, extra_item)
                    cart = await self.cart_manager.get_cart(phone_number)
                    return f"✅ *{extra_item.name} agregado al carrito*\n\n{self.cart_manager.format_cart_message(cart)}\n\n📋 *Elige una opción (escribe el número):*\n\n1️⃣ Agregar otro extra\n2️⃣ Proceder con el pago\n3️⃣ Vaciar el carrito\n\n¿Qué opción eliges, grumete?"
                else:
                    # User tried to add something but we didn't recognize it
                    return """❌ *No reconocí ese extra*, grumete ⚓

¿Qué te gustaría hacer?

1️⃣ Ver todos los extras disponibles
2️⃣ Proceder con el pago (sin agregar más)
3️⃣ Vaciar el carrito

Escribe el número que prefieras 🚤"""
        
        # Confirm cart
        if any(cmd in message_lower for cmd in ["confirmar", "confirmo", "pagar", "comprar", "finalizar"]):
            cart = await self.cart_manager.get_cart(phone_number)
            if not cart:
                return "🛒 Tu carrito está vacío. Agrega items antes de confirmar."
            
            # Check if reservation exists
            has_reservation = any(item.item_type == "reservation" for item in cart)
            if not has_reservation:
                return "📅 Necesitas agregar una reserva primero. Consulta disponibilidad y luego agrega la fecha y horario que prefieras."
            
            total = self.cart_manager.calculate_total(cart)
            reservation = next((item for item in cart if item.item_type == "reservation"), None)
            
            confirm_message = "✅ *Reserva Confirmada*\n\n"
            confirm_message += f"📅 *Detalles de la Reserva:*\n"
            confirm_message += f"   Fecha: {reservation.metadata.get('date')}\n"
            confirm_message += f"   Horario: {reservation.metadata.get('time')}\n"
            confirm_message += f"   Personas: {reservation.quantity}\n\n"
            
            if len(cart) > 1:
                confirm_message += f"✨ *Extras incluidos:*\n"
                for item in cart:
                    if item.item_type == "extra":
                        confirm_message += f"   • {item.name}\n"
                confirm_message += "\n"
            
            confirm_message += f"💰 *Total a pagar: ${total:,}*\n\n"
            confirm_message += f"📞 El Capitán Tomás se comunicará contigo pronto para finalizar el pago y confirmar todos los detalles 👨‍✈️\n\n"
            confirm_message += f"¡Gracias por elegir HotBoat! 🚤🌊"
            
            # Clear cart after confirmation
            await self.cart_manager.clear_cart(phone_number)
            
            return confirm_message
        
        # Add reservation (if user specifies date and time after checking availability)
        # This will be handled when user confirms a specific slot
        if self._is_reservation_confirm(message_lower):
            # Try to parse reservation from message
            reservation_item = await self._parse_reservation_from_message(message, phone_number)
            if reservation_item:
                await self.cart_manager.add_item(phone_number, contact_name, reservation_item)
                cart = await self.cart_manager.get_cart(phone_number)
                return f"✅ Reserva agregada al carrito\n\n{self.cart_manager.format_cart_message(cart)}"
        
        return None
    
    async def _is_cart_option_selection(self, message: str, phone_number: str) -> bool:
        """
        Check if user is selecting a cart option (1, 2, or 3)
        Only returns True if the cart is not empty
        """
        message_stripped = message.strip()
        if message_stripped in ['1', '2', '3']:
            cart = await self.cart_manager.get_cart(phone_number)
            return len(cart) > 0
        return False
    
    async def _handle_cart_option_selection(self, message: str, phone_number: str, contact_name: str) -> str:
        """
        Handle cart option selection (1, 2, or 3)
        
        Args:
            message: User's message (should be '1', '2', or '3')
            phone_number: User's phone number
            contact_name: User's name
        
        Returns:
            Response message
        """
        option = message.strip()
        cart = await self.cart_manager.get_cart(phone_number)
        
        if option == '1':
            # Option 1: Agregar un extra - usar EXACTAMENTE los mismos del menú 4
            return """✨ *Servicios Extra:*

¿Quieres agregar algo especial a tu HotBoat?

🍇 *Tablas de Picoteo*
$25.000 → Tabla grande (4 personas): jamón serrano, queso crema con mermelada de pimentón, y más
$20.000 → Tabla pequeña (2 personas): queso crema con mermelada de pimentón, jamón serrano y más

🥤 *Bebidas y Jugos* (sin alcohol)
$10.000 → Jugo natural 1L (piña o naranja)
$2.900 → Lata bebida (Coca-Cola o Fanta)
$2.500 → Agua mineral 1,5 L
🍦 $3.500 → Helado individual (Cookies & Cream 🍪 o Frambuesa a la Crema con Chocolate Belga 🍫)

🌹 *Modo Romántico*
$25.000 → pétalos de rosas y decoración especial 💕

🌙 *Decoración Nocturna Extra*
$10.000 → Velas LED decorativas 💡
$15.000 → Letras luminosas "Te Amo" / "Love" ❤️
$20.000 → Pack completo (velas + letras iluminadas) 💍

✨🎥 *Video personalizado*
15 s → $30.000 / 60 s → $40.000

🚐 *Transporte* ida y vuelta
$50.000 desde Pucón

🧻 *Toallas*
Toalla normal $9.000
Toalla poncho $10.000

🩴 *Chalas de ducha*
$10.000

🔒 *Reserva FLEX +10%* → cancela/reprograma cuando quieras

Para agregar, escribe lo que quieres. Por ejemplo:
• "Quiero la tabla grande"
• "Agregar modo romántico"
• "Dame el pack completo"

¿Qué extra te gustaría agregar? 🚤"""
        
        elif option == '2':
            # Option 2: Proceder con el pago
            if not cart:
                return "🛒 Tu carrito está vacío. Agrega items antes de confirmar."
            
            # Check if reservation exists
            has_reservation = any(item.item_type == "reservation" for item in cart)
            if not has_reservation:
                return "📅 Necesitas agregar una reserva primero. Consulta disponibilidad y luego agrega la fecha y horario que prefieras."
            
            total = self.cart_manager.calculate_total(cart)
            reservation = next((item for item in cart if item.item_type == "reservation"), None)
            
            confirm_message = "✅ *Reserva Confirmada*\n\n"
            confirm_message += f"📅 *Detalles de la Reserva:*\n"
            confirm_message += f"   Fecha: {reservation.metadata.get('date')}\n"
            confirm_message += f"   Horario: {reservation.metadata.get('time')}\n"
            confirm_message += f"   Personas: {reservation.quantity}\n\n"
            
            if len(cart) > 1:
                confirm_message += f"✨ *Extras incluidos:*\n"
                for item in cart:
                    if item.item_type == "extra":
                        confirm_message += f"   • {item.name}\n"
                confirm_message += "\n"
            
            confirm_message += f"💰 *Total a pagar: ${total:,}*\n\n"
            confirm_message += f"📞 El Capitán Tomás se comunicará contigo pronto para finalizar el pago y confirmar todos los detalles 👨‍✈️\n\n"
            confirm_message += f"¡Gracias por elegir HotBoat! 🚤🌊"
            
            # Clear cart after confirmation
            await self.cart_manager.clear_cart(phone_number)
            
            return confirm_message
        
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
        
        return "No entendí esa opción. Por favor elige 1, 2 o 3."
    
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
            
            # Create reservation item
            reservation_item = self.cart_manager.create_reservation_item(
                date=date,
                time=time,
                capacity=party_size
            )
            
            # Add to cart
            await self.cart_manager.add_item(phone_number, contact_name, reservation_item)
            cart = await self.cart_manager.get_cart(phone_number)
            
            return f"✅ *Reserva agregada al carrito*\n\n{self.cart_manager.format_cart_message(cart)}\n\n📋 *Elige una opción (escribe el número):*\n\n1️⃣ Agregar un extra\n2️⃣ Proceder con el pago\n3️⃣ Vaciar el carrito\n\n¿Qué opción eliges, grumete?"
            
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
            message_lower = message.lower().strip()
            
            # Skip if message includes party size
            if 'persona' in message_lower or any(str(i) in message_lower and ('para' in message_lower or 'somos' in message_lower) for i in range(2, 8)):
                return None
            
            # Check if message contains date/time pattern
            if not ('a las' in message_lower or any(day in message_lower for day in ['lunes', 'martes', 'miércoles', 'miercoles', 'jueves', 'viernes', 'sábado', 'sabado', 'domingo']) or any(month in message_lower for month in ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre'])):
                return None
            
            import re
            from datetime import datetime, timedelta
            import pytz
            
            CHILE_TZ = pytz.timezone('America/Santiago')
            now = datetime.now(CHILE_TZ)
            
            spanish_days = {
                'lunes': 0, 'martes': 1, 'miercoles': 2, 'miércoles': 2,
                'jueves': 3, 'viernes': 4, 'sabado': 5, 'sábado': 5,
                'domingo': 6
            }
            
            # Patterns for date/time without party size
            patterns = [
                r'\b(el\s+)?(\w+)\s+a\s+las\s+(\d{1,2}):?(\d{0,2})\b',  # "el sábado a las 9:00" or "sábado a las 9"
                r'\b(\d{1,2})\s+de\s+(\w+)\s+a\s+las\s+(\d{1,2}):?(\d{0,2})\b',  # "8 de noviembre a las 9:00"
            ]
            
            for pattern in patterns:
                match = re.search(pattern, message_lower)
                if match:
                    groups = match.groups()
                    
                    # Extract time
                    time_hour = None
                    for group in groups:
                        if group and group.isdigit():
                            hour = int(group)
                            if 9 <= hour <= 21:
                                # Convert to operating hours (9, 12, 15, 18, 21)
                                if hour == 16:
                                    time_hour = 15
                                elif hour == 10:
                                    time_hour = 9
                                elif hour in [9, 12, 15, 18, 21]:
                                    time_hour = hour
                                else:
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
                    
                    for group in groups:
                        if group and group.lower() in spanish_days:
                            day_name = group.lower()
                        elif group and group.lower() in SPANISH_MONTHS:
                            month_name = group.lower()
                        elif group and group.isdigit() and 1 <= int(group) <= 31:
                            day_number = int(group)
                    
                    # Resolve date
                    target_date = None
                    
                    if day_name:
                        target_dow = spanish_days[day_name]
                        current_dow = now.weekday()
                        days_ahead = target_dow - current_dow
                        if days_ahead <= 0:
                            days_ahead += 7
                        target_date = (now + timedelta(days=days_ahead)).replace(hour=0, minute=0, second=0, microsecond=0)
                        spanish_months = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                                         'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
                        date_str = f"{target_date.day} de {spanish_months[target_date.month - 1]} {target_date.year}"
                    
                    elif day_number and month_name:
                        month_num = SPANISH_MONTHS.get(month_name)
                        if month_num:
                            year = now.year
                            try:
                                target_date = datetime(year, month_num, day_number, 0, 0, 0)
                                target_date = CHILE_TZ.localize(target_date)
                                if target_date < now:
                                    target_date = datetime(year + 1, month_num, day_number, 0, 0, 0)
                                    target_date = CHILE_TZ.localize(target_date)
                                spanish_months = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
                                                 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
                                date_str = f"{target_date.day} de {spanish_months[target_date.month - 1]} {target_date.year}"
                            except ValueError:
                                continue
                    
                    if target_date and time_hour:
                        time_str = f"{time_hour:02d}:00"
                        logger.info(f"Parsed date/time only: date={date_str}, time={time_str}")
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
            
            # Create reservation item
            reservation_item = self.cart_manager.create_reservation_item(
                date=pending['date'],
                time=pending['time'],
                capacity=party_size
            )
            
            # Add to cart
            await self.cart_manager.add_item(phone_number, contact_name, reservation_item)
            cart = await self.cart_manager.get_cart(phone_number)
            
            # Clear the pending state
            conversation["metadata"]["awaiting_party_size"] = False
            conversation["metadata"]["pending_reservation"] = None
            
            return f"✅ *Reserva agregada al carrito*\n\n{self.cart_manager.format_cart_message(cart)}\n\n📋 *Elige una opción (escribe el número):*\n\n1️⃣ Agregar un extra\n2️⃣ Proceder con el pago\n3️⃣ Vaciar el carrito\n\n¿Qué opción eliges, grumete?"
            
        except Exception as e:
            logger.error(f"Error handling party size response: {e}")
            import traceback
            traceback.print_exc()
            # Clear the pending state
            conversation["metadata"]["awaiting_party_size"] = False
            conversation["metadata"]["pending_reservation"] = None
            return "Hubo un error procesando tu reserva. Por favor, intenta de nuevo."
    
    def _is_reservation_confirm(self, message: str) -> bool:
        """Check if message is confirming a reservation"""
        keywords = ["reservar", "reserva", "quiero ese", "confirmo", "ese horario", "ese día"]
        return any(keyword in message for keyword in keywords)
    
    async def _try_parse_reservation_from_message(self, message: str, phone_number: str, conversation: dict = None):
        """Try to parse reservation from message (date, time, capacity)"""
        try:
            message_lower = message.lower().strip()
            logger.info(f"Trying to parse reservation from: '{message_lower}'")
            
            # Quick exit for simple messages
            if len(message_lower) < 10 or message_lower in ['hola', 'si', 'no', 'gracias', 'ok', 'okay']:
                logger.debug(f"Message too short or simple, skipping: '{message_lower}'")
                return None
            
            # Check if this looks like a reservation intent
            # Look for patterns: "a las [hora] para [X] personas", "[día] a las [hora]", etc.
            has_reservation_pattern = any([
                'a las' in message_lower and 'personas' in message_lower,
                'para' in message_lower and 'personas' in message_lower and any(c.isdigit() for c in message_lower),
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
                r'\bel\s+(\w+)\s+a\s+las\s+(\d{1,2})\s+para\s+(\d+)\s+personas?\b',  # "el martes a las 16 para 3 personas"
                r'\b(\w+)\s+a\s+las\s+(\d{1,2})\s+para\s+(\d+)\s+personas?\b',  # "martes a las 16 para 3 personas"
                r'\b(\w+)\s+(\d{1,2}):?(\d{0,2})\s+(\d+)\s+personas?\b',  # "martes 16:00 3 personas"
                r'\b(\d{1,2})\s+de\s+(\w+)\s+a\s+las\s+(\d{1,2})\s+para\s+(\d+)\s+personas?\b',  # "4 de noviembre a las 16 para 3 personas"
                r'\ba\s+las\s+(\d{1,2})\s+para\s+(\d+)\s+personas?\b',  # "a las 16 para 3 personas" (sin día específico)
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
                        
                        logger.info(f"Parsed reservation: date={date_str}, time={time_str}, capacity={capacity}")
                        
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




