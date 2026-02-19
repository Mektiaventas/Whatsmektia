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
        try:
            # Ahora que es modular, importamos desde el archivo principal
            # donde reside la lógica de los tenants
            from app import obtener_configuracion_por_host
            config = obtener_configuracion_por_host()
        except ImportError:
            # Si esto falla, es porque el nombre del paquete cambió en el path
            # Intentamos una importación relativa si es necesario
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
        # 1. Configuración de Token y Tenant
        if config is None:
            try:
                from app import obtener_configuracion_por_host
                config = obtener_configuracion_por_host()
            except Exception:
                config = {}
        token = config.get('whatsapp_token') if isinstance(config, dict) else None
        # Detectar el slug del cliente (ej: unilova, ofitodo)
        tenant_slug = config.get('dominio', 'default').split('.')[0] if isinstance(config, dict) else 'default'
        url = f"https://graph.facebook.com/v18.0/{audio_id}"
        headers = {'Authorization': f'Bearer {token}'}
        logger.info(f"📥 Solicitando metadata de audio ({tenant_slug}): {url}")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        metadata = response.json()
        download_url = metadata.get('url')
        audio_response = requests.get(download_url, headers=headers, timeout=30)
        audio_response.raise_for_status()
        # 2. RUTA ORGANIZADA POR CLIENTE
        # Definimos la base y aseguramos que exista la subcarpeta del cliente
        uploads_base = "/home/ubuntu/Whatsmektia/uploads"
        target_dir = os.path.join(uploads_base, "audios", tenant_slug)
        os.makedirs(target_dir, exist_ok=True)
        # El archivo ahora se guarda en: uploads/docs/unilova/audio_xxx.ogg
        audio_path = os.path.join(target_dir, f"audio_{audio_id}.ogg")
        # 3. Guardar el archivo
        with open(audio_path, 'wb') as f:
            f.write(audio_response.content)
        logger.info(f"💾 Audio de {tenant_slug} guardado en: {audio_path}")
        # 4. Generar URL pública USANDO EL PROXY
        # El proxy se encarga de buscarlo en la subcarpeta correcta
        dominio = config.get('dominio', 'unilova.mektia.com')
        audio_url = f"https://{dominio}/proxy-audio/audio_{audio_id}.ogg"
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
    import logging
    from openai import OpenAI
    logger = logging.getLogger(__name__)
    # 1. IDENTIFICAR CLIENTE Y RUTA (CORREGIDO)
    # Detectamos el slug (ej: unilova) desde la config
    tenant_slug = (config.get('dominio', 'default').split('.')[0]) if isinstance(config, dict) else 'default'
    # Definimos la ruta hacia la subcarpeta docs del cliente
    BASE_UPLOAD = "/home/ubuntu/Whatsmektia/uploads"
    TARGET_FOLDER = os.path.join(BASE_UPLOAD, "audios", tenant_slug)
    # Asegurar que la subcarpeta del cliente existe
    os.makedirs(TARGET_FOLDER, exist_ok=True)
    # Limpiamos el filename y definimos la ruta final en la subcarpeta
    clean_filename = filename.replace('.ogg', '').replace('.mp3', '')
    output_path = os.path.join(TARGET_FOLDER, f"{clean_filename}.ogg")
    logger.info(f"🎤 TTS - Texto a procesar: {texto[:50]}...")
    logger.info(f"🎤 TTS - Guardando en: {output_path}")
    # 2. Configuración de API
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    if not OPENAI_API_KEY:
        logger.error("🔴 ERROR: OPENAI_API_KEY no configurada")
        return None
    client = OpenAI(api_key=OPENAI_API_KEY)
    # Definición de voz
    VOZ_A_USAR = voz.strip() if voz and voz.strip() in ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer'] else "nova"
    try:
        # 3. Llamada a OpenAI TTS
        response = client.audio.speech.create(
            model="tts-1",
            voice=VOZ_A_USAR, 
            input=texto,
            response_format="opus" # Formato nativo para WhatsApp
        )
        # 4. Guardar archivo físicamente
        response.stream_to_file(output_path)
        if os.path.exists(output_path):
            file_size = os.path.getsize(output_path)
            logger.info(f"✅ ¡ARCHIVO CREADO! Tamaño: {file_size} bytes")
        else:
            logger.error(f"🔴 ERROR: El archivo no se creó en {output_path}")
            return None
        # 5. Construir URL pública
        # Intentamos sacar el dominio de la config, si no, del env, si no, usamos el de unilova por defecto
        dominio = (config.get('dominio') if isinstance(config, dict) else None) or os.getenv('MI_DOMINIO') or 'unilova.mektia.com'
        
        # Asegurar HTTPS
        if not dominio.startswith('http'):
            dominio = 'https://' + dominio
        dominio = dominio.replace('http://', 'https://')
        audio_url_publica = f"{dominio.rstrip('/')}/proxy-audio/{os.path.basename(output_path)}"
        logger.info(f"🔗 URL generada: {audio_url_publica}")
        return audio_url_publica
    except Exception as e:
        logger.error(f"🔴 EXCEPCIÓN en texto_a_voz: {e}")
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
def enviar_imagen(numero, image_url, texto=None, config=None):
    """
    LA CHULADA CONFIRMADA: Envía imagen + texto (caption) en un solo globo.
    Usa la ruta directa confirmada: https://dominio/uploads/productos/archivo.ext
    """
    try:
        cfg = config or {}
        phone_id = cfg.get('phone_number_id')
        token = cfg.get('whatsapp_token')
        
        # Obtenemos el dominio (unilova.mektia.com)
        dominio = cfg.get('dominio', 'unilova.mektia.com')
        base_url = f"https://{dominio}" if not dominio.startswith('http') else dominio
        
        # Extraemos el nombre del archivo (ej: excel_unzip_img_4_1771354691.jpeg)
        filename = os.path.basename(image_url.strip())
        
        # LA RUTA QUE CONFIRMASTE (OPCIÓN 1)
        public_url = f"{base_url.rstrip('/')}/uploads/productos/{filename}"

        if not phone_id or not token:
            logger.error("🔴 Falta ID o Token en config")
            return False

        url_api = f"https://graph.facebook.com/v21.0/{phone_id}/messages"
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        # Estructura de un solo mensaje (Imagen con pie de foto)
        payload = {
            'messaging_product': 'whatsapp',
            'to': numero,
            'type': 'image',
            'image': {
                'link': public_url,
                'caption': str(texto).strip() if texto else ""
            }
        }

        logger.info(f"🚀 ENVIANDO CHULADA A META: {public_url}")
        r = requests.post(url_api, headers=headers, json=payload, timeout=15)
        
        if r.status_code in (200, 201, 202):
            logger.info(f"✅ ¡OPERACIÓN CERRADA! Imagen enviada a {numero}")
            return True
        else:
            logger.error(f"🔴 Error Meta: {r.text}")
            return False

    except Exception as e:
        logger.error(f"🔴 Error en enviar_imagen: {str(e)}")
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
def enviar_plantilla_comodin(numero, nombre_cliente, mensaje_libre, config):
    return True
    """
    Envía una plantilla de utilidad/marketing para reactivar usuarios fuera de las 24h.
    Rellena {{1}} con el nombre y {{2}} con el mensaje generado por IA.
    """
    NOMBRE_PLANTILLA = "notificacion_general_v2"
    try:
        # Usamos v23.0 para mantener consistencia con el resto de tu archivo
        url = f"https://graph.facebook.com/v23.0/{config['phone_number_id']}/messages"
        headers = {
            "Authorization": f"Bearer {config['whatsapp_token']}",
            "Content-Type": "application/json"
        }
        nombre_final = nombre_cliente if nombre_cliente else "Cliente"
        mensaje_final = mensaje_libre if mensaje_libre else "Hola, ¿seguimos en contacto?"
        data = {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "template",
            "template": {
                "name": NOMBRE_PLANTILLA,
                "language": { "code": "es_MX" },
                "components": [
                    {
                        "type": "body",
                        "parameters": [
                            { "type": "text", "text": nombre_final },
                            { "type": "text", "text": mensaje_final }
                        ]
                    }
                ]
            }
        }
        response = requests.post(url, headers=headers, json=data, timeout=15)
        if response.status_code in [200, 201, 202]:
            logger.info(f"✅ Plantilla comodín enviada a {numero}")
            return True
        else:
            logger.error(f"🔴 Error enviando plantilla: {response.text}")
            return False
    except Exception as e:
        logger.error(f"🔴 Excepción en enviar_plantilla_comodin: {e}")
        return False
