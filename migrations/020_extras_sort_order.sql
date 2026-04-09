-- Add sort_order to extras_visibility for admin-controlled ordering
ALTER TABLE extras_visibility
    ADD COLUMN IF NOT EXISTS sort_order INTEGER NOT NULL DEFAULT 999;
