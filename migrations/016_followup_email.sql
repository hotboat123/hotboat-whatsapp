-- Tracks when the post-booking follow-up email was sent (idempotent daily sweep)
ALTER TABLE hotboat_appointments
ADD COLUMN IF NOT EXISTS followup_email_sent_at TIMESTAMPTZ;
