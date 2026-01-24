"""
Script para limpiar el historial de conversaciones con Tomo
"""
import asyncio
import os
from app.db.connection import get_db_pool

async def clear_tomo_conversations():
    """Elimina todas las conversaciones con el número de Tomo"""
    
    # Número de Tomo
    tomo_phone = "56977577307"
    
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Contar mensajes antes de eliminar
            count_query = """
                SELECT COUNT(*) as total 
                FROM conversations 
                WHERE phone_number = $1
            """
            result = await conn.fetchrow(count_query, tomo_phone)
            total_messages = result['total']
            
            print(f"📊 Total de mensajes con Tomo ({tomo_phone}): {total_messages}")
            
            if total_messages == 0:
                print("✅ No hay mensajes para eliminar")
                return
            
            # Confirmar
            print(f"\n⚠️  ¿Estás seguro de eliminar {total_messages} mensajes?")
            print("   Escribe 'SI' para confirmar: ", end="")
            confirmation = input().strip().upper()
            
            if confirmation != "SI":
                print("❌ Operación cancelada")
                return
            
            # Eliminar mensajes
            delete_query = """
                DELETE FROM conversations 
                WHERE phone_number = $1
            """
            await conn.execute(delete_query, tomo_phone)
            
            print(f"✅ Se eliminaron {total_messages} mensajes de Tomo")
            
            # Verificar
            verify_result = await conn.fetchrow(count_query, tomo_phone)
            remaining = verify_result['total']
            print(f"📊 Mensajes restantes: {remaining}")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await pool.close()

if __name__ == "__main__":
    asyncio.run(clear_tomo_conversations())
