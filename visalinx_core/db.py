import os
import json
import base64
import hashlib
from datetime import date, datetime
import psycopg
from psycopg.rows import dict_row

def descifrar_credencial(val: str) -> str:
    """Descifra credenciales protegidas con AES-256-GCM o retorna texto plano legado."""
    if not val or not isinstance(val, str) or not val.startswith("ENC:gcm:"):
        return val
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        master_key = os.environ.get("ENCRYPTION_SECRET_KEY")
        if not master_key:
            env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
            if os.path.exists(env_file):
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            if k.strip() == "ENCRYPTION_SECRET_KEY":
                                master_key = v.strip().strip('"').strip("'")
                                break
        if not master_key:
            master_key = "v1s4L1nx_S3cur1ty_M4st3r_K3y_2026!"
        key_bytes = hashlib.sha256(master_key.encode("utf-8")).digest()
        raw = base64.b64decode(val[len("ENC:gcm:"):])
        iv = raw[:12]
        ciphertext = raw[12:]
        aesgcm = AESGCM(key_bytes)
        return aesgcm.decrypt(iv, ciphertext, None).decode("utf-8")
    except Exception:
        return val

class DatabaseManager:
    """
    Gestor de persistencia en PostgreSQL para VisaLinx.
    Extrae la configuración relacional y genera el diccionario JSON en memoria (Patrón Adaptador).
    """
    def __init__(self, conn_str: str = None):
        self.conn_str = conn_str or self._obtener_cadena_conexion()

    def _obtener_cadena_conexion(self) -> str:
        # 1. Intentar variable de entorno directa del sistema
        conn_env = os.environ.get("DATABASE_URL")
        if conn_env:
            return conn_env

        # 2. Leer archivo .env si existe
        env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
        env_vars = {}
        if os.path.exists(env_file):
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        env_vars[k.strip()] = v.strip().strip('"').strip("'")

        if "DATABASE_URL" in env_vars and env_vars["DATABASE_URL"]:
            return env_vars["DATABASE_URL"]

        # 3. Construir desde variables individuales si están definidas
        host = env_vars.get("DB_HOST") or os.environ.get("DB_HOST")
        port = env_vars.get("DB_PORT") or os.environ.get("DB_PORT")
        dbname = env_vars.get("DB_NAME") or os.environ.get("DB_NAME")
        user = env_vars.get("DB_USER") or os.environ.get("DB_USER")
        password = env_vars.get("DB_PASSWORD") or os.environ.get("DB_PASSWORD")

        if host and port and dbname and user and password:
            return f"host={host} port={port} dbname={dbname} user={user} password={password}"

        raise ValueError(
            "Error de configuración: No se encontró la cadena de conexión a PostgreSQL. "
            "Defina la variable DATABASE_URL o (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD) "
            "en el archivo .env o en las variables de entorno del sistema."
        )

    def obtener_configuracion_desde_db(self, imprimir_log: bool = True) -> dict:
        """
        Algoritmo de Extracción: Consulta las tablas relacionales y construye
        el diccionario de configuración idéntico a la estructura esperada por VisaConfig.
        """
        with psycopg.connect(self.conn_str, row_factory=dict_row) as conn:
            with conn.cursor() as cur:
                # 1. Obtener Configuración Global
                cur.execute("SELECT * FROM configuracion_global ORDER BY id DESC LIMIT 1;")
                glob = cur.fetchone()
                
                if not glob:
                    raise ValueError("No se encontró ningún registro en la tabla 'configuracion_global'.")

                config_dict = {
                    "headless": bool(glob.get("headless", False)),
                    "usar_proxy": bool(glob.get("usar_proxy", False)),
                    "url": glob.get("url", "https://ais.usvisa-info.com/es-mx/niv/users/sign_in"),
                    "minutos_espera_ciclo": int(glob.get("minutos_espera_ciclo", 15)),
                    "activar_telegram": bool(glob.get("activar_telegram", True)),
                    "telegram_bot_token": glob.get("telegram_bot_token") or "",
                    "telegram_admin_chat_id": str(glob.get("telegram_admin_chat_id") or ""),
                    "busqueda_general_activa": bool(glob.get("busqueda_general_activa", False)),
                    "guardar_logs": bool(glob.get("guardar_logs", True)),
                    "usar_sesiones_guardadas": bool(glob.get("usar_sesiones_guardadas", False)),
                    "cuentas": []
                }

                # 2. Consultar Clientes, Cuentas y Trámites PENDIENTES
                sql_pendientes = """
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
                """
                cur.execute(sql_pendientes)
                filas = cur.fetchall()

                # 3. Agrupación Jerárquica: Cuentas -> Trámites -> Opciones
                cuentas_map = {}
                tramites_map = {}

                for row in filas:
                    cta_id = row["cuenta_id"]
                    tra_id = row["tramite_id"]

                    if cta_id not in cuentas_map:
                        proxy_obj = None
                        if row["cuenta_usar_proxy"] and row["proxy_server"]:
                            proxy_obj = {
                                "server": row["proxy_server"],
                                "username": row["proxy_username"] or "",
                                "password": descifrar_credencial(row["proxy_password"]) if row["proxy_password"] else ""
                            }

                        chat_ids_list = [str(row["telegram_chat_id"])] if row["telegram_chat_id"] else []

                        cuentas_map[cta_id] = {
                            "correo": row["correo"],
                            "contrasena": descifrar_credencial(row["contrasena"]),
                            "telegram_chat_ids": chat_ids_list,
                            "proxy": proxy_obj,
                            "tramites": []
                        }
                        config_dict["cuentas"].append(cuentas_map[cta_id])

                    if tra_id not in tramites_map:
                        fecha_ini_str = row["fecha_inicio"].isoformat() if isinstance(row["fecha_inicio"], (date, datetime)) else str(row["fecha_inicio"])
                        fecha_top_str = row["fecha_tope"].isoformat() if isinstance(row["fecha_tope"], (date, datetime)) else str(row["fecha_tope"])

                        tramite_obj = {
                            "db_id": tra_id,
                            "ivr": str(row["ivr"]),
                            "estado_actual": row["estado_actual"],
                            "fecha_inicio": fecha_ini_str,
                            "fecha_tope": fecha_top_str,
                            "dias_margen_traslado": int(row["dias_margen_traslado"] or 2),
                            "solo_consular": bool(row["solo_consular"]),
                            "opciones": []
                        }
                        tramites_map[tra_id] = tramite_obj
                        cuentas_map[cta_id]["tramites"].append(tramite_obj)

                    if row["consulado_nombre"]:
                        opcion = {"consulado": row["consulado_nombre"]}
                        if not row["solo_consular"] and row["cas_nombre"]:
                            opcion["asc"] = row["cas_nombre"]
                        tramites_map[tra_id]["opciones"].append(opcion)

        # 4. Imprimir Log del JSON generado para comparación y auditoría
        if imprimir_log:
            json_preview = json.dumps(config_dict, indent=4, ensure_ascii=False)
            print("\n" + "="*60)
            print("📦 [POSTGRESQL -> ESTRUCTURA JSON GENERADA EXITOSAMENTE]")
            print("="*60)
            print(json_preview)
            print("="*60 + "\n")
            
            # Guardar copia de auditoría en logs
            if not os.path.exists("logs"):
                os.makedirs("logs")
            with open("logs/config_generada_db.json", "w", encoding="utf-8") as f_log:
                f_log.write(json_preview)

        return config_dict

    def marcar_tramite_agendado(self, tramite_db_id: int, consulado: str, fecha_cons: str, 
                                hora_cons: str = None, cas: str = None, fecha_cas: str = None, 
                                hora_cas: str = None):
        """
        Actualiza de forma atómica y persistente el trámite en PostgreSQL cuando la embajada
        ha confirmado la cita con éxito.
        """
        sql = """
            UPDATE tramites 
            SET estado_proceso = 'AGENDADO',
                consulado_agendado = %s,
                fecha_consular_agendada = %s,
                hora_consular_agendada = %s,
                cas_agendado = %s,
                fecha_cas_agendada = %s,
                hora_cas_agendada = %s,
                agendado_at = NOW(),
                updated_at = NOW()
            WHERE id = %s;
        """
        try:
            with psycopg.connect(self.conn_str) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (
                        consulado,
                        fecha_cons,
                        hora_cons,
                        cas,
                        fecha_cas,
                        hora_cas,
                        tramite_db_id
                    ))
                    conn.commit()
            print(f"  💾 [POSTGRESQL] Trámite ID {tramite_db_id} actualizado con éxito a 'AGENDADO'.")
        except Exception as e:
            print(f"  ❌ [POSTGRESQL ERROR] No se pudo actualizar el trámite {tramite_db_id} en la BD: {e}")

    def actualizar_estado_ivr(self, tramite_db_id: int, nuevo_estado: str):
        """
        Actualiza el estado de la tarjeta si la auto-sanación detecta un cambio.
        """
        sql = """
            UPDATE tramites 
            SET estado_actual = %s,
                estado_proceso = CASE WHEN %s = 'Cita Asistir' THEN 'AGENDADO' ELSE estado_proceso END,
                updated_at = NOW()
            WHERE id = %s;
        """
        try:
            with psycopg.connect(self.conn_str) as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (nuevo_estado, nuevo_estado, tramite_db_id))
                    conn.commit()
            print(f"  💾 [POSTGRESQL] Estado del trámite ID {tramite_db_id} actualizado a '{nuevo_estado}'.")
        except Exception as e:
            print(f"  ❌ [POSTGRESQL ERROR] No se pudo actualizar estado de trámite {tramite_db_id}: {e}")
