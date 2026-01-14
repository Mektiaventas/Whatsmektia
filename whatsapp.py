# (entire file replaced, only enviar_imagen modified to build public URLs from filename
#  instead of searching tenant-local filesystem or uploading local files)
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
    """Obtiene la imagen de WhatsApp, la convierte a base64 y guarda localmente EN UPLOAD_FOLDER"""
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
        
        # --- INICIO DE LA CORRECCIÓN ---
        
        # 3. Guardar la imagen en UPLOAD_FOLDER (importado de app.py)
        try:
            from app import UPLOAD_FOLDER
        except ImportError:
            logger.warning("Could not import UPLOAD_FOLDER from app, using fallback path.")
            UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
            
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        
        # Nombre seguro para el archivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = secure_filename(f"whatsapp_image_{timestamp}.jpg")
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        with open(filepath, 'wb') as f:
            f.write(image_response.content)
        
        # 4. Convertir a base64 para OpenAI (si es necesario)
        image_base64 = base64.b64encode(image_response.content).decode('utf-8')
        base64_string = f"data:{mime_type};base64,{image_base64}"
        
        # 5. URL pública: DEBE SER SOLO EL NOMBRE DEL ARCHIVO
        public_url = filename
        
        # --- FIN DE LA CORRECCIÓN ---
        
        logger.info(f"✅ Imagen guardada: {filepath}")
        logger.info(f"🌐 URL web (para DB): {public_url}")
        
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

def texto_a_voz(texto, filename, config=None, voz=None):
    """
    Convierte texto a audio usando la API de OpenAI TTS (tts-1), lo guarda como OGG/OPUS
    y devuelve la URL pública para WhatsApp.
    """
    import os
    import requests
    from openai import OpenAI
    from urllib.parse import urlparse
    import logging
    
    logger = logging.getLogger(__name__)
    
    # AGREGAR LOS LOGS DE DEPURACIÓN
    logger.info(f"🎤 DEBUG texto_a_voz - Entrando con texto: {texto[:100]}...")
    logger.info(f"🎤 DEBUG texto_a_voz - filename: {filename}, voz: {voz}")
    
    # Obtener OPENAI_API_KEY de las variables de entorno
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    logger.info(f"🎤 DEBUG texto_a_voz - OPENAI_API_KEY configurada: {'Sí' if OPENAI_API_KEY else 'No'}")
    
    if not OPENAI_API_KEY:
        logger.error("🔴 La clave de OPENAI_API_KEY no está configurada.")
        return None

    client = OpenAI(api_key=OPENAI_API_KEY)
    
    # 1. Definición del Tono/Voz
    VOZ_DEFECTO = "nova"
    if voz and isinstance(voz, str) and voz.strip() in ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']:
        VOZ_A_USAR = voz.strip()
    else:
        VOZ_A_USAR = VOZ_DEFECTO

    # Definir UPLOAD_FOLDER (usar variable de entorno o ruta por defecto)
    UPLOAD_FOLDER = os.getenv('UPLOAD_FOLDER') or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'uploads')
    logger.info(f"🎤 DEBUG texto_a_voz - UPLOAD_FOLDER: {UPLOAD_FOLDER}")
    
    # Asegurar que el directorio existe
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    
    output_path = os.path.join(UPLOAD_FOLDER, f"{filename}.ogg")
    
    try:
        # 2. Llamada a la API de OpenAI TTS
        logger.info(f"🎤 DEBUG texto_a_voz - Llamando a OpenAI TTS con voz: {VOZ_A_USAR}")
        response = client.audio.speech.create(
            model="tts-1",
            voice=VOZ_A_USAR, 
            input=texto,
            response_format="opus" # <-- Formato requerido por Telegram
        )
        
        # 3. Guardar archivo OGG/OPUS (ruta local)
        response.stream_to_file(output_path)
        
        # AGREGAR LOG DESPUÉS DE GUARDAR EL ARCHIVO
        logger.info(f"🎤 DEBUG texto_a_voz - Audio generado en: {output_path}")
        logger.info(f"🎤 DEBUG texto_a_voz - Tamaño del archivo: {os.path.getsize(output_path) if os.path.exists(output_path) else 0} bytes")
        
        # 4. Construir URL pública (para WhatsApp)
        dominio_conf = config.get('dominio') if isinstance(config, dict) else None
        dominio = dominio_conf or os.getenv('MI_DOMINIO') or 'http://localhost:5000'
        
        # 💥 FORZAR HTTPS para compatibilidad total con WhatsApp y Telegram
        if not dominio.startswith('http'):
            dominio = 'https://' + dominio
        if dominio.startswith('http://'):
             dominio = dominio.replace('http://', 'https://')

        # Asumir que /uploads/ es servido públicamente (o usar /proxy-audio/ si está configurado)
        # Usaremos el proxy que configuramos en app.py para servirlo desde la ruta local de forma segura
        audio_url_publica = f"{dominio.rstrip('/')}/proxy-audio/{os.path.basename(output_path)}"

        # AGREGAR LOG CON LA URL PÚBLICA
        logger.info(f"🎤 DEBUG texto_a_voz - URL pública: {audio_url_publica}")
        
        logger.info(f"🌐 URL pública generada (proxy): {audio_url_publica} (Ruta local: {output_path})")
        
        # DEVOLVER la URL pública, aunque el archivo exista localmente
        return audio_url_publica
        
    except Exception as e:
        logger.error(f"🔴 Error al llamar a la API de OpenAI TTS: {e}")
        import traceback
        logger.error(f"🔴 Traceback: {traceback.format_exc()}")
        return None


