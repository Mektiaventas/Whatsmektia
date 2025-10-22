import os
import time
import logging
import base64
import requests
import shutil
import zipfile
from datetime import datetime
from werkzeug.utils import secure_filename

# Audio conversion/transcription imports (las funciones que las usan esperan estas librerías)
try:
    from pydub import AudioSegment
except Exception:
    AudioSegment = None

try:
    from gtts import gTTS
except Exception:
    gTTS = None

from openai import OpenAI

logger = logging.getLogger(__name__)

def obtener_archivo_whatsapp(media_id, config=None):
    """Obtiene archivos de WhatsApp y los guarda localmente"""
    if config is None:
        # Existe la expectativa de que la app provea obtener_configuracion_por_host si no se pasa config
        try:
            from app import obtener_configuracion_por_host
            config = obtener_configuracion_por_host()
        except Exception:
            config = None
    
    try:
        # 1. Obtener metadata del archivo
        url_metadata = f"https://graph.facebook.com/v18.0/{media_id}"
        headers = {
            'Authorization': f'Bearer {config["whatsapp_token"]}',
            'Content-Type': 'application/json'
        }
        
        logger.info(f"📎 Obteniendo metadata de archivo: {url_metadata}")
        response_metadata = requests.get(url_metadata, headers=headers, timeout=30)
        response_metadata.raise_for_status()
        
        metadata = response_metadata.json()
        download_url = metadata.get('url')
        mime_type = metadata.get('mime_type', 'application/octet-stream')
        filename = metadata.get('filename', f'archivo_{media_id}')
        
        if not download_url:
            logger.error(f"🔴 No se encontró URL de descarga: {metadata}")
            return None, None, None
            
        logger.info(f"📎 Descargando archivo: {filename} ({mime_type})")
        
        # 2. Descargar el archivo
        file_response = requests.get(download_url, headers=headers, timeout=60)
        if file_response.status_code != 200:
            logger.error(f"🔴 Error descargando archivo: {file_response.status_code}")
            return None, None, None
        
        # 3. Determinar extensión y guardar
        # intentar usar una función determinar_extension si está disponible en la app
        extension = None
        try:
            from app import determinar_extension, UPLOAD_FOLDER
            extension = determinar_extension(mime_type, filename)
            uploads = UPLOAD_FOLDER
        except Exception:
            # fallback
            extension = mime_type.split('/')[-1] if '/' in mime_type else os.path.splitext(filename)[1].lstrip('.') or 'bin'
            uploads = os.path.join(os.path.dirname(__file__), '..', 'uploads')
        
        safe_filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}")
        filepath = os.path.join(uploads, safe_filename)
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        with open(filepath, 'wb') as f:
            f.write(file_response.content)
        
        logger.info(f"✅ Archivo guardado: {filepath}")
        return filepath, safe_filename, extension
        
    except Exception as e:
        logger.error(f"🔴 Error obteniendo archivo WhatsApp: {str(e)}")
        return None, None, None

