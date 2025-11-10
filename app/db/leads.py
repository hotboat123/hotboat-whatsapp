"""
Leads and contacts management
"""
import logging
from typing import Optional, List, Dict
from datetime import datetime

from app.db.connection import get_connection

logger = logging.getLogger(__name__)


async def get_or_create_lead(phone_number: str, customer_name: str = None) -> Dict:
    """
    Get or create a lead in the database
    
    Args:
        phone_number: Contact phone number
        customer_name: Contact name
    
    Returns:
        Lead dictionary
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Try to get existing lead
                cur.execute("""
                    SELECT 
                        id, phone_number, customer_name, lead_status, 
                        notes, tags, created_at, updated_at, last_interaction_at
                    FROM whatsapp_leads
                    WHERE phone_number = %s
                """, (phone_number,))
                
                row = cur.fetchone()
                
                if row:
                    # Update last interaction
                    cur.execute("""
                        UPDATE whatsapp_leads
                        SET last_interaction_at = NOW(),
                            updated_at = NOW()
                        WHERE phone_number = %s
                    """, (phone_number,))
                    
                    if customer_name and customer_name != row[2]:
                        # Update name if different
                        cur.execute("""
                            UPDATE whatsapp_leads
                            SET customer_name = %s, updated_at = NOW()
                            WHERE phone_number = %s
                        """, (customer_name, phone_number))
                    
                    conn.commit()
                    
                    return {
                        "id": row[0],
                        "phone_number": row[1],
                        "customer_name": row[2],
                        "lead_status": row[3],
                        "notes": row[4],
                        "tags": row[5] if row[5] else [],
                        "created_at": row[6].isoformat() if row[6] else None,
                        "updated_at": row[7].isoformat() if row[7] else None,
                        "last_interaction_at": row[8].isoformat() if row[8] else None
                    }
                else:
                    # Create new lead
                    cur.execute("""
                        INSERT INTO whatsapp_leads 
                        (phone_number, customer_name, lead_status, last_interaction_at, created_at, updated_at)
                        VALUES (%s, %s, 'unknown', NOW(), NOW(), NOW())
                        RETURNING id
                    """, (phone_number, customer_name))
                    
                    lead_id = cur.fetchone()[0]
                    conn.commit()
                    
                    return {
                        "id": lead_id,
                        "phone_number": phone_number,
                        "customer_name": customer_name,
                        "lead_status": "unknown",
                        "notes": None,
                        "tags": [],
                        "created_at": datetime.now().isoformat(),
                        "updated_at": datetime.now().isoformat(),
                        "last_interaction_at": datetime.now().isoformat()
                    }
    
    except Exception as e:
        logger.error(f"Error getting/creating lead: {e}")
        import traceback
        traceback.print_exc()
        return None


async def update_lead_status(phone_number: str, lead_status: str, notes: str = None) -> bool:
    """
    Update lead classification status
    
    Args:
        phone_number: Contact phone number
        lead_status: 'potential_client', 'bad_lead', 'customer', 'unknown'
        notes: Optional notes about the lead
    
    Returns:
        True if successful
    """
    try:
        valid_statuses = ['potential_client', 'bad_lead', 'customer', 'unknown']
        if lead_status not in valid_statuses:
            logger.error(f"Invalid lead status: {lead_status}")
            return False
        
        with get_connection() as conn:
            with conn.cursor() as cur:
                if notes:
                    cur.execute("""
                        UPDATE whatsapp_leads
                        SET lead_status = %s, notes = %s, updated_at = NOW()
                        WHERE phone_number = %s
                    """, (lead_status, notes, phone_number))
                else:
                    cur.execute("""
                        UPDATE whatsapp_leads
                        SET lead_status = %s, updated_at = NOW()
                        WHERE phone_number = %s
                    """, (lead_status, phone_number))
                
                conn.commit()
                return True
    
    except Exception as e:
        logger.error(f"Error updating lead status: {e}")
        return False


async def get_leads_by_status(lead_status: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """
    Get leads filtered by status
    
    Args:
        lead_status: Filter by status (None = all)
        limit: Maximum number of leads to return
    
    Returns:
        List of leads
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                if lead_status:
                    cur.execute("""
                        SELECT 
                            id, phone_number, customer_name, lead_status, 
                            notes, tags, created_at, updated_at, last_interaction_at
                        FROM whatsapp_leads
                        WHERE lead_status = %s
                        ORDER BY last_interaction_at DESC NULLS LAST
                        LIMIT %s
                    """, (lead_status, limit))
                else:
                    cur.execute("""
                        SELECT 
                            id, phone_number, customer_name, lead_status, 
                            notes, tags, created_at, updated_at, last_interaction_at
                        FROM whatsapp_leads
                        ORDER BY last_interaction_at DESC NULLS LAST
                        LIMIT %s
                    """, (limit,))
                
                results = cur.fetchall()
                
                leads = []
                for row in results:
                    leads.append({
                        "id": row[0],
                        "phone_number": row[1],
                        "customer_name": row[2],
                        "lead_status": row[3],
                        "notes": row[4],
                        "tags": row[5] if row[5] else [],
                        "created_at": row[6].isoformat() if row[6] else None,
                        "updated_at": row[7].isoformat() if row[7] else None,
                        "last_interaction_at": row[8].isoformat() if row[8] else None
                    })
                
                return leads
    
    except Exception as e:
        logger.error(f"Error getting leads: {e}")
        return []


