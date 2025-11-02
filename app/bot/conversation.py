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
            # Get or create conversation context
            conversation = self.get_conversation(from_number, contact_name)
            
            # Add message to history
            conversation["messages"].append({
                "role": "user",
                "content": message_text,
                "timestamp": datetime.now().isoformat(),
                "message_id": message_id
            })
            
            logger.info(f"Processing message from {contact_name}: {message_text}")
            
            # Check if it's the first message or a greeting - send welcome message
            is_first = self._is_first_message(conversation)
            is_greeting = self._is_greeting_message(message_text)
            
            if is_first and is_greeting:
                logger.info("First message with greeting - sending welcome message")
                response = """¡Hola! Soy el asistente virtual de HotBoat Chile 🤖🚤
Estoy aquí para ayudarte con tus consultas sobre nuestras experiencias flotantes.

Si prefieres hablar con un humano, puedes esperar a Tomás — te responderá en cuanto pueda 🌿"""
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
    
    def get_conversation(self, phone_number: str, contact_name: str) -> dict:
        """Get or create conversation context"""
        if phone_number not in self.conversations:
            self.conversations[phone_number] = {
                "phone": phone_number,
                "name": contact_name,
                "messages": [],
                "created_at": datetime.now().isoformat(),
                "last_interaction": datetime.now().isoformat(),
                "metadata": {}
            }
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
            "buenas noches", "buen día", "saludos", "qué tal", "que tal"
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
        """Check if this is the first message in the conversation"""
        # Count user messages only
        user_messages = [msg for msg in conversation.get("messages", []) if msg.get("role") == "user"]
        return len(user_messages) <= 1
    
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
        
        # First check: traditional keywords
        keywords = [
            "disponibilidad", "disponible", "horario", "cuándo", "cuando",
            "fecha", "día", "reservar", "reserva", "agendar"
        ]
        if any(keyword in message_lower for keyword in keywords):
            return True
        
        # Second check: if message contains a date pattern, treat it as availability query
        if self._contains_date(message):
            logger.info(f"Date pattern detected in message, treating as availability query")
            return True
        
        return False



