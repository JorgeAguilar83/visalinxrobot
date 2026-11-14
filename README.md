# Documentación del Bot de Visas - VisaLinx (Arquitectura Modular POO Multi-Cuenta)

Este proyecto es un bot automatizado basado en **Playwright** para la programación inteligente de citas consulares y ASC en el sistema de visas de EE. UU.
Ha sido refactorizado para operar como un **Gestor Multi-Cuenta y Multi-Trámite**, capaz de procesar listas de clientes en distintas cuentas bajo un mismo ciclo continuo.

## 🏛️ Arquitectura del Sistema

El proyecto está dividido en un punto de entrada principal (`main.py`) y un paquete de núcleo de negocio (`visalinx_core`).

```text
VisaLinx/
├── config_ejemplo.json        # Archivo de contrato de datos JSON (Opcional/Respaldo).
├── main.py                    # Punto de entrada. Ejecuta el ciclo continuo (PostgreSQL o JSON).
├── migrar_json_a_postgres.py  # Script de migración de datos hacia PostgreSQL.
├── sql/                       # Sentencias SQL del sistema
│   ├── schema.sql             # Creación de tablas, catálogos e índices.
│   ├── consultas.sql          # Consultas útiles para reportes y auditoría.
│   └── inserciones.sql        # Plantillas para agregar nuevos clientes y trámites.
│
└── visalinx_core/             # Núcleo de Inteligencia
    ├── config.py              # Validador jerárquico (Adaptador dual: PostgreSQL o JSON).
    ├── db.py                  # Gestor de persistencia PostgreSQL y generación de JSON en memoria.
    ├── notificador.py         # Envío de alertas y evidencia visual por Telegram.
    ├── operaciones_web.py     # Interacción directa con el DOM (clics, validación estricta de IVR, navegación).
    └── bot.py                 # Cerebro orquestador: itera cuentas, itera trámites, y evalúa reglas lógicas.
```

## 🧠 Flujo de Negocio (Business Flow)

1. **Lectura y Validación:** `main.py` lee el JSON y `config.py` valida la jerarquía (Cuentas y sus respectivos Trámites).
2. **Ciclo de Iteración (Ronda de Búsqueda):**
   * El bot abre una única ventana del navegador.
   * Por cada **cuenta** en la lista:
     * Inicia sesión.
     * Por cada **trámite (IVR)** configurado en esa cuenta:
       * Localiza la tarjeta estrictamente verificando el `ivr` (ignora cualquier otra tarjeta).
       * Entra a la programación, busca fechas válidas para Consulado y ASC (considerando días de margen si están en ciudades diferentes).
       * Si agenda con éxito, notifica por Telegram con captura de pantalla oficial y descarta el trámite de los pendientes.
       * Si no encuentra fechas, regresa al Dashboard principal usando el botón "Regresar" para procesar el siguiente trámite.
     * Cierra la sesión de la cuenta actual.
3. **Espera Segura:** Una vez que iteró todas las cuentas, cierra el navegador y espera el tiempo global `minutos_espera_ciclo` con la sesión completamente cerrada antes de volver a empezar (esto evita bloqueos por inactividad o saturación).
4. **Finalización:** Si todos los trámites de todas las cuentas logran agendarse, el script termina exitosamente.

## ⚙️ Configuración (Contrato JSON)

La estructura ahora soporta múltiples cuentas y múltiples trámites. 

### Variables Globales
| Variable | Tipo | Descripción |
| :--- | :--- | :--- |
| `headless` | `Boolean` | Oculta el navegador si es `true`. |
| `url` | `String` | URL del portal. |
| `minutos_espera_ciclo` | `Integer` | Minutos de espera total (sesión cerrada) entre cada ronda de búsquedas. |
| `activar_telegram` | `Boolean` | Enciende o apaga el notificador de Telegram. |
| `telegram_bot_token` | `String` | Token del bot otorgado por @BotFather. |
| `telegram_admin_chat_id` | `String` | ID personal del administrador para recibir exclusivamente errores y alertas técnicas. |
| `proxy_global` | `Object` | (Opcional) Proxy por defecto para todas las cuentas. Formato: `{"server": "http://ip:port", "username": "", "password": ""}` |
| `solo_consular` | `Boolean` | **(A nivel de trámite)** Si es `true`, omite por completo la búsqueda y selección de cita del CAS. |

