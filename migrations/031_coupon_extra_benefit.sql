-- Extra benefit copy shown to customer (e.g. ruleta) persisted on booking row
ALTER TABLE all_appointments ADD COLUMN IF NOT EXISTS coupon_extra_benefit TEXT DEFAULT NULL;
