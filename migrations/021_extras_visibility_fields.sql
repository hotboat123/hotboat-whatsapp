-- Add persistent editable fields to extras_visibility (survive Sheets re-sync)
ALTER TABLE extras_visibility
    ADD COLUMN IF NOT EXISTS description  TEXT,
    ADD COLUMN IF NOT EXISTS precio_venta INTEGER,
    ADD COLUMN IF NOT EXISTS costo        INTEGER,
    ADD COLUMN IF NOT EXISTS icon         TEXT;
