from app.db.connection import get_connection

with get_connection() as conn:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT phone_number, customer_name, unread_count 
            FROM whatsapp_leads 
            WHERE unread_count > 0 
            ORDER BY unread_count DESC 
            LIMIT 15
        """)
        
        results = cur.fetchall()
        
        print("\nConversaciones con badges activos:")
        print("-" * 70)
        print(f"{'Nombre':<35} | {'Telefono':<15} | Badge")
        print("-" * 70)
        
        for row in results:
            name = (row[1] or row[0])[:34]
            phone = row[0]
            badge = row[2]
            print(f"{name:<35} | {phone:<15} | ({badge})")
        
        print(f"\nTotal: {len(results)} conversaciones con badges")