def enviar_mensaje(numero, texto, config=None):
    if config is None:
        try:
            # Asume que app.py define esta función
            from app import obtener_configuracion_por_host
            config = obtener_configuracion_por_host()
        except Exception:
            config = None
            logger.error("🔴 enviar_mensaje: No se pudo cargar la configuración por host")
            return False
    
    # --- INICIO LÓGICA MULTI-TENANT ---

    # 1. LÓGICA DE ENVÍO POR MESSENGER (fb_)
    if numero.startswith('fb_'):
        # 'config' debe contener 'page_access_token' inyectado por obtener_configuracion_por_page_id
        PAGE_ACCESS_TOKEN = config.get('page_access_token') 
        sender_id = numero.replace('fb_', '')
        
        if not PAGE_ACCESS_TOKEN:
            logger.error(f"❌ MESSENGER: No se encontró Page Access Token para {config.get('dominio')}")
            return False

        # Usamos v19.0 como en el webhook de app.py
        url = f"https://graph.facebook.com/v19.0/me/messages?access_token={PAGE_ACCESS_TOKEN}"
        
        payload = {
            "messaging_type": "RESPONSE",
            "recipient": { "id": sender_id },
            "message": { "text": texto }
        }
        
        try:
            logger.info(f"📤 Enviando (Messenger): {texto[:50]}...")
            r = requests.post(url, json=payload, timeout=10)
            
            if r.status_code == 200:
                logger.info("✅ Mensaje (Messenger) enviado")
                return True
            else:
                logger.error(f"🔴 Error (Messenger) {r.status_code}: {r.text}")
                return False
        except Exception as e:
            logger.error(f"🔴 Exception (Messenger): {e}")
            return False

    # 2. LÓGICA DE ENVÍO POR WHATSAPP (Lógica existente)
    
    # Validar texto
    if not texto or str(texto).strip() == '':
        logger.error("🔴 ERROR: Texto de mensaje vacío")
        return False
    
    texto_limpio = str(texto).strip()
    
    # Usamos v23.0 como en tu archivo original de whatsapp.py
    url = f"https://graph.facebook.com/v23.0/{config['phone_number_id']}/messages"
    headers = {
        'Authorization': f'Bearer {config["whatsapp_token"]}',
        'Content-Type': 'application/json'
    }
    
    # PAYLOAD CORRECTO
    payload = {
        'messaging_product': 'whatsapp',
        'to': numero,
        'type': 'text',
        'text': {
            'body': texto_limpio
        }
    }

    try:
        logger.info(f"📤 Enviando (WhatsApp): {texto_limpio[:50]}...")
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if r.status_code == 200:
            logger.info("✅ Mensaje (WhatsApp) enviado")
            return True
        else:
            logger.error(f"🔴 Error (WhatsApp) {r.status_code}: {r.text}")
            return False
            
    except Exception as e:
        logger.error(f"🔴 Exception (WhatsApp): {e}")
        return False 

