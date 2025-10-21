import os
import time
import logging
import base64
import requests
from datetime import datetime
from werkzeug.utils import secure_filename

# Import helper from files.py (fallback if import fails)
try:
    from files import get_upload_base
except Exception:
    def get_upload_base():
        return os.getenv('UPLOAD_FOLDER') or os.path.join(os.path.dirname(__file__), '..', 'uploads')

logger = logging.getLogger(__name__)

def _ensure_static_dir(subpath):
    base = os.getenv('APP_BASE_DIR') or os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    dest = os.path.join(base, 'static', subpath)
    os.makedirs(dest, exist_ok=True)
    return dest

def obtener_archivo_whatsapp(media_id, config):
    """
    Obtener metadata + descargar media desde Graph API.
    Retorna: (filepath, filename, extension) o (None, None, None)
    """
    token = config.get('whatsapp_token') or os.getenv('WHATSAPP_TOKEN')
    if not token:
        logger.error("No whatsapp token configured")
        return None, None, None

    try:
        url_meta = f"https://graph.facebook.com/v18.0/{media_id}"
        headers = {'Authorization': f'Bearer {token}'}
        r = requests.get(url_meta, headers=headers, timeout=30)
        r.raise_for_status()
        meta = r.json()
        download_url = meta.get('url')
        mime = meta.get('mime_type', 'application/octet-stream')
        filename = meta.get('filename') or f"media_{media_id}"
        if not download_url:
            logger.error(f"No download url for media {media_id}: {meta}")
            return None, None, None

        r2 = requests.get(download_url, headers=headers, timeout=60)
        r2.raise_for_status()
        content = r2.content

        uploads = os.getenv('UPLOAD_FOLDER') or os.path.join(os.path.dirname(__file__), '..', 'uploads')
        os.makedirs(uploads, exist_ok=True)
        safe_name = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}")
        filepath = os.path.join(uploads, safe_name)
        with open(filepath, 'wb') as f:
            f.write(content)

        # deduce ext
        ext = mime.split('/')[-1] if '/' in mime else os.path.splitext(filename)[1].lstrip('.') or 'bin'
        logger.info(f"Saved media to {filepath}")
        return filepath, safe_name, ext
    except Exception as e:
        logger.error(f"Error obtener_archivo_whatsapp: {e}")
        return None, None, None

