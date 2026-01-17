#!/usr/bin/env python3
"""
Temporary script to run database migration for bot_enabled field
Run once, then delete this file.
"""
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

def run_migration():
    print("🔄 Connecting to database...")
    
    with psycopg.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            print("📝 Adding bot_enabled column...")
            
            try:
                cur.execute("""
                    ALTER TABLE whatsapp_leads 
                    ADD COLUMN bot_enabled BOOLEAN DEFAULT TRUE;
                """)
                print("✅ Column added successfully")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print("⚠️ Column already exists, skipping...")
                else:
                    print(f"❌ Error adding column: {e}")
                    raise
            
            print("📝 Creating index...")
            try:
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_whatsapp_leads_bot_enabled 
                    ON whatsapp_leads(bot_enabled);
                """)
                print("✅ Index created successfully")
            except Exception as e:
                print(f"❌ Error creating index: {e}")
                raise
            
            conn.commit()
            print("✅ Migration completed successfully!")
            
            # Verify
            cur.execute("SELECT COUNT(*) FROM whatsapp_leads WHERE bot_enabled IS NOT NULL")
            count = cur.fetchone()[0]
            print(f"✅ Verified: {count} leads have bot_enabled field")

if __name__ == "__main__":
    try:
        run_migration()
    except Exception as e:
        print(f"💥 Migration failed: {e}")
        exit(1)
