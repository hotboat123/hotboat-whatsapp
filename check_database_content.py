"""
Script para verificar el contenido de la base de datos de Kia-Ai
"""
import asyncio
from app.db.connection import get_connection

async def check_database():
    print("=" * 60)
    print("VERIFICANDO CONTENIDO DE LA BASE DE DATOS")
    print("=" * 60)
    
    try:
        # Check conversations table
        print("\n[1] Tabla: whatsapp_conversations")
        print("-" * 60)
        
        with get_connection() as conn:
            with conn.cursor() as cur:
                # Count total conversations
                cur.execute("SELECT COUNT(*) FROM whatsapp_conversations")
                total = cur.fetchone()[0]
                print(f"Total de conversaciones: {total}")
                
                # Count by direction
                cur.execute("""
                    SELECT direction, COUNT(*) 
                    FROM whatsapp_conversations 
                    GROUP BY direction
                """)
                for row in cur.fetchall():
                    direction = row[0] if row[0] else 'NULL'
                    count = row[1]
                    print(f"  - {direction}: {count} mensajes")
                
                # Show sample records
                print("\nMuestra de registros (últimos 5):")
                cur.execute("""
                    SELECT 
                        phone_number,
                        customer_name,
                        message_text,
                        response_text,
                        direction,
                        created_at
                    FROM whatsapp_conversations
                    ORDER BY created_at DESC
                    LIMIT 5
                """)
                
                for i, row in enumerate(cur.fetchall(), 1):
                    print(f"\n  Registro {i}:")
                    print(f"    Teléfono: {row[0]}")
                    print(f"    Nombre: {row[1] if row[1] else 'Sin nombre'}")
                    print(f"    Mensaje: {row[2][:50] if row[2] else 'NULL'}...")
                    print(f"    Respuesta: {row[3][:50] if row[3] else 'NULL'}...")
                    print(f"    Dirección: {row[4] if row[4] else 'NULL'}")
                    print(f"    Fecha: {row[5]}")
        
        # Check leads table
        print("\n" + "=" * 60)
        print("[2] Tabla: whatsapp_leads")
        print("-" * 60)
        
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM whatsapp_leads")
                total = cur.fetchone()[0]
                print(f"Total de leads: {total}")
                
                # Count by status
                cur.execute("""
                    SELECT lead_status, COUNT(*) 
                    FROM whatsapp_leads 
                    GROUP BY lead_status
                """)
                for row in cur.fetchall():
                    status = row[0] if row[0] else 'NULL'
                    count = row[1]
                    print(f"  - {status}: {count} leads")
                
                # Show all leads
                print("\nTodos los leads:")
                cur.execute("""
                    SELECT 
                        phone_number,
                        customer_name,
                        lead_status,
                        last_interaction_at
                    FROM whatsapp_leads
                    ORDER BY last_interaction_at DESC
                """)
                
                for i, row in enumerate(cur.fetchall(), 1):
                    print(f"\n  Lead {i}:")
                    print(f"    Teléfono: {row[0]}")
                    print(f"    Nombre: {row[1] if row[1] else 'Sin nombre'}")
                    print(f"    Estado: {row[2]}")
                    print(f"    Última interacción: {row[3]}")
        
        # Check table structure
        print("\n" + "=" * 60)
        print("[3] Estructura de whatsapp_conversations")
        print("-" * 60)
        
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT column_name, data_type, is_nullable
                    FROM information_schema.columns
                    WHERE table_name = 'whatsapp_conversations'
                    ORDER BY ordinal_position
                """)
                
                print("\nColumnas:")
                for row in cur.fetchall():
                    nullable = "NULL" if row[2] == 'YES' else "NOT NULL"
                    print(f"  - {row[0]}: {row[1]} ({nullable})")
        
        print("\n" + "=" * 60)
        print("VERIFICACIÓN COMPLETADA")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(check_database())

