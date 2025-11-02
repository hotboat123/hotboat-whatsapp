-- Create whatsapp_conversations table for storing chat history
CREATE TABLE IF NOT EXISTS whatsapp_conversations (
    id SERIAL PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL,
    customer_name VARCHAR(100),
    message_text TEXT NOT NULL,
    response_text TEXT NOT NULL,
    message_type VARCHAR(20) DEFAULT 'text',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster queries by phone number
CREATE INDEX IF NOT EXISTS idx_phone_number ON whatsapp_conversations(phone_number);

-- Create index for faster queries by date
CREATE INDEX IF NOT EXISTS idx_created_at ON whatsapp_conversations(created_at DESC);

