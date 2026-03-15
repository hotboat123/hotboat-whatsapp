-- Add index to speed up message search (ILIKE on message_text, response_text)
-- Requires pg_trgm extension for trigram similarity
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_conversations_message_text_gin 
ON whatsapp_conversations USING gin (message_text gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_conversations_response_text_gin 
ON whatsapp_conversations USING gin (response_text gin_trgm_ops);
