-- 034_utilidad_flag.sql: flag to include/exclude transactions from bonus utility base
ALTER TABLE all_appointments
    ADD COLUMN IF NOT EXISTS incluir_en_utilidad BOOLEAN DEFAULT TRUE;

ALTER TABLE gastos
    ADD COLUMN IF NOT EXISTS incluir_en_utilidad BOOLEAN DEFAULT TRUE;
