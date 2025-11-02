"""
Conversation manager - handles message flow and context
"""
import logging
from typing import Dict, Optional
from datetime import datetime

from app.bot.ai_handler import AIHandler
from app.bot.availability import AvailabilityChecker
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
            
            # Check if it's a FAQ question
            faq_response = self.faq_handler.get_response(message_text)
            if faq_response:
                logger.info("Responding with FAQ answer")
                response = faq_response
            
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
    
    def is_availability_query(self, message: str) -> bool:
        """Check if message is asking about availability"""
        keywords = [
            "disponibilidad", "disponible", "horario", "cuándo", "cuando",
            "fecha", "día", "reservar", "reserva", "agendar"
        ]
        message_lower = message.lower()
        return any(keyword in message_lower for keyword in keywords)


