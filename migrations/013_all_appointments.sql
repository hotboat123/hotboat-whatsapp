-- Migration 013: Unified all_appointments table
-- Consolidates: Reservas_Con_Extras_Sheets (historical) + booknetic_appointments + hotboat_appointments (future)

CREATE TABLE IF NOT EXISTS all_appointments (
    id                      SERIAL PRIMARY KEY,
    -- Source tracking
    source                  VARCHAR(30) NOT NULL DEFAULT 'manual',
    source_id               TEXT,           -- original ID in source table
    appointment_id          TEXT,           -- external booking ref / booknetic ID

    -- Date / time
    fecha                   DATE NOT NULL,
    hora                    TIME,

    -- Customer
    nombre_cliente          TEXT,
    email                   TEXT,
    telefono                TEXT,

    -- Service
    servicio                TEXT,
    num_personas            TEXT,
    num_adultos             INT DEFAULT 0,
    num_ninos               INT DEFAULT 0,

    -- Financials (in CLP)
    ingreso_reserva         NUMERIC DEFAULT 0,
    ingreso_extras          NUMERIC DEFAULT 0,
    ingreso_total           NUMERIC DEFAULT 0,
    costo_operativo_fijo    NUMERIC DEFAULT 0,
    costo_operativo_variable NUMERIC DEFAULT 0,
    costo_operativo_total   NUMERIC DEFAULT 0,

    -- Operational fields (editable from dashboard)
    ciudad_origen           TEXT,
    como_supieron           TEXT,
    clima_del_dia           TEXT,
    categoria_clientes      TEXT,
    tipo_clientes           TEXT,
    tiene_cruce             BOOLEAN DEFAULT FALSE,
    observaciones           TEXT,           -- admin notes (editable)

    -- Extras
    extras_json             JSONB DEFAULT '{}',

    -- Status
    status                  TEXT,

    -- Payment (from hotboat_appointments)
    payment_id              TEXT,
    payment_status          TEXT,

    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aa_fecha    ON all_appointments (fecha);
CREATE INDEX IF NOT EXISTS idx_aa_status   ON all_appointments (status);
CREATE INDEX IF NOT EXISTS idx_aa_source   ON all_appointments (source, source_id);
CREATE INDEX IF NOT EXISTS idx_aa_telefono ON all_appointments (telefono);
CREATE INDEX IF NOT EXISTS idx_aa_appt_id  ON all_appointments (appointment_id);
