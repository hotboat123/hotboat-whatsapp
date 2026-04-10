-- Migration 025: Add medio_contacto column to all_appointments
-- Tracks the contact channel used to reach the client (Instagram, WhatsApp, etc.)
ALTER TABLE all_appointments
    ADD COLUMN IF NOT EXISTS medio_contacto VARCHAR(64);
