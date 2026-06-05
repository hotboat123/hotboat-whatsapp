-- 032_gastos.sql: expense tracking with categories
CREATE TABLE IF NOT EXISTS gastos_categorias (
    id SERIAL PRIMARY KEY,
    nombre TEXT NOT NULL,
    nivel INTEGER NOT NULL DEFAULT 1,
    parent_id INTEGER REFERENCES gastos_categorias(id) ON DELETE CASCADE,
    keywords JSONB DEFAULT '[]',
    color TEXT DEFAULT '#6b7280',
    icono TEXT DEFAULT '📌',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gastos (
    id SERIAL PRIMARY KEY,
    fecha DATE NOT NULL DEFAULT CURRENT_DATE,
    monto INTEGER NOT NULL DEFAULT 0,
    descripcion TEXT DEFAULT '',
    comercio TEXT DEFAULT '',
    imagen_path TEXT DEFAULT '',
    categoria1_id INTEGER REFERENCES gastos_categorias(id) ON DELETE SET NULL,
    categoria2_id INTEGER REFERENCES gastos_categorias(id) ON DELETE SET NULL,
    notas TEXT DEFAULT '',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gastos_fecha ON gastos(fecha);
CREATE INDEX IF NOT EXISTS idx_gastos_cat1 ON gastos(categoria1_id);
