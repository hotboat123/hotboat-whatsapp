-- Migration 030: Scope urgency_days per product (HotBoat global vs experience / pack / alojamiento)
-- Existing rows become hotboat + empty slug (same behavior as before for availability).

ALTER TABLE urgency_days ADD COLUMN IF NOT EXISTS entity_type VARCHAR(32) NOT NULL DEFAULT 'hotboat';
ALTER TABLE urgency_days ADD COLUMN IF NOT EXISTS entity_slug VARCHAR(160) NOT NULL DEFAULT '';

ALTER TABLE urgency_days DROP CONSTRAINT IF EXISTS urgency_days_pkey;

ALTER TABLE urgency_days ADD PRIMARY KEY (entity_type, entity_slug, fecha);
