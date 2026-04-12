-- Stock management system
-- stock_products: catalog of individual products/ingredients
CREATE TABLE IF NOT EXISTS stock_products (
    id              SERIAL PRIMARY KEY,
    name            TEXT NOT NULL,
    category        TEXT DEFAULT '',
    unit            TEXT DEFAULT 'unidad',   -- unidad, kg, litro, bolsa, caja, etc.
    current_stock   NUMERIC DEFAULT 0,
    min_stock       NUMERIC DEFAULT 0,
    cost_per_unit   NUMERIC DEFAULT 0,
    notes           TEXT DEFAULT '',
    is_active       BOOLEAN DEFAULT TRUE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

-- extras_bom: bill-of-materials — which products does each extra consume?
-- is_variant=TRUE means the user must PICK one product from the group (e.g. beer type)
CREATE TABLE IF NOT EXISTS extras_bom (
    id              SERIAL PRIMARY KEY,
    extra_slug      TEXT NOT NULL,
    product_id      INT REFERENCES stock_products(id) ON DELETE CASCADE,
    quantity        NUMERIC DEFAULT 1,
    is_variant      BOOLEAN DEFAULT FALSE,
    variant_label   TEXT DEFAULT '',    -- shown in picker: 'Ámbar', 'Stout', etc.
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bom_slug ON extras_bom(extra_slug);

-- stock_movements: full audit log
-- delta > 0 = stock in (purchase / manual add)
-- delta < 0 = stock out (booking consumption / manual remove)
CREATE TABLE IF NOT EXISTS stock_movements (
    id              SERIAL PRIMARY KEY,
    product_id      INT REFERENCES stock_products(id),
    product_name    TEXT DEFAULT '',   -- snapshot so history survives product rename
    delta           NUMERIC NOT NULL,
    reason          TEXT DEFAULT '',   -- 'booking', 'purchase', 'manual', 'return'
    booking_ref     TEXT DEFAULT '',
    extra_slug      TEXT DEFAULT '',
    notes           TEXT DEFAULT '',
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_movements_product ON stock_movements(product_id);
CREATE INDEX IF NOT EXISTS idx_movements_booking  ON stock_movements(booking_ref);

-- Track which extras have been consumed per booking (prevents double-deduct)
ALTER TABLE hotboat_appointments
    ADD COLUMN IF NOT EXISTS stock_consumed_at TIMESTAMPTZ;
ALTER TABLE all_appointments
    ADD COLUMN IF NOT EXISTS stock_consumed_at TIMESTAMPTZ;
