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

def obtener_audio_whatsapp(audio_id, config=None):
    """
    Descarga audio desde Graph API y guarda en uploads; retorna (audio_path, public_url)
    """
    try:
        token = config.get('whatsapp_token') or os.getenv('MEKTIA_WHATSAPP_TOKEN') or os.getenv('WHATSAPP_TOKEN')
        if not token:
            logger.error("🔴 obtener_audio_whatsapp: no whatsapp token configured")
            return None, None

        meta_url = f"https://graph.facebook.com/v18.0/{audio_id}"
        headers = {'Authorization': f'Bearer {token}'}
        r = requests.get(meta_url, headers=headers, timeout=30)
        r.raise_for_status()
        meta = r.json()
        download_url = meta.get('url')
        if not download_url:
            logger.error(f"🔴 No download url for audio: {meta}")
            return None, None

        audio_r = requests.get(download_url, headers=headers, timeout=30)
        audio_r.raise_for_status()
        content = audio_r.content

        # Determine extension from response Content-Type
        content_type = audio_r.headers.get('Content-Type', '')
        # map minimal set
        ct_map = {
            'audio/ogg': 'ogg',
            'audio/webm': 'webm',
            'audio/mpeg': 'mp3',
            'audio/mp3': 'mp3',
            'audio/wav': 'wav',
            'audio/x-wav': 'wav',
            'audio/mp4': 'mp4',
            'audio/m4a': 'm4a',
            'audio/opus': 'ogg'
        }
        ext = None
        for k, v in ct_map.items():
            if content_type.startswith(k):
                ext = v
                break
        # fallback: try to parse filename from URL
        if not ext:
            parsed = download_url.split('?')[0].split('/')[-1]
            if '.' in parsed:
                ext = parsed.rsplit('.', 1)[1].lower()
        if not ext:
            ext = 'ogg'  # safe default if unsure

        uploads = get_upload_base()
        os.makedirs(uploads, exist_ok=True)
        filename = secure_filename(f"audio_{audio_id}.{ext}")
        audio_path = os.path.join(uploads, filename)
        with open(audio_path, 'wb') as f:
            f.write(content)

        dominio = (config.get('dominio') or os.getenv('MI_DOMINIO') or 'http://localhost:5000').rstrip('/')
        if not dominio.startswith('http'):
            dominio = f"https://{dominio}"
        audio_url = f"{dominio}/uploads/{os.path.basename(audio_path)}"
        logger.info(f"✅ Saved whatsapp audio: {audio_path} (Content-Type: {content_type})")
        return audio_path, audio_url
    except Exception as e:
        logger.error(f"🔴 obtener_audio_whatsapp error: {e}")
        return None, None

def enviar_mensaje(numero, texto, config):
    """Enviar texto por Graph API. Retorna True/False con logging diagnóstico."""
    try:
        cfg = config or {}
        phone_id = cfg.get('phone_number_id') or os.getenv('MEKTIA_PHONE_NUMBER_ID') or os.getenv('PHONE_NUMBER_ID')
        token = cfg.get('whatsapp_token') or os.getenv('MEKTIA_WHATSAPP_TOKEN') or os.getenv('WHATSAPP_TOKEN')

        if not phone_id or not token:
            logger.error("🔴 enviar_mensaje: falta phone_number_id o whatsapp_token (config/ENV)")
            logger.debug(f"🔍 config keys: {list(cfg.keys()) if isinstance(cfg, dict) else type(cfg)}")
            return False

        url = f"https://graph.facebook.com/v23.0/{phone_id}/messages"
        headers = {'Authorization': f"Bearer {token}", 'Content-Type': 'application/json'}
        payload = {'messaging_product': 'whatsapp', 'to': numero, 'type': 'text', 'text': {'body': str(texto)}}

        logger.info(f"📤 enviar_mensaje -> to={numero} phone_number_id={phone_id} text_preview={str(texto)[:120]}")
        r = requests.post(url, headers=headers, json=payload, timeout=12)

        status = getattr(r, 'status_code', 'n/a')
        body_preview = ''
        try:
            body_txt = r.text or ''
            body_preview = body_txt[:1000] + ('...' if len(body_txt) > 1000 else '')
        except Exception:
            body_preview = '<unreadable-response-body>'

        if status in (200, 201, 202):
            logger.info(f"✅ enviar_mensaje OK (status={status}) - resp_preview: {body_preview}")
            return True

        # fallo
        err_info = None
        try:
            err_json = r.json()
            err_info = err_json.get('error') or err_json
        except Exception:
            err_info = body_preview

        logger.error(f"🔴 enviar_mensaje FAILED status={status} -> {err_info}")
        return False
    except Exception as e:
        logger.error(f"Exception enviar_mensaje: {e}")
        return False

