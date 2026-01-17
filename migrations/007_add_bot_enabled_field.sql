-- Add bot_enabled field to whatsapp_leads table
-- This allows manual intervention by disabling automatic bot responses per user

ALTER TABLE whatsapp_leads 
ADD COLUMN IF NOT EXISTS bot_enabled BOOLEAN DEFAULT TRUE;

-- Add index for faster queries
CREATE INDEX IF NOT EXISTS idx_whatsapp_leads_bot_enabled 
ON whatsapp_leads(bot_enabled);

-- Add comment
COMMENT ON COLUMN whatsapp_leads.bot_enabled IS 'Controls whether automatic bot responses are enabled for this lead';