def obtener_imagen_whatsapp(image_id, config=None):
    """Obtiene la imagen de WhatsApp, la convierte a base64 y guarda localmente"""
    if config is None:
        try:
            from app import obtener_configuracion_por_host
            config = obtener_configuracion_por_host()
        except Exception:
            config = None
    
    try:
        # 1. Obtener metadata de la imagen
        url_metadata = f"https://graph.facebook.com/v18.0/{image_id}"
        headers = {
            'Authorization': f'Bearer {config["whatsapp_token"]}',
            'Content-Type': 'application/json'
        }
        
        logger.info(f"🖼️ Obteniendo metadata de imagen WhatsApp: {url_metadata}")
        response_metadata = requests.get(url_metadata, headers=headers, timeout=30)
        response_metadata.raise_for_status()
        
        metadata = response_metadata.json()
        download_url = metadata.get('url')
        mime_type = metadata.get('mime_type', 'image/jpeg')
        
        if not download_url:
            logger.error(f"🔴 No se encontró URL de descarga de imagen: {metadata}")
            return None, None
            
        logger.info(f"🖼️ URL de descarga: {download_url}")
        
        # 2. Descargar la imagen
        image_response = requests.get(download_url, headers=headers, timeout=30)
        if image_response.status_code != 200:
            logger.error(f"🔴 Error descargando imagen: {image_response.status_code}")
            return None, None
        
        # 3. Guardar la imagen en directorio estático para mostrarla en web
        static_images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images', 'whatsapp')
        os.makedirs(static_images_dir, exist_ok=True)
        
        # Nombre seguro para el archivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = secure_filename(f"whatsapp_image_{timestamp}.jpg")
        filepath = os.path.join(static_images_dir, filename)
        
        with open(filepath, 'wb') as f:
            f.write(image_response.content)
        
        # 4. Convertir a base64 para OpenAI (si es necesario)
        image_base64 = base64.b64encode(image_response.content).decode('utf-8')
        base64_string = f"data:{mime_type};base64,{image_base64}"
        
        # 5. URL pública para mostrar en web
        public_url = f"/static/images/whatsapp/{filename}"
        
        logger.info(f"✅ Imagen guardada: {filepath}")
        logger.info(f"🌐 URL web: {public_url}")
        
        return base64_string, public_url
        
    except Exception as e:
        logger.error(f"🔴 Error en obtener_imagen_whatsapp: {str(e)}")
        logger.error(traceback.format_exc())
        return None, None

def obtener_audio_whatsapp(audio_id, config=None):
    try:
        # Intentar obtener token del config dict
        token = None
        if isinstance(config, dict):
            token = config.get('whatsapp_token')
        # Fallbacks no modificados aquí asumen que la app proporciona variables de entorno si no hay config
        if config is None:
            try:
                from app import obtener_configuracion_por_host
                config = obtener_configuracion_por_host()
            except Exception:
                config = None

        url = f"https://graph.facebook.com/v18.0/{audio_id}"
        headers = {'Authorization': f'Bearer {config["whatsapp_token"]}'}
        logger.info(f"📥 Solicitando metadata de audio: {url}")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        metadata = response.json()
        download_url = metadata.get('url')
        logger.info(f"🔗 URL de descarga: {download_url}")
        
        audio_response = requests.get(download_url, headers=headers, timeout=30)
        audio_response.raise_for_status()
        
        # Verificar tipo de contenido
        content_type = audio_response.headers.get('content-type')
        logger.info(f"🎧 Tipo de contenido: {content_type}")
        if 'audio' not in content_type:
            logger.error(f"🔴 Archivo no es audio: {content_type}")
            return None, None
        
        # Guardar archivo
        try:
            from app import UPLOAD_FOLDER
            uploads = UPLOAD_FOLDER
        except Exception:
            uploads = os.path.join(os.path.dirname(__file__), '..', 'uploads')
        os.makedirs(uploads, exist_ok=True)
        audio_path = os.path.join(uploads, f"audio_{audio_id}.ogg")
        with open(audio_path, 'wb') as f:
            f.write(audio_response.content)
        logger.info(f"💾 Audio guardado en: {audio_path}")
        
        # Generar URL pública
        # Nota: la app construye https://{config['dominio']}/uploads/...
        audio_url = f"https://{config['dominio']}/uploads/audio_{audio_id}.ogg"
        return audio_path, audio_url
    except Exception as e:
        logger.error(f"🔴 Error en obtener_audio_whatsapp: {str(e)}")
        return None, None

def transcribir_audio_con_openai(audio_path):
    try:
        logger.info(f"🎙️ Enviando audio para transcripción: {audio_path}")
        
        # Usar el cliente OpenAI correctamente (nueva versión)
        client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
        
        with open(audio_path, 'rb') as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="es"
            )
            
        logger.info(f"✅ Transcripción exitosa: {transcription.text}")
        return transcription.text
        
    except Exception as e:
        logger.error(f"🔴 Error en transcripción: {str(e)}")
        # intentar leer response si existe en excepción
        try:
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"🔴 Respuesta de OpenAI: {e.response.text}")
        except Exception:
            pass
        return None