def obtener_imagen_whatsapp(media_id, config):
    """Descarga imagen y retorna base64 + public_url (relative)"""
    filepath, filename, ext = obtener_archivo_whatsapp(media_id, config)
    if not filepath:
        return None, None
    try:
        with open(filepath, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
        mime = 'image/jpeg' if ext.lower() in ('jpg','jpeg') else f'image/{ext}'
        base64_string = f"data:{mime};base64,{b64}"
        public_url = f"/uploads/{filename}"
        return base64_string, public_url
    except Exception as e:
        logger.error(f"Error encoding image {filepath}: {e}")
        return None, None

def _build_fallback_config(config):
    """Return a minimal config dict when caller didn't pass one."""
    if config and isinstance(config, dict) and 'phone_number_id' in config and 'whatsapp_token' in config:
        return config
    return {
        'phone_number_id': os.getenv('MEKTIA_PHONE_NUMBER_ID') or os.getenv('PHONE_NUMBER_ID'),
        'whatsapp_token': os.getenv('MEKTIA_WHATSAPP_TOKEN') or os.getenv('WHATSAPP_TOKEN')
    }

def _log_response(r):
    """Helper to log response status and truncated body."""
    try:
        text = r.text if hasattr(r, 'text') else '<no-body>'
        preview = text[:800] + ('...' if len(text) > 800 else '')
    except Exception:
        preview = '<unreadable response>'
    logger.info(f"HTTP {getattr(r, 'status_code', 'n/a')} - response preview: {preview}")

def enviar_mensaje(numero, texto, config=None):
    """Enviar texto por Graph API. Retorna True/False"""
    try:
        cfg = _build_fallback_config(config)
        if not cfg.get('phone_number_id') or not cfg.get('whatsapp_token'):
            logger.error("🔴 enviar_mensaje: missing phone_number_id or whatsapp_token (config or env)")
            return False

        url = f"https://graph.facebook.com/v23.0/{cfg['phone_number_id']}/messages"
        headers = {'Authorization': f"Bearer {cfg['whatsapp_token']}", 'Content-Type': 'application/json'}
        payload = {'messaging_product': 'whatsapp', 'to': numero, 'type': 'text', 'text': {'body': str(texto)}}

        # Log minimal safe info (avoid logging token)
        logger.info(f"📤 Sending text to {numero}: {str(texto)[:120]}")
        logger.debug(f"📤 Payload (no token): { {k:v for k,v in payload.items() if k!='text' or len(str(payload['text']['body']))<200} }")

        r = requests.post(url, headers=headers, json=payload, timeout=12)

        if r.status_code in (200,201,202):
            logger.info("✅ Text message sent")
            _log_response(r)
            return True

        logger.error(f"🔴 Error sending text {r.status_code}")
        _log_response(r)
        return False
    except Exception as e:
        logger.error(f"Exception enviar_mensaje: {e}")
        return False

def enviar_imagen(numero, image_url, config=None):
    try:
        cfg = _build_fallback_config(config)
        if not cfg.get('phone_number_id') or not cfg.get('whatsapp_token'):
            logger.error("🔴 enviar_imagen: missing phone_number_id or whatsapp_token (config or env)")
            return False

        url = f"https://graph.facebook.com/v23.0/{cfg['phone_number_id']}/messages"
        headers = {'Authorization': f"Bearer {cfg['whatsapp_token']}", 'Content-Type': 'application/json'}
        payload = {'messaging_product':'whatsapp','to':numero,'type':'image','image':{'link': image_url}}

        logger.info(f"📤 Sending image to {numero}: {image_url[:200]}")
        r = requests.post(url, headers=headers, json=payload, timeout=12)

        if r.status_code in (200,201,202):
            logger.info("✅ Image message sent")
            _log_response(r)
            return True

        logger.error(f"🔴 Error sending image {r.status_code}")
        _log_response(r)
        return False
    except Exception as e:
        logger.error(f"Exception enviar_imagen: {e}")
        return False

def enviar_documento(numero, file_url, filename, config=None):
    try:
        cfg = _build_fallback_config(config)
        if not cfg.get('phone_number_id') or not cfg.get('whatsapp_token'):
            logger.error("🔴 enviar_documento: missing phone_number_id or whatsapp_token (config or env)")
            return False

        url = f"https://graph.facebook.com/v23.0/{cfg['phone_number_id']}/messages"
        headers = {'Authorization': f"Bearer {cfg['whatsapp_token']}", 'Content-Type': 'application/json'}
        payload = {'messaging_product':'whatsapp','to':numero,'type':'document','document':{'link': file_url,'filename': filename}}

        logger.info(f"📤 Sending document to {numero}: {filename} ({file_url[:200]})")
        r = requests.post(url, headers=headers, json=payload, timeout=20)

        if r.status_code in (200,201,202):
            logger.info("✅ Document message sent")
            _log_response(r)
            return True

        logger.error(f"🔴 Error sending document {r.status_code}")
        _log_response(r)
        return False
    except Exception as e:
        logger.error(f"Exception enviar_documento: {e}")
        return False

def enviar_mensaje_voz(numero, audio_url, config=None):
    try:
        cfg = _build_fallback_config(config)
        if not cfg.get('phone_number_id') or not cfg.get('whatsapp_token'):
            logger.error("🔴 enviar_mensaje_voz: missing phone_number_id or whatsapp_token (config or env)")
            return False

        url = f"https://graph.facebook.com/v23.0/{cfg['phone_number_id']}/messages"
        headers = {'Authorization': f"Bearer {cfg['whatsapp_token']}", 'Content-Type': 'application/json'}
        payload = {'messaging_product':'whatsapp','to':numero,'type':'audio','audio':{'link': audio_url}}

        logger.info(f"📤 Sending audio to {numero}: {audio_url[:200]}")
        r = requests.post(url, headers=headers, json=payload, timeout=15)

        if r.status_code in (200,201,202):
            logger.info("✅ Audio message sent")
            _log_response(r)
            return True

        logger.error(f"🔴 Error sending audio {r.status_code}")
        _log_response(r)
        return False
    except Exception as e:
        logger.error(f"Exception enviar_mensaje_voz: {e}")
        return False