-- Add display name column so extras_visibility is fully self-contained
ALTER TABLE extras_visibility
    ADD COLUMN IF NOT EXISTS name TEXT;

-- Backfill name from extra_name_lower for any existing rows
UPDATE extras_visibility SET name = extra_name_lower WHERE name IS NULL;