def enviar_imagen(numero, image_url, config):
    """Enviar imagen por link con logging diagnóstico."""
    try:
        cfg = config or {}
        phone_id = cfg.get('phone_number_id') or os.getenv('MEKTIA_PHONE_NUMBER_ID') or os.getenv('PHONE_NUMBER_ID')
        token = cfg.get('whatsapp_token') or os.getenv('MEKTIA_WHATSAPP_TOKEN') or os.getenv('WHATSAPP_TOKEN')

        if not phone_id or not token:
            logger.error("🔴 enviar_imagen: falta phone_number_id o whatsapp_token (config/ENV)")
            return False

        url = f"https://graph.facebook.com/v23.0/{phone_id}/messages"
        headers = {'Authorization': f"Bearer {token}", 'Content-Type': 'application/json'}
        payload = {'messaging_product':'whatsapp','to':numero,'type':'image','image':{'link': image_url}}

        logger.info(f"📤 enviar_imagen -> to={numero} phone_number_id={phone_id} image_url={image_url[:200]}")
        r = requests.post(url, headers=headers, json=payload, timeout=12)

        status = getattr(r, 'status_code', 'n/a')
        try:
            body_preview = (r.text or '')[:1000]
        except Exception:
            body_preview = '<unreadable-response-body>'

        if status in (200, 201, 202):
            logger.info(f"✅ enviar_imagen OK (status={status}) - resp_preview: {body_preview}")
            return True

        logger.error(f"🔴 enviar_imagen FAILED status={status} - resp_preview: {body_preview}")
        return False
    except Exception as e:
        logger.error(f"Exception enviar_imagen: {e}")
        return False

def enviar_documento(numero, file_url, filename, config):
    """Enviar documento por link con logging diagnóstico."""
    try:
        cfg = config or {}
        phone_id = cfg.get('phone_number_id') or os.getenv('MEKTIA_PHONE_NUMBER_ID') or os.getenv('PHONE_NUMBER_ID')
        token = cfg.get('whatsapp_token') or os.getenv('MEKTIA_WHATSAPP_TOKEN') or os.getenv('WHATSAPP_TOKEN')

        if not phone_id or not token:
            logger.error("🔴 enviar_documento: falta phone_number_id o whatsapp_token (config/ENV)")
            return False

        url = f"https://graph.facebook.com/v23.0/{phone_id}/messages"
        headers = {'Authorization': f"Bearer {token}", 'Content-Type': 'application/json'}
        payload = {'messaging_product':'whatsapp','to':numero,'type':'document','document':{'link': file_url,'filename': filename}}

        logger.info(f"📤 enviar_documento -> to={numero} phone_number_id={phone_id} file_url={file_url[:200]} filename={filename}")
        r = requests.post(url, headers=headers, json=payload, timeout=20)

        status = getattr(r, 'status_code', 'n/a')
        try:
            body_preview = (r.text or '')[:1000]
        except Exception:
            body_preview = '<unreadable-response-body>'

        if status in (200, 201, 202):
            logger.info(f"✅ enviar_documento OK (status={status}) - resp_preview: {body_preview}")
            return True

        logger.error(f"🔴 enviar_documento FAILED status={status} - resp_preview: {body_preview}")
        return False
    except Exception as e:
        logger.error(f"Exception enviar_documento: {e}")
        return False

def enviar_mensaje_voz(numero, audio_url, config):
    """Enviar audio (voice message) por link con validaciones y logging diagnóstico."""
    try:
        cfg = config or {}
        phone_id = cfg.get('phone_number_id') or os.getenv('MEKTIA_PHONE_NUMBER_ID') or os.getenv('PHONE_NUMBER_ID')
        token = cfg.get('whatsapp_token') or os.getenv('MEKTIA_WHATSAPP_TOKEN') or os.getenv('WHATSAPP_TOKEN')

        if not phone_id or not token:
            logger.error("🔴 enviar_mensaje_voz: falta phone_number_id o whatsapp_token (config/ENV)")
            return False

        url = f"https://graph.facebook.com/v23.0/{phone_id}/messages"
        headers = {'Authorization': f"Bearer {token}", 'Content-Type': 'application/json'}
        payload = {'messaging_product':'whatsapp','to':numero,'type':'audio','audio':{'link': audio_url}}

        logger.info(f"📤 enviar_mensaje_voz -> to={numero} phone_number_id={phone_id} audio_url={audio_url}")
        r = requests.post(url, headers=headers, json=payload, timeout=15)

        status = getattr(r, 'status_code', 'n/a')
        try:
            body_preview = (r.text or '')[:1000]
        except Exception:
            body_preview = '<unreadable-response-body>'

        if status in (200, 201, 202):
            logger.info(f"✅ enviar_mensaje_voz OK (status={status}) - resp_preview: {body_preview}")
            return True

        # If failed, try to parse JSON error for better message
        err_info = None
        try:
            err_json = r.json()
            err_info = err_json.get('error') or err_json
        except Exception:
            err_info = body_preview

        logger.error(f"🔴 enviar_mensaje_voz FAILED status={status} -> {err_info}")
        return False
    except Exception as e:
        logger.error(f"Exception enviar_mensaje_voz: {e}")
        return False

