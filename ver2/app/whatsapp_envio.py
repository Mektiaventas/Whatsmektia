import requests
import logging

logger = logging.getLogger(__name__)

# Definimos la versión global aquí para cambiarla en un solo lugar si Meta actualiza
API_VERSION = "v22.0"

def enviar_texto(numero, texto, config_tenant):
    """Envía un mensaje de texto plano."""
    print(f"📤 DEBUG: Intentando enviar texto a {numero}...")
    if not texto:
        print("⚠️ DEBUG: Intento de enviar mensaje VACÍO abortado.")
        return None

    url = f"https://graph.facebook.com/{API_VERSION}/{config_tenant['phone_id']}/messages"
    headers = {
        "Authorization": f"Bearer {config_tenant['token']}",
        "Content-Type": "application/json"
    }
    
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": numero,
        "type": "text",
        "text": {"body": texto}
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        res_json = response.json()
        print(f"📩 DEBUG: Respuesta de Meta: {response.status_code}")
        return res_json
    except Exception as e:
        print(f"❌ DEBUG ERROR enviando texto: {e}")
        return None

def enviar_imagen(numero, url_imagen, leyenda, config_tenant):
    """Envía una imagen por URL."""
    url = f"https://graph.facebook.com/{API_VERSION}/{config_tenant['phone_id']}/messages"
    headers = {"Authorization": f"Bearer {config_tenant['token']}"}
    
    data = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "image",
        "image": {"link": url_imagen, "caption": leyenda}
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"❌ Error imagen: {e}")
        return None

def enviar_audio(numero, url_audio, config_tenant):
    """
    Envía un archivo de audio (debe ser .ogg o .mp3).
    Útil para las respuestas de voz de la IA.
    """
    url = f"https://graph.facebook.com/{API_VERSION}/{config_tenant['phone_id']}/messages"
    headers = {"Authorization": f"Bearer {config_tenant['token']}"}
    
    data = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "audio",
        "audio": {"link": url_audio}
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=10)
        return response.json()
    except Exception as e:
        logger.error(f"❌ Error audio: {e}")
        return None

def marcar_leido(message_id, config_tenant):
    """Envía el doble check azul."""
    url = f"https://graph.facebook.com/{API_VERSION}/{config_tenant['phone_id']}/messages"
    headers = {"Authorization": f"Bearer {config_tenant['token']}"}
    
    data = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id
    }
    requests.post(url, headers=headers, json=data)
