-- =============================================================================
-- PLANTILLAS DE INSERCIÓN: AGREGAR NUEVOS CLIENTES Y TRÁMITES
-- =============================================================================

-- PASO 1: Insertar un nuevo cliente (Retorna el id del cliente)
INSERT INTO clientes (nombre, telefono, telegram_chat_id, notas)
VALUES ('Familia Pérez Gómez', '524771234567', '-1002489123456', 'Trámite B1/B2 primera vez')
RETURNING id; -- Supongamos que retorna id = 1

-- PASO 2: Insertar la cuenta de acceso de la embajada asociada al cliente
INSERT INTO cuentas_embajada (cliente_id, correo, contrasena, usar_proxy, proxy_server, proxy_username, proxy_password)
VALUES (
    1,                                 -- 👈 ID del cliente del PASO 1
    'perez_familiar@gmail.com',
    'PasswordSeguro123$-',
    TRUE,                              -- usar_proxy para esta cuenta
    'http://gate.decodo.com:10001',
    'spz9c5osy8',
    'UfM2mslax_vKp349Di'
)
RETURNING id; -- Supongamos que retorna id = 1

-- PASO 3: Insertar el trámite (IVR) asociado a la cuenta
INSERT INTO tramites (
    cuenta_id, 
    ivr, 
    solicitante_principal, 
    estado_actual, 
    fecha_inicio, 
    fecha_tope, 
    dias_margen_traslado, 
    solo_consular
)
VALUES (
    1,                                 -- 👈 ID de la cuenta del PASO 2
    '77889900',                        -- IVR del grupo
    'Juan Pérez',
    'Programe la cita',                -- o 'Reprograme la cita'
    '2026-11-15',                      -- Fecha desde la que pueden viajar
    '2026-12-20',                      -- Fecha límite máxima
    5,                                 -- Días de margen entre CAS y Consulado
    FALSE                              -- FALSE si requiere CAS, TRUE si es solo consular
)
RETURNING id; -- Supongamos que retorna id = 1

-- PASO 4: Insertar las sedes deseadas para este trámite
-- Opción 1: Guadalajara
INSERT INTO tramite_opciones (tramite_id, consulado_id, cas_id, prioridad)
VALUES (
    1,                                 -- 👈 ID del trámite del PASO 3
    (SELECT id FROM sedes_consulares WHERE nombre = 'Guadalajara'),
    (SELECT id FROM sedes_cas WHERE nombre = 'Guadalajara ASC'),
    1
);

-- Opción 2: Monterrey (Segunda opción si no hay en Guadalajara)
INSERT INTO tramite_opciones (tramite_id, consulado_id, cas_id, prioridad)
VALUES (
    1,                                 -- 👈 ID del trámite del PASO 3
    (SELECT id FROM sedes_consulares WHERE nombre = 'Monterrey'),
    (SELECT id FROM sedes_cas WHERE nombre = 'Monterrey ASC'),
    2
);
