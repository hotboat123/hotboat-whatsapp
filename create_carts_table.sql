-- Create shopping carts table
CREATE TABLE IF NOT EXISTS whatsapp_carts (
    id SERIAL PRIMARY KEY,
    phone_number VARCHAR(20) NOT NULL UNIQUE,
    customer_name VARCHAR(100),
    cart_data JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Create index for faster queries
CREATE INDEX IF NOT EXISTS idx_carts_phone_number ON whatsapp_carts(phone_number);
CREATE INDEX IF NOT EXISTS idx_carts_updated_at ON whatsapp_carts(updated_at DESC);

