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
                
                # Contar items en carrito
                cart_query = "SELECT COUNT(*) FROM whatsapp_carts WHERE phone_number = %s"
                cur.execute(cart_query, (tomo_phone,))
                cart_count = cur.fetchone()[0]
                print(f"[INFO] Items en carrito: {cart_count}")
                
                if total_messages == 0 and cart_count == 0:
                    print("[OK] No hay datos para eliminar")
                    return
                
                # Confirmar
                if not auto_confirm:
                    print(f"\n[WARNING] Estas seguro de eliminar {total_messages} mensajes y {cart_count} items del carrito?")
                    print("   Escribe 'SI' para confirmar: ", end="")
                    confirmation = input().strip().upper()
                    
                    if confirmation != "SI":
                        print("[CANCELADO] Operacion cancelada")
                        return
                else:
                    print(f"[INFO] Auto-confirmando limpieza completa...")
                
                # 1. Eliminar items del carrito
                print("[INFO] Eliminando items del carrito...")
                delete_cart = "DELETE FROM whatsapp_carts WHERE phone_number = %s"
                cur.execute(delete_cart, (tomo_phone,))
                print(f"[OK] {cart_count} items eliminados del carrito")
                
                # 2. Eliminar mensajes
                print("[INFO] Eliminando mensajes...")
                delete_query = """
                    DELETE FROM whatsapp_conversations 
                    WHERE phone_number = %s
                """
                cur.execute(delete_query, (tomo_phone,))
                print(f"[OK] {total_messages} mensajes eliminados")
                
                # 3. Resetear el lead (mantener el lead pero limpiar estado)
                print("[INFO] Reseteando lead...")
                reset_lead_query = """
                    UPDATE whatsapp_leads 
                    SET bot_enabled = true,
                        lead_status = 'new',
                        unread_count = 0
                    WHERE phone_number = %s
                """
                cur.execute(reset_lead_query, (tomo_phone,))
                print("[OK] Lead reseteado")
                
                conn.commit()
                
                # Verificar
                print("\n[INFO] Verificando limpieza...")
                cur.execute(count_query, (tomo_phone,))
                remaining = cur.fetchone()[0]
                cur.execute(cart_query, (tomo_phone,))
                remaining_cart = cur.fetchone()[0]
                
                print(f"[RESULT] Mensajes restantes: {remaining}")
                print(f"[RESULT] Items en carrito restantes: {remaining_cart}")
                print("\n[OK] Limpieza completa exitosa!")
                
    except Exception as e:
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    clear_tomo_conversations()
