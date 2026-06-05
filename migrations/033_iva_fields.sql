-- 033_iva_fields.sql: IVA tracking fields for gastos and ventas
ALTER TABLE all_appointments
    ADD COLUMN IF NOT EXISTS boletado BOOLEAN DEFAULT FALSE;

ALTER TABLE gastos
    ADD COLUMN IF NOT EXISTS tipo_documento VARCHAR(20) DEFAULT 'boleta';
