"""
Script para limpiar el historial de conversaciones con Tomo
"""
import os
import sys
from app.db.connection import get_connection

def clear_tomo_conversations():
    """Elimina todas las conversaciones con el número de Tomo"""
    
    # Número de Tomo
    tomo_phone = "56977577307"
    
    # Auto-confirm desde argumentos de línea de comandos
    auto_confirm = len(sys.argv) > 1 and sys.argv[1] == "--yes"
    
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Contar mensajes antes de eliminar
                count_query = """
                    SELECT COUNT(*) as total 
                    FROM whatsapp_conversations 
                    WHERE phone_number = %s
                """
                cur.execute(count_query, (tomo_phone,))
                result = cur.fetchone()
                total_messages = result[0]
                
                print(f"[INFO] Total de mensajes con Tomo ({tomo_phone}): {total_messages}")
                
                if total_messages == 0:
                    print("[OK] No hay mensajes para eliminar")
                    return
                
                # Confirmar
                if not auto_confirm:
                    print(f"\n[WARNING] Estas seguro de eliminar {total_messages} mensajes?")
                    print("   Escribe 'SI' para confirmar: ", end="")
                    confirmation = input().strip().upper()
                    
                    if confirmation != "SI":
                        print("[CANCELADO] Operacion cancelada")
                        return
                else:
                    print(f"[INFO] Auto-confirmando eliminacion de {total_messages} mensajes...")
                
                # Eliminar mensajes
                delete_query = """
                    DELETE FROM whatsapp_conversations 
                    WHERE phone_number = %s
                """
                cur.execute(delete_query, (tomo_phone,))
                conn.commit()
                
                print(f"[OK] Se eliminaron {total_messages} mensajes de Tomo")
                
                # Verificar
                cur.execute(count_query, (tomo_phone,))
                verify_result = cur.fetchone()
                remaining = verify_result[0]
                print(f"[INFO] Mensajes restantes: {remaining}")
                
                # También limpiar metadata del lead
                print("\n[INFO] Limpiando metadata del lead...")
                reset_lead_query = """
                    UPDATE whatsapp_leads 
                    SET bot_enabled = true 
                    WHERE phone_number = %s
                """
                cur.execute(reset_lead_query, (tomo_phone,))
                conn.commit()
                print("[OK] Metadata del lead limpiada")
                
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    clear_tomo_conversations()
