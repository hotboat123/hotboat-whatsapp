"""
Script para marcar conversaciones recientes como no leídas
Útil después de la migración para ver el badge en acción
"""
import asyncio
from datetime import datetime, timedelta
from app.db.connection import get_connection
from app.config import get_settings
from zoneinfo import ZoneInfo

CHILE_TZ = ZoneInfo("America/Santiago")

async def set_unread_for_recent_conversations(hours_back=48):
    """
    Marca como no leídas las conversaciones con mensajes en las últimas X horas
    que nunca se han marcado como leídas
    """
    settings = get_settings()
    
    print(f"Buscando conversaciones con mensajes de las ultimas {hours_back} horas...\n")
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Obtener conversaciones con mensajes recientes que nunca se han leído
                cutoff_time = datetime.now(CHILE_TZ) - timedelta(hours=hours_back)
                
                cur.execute("""
                    SELECT DISTINCT ON (c.phone_number)
                        c.phone_number,
                        c.customer_name,
                        COUNT(*) OVER (PARTITION BY c.phone_number) as message_count,
                        MAX(c.created_at) OVER (PARTITION BY c.phone_number) as last_message,
                        l.last_read_at,
                        l.unread_count
                    FROM whatsapp_conversations c
                    LEFT JOIN whatsapp_leads l ON c.phone_number = l.phone_number
                    WHERE c.created_at > %s
                      AND c.direction = 'incoming'
                    ORDER BY c.phone_number, c.created_at DESC
                """, (cutoff_time,))
                
                conversations = cur.fetchall()
                
                if not conversations:
                    print("No se encontraron conversaciones recientes")
                    return
                
                print(f"Encontradas {len(conversations)} conversaciones:\n")
                
                updated_count = 0
                for conv in conversations:
                    phone = conv[0]
                    name = conv[1] or phone
                    msg_count = conv[2]
                    last_read = conv[4]
                    current_unread = conv[5] or 0
                    
                    # Solo actualizar si nunca se ha leído O si unread_count es 0
                    should_update = last_read is None or current_unread == 0
                    
                    status = ""
                    if should_update:
                        # Contar mensajes incoming desde la última lectura (o todos si nunca se leyó)
                        if last_read:
                            cur.execute("""
                                SELECT COUNT(*)
                                FROM whatsapp_conversations
                                WHERE phone_number = %s
                                  AND direction = 'incoming'
                                  AND created_at > %s
                            """, (phone, last_read))
                        else:
                            cur.execute("""
                                SELECT COUNT(*)
                                FROM whatsapp_conversations
                                WHERE phone_number = %s
                                  AND direction = 'incoming'
                                  AND created_at > %s
                            """, (phone, cutoff_time))
                        
                        unread = cur.fetchone()[0]
                        
                        if unread > 0:
                            cur.execute("""
                                UPDATE whatsapp_leads
                                SET unread_count = %s
                                WHERE phone_number = %s
                            """, (unread, phone))
                            status = f"OK - Actualizado a {unread} no leidos"
                            updated_count += 1
                        else:
                            status = "SKIP - Sin mensajes nuevos"
                    else:
                        status = f"SKIP - Ya marcado ({current_unread} no leidos)"
                    
                    print(f"  {name[:30]:30} | {phone} | {status}")
                
                conn.commit()
                
                print(f"\n{updated_count} conversaciones actualizadas")
                print("\nRefresca Kia-Ai para ver los badges!")
                
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    import sys
    
    hours = 48  # Default: últimas 48 horas
    if len(sys.argv) > 1:
        try:
            hours = int(sys.argv[1])
        except:
            print("Uso: python set_unread_for_recent.py [horas]")
            print("Ejemplo: python set_unread_for_recent.py 24")
            sys.exit(1)
    
    print(f"Marcando conversaciones de las ultimas {hours} horas como no leidas\n")
    asyncio.run(set_unread_for_recent_conversations(hours))