def convertir_audio(audio_path):
    try:
        output_path = audio_path.replace('.ogg', '.mp3')
        if AudioSegment is None:
            logger.error("🔴 convertir_audio: pydub no está disponible")
            return None
        audio = AudioSegment.from_file(audio_path, format='ogg')
        audio.export(output_path, format='mp3')
        logger.info(f"🔄 Audio convertido a: {output_path}")
        return output_path
    except Exception as e:
        logger.error(f"🔴 Error convirtiendo audio: {str(e)}")
        return None

def texto_a_voz(texto, filename, config=None):
    """Convierte texto a audio usando Google TTS y devuelve URL pública verificable."""
    if config is None:
        try:
            from app import obtener_configuracion_por_host
            config = obtener_configuracion_por_host()
        except Exception:
            config = None
    try:
        if gTTS is None:
            logger.error("🔴 texto_a_voz: gTTS no está instalado")
            return None
        import os

        base_dir = os.path.dirname(os.path.abspath(__file__))
        audio_dir = os.path.join(base_dir, 'static', 'audio', 'respuestas')
        os.makedirs(audio_dir, exist_ok=True)

        filepath = os.path.join(audio_dir, f"{filename}.mp3")

        # Generar y guardar MP3
        tts = gTTS(text=texto, lang='es', slow=False)
        tts.save(filepath)

        # Verificar que el archivo se creó
        if not os.path.isfile(filepath):
            logger.error(f"🔴 texto_a_voz: archivo no encontrado después de gTTS: {filepath}")
            return None

        # Construir URL pública robusta
        dominio_conf = None
        try:
            if isinstance(config, dict):
                dominio_conf = config.get('dominio')
        except Exception:
            dominio_conf = None

        dominio = dominio_conf or os.getenv('MI_DOMINIO') or 'http://localhost:5000'
        if not dominio.startswith('http'):
            dominio = 'https://' + dominio

        audio_url = f"{dominio.rstrip('/')}/static/audio/respuestas/{filename}.mp3"

        # Intentar HEAD para validar accesibilidad (no bloqueante en producción)
        try:
            resp = requests.head(audio_url, timeout=6, allow_redirects=True)
            if resp.status_code >= 400:
                logger.warning(f"⚠️ texto_a_voz: HEAD {audio_url} returned {resp.status_code}. The URL may not be publicly accessible.")
            else:
                ct = resp.headers.get('content-type', '')
                logger.info(f"🎵 texto_a_voz: audio saved and reachable. HEAD status {resp.status_code} content-type={ct}")
        except Exception as e:
            logger.warning(f"⚠️ texto_a_voz: unable to HEAD audio_url ({audio_url}): {e}")

        logger.info(f"🌐 URL pública generada: {audio_url} (archivo: {filepath})")
        return audio_url

    except Exception as e:
        logger.error(f"Error en texto_a_voz: {e}")
        return None

def enviar_mensaje(numero, texto, config=None):
    if config is None:
        try:
            from app import obtener_configuracion_por_host
            config = obtener_configuracion_por_host()
        except Exception:
            config = None
    
    # Validar texto
    if not texto or str(texto).strip() == '':
        logger.error("🔴 ERROR: Texto de mensaje vacío")
        return False
    
    texto_limpio = str(texto).strip()
    
    url = f"https://graph.facebook.com/v23.0/{config['phone_number_id']}/messages"
    headers = {
        'Authorization': f'Bearer {config["whatsapp_token"]}',
        'Content-Type': 'application/json'
    }
    
    # ✅ PAYLOAD CORRECTO
    payload = {
        'messaging_product': 'whatsapp',
        'to': numero,
        'type': 'text',
        'text': {
            'body': texto_limpio
        }
    }

    try:
        logger.info(f"📤 Enviando: {texto_limpio[:50]}...")
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if r.status_code == 200:
            logger.info("✅ Mensaje enviado")
            return True
        else:
            logger.error(f"🔴 Error {r.status_code}: {r.text}")
            return False
            
    except Exception as e:
        logger.error(f"🔴 Exception: {e}")
        return False

