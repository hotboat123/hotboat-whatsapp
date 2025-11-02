"""
Database queries for availability and appointments
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from app.db.connection import get_connection

logger = logging.getLogger(__name__)


async def get_appointments_between_dates(
    start_date: datetime,
    end_date: datetime
) -> List[Dict]:
    """
    Get all appointments between two dates
    
    Args:
        start_date: Start date
        end_date: End date
    
    Returns:
        List of appointments
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        id,
                        customer_name,
                        customer_email,
                        service_name,
                        starts_at,
                        status
                    FROM booknetic_appointments
                    WHERE starts_at >= %s
                      AND starts_at <= %s
                      AND status NOT IN ('cancelled', 'rejected')
                    ORDER BY starts_at
                """, (start_date, end_date))
                
                results = cur.fetchall()
                
                appointments = []
                for row in results:
                    appointments.append({
                        "id": row[0],
                        "customer_name": row[1],
                        "customer_email": row[2],
                        "service_name": row[3],
                        "starts_at": row[4],
                        "status": row[5]
                    })
                
                return appointments
    
    except Exception as e:
        logger.error(f"Error querying appointments: {e}")
        return []


async def check_slot_availability(slot_datetime: datetime) -> bool:
    """
    Check if a specific time slot is available
    
    Args:
        slot_datetime: DateTime to check
    
    Returns:
        True if available, False if booked
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Check if there's an appointment within 2 hours of this time
                cur.execute("""
                    SELECT COUNT(*)
                    FROM booknetic_appointments
                    WHERE starts_at BETWEEN %s AND %s
                      AND status NOT IN ('cancelled', 'rejected')
                """, (
                    slot_datetime - timedelta(hours=1),
                    slot_datetime + timedelta(hours=1)
                ))
                
                count = cur.fetchone()[0]
                return count == 0
    
    except Exception as e:
        logger.error(f"Error checking slot availability: {e}")
        return False


async def save_conversation(
    phone_number: str,
    customer_name: str,
    message_text: str,
    response_text: str,
    message_type: str = "text"
) -> None:
    """
    Save conversation to database for analytics
    
    Args:
        phone_number: Customer phone
        customer_name: Customer name
        message_text: User's message
        response_text: Bot's response
        message_type: Type of message
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # TODO: Create conversations table if it doesn't exist
                cur.execute("""
                    INSERT INTO whatsapp_conversations 
                    (phone_number, customer_name, message_text, response_text, message_type, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                """, (phone_number, customer_name, message_text, response_text, message_type))
            conn.commit()
            logger.info(f"Conversation saved for {phone_number}")
    
    except Exception as e:
        logger.warning(f"Could not save conversation: {e}")
        # Don't fail if we can't save - this is not critical


async def get_recent_conversations(limit: int = 50) -> List[Dict]:
    """
    Get recent conversations from database
    
    Args:
        limit: Maximum number of conversations to return
    
    Returns:
        List of conversations
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        id,
                        phone_number,
                        customer_name,
                        message_text,
                        response_text,
                        message_type,
                        created_at
                    FROM whatsapp_conversations
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
                
                results = cur.fetchall()
                
                conversations = []
                for row in results:
                    conversations.append({
                        "id": row[0],
                        "phone_number": row[1],
                        "customer_name": row[2],
                        "message_text": row[3],
                        "response_text": row[4],
                        "message_type": row[5],
                        "created_at": row[6].isoformat() if row[6] else None
                    })
                
                return conversations
    
    except Exception as e:
        logger.error(f"Error querying conversations: {e}")
        return []



