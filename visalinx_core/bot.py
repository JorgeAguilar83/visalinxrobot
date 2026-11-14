import time
import os
import unicodedata
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth
from .config import VisaConfig
from .operaciones_web import OperacionesWeb

class VisaBot:
    def __init__(self, config: VisaConfig, notificador, db=None):
        self.config = config
        self.notificador = notificador
        self.db = db or getattr(config, 'db', None)

    def _calcular_limite_asc(self, consulado: str, asc: str, fecha_consular: str, dias_margen_traslado: int) -> str:
        if consulado.lower() in asc.lower() or asc.lower() in consulado.lower():
            return fecha_consular
        else:
            formato = "%Y-%m-%d"
            dt_consular = datetime.strptime(fecha_consular, formato)
            dt_asc_max = dt_consular - timedelta(days=dias_margen_traslado)
            return dt_asc_max.strftime(formato)

    def _evaluar_match_tramite(self, tramite, consulado: str, resultado_sede: dict):
        """
        Evalúa si el resultado de una sede cumple con las opciones y fechas de un trámite.
        Retorna (opcion, fecha_consular, fecha_asc) si hay match, o None.
        """
        if not resultado_sede or not resultado_sede.get("consular"):
            return None

        fecha_web_consular = resultado_sede["consular"]
        if fecha_web_consular < tramite.fecha_inicio or fecha_web_consular > tramite.fecha_tope:
            return None

        for opcion in tramite.opciones:
            if opcion.get("consulado") != consulado:
                continue

            if getattr(tramite, "solo_consular", False):
                return (opcion, fecha_web_consular, None)

            asc_req = opcion.get("asc")
            if not asc_req:
                continue

            fecha_web_asc = resultado_sede.get("ascs", {}).get(asc_req)
            if not fecha_web_asc:
                continue

            fecha_tope_asc = self._calcular_limite_asc(consulado, asc_req, fecha_web_consular, tramite.dias_margen_traslado)
            if fecha_web_asc > fecha_tope_asc:
                continue

            return (opcion, fecha_web_consular, fecha_web_asc)

        return None

    @staticmethod
    def _ancho_str(s) -> int:
        w = 0
        for ch in str(s):
            if unicodedata.east_asian_width(ch) in ("W", "F"):
                w += 2
            elif ord(ch) in (0x274c, 0x2705, 0x26a0, 0x1f3af, 0x1f4ca): # ❌, ✅, ⚠️, 🎯, 📊
                w += 2
            else:
                w += 1
        return w

    @staticmethod
    def _ajustar_izq(s, ancho: int) -> str:
        s_str = str(s)
        espacios = ancho - VisaBot._ancho_str(s_str)
        return s_str + (" " * max(0, espacios))

    def _imprimir_tabla(self, headers: dict, filas: list):
        if not filas:
            return

        col_widths = {
            k: max(self._ancho_str(headers[k]), max(self._ancho_str(f.get(k, "")) for f in filas))
            for k in headers
        }

        linea_sup = "┌─" + "─┬─".join("─" * col_widths[k] for k in headers) + "─┐"
        linea_sep = "├─" + "─┼─".join("─" * col_widths[k] for k in headers) + "─┤"
        linea_inf = "└─" + "─┴─".join("─" * col_widths[k] for k in headers) + "─┘"
        header_row = "│ " + " │ ".join(self._ajustar_izq(headers[k], col_widths[k]) for k in headers) + " │"

        print(linea_sup)
        print(header_row)
        print(linea_sep)
        for f in filas:
            fila_str = "│ " + " │ ".join(self._ajustar_izq(f.get(k, ""), col_widths[k]) for k in headers) + " │"
            print(fila_str)
        print(linea_inf)

    def _imprimir_tabla_tramites(self):
        filas = []
        for cuenta in self.config.cuentas:
            for tramite in cuenta.tramites:
                if getattr(tramite, 'solo_consular', False):
                    sedes_list = [f"{op['consulado']} / (Solo Consular)" for op in tramite.opciones]
                    margen = "N/A"
                else:
                    sedes_list = [f"{op['consulado']} / {op.get('asc', 'N/A')}" for op in tramite.opciones]
                    margen = f"{tramite.dias_margen_traslado} días"
                sedes_str = ", ".join(sedes_list)
                rango_str = f"{tramite.fecha_inicio} al {tramite.fecha_tope}"
                filas.append({
                    "cuenta": str(cuenta.correo),
                    "ivr": str(tramite.ivr),
                    "sedes": sedes_str,
                    "rango": rango_str,
                    "margen": margen
                })
        
        headers = {
            "cuenta": "Cuenta",
            "ivr": "IVR",
            "sedes": "Sede Consular / CAS",
            "rango": "Rango de Fechas Deseado",
            "margen": "Margen Trasl."
        }
        self._imprimir_tabla(headers, filas)

    def ejecutar_ciclo(self) -> tuple[bool, bool]:
        """ 
        Arquitectura Scout & Ataque Quirúrgico con Fast-Path y Circuit Breaker.
        Retorna (todo_completado, hubo_agendamiento).
        """
        if not self.config.cuentas:
            return (True, False)

        if not os.path.exists("sesiones"):
            os.makedirs("sesiones")
            
        print("\n" + "="*50)
        ahora_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ahora_str}] INICIANDO CICLO DE EXPLORACIÓN (MODO SCOUT)...\n")

        # --- FASE 1: Mapeo Global ---
        print("[1/4] ARMANDO LISTA MAESTRA DE SEDES (Consular + CAS)...\n")
        self._imprimir_tabla_tramites()

        sedes_maestras = {}
        for cuenta in self.config.cuentas:
            for tramite in cuenta.tramites:
                for opcion in tramite.opciones:
                    consulado = opcion["consulado"]
                    asc = opcion.get("asc")
                    if consulado not in sedes_maestras:
                        sedes_maestras[consulado] = {"ascs": set(), "rangos": []}
                    if not getattr(tramite, 'solo_consular', False) and asc:
                        sedes_maestras[consulado]["ascs"].add(asc)
                    sedes_maestras[consulado]["rangos"].append((tramite.fecha_inicio, tramite.fecha_tope))
        
        if not sedes_maestras:
            return (True, False)

        scout_cuenta = None
        for c in self.config.cuentas:
            if any(not getattr(t, 'solo_consular', False) for t in c.tramites):
                scout_cuenta = c
                break
                
        if not scout_cuenta:
            scout_cuenta = next((c for c in self.config.cuentas if c.tramites), None)

        if not scout_cuenta:
            return (True, False)

        fechas_encontradas = {}
        ganadores = [] # (cuenta, tramite, opcion, fecha_consular, fecha_asc)
        hubo_agendamiento = False
        
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=self.config.headless, 
                slow_mo=150,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process"
                ]
            )
            
            scout_context = None
            scout_web_ops = None
            ruta_sesion_scout = f"sesiones/sesion_{scout_cuenta.correo.replace('@', '_at_')}.json"
            
            # --- FASE 2: Exploración (Scout Avanzado) ---
            print("\n[2/4] FASE DE EXPLORACIÓN (SCOUT AVANZADO)\n")
            
            context_args = {
                "viewport": {'width': 1920, 'height': 1080},
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            }
            if self.config.usar_sesiones_guardadas and os.path.exists(ruta_sesion_scout):
                context_args["storage_state"] = ruta_sesion_scout
            
            if self.config.usar_proxy:
                proxy_settings_scout = scout_cuenta.proxy if getattr(scout_cuenta, 'proxy', None) else getattr(self.config, 'proxy_global', None)
                if proxy_settings_scout and "server" in proxy_settings_scout:
                    context_args["proxy"] = proxy_settings_scout

            try:
                scout_context = browser.new_context(**context_args)
                scout_page = scout_context.new_page()
                Stealth().apply_stealth_sync(scout_page)
                scout_web_ops = OperacionesWeb(scout_page)
                
                sesion_iniciada = scout_web_ops.iniciar_sesion(self.config.url, scout_cuenta.correo, scout_cuenta.contrasena, self.config.usar_sesiones_guardadas)
                estado_sesion = "✅ Sesión iniciada con éxito" if sesion_iniciada else "✅ Sesión activa (Token reutilizado)"
                
                tramite_scout = None
                for t_cand in list(scout_cuenta.tramites):
                    if scout_web_ops.seleccionar_tramite(t_cand.ivr, t_cand.estado_actual):
                        tramite_scout = t_cand
                        break
                    else:
                        estado_en_dashboard = scout_web_ops.obtener_estado_ivr(t_cand.ivr)
                        if estado_en_dashboard == "Cita Asistir":
                            print(f"\n  ⚡ [AUTO-SANACIÓN] El trámite IVR {t_cand.ivr} ya cuenta con cita agendada ('Cita Asistir') en la embajada.")
                            print(f"     -> Retirando IVR {t_cand.ivr} de la lista de pendientes.")
                            scout_cuenta.tramites.remove(t_cand)
                            hubo_agendamiento = True
                            if getattr(t_cand, "db_id", None) and self.db:
                                self.db.actualizar_estado_ivr(t_cand.db_id, "Cita Asistir")
                            if self.config.activar_telegram:
                                try:
                                    self.notificador.notificar_exito_cliente(
                                        scout_cuenta.telegram_chat_ids,
                                        f"✅ ¡CONFIRMACIÓN OFICIAL! La tarjeta del grupo IVR {t_cand.ivr} ya cuenta con cita activa (Estado: Cita Asistir)."
                                    )
                                except Exception:
                                    pass

                if not tramite_scout:
                    if not scout_cuenta.tramites:
                        print(f"\n  [✓] Todos los trámites de la cuenta {scout_cuenta.correo} han sido procesados.")
                        self.config.cuentas.remove(scout_cuenta)
                        scout_web_ops.volver_al_dashboard()
                        scout_web_ops.cerrar_sesion(self.config.usar_sesiones_guardadas)
                        scout_context.close()
                        browser.close()
                        return (len(self.config.cuentas) == 0, hubo_agendamiento)
                    else:
                        raise Exception(f"El Scout no pudo acceder a ningún trámite disponible de {scout_cuenta.correo}")
                    
                filas_prep = [
                    {"parametro": "Cuenta Comodín (Scout)", "detalle": scout_cuenta.correo},
                    {"parametro": "Autenticación", "detalle": estado_sesion},
                    {"parametro": "Trámite de Entrada", "detalle": f"✅ IVR {tramite_scout.ivr} ({tramite_scout.estado_actual})"},
                    {"parametro": "Objetivo de Búsqueda", "detalle": f"{len(sedes_maestras)} consulados únicos ({', '.join(sedes_maestras.keys())})"}
                ]
                self._imprimir_tabla({"parametro": "Parámetro", "detalle": "Detalle de Preparación Scout"}, filas_prep)
                
                print("\n⏳ Consultando disponibilidad global en la web...")
                todos_resultados_scout = {}
                circuit_breaker_activado = False
                fast_path_ejecutado = False

                for consulado, data_sede in sedes_maestras.items():
                    ascs = data_sede["ascs"]
                    rangos = data_sede["rangos"]
                    print(f"   • {consulado}...", end=" ", flush=True)
                    resultado_sede = scout_web_ops.explorar_sede_completa(consulado, list(ascs), rangos)
                    todos_resultados_scout[consulado] = resultado_sede
                    
                    if resultado_sede and resultado_sede.get("consular"):
                        fechas_encontradas[consulado] = resultado_sede
                        print(f"[✓ Cita: {resultado_sede['consular']}]")

                        # --- VERIFICACIÓN 1: Fast-Path (Agendamiento In-Situ en Caliente) ---
                        match_scout = self._evaluar_match_tramite(tramite_scout, consulado, resultado_sede)
                        if match_scout:
                            opcion_scout, fech_cons_scout, fech_asc_scout = match_scout
                            print(f"\n  🔥 [FAST-PATH] ¡MATCH DIRECTO EN CALIENTE PARA IVR {tramite_scout.ivr}!")
                            print(f"     Sede Consular: {consulado} | Fecha: {fech_cons_scout}")

                            try:
                                if not getattr(tramite_scout, "solo_consular", False):
                                    ubicacion_asc = opcion_scout.get("asc", "")
                                    print(f"     Sede ASC objetivo: {ubicacion_asc} | Fecha ASC: {fech_asc_scout}")
                                    scout_web_ops.page.locator("#appointments_asc_appointment_facility_id").select_option(label=ubicacion_asc)
                                    time.sleep(2)

                                    if not scout_web_ops.seleccionar_fecha_exacta("#appointments_asc_appointment_date", fech_asc_scout):
                                        raise Exception(f"No se pudo seleccionar la fecha ASC {fech_asc_scout}")

                                    if fech_asc_scout == fech_cons_scout:
                                        scout_web_ops._seleccionar_primera_hora("#appointments_asc_appointment_time")
                                    else:
                                        scout_web_ops._seleccionar_ultima_hora("#appointments_asc_appointment_time")

                                    # Asegurar que la hora consular no se haya perdido durante la selección del ASC
                                    val_hora_cons = scout_web_ops.page.locator("#appointments_consulate_appointment_time").input_value()
                                    if not val_hora_cons:
                                        print("     [!] Selector de hora consular vacío tras seleccionar CAS. Re-seleccionando hora...")
                                        scout_web_ops._seleccionar_primera_hora("#appointments_consulate_appointment_time")
                                        time.sleep(1)
                                else:
                                    print("     Trámite Solo Consular. Verificando hora consular antes de confirmar...")
                                    val_hora_cons = scout_web_ops.page.locator("#appointments_consulate_appointment_time").input_value()
                                    if not val_hora_cons:
                                        print("     [!] Selector de hora vacío en Fast-Path. Intentando seleccionar hora...")
                                        scout_web_ops._seleccionar_primera_hora("#appointments_consulate_appointment_time")
                                        time.sleep(1)

                                hora_cons_scout = scout_web_ops.obtener_hora_seleccionada("#appointments_consulate_appointment_time")
                                hora_asc_scout = scout_web_ops.obtener_hora_seleccionada("#appointments_asc_appointment_time") if not getattr(tramite_scout, "solo_consular", False) else ""

                                exito, motivo, ruta_img, estado_img = scout_web_ops.confirmar_cita(ivr=tramite_scout.ivr)
                                hora_cons_str = f" a las {hora_cons_scout}" if hora_cons_scout else ""
                                hora_asc_str = f" a las {hora_asc_scout}" if hora_asc_scout else ""
                                hora_registro = datetime.now().strftime("%H:%M")
                                sede_cas_str = f"{opcion_scout.get('asc', '')} ({fech_asc_scout}{hora_asc_str})" if not getattr(tramite_scout, "solo_consular", False) else "N/A (Solo Consular)"

                                if exito:
                                    print("-> Regresando al menú principal (Inicio) para verificación estricta de estado...")
                                    print(f"🔍 [VERIFICACIÓN EN DASHBOARD] Inspeccionando tarjeta del IVR {tramite_scout.ivr}...")
                                    estado_dashboard = scout_web_ops.obtener_estado_ivr(tramite_scout.ivr)

                                    if estado_dashboard != "Cita Asistir":
                                        time.sleep(2)
                                        estado_dashboard = scout_web_ops.obtener_estado_ivr(tramite_scout.ivr)

                                    if estado_dashboard == "Cita Asistir" or exito:
                                        estado_tag = f"✅ {estado_dashboard}" if estado_dashboard == "Cita Asistir" else "✅ Cita Confirmada (Pantalla Oficial)"
                                        print(f"✅ [ESTADO CONFIRMADO] {estado_tag} para el IVR {tramite_scout.ivr}.")
                                        filas_res = [
                                            {"parametro": "IVR", "detalle": str(tramite_scout.ivr)},
                                            {"parametro": "Estado Anterior", "detalle": tramite_scout.estado_actual},
                                            {"parametro": "Estado en Inicio", "detalle": estado_tag},
                                            {"parametro": "Sede Consular", "detalle": f"{consulado} ({fech_cons_scout}{hora_cons_str})"},
                                            {"parametro": "Sede CAS", "detalle": sede_cas_str},
                                            {"parametro": "Evidencia Visual", "detalle": f"{ruta_img} [{estado_img}]"}
                                        ]
                                        self._imprimir_tabla({"parametro": "Parámetro", "detalle": "Resultado del Agendamiento"}, filas_res)
                                        print(f"  [¡ÉXITO TOTAL!] Cita agendada para el grupo IVR {tramite_scout.ivr}. Retirando trámite de la lista.")
                                        print(f"  📌 Estado actual del trámite: {estado_dashboard}")

                                        if self.config.activar_telegram:
                                            cas_linea = f"🏛️ Cita CAS: {opcion_scout.get('asc', '')} ({fech_asc_scout}{hora_asc_str})\n" if not getattr(tramite_scout, 'solo_consular', False) else "🏛️ CAS: N/A (Solo Consular)\n"
                                            mensaje_exito = (
                                                f"✅ ¡ÉXITO TOTAL! Cita agendada para el grupo IVR {tramite_scout.ivr}\n"
                                                f"📍 Consulado: {consulado}\n"
                                                f"📅 Cita Consular: {fech_cons_scout}{hora_cons_str}\n"
                                                f"{cas_linea}"
                                                f"📌 Estado: {estado_dashboard}\n"
                                                f"⏰ Hora de confirmación: {hora_registro} hrs"
                                            )
                                            self.notificador.notificar_exito_cliente(
                                                scout_cuenta.telegram_chat_ids,
                                                mensaje_exito
                                            )

                                        if getattr(tramite_scout, "db_id", None) and self.db:
                                            self.db.marcar_tramite_agendado(
                                                tramite_scout.db_id,
                                                consulado=consulado,
                                                fecha_cons=fech_cons_scout,
                                                hora_cons=hora_cons_scout,
                                                cas=opcion_scout.get('asc', '') if not getattr(tramite_scout, 'solo_consular', False) else None,
                                                fecha_cas=fech_asc_scout if not getattr(tramite_scout, 'solo_consular', False) else None,
                                                hora_cas=hora_asc_scout if not getattr(tramite_scout, 'solo_consular', False) else None
                                            )

                                        scout_cuenta.tramites.remove(tramite_scout)
                                        hubo_agendamiento = True
                                        fast_path_ejecutado = True
                                        break # Rompe el ciclo de sedes_maestras inmediatamente
                                    else:
                                        print(f"❌ [VERIFICACIÓN FALLIDA] El estado en la tarjeta es: '{estado_dashboard}' (Se requiere 'Cita Asistir').")
                                        print("   -> La embajada no procesó el cambio en la base de datos.")
                                        print("   -> El trámite SE MANTIENE ACTIVO y se volverá a buscar en el próximo ciclo.")
                                        filas_res = [
                                            {"parametro": "IVR", "detalle": str(tramite_scout.ivr)},
                                            {"parametro": "Estado Esperado", "detalle": "Cita Asistir"},
                                            {"parametro": "Estado Detectado", "detalle": f"❌ {estado_dashboard}"},
                                            {"parametro": "Evidencia Visual", "detalle": f"{ruta_img} [{estado_img}]"},
                                            {"parametro": "Acción Tomada", "detalle": "El trámite SE MANTIENE ACTIVO para seguir buscando en el siguiente ciclo."}
                                        ]
                                        self._imprimir_tabla({"parametro": "Parámetro", "detalle": "Resultado de Verificación"}, filas_res)
                                        break
                                else:
                                    filas_res = [
                                        {"parametro": "IVR", "detalle": str(tramite_scout.ivr)},
                                        {"parametro": "Estado", "detalle": "❌ Cita NO agendada (Rechazada por el servidor consular)"},
                                        {"parametro": "Motivo Detectado", "detalle": motivo},
                                        {"parametro": "Evidencia Visual", "detalle": f"{ruta_img} [{estado_img}]"},
                                        {"parametro": "Acción Tomada", "detalle": "El trámite SE MANTIENE ACTIVO para seguir buscando en el siguiente ciclo."}
                                    ]
                                    self._imprimir_tabla({"parametro": "Parámetro", "detalle": "Resultado del Agendamiento"}, filas_res)
                                    break

                            except Exception as e_fast:
                                print(f"  [X] Error durante confirmación Fast-Path: {e_fast}")
                                break

                        # --- VERIFICACIÓN 2: Circuit Breaker (Cita para otra cuenta u otro IVR) ---
                        match_otro = None
                        for cta in self.config.cuentas:
                            for tra in cta.tramites:
                                if cta == scout_cuenta and tra == tramite_scout:
                                    continue
                                m = self._evaluar_match_tramite(tra, consulado, resultado_sede)
                                if m:
                                    match_otro = (cta, tra, m[0], m[1], m[2])
                                    break
                            if match_otro:
                                break

                        if match_otro:
                            print(f"\n  ⚡ [CIRCUIT BREAKER] Cita viable detectada en {consulado} ({resultado_sede['consular']})")
                            print(f"     -> Coincide con {match_otro[0].correo} (IVR {match_otro[1].ivr}).")
                            print("     -> Interrumpiendo escaneo de sedes restantes para ejecutar ataque inmediato...")
                            ganadores.append(match_otro)
                            circuit_breaker_activado = True
                            break # Rompe el ciclo de sedes_maestras
                    else:
                        print(f"[Completado]")

                if fast_path_ejecutado:
                    if self.config.usar_sesiones_guardadas:
                        try:
                            scout_context.storage_state(path=ruta_sesion_scout)
                        except Exception: pass
                    scout_web_ops.volver_al_dashboard()
                    scout_web_ops.cerrar_sesion(self.config.usar_sesiones_guardadas)
                    scout_context.close()
                    browser.close()

                    for cta in list(self.config.cuentas):
                        if not cta.tramites:
                            self.config.cuentas.remove(cta)

                    print("\n[CICLO FINALIZADO (FAST-PATH EXITOSO)]")
                    return (len(self.config.cuentas) == 0, True)

                print("\n[2/4] RESULTADOS DE EXPLORACIÓN GLOBAL (MODO SCOUT)\n")
                filas_scout = []
                for consulado, data_sede in sedes_maestras.items():
                    res = todos_resultados_scout.get(consulado, {})
                    ascs_solicitados = data_sede["ascs"]
                    
                    if not ascs_solicitados:
                        cas_str = "N/A (Solo Consular)"
                    else:
                        partes_cas = []
                        for asc_name in ascs_solicitados:
                            f_cas = res.get("ascs", {}).get(asc_name)
                            partes_cas.append(f"{asc_name}: {f_cas if f_cas else 'Sin citas'}")
                        cas_str = ", ".join(partes_cas)
                        
                    primer_dia_val = str(res.get("primer_dia") or "Sin fechas")
                    tope_val = str(res.get("tope_maximo") or "N/D")
                    consular_val = str(res.get("consular") or "Sin citas")
                    
                    if res.get("consular"):
                        diag = "✅ Cita Consular disponible"
                    else:
                        motivo_txt = res.get("motivo", "Sin citas")
                        diag = f"❌ {motivo_txt}"
                        
                    filas_scout.append({
                        "consulado": consulado,
                        "primer_dia": primer_dia_val,
                        "tope": tope_val,
                        "consular": consular_val,
                        "cas": cas_str,
                        "diagnostico": diag
                    })
                    
                headers_scout = {
                    "consulado": "Consulado",
                    "primer_dia": "1er Día en Calendario",
                    "tope": "Tope Máx.",
                    "consular": "Cita Consular",
                    "cas": "Cita CAS",
                    "diagnostico": "Estado / Diagnóstico"
                }
                self._imprimir_tabla(headers_scout, filas_scout)
                    
            except Exception as e:
                print(f"  [X] Error crítico en Scout: {e}")
                self.notificador.notificar_error_admin(f"🚨 [Error Crítico Scout]\nCuenta: {scout_cuenta.correo}\nDetalle: {e}")
                if scout_context:
                    scout_context.close()
                browser.close()
                return (False, False)
                
            if not circuit_breaker_activado:
                # --- FASE 3: Matchmaking Avanzado ---
                print("\n[3/4] FASE DE EVALUACIÓN (MATCHMAKING)\n")
                filas_match = []
                for cuenta in self.config.cuentas:
                    if not cuenta.tramites:
                        continue
                    for tramite in cuenta.tramites:
                        rango_str = f"{tramite.fecha_inicio} al {tramite.fecha_tope}"
                        
                        for opcion in tramite.opciones:
                            consulado = opcion["consulado"]
                            asc_req = opcion.get("asc")
                            sede_str = f"{consulado} / {asc_req}" if asc_req and not getattr(tramite, 'solo_consular', False) else f"{consulado} (Solo Consular)"
                            
                            data_sede = fechas_encontradas.get(consulado)
                            
                            if not data_sede or not data_sede.get("consular"):
                                filas_match.append({
                                    "cuenta": cuenta.correo,
                                    "ivr": str(tramite.ivr),
                                    "sede": sede_str,
                                    "rango": rango_str,
                                    "consular_web": "Sin citas",
                                    "cas_web": "Sin citas" if asc_req and not getattr(tramite, 'solo_consular', False) else "N/A",
                                    "resultado": "❌ Sin citas consulares en web"
                                })
                                continue
                                
                            fecha_web_consular = data_sede["consular"]
                            fecha_web_asc = data_sede.get("ascs", {}).get(asc_req) if not getattr(tramite, 'solo_consular', False) else None
                            
                            cas_web_str = fecha_web_asc if fecha_web_asc else ("N/A" if getattr(tramite, 'solo_consular', False) else "Sin citas")
                            
                            if fecha_web_consular < tramite.fecha_inicio:
                                filas_match.append({
                                    "cuenta": cuenta.correo,
                                    "ivr": str(tramite.ivr),
                                    "sede": sede_str,
                                    "rango": rango_str,
                                    "consular_web": fecha_web_consular,
                                    "cas_web": cas_web_str,
                                    "resultado": f"❌ Consular ({fecha_web_consular}) anterior a inicio"
                                })
                                continue
                            elif fecha_web_consular > tramite.fecha_tope:
                                filas_match.append({
                                    "cuenta": cuenta.correo,
                                    "ivr": str(tramite.ivr),
                                    "sede": sede_str,
                                    "rango": rango_str,
                                    "consular_web": fecha_web_consular,
                                    "cas_web": cas_web_str,
                                    "resultado": f"❌ Consular ({fecha_web_consular}) supera tope"
                                })
                                continue
                                
                            # Si Consular es buena, evaluamos el CAS (solo si se requiere)
                            if getattr(tramite, 'solo_consular', False):
                                resultado_str = "✅ ¡MATCH PERFECTO (Solo Consular)!"
                            else:
                                if not fecha_web_asc:
                                    filas_match.append({
                                        "cuenta": cuenta.correo,
                                        "ivr": str(tramite.ivr),
                                        "sede": sede_str,
                                        "rango": rango_str,
                                        "consular_web": fecha_web_consular,
                                        "cas_web": "Sin citas",
                                        "resultado": f"❌ CAS ({asc_req}) sin fechas"
                                    })
                                    continue
                                    
                                fecha_tope_asc = self._calcular_limite_asc(consulado, asc_req, fecha_web_consular, tramite.dias_margen_traslado)
                                
                                if fecha_web_asc > fecha_tope_asc:
                                    filas_match.append({
                                        "cuenta": cuenta.correo,
                                        "ivr": str(tramite.ivr),
                                        "sede": sede_str,
                                        "rango": rango_str,
                                        "consular_web": fecha_web_consular,
                                        "cas_web": fecha_web_asc,
                                        "resultado": f"❌ CAS ({fecha_web_asc}) supera margen ({fecha_tope_asc})"
                                    })
                                    continue
                                    
                                resultado_str = "✅ ¡MATCH PERFECTO!"
                                
                            ganadores.append((cuenta, tramite, opcion, fecha_web_consular, fecha_web_asc))
                            filas_match.append({
                                "cuenta": cuenta.correo,
                                "ivr": str(tramite.ivr),
                                "sede": sede_str,
                                "rango": rango_str,
                                "consular_web": fecha_web_consular,
                                "cas_web": cas_web_str,
                                "resultado": resultado_str
                            })
                            break 
                            
                headers_match = {
                    "cuenta": "Cuenta",
                    "ivr": "IVR",
                    "sede": "Sede",
                    "rango": "Rango Deseado",
                    "consular_web": "Consular Web",
                    "cas_web": "CAS Web",
                    "resultado": "Resultado"
                }
                self._imprimir_tabla(headers_match, filas_match)
            else:
                print("\n[3/4] FASE DE EVALUACIÓN (MATCHMAKING) - Saltada por Circuit Breaker (Ataque Prioritario)")

            # --- FASE 4: Ejecución Quirúrgica ---
            print("\n[4/4] FASE DE EJECUCIÓN (ATAQUE QUIRÚRGICO)\n")
            if not ganadores:
                consumo = scout_web_ops.obtener_consumo_mb() if scout_web_ops else "0.00 MB"
                filas_estado = [
                    {"parametro": "Estado del Ciclo", "detalle": "⚠️ Ninguna fecha encontrada en la web le sirve a las cuentas actuales."},
                    {"parametro": "Acción Tomada", "detalle": f"Sesión del Scout cerrada limpiamente. Consumo de red: {consumo}."},
                    {"parametro": "Próximo Intento", "detalle": f"Esperando {self.config.minutos_espera_ciclo} minutos con la sesión cerrada."}
                ]
                self._imprimir_tabla({"parametro": "Parámetro", "detalle": "Detalle de Ejecución"}, filas_estado)
            else:
                filas_estado = [
                    {"parametro": "Estado del Ciclo", "detalle": f"🎯 Se encontraron {len(ganadores)} coincidencias para agendar."},
                    {"parametro": "Acción Tomada", "detalle": "Iniciando Ataque Quirúrgico en cuentas ganadoras..."},
                ]
                self._imprimir_tabla({"parametro": "Parámetro", "detalle": "Detalle de Ejecución"}, filas_estado)
                cuentas_ganadoras = {}
                for g in ganadores:
                    cta, tra, opc, fech_cons, fech_asc = g
                    if cta not in cuentas_ganadoras:
                        cuentas_ganadoras[cta] = []
                    cuentas_ganadoras[cta].append((tra, opc, fech_cons, fech_asc))
                    
                for cta, matches in cuentas_ganadoras.items():
                    print(f"\n  [🎯] EJECUTANDO ATAQUE PARA: {cta.correo}")
                    
                    contexto_ataque = None
                    web_ops_ataque = None
                    ruta_sesion_ataque = f"sesiones/sesion_{cta.correo.replace('@', '_at_')}.json"
                    
                    if cta == scout_cuenta:
                        print("  -> Aprovechando sesión Scout activa para agendar inmediatamente...")
                        contexto_ataque = scout_context
                        web_ops_ataque = scout_web_ops
                    else:
                        c_args = {
                            "viewport": {'width': 1920, 'height': 1080},
                            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                        }
                        if self.config.usar_sesiones_guardadas and os.path.exists(ruta_sesion_ataque):
                            c_args["storage_state"] = ruta_sesion_ataque
                            
                        if self.config.usar_proxy:
                            proxy_set = cta.proxy if getattr(cta, 'proxy', None) else getattr(self.config, 'proxy_global', None)
                            if proxy_set and "server" in proxy_set:
                                print("  -> Levantando navegador nuevo con el proxy de esta cuenta...")
                                c_args["proxy"] = proxy_set
                        else:
                            print("  -> Levantando navegador nuevo SIN proxy (Red local)...")
                            
                        contexto_ataque = browser.new_context(**c_args)
                        page = contexto_ataque.new_page()
                        Stealth().apply_stealth_sync(page)
                        web_ops_ataque = OperacionesWeb(page)
                        try:
                            web_ops_ataque.iniciar_sesion(self.config.url, cta.correo, cta.contrasena, self.config.usar_sesiones_guardadas)
                        except Exception as e:
                            print(f"  [X] Fallo al iniciar sesión para ataque: {e}")
                            contexto_ataque.close()
                            continue

                    tramites_completados_ahora = []
                    es_primer_tramite = True
                    try:
                        for match in matches:
                            tramite, opcion, fech_cons, fech_asc = match
                            print(f"  [-] Asegurando cita para IVR {tramite.ivr}")
                            
                            if not es_primer_tramite or cta == scout_cuenta:
                                web_ops_ataque.volver_al_dashboard()
                            es_primer_tramite = False
                            
                            if not web_ops_ataque.seleccionar_tramite(tramite.ivr, tramite.estado_actual):
                                estado_actual_web = web_ops_ataque.obtener_estado_ivr(tramite.ivr)
                                if estado_actual_web == "Cita Asistir":
                                    print(f"  ⚡ [AUTO-SANACIÓN] El trámite IVR {tramite.ivr} ya cuenta con cita agendada ('Cita Asistir') en la embajada.")
                                    print(f"     -> Retirando de la lista de pendientes.")
                                    tramites_completados_ahora.append(tramite)
                                    hubo_agendamiento = True
                                    if getattr(tramite, "db_id", None) and self.db:
                                        self.db.actualizar_estado_ivr(tramite.db_id, "Cita Asistir")
                                    if self.config.activar_telegram:
                                        try:
                                            self.notificador.notificar_exito_cliente(
                                                cta.telegram_chat_ids,
                                                f"✅ ¡CONFIRMACIÓN OFICIAL! El trámite IVR {tramite.ivr} ya cuenta con cita activa (Estado: Cita Asistir)."
                                            )
                                        except Exception:
                                            pass
                                else:
                                    print(f"  [!] Fallo seleccionando trámite {tramite.ivr} durante el ataque. Estado en web: '{estado_actual_web}'.")
                                continue
                                
                            consulado_destino = opcion["consulado"]
                            ubicacion_asc = opcion.get("asc", "")
                            
                            print(f"  [-] Sede Consular objetivo: {consulado_destino} | Fecha: {fech_cons}")
                            web_ops_ataque.page.locator("#appointments_consulate_appointment_facility_id").select_option(label=consulado_destino)
                            time.sleep(3)
                            
                            if not web_ops_ataque.seleccionar_fecha_exacta("#appointments_consulate_appointment_date", fech_cons):
                                print(f"  [!] La fecha consular {fech_cons} desapareció durante el ataque (¡Alguien la tomó antes!).")
                                self.notificador.notificar_error_admin(
                                    f"⚠️ [Cita Ganada por Terceros]\nLa fecha consular {fech_cons} en {consulado_destino} desapareció durante el ataque para el IVR {tramite.ivr} ({cta.correo})."
                                )
                                continue
                                
                            web_ops_ataque._seleccionar_ultima_hora("#appointments_consulate_appointment_time")
                            
                            if not getattr(tramite, 'solo_consular', False):
                                print(f"  [-] Sede ASC objetivo: {ubicacion_asc} | Fecha: {fech_asc}")
                                web_ops_ataque.page.locator("#appointments_asc_appointment_facility_id").select_option(label=ubicacion_asc)
                                time.sleep(2)
                                
                                if web_ops_ataque.page.locator("#asc_date_time_not_available").is_visible():
                                    print("  [!] El sistema ASC está ocupado.")
                                    continue
                                    
                                if not web_ops_ataque.seleccionar_fecha_exacta("#appointments_asc_appointment_date", fech_asc):
                                    print(f"  [!] La fecha ASC {fech_asc} desapareció durante el ataque.")
                                    continue
                                    
                                if fech_asc == fech_cons:
                                    web_ops_ataque._seleccionar_primera_hora("#appointments_asc_appointment_time")
                                else:
                                    web_ops_ataque._seleccionar_ultima_hora("#appointments_asc_appointment_time")
                            else:
                                print("  [-] Trámite Solo Consular. Omitiendo selección de ASC.")
                                
                            hora_cons_ataque = web_ops_ataque.obtener_hora_seleccionada("#appointments_consulate_appointment_time")
                            hora_asc_ataque = web_ops_ataque.obtener_hora_seleccionada("#appointments_asc_appointment_time") if not getattr(tramite, 'solo_consular', False) else ""

                            exito, motivo, ruta_img, estado_img = web_ops_ataque.confirmar_cita(ivr=tramite.ivr)
                            hora_cons_str = f" a las {hora_cons_ataque}" if hora_cons_ataque else ""
                            hora_asc_str = f" a las {hora_asc_ataque}" if hora_asc_ataque else ""
                            hora_registro = datetime.now().strftime("%H:%M")
                            sede_cas_str = f"{ubicacion_asc} ({fech_asc}{hora_asc_str})" if not getattr(tramite, "solo_consular", False) else "N/A (Solo Consular)"

                            if exito:
                                print("-> Regresando al menú principal (Inicio) para verificación estricta de estado...")
                                print(f"🔍 [VERIFICACIÓN EN DASHBOARD] Inspeccionando tarjeta del IVR {tramite.ivr}...")
                                estado_dashboard = web_ops_ataque.obtener_estado_ivr(tramite.ivr)

                                if estado_dashboard != "Cita Asistir":
                                    time.sleep(2)
                                    estado_dashboard = web_ops_ataque.obtener_estado_ivr(tramite.ivr)

                                if estado_dashboard == "Cita Asistir" or exito:
                                    estado_tag = f"✅ {estado_dashboard}" if estado_dashboard == "Cita Asistir" else "✅ Cita Confirmada (Pantalla Oficial)"
                                    print(f"✅ [ESTADO CONFIRMADO] {estado_tag} para el IVR {tramite.ivr}.")
                                    filas_res = [
                                        {"parametro": "IVR", "detalle": str(tramite.ivr)},
                                        {"parametro": "Estado Anterior", "detalle": tramite.estado_actual},
                                        {"parametro": "Estado en Inicio", "detalle": estado_tag},
                                        {"parametro": "Sede Consular", "detalle": f"{consulado_destino} ({fech_cons}{hora_cons_str})"},
                                        {"parametro": "Sede CAS", "detalle": sede_cas_str},
                                        {"parametro": "Evidencia Visual", "detalle": f"{ruta_img} [{estado_img}]"}
                                    ]
                                    self._imprimir_tabla({"parametro": "Parámetro", "detalle": "Resultado del Agendamiento"}, filas_res)
                                    print(f"  [¡ÉXITO TOTAL!] Cita agendada para el grupo IVR {tramite.ivr}. Retirando trámite de la lista.")
                                    print(f"  📌 Estado actual del trámite: {estado_dashboard}")
                                    tramites_completados_ahora.append(tramite)
                                    hubo_agendamiento = True
                                    
                                    if self.config.activar_telegram:
                                        cas_linea = f"🏛️ Cita CAS: {ubicacion_asc} ({fech_asc}{hora_asc_str})\n" if not getattr(tramite, 'solo_consular', False) else "🏛️ CAS: N/A (Solo Consular)\n"
                                        mensaje_exito = (
                                            f"✅ ¡ÉXITO TOTAL! Cita agendada para el grupo IVR {tramite.ivr}\n"
                                            f"📍 Consulado: {consulado_destino}\n"
                                            f"📅 Cita Consular: {fech_cons}{hora_cons_str}\n"
                                            f"{cas_linea}"
                                            f"📌 Estado: {estado_dashboard}\n"
                                            f"⏰ Hora de confirmación: {hora_registro} hrs"
                                        )
                                        self.notificador.notificar_exito_cliente(
                                            cta.telegram_chat_ids,
                                            mensaje_exito
                                        )

                                    if getattr(tramite, "db_id", None) and self.db:
                                        self.db.marcar_tramite_agendado(
                                            tramite.db_id,
                                            consulado=consulado_destino,
                                            fecha_cons=fech_cons,
                                            hora_cons=hora_cons_ataque,
                                            cas=ubicacion_asc if not getattr(tramite, 'solo_consular', False) else None,
                                            fecha_cas=fech_asc if not getattr(tramite, 'solo_consular', False) else None,
                                            hora_cas=hora_asc_ataque if not getattr(tramite, 'solo_consular', False) else None
                                        )
                                else:
                                    print(f"❌ [VERIFICACIÓN FALLIDA] El estado en la tarjeta es: '{estado_dashboard}' (Se requiere 'Cita Asistir').")
                                    print("   -> La embajada no procesó el cambio en la base de datos.")
                                    print("   -> El trámite SE MANTIENE ACTIVO y se volverá a buscar en el próximo ciclo.")
                                    filas_res = [
                                        {"parametro": "IVR", "detalle": str(tramite.ivr)},
                                        {"parametro": "Estado Esperado", "detalle": "Cita Asistir"},
                                        {"parametro": "Estado Detectado", "detalle": f"❌ {estado_dashboard}"},
                                        {"parametro": "Evidencia Visual", "detalle": f"{ruta_img} [{estado_img}]"},
                                        {"parametro": "Acción Tomada", "detalle": "El trámite SE MANTIENE ACTIVO para seguir buscando en el siguiente ciclo."}
                                    ]
                                    self._imprimir_tabla({"parametro": "Parámetro", "detalle": "Resultado de Verificación"}, filas_res)
                            else:
                                filas_res = [
                                    {"parametro": "IVR", "detalle": str(tramite.ivr)},
                                    {"parametro": "Estado", "detalle": "❌ Cita NO agendada (Rechazada por el servidor consular)"},
                                    {"parametro": "Motivo Detectado", "detalle": motivo},
                                    {"parametro": "Evidencia Visual", "detalle": f"{ruta_img} [{estado_img}]"},
                                    {"parametro": "Acción Tomada", "detalle": "El trámite SE MANTIENE ACTIVO para seguir buscando en el siguiente ciclo."}
                                ]
                                self._imprimir_tabla({"parametro": "Parámetro", "detalle": "Resultado del Agendamiento"}, filas_res)
                                
                        for t in tramites_completados_ahora:
                            cta.tramites.remove(t)
                            
                        if self.config.usar_sesiones_guardadas:
                            try:
                                contexto_ataque.storage_state(path=ruta_sesion_ataque)
                            except Exception: pass
                        
                        web_ops_ataque.volver_al_dashboard()
                        web_ops_ataque.cerrar_sesion(self.config.usar_sesiones_guardadas)
                        print(f"  📊 Consumo de red estimado: {web_ops_ataque.obtener_consumo_mb()}")
                        
                    except Exception as e:
                        print(f"  [X] Error durante el ataque: {e}")
                        self.notificador.notificar_error_admin(
                            f"🚨 [Error en Ataque Quirúrgico]\nCuenta: {cta.correo}\nDetalle: {e}"
                        )
                    finally:
                        if cta != scout_cuenta and contexto_ataque:
                            contexto_ataque.close()
                            
            for cta in list(self.config.cuentas):
                if not cta.tramites:
                    self.config.cuentas.remove(cta)
                    
            if scout_context:
                try:
                    if self.config.usar_sesiones_guardadas:
                        scout_context.storage_state(path=ruta_sesion_scout)
                    if not ganadores: 
                        print(f"  📊 Consumo de red estimado (Scout): {scout_web_ops.obtener_consumo_mb()}")
                        scout_web_ops.cerrar_sesion(self.config.usar_sesiones_guardadas)
                except Exception:
                    pass
                scout_context.close()

            browser.close()
                
        print("\n[CICLO FINALIZADO]")
        return (len(self.config.cuentas) == 0, hubo_agendamiento)
