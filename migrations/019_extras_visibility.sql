-- Persistent visibility overrides for "Precios Extras" items.
-- This table is NOT synced from Google Sheets, so it survives DB resyncs.
CREATE TABLE IF NOT EXISTS extras_visibility (
    extra_name_lower TEXT PRIMARY KEY,  -- LOWER(raw->>'Extra')
    show_in_booking  BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
