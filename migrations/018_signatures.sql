-- T&C passenger signatures: one row per passenger per booking
CREATE TABLE IF NOT EXISTS hotboat_signatures (
    id               SERIAL PRIMARY KEY,
    booking_ref      VARCHAR(50)  NOT NULL,
    passenger_name   VARCHAR(255) NOT NULL,
    passenger_email  VARCHAR(255),
    passenger_phone  VARCHAR(50),
    passenger_birthday DATE,
    accepted_tc      BOOLEAN      DEFAULT TRUE,
    ip_address       VARCHAR(50),
    created_at       TIMESTAMPTZ  DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signatures_booking_ref ON hotboat_signatures(booking_ref);
CREATE INDEX IF NOT EXISTS idx_signatures_email       ON hotboat_signatures(passenger_email);
