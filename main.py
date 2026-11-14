import sys
import os
import time
from datetime import datetime
from visalinx_core.config import VisaConfig
from visalinx_core.notificador import TelegramNotifier
from visalinx_core.bot import VisaBot

class LoggerDiario(object):
    def __init__(self, activo=True):
        self.terminal = sys.stdout
        self.activo = activo
        self.fecha_actual = datetime.now().strftime("%Y-%m-%d")
        if self.activo:
            self.crear_archivo()

    def crear_archivo(self):
        if not os.path.exists("logs"):
            os.makedirs("logs")
        self.log = open(f"logs/visalinx_{self.fecha_actual}.log", "a", encoding="utf-8")

    def write(self, message):
        self.terminal.write(message)
        if self.activo:
            nueva_fecha = datetime.now().strftime("%Y-%m-%d")
            if nueva_fecha != self.fecha_actual:
                self.fecha_actual = nueva_fecha
                self.log.close()
                self.crear_archivo()
            self.log.write(message)
            self.log.flush()

    def flush(self):
        self.terminal.flush()
        if self.activo:
            self.log.flush()

def main():
    ruta_config = None
    db = None

    if len(sys.argv) > 1 and sys.argv[1] != "--db":
        ruta_config = sys.argv[1]
        print(f"📖 Modo Archivo JSON: Cargando configuración desde '{ruta_config}'...")
        try:
            config = VisaConfig(ruta_archivo=ruta_config)
        except Exception as e:
            print(f"Error al iniciar configuración desde JSON: {e}")
            sys.exit(1)
    else:
        print("🐘 Modo PostgreSQL: Conectando a la base de datos (db_visas)...")
        try:
            from visalinx_core.db import DatabaseManager
            db = DatabaseManager()
            config = VisaConfig(db=db, imprimir_log=False)
        except Exception as e:
            print(f"Error al iniciar configuración desde PostgreSQL: {e}")
            sys.exit(1)

    # Inyectamos el interceptor de logs en la consola del sistema
    sys.stdout = LoggerDiario(activo=config.guardar_logs)

    notificador = TelegramNotifier(
        bot_token=config.telegram_bot_token,
        admin_chat_id=config.telegram_admin_chat_id,
        activo=config.activar_telegram
    )
    bot = VisaBot(config, notificador, db=db)
    
    print("Iniciando el ciclo continuo del bot Multi-Cuenta y Multi-Trámite...")
    
    while True:
        ahora = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("\n==================================================")
        print(f"[{ahora}] INICIANDO NUEVO CICLO DE BÚSQUEDA...")

        # Si opera con PostgreSQL, refrescar los trámites pendientes en cada ciclo
        if db:
            try:
                config = VisaConfig(db=db, imprimir_log=True)
                bot.config = config
            except Exception as e_db:
                print(f"  [!] Alerta al refrescar desde PostgreSQL: {e_db}")
        
        todo_completado, hubo_agendamiento = bot.ejecutar_ciclo()
        
        ahora_fin = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ahora_fin}] CICLO FINALIZADO.")
        
        if todo_completado:
            print("✅ Todos los trámites de todas las cuentas han sido procesados con éxito. Finalizando script.")
            break 
            
        if hubo_agendamiento:
            print("\n⚡ [RE-DISPARO INTELIGENTE] Se agendó una cita con éxito en esta ronda.")
            print("Pausa táctica de 30 segundos con la sesión cerrada antes de continuar con los trámites restantes...")
            time.sleep(30)
        else:
            minutos = config.minutos_espera_ciclo
            print(f"Esperando {minutos} minutos con la sesión cerrada antes del próximo intento...")
            time.sleep(minutos * 60)

if __name__ == "__main__":
    main()
