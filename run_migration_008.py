"""
Run migration 008: Add unread_count to whatsapp_leads
"""
import psycopg2
from app.config import get_settings
import sys

def run_migration():
    settings = get_settings()
    
    print("🔄 Running migration 008: Add unread_count to whatsapp_leads...")
    
    try:
        # Connect to database
        conn = psycopg2.connect(settings.database_url)
        cur = conn.cursor()
        
        # Read and execute migration
        with open('migrations/008_add_unread_count.sql', 'r') as f:
            migration_sql = f.read()
        
        print("📝 Executing SQL migration...")
        cur.execute(migration_sql)
        conn.commit()
        
        print("✅ Migration 008 completed successfully!")
        
        # Verify the column was added
        cur.execute("""
            SELECT column_name, data_type, column_default 
            FROM information_schema.columns 
            WHERE table_name = 'whatsapp_leads' 
            AND column_name IN ('unread_count', 'last_read_at')
            ORDER BY column_name;
        """)
        
        columns = cur.fetchall()
        if columns:
            print("\n✅ Verified new columns:")
            for col in columns:
                print(f"   - {col[0]}: {col[1]} (default: {col[2]})")
        else:
            print("⚠️ Warning: Could not verify columns")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run_migration()
