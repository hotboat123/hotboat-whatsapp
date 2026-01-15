-- Create leads/contacts table for classification
CREATE TABLE IF NOT EXISTS whatsapp_leads (
    id SERIAL PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL UNIQUE,
    customer_name VARCHAR(100),
    lead_status VARCHAR(20) DEFAULT 'unknown', -- 'potential_client', 'bad_lead', 'customer', 'unknown'
    notes TEXT,
    tags TEXT[], -- Array of tags for categorization
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_interaction_at TIMESTAMP
);

-- Create index for faster queries by phone number
CREATE INDEX IF NOT EXISTS idx_leads_phone_number ON whatsapp_leads(phone_number);
CREATE INDEX IF NOT EXISTS idx_leads_status ON whatsapp_leads(lead_status);

-- Update whatsapp_conversations table to add message_id and direction
ALTER TABLE whatsapp_conversations 
ADD COLUMN IF NOT EXISTS message_id VARCHAR(100),
ADD COLUMN IF NOT EXISTS direction VARCHAR(10) DEFAULT 'incoming', -- 'incoming' or 'outgoing'
ADD COLUMN IF NOT EXISTS imported BOOLEAN DEFAULT FALSE; -- True if imported from old conversations

-- Create index for message_id
CREATE INDEX IF NOT EXISTS idx_message_id ON whatsapp_conversations(message_id);