def enviar_imagen(numero, image_url, config=None):
    """Enviar imagen: si se pasa nombre de archivo simple, construir URL pública usando config['dominio']
       y enviar por link. NO buscar archivos en disco ni subirlos a Graph en este versión.
    """
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

        if not isinstance(image_url, str) or not image_url.strip():
            logger.error("🔴 enviar_imagen: image_url inválida")
            return False

        img = image_url.strip()

        # If already absolute URL or data: use as-is
        if img.startswith('http://') or img.startswith('https://') or img.startswith('data:'):
            public_url = img
            logger.info(f"ℹ️ enviar_imagen: recibida URL absoluta/data, enviando tal cual: {public_url}")
        else:
            # Treat the value as a filename (basename) and build candidate public URLs using tenant/domain
            dominio = None
            tenant_slug = None
            try:
                dominio = cfg.get('dominio') or os.getenv('MI_DOMINIO')
            except Exception:
                dominio = os.getenv('MI_DOMINIO', None)
            if not dominio:
                # last-resort: try request.url_root if running in request context
                try:
                    from flask import request
                    dominio = request.url_root.rstrip('/')
                except Exception:
                    dominio = None

            # derive tenant slug from domain if possible
            if dominio:
                if dominio.startswith('http'):
                    host_part = dominio.replace('https://', '').replace('http://', '').split('/')[0]
                else:
                    host_part = dominio.split('/')[0]
                tenant_slug = host_part.split('.')[0] if host_part else None

            # Build ordered candidate URLs (tenant-aware first)
            candidates = []
            filename_only = os.path.basename(img)
            if dominio:
                base = dominio if dominio.startswith('http') else f"https://{dominio}"
                if tenant_slug:
                    candidates.append(f"{base.rstrip('/')}/uploads/productos/{tenant_slug}/{filename_only}")
                candidates.append(f"{base.rstrip('/')}/uploads/productos/{filename_only}")
                candidates.append(f"{base.rstrip('/')}/uploads/{filename_only}")
                candidates.append(f"{base.rstrip('/')}/static/images/{filename_only}")
            else:
                # fallback: relative paths (Graph likely can't fetch these)
                candidates.append(f"/uploads/productos/{filename_only}")
                candidates.append(f"/uploads/{filename_only}")
                candidates.append(f"/static/images/{filename_only}")

            # Try HEAD on candidates and pick first reachable (status < 400)
            public_url = None
            for c in candidates:
                try:
                    # Only perform HEAD on absolute URLs (start with http)
                    if c.startswith('http://') or c.startswith('https://'):
                        head = requests.head(c, timeout=6, allow_redirects=True)
                        if head.status_code < 400:
                            public_url = c
                            logger.info(f"✅ enviar_imagen: candidate reachable (HEAD {head.status_code}): {c}")
                            break
                        else:
                            logger.info(f"⚠️ enviar_imagen: candidate HEAD returned {head.status_code}: {c}")
                    else:
                        # not absolute -> skip HEAD but remember as fallback
                        if public_url is None:
                            public_url = c
                except Exception as e:
                    logger.info(f"⚠️ enviar_imagen: HEAD check failed for {c}: {e}")
                    # keep trying next candidate

            # If none reachable, use the first candidate (allow Graph to attempt fetch)
            if not public_url and candidates:
                public_url = candidates[0]
                logger.warning(f"⚠️ enviar_imagen: ningún candidate HEAD OK; usando fallback candidate: {public_url}")

        # Send image by link using Graph API
        try:
            url = f"https://graph.facebook.com/v23.0/{phone_id}/messages"
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            payload = {'messaging_product':'whatsapp','to':numero,'type':'image','image':{'link': public_url}}
            logger.info(f"📤 enviar_imagen (link) -> to={numero} phone_number_id={phone_id} image_link={public_url}")
            r = requests.post(url, headers=headers, json=payload, timeout=15)
            status = getattr(r, 'status_code', 'n/a')
            body_preview = (r.text or '')[:1000]
            if status in (200, 201, 202):
                logger.info(f"✅ enviar_imagen OK (status={status}) - resp_preview: {body_preview}")
                return True
            logger.error(f"🔴 enviar_imagen FAILED status={status} - resp_preview: {body_preview}")
            return False
        except Exception as e:
            logger.error(f"🔴 Exception sending image link: {e}")
            return False

    except Exception as e:
        logger.error(f"Exception enviar_imagen: {e}")
        return False

