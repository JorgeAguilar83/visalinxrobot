-- =============================================================================
-- CONSULTAS ÚTILES Y OPERATIVAS: VISALINX
-- =============================================================================

-- 1. Consulta Maestra utilizada por el Bot para cargar trámites PENDIENTES
SELECT 
    c.id AS cliente_id,
    c.nombre AS cliente_nombre,
    c.telegram_chat_id,
    cta.id AS cuenta_id,
    cta.correo,
    cta.contrasena,
    cta.usar_proxy AS cuenta_usar_proxy,
    cta.proxy_server,
    cta.proxy_username,
    cta.proxy_password,
    t.id AS tramite_id,
    t.ivr,
    t.solicitante_principal,
    t.estado_actual,
    t.fecha_inicio,
    t.fecha_tope,
    t.dias_margen_traslado,
    t.solo_consular,
    sc.nombre AS consulado_nombre,
    scas.nombre AS cas_nombre,
    o.prioridad
FROM tramites t
JOIN cuentas_embajada cta ON t.cuenta_id = cta.id
JOIN clientes c ON cta.cliente_id = c.id
LEFT JOIN tramite_opciones o ON o.tramite_id = t.id
LEFT JOIN sedes_consulares sc ON o.consulado_id = sc.id
LEFT JOIN sedes_cas scas ON o.cas_id = scas.id
WHERE t.estado_proceso = 'PENDIENTE'
  AND c.activo = TRUE
  AND cta.activa = TRUE
  AND t.fecha_tope >= CURRENT_DATE
ORDER BY cta.id, t.id, o.prioridad ASC;

-- 2. Ver todas las citas agendadas con éxito por el Robot (Reporte de Logros)
SELECT 
    c.nombre AS cliente,
    c.telegram_chat_id AS grupo_telegram,
    cta.correo AS cuenta_login,
    t.ivr,
    t.consulado_agendado AS consulado,
    t.fecha_consular_agendada AS fecha_consulado,
    t.hora_consular_agendada AS hora_consulado,
    COALESCE(t.cas_agendado, 'N/A (Solo Consular)') AS cas,
    t.fecha_cas_agendada AS fecha_cas,
    t.hora_cas_agendada AS hora_cas,
    t.agendado_at AS fecha_agendamiento
FROM tramites t
JOIN cuentas_embajada cta ON t.cuenta_id = cta.id
JOIN clientes c ON cta.cliente_id = c.id
WHERE t.estado_proceso = 'AGENDADO'
ORDER BY t.agendado_at DESC;

-- 3. Resumen estadístico del sistema (Cuántos pendientes vs agendados)
SELECT 
    estado_proceso,
    COUNT(*) AS total_tramites
FROM tramites
GROUP BY estado_proceso;

-- 4. Ver configuración global del bot
SELECT * FROM configuracion_global LIMIT 1;

-- =============================================================================
-- 5. CONTROL Y GESTIÓN DE PROXIES (ACTIVAR / DESACTIVAR)
-- =============================================================================

-- 5.1. Consultar el estado actual de los proxies (Global y por Cuenta)
SELECT 
    'CONFIGURACIÓN GLOBAL' AS nivel,
    NULL AS correo_cuenta,
    usar_proxy AS proxy_activo,
    NULL AS servidor_proxy
FROM configuracion_global
UNION ALL
SELECT 
    'CUENTA' AS nivel,
    correo AS correo_cuenta,
    usar_proxy AS proxy_activo,
    proxy_server AS servidor_proxy
FROM cuentas_embajada;

-- 5.2. ACTIVAR PROXY GLOBALMENTE (El bot usará proxy en todas sus conexiones)
UPDATE configuracion_global 
SET usar_proxy = TRUE;

-- 5.3. DESACTIVAR PROXY GLOBALMENTE (El bot navegará con la IP local de tu internet)
UPDATE configuracion_global 
SET usar_proxy = FALSE;

-- 5.4. Activar proxy para una cuenta específica
UPDATE cuentas_embajada 
SET usar_proxy = TRUE 
WHERE correo = 'fam.cruz.sanchez1707@gmail.com';

-- 5.5. Desactivar proxy para una cuenta específica
UPDATE cuentas_embajada 
SET usar_proxy = FALSE 
WHERE correo = 'fam.cruz.sanchez1707@gmail.com';

-- 5.6. Cambiar o rotar el puerto/servidor del proxy de una cuenta
UPDATE cuentas_embajada 
SET usar_proxy = TRUE,
    proxy_server = 'http://gate.decodo.com:10002',
    proxy_username = 'spz9c5osy8',
    proxy_password = 'UfM2mslax_vKp349Di'
WHERE correo = 'fam.cruz.sanchez1707@gmail.com';

