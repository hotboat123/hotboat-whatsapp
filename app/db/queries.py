"""
Database queries for availability and appointments
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from zoneinfo import ZoneInfo

from app.db.connection import get_connection

# Chilean timezone
CHILE_TZ = ZoneInfo("America/Santiago")

logger = logging.getLogger(__name__)

# Admin notification settings
ADMIN_PHONE = "56974950762"
_last_error_notification = {}  # Track last notification time to avoid spam


async def _notify_admin_db_error(error: Exception, function_name: str) -> None:
    """
    Send WhatsApp notification to admin about database errors
    Only sends once per hour to avoid spam
    """
    try:
        from app.whatsapp.client import WhatsAppClient
        
        # Check if we already notified about this recently (within 1 hour)
        current_time = datetime.now(CHILE_TZ)
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
    Check if a specific time slot is available.
    Checks booknetic_appointments AND all_appointments (web bookings via hotboat_web).
    """
    import pytz
    CHILE_TZ = pytz.timezone('America/Santiago')

    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                slot_start_buf = slot_datetime - timedelta(hours=buffer_hours)
                slot_end       = slot_datetime + timedelta(hours=duration_hours)
                slot_end_buf   = slot_end + timedelta(hours=buffer_hours)

                # Strip tz for booknetic (stores Chile time as UTC)
                s_start = slot_start_buf.replace(tzinfo=None) if slot_start_buf.tzinfo else slot_start_buf
                s_end   = slot_end_buf.replace(tzinfo=None)   if slot_end_buf.tzinfo   else slot_end_buf
                appt_dur = duration_hours + buffer_hours

                # 1. Booknetic appointments
                cur.execute("""
                    SELECT COUNT(*) FROM booknetic_appointments
                    WHERE starts_at IS NOT NULL
                      AND status IS NOT NULL
                      AND status NOT IN ('cancelled','rejected','cancelada','pending_payment','solicitud')
                      AND starts_at < %s
                      AND starts_at + INTERVAL '1 hour' * %s > %s
                """, (s_end, appt_dur, s_start))
                if cur.fetchone()[0] > 0:
                    return False

                # 2. Web bookings (all_appointments canonical source)
                slot_date   = slot_datetime.date()
                slot_h      = slot_datetime.hour
                slot_m      = slot_datetime.minute
                slot_start_min = (slot_h * 60 + slot_m) - int(buffer_hours * 60)
                slot_end_min   = (slot_h * 60 + slot_m) + int((duration_hours + buffer_hours) * 60)
                cur.execute("""
                    SELECT COUNT(*) FROM all_appointments
                    WHERE source = 'hotboat_web'
                      AND fecha = %s
                      AND hora IS NOT NULL
                      AND status NOT IN ('cancelled','rejected','solicitud')
                      AND (
                          (EXTRACT(HOUR FROM hora)::int * 60 + EXTRACT(MINUTE FROM hora)::int)
                              - %s < %s
                          AND (EXTRACT(HOUR FROM hora)::int * 60 + EXTRACT(MINUTE FROM hora)::int)
                              + %s > %s
                      )
                """, (
                    slot_date,
                    int(buffer_hours * 60),
                    slot_end_min,
                    int((duration_hours + buffer_hours) * 60),
                    slot_start_min,
                ))
                if cur.fetchone()[0] > 0:
                    return False

                return True

    except Exception as e:
        logger.error(f"Error checking slot availability: {e}")
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
    import pytz
    CHILE_TZ = pytz.timezone('America/Santiago')
    
    if exclude_statuses is None:
        exclude_statuses = ['cancelled', 'rejected']
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Build query based on exclude_statuses
                if exclude_statuses and len(exclude_statuses) > 0:
                    placeholders = ','.join(['%s'] * len(exclude_statuses))
                    # status NULL in booknetic has produced orphan/ghost blocks; ignore NULL.
                    status_filter = f"AND status IS NOT NULL AND status NOT IN ({placeholders})"
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
                    starts_at = row[1]
                    # Booknetic stores Chile time marked as UTC — fix timezone
                    if starts_at and starts_at.tzinfo is not None:
                        starts_at = CHILE_TZ.localize(starts_at.replace(tzinfo=None))
                    booked_slots.append({
                        "id": row[0],
                        "starts_at": starts_at,
                        "service_name": row[2],
                        "customer_name": row[3],
                        "status": row[4],
                    })

                # Include all_appointments (web hotboat_web + manual/sheets; canonical).
                from datetime import time as dt_time
                cur.execute("""
                    SELECT fecha, hora, nombre_cliente, status
                    FROM all_appointments
                    WHERE source NOT IN ('booknetic')
                      AND fecha >= %s::date
                      AND fecha <= %s::date
                      AND hora IS NOT NULL
                      AND status NOT IN ('cancelled','rejected','cancelada','solicitud','pending_payment')
                    ORDER BY fecha, hora
                """, (start_date, end_date))
                for row in cur.fetchall():
                    b_date, b_time, b_name, b_status = row
                    try:
                        if hasattr(b_time, 'hour'):
                            h, m = b_time.hour, b_time.minute
                        else:
                            parts = str(b_time).split(":")
                            h, m = int(parts[0]), int(parts[1])
                        dt_naive = datetime.combine(b_date, dt_time(h, m))
                        starts_at = CHILE_TZ.localize(dt_naive)
                        booked_slots.append({
                            "id": None,
                            "starts_at": starts_at,
                            "service_name": "Manual",
                            "customer_name": b_name,
                            "status": b_status,
                        })
                    except Exception:
                        pass

                return booked_slots

    except Exception as e:
        logger.error(f"Error getting booked slots: {e}")
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
                # ad_source column added dynamically; use NULL fallback if not yet present
                try:
                    cur.execute("""
                        SELECT
                            latest.phone_number,
                            latest.customer_name,
                            latest.created_at,
                            latest.message_text,
                            latest.response_text,
                            latest.direction,
                            COALESCE(l.unread_count, 0) as unread_count,
                            COALESCE(l.priority, 0) as priority,
                            l.ad_source
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
                        LEFT JOIN whatsapp_leads l ON latest.phone_number = l.phone_number
                        ORDER BY latest.created_at DESC
                        LIMIT %s
                    """, (limit,))
                except Exception:
                    # Fallback: query without ad_source if column doesn't exist yet
                    cur.execute("""
                        SELECT
                            latest.phone_number,
                            latest.customer_name,
                            latest.created_at,
                            latest.message_text,
                            latest.response_text,
                            latest.direction,
                            COALESCE(l.unread_count, 0) as unread_count,
                            COALESCE(l.priority, 0) as priority
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
                        LEFT JOIN whatsapp_leads l ON latest.phone_number = l.phone_number
                        ORDER BY latest.created_at DESC
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
                    unread_count = row[6] if len(row) > 6 else 0
                    priority = row[7] if len(row) > 7 else 0
                    ad_source = row[8] if len(row) > 8 else None

                    if direction == 'outgoing':
                        last_message = response_text or message_text
                    else:
                        last_message = message_text or response_text

                    # Convert UTC to Chilean timezone
                    if created_at:
                        if created_at.tzinfo is None:
                            # If naive datetime, assume it's UTC
                            created_at = created_at.replace(tzinfo=ZoneInfo("UTC"))
                        # Convert to Chilean time
                        created_at = created_at.astimezone(CHILE_TZ)

                    conversations.append({
                        "phone_number": phone_number,
                        "customer_name": customer_name,
                        "last_message_at": created_at.isoformat() if created_at else None,
                        "last_message": last_message,
                        "direction": direction,
                        "unread_count": unread_count,
                        "priority": priority,
                        "ad_source": ad_source,
                    })
                
                conversations.sort(key=lambda x: x["last_message_at"] or "", reverse=True)
                return conversations
    
    except Exception as e:
        logger.error(f"Error querying conversations: {e}")
        return []


async def search_conversations_by_phone(phone_query: str, limit: int = 20) -> List[Dict]:
    """
    Search conversations by phone number (partial match).
    Useful when the conversation is not in the recent list.
    
    Args:
        phone_query: Partial phone number to search (e.g., "5697757730")
        limit: Maximum results to return
    
    Returns:
        List of matching conversations
    """
    if not phone_query or len(phone_query.strip()) < 3:
        return []
    
    query = phone_query.strip().replace(" ", "").replace("+", "")
    if not query.isdigit():
        return []
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        latest.phone_number,
                        latest.customer_name,
                        latest.created_at,
                        latest.message_text,
                        latest.response_text,
                        latest.direction,
                        COALESCE(l.unread_count, 0) as unread_count,
                        COALESCE(l.priority, 0) as priority
                    FROM (
                        SELECT DISTINCT ON (phone_number)
                            phone_number,
                            customer_name,
                            created_at,
                            message_text,
                            response_text,
                            direction
                        FROM whatsapp_conversations
                        WHERE phone_number LIKE %s
                        ORDER BY phone_number, created_at DESC
                    ) latest
                    LEFT JOIN whatsapp_leads l ON latest.phone_number = l.phone_number
                    ORDER BY latest.created_at DESC
                    LIMIT %s
                """, (f"%{query}%", limit))
                
                results = cur.fetchall()
                conversations = []
                for row in results:
                    phone_number = row[0]
                    customer_name = row[1] if row[1] else phone_number
                    created_at = row[2]
                    message_text = row[3] or ""
                    response_text = row[4] or ""
                    direction = row[5] if row[5] else 'incoming'
                    unread_count = row[6] if len(row) > 6 else 0
                    priority = row[7] if len(row) > 7 else 0
                    
                    if direction == 'outgoing':
                        last_message = response_text or message_text
                    else:
                        last_message = message_text or response_text
                    
                    if created_at:
                        if created_at.tzinfo is None:
                            created_at = created_at.replace(tzinfo=ZoneInfo("UTC"))
                        created_at = created_at.astimezone(CHILE_TZ)
                    
                    conversations.append({
                        "phone_number": phone_number,
                        "customer_name": customer_name,
                        "last_message_at": created_at.isoformat() if created_at else None,
                        "last_message": last_message,
                        "direction": direction,
                        "unread_count": unread_count,
                        "priority": priority
                    })
                
                return conversations
    
    except Exception as e:
        logger.error(f"Error searching conversations: {e}")
        return []


