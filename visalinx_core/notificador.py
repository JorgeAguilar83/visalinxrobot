import os
import json
import uuid
import urllib.request
import urllib.parse

class TelegramNotifier:
    """
    Notificador nativo y ultraligero mediante Telegram Bot API.
    No requiere navegadores ni dependencias externas (utiliza urllib nativo de Python).
    """
    def __init__(self, bot_token: str = "", admin_chat_id: str = "", activo: bool = True):
        self.bot_token = bot_token.strip() if bot_token else ""
        self.admin_chat_id = str(admin_chat_id).strip() if admin_chat_id else ""
        self.activo = activo and bool(self.bot_token)

    def _enviar_texto(self, chat_id: str, texto: str) -> bool:
        if not self.activo or not chat_id:
            return False
            
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": texto
        }
        data = urllib.parse.urlencode(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        
        try:
            with urllib.request.urlopen(req, timeout=12) as response:
                res = json.loads(response.read().decode("utf-8"))
                return res.get("ok", False)
        except Exception as e:
            print(f"  [Telegram] Error enviando mensaje a {chat_id}: {e}")
            return False

    def _enviar_foto(self, chat_id: str, ruta_foto: str, caption: str = "") -> bool:
        if not self.activo or not chat_id:
            return False

        if not os.path.exists(ruta_foto):
            print(f"  [Telegram] Captura {ruta_foto} no encontrada, enviando solo texto...")
            return self._enviar_texto(chat_id, caption)

        boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
        body = bytearray()

        # Campo chat_id
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode("utf-8"))

        # Campo caption (descripción de la foto)
        if caption:
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode("utf-8"))

        # Campo photo
        nombre_archivo = os.path.basename(ruta_foto)
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="photo"; filename="{nombre_archivo}"\r\n'.encode("utf-8"))
        body.extend(b"Content-Type: image/png\r\n\r\n")
        try:
            with open(ruta_foto, "rb") as f:
                body.extend(f.read())
            body.extend(b"\r\n")
            body.extend(f"--{boundary}--\r\n".encode("utf-8"))

            url = f"https://api.telegram.org/bot{self.bot_token}/sendPhoto"
            req = urllib.request.Request(url, data=bytes(body))
            req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")

            with urllib.request.urlopen(req, timeout=20) as response:
                res = json.loads(response.read().decode("utf-8"))
                return res.get("ok", False)
        except Exception as e:
            print(f"  [Telegram] Error enviando foto a {chat_id}: {e}. Intentando texto alternativo...")
            return self._enviar_texto(chat_id, caption)

    def notificar_error_admin(self, mensaje: str):
        """
        Envía alertas críticas, fallos de proxy, citas perdidas y avisos de mantenimiento
        exclusivamente al chat privado del administrador.
        """
        if not self.activo:
            return
            
        if not self.admin_chat_id:
            print("  [Telegram Admin] Alerta no enviada: 'telegram_admin_chat_id' no está configurado.")
            return

        print(f"📡 [Telegram Admin] Enviando alerta técnica al administrador ({self.admin_chat_id})...")
        texto_admin = f"⚠️ [ALERTA SISTEMA VISALINX]\n{mensaje}"
        if self._enviar_texto(self.admin_chat_id, texto_admin):
            print("  [✓] Alerta entregada al administrador.")
        else:
            print("  [X] No se pudo entregar la alerta al administrador.")

    def notificar_exito_cliente(self, lista_chat_ids: list, mensaje: str, ruta_foto: str = None):
        """
        Envía notificaciones de citas agendadas con éxito únicamente como texto
        a los grupos específicos asignados al cliente (sin adjuntar fotos).
        """
        if not self.activo:
            return

        if not lista_chat_ids:
            print("  [Telegram] No hay chat_ids configurados para este cliente.")
            return

        print("📡 [Telegram Clientes] Enviando confirmación de cita a los grupos del cliente...")
        for chat_id in lista_chat_ids:
            exito = self._enviar_texto(chat_id, mensaje)

            if exito:
                print(f"  [✓] Notificación de cita entregada con éxito al chat/grupo: {chat_id}")
            else:
                print(f"  [X] Falló el envío al chat/grupo: {chat_id}")

    def enviar_alerta_multiple(self, lista_chat_ids: list, mensaje: str):
        """
        Método de compatibilidad con llamadas legadas.
        """
        self.notificar_exito_cliente(lista_chat_ids, mensaje)
