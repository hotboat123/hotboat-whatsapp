-- Coupon / discount codes
CREATE TABLE IF NOT EXISTS coupons (
    id                  SERIAL PRIMARY KEY,
    code                TEXT NOT NULL UNIQUE,           -- e.g. "VERANO20"
    name                TEXT DEFAULT '',               -- internal label
    discount_percent    NUMERIC DEFAULT 0,             -- e.g. 20 = 20% off
    discount_fixed      NUMERIC DEFAULT 0,             -- flat CLP off (alternative)
    extra_description   TEXT DEFAULT '',               -- e.g. "🎰 Tiro en la ruleta"
    max_uses            INT DEFAULT 0,                 -- 0 = unlimited
    uses_count          INT DEFAULT 0,
    expires_at          DATE DEFAULT NULL,             -- NULL = never expires
    is_active           BOOLEAN DEFAULT TRUE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Track which bookings used which coupon
ALTER TABLE hotboat_appointments
    ADD COLUMN IF NOT EXISTS coupon_code TEXT DEFAULT NULL;
ALTER TABLE hotboat_appointments
    ADD COLUMN IF NOT EXISTS coupon_discount NUMERIC DEFAULT 0;
