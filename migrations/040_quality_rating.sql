-- Manual 1-5 quality rating an operator assigns per conversation, to track
-- how well the bot handled it. NULL = not rated yet (kept distinct from a
-- real low score of 1). Applied idempotently at startup via
-- app/db/leads.py::_ensure_quality_col — this file is a historical record.
ALTER TABLE whatsapp_leads ADD COLUMN IF NOT EXISTS quality_rating SMALLINT;
