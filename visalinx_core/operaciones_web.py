import time
import os
from datetime import datetime, timedelta
from playwright.sync_api import Page

class OperacionesWeb:
    def __init__(self, page: Page):
        self.page = page
        self.page.set_default_timeout(60000)
        self.page.set_default_navigation_timeout(60000)
        
        # Telemetría de red
        self.bytes_descargados = 0
        self.page.on("response", self._contabilizar_datos)
        
        # Interceptor de red para ahorrar ancho de banda del proxy
        self.page.route("**/*", self._bloquear_recursos_pesados)

    def _contabilizar_datos(self, response):
        try:
            headers = response.headers
            if "content-length" in headers:
                self.bytes_descargados += int(headers["content-length"])
        except Exception:
            pass

    def obtener_consumo_mb(self) -> str:
        mb = self.bytes_descargados / (1024 * 1024)
        return f"{mb:.2f} MB"

    def _bloquear_recursos_pesados(self, route):
        url_peticion = route.request.url.lower()

        # Bloqueo por tipo de archivo
        if route.request.resource_type in ["image", "font", "media"]:
            route.abort()
            return

        # Lista negra de dominios de analíticas y telemetría
        dominios_basura = [
            "googletagmanager.com",
            "google-analytics.com",
            "newrelic.com",
            "nr-data.net",
            "trustwave.com",
            "digitalgov.gov"
        ]

        if any(dominio in url_peticion for dominio in dominios_basura):
            route.abort()
            return

        route.continue_()

    def iniciar_sesion(self, url: str, correo: str, contrasena: str, usar_sesiones: bool = False) -> bool:
        if usar_sesiones:
            url_base = url.replace("/users/sign_in", "")
            self.page.goto(url_base, timeout=90000)
            
            # Revisión rápida de mantenimiento
            texto_pagina = self.page.content().lower()
            if "mantenimiento" in texto_pagina or "maintenance" in texto_pagina or "down for" in texto_pagina:
                import os
                ahora_debug = datetime.now().strftime("%Y%m%d_%H%M%S")
                if not os.path.exists("logs"):
                    os.makedirs("logs")
                try:
                    self.page.screenshot(path=f"logs/debug_mantenimiento_{ahora_debug}.png", full_page=True)
                    with open(f"logs/debug_html_{ahora_debug}.html", "w", encoding="utf-8") as f:
                        f.write(self.page.content())
                except Exception as e:
                    print(f"No se pudo guardar telemetría visual: {e}")
                raise Exception("El sitio de la embajada se encuentra en MANTENIMIENTO (Se guardó captura en logs/).")

            try:
                if "/account" in self.page.url or "/groups" in self.page.url:
                    return False
                    
                sign_out_btn = self.page.locator("a[href*='sign_out']").first
                if sign_out_btn.is_visible(timeout=5000):
                    return False
            except Exception:
                pass

            if "sign_in" not in self.page.url:
                self.page.goto(url, timeout=60000)
        else:
            self.page.goto(url, timeout=90000)
            
            texto_pagina = self.page.content().lower()
            if "mantenimiento" in texto_pagina or "maintenance" in texto_pagina or "down for" in texto_pagina:
                import os
                ahora_debug = datetime.now().strftime("%Y%m%d_%H%M%S")
                if not os.path.exists("logs"):
                    os.makedirs("logs")
                try:
                    self.page.screenshot(path=f"logs/debug_mantenimiento_{ahora_debug}.png", full_page=True)
                    with open(f"logs/debug_html_{ahora_debug}.html", "w", encoding="utf-8") as f:
                        f.write(self.page.content())
                except Exception as e:
                    print(f"No se pudo guardar telemetría visual: {e}")
                raise Exception("El sitio de la embajada se encuentra en MANTENIMIENTO (Se guardó captura en logs/).")
            
        # Manejo inteligente de modales superpuestos (Ej: "You need to sign in...")
        try:
            boton_ok = self.page.locator("button", has_text="OK").first
            boton_ok.wait_for(state="visible", timeout=3000)
            boton_ok.click(force=True)
            time.sleep(0.5)
        except Exception:
            pass

        # Esperar por el input de correo (extendido por si hay captcha de Cloudflare)
        self.page.wait_for_selector("#user_email", timeout=60000)

        self.page.fill("#user_email", correo)
        self.page.fill("#user_password", contrasena)
        self.page.click(".icheckbox")
        self.page.click("input[type='submit']")
        self.page.wait_for_load_state("domcontentloaded", timeout=60000)
        
        return True

    def seleccionar_tramite(self, ivr: str, estado_actual: str) -> bool:
        # 1. Atrapamos la caja EXACTA del cliente (ignorando el estado para no engañar a Playwright)
        tarjetas_candidatas = self.page.locator("div").filter(has_text=str(ivr)).filter(has_text="Continuar")
        
        try:
            tarjetas_candidatas.last.wait_for(state="visible", timeout=15000)
        except Exception:
            print(f"  [X] No se encontró la tarjeta individual para el IVR {ivr} o tardó demasiado en cargar.")
            return False
            
        tarjeta_individual = tarjetas_candidatas.last
        texto_tarjeta = tarjeta_individual.inner_text()
        
        # 2. Aplicamos la REGLA DE ORO verificando el estado en el texto extraído
        if estado_actual in texto_tarjeta:
            tarjeta_individual.locator("text='Continuar'").first.click(force=True)
            self.page.wait_for_load_state("domcontentloaded")
            
            titulo_acordeon = self.page.locator("a.accordion-title").filter(has_text=estado_actual).first
            titulo_acordeon.click(force=True)
            time.sleep(2)
            
            # Clic en el botón azul interno
            boton_programar = self.page.locator("a.button").filter(has_text=estado_actual).first
            boton_programar.click(force=True)
            self.page.wait_for_load_state("domcontentloaded")
            
            return True
        else:
            # El estado cambió (ej. a "Cita Asistir"), abortamos con mensaje claro.
            print(f"  [X] El IVR {ivr} se encontró, pero su estado actual es distinto a '{estado_actual}'. Ignorando trámite.")
            return False

    def volver_al_dashboard(self):
        print("-> Regresando al menú principal (Inicio)...")
        try:
            # 1. Si ya estamos en /account (y no en /groups ni /schedule ni /instructions ni /appointment)
            url_actual = self.page.url.lower()
            if "/account" in url_actual and not any(x in url_actual for x in ["/schedule", "/groups", "/instructions", "/appointment"]):
                self.page.wait_for_load_state("domcontentloaded")
                return

            # 2. Cerrar modales residuales si existen para desbloquear la barra superior
            try:
                btn_no_gracias = self.page.locator("a:visible, button:visible").filter(has_text="No gracias").first
                if btn_no_gracias.is_visible(timeout=1000):
                    btn_no_gracias.click(force=True)
                    time.sleep(0.5)
                else:
                    btn_cerrar_modal = self.page.locator(".reveal-modal a.close-reveal-modal, .reveal a.close-button, button.close-button").first
                    if btn_cerrar_modal.is_visible(timeout=1000):
                        btn_cerrar_modal.click(force=True)
                        time.sleep(0.5)
                    else:
                        self.page.keyboard.press("Escape")
            except Exception:
                pass

            # 3. Intentar clic en el enlace 'Inicio' de la barra superior
            clic_completado = False
            try:
                boton_inicio = self.page.locator("a[href*='/account']:visible", has_text="Inicio").first
                if boton_inicio.is_visible(timeout=3000):
                    boton_inicio.click(force=True)
                    self.page.wait_for_url("**/account*", timeout=8000)
                    clic_completado = True
            except Exception:
                clic_completado = False

            # 4. Fallback robusto por URL directa si el clic no llevó a /account
            if not clic_completado or "/account" not in self.page.url:
                print("No se completó la transición con el botón 'Inicio', forzando navegación directa por URL...")
                if "/es-mx/niv/" in self.page.url:
                    url_base = self.page.url.split("/es-mx/niv/")[0] + "/es-mx/niv/account"
                else:
                    url_base = self.page.url.split("/groups")[0].split("/schedule")[0].split("/appointment")[0]
                    if not url_base.endswith("/account"):
                        url_base = url_base + "/account"
                self.page.goto(url_base, timeout=45000)

            self.page.wait_for_load_state("domcontentloaded", timeout=30000)
            time.sleep(1)  # Breve pausa para estabilizar renderizado de tarjetas
        except Exception as e:
            if "ERR_ABORTED" in str(e) or "chrome-error" in str(e):
                print(" -> [Proxy] Conexión abortada al intentar volver al dashboard. Ignorando...")
            else:
                print(f"Error al intentar volver al dashboard: {e}")

    def obtener_estado_ivr(self, ivr: str) -> str:
        """
        Navega al menú principal (Inicio/Dashboard) y consulta el estado actual de la tarjeta del IVR.
        Localiza la tarjeta del trámite (excluyendo pie de página) y evalúa su estado actual.
        """
        self.volver_al_dashboard()
        
        # 1. Prioridad: Tarjetas del trámite que contienen el IVR y el botón 'Continuar' (patrón probado)
        tarjetas_candidatas = self.page.locator("div").filter(has_text=str(ivr)).filter(has_text="Continuar")
        
        # 2. Si no hay con 'Continuar', buscar contenedores con el IVR excluyendo el bloque de pie de página
        if tarjetas_candidatas.count() == 0:
            tarjetas_candidatas = self.page.locator("div").filter(has_text=str(ivr)).filter(has_not_text="Cuenta de usuario:")
            
        try:
            tarjetas_candidatas.last.wait_for(state="visible", timeout=12000)
        except Exception:
            print(f"  [X] No se pudo encontrar la tarjeta del IVR {ivr} en Inicio.")
            return "No encontrada"

        tarjeta_individual = tarjetas_candidatas.last
        texto_tarjeta = tarjeta_individual.inner_text()

        # Si el texto es muy corto (solo la etiqueta del IVR), expandir al elemento padre
        lineas = [l.strip() for l in texto_tarjeta.split("\n") if l.strip()]
        if len(lineas) <= 2 and str(ivr) in texto_tarjeta:
            try:
                padre = tarjeta_individual.locator("xpath=..")
                if padre.count() > 0:
                    texto_padre = padre.inner_text()
                    if any(k in texto_padre.lower() for k in ["cita", "asistir", "programe", "reprograme", "continuar"]):
                        texto_tarjeta = texto_padre
            except Exception:
                pass

        # Detección y normalización de estado
        texto_lower = texto_tarjeta.lower()
        if "cita asistir" in texto_lower or "cita para asistir" in texto_lower or "asistir" in texto_lower:
            return "Cita Asistir"
        elif "programe la cita" in texto_lower or "programar cita" in texto_lower:
            return "Programe la cita"
        elif "reprograme la cita" in texto_lower or "reprogramar cita" in texto_lower:
            return "Reprograme la cita"
        else:
            for linea in texto_tarjeta.split("\n"):
                linea_clean = linea.strip()
                if any(k in linea_clean.lower() for k in ["cita", "asistir", "programe"]):
                    return linea_clean
            return texto_tarjeta.split("\n")[0].strip() or "Desconocido"

    def cerrar_sesion(self, usar_sesiones: bool = False):
        print("-> Gestionando el cierre de sesión de la cuenta actual...")
        if usar_sesiones:
            print("  [✓] Cierre de sesión web omitido para preservar el token vivo en el servidor.")
        else:
            print("  [+] Haciendo clic en el botón 'Sign Out' para liberar la cuenta limpiamente...")
            try:
                # Para evitar problemas con menús ocultos, extraemos el enlace y navegamos directamente
                sign_out_btn = self.page.locator("a[href*='sign_out']").first
                href = sign_out_btn.get_attribute("href", timeout=3000)
                if href:
                    url_salida = f"https://ais.usvisa-info.com{href}"
                    self.page.goto(url_salida, timeout=10000)
                    time.sleep(2)
                    print("  [✓] Sesión cerrada correctamente en los servidores de la embajada.")
                else:
                    print("  [!] Enlace 'Sign Out' no encontrado. (Quizás la sesión ya había expirado).")
            except Exception as e:
                print(f"  [X] Detalle al intentar hacer clic en Sign Out: {e}")

    def _seleccionar_ultima_hora(self, locator_id: str) -> str:
        dropdown = self.page.locator(locator_id)
        try:
            dropdown.locator("option:nth-child(2)").wait_for(state="attached", timeout=15000)
        except Exception:
            raise Exception("No cargaron los horarios disponibles en el selector.")
        opciones = dropdown.locator("option").all()
        if len(opciones) > 1:
            ultimo_valor = opciones[-1].get_attribute("value")
            dropdown.select_option(value=ultimo_valor)
            texto = opciones[-1].inner_text().strip()
            return texto if texto else (ultimo_valor or "")
        return ""

    def _seleccionar_primera_hora(self, locator_id: str) -> str:
        dropdown = self.page.locator(locator_id)
        try:
            dropdown.locator("option:nth-child(2)").wait_for(state="attached", timeout=6000)
        except Exception:
            raise Exception("No cargaron los horarios disponibles en el selector.")
        opciones = dropdown.locator("option").all()
        for op in opciones[1:]:
            val = op.get_attribute("value")
            if val:
                dropdown.select_option(value=val)
                texto = op.inner_text().strip()
                return texto if texto else val
        raise Exception("El selector no tiene opciones de horario válidas.")

    def obtener_hora_seleccionada(self, locator_id: str) -> str:
        try:
            val = self.page.locator(f"{locator_id} option:checked").inner_text().strip()
            if not val or val == " ":
                val = self.page.locator(locator_id).input_value().strip()
            return val
        except Exception:
            try:
                return self.page.locator(locator_id).input_value().strip()
            except Exception:
                return ""

    def seleccionar_fecha_exacta(self, id_calendario: str, fecha_objetivo: str) -> bool:
        """ Navega directamente a una fecha previamente conocida y la selecciona (Modo Francotirador). """
        # Forzar reseteo de la memoria del calendario
        try:
            self.page.evaluate(f"jQuery('{id_calendario}').datepicker('setDate', new Date());")
            self.page.evaluate(f"jQuery('{id_calendario}').datepicker('setDate', null);")
        except Exception:
            pass
            
        try:
            self.page.locator(id_calendario).click(timeout=15000)
        except Exception:
            print(" -> El calendario no apareció a tiempo.")
            return False
            
        time.sleep(1)
        
        target_year = int(fecha_objetivo.split("-")[0])
        target_month = int(fecha_objetivo.split("-")[1])
        
        for _ in range(24): # Límite de seguridad
            mes_actual_info = self.page.evaluate("""
                () => {
                    let yearStr = document.querySelector('.ui-datepicker-year');
                    let monthStr = document.querySelector('.ui-datepicker-month');
                    if (!yearStr || !monthStr) return null;
                    
                    let year = parseInt(yearStr.textContent);
                    let monthName = monthStr.textContent.trim().toLowerCase();
                    let monthMap = {
                        'january': 1, 'february': 2, 'march': 3, 'april': 4, 'may': 5, 'june': 6,
                        'july': 7, 'august': 8, 'september': 9, 'october': 10, 'november': 11, 'december': 12,
                        'enero': 1, 'febrero': 2, 'marzo': 3, 'abril': 4, 'mayo': 5, 'junio': 6,
                        'julio': 7, 'agosto': 8, 'septiembre': 9, 'octubre': 10, 'noviembre': 11, 'diciembre': 12
                    };
                    return { year: year, month: monthMap[monthName] || 1 };
                }
            """)
            
            if not mes_actual_info:
                print("No se pudo leer el título del calendario.")
                self.page.keyboard.press("Escape")
                return False
                
            current_val = mes_actual_info['year'] * 12 + mes_actual_info['month']
            target_val = target_year * 12 + target_month
            
            if current_val > target_val:
                prev_btn = self.page.locator("a.ui-datepicker-prev")
                if prev_btn.is_visible():
                    prev_btn.click()
                    time.sleep(0.5)
                else:
                    self.page.keyboard.press("Escape")
                    return False
            elif current_val < target_val:
                next_btn = self.page.locator("a.ui-datepicker-next")
                if next_btn.is_visible():
                    next_btn.click()
                    time.sleep(0.5)
                else:
                    self.page.keyboard.press("Escape")
                    return False
            else:
                break
                
        # Clic exacto en el día
        script_click = f"""
        () => {{
            let target = Array.from(document.querySelectorAll('.ui-datepicker-calendar td[data-handler="selectDay"] a.ui-state-default')).find(a => {{
                let td = a.parentElement;
                let year = td.getAttribute('data-year');
                let month = parseInt(td.getAttribute('data-month')) + 1;
                let day = a.textContent.trim();
                let dateStr = year + "-" + month.toString().padStart(2, '0') + "-" + day.padStart(2, '0');
                return dateStr === '{fecha_objetivo}';
            }});
            if(target) {{
                target.click();
                return true;
            }}
            return false;
        }}
        """
        encontrado = self.page.evaluate(script_click)
        time.sleep(1)
        
        # Cerramos calendario por si acaso el click no lo cerró
        self.page.keyboard.press("Escape")
        time.sleep(1)
        
        if not encontrado:
            print(f"La fecha {fecha_objetivo} ya no está disponible en la pantalla del calendario.")
            return False
            
        fecha_input = self.page.locator(id_calendario).input_value()
        return fecha_input != ""

    def buscar_fecha_consular(self, consulado: str, fecha_inicio: str, fecha_tope: str, limite_meses: int = 12) -> str:
        print(f"5. Seleccionando el consulado: {consulado}...")
        self.page.locator("#appointments_consulate_appointment_facility_id").select_option(label=consulado)
        time.sleep(3) 

        print("6. Buscando y seleccionando la fecha consular válida...")
        try:
            self.page.locator("#appointments_consulate_appointment_date").click(timeout=15000)
        except Exception:
            print(" -> El calendario Consular no apareció a tiempo (Bloqueo, sin citas o proxy muy lento).")
            return None
        time.sleep(1)
        
        meses_buscados = 0
        fecha_encontrada = None
        
        while True:
            if meses_buscados >= limite_meses:
                print(f"No se encontraron fechas Consulares en los próximos {limite_meses} meses.")
                break 

            dias_disponibles = self.page.locator(".ui-datepicker-calendar a.ui-state-default")
            cantidad_dias = dias_disponibles.count()
            
            if cantidad_dias > 0:
                print(f"Evaluando {cantidad_dias} días disponibles en este mes...")
                fecha_actual = ""
                for i in range(cantidad_dias):
                    dias_disponibles = self.page.locator(".ui-datepicker-calendar a.ui-state-default")
                    dias_disponibles.nth(i).click()
                    time.sleep(1)
                    fecha_actual = self.page.locator("#appointments_consulate_appointment_date").input_value()
                    
                    if fecha_actual < fecha_inicio:
                        print(f"Día ignorado ({fecha_actual}): Anterior a fecha de inicio ({fecha_inicio}).")
                        self.page.locator("#appointments_consulate_appointment_date").click()
                        time.sleep(0.5)
                        continue
                    elif fecha_inicio <= fecha_actual <= fecha_tope:
                        print(f"¡Cita Consular válida encontrada! Fecha: {fecha_actual}")
                        fecha_encontrada = fecha_actual
                        break
                    else:
                        print(f"Día superó tu fecha tope ({fecha_actual} > {fecha_tope}).")
                        break
                
                if fecha_encontrada:
                    break
                elif fecha_actual and fecha_actual > fecha_tope:
                    break
                    
            boton_siguiente = self.page.locator("a.ui-datepicker-next")
            if boton_siguiente.is_visible():
                boton_siguiente.click()
                meses_buscados += 1
                time.sleep(0.5) 
            else:
                break
        
        # Limpieza de interfaz: Asegurarse de cerrar el calendario para no estorbar a la siguiente iteración
        self.page.keyboard.press("Escape")
        time.sleep(1)
        
        if fecha_encontrada:
            time.sleep(3)
            print("7. Seleccionando la última hora disponible Consular...")
            self._seleccionar_ultima_hora("#appointments_consulate_appointment_time")
            print("¡Hora Consular ingresada con éxito!")
            
        return fecha_encontrada

    def buscar_fecha_asc(self, asc: str, fecha_inicio: str, fecha_tope_asc: str, fecha_consular_agendada: str, limite_meses: int = 12) -> str:
        print(f"8. Seleccionando la ubicación ASC: {asc}...")
        self.page.locator("#appointments_asc_appointment_facility_id").select_option(label=asc)
        time.sleep(2)
        
        if self.page.locator("#asc_date_time_not_available").is_visible():
            print("El sistema ASC está ocupado.")
            return None
            
        print("9. Buscando la fecha ASC ÓPTIMA (más cercana al margen de traslado)...")
        # Forzar el reseteo de la memoria interna del calendario ASC
        try:
            self.page.evaluate("jQuery('#appointments_asc_appointment_date').datepicker('setDate', new Date());")
            self.page.evaluate("jQuery('#appointments_asc_appointment_date').datepicker('setDate', null);")
        except Exception:
            pass

        try:
            self.page.locator("#appointments_asc_appointment_date").click(timeout=15000)
        except Exception:
            print(" -> El calendario ASC no apareció a tiempo o el proxy es muy lento.")
            return None
        time.sleep(1)
        
        meses_buscados = 0
        mejor_fecha = None
        
        script_extraccion = """
        () => {
            let dates = [];
            document.querySelectorAll('.ui-datepicker-calendar td[data-handler="selectDay"] a.ui-state-default').forEach(a => {
                let td = a.parentElement;
                let year = td.getAttribute('data-year');
                let month = parseInt(td.getAttribute('data-month')) + 1;
                let day = a.textContent.trim();
                let dateStr = year + "-" + month.toString().padStart(2, '0') + "-" + day.padStart(2, '0');
                dates.push(dateStr);
            });
            return dates;
        }
        """

        tope_year = int(fecha_tope_asc.split("-")[0])
        tope_month = int(fecha_tope_asc.split("-")[1])

        while meses_buscados < limite_meses:
            # Revisar el mes actual para no avanzar hacia el futuro infinitamente
            mes_actual_info = self.page.evaluate("""
                () => {
                    let td = document.querySelector('.ui-datepicker-calendar td');
                    if(!td) return null;
                    return { year: parseInt(td.getAttribute('data-year')), month: parseInt(td.getAttribute('data-month')) + 1 };
                }
            """)
            if mes_actual_info:
                if (mes_actual_info['year'] * 12 + mes_actual_info['month']) > (tope_year * 12 + tope_month):
                    break # Detener si ya estamos en un mes que supera el tope

            dias_disponibles = self.page.locator(".ui-datepicker-calendar a.ui-state-default")
            
            if dias_disponibles.count() > 0:
                dias_en_pantalla = self.page.evaluate(script_extraccion)
                
                if dias_en_pantalla:
                    # Filtramos todas las fechas que estén dentro del límite superior (sin importar qué tan atrás)
                    validos = [d for d in dias_en_pantalla if d <= fecha_tope_asc]
                    
                    if validos:
                        candidato = max(validos) # Seleccionamos la fecha más cercana al tope
                        if not mejor_fecha or candidato > mejor_fecha:
                            mejor_fecha = candidato
                            
                    # Si el último día mostrado en pantalla ya superó el tope, 
                    # no tiene sentido seguir buscando en los siguientes meses.
                    if dias_en_pantalla[-1] >= fecha_tope_asc:
                        break

            boton_siguiente = self.page.locator("a.ui-datepicker-next")
            if boton_siguiente.is_visible():
                boton_siguiente.click()
                meses_buscados += 1
                time.sleep(0.5)
            else:
                break

        if mejor_fecha:
            print(f"¡Cita ASC ideal encontrada (más cercana al límite {fecha_tope_asc})! Fecha: {mejor_fecha}")
            
            # Navegar de vuelta al mes correspondiente si nos pasamos explorando
            while True:
                mes_actual_info = self.page.evaluate("""
                    () => {
                        let td = document.querySelector('.ui-datepicker-calendar td[data-month]');
                        if(!td) return null;
                        return { year: parseInt(td.getAttribute('data-year')), month: parseInt(td.getAttribute('data-month')) + 1 };
                    }
                """)
                if not mes_actual_info: 
                    break
                    
                target_year = int(mejor_fecha.split("-")[0])
                target_month = int(mejor_fecha.split("-")[1])
                
                current_val = mes_actual_info['year'] * 12 + mes_actual_info['month']
                target_val = target_year * 12 + target_month
                
                if current_val > target_val:
                    prev_btn = self.page.locator("a.ui-datepicker-prev")
                    if prev_btn.is_visible():
                        prev_btn.click()
                        time.sleep(0.5)
                    else:
                        break
                elif current_val < target_val:
                    next_btn = self.page.locator("a.ui-datepicker-next")
                    if next_btn.is_visible():
                        next_btn.click()
                        time.sleep(0.5)
                    else:
                        break
                else:
                    break

            # Seleccionar la fecha óptima inyectando el click en el DOM
            script_click = f"""
            () => {{
                let target = Array.from(document.querySelectorAll('.ui-datepicker-calendar td[data-handler="selectDay"] a.ui-state-default')).find(a => {{
                    let td = a.parentElement;
                    let year = td.getAttribute('data-year');
                    let month = parseInt(td.getAttribute('data-month')) + 1;
                    let day = a.textContent.trim();
                    let dateStr = year + "-" + month.toString().padStart(2, '0') + "-" + day.padStart(2, '0');
                    return dateStr === '{mejor_fecha}';
                }});
                if(target) target.click();
            }}
            """
            self.page.evaluate(script_click)
            time.sleep(1)
            
            # Verificar si se seleccionó correctamente leyendo el input
            fecha_input = self.page.locator("#appointments_asc_appointment_date").input_value()
            if not fecha_input:
                print("Error: No se pudo seleccionar la fecha ideal en el calendario.")
                mejor_fecha = None
        else:
            print(f"No se encontró ninguna fecha ASC válida entre {fecha_inicio} y {fecha_tope_asc}.")

        # Limpieza de interfaz
        self.page.keyboard.press("Escape")
        time.sleep(1)

        if mejor_fecha:
            time.sleep(3)
            if mejor_fecha == fecha_consular_agendada:
                print("10. [Mismo Día] Seleccionando la PRIMERA hora disponible para ASC...")
                self._seleccionar_primera_hora("#appointments_asc_appointment_time")
            else:
                print("10. [Distinto Día] Seleccionando la ÚLTIMA hora disponible para ASC...")
                self._seleccionar_ultima_hora("#appointments_asc_appointment_time")
            print("¡Hora ASC ingresada con éxito!")

        return mejor_fecha

    def explorar_sede_completa(self, consulado: str, lista_ascs: list, rangos: list, limite_meses: int = 12) -> dict:
        """ Método Scout Avanzado: Escanea el calendario, elige un día que encaje en los rangos y desbloquea el CAS. """
        tope_absoluto = max([r[1] for r in rangos]) if rangos else "9999-12-31"
        resultado = {
            "consular": None,
            "ascs": {},
            "primer_dia": None,
            "tope_maximo": tope_absoluto,
            "motivo": "Sin citas disponibles en rango"
        }
        
        try:
            self.page.locator("#appointments_consulate_appointment_facility_id").select_option(label=consulado, timeout=5000)
        except Exception:
            resultado["motivo"] = f"Error: No se pudo seleccionar '{consulado}'"
            return resultado
            
        time.sleep(3) 

        # Forzar el reseteo de la memoria interna del calendario para que empiece desde el mes actual
        try:
            self.page.evaluate("jQuery('#appointments_consulate_appointment_date').datepicker('setDate', new Date());")
            self.page.evaluate("jQuery('#appointments_consulate_appointment_date').datepicker('setDate', null);")
        except Exception:
            pass

        try:
            self.page.locator("#appointments_consulate_appointment_date").click(timeout=10000)
        except Exception:
            resultado["motivo"] = "Calendario consular no abrió (Sin citas)"
            return resultado
        time.sleep(1)
        
        meses_buscados = 0
        fecha_consular = None
        
        while True:
            if meses_buscados >= limite_meses:
                resultado["motivo"] = f"Sin citas en próximos {limite_meses} meses"
                break 

            dias_disponibles = self.page.locator(".ui-datepicker-calendar a.ui-state-default")
            cantidad_dias = dias_disponibles.count()
            
            if cantidad_dias > 0:
                script = """
                () => {
                    let dates = [];
                    document.querySelectorAll('.ui-datepicker-calendar td[data-handler="selectDay"] a.ui-state-default').forEach(a => {
                        let td = a.parentElement;
                        let year = td.getAttribute('data-year');
                        let month = parseInt(td.getAttribute('data-month')) + 1;
                        let day = a.textContent.trim();
                        let dateStr = year + "-" + month.toString().padStart(2, '0') + "-" + day.padStart(2, '0');
                        dates.push(dateStr);
                    });
                    return dates;
                }
                """
                dias_en_pantalla = self.page.evaluate(script)
                
                if dias_en_pantalla:
                    if not resultado["primer_dia"]:
                        resultado["primer_dia"] = dias_en_pantalla[0]
                        
                    # REGLA DE OPTIMIZACIÓN: Si la primera fecha que vemos ya está en el futuro (supera el tope), abortamos.
                    if dias_en_pantalla[0] > tope_absoluto:
                        resultado["motivo"] = f"Calendario en {dias_en_pantalla[0]} supera tope ({tope_absoluto})"
                        break
                
                dia_a_hacer_clic = None
                for dia_str in dias_en_pantalla:
                    valido = False
                    for r_inicio, r_tope in rangos:
                        if r_inicio <= dia_str <= r_tope:
                            valido = True
                            break
                    if valido:
                        dia_a_hacer_clic = dia_str
                        break
                
                if dia_a_hacer_clic:
                    script_click = f"""
                    () => {{
                        let target = Array.from(document.querySelectorAll('.ui-datepicker-calendar td[data-handler="selectDay"] a.ui-state-default')).find(a => {{
                            let td = a.parentElement;
                            let year = td.getAttribute('data-year');
                            let month = parseInt(td.getAttribute('data-month')) + 1;
                            let day = a.textContent.trim();
                            let dateStr = year + "-" + month.toString().padStart(2, '0') + "-" + day.padStart(2, '0');
                            return dateStr === '{dia_a_hacer_clic}';
                        }});
                        if(target) target.click();
                    }}
                    """
                    self.page.evaluate(script_click)
                    time.sleep(1)
                    fecha_consular = self.page.locator("#appointments_consulate_appointment_date").input_value()
                    resultado["motivo"] = "Cita consular encontrada"
                    break
                    
            boton_siguiente = self.page.locator("a.ui-datepicker-next")
            if boton_siguiente.is_visible():
                boton_siguiente.click()
                meses_buscados += 1
                time.sleep(0.5) 
            else:
                break
                
        if not fecha_consular:
            self.page.keyboard.press("Escape")
            self.page.evaluate("document.activeElement.blur()") # Fuerza a quitar el borde azul y foco
            time.sleep(0.5)
            if not resultado["primer_dia"]:
                resultado["primer_dia"] = "Sin fechas"
            return resultado
            
        # Seleccionar la primera hora disponible para validar la cita y desbloquear el CAS
        time.sleep(2)
        hora_ok = False
        try:
            self._seleccionar_primera_hora("#appointments_consulate_appointment_time")
            time.sleep(1)
            val_hora = self.page.locator("#appointments_consulate_appointment_time").input_value()
            if val_hora:
                hora_ok = True
        except Exception:
            pass

        if not hora_ok:
            print(f" -> [!] Fecha {fecha_consular} sin horarios disponibles (Cita fantasma o ganada).")
            resultado["consular"] = None
            resultado["motivo"] = f"Fecha {fecha_consular} sin horarios disponibles"
            self.page.keyboard.press("Escape")
            self.page.evaluate("document.activeElement.blur()")
            return resultado

        # Solo si la hora fue seleccionada con éxito, marcamos la fecha como disponible
        resultado["consular"] = fecha_consular
            
        # Iterar sobre los ASCs solicitados
        for asc in lista_ascs:
            try:
                self.page.locator("#appointments_asc_appointment_facility_id").select_option(label=asc, timeout=5000)
            except Exception:
                resultado["ascs"][asc] = None
                continue
                
            time.sleep(3)
            
            # Forzar reseteo del calendario ASC
            try:
                self.page.evaluate("jQuery('#appointments_asc_appointment_date').datepicker('setDate', new Date());")
                self.page.evaluate("jQuery('#appointments_asc_appointment_date').datepicker('setDate', null);")
            except Exception:
                pass
            
            try:
                self.page.locator("#appointments_asc_appointment_date").click(timeout=10000)
                time.sleep(1)
            except Exception:
                resultado["ascs"][asc] = None
                continue
                
            meses_buscados_asc = 0
            fecha_asc = None
            
            while True:
                if meses_buscados_asc >= limite_meses:
                    break
                    
                dias_disponibles_asc = self.page.locator(".ui-datepicker-calendar a.ui-state-default")
                if dias_disponibles_asc.count() > 0:
                    dias_en_pantalla_asc = self.page.evaluate(script) # Reutilizamos el mismo script de extracción
                    
                    if dias_en_pantalla_asc and dias_en_pantalla_asc[0] > tope_absoluto:
                        break
                    
                    dia_asc_clic = None
                    validos_asc = []
                    for dia_str in dias_en_pantalla_asc:
                        valido = False
                        for r_inicio, r_tope in rangos:
                            if dia_str <= r_tope:
                                valido = True
                                break
                        if valido:
                            validos_asc.append(dia_str)
                            
                    if validos_asc:
                        dia_asc_clic = max(validos_asc)
                            
                    if dia_asc_clic:
                        script_click_asc = f"""
                        () => {{
                            let target = Array.from(document.querySelectorAll('.ui-datepicker-calendar td[data-handler="selectDay"] a.ui-state-default')).find(a => {{
                                let td = a.parentElement;
                                let year = td.getAttribute('data-year');
                                let month = parseInt(td.getAttribute('data-month')) + 1;
                                let day = a.textContent.trim();
                                let dateStr = year + "-" + month.toString().padStart(2, '0') + "-" + day.padStart(2, '0');
                                return dateStr === '{dia_asc_clic}';
                            }});
                            if(target) target.click();
                        }}
                        """
                        self.page.evaluate(script_click_asc)
                        time.sleep(1)
                        fecha_asc = self.page.locator("#appointments_asc_appointment_date").input_value()
                        break
                    
                boton_siguiente = self.page.locator("a.ui-datepicker-next")
                if boton_siguiente.is_visible():
                    boton_siguiente.click()
                    meses_buscados_asc += 1
                    time.sleep(0.5)
                else:
                    break
                    
            resultado["ascs"][asc] = fecha_asc
            
            # Limpiar el calendario ASC visualmente para la siguiente iteración
            self.page.keyboard.press("Escape")
            self.page.evaluate("document.activeElement.blur()")
            time.sleep(0.5)
            
        return resultado

    def confirmar_cita(self, ivr: str = "") -> tuple[bool, str, str, str]:
        print("11. Haciendo clic en el botón final para programar la cita...")
        boton_final = self.page.locator("#appointments_submit")
        boton_final.wait_for(state="visible", timeout=10000)
        
        # Validación de seguridad: no esperar 60s si el botón está deshabilitado
        if boton_final.is_disabled():
            time.sleep(2)  # Breve pausa por si el DOM estaba terminando de habilitarlo
            if boton_final.is_disabled():
                raise Exception("El botón 'Programe la cita' está DESHABILITADO. Faltan campos obligatorios o la hora no fue aceptada.")

        boton_final.click(timeout=5000)
        print("⏳ Esperando confirmación oficial de la embajada en pantalla...")
        
        exito = False
        motivo = "Sin respuesta clara del servidor consular"
        
        # Monitorear la respuesta durante hasta 12 segundos
        inicio_espera = time.time()
        while time.time() - inicio_espera < 12:
            time.sleep(1)
            url_actual = self.page.url.lower()
            
            # 1. Redirección exitosa a instrucciones o confirmación
            if "/appointment/instructions" in url_actual or "/instructions" in url_actual:
                exito = True
                motivo = "Su cita ha sido programada con éxito"
                break

            # 2. Modal emergente visible (Foundation Reveal, etc.)
            modal_loc = self.page.locator(".reveal-modal:visible, .reveal:visible, div[role='dialog']:visible, .ui-dialog:visible")
            if modal_loc.count() > 0:
                texto_modal = modal_loc.first.inner_text().strip()
                texto_modal_lower = texto_modal.lower()
                palabras_error = ["no está disponible", "no longer available", "error", "ha ocurrido", "excedido", "exceeded", "no disponible"]
                if any(p in texto_modal_lower for p in palabras_error):
                    exito = False
                    motivo = texto_modal.split("\n")[0].strip() or "La fecha u hora seleccionada ya no está disponible"
                    break
                else:
                    exito = True
                    motivo = texto_modal.split("\n")[0].strip() or "Su cita ha sido programada con éxito"
                    break
                    
            # 3. Alertas o notificaciones visibles en pantalla
            alert_loc = self.page.locator(".alert-box:visible, .flash-alert:visible, .notice:visible, .alert:visible")
            if alert_loc.count() > 0:
                texto_alert = alert_loc.first.inner_text().strip()
                texto_alert_lower = texto_alert.lower()
                palabras_error = ["no está disponible", "no longer available", "error", "problema", "incorrecto"]
                if any(p in texto_alert_lower for p in palabras_error):
                    exito = False
                    motivo = texto_alert.split("\n")[0].strip()
                    break
                elif any(p in texto_alert_lower for p in ["éxito", "exito", "programada", "scheduled", "confirmada"]):
                    exito = True
                    motivo = texto_alert.split("\n")[0].strip()
                    break

        # Evaluación complementaria del contenido general si no se detectó corte
        if not exito and motivo == "Sin respuesta clara del servidor consular":
            contenido = self.page.content().lower()
            if "programada con éxito" in contenido or "appointment scheduled" in contenido or "ha sido programada" in contenido:
                exito = True
                motivo = "Su cita ha sido programada con éxito"
            elif "no está disponible" in contenido or "no longer available" in contenido:
                exito = False
                motivo = "La fecha y hora seleccionada ya no está disponible"
            else:
                exito = False
                motivo = "Tiempo de espera agotado sin confirmación visual de la embajada"

        # Generar captura de pantalla en ambos casos (éxito o fallo)
        ahora_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        tipo_str = "exito" if exito else "fallo"
        ivr_str = str(ivr) if ivr else "desconocido"
        nombre_archivo = f"{tipo_str}_IVR_{ivr_str}_{ahora_str}.png"
        ruta_completa = f"logs/{nombre_archivo}"
        
        if not os.path.exists("logs"):
            os.makedirs("logs")
            
        estado_imagen = "GUARDADA"
        try:
            self.page.screenshot(path=ruta_completa, full_page=True)
        except Exception as e_img:
            estado_imagen = f"FALLO AL GUARDAR: {e_img}"

        if exito:
            print(f'✅ [EMBAJADA] Modal de confirmación detectado: "{motivo}".')
            if estado_imagen == "GUARDADA":
                print(f"📸 [EVIDENCIA] Captura guardada con éxito: {ruta_completa}")
            else:
                print(f"⚠️ [EVIDENCIA] No se pudo guardar la captura de imagen: {estado_imagen}")

            # Descartar modal emergente (ej. servicios premium) para liberar la navegación
            try:
                btn_no_gracias = self.page.locator("a:visible, button:visible").filter(has_text="No gracias").first
                if btn_no_gracias.is_visible(timeout=2000):
                    btn_no_gracias.click(force=True)
                    time.sleep(1)
                else:
                    self.page.keyboard.press("Escape")
                    time.sleep(0.5)
            except Exception:
                try:
                    self.page.keyboard.press("Escape")
                except Exception:
                    pass
        else:
            print(f'❌ [EMBAJADA] No se confirmó la cita. Motivo: "{motivo}".')
            if estado_imagen == "GUARDADA":
                print(f"📸 [EVIDENCIA] Captura de pantalla del error guardada: {ruta_completa}")
            else:
                print(f"⚠️ [EVIDENCIA] No se pudo guardar la captura de imagen: {estado_imagen}")

        return exito, motivo, ruta_completa, estado_imagen

    def busqueda_general(self, limite_meses: int = 12):
        print("--- INICIANDO BÚSQUEDA GENERAL DE FECHAS EN TODOS LOS CONSULADOS ---")
        lista_consulados = [
            "Ciudad Juarez", "Guadalajara", "Hermosillo", "Matamoros", 
            "Merida", "Mexico City", "Monterrey", "Nogales", 
            "Nuevo Laredo", "Tijuana"
        ]
        for ciudad in lista_consulados:
            print(f"Revisando disponibilidad en: {ciudad}...")
            try:
                self.page.locator("#appointments_consulate_appointment_facility_id").select_option(label=ciudad)
                time.sleep(3) 
                self.page.locator("#appointments_consulate_appointment_date").click()
                time.sleep(1)
                
                meses_temp = 0
                fecha_ciudad = "Sin citas disponibles"
                while meses_temp < limite_meses:
                    dias_disp = self.page.locator(".ui-datepicker-calendar a.ui-state-default")
                    if dias_disp.count() > 0:
                        dias_disp.first.click()
                        time.sleep(1)
                        fecha_ciudad = self.page.locator("#appointments_consulate_appointment_date").input_value()
                        break
                    else:
                        btn_sig = self.page.locator("a.ui-datepicker-next")
                        if btn_sig.is_visible():
                            btn_sig.click()
                            meses_temp += 1
                            time.sleep(0.5)
                        else:
                            break
                print(f" -> Fecha más próxima en {ciudad}: {fecha_ciudad}")
            except Exception as error_ciudad:
                print(f" -> No se pudo revisar {ciudad}. Detalle: {error_ciudad}")
        print("Búsqueda general finalizada.")
