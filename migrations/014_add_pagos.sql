-- Migration 014: Add pagos JSONB column to all_appointments
-- Stores an array of payment records: [{amount, method, date}]
ALTER TABLE all_appointments
  ADD COLUMN IF NOT EXISTS pagos JSONB DEFAULT '[]'::jsonb;
