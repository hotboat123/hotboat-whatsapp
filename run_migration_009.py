#!/usr/bin/env python3
"""
Run migration 009: Add priority field to conversations
"""
import os
import sys
import psycopg2
from pathlib import Path

# Get database URL from environment
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL not set in environment")
    print("\nPlease set it using:")
    print("  export DATABASE_URL='your_database_url'")
    sys.exit(1)

def run_migration():
    """Run the migration"""
    print("🚀 Running Migration 009: Add priority field")
    print(f"📍 Database: {DATABASE_URL[:30]}...")
    
    try:
        # Read migration file
        migration_file = Path(__file__).parent / "migrations" / "009_add_priority_field.sql"
        
        if not migration_file.exists():
            print(f"❌ Migration file not found: {migration_file}")
            sys.exit(1)
        
        with open(migration_file, 'r', encoding='utf-8') as f:
            migration_sql = f.read()
        
        print(f"📄 Read migration file: {migration_file.name}")
        
        # Connect to database
        print("🔌 Connecting to database...")
        conn = psycopg2.connect(DATABASE_URL)
        
        # Run migration
        print("⚙️  Executing migration...")
        with conn.cursor() as cur:
            cur.execute(migration_sql)
            conn.commit()
        
        print("✅ Migration 009 completed successfully!")
        print("\n📊 Changes:")
        print("  • Added 'priority' column to whatsapp_leads table")
        print("  • Created index on priority column")
        print("  • Priority levels: 0 = none, 1 = high, 2 = medium, 3 = low")
        
        # Close connection
        conn.close()
        print("\n✨ All done!")
        
    except Exception as e:
        print(f"\n❌ ERROR running migration: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    run_migration()
