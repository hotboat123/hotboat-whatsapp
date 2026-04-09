-- Migration 024: Track when the "pending payment" reminder email was sent
-- so we only send it once per booking and only if payment wasn't completed.
ALTER TABLE hotboat_appointments
    ADD COLUMN IF NOT EXISTS pending_email_sent_at TIMESTAMPTZ;
