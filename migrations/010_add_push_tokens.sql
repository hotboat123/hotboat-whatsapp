-- Migration: Add push_tokens table for mobile push notifications
-- This replaces email notifications with free push notifications via Expo

CREATE TABLE IF NOT EXISTS push_tokens (
    id SERIAL PRIMARY KEY,
    token TEXT NOT NULL UNIQUE,
    device_info JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    last_used_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_push_tokens_last_used 
ON push_tokens(last_used_at DESC);

CREATE INDEX IF NOT EXISTS idx_push_tokens_token 
ON push_tokens(token);

COMMENT ON TABLE push_tokens IS 'Registered push notification tokens for mobile devices';
COMMENT ON COLUMN push_tokens.token IS 'Expo push token (ExponentPushToken[...])';
COMMENT ON COLUMN push_tokens.device_info IS 'Device metadata (platform, name, etc.)';
COMMENT ON COLUMN push_tokens.last_used_at IS 'Last time this token was used/updated';
