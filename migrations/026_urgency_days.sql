-- Migration 026: Per-day urgency mode overrides
-- Each row forces urgency ON (enabled=true) or OFF (enabled=false) for a specific date,
-- overriding the global urgency_mode setting.
CREATE TABLE IF NOT EXISTS urgency_days (
    fecha   DATE        PRIMARY KEY,
    enabled BOOLEAN     NOT NULL DEFAULT TRUE,
    reason  VARCHAR(255)
);
