"""
Conversation manager - handles message flow and context
"""
import logging
import re
from typing import Dict, Optional
from datetime import datetime

from app.bot.ai_handler import AIHandler
from app.bot.availability import AvailabilityChecker, SPANISH_MONTHS
from app.bot.faq import FAQHandler
from app.db.leads import get_or_create_lead, get_conversation_history

logger = logging.getLogger(__name__)


class ConversationManager:
    """Manages conversations with users"""
    
    def __init__(self):
        self.ai_handler = AIHandler()
        self.availability_checker = AvailabilityChecker()
        self.faq_handler = FAQHandler()
        # In-memory conversation storage (use Redis or DB in production)
        self.conversations: Dict[str, dict] = {}
    
    async def process_message(
        self,
        from_number: str,
        message_text: str,
        contact_name: str,
        message_id: str
    ) -> Optional[str]:
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
            # Check if it's a FAQ question
            elif self.faq_handler.get_response(message_text):
                logger.info("Responding with FAQ answer")
                response = self.faq_handler.get_response(message_text)
            
            # Check if asking about availability
            elif self.is_availability_query(message_text):
                logger.info("Checking availability")
                response = await self.availability_checker.check_availability(message_text)
            
            # Use AI for general conversation
            else:
                logger.info("Using AI handler for response")
                response = await self.ai_handler.generate_response(
                    message_text=message_text,
                    conversation_history=conversation["messages"],
                    contact_name=contact_name
                )
            
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
            lead = await get_or_create_lead(phone_number, contact_name)
            history = await get_conversation_history(phone_number, limit=50)
            
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



