-- Migration 023: Add followup_email_sent_at to all_appointments so manual
-- reservations can participate in the post-booking follow-up email sweep.
ALTER TABLE all_appointments
    ADD COLUMN IF NOT EXISTS followup_email_sent_at TIMESTAMPTZ;