> [!TIP] Aislamiento de Red (Anti-Ban)
> Para evitar baneos de IPs, puedes asignar un objeto `"proxy"` específico dentro de cada objeto de cuenta en el arreglo `"cuentas"`. El bot cerrará el navegador y creará un nuevo contexto aislado para cada cuenta utilizando su proxy específico.

### Lista de consulados - entrevista
Ciudad Juarez
Guadalajara
Hermosillo
Matamoros
Merida
Mexico City
Monterrey
Nogales
Nuevo Laredo
Tijuana

### Lista de CAS (ASC) - toma de huellas
<select name="appointments[asc_appointment][facility_id]" id="appointments_asc_appointment_facility_id" class="required"><option value="" label=" "></option>
Ciudad Juarez ASC
Guadalajara ASC
Hermosillo ASC
Matamoros ASC
Merida ASC
Mexico City ASC
Monterrey ASC
Nogales ASC
Nuevo Laredo ASC
Tijuana ASC

### Ejemplo Completo (3 Cuentas, Múltiples IVRs)

Este es un ejemplo de un JSON con tres cuentas de correo diferentes. Observa que una cuenta tiene múltiples IVR (familias diferentes dentro del mismo login), mientras que otras tienen un solo trámite.

```json
{
    "headless": true,
    "url": "https://ais.usvisa-info.com/es-mx/niv/users/sign_in",
    "minutos_espera_ciclo": 5,
    "activar_telegram": true,
    "telegram_bot_token": "7123456789:AAFlkjw9823u4lkjsdf...",
    "telegram_admin_chat_id": "123456789",
    "proxy_global": {
        "server": "http://mi_proxy_global.com:8080"
    },
    "cuentas": [
        {
            "correo": "agencia_master@ejemplo.com",
            "contrasena": "Password123$-",
            "telegram_chat_ids": ["-1001234567890"],
            "tramites": [
                {
                    "ivr": "11111111",
                    "estado_actual": "Programe la cita",
                    "fecha_inicio": "2024-05-01",
                    "fecha_tope": "2024-07-31",
                    "dias_margen_traslado": 1,
                    "solo_consular": false,
                    "opciones": [
                        {"consulado": "Monterrey", "asc": "Monterrey"},
                        {"consulado": "Nuevo Laredo", "asc": "Nuevo Laredo"}
                    ]
                },
                {
                    "ivr": "22222222",
                    "estado_actual": "Reprograme la cita",
                    "fecha_inicio": "2024-08-01",
                    "fecha_tope": "2024-12-15",
                    "dias_margen_traslado": 2,
                    "solo_consular": true,
                    "opciones": [
                        {"consulado": "Guadalajara"}
                    ]
                }
            ]
        },
        {
            "correo": "familia_lopez@ejemplo.com",
            "contrasena": "LopezFam2024*",
            "telegram_chat_ids": ["-1005559876543"],
            "proxy": {
                "server": "socks5://proxy_privado.com:1080",
                "username": "usr_lopez",
                "password": "pwd_lopez"
            },
            "tramites": [
                {
                    "ivr": "33333333",
                    "estado_actual": "Programe la cita",
                    "fecha_inicio": "2024-10-01",
                    "fecha_tope": "2025-02-28",
                    "dias_margen_traslado": 0,
                    "opciones": [
                        {"consulado": "Mexico City", "asc": "Mexico City ASC"}
                    ]
                }
            ]
        },
        {
            "correo": "estudiante_viajero@ejemplo.com",
            "contrasena": "ViajeSeguro99!",
            "telegram_chat_ids": [],
            "tramites": [
                {
                    "ivr": "44444444",
                    "estado_actual": "Programe la cita",
                    "fecha_inicio": "2024-01-01",
                    "fecha_tope": "2024-03-31",
                    "dias_margen_traslado": 2,
                    "opciones": [
                        {"consulado": "Tijuana", "asc": "Tijuana"},
                        {"consulado": "Hermosillo", "asc": "Hermosillo"},
                        {"consulado": "Nogales", "asc": "Nogales"}
                    ]
                }
            ]
        }
    ]
}
```