def enviar_imagen(numero, image_url, config=None):
    """Enviar imagen por link con logging diagnóstico."""
    if config is None:
        try:
            from app import obtener_configuracion_por_host
            config = obtener_configuracion_por_host()
        except Exception:
            config = None

    try:
        cfg = config or {}
        phone_id = cfg.get('phone_number_id') if isinstance(cfg, dict) else None
        token = cfg.get('whatsapp_token') if isinstance(cfg, dict) else None

        if not phone_id or not token:
            logger.error("🔴 enviar_imagen: falta phone_number_id o whatsapp_token (config/ENV)")
            return False

        url = f"https://graph.facebook.com/v23.0/{phone_id}/messages"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
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

def enviar_documento(numero, file_url, filename, config=None):
    """Enviar documento por link con logging diagnóstico."""
    if config is None:
        try:
            from app import obtener_configuracion_por_host
            config = obtener_configuracion_por_host()
        except Exception:
            config = None

    try:
        cfg = config or {}
        phone_id = cfg.get('phone_number_id') if isinstance(cfg, dict) else None
        token = cfg.get('whatsapp_token') if isinstance(cfg, dict) else None

        if not phone_id or not token:
            logger.error("🔴 enviar_documento: falta phone_number_id o whatsapp_token (config/ENV)")
            return False

        url = f"https://graph.facebook.com/v23.0/{phone_id}/messages"
        headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
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

def enviar_mensaje_voz(numero, audio_url, config=None):
    """Enviar audio (voice message) por link con validaciones y logging diagnóstico."""
    if config is None:
        try:
            from app import obtener_configuracion_por_host
            config = obtener_configuracion_por_host()
        except Exception:
            config = None

    try:
        cfg = config or {}
        phone_id = cfg.get('phone_number_id') if isinstance(cfg, dict) else None
        token = cfg.get('whatsapp_token') if isinstance(cfg, dict) else None

        if not phone_id or not token:
            logger.error("🔴 enviar_mensaje_voz: falta phone_number_id o whatsapp_token (config/ENV)")
            return False

        if not audio_url or not audio_url.startswith('http'):
            logger.error(f"🔴 enviar_mensaje_voz: audio_url inválida: {audio_url}")
            return False

        # Verificar que Facebook pueda acceder al archivo (HEAD)
        try:
            head = requests.head(audio_url, timeout=8, allow_redirects=True)
            if head.status_code >= 400:
                logger.error(f"🔴 enviar_mensaje_voz: audio URL not reachable (HEAD {head.status_code}): {audio_url}")
                return False
            content_type = head.headers.get('content-type', '')
            if not content_type.startswith('audio'):
                logger.warning(f"⚠️ enviar_mensaje_voz: content-type no es audio: {content_type}")
        except Exception as e:
            logger.warning(f"⚠️ enviar_mensaje_voz: HEAD check failed for {audio_url}: {e}")
            # no short-circuit — intentaremos enviar pero lo registramos
       
        url = f"https://graph.facebook.com/v23.0/{phone_id}/messages"
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        payload = {
            'messaging_product': 'whatsapp',
            'to': numero,
            'type': 'audio',
            'audio': {
                'link': audio_url
            }
        }

        logger.info(f"📤 enviar_mensaje_voz: enviando audio a {numero} -> {audio_url}")
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        logger.info(f"📥 Graph API status: {r.status_code} response: {r.text[:1000]}")

        if r.status_code in (200, 201, 202):
            logger.info(f"✅ Audio enviado a {numero}")
            return True
        else:
            logger.error(f"🔴 Error enviando audio ({r.status_code}): {r.text}")
            return False
    except Exception as e:
        logger.error(f"🔴 Exception en enviar_mensaje_voz: {e}")
        return False