def enviar_documento(numero, file_url, filename, config=None):
    """Enviar documento por link con logging diagnóstico y mejor manejo de URLs."""
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

        # Asegurar que file_url sea HTTPS (WhatsApp requiere HTTPS)
        if file_url.startswith('http://'):
            file_url = file_url.replace('http://', 'https://')
        elif not file_url.startswith('https://'):
            # Si es una ruta relativa o nombre de archivo, construir URL completa
            dominio = cfg.get('dominio') or os.getenv('MI_DOMINIO')
            if not dominio:
                try:
                    from flask import request
                    if request:
                        dominio = request.url_root.rstrip('/')
                except:
                    dominio = 'https://localhost:5000'
            
            if not dominio.startswith('http'):
                dominio = f"https://{dominio}"
            elif dominio.startswith('http://'):
                dominio = dominio.replace('http://', 'https://')
            
            # Construir URL completa para WhatsApp
            file_url = f"{dominio.rstrip('/')}/uploads/{os.path.basename(file_url)}"

        # WhatsApp requiere que el archivo sea accesible públicamente
        # Verificar si la URL es accesible
        try:
            import requests
            verify_response = requests.head(file_url, timeout=10, allow_redirects=True)
            if verify_response.status_code != 200:
                logger.warning(f"⚠️ URL no accesible directamente: {file_url}")
                # Intentar usar proxy si está disponible
                if '/uploads/' in file_url:
                    file_url = file_url.replace('/uploads/', '/proxy-file/')
        except Exception as verify_error:
            logger.warning(f"⚠️ No se pudo verificar URL: {verify_error}")

        url = f"https://graph.facebook.com/v23.0/{phone_id}/messages"
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Limitar longitud del filename para WhatsApp (max 240 chars)
        safe_filename = filename[:240]
        
        payload = {
            'messaging_product': 'whatsapp',
            'to': numero,
            'type': 'document',
            'document': {
                'link': file_url,
                'filename': safe_filename
            }
        }

        logger.info(f"📤 enviar_documento -> to={numero} filename={safe_filename}")
        logger.info(f"📤 URL del documento: {file_url}")
        
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=30)
            
            status = r.status_code
            try:
                body_preview = r.text[:500] if r.text else '<empty-response>'
            except Exception:
                body_preview = '<unreadable-response-body>'

            if status in (200, 201, 202):
                logger.info(f"✅ enviar_documento OK (status={status})")
                return True
            else:
                logger.error(f"🔴 enviar_documento FAILED status={status}")
                logger.error(f"🔴 Response: {body_preview}")
                
                # Intentar debug adicional
                try:
                    error_json = r.json()
                    logger.error(f"🔴 Error details: {error_json}")
                    
                    # Si es error de URL, intentar alternativas
                    if 'error' in error_json and 'message' in error_json['error']:
                        error_msg = error_json['error']['message']
                        if 'URL' in error_msg or 'unreachable' in error_msg:
                            logger.error(f"🔴 Problema con la URL del documento: {error_msg}")
                            # Intentar con URL directa si estamos usando proxy
                            if '/proxy-file/' in file_url:
                                direct_url = file_url.replace('/proxy-file/', '/uploads/')
                                logger.info(f"🔄 Intentando con URL directa: {direct_url}")
                                payload['document']['link'] = direct_url
                                r2 = requests.post(url, headers=headers, json=payload, timeout=30)
                                if r2.status_code in (200, 201, 202):
                                    logger.info(f"✅ enviar_documento OK con URL directa")
                                    return True
                except:
                    pass
                    
                return False
                
        except requests.exceptions.Timeout:
            logger.error(f"🔴 Timeout enviando documento a {numero}")
            return False
        except requests.exceptions.ConnectionError:
            logger.error(f"🔴 Connection error enviando documento a {numero}")
            return False
            
    except Exception as e:
        logger.error(f"Exception enviar_documento: {e}")
        import traceback
        logger.error(traceback.format_exc())
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

        if not audio_url or not isinstance(audio_url, str):
            logger.error(f"🔴 enviar_mensaje_voz: audio_url inválida: {audio_url}")
            return False

        # WhatsApp requiere HTTPS y URL accesible
        if audio_url.startswith('http://'):
            audio_url = audio_url.replace('http://', 'https://')
        elif not audio_url.startswith('https://'):
            # Si es una ruta relativa, construir URL completa
            dominio = cfg.get('dominio') or os.getenv('MI_DOMINIO')
            if not dominio:
                try:
                    from flask import request
                    dominio = request.url_root.rstrip('/')
                except:
                    dominio = 'https://localhost:5000'
            
            if not dominio.startswith('http'):
                dominio = f"https://{dominio}"
            elif dominio.startswith('http://'):
                dominio = dominio.replace('http://', 'https://')
            
            # Extraer solo el nombre del archivo
            if '/' in audio_url:
                filename = audio_url.split('/')[-1]
            else:
                filename = audio_url
            
            audio_url = f"{dominio.rstrip('/')}/uploads/{filename}"

        # IMPORTANTE: WhatsApp necesita que el audio sea accesible públicamente
        # Verificar accesibilidad de la URL
        try:
            if audio_url.startswith('https://'):
                headers = {'User-Agent': 'Mozilla/5.0 (WhatsApp)'}
                head = requests.head(audio_url, timeout=10, allow_redirects=True, headers=headers)
                
                logger.info(f"🔗 Verificación URL audio: HTTP {head.status_code}, Content-Type: {head.headers.get('content-type')}")
                
                if head.status_code != 200:
                    logger.warning(f"⚠️ audio URL not directly accessible (HEAD {head.status_code}): {audio_url}")
                    
                    # Intentar con proxy si la URL tiene /uploads/
                    if '/uploads/' in audio_url:
                        proxy_url = audio_url.replace('/uploads/', '/proxy-audio/')
                        logger.info(f"🔄 Intentando con proxy: {proxy_url}")
                        
                        # Verificar si el proxy funciona
                        head2 = requests.head(proxy_url, timeout=8, allow_redirects=True)
                        if head2.status_code == 200:
                            audio_url = proxy_url
                            logger.info(f"✅ Usando proxy para audio")
                        
                # Verificar tipo de contenido
                content_type = head.headers.get('content-type', '').lower()
                if 'audio' not in content_type and 'ogg' not in content_type and 'mpeg' not in content_type:
                    logger.warning(f"⚠️ Content-Type no es audio: {content_type}")
                    
        except Exception as e:
            logger.warning(f"⚠️ enviar_mensaje_voz: HEAD check failed for {audio_url}: {e}")
            # Continuar de todas formas - WhatsApp verificará por su lado
        
        # WhatsApp Graph API endpoint
        url = f"https://graph.facebook.com/v23.0/{phone_id}/messages"
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }

        # IMPORTANTE: WhatsApp necesita que los audios de voz usen type: 'audio'
        payload = {
            'messaging_product': 'whatsapp',
            'to': numero,
            'type': 'audio',
            'audio': {
                'link': audio_url
            }
        }

        logger.info(f"📤 enviar_mensaje_voz: enviando audio a {numero}")
        logger.info(f"🔗 URL de audio: {audio_url}")
        
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=20)
            
            logger.info(f"📥 Graph API status: {r.status_code}")
            
            if r.status_code in (200, 201, 202):
                logger.info(f"✅ Audio de voz enviado exitosamente a {numero}")
                return True
            else:
                # Intentar parsear el error
                try:
                    error_json = r.json()
                    logger.error(f"🔴 Error enviando audio ({r.status_code}): {error_json}")
                    
                    # Si es error de URL, intentar verificar la accesibilidad
                    if 'error' in error_json and 'message' in error_json['error']:
                        error_msg = error_json['error']['message']
                        if 'URL' in error_msg or 'unreachable' in error_msg or 'supported' in error_msg:
                            logger.error(f"🔴 Problema con el audio: {error_msg}")
                            
                            # Intentar enviar como documento si falla como audio de voz
                            logger.info(f"🔄 Intentando enviar como documento...")
                            return enviar_documento(numero, audio_url, "audio.ogg", config)
                except:
                    logger.error(f"🔴 Error enviando audio ({r.status_code}): {r.text[:200]}")
                
                return False
                
        except requests.exceptions.Timeout:
            logger.error(f"🔴 Timeout enviando audio a {numero}")
            return False
        except requests.exceptions.ConnectionError:
            logger.error(f"🔴 Connection error enviando audio a {numero}")
            return False
            
    except Exception as e:
        logger.error(f"🔴 Exception en enviar_mensaje_voz: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False 
