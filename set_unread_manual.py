#!/usr/bin/env python3
"""
Script simple para establecer unread_count=1 en una conversación específica
Para probar el sistema de notificaciones
"""
import os
import sys
from dotenv import load_dotenv
import psycopg

# Load environment
load_dotenv()

def set_unread(phone_number: str, count: int = 1):
    """Set unread count for a specific phone number"""
    try:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            print("❌ DATABASE_URL not found in environment")
            return False
        
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                # First check if lead exists
                cur.execute("""
                    SELECT phone_number, customer_name, unread_count 
                    FROM whatsapp_leads 
                    WHERE phone_number = %s
                """, (phone_number,))
                
                row = cur.fetchone()
                if not row:
                    print(f"❌ No lead found with phone number: {phone_number}")
                    return False
                
                old_count = row[2] or 0
                print(f"📱 Found: {row[1] or row[0]}")
                print(f"   Current unread: {old_count}")
                
                # Update unread count
                cur.execute("""
                    UPDATE whatsapp_leads
                    SET unread_count = %s,
                        updated_at = NOW()
                    WHERE phone_number = %s
                """, (count, phone_number))
                
                conn.commit()
                print(f"✅ Updated unread_count to: {count}")
                return True
                
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python set_unread_manual.py <phone_number> [count]")
        print("Example: python set_unread_manual.py 56993321806 3")
        sys.exit(1)
    
    phone = sys.argv[1]
    count = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    
    print(f"🔧 Setting unread_count={count} for {phone}")
    success = set_unread(phone, count)
    
    if success:
        print("\n✅ Done! Now:")
        print("   1. Refresh Kia-Ai (Ctrl+Shift+R)")
        print("   2. You should see a green badge with the number")
        print("   3. Click on the conversation to mark it as read")
    else:
        sys.exit(1)
