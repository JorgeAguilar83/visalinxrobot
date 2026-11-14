#!/usr/bin/env python3
"""
Script de migración: Vuelca los datos del archivo JSON actual (config_ejemplo.json)
a la base de datos PostgreSQL db_visas.
"""
import json
import os
import sys
import psycopg

def cargar_env():
    env_file = os.path.join(os.path.dirname(__file__), ".env")
    env_vars = {}
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    val = val.strip().strip('"').strip("'")
                    env_vars[key.strip()] = val
    return env_vars

def migrar(ruta_json="config_ejemplo.json"):
    if not os.path.exists(ruta_json):
        print(f"Error: No se encontró el archivo {ruta_json}")
        sys.exit(1)

    with open(ruta_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    env = cargar_env()
    conn_str = env.get("DATABASE_URL")
    if not conn_str:
        host = env.get("DB_HOST") or os.environ.get("DB_HOST")
        port = env.get("DB_PORT") or os.environ.get("DB_PORT")
        dbname = env.get("DB_NAME") or os.environ.get("DB_NAME")
        user = env.get("DB_USER") or os.environ.get("DB_USER")
        password = env.get("DB_PASSWORD") or os.environ.get("DB_PASSWORD")
        if host and port and dbname and user and password:
            conn_str = f"host={host} port={port} dbname={dbname} user={user} password={password}"
        else:
            raise ValueError(
                "Error: No se encontró la configuración de PostgreSQL. "
                "Defina DATABASE_URL o (DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD) en .env"
            )

    print(f"🚀 Iniciando migración de {ruta_json} hacia PostgreSQL...")

    with psycopg.connect(conn_str) as conn:
        with conn.cursor() as cur:
            # 1. Migrar Configuración Global
            cur.execute("DELETE FROM configuracion_global;")
            cur.execute("""
                INSERT INTO configuracion_global (
                    headless, usar_proxy, url, minutos_espera_ciclo,
                    activar_telegram, telegram_bot_token, telegram_admin_chat_id,
                    busqueda_general_activa, guardar_logs, usar_sesiones_guardadas
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id;
            """, (
                data.get("headless", False),
                data.get("usar_proxy", False),
                data.get("url", "https://ais.usvisa-info.com/es-mx/niv/users/sign_in"),
                int(data.get("minutos_espera_ciclo", 15)),
                data.get("activar_telegram", True),
                data.get("telegram_bot_token", ""),
                str(data.get("telegram_admin_chat_id", "")),
                data.get("busqueda_general_activa", False),
                data.get("guardar_logs", True),
                data.get("usar_sesiones_guardadas", False)
            ))
            print("  [✓] Configuración global migrada.")

            # 2. Migrar Cuentas y Trámites
            cuentas = data.get("cuentas", [])
            for cta in cuentas:
                correo = cta.get("correo", "")
                contrasena = cta.get("contrasena", "")
                chat_ids = cta.get("telegram_chat_ids", [])
                chat_id_unico = str(chat_ids[0]) if chat_ids else None
                
                # Nombre del cliente basado en el correo o nombre genérico
                nombre_cliente = correo.split("@")[0].replace(".", " ").title()
                if "Cruz" in correo or "cruz" in correo:
                    nombre_cliente = "Familia Cruz Sánchez"

                # Insertar o buscar cliente
                cur.execute("""
                    INSERT INTO clientes (nombre, telegram_chat_id, activo)
                    VALUES (%s, %s, TRUE)
                    RETURNING id;
                """, (nombre_cliente, chat_id_unico))
                cliente_id = cur.fetchone()[0]
                print(f"  [✓] Cliente '{nombre_cliente}' registrado (ID: {cliente_id}, Telegram Chat: {chat_id_unico}).")

                # Insertar cuenta de embajada
                proxy_data = cta.get("proxy", {}) or {}
                usar_proxy_cuenta = bool(proxy_data and proxy_data.get("server"))
                cur.execute("""
                    INSERT INTO cuentas_embajada (
                        cliente_id, correo, contrasena, usar_proxy,
                        proxy_server, proxy_username, proxy_password, activa
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, TRUE)
                    RETURNING id;
                """, (
                    cliente_id,
                    correo,
                    contrasena,
                    usar_proxy_cuenta,
                    proxy_data.get("server"),
                    proxy_data.get("username"),
                    proxy_data.get("password")
                ))
                cuenta_id = cur.fetchone()[0]
                print(f"  [✓] Cuenta '{correo}' registrada (ID: {cuenta_id}).")

                # Insertar trámites de esta cuenta
                for tra in cta.get("tramites", []):
                    ivr = str(tra.get("ivr", ""))
                    cur.execute("""
                        INSERT INTO tramites (
                            cuenta_id, ivr, estado_actual, fecha_inicio,
                            fecha_tope, dias_margen_traslado, solo_consular, estado_proceso
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'PENDIENTE')
                        RETURNING id;
                    """, (
                        cuenta_id,
                        ivr,
                        tra.get("estado_actual", "Programe la cita"),
                        tra.get("fecha_inicio"),
                        tra.get("fecha_tope"),
                        int(tra.get("dias_margen_traslado", 2)),
                        bool(tra.get("solo_consular", False))
                    ))
                    tramite_id = cur.fetchone()[0]
                    print(f"    [✓] Trámite IVR '{ivr}' registrado (ID: {tramite_id}).")

                    # Insertar opciones de sedes
                    for idx, op in enumerate(tra.get("opciones", []), start=1):
                        consulado_nombre = op.get("consulado")
                        asc_nombre = op.get("asc")

                        cur.execute("SELECT id FROM sedes_consulares WHERE nombre = %s;", (consulado_nombre,))
                        row_c = cur.fetchone()
                        consulado_id = row_c[0] if row_c else None

                        cas_id = None
                        if asc_nombre:
                            cur.execute("SELECT id FROM sedes_cas WHERE nombre = %s;", (asc_nombre,))
                            row_cas = cur.fetchone()
                            cas_id = row_cas[0] if row_cas else None

                        if consulado_id:
                            cur.execute("""
                                INSERT INTO tramite_opciones (tramite_id, consulado_id, cas_id, prioridad)
                                VALUES (%s, %s, %s, %s);
                            """, (tramite_id, consulado_id, cas_id, idx))
                            print(f"      [✓] Sede asignada: {consulado_nombre} / {asc_nombre or 'N/A'}")
                        else:
                            print(f"      [!] Alerta: No se encontró la sede consular '{consulado_nombre}' en catálogo.")

            conn.commit()

    print("\n✅ ¡Migración completada con éxito en PostgreSQL (db_visas)!")

if __name__ == "__main__":
    archivo = sys.argv[1] if len(sys.argv) > 1 else "config_ejemplo.json"
    migrar(archivo)
