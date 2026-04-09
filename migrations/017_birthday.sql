-- Customer birthday for the birthday email trigger
ALTER TABLE hotboat_appointments
ADD COLUMN IF NOT EXISTS customer_birthday DATE;

-- One birthday email per customer per calendar year (dedup across multiple bookings)
CREATE TABLE IF NOT EXISTS birthday_emails_sent (
    customer_email  VARCHAR(255) NOT NULL,
    sent_year       INT          NOT NULL,
    sent_at         TIMESTAMPTZ  DEFAULT NOW(),
    PRIMARY KEY (customer_email, sent_year)
);
