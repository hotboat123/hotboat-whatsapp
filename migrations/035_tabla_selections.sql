CREATE TABLE IF NOT EXISTS tabla_selections (
  id           SERIAL PRIMARY KEY,
  booking_ref  VARCHAR(50) UNIQUE NOT NULL,
  tabla_type   VARCHAR(50),
  elige_1      TEXT,
  elige_2      JSONB DEFAULT '[]',
  elige_3      JSONB DEFAULT '[]',
  completed_at TIMESTAMP WITH TIME ZONE,
  created_at   TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_tabla_booking_ref ON tabla_selections(booking_ref);