def search_messages_in_all_conversations_sync(search_term: str, limit: int = 50) -> List[Dict]:
    """Sync version for use in thread pool (blocking DB operations)."""
    return _search_messages_impl(search_term, limit)


async def search_messages_in_all_conversations(search_term: str, limit: int = 50) -> List[Dict]:
    """Async wrapper - runs sync impl in thread pool via caller."""
    return _search_messages_impl(search_term, limit)


def _search_messages_impl(search_term: str, limit: int = 50) -> List[Dict]:
    """
    Search for a term across:
    - Message content (message_text, response_text)
    - Lead/contact info (customer_name, notes) - for "buscador por nombre"
    Returns conversations matching any of these.
    """
    if not search_term or len(search_term.strip()) < 2:
        return []
    
    term = f"%{search_term.strip()}%"
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # 1) Matches in MESSAGES
                cur.execute("""
                    SELECT 
                        w.phone_number,
                        COUNT(*) as match_count,
                        MAX(w.created_at) as last_match_at,
                        'message' as source
                    FROM whatsapp_conversations w
                    WHERE (w.message_text IS NOT NULL AND w.message_text ILIKE %s)
                       OR (w.response_text IS NOT NULL AND w.response_text ILIKE %s)
                    GROUP BY w.phone_number
                """, (term, term))
                msg_rows = {r[0]: (r[1], r[2], 'message') for r in cur.fetchall()}
                
                # 2) Matches in LEADS (customer_name, notes - e.g. Destinatario, Email in notes)
                cur.execute("""
                    SELECT phone_number, 1 as match_count, last_interaction_at, 'lead' as source
                    FROM whatsapp_leads
                    WHERE (customer_name IS NOT NULL AND customer_name ILIKE %s)
                       OR (notes IS NOT NULL AND notes ILIKE %s)
                """, (term, term))
                lead_rows = {r[0]: (r[1], r[2], 'lead') for r in cur.fetchall()}
                
                # 3) Matches in conversation customer_name (from latest msg)
                cur.execute("""
                    SELECT DISTINCT ON (phone_number) phone_number, customer_name
                    FROM whatsapp_conversations
                    WHERE customer_name IS NOT NULL AND customer_name ILIKE %s
                """, (term,))
                conv_name_matches = [r[0] for r in cur.fetchall()]
                
                # Merge: combine msg + lead matches, dedupe by phone
                seen = {}
                for phone, (cnt, dt, src) in msg_rows.items():
                    seen[phone] = (cnt, dt)
                for phone, (cnt, dt, _) in lead_rows.items():
                    if phone in seen:
                        old_cnt, old_dt = seen[phone]
                        seen[phone] = (old_cnt + cnt, old_dt or dt)
                    else:
                        seen[phone] = (cnt, dt)
                for phone in conv_name_matches:
                    if phone not in seen:
                        cur.execute("SELECT MAX(created_at) FROM whatsapp_conversations WHERE phone_number = %s", (phone,))
                        row = cur.fetchone()
                        seen[phone] = (1, row[0] if row else None)
                    else:
                        old_cnt, old_dt = seen[phone]
                        seen[phone] = (old_cnt + 1, old_dt)
                
                # Sort by match_count desc, then last_match desc; take limit
                def _sort_key(item):
                    _, (cnt, dt) = item
                    try:
                        ts = dt.timestamp() if dt else 0
                    except (AttributeError, OSError):
                        ts = 0
                    return (-cnt, -ts)
                sorted_items = sorted(seen.items(), key=_sort_key)[:limit]
                
                conversations = []
                for phone_number, (match_count, last_match_at) in sorted_items:
                    # Get customer_name and last message
                    cur.execute("""
                        SELECT customer_name, message_text, response_text, direction
                        FROM whatsapp_conversations
                        WHERE phone_number = %s
                        ORDER BY created_at DESC
                        LIMIT 1
                    """, (phone_number,))
                    last_row = cur.fetchone()
                    customer_name = phone_number
                    last_message = ""
                    if last_row:
                        customer_name = last_row[0] or phone_number
                        msg_t, resp_t, direction = last_row[1], last_row[2], last_row[3]
                        if direction == "outgoing":
                            last_message = (resp_t or msg_t or "")[:200]
                        else:
                            last_message = (msg_t or resp_t or "")[:200]
                    
                    # Get lead info
                    cur.execute("""
                        SELECT customer_name, COALESCE(unread_count, 0), COALESCE(priority, 0)
                        FROM whatsapp_leads WHERE phone_number = %s
                    """, (phone_number,))
                    lead_row = cur.fetchone()
                    if lead_row:
                        customer_name = lead_row[0] or customer_name
                        unread_count = lead_row[1]
                        priority = lead_row[2]
                    else:
                        unread_count = 0
                        priority = 0
                    
                    if last_match_at:
                        if last_match_at.tzinfo is None:
                            last_match_at = last_match_at.replace(tzinfo=ZoneInfo("UTC"))
                        last_match_at = last_match_at.astimezone(CHILE_TZ).isoformat()
                    
                    conversations.append({
                        "phone_number": phone_number,
                        "customer_name": customer_name,
                        "last_message": last_message,
                        "last_message_at": last_match_at,
                        "unread_count": unread_count,
                        "priority": priority,
                        "match_count": match_count
                    })
                
                return conversations
    
    except Exception as e:
        logger.error(f"Error searching messages: {e}", exc_info=True)
        return []










