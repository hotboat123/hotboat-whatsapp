-- Add unread_count field to whatsapp_leads table
-- This tracks the number of unread messages from the customer

ALTER TABLE whatsapp_leads 
ADD COLUMN IF NOT EXISTS unread_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_read_at TIMESTAMP DEFAULT NULL;

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_leads_unread_count ON whatsapp_leads(unread_count) WHERE unread_count > 0;

COMMENT ON COLUMN whatsapp_leads.unread_count IS 'Number of unread incoming messages from this contact';
COMMENT ON COLUMN whatsapp_leads.last_read_at IS 'Last time admin read this conversation in Kia-Ai interface';
