import json
import os

class TramiteConfig:
    def __init__(self, data: dict):
        self.db_id = data.get("db_id", None)
        self.cliente_id = data.get("cliente_id", None)
        self.cuenta_id = data.get("cuenta_id", None)
        self.nombre_solicitante = str(data.get("nombre_solicitante", ""))
        self.ivr = str(data.get("ivr", ""))
        self.estado_actual = data.get("estado_actual", "")
        self.fecha_inicio = data.get("fecha_inicio", "")
        self.fecha_tope = data.get("fecha_tope", "")
        self.dias_margen_traslado = int(data.get("dias_margen_traslado", 2))
        self.solo_consular = bool(data.get("solo_consular", False))
        self.opciones = data.get("opciones", [])
        
        # Validaciones de tramite
        campos_req = ["ivr", "estado_actual", "fecha_inicio", "fecha_tope", "opciones"]
        for c in campos_req:
            if not getattr(self, c, None) and c != "opciones":
                raise ValueError(f"Falta el campo requerido en el trámite: '{c}'")
        if not isinstance(self.opciones, list) or len(self.opciones) == 0:
            raise ValueError(f"El campo 'opciones' del trámite IVR {self.ivr} debe ser una lista con al menos una combinación.")

class CuentaConfig:
    def __init__(self, data: dict):
        self.cliente_id = data.get("cliente_id", None)
        self.correo = data.get("correo", "")
        self.contrasena = data.get("contrasena", "")
        # Soporte para telegram_chat_ids con retrocompatibilidad a numeros_whatsapp
        self.telegram_chat_ids = data.get("telegram_chat_ids", data.get("numeros_whatsapp", []))
        self.proxy = data.get("proxy", None)
        
        if not self.correo or not self.contrasena:
            raise ValueError("Las cuentas deben tener 'correo' y 'contrasena'.")
            
        tramites_data = data.get("tramites", [])
        if not isinstance(tramites_data, list) or len(tramites_data) == 0:
            raise ValueError(f"La cuenta {self.correo} debe tener al menos un trámite en la lista 'tramites'.")
            
        self.tramites = [TramiteConfig(t) for t in tramites_data]

class VisaConfig:
    def __init__(self, ruta_archivo: str = None, db = None, imprimir_log: bool = True):
        self.ruta_archivo = ruta_archivo
        self.db = db
        self.imprimir_log = imprimir_log
        self.datos = self._cargar_y_validar()
        
        self.headless = self.datos.get("headless", True)
        self.usar_proxy = self.datos.get("usar_proxy", True)
        self.url = self.datos.get("url", "")
        self.minutos_espera_ciclo = int(self.datos.get("minutos_espera_ciclo", 5))
        self.activar_telegram = self.datos.get("activar_telegram", self.datos.get("activar_whatsapp", False))
        self.telegram_bot_token = str(self.datos.get("telegram_bot_token", ""))
        self.telegram_admin_chat_id = str(self.datos.get("telegram_admin_chat_id", ""))
        self.busqueda_general_activa = self.datos.get("busqueda_general_activa", False)
        self.guardar_logs = self.datos.get("guardar_logs", False)
        self.usar_sesiones_guardadas = self.datos.get("usar_sesiones_guardadas", False)
        self.proxy_global = self.datos.get("proxy_global", None)
        
        cuentas_data = self.datos.get("cuentas", [])
        if not isinstance(cuentas_data, list) or len(cuentas_data) == 0:
            raise ValueError("El campo 'cuentas' debe ser una lista con al menos una cuenta configurada.")
            
        self.cuentas = [CuentaConfig(c) for c in cuentas_data]

    def _cargar_y_validar(self) -> dict:
        if self.db:
            return self.db.obtener_configuracion_desde_db(imprimir_log=self.imprimir_log)

        if not self.ruta_archivo or self.ruta_archivo == "--db":
            from .db import DatabaseManager
            self.db = DatabaseManager()
            return self.db.obtener_configuracion_desde_db(imprimir_log=self.imprimir_log)

        if not os.path.exists(self.ruta_archivo):
            raise FileNotFoundError(f"El archivo de configuración {self.ruta_archivo} no existe.")
            
        with open(self.ruta_archivo, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"El archivo JSON es inválido. Error: {e}")
