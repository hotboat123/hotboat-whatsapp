"""
Database queries for availability and appointments
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from app.db.connection import get_connection

logger = logging.getLogger(__name__)

# Admin notification settings
ADMIN_PHONE = "56977577307"
_last_error_notification = {}  # Track last notification time to avoid spam


async def _notify_admin_db_error(error: Exception, function_name: str) -> None:
    """
    Send WhatsApp notification to admin about database errors
    Only sends once per hour to avoid spam
    """
    try:
        from app.whatsapp.client import WhatsAppClient
        
        # Check if we already notified about this recently (within 1 hour)
        current_time = datetime.now()
        error_key = f"{function_name}_{type(error).__name__}"
        
        if error_key in _last_error_notification:
            last_notification = _last_error_notification[error_key]
            if (current_time - last_notification).total_seconds() < 3600:  # 1 hour
                logger.info(f"Skipping admin notification for {error_key} - already notified recently")
                return
        
        # Send notification
        client = WhatsAppClient()
        message = f"⚠️ *Error de Base de Datos*\n\n"
        message += f"🔧 *Función:* {function_name}\n"
        message += f"❌ *Error:* {type(error).__name__}\n"
        message += f"📝 *Detalles:* {str(error)[:200]}\n\n"
        message += f"🕐 *Hora:* {current_time.strftime('%H:%M:%S')}\n\n"
        message += f"⚡ *Acción:* El bot está bloqueando disponibilidad por seguridad. Revisa la base de datos."
        
        await client.send_text_message(ADMIN_PHONE, message)
        
        # Update last notification time
        _last_error_notification[error_key] = current_time
        logger.info(f"Admin notified about database error in {function_name}")
        
    except Exception as notify_error:
        logger.error(f"Failed to notify admin about database error: {notify_error}")


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
                        "starts_at": row[4].isoformat() if row[4] else None,
                        "status": row[5]
                    })
                
                return appointments
    
    except Exception as e:
        logger.error(f"Error querying appointments: {e}")
        return []


async def check_slot_availability(slot_datetime: datetime, duration_hours: float = 2.0, buffer_hours: float = 0.5) -> bool:
    """
    Check if a specific time slot is available
    
    Args:
        slot_datetime: DateTime to check
        duration_hours: Duration of the booking in hours
        buffer_hours: Buffer time before/after booking
    
    Returns:
        True if available, False if booked
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Calculate the actual slot range with buffer
                # Slot needs buffer before start and after end
                slot_start_with_buffer = slot_datetime - timedelta(hours=buffer_hours)
                slot_end = slot_datetime + timedelta(hours=duration_hours)
                slot_end_with_buffer = slot_end + timedelta(hours=buffer_hours)
                
                # An appointment overlaps if:
                # 1. Appointment starts before our slot ends (with buffer), AND
                # 2. Appointment ends (with buffer) after our slot starts
                # 
                # Appointment duration is assumed to be 2 hours (can be made configurable later)
                appointment_duration_hours = 2.0
                
                # Calculate appointment end with buffer using Python timedelta
                # Then pass as parameter to avoid SQL injection
                cur.execute("""
                    SELECT COUNT(*)
                    FROM booknetic_appointments
                    WHERE starts_at IS NOT NULL
                      AND (status IS NULL OR status NOT IN ('cancelled', 'rejected'))
                      AND (
                          -- Appointment starts before our slot ends (with buffer)
                          starts_at < %s
                          AND (
                              -- Appointment ends (with buffer) after our slot starts (with buffer)
                              starts_at + INTERVAL '1 hour' * %s > %s
                          )
                      )
                """, (
                    slot_end_with_buffer,  # Our slot end with buffer
                    appointment_duration_hours + buffer_hours,  # Appointment duration + buffer
                    slot_start_with_buffer  # Our slot start with buffer
                ))
                
                count = cur.fetchone()[0]
                return count == 0
    
    except Exception as e:
        logger.error(f"Error checking slot availability: {e}")
        # Notify admin about the database error
        await _notify_admin_db_error(e, "check_slot_availability")
        return False


