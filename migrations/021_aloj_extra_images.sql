-- Multiple images per alojamiento (stored as JSON array of URLs)
ALTER TABLE alojamientos
    ADD COLUMN IF NOT EXISTS extra_images JSONB DEFAULT '[]';
