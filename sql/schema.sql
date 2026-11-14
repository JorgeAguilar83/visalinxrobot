-- =============================================================================
-- ESQUEMA DE BASE DE DATOS: VISALINX (Automatización de Citas Consulares y CAS)
-- =============================================================================

-- 1. Catálogos Oficiales de Sedes Consulares
CREATE TABLE IF NOT EXISTS sedes_consulares (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) UNIQUE NOT NULL,      -- Coincide exactamente con el label del HTML
    activo BOOLEAN DEFAULT TRUE
);

-- 2. Catálogos Oficiales de Sedes CAS / ASC
CREATE TABLE IF NOT EXISTS sedes_cas (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) UNIQUE NOT NULL,      -- Coincide exactamente con el label del HTML
    activo BOOLEAN DEFAULT TRUE
);

-- Inserción inicial de los 10 Consulados oficiales en México
INSERT INTO sedes_consulares (nombre) VALUES 
    ('Ciudad Juarez'), ('Guadalajara'), ('Hermosillo'), ('Matamoros'), 
    ('Merida'), ('Mexico City'), ('Monterrey'), ('Nogales'), 
    ('Nuevo Laredo'), ('Tijuana')
ON CONFLICT (nombre) DO NOTHING;

-- Inserción inicial de los 10 CAS oficiales en México
INSERT INTO sedes_cas (nombre) VALUES 
    ('Ciudad Juarez ASC'), ('Guadalajara ASC'), ('Hermosillo ASC'), ('Matamoros ASC'), 
    ('Merida ASC'), ('Mexico City ASC'), ('Monterrey ASC'), ('Nogales ASC'), 
    ('Nuevo Laredo ASC'), ('Tijuana ASC')
ON CONFLICT (nombre) DO NOTHING;

-- 3. Entidad Clientes (1 Cliente = 1 Grupo de Telegram)
CREATE TABLE IF NOT EXISTS clientes (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,              -- Nombre del cliente o familia
    telefono VARCHAR(50),                      -- Contacto directo
    telegram_chat_id VARCHAR(100),            -- ID negativo del grupo de Telegram exclusivo
    notas TEXT,                                -- Comentarios internos de la agencia
    activo BOOLEAN DEFAULT TRUE,               -- Enciende o apaga el cliente completo
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Cuentas de Embajada (Logins en ais.usvisa-info.com)
CREATE TABLE IF NOT EXISTS cuentas_embajada (
    id SERIAL PRIMARY KEY,
    cliente_id INT NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    correo VARCHAR(255) NOT NULL,
    contrasena VARCHAR(255) NOT NULL,
    usar_proxy BOOLEAN DEFAULT TRUE,          -- Flag de proxy por cuenta
    proxy_server VARCHAR(255),
    proxy_username VARCHAR(255),
    proxy_password VARCHAR(255),
    activa BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 5. Trámites / IVRs (La unidad de trabajo del Robot)
CREATE TABLE IF NOT EXISTS tramites (
    id SERIAL PRIMARY KEY,
    cuenta_id INT NOT NULL REFERENCES cuentas_embajada(id) ON DELETE CASCADE,
    ivr VARCHAR(50) NOT NULL,
    solicitante_principal VARCHAR(150),       -- Nombre en la tarjeta de la embajada
    estado_actual VARCHAR(100) DEFAULT 'Programe la cita',
    fecha_inicio DATE NOT NULL,
    fecha_tope DATE NOT NULL,
    dias_margen_traslado INT DEFAULT 2,
    solo_consular BOOLEAN DEFAULT FALSE,
    estado_proceso VARCHAR(50) DEFAULT 'PENDIENTE', -- 'PENDIENTE', 'AGENDADO', 'PAUSADO', 'CANCELADO'
    
    -- Campos que el bot llena automáticamente al confirmar con éxito:
    consulado_agendado VARCHAR(100),
    fecha_consular_agendada DATE,
    hora_consular_agendada VARCHAR(20),
    cas_agendado VARCHAR(100),
    fecha_cas_agendada DATE,
    hora_cas_agendada VARCHAR(20),
    agendado_at TIMESTAMPTZ,
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 6. Opciones de Sedes Deseadas por Trámite
CREATE TABLE IF NOT EXISTS tramite_opciones (
    id SERIAL PRIMARY KEY,
    tramite_id INT NOT NULL REFERENCES tramites(id) ON DELETE CASCADE,
    consulado_id INT NOT NULL REFERENCES sedes_consulares(id),
    cas_id INT REFERENCES sedes_cas(id),
    prioridad INT DEFAULT 1
);

-- 7. Configuración Global del Bot
CREATE TABLE IF NOT EXISTS configuracion_global (
    id SERIAL PRIMARY KEY,
    headless BOOLEAN DEFAULT FALSE,
    usar_proxy BOOLEAN DEFAULT FALSE,         -- Flag global de proxy
    url VARCHAR(255) DEFAULT 'https://ais.usvisa-info.com/es-mx/niv/users/sign_in',
    minutos_espera_ciclo INT DEFAULT 15,
    activar_telegram BOOLEAN DEFAULT TRUE,
    telegram_bot_token VARCHAR(255),
    telegram_admin_chat_id VARCHAR(100),      -- Chat privado del admin para errores
    busqueda_general_activa BOOLEAN DEFAULT FALSE,
    guardar_logs BOOLEAN DEFAULT TRUE,
    usar_sesiones_guardadas BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
