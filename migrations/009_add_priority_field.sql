-- Migration 009: Add priority field to whatsapp_leads table
-- This allows marking conversations with urgency levels (1, 2, 3)

-- Add priority column (default 0 means no priority set)
ALTER TABLE whatsapp_leads
ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 0;

-- Add index for faster filtering by priority
CREATE INDEX IF NOT EXISTS idx_whatsapp_leads_priority ON whatsapp_leads(priority);

-- Update comment
COMMENT ON COLUMN whatsapp_leads.priority IS 'Urgency level: 0 = none, 1 = high, 2 = medium, 3 = low';
