"""
Script to run database migrations for leads and conversations

Environment variables required:
- DATABASE_URL: PostgreSQL connection string (automatically loaded from .env or Railway)
"""
import os
import sys
import psycopg

# Load environment variables from .env file if it exists
from dotenv import load_dotenv
load_dotenv()

# Get DATABASE_URL from environment
DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    print("❌ Error: DATABASE_URL environment variable is not set")
    print("   Please set it in your .env file or Railway environment variables")
    sys.exit(1)

def run_migrations():
    """Run SQL migrations"""
    print("🔧 Running database migrations...")
    print("=" * 60)
    
    try:
        with psycopg.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # Read and execute create_leads_table.sql
                print("\n📋 Creating leads table and updating conversations table...")
                
                # Create leads table
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS whatsapp_leads (
                        id SERIAL PRIMARY KEY,
                        phone_number VARCHAR(20) NOT NULL UNIQUE,
                        customer_name VARCHAR(100),
                        lead_status VARCHAR(20) DEFAULT 'unknown',
                        notes TEXT,
                        tags TEXT[],
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        last_interaction_at TIMESTAMP
                    );
                """)
                
                # Create indexes for leads
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_leads_phone_number ON whatsapp_leads(phone_number);
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_leads_status ON whatsapp_leads(lead_status);
                """)
                
                # Create conversations table if it doesn't exist
                print("\n📋 Creating/updating conversations table...")
                
                # Create carts table
                print("\n🛒 Creating carts table...")
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS whatsapp_carts (
                        id SERIAL PRIMARY KEY,
                        phone_number VARCHAR(20) NOT NULL UNIQUE,
                        customer_name VARCHAR(100),
                        cart_data JSONB NOT NULL DEFAULT '[]'::jsonb,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_carts_phone_number ON whatsapp_carts(phone_number);
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_carts_updated_at ON whatsapp_carts(updated_at DESC);
                """)
                
                cur.execute("""
                    CREATE TABLE IF NOT EXISTS whatsapp_conversations (
                        id SERIAL PRIMARY KEY,
                        phone_number VARCHAR(20) NOT NULL,
                        customer_name VARCHAR(100),
                        message_text TEXT NOT NULL,
                        response_text TEXT NOT NULL,
                        message_type VARCHAR(20) DEFAULT 'text',
                        message_id VARCHAR(100),
                        direction VARCHAR(10) DEFAULT 'incoming',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        imported BOOLEAN DEFAULT FALSE
                    );
                """)
                
                # Create indexes for conversations
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_phone_number ON whatsapp_conversations(phone_number);
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_created_at ON whatsapp_conversations(created_at DESC);
                """)
                
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_message_id ON whatsapp_conversations(message_id);
                """)
                
                # Add columns if they don't exist (for existing tables)
                cur.execute("""
                    DO $$ 
                    BEGIN
                        IF EXISTS (SELECT 1 FROM information_schema.tables 
                                   WHERE table_name = 'whatsapp_conversations') THEN
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                           WHERE table_name = 'whatsapp_conversations' 
                                           AND column_name = 'message_id') THEN
                                ALTER TABLE whatsapp_conversations 
                                ADD COLUMN message_id VARCHAR(100);
                            END IF;
                            
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                           WHERE table_name = 'whatsapp_conversations' 
                                           AND column_name = 'direction') THEN
                                ALTER TABLE whatsapp_conversations 
                                ADD COLUMN direction VARCHAR(10) DEFAULT 'incoming';
                            END IF;
                            
                            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                           WHERE table_name = 'whatsapp_conversations' 
                                           AND column_name = 'imported') THEN
                                ALTER TABLE whatsapp_conversations 
                                ADD COLUMN imported BOOLEAN DEFAULT FALSE;
                            END IF;
                        END IF;
                    END $$;
                """)
                
                # Create index for message_id
                cur.execute("""
                    CREATE INDEX IF NOT EXISTS idx_message_id ON whatsapp_conversations(message_id);
                """)
                
                conn.commit()
                
                print("\n✅ Migrations completed successfully!")
                print("\n📊 Verifying tables...")
                
                # Verify leads table
                cur.execute("""
                    SELECT COUNT(*) FROM whatsapp_leads;
                """)
                lead_count = cur.fetchone()[0]
                print(f"   • whatsapp_leads: {lead_count} leads")
                
                # Verify conversations table
                cur.execute("""
                    SELECT COUNT(*) FROM whatsapp_conversations;
                """)
                conv_count = cur.fetchone()[0]
                print(f"   • whatsapp_conversations: {conv_count} conversations")
                
                print("\n" + "=" * 60)
                print("✅ Database ready for leads management and conversation import!")
                
    except Exception as e:
        print(f"\n❌ Error running migrations: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    return True

if __name__ == "__main__":
    success = run_migrations()
    sys.exit(0 if success else 1)