## 🚀 ¿Cómo Ejecutarlo?

### 1. Ejecución en Servidor Dedicado 24/7 (Producción en Segundo Plano)

Esta es la forma estándar de correr el bot de manera ininterrumpida en tu servidor (ej. `192.168.1.50`):

> [!IMPORTANT]
> **Requisito Previo (Solo la primera vez):**
> Para que el túnel SSH pueda abrirse en segundo plano sin pedir contraseña por teclado, autoriza la llave del servidor en el VPS ejecutando una sola vez:
> ```bash
> ssh-copy-id root@191.101.0.80
> ```

**Comando de Ejecución 24/7:**
```bash
nohup env -u WAYLAND_DISPLAY -u XDG_SESSION_TYPE xvfb-run -a ./run_with_tunnel.sh > /dev/null 2>&1 &
```

**¿Qué hace este comando?**
* `nohup ... &`: Permite que el bot siga trabajando en segundo plano aunque cierres tu terminal o sesión SSH.
* `xvfb-run -a`: Crea una pantalla virtual (*X Virtual Framebuffer*) para que Playwright ejecute Chromium simulando un monitor real, evitando bloqueos y detección de bots anti-scraping en servidores sin pantalla.
* `./run_with_tunnel.sh`: Abre automáticamente el túnel SSH cifrado hacia el VPS (`191.101.0.80:5433` ➔ local `5435`) y arranca el bot con su entorno virtual `.venv`.

---

### 2. Ejecución Interactiva (Desarrollo o Pruebas en tu PC con Pantalla)

Si estás en tu computadora de escritorio y quieres ver o probar la ejecución:

```bash
# Iniciar automáticamente el túnel y lanzar el Robot:
./run_with_tunnel.sh

# Al terminar tus pruebas, para detener el túnel y liberar el puerto:
./stop_tunnel.sh
```

---

### 3. Modos Manuales Alternativos (Compatibilidad)

```bash
source .venv/bin/activate

# Modo PostgreSQL Directo:
python main.py

# Modo Archivo JSON tradicional (Respaldo sin BD):
python main.py config_ejemplo.json
```

---

## ⚙️ Configuración del Entorno (`.env`)

El bot lee automáticamente sus parámetros de conexión y seguridad desde el archivo `.env`:

```env
# Conexión a la base de datos (puerto 5435 para túnel VPS, o 5433 para docker local)
DATABASE_URL="postgresql://admin_visas:Vi123%23%24sas_132026@127.0.0.1:5435/db_visas"

DB_HOST=127.0.0.1
DB_PORT=5435
DB_NAME=db_visas
DB_USER=admin_visas
DB_PASSWORD="Vi123#$sas_132026"

# Clave simétrica para descifrado de credenciales AIS (idéntica a VisaLinx-Backend)
ENCRYPTION_SECRET_KEY=v1s4L1nx_S3cur1ty_M4st3r_K3y_2026!
```

> [!IMPORTANT]
> **Descifrado Criptográfico Automático:**  
> Las contraseñas de las cuentas de embajada registradas por las agencias se almacenan cifradas en la base de datos mediante **AES-256-GCM** (prefijo `ENC:gcm:`). El módulo [`visalinx_core/db.py`](./visalinx_core/db.py) utiliza la librería `cryptography` y la variable `ENCRYPTION_SECRET_KEY` para descifrar en memoria la contraseña real antes de iniciar sesión en el portal AIS.

---

## 📦 Supervisión y Monitoreo

### 1. Ver los Logs en Tiempo Real
```bash
tail -f logs/visalinx_$(date +%Y-%m-%d).log
```

### 2. Detener Procesos Huérfanos
```bash
pkill -f "python main.py"
```





