-- When the booking confirmation email was sent (idempotent webhook / retries)
ALTER TABLE hotboat_appointments
ADD COLUMN IF NOT EXISTS confirmation_email_sent_at TIMESTAMPTZ;
