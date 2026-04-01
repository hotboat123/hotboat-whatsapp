-- Migration 012
CREATE TABLE IF NOT EXISTS hotboat_appointments (
    id SERIAL PRIMARY KEY,
    booking_ref VARCHAR(20) UNIQUE NOT NULL,
    customer_name VARCHAR(255) NOT NULL,
    customer_phone VARCHAR(50) NOT NULL,
    customer_email VARCHAR(255),
    booking_date DATE NOT NULL,
    booking_time TIME NOT NULL,
    num_people INT NOT NULL,
    price_per_person INT NOT NULL,
    subtotal INT NOT NULL,
    extras_total INT NOT NULL DEFAULT 0,
    flex_amount INT NOT NULL DEFAULT 0,
    total_price INT NOT NULL,
    extras JSONB,
    has_flex BOOLEAN DEFAULT FALSE,
    status VARCHAR(30) NOT NULL,
    payment_id VARCHAR(255),
    payment_order_id VARCHAR(255),
    payment_status VARCHAR(30),
    paid_at TIMESTAMPTZ,
    source VARCHAR(30),
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_hb_date   ON hotboat_appointments (booking_date);
CREATE INDEX IF NOT EXISTS idx_hb_status ON hotboat_appointments (status);
CREATE INDEX IF NOT EXISTS idx_hb_phone  ON hotboat_appointments (customer_phone);
CREATE INDEX IF NOT EXISTS idx_hb_ref    ON hotboat_appointments (booking_ref);
CREATE INDEX IF NOT EXISTS idx_hb_pay    ON hotboat_appointments (payment_id);
