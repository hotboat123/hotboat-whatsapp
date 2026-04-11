-- 1-hour pre-booking admin notification tracker
ALTER TABLE hotboat_appointments
    ADD COLUMN IF NOT EXISTS pre_booking_notif_sent_at TIMESTAMPTZ;