async def get_booked_slots(
    start_date: datetime,
    end_date: datetime,
    exclude_statuses: Optional[List[str]] = None
) -> List[Dict]:
    """
    Get all booked time slots between dates
    
    Args:
        start_date: Start date for search
        end_date: End date for search
        exclude_statuses: List of statuses to exclude (default: ['cancelled', 'rejected'])
    
    Returns:
        List of booked slots with datetime and service info
    """
    if exclude_statuses is None:
        exclude_statuses = ['cancelled', 'rejected']
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Build query based on exclude_statuses
                if exclude_statuses and len(exclude_statuses) > 0:
                    placeholders = ','.join(['%s'] * len(exclude_statuses))
                    status_filter = f"AND (status IS NULL OR status NOT IN ({placeholders}))"
                    params = (start_date, end_date) + tuple(exclude_statuses)
                else:
                    status_filter = ""
                    params = (start_date, end_date)
                
                cur.execute(f"""
                    SELECT 
                        id,
                        starts_at,
                        service_name,
                        customer_name,
                        status
                    FROM booknetic_appointments
                    WHERE starts_at >= %s
                      AND starts_at <= %s
                      AND starts_at IS NOT NULL
                      {status_filter}
                    ORDER BY starts_at
                """, params)
                
                results = cur.fetchall()
                
                booked_slots = []
                for row in results:
                    booked_slots.append({
                        "id": row[0],
                        "starts_at": row[1],
                        "service_name": row[2],
                        "customer_name": row[3],
                        "status": row[4]
                    })
                
                return booked_slots
    
    except Exception as e:
        logger.error(f"Error getting booked slots: {e}")
        # Notify admin about the database error
        await _notify_admin_db_error(e, "get_booked_slots")
        return []


async def save_conversation(
    phone_number: str,
    customer_name: str,
    message_text: str,
    response_text: str,
    message_type: str = "text",
    message_id: str = None,
    direction: str = "incoming"
) -> None:
    """
    Save conversation to database for analytics
    
    Args:
        phone_number: Customer phone
        customer_name: Customer name
        message_text: User's message
        response_text: Bot's response
        message_type: Type of message
        message_id: WhatsApp message ID (to avoid duplicates)
        direction: 'incoming' or 'outgoing'
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Check if message already exists (by message_id if available)
                if message_id:
                    cur.execute("""
                        SELECT id FROM whatsapp_conversations 
                        WHERE message_id = %s
                    """, (message_id,))
                    if cur.fetchone():
                        logger.info(f"Conversation with message_id {message_id} already exists, skipping")
                        return
                
                cur.execute("""
                    INSERT INTO whatsapp_conversations 
                    (phone_number, customer_name, message_text, response_text, message_type, message_id, direction, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                """, (phone_number, customer_name, message_text, response_text, message_type, message_id, direction))
            conn.commit()
            logger.info(f"Conversation saved for {phone_number}")
    
    except Exception as e:
        logger.warning(f"Could not save conversation: {e}")
        # Don't fail if we can't save - this is not critical


async def get_recent_conversations(limit: int = 50) -> List[Dict]:
    """
    Get recent conversations from database grouped by phone number
    
    Args:
        limit: Maximum number of conversations to return
    
    Returns:
        List of conversations with latest message per phone number
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        phone_number,
                        customer_name,
                        created_at,
                        message_text,
                        response_text,
                        direction
                    FROM (
                        SELECT DISTINCT ON (phone_number)
                            phone_number,
                            customer_name,
                            created_at,
                            message_text,
                            response_text,
                            direction
                        FROM whatsapp_conversations
                        ORDER BY phone_number, created_at DESC
                    ) latest
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))
                
                results = cur.fetchall()
                
                conversations = []
                for row in results:
                    phone_number = row[0]
                    customer_name = row[1] if row[1] else phone_number
                    created_at = row[2]
                    message_text = row[3] or ""
                    response_text = row[4] or ""
                    direction = row[5] if row[5] else 'incoming'
                    
                    if direction == 'outgoing':
                        last_message = response_text or message_text
                    else:
                        last_message = message_text or response_text
                    
                    conversations.append({
                        "phone_number": phone_number,
                        "customer_name": customer_name,
                        "last_message_at": created_at.isoformat() if created_at else None,
                        "last_message": last_message,
                        "direction": direction
                    })
                
                conversations.sort(key=lambda x: x["last_message_at"] or "", reverse=True)
                return conversations
    
    except Exception as e:
        logger.error(f"Error querying conversations: {e}")
        return []








