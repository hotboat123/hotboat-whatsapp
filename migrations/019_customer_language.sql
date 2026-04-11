-- Language preference stored at booking time (es / en / pt)
ALTER TABLE hotboat_appointments
    ADD COLUMN IF NOT EXISTS customer_language VARCHAR(5) DEFAULT 'es';
