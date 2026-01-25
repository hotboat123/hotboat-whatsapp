"""
Quick migration script - Run this with: python migrate_direct.py
Paste your DATABASE_URL when prompted
"""
import psycopg2

DATABASE_URL = input("Pega tu DATABASE_URL de Railway aquí: ").strip()

SQL = """
-- Add unread_count field to whatsapp_leads table
ALTER TABLE whatsapp_leads 
ADD COLUMN IF NOT EXISTS unread_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_read_at TIMESTAMP DEFAULT NULL;

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_leads_unread_count ON whatsapp_leads(unread_count) WHERE unread_count > 0;

COMMENT ON COLUMN whatsapp_leads.unread_count IS 'Number of unread incoming messages from this contact';
COMMENT ON COLUMN whatsapp_leads.last_read_at IS 'Last time admin read this conversation in Kia-Ai interface';
"""

print("\n🔄 Conectando a la base de datos...")
try:
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    
    print("📝 Ejecutando migración...")
    cur.execute(SQL)
    conn.commit()
    
    print("✅ Migración completada con éxito!")
    
    # Verificar
    cur.execute("""
        SELECT column_name, data_type, column_default 
        FROM information_schema.columns 
        WHERE table_name = 'whatsapp_leads' 
        AND column_name IN ('unread_count', 'last_read_at')
        ORDER BY column_name;
    """)
    
    print("\n✅ Columnas verificadas:")
    for col in cur.fetchall():
        print(f"   - {col[0]}: {col[1]} (default: {col[2]})")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