async def get_conversation_history(phone_number: str, limit: int = 50) -> List[Dict]:
    """
    Get conversation history for a specific phone number
    
    Args:
        phone_number: Contact phone number
        limit: Maximum number of messages to return
    
    Returns:
        List of conversation messages in chronological order
    """
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT 
                        id,
                        message_text,
                        response_text,
                        message_type,
                        direction,
                        created_at
                    FROM whatsapp_conversations
                    WHERE phone_number = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                """, (phone_number, limit))
                
                results = cur.fetchall()
                
                history = []
                for row in results:
                    # Build conversation history format for AI
                    # User messages
                    history.append({
                        "role": "user",
                        "content": row[1],
                        "timestamp": row[5].isoformat() if row[5] else None
                    })
                    
                    # Bot responses
                    if row[2]:  # If there's a response
                        history.append({
                            "role": "assistant",
                            "content": row[2],
                            "timestamp": row[5].isoformat() if row[5] else None
                        })
                
                return history
    
    except Exception as e:
        logger.error(f"Error getting conversation history: {e}")
        return []


async def import_conversation_batch(
    conversations: List[Dict],
    phone_number: str,
    customer_name: str = None
) -> int:
    """
    Import a batch of conversations for a contact
    
    Args:
        conversations: List of conversation dicts with 'message', 'response', 'timestamp', 'direction'
        phone_number: Contact phone number
        customer_name: Contact name
    
    Returns:
        Number of conversations imported
    """
    try:
        # First ensure lead exists
        await get_or_create_lead(phone_number, customer_name)
        
        imported_count = 0
        with get_connection() as conn:
            with conn.cursor() as cur:
                for conv in conversations:
                    message_text = conv.get('message', '')
                    response_text = conv.get('response', '')
                    timestamp = conv.get('timestamp')
                    direction = conv.get('direction', 'incoming')
                    message_id = conv.get('message_id')
                    
                    if not message_text and not response_text:
                        continue
                    
                    # Check if already exists (by message_id if available)
                    if message_id:
                        cur.execute("""
                            SELECT id FROM whatsapp_conversations 
                            WHERE message_id = %s
                        """, (message_id,))
                        if cur.fetchone():
                            continue  # Skip duplicates
                    
                    # Insert conversation
                    if timestamp:
                        cur.execute("""
                            INSERT INTO whatsapp_conversations 
                            (phone_number, customer_name, message_text, response_text, 
                             message_type, direction, message_id, created_at, imported)
                            VALUES (%s, %s, %s, %s, 'text', %s, %s, %s, TRUE)
                        """, (phone_number, customer_name, message_text, response_text, 
                              direction, message_id, timestamp))
                    else:
                        cur.execute("""
                            INSERT INTO whatsapp_conversations 
                            (phone_number, customer_name, message_text, response_text, 
                             message_type, direction, message_id, imported)
                            VALUES (%s, %s, %s, %s, 'text', %s, %s, TRUE)
                        """, (phone_number, customer_name, message_text, response_text, 
                              direction, message_id))
                    
                    imported_count += 1
                
                conn.commit()
                
                # Update lead's last interaction
                cur.execute("""
                    UPDATE whatsapp_leads
                    SET last_interaction_at = (
                        SELECT MAX(created_at) FROM whatsapp_conversations 
                        WHERE phone_number = %s
                    ),
                    updated_at = NOW()
                    WHERE phone_number = %s
                """, (phone_number, phone_number))
                conn.commit()
        
        logger.info(f"Imported {imported_count} conversations for {phone_number}")
        return imported_count
    
    except Exception as e:
        logger.error(f"Error importing conversations: {e}")
        import traceback
        traceback.print_exc()
        return 0



