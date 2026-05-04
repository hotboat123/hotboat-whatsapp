-- Migration 029: Add has_flex and flex_amount to all_appointments
ALTER TABLE all_appointments
    ADD COLUMN IF NOT EXISTS has_flex    BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS flex_amount NUMERIC DEFAULT 0;
