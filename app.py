# Agrega esto con los otros imports al inicio
import traceback
# Agrega estos imports al inicio del archivo
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import hashlib
import time
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account
import pytz
import os
import logging
import json 
import base64
import argparse
import mysql.connector
from flask import Flask, send_from_directory, Response, request, render_template, redirect, url_for, abort, flash, jsonify
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
from decimal import Decimal
import re
import io
from flask import current_app as app
from werkzeug.utils import secure_filename
from pydub import AudioSegment
from PIL import Image
from openai import OpenAI
processed_messages = {}

# Configurar Gemini

tz_mx = pytz.timezone('America/Mexico_City')
guardado = True
load_dotenv()  # Cargar desde archivo específico
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cualquier-cosa")
app.logger.setLevel(logging.INFO)

# ——— Env vars ———

GOOGLE_CLIENT_SECRET_FILE = os.getenv("GOOGLE_CLIENT_SECRET_FILE")    
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ALERT_NUMBER = os.getenv("ALERT_NUMBER")
SECRET_KEY = os.getenv("SECRET_KEY", "cualquier-cosa")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
IA_ESTADOS = {}
client = OpenAI(api_key=OPENAI_API_KEY)  # ✅
# ——— Configuración Multi-Tenant ———
NUMEROS_CONFIG = {
    '524495486142': {  # Número de Mektia
        'phone_number_id': os.getenv("MEKTIA_PHONE_NUMBER_ID"),
        'whatsapp_token': os.getenv("MEKTIA_WHATSAPP_TOKEN"),
        'db_host': os.getenv("MEKTIA_DB_HOST"),
        'db_user': os.getenv("MEKTIA_DB_USER"),
        'db_password': os.getenv("MEKTIA_DB_PASSWORD"),
        'db_name': os.getenv("MEKTIA_DB_NAME"),
        'dominio': 'mektia.com'
    },
    '524812372326': {  # Número de La Porfirianna
        'phone_number_id': os.getenv("PORFIRIANNA_PHONE_NUMBER_ID"),
        'whatsapp_token': os.getenv("PORFIRIANNA_WHATSAPP_TOKEN"),
        'db_host': os.getenv("PORFIRIANNA_DB_HOST"),
        'db_user': os.getenv("PORFIRIANNA_DB_USER"),
        'db_password': os.getenv("PORFIRIANNA_DB_PASSWORD"),
        'db_name': os.getenv("PORFIRIANNA_DB_NAME"),
        'dominio': 'laporfirianna.mektia.com'
    }
}

soli = "cita"
servicios_clave = [
            'página web', 'sitio web', 'ecommerce', 'tienda online',
            'aplicación', 'app', 'software', 'sistema',
            'marketing', 'seo', 'redes sociales', 'publicidad',
            'diseño', 'branding', 'logo', 'identidad visual',
            'hosting', 'dominio', 'mantenimiento', 'soporte',
            'electronica', 'hardware', 'iot', 'internet de las cosas',
        ]    

# Configuración por defecto (para backward compatibility)
# Por esto (valores explícitos en lugar de llamar a la función):
DEFAULT_CONFIG = NUMEROS_CONFIG['524495486142']
WHATSAPP_TOKEN = DEFAULT_CONFIG['whatsapp_token']
DB_HOST = DEFAULT_CONFIG['db_host']
DB_USER = DEFAULT_CONFIG['db_user']
DB_PASSWORD = DEFAULT_CONFIG['db_password']
DB_NAME = DEFAULT_CONFIG['db_name']
MI_NUMERO_BOT = DEFAULT_CONFIG['phone_number_id']
PHONE_NUMBER_ID = MI_NUMERO_BOT
# Agrega esto después de las otras variables de configuración
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Diccionario de prefijos a código de país
PREFIJOS_PAIS = {
    '52': 'mx', '1': 'us', '54': 'ar', '57': 'co', '55': 'br',
    '34': 'es', '51': 'pe', '56': 'cl', '58': 've', '593': 'ec',
    '591': 'bo', '507': 'pa', '502': 'gt'
}

app.jinja_env.filters['bandera'] = lambda numero: get_country_flag(numero)

def get_db_connection(config=None):
    if config is None:
        try:
            # Solo intentar obtener configuración por host si hay contexto de solicitud
            from flask import has_request_context
            if has_request_context():
                config = obtener_configuracion_por_host()
            else:
                config = NUMEROS_CONFIG['524495486142']  # Default
        except Exception as e:
            app.logger.error(f"Error obteniendo configuración: {e}")
            # Fallback a configuración por defecto
            config = NUMEROS_CONFIG['524495486142']
    
    app.logger.info(f"🗄️ Conectando a BD: {config['db_name']}")
    
    try:
        return mysql.connector.connect(
            host=config['db_host'],
            user=config['db_user'],
            password=config['db_password'],
            database=config['db_name']
        )
    except Exception as e:
        app.logger.error(f"Error conectando a BD {config['db_name']}: {e}")
        raise

# ——— Función para enviar mensajes de voz ———
def enviar_mensaje_voz(numero, audio_url, config=None):
    """Envía un mensaje de voz por WhatsApp"""
    if config is None:
        config = obtener_configuracion_por_host()
    if config is None:
        config = obtener_configuracion_numero(numero)
    
    url = f"https://graph.facebook.com/v23.0/{config['phone_number_id']}/messages"
    headers = {
        'Authorization': f'Bearer {config['whatsapp_token']}',
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
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        app.logger.info(f"✅ Audio enviado a {numero}")
        return True
    except Exception as e:
        app.logger.error(f"🔴 Error enviando audio: {e}")
        return False
    
def texto_a_voz(texto, filename,config=None):
    """Convierte texto a audio usando Google TTS"""
    if config is None:
        config = obtener_configuracion_por_host()
    try:
        from gtts import gTTS
        import os
        
        # ✅ Ruta ABSOLUTA para evitar problemas
        base_dir = os.path.dirname(os.path.abspath(__file__))
        audio_dir = os.path.join(base_dir, 'static', 'audio', 'respuestas')
        
        # Crear directorio si no existe
        os.makedirs(audio_dir, exist_ok=True)
        
        # Ruta completa del archivo
        filepath = os.path.join(audio_dir, f"{filename}.mp3")
        
        # Convertir texto a voz
        tts = gTTS(text=texto, lang='es', slow=False)
        tts.save(filepath)
        
        # ✅ URL PÚBLICA - Usa tu dominio real
        MI_DOMINIO = os.getenv('MI_DOMINIO', 'https://tu-dominio.com')
        audio_url = f"{MI_DOMINIO}/static/audio/respuestas/{filename}.mp3"
        
        app.logger.info(f"🎵 Audio guardado en: {filepath}")
        app.logger.info(f"🌐 URL pública: {audio_url}")
        
        return audio_url
        
    except Exception as e:
        app.logger.error(f"Error en texto a voz: {e}")
        return None

def detectar_solicitud_cita_ia(mensaje, numero, config=None):
    """Usa DeepSeek para detectar si el mensaje es una solicitud de cita/pedido"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    # 🔥 AGREGAR LOGGING DETALLADO
    app.logger.info(f"🎯 Analizando mensaje para pedido: '{mensaje}'")
    
    # Primero verificar con la lista de palabras clave existente (más rápida)
    deteccion_keywords = detectar_solicitud_cita_keywords(mensaje)
    app.logger.info(f"🔍 Detección por keywords: {deteccion_keywords}")
    
    if deteccion_keywords:
        return True
    
    # Si no se detectó con keywords, usar IA para análisis semántico
    try:
        # 🔥 MEJORAR EL PROMPT PARA LA PORFIRIANNA
        prompt = f"""
        Evalúa si el siguiente mensaje indica que el usuario quiere hacer un PEDIDO de comida.
        Responde SOLO con "SI" o "NO".
        
        Mensaje: "{mensaje}"
        
        Considera que podría ser un pedido si:
        - Confirma un platillo específico (chilaquiles, tacos, gorditas, etc.)
        - Proporciona su nombre para el pedido
        - Menciona forma de pago (efectivo, transferencia, etc.)
        - Confirma ingredientes o especificaciones ("con todo", "sin cebolla", etc.)
        - Responde a preguntas previas sobre el pedido
        
        Responde "SI" si es una confirmación o continuación de un pedido.
        Responde "NO" solo si es completamente irrelevante para hacer un pedido.
        """
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 10
        }
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        respuesta_ia = data['choices'][0]['message']['content'].strip().upper()
        
        app.logger.info(f"🔍 IA detectó solicitud de pedido: {respuesta_ia}")
        
        return "SI" in respuesta_ia
        
    except Exception as e:
        app.logger.error(f"Error en detección IA de pedido: {e}")
        # Fallback a detección por keywords si la IA falla
        return detectar_solicitud_cita_keywords(mensaje)
    
def autenticar_google_calendar(config=None):
    """Autentica con OAuth usando client_secret.json"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    SCOPES = ['https://www.googleapis.com/auth/calendar']
    creds = None
    
    try:
        app.logger.info("🔐 Intentando autenticar con OAuth...")
        
        # 1. Verificar si ya tenemos token guardado
        if os.path.exists('token.json'):
            try:
                creds = Credentials.from_authorized_user_file('token.json', SCOPES)
                if creds and creds.valid:
                    app.logger.info("✅ Token OAuth válido encontrado")
                    service = build('calendar', 'v3', credentials=creds)
                    return service
                elif creds and creds.expired and creds.refresh_token:
                    app.logger.info("🔄 Refrescando token expirado...")
                    creds.refresh(Request())
                    with open('token.json', 'w') as token:
                        token.write(creds.to_json())
                    service = build('calendar', 'v3', credentials=creds)
                    return service
            except Exception as e:
                app.logger.error(f"❌ Error con token existente: {e}")
        
        # 2. Si no hay token válido, hacer flujo OAuth
        if not os.path.exists('client_secret.json'):
            app.logger.error("❌ No se encuentra client_secret.json")
            return None
        
        try:
            flow = InstalledAppFlow.from_client_secrets_file(
                'client_secret.json', SCOPES)
            
            # Para servidor, genera una URL para autorizar manualmente
            auth_url, _ = flow.authorization_url(prompt='consent')
            
            app.logger.info(f"🌐 Por favor visita esta URL para autorizar: {auth_url}")
            app.logger.info("📋 Después de autorizar, copia el código de autorización que te da Google")
            
            # En entorno de servidor, necesitamos manejar el código manualmente
            code = input("Pega el código de autorización aquí: ") if app.debug else None
            
            if code:
                flow.fetch_token(code=code)
                creds = flow.credentials
                
                # Guardar las credenciales
                with open('token.json', 'w') as token:
                    token.write(creds.to_json())
                
                app.logger.info("✅ Autenticación OAuth exitosa")
                service = build('calendar', 'v3', credentials=creds)
                return service
            else:
                app.logger.error("❌ No se proporcionó código de autorización")
                return None
                
        except Exception as e:
            app.logger.error(f"❌ Error en autenticación OAuth: {e}")
            return None
            
    except Exception as e:
        app.logger.error(f'❌ Error inesperado: {e}')
        app.logger.error(traceback.format_exc())
        return None

@app.route('/autorizar-manual')
def autorizar_manual():
    """Endpoint para autorizar manualmente con Google"""
    try:
        SCOPES = ['https://www.googleapis.com/auth/calendar']
        
        if not os.path.exists('client_secret.json'):
            return "❌ Error: No se encuentra client_secret.json"
        
        # Obtener el host actual de la solicitud
        host = request.host
        app.logger.info(f"🔍 Host actual en autorizar_manual: {host}")
        
        # Construir la URI de redirección basada en el host actual
        redirect_uri = f'https://{host}/completar-autorizacion'
        app.logger.info(f"🔐 URI de redirección en autorizar_manual: {redirect_uri}")
        
        flow = InstalledAppFlow.from_client_secrets_file(
            'client_secret.json', 
            SCOPES,
            redirect_uri=redirect_uri
        )
        
        # Generar URL de autorización
        auth_url, _ = flow.authorization_url(
            prompt='consent', 
            access_type='offline',
            include_granted_scopes='true'
        )
        
        app.logger.info(f"🌐 URL de autorización generada: {auth_url}")
        
        return f'''
        <h1>✅ Autorización Google Calendar</h1>
        <p>Por favor visita esta URL para autorizar:</p>
        <a href="{auth_url}" target="_blank">{auth_url}</a>
        <p>Después de autorizar, Google te dará un código. Pégalo aquí:</p>
        <form action="/procesar-codigo" method="post">
            <input type="text" name="codigo" placeholder="Pega el código aquí" size="50">
            <input type="submit" value="Enviar">
        </form>
        '''
        
    except Exception as e:
        app.logger.error(f"❌ Error en autorización manual: {str(e)}")
        return f"❌ Error: {str(e)}"
    
def crear_evento_calendar(service, cita_info, config=None):
    """Crea un evento en Google Calendar para la cita"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # Determinar el tipo de negocio
        es_porfirianna = 'laporfirianna' in config.get('dominio', '')
        
        # Formatear fecha y hora (solo para Mektia)
        if not es_porfirianna:
            start_time = f"{cita_info['fecha_sugerida']}T{cita_info['hora_sugerida']}:00"
            end_time_dt = datetime.strptime(f"{cita_info['fecha_sugerida']} {cita_info['hora_sugerida']}", 
                                          "%Y-%m-%d %H:%M") + timedelta(hours=1)
            end_time = end_time_dt.strftime("%Y-%m-%dT%H:%M:00")
        else:
            # Para La Porfirianna, usar la hora actual + 1 hora
            now = datetime.now()
            start_time = now.isoformat()
            end_time = (now + timedelta(hours=1)).isoformat()
        
        # Crear el evento
        event = {
            'summary': f"{'Pedido' if es_porfirianna else 'Cita'} - {cita_info['nombre_cliente']}",
            'description': f"""
{'Platillo' if es_porfirianna else 'Servicio'}: {cita_info.get('servicio_solicitado', 'No especificado')}
Cliente: {cita_info.get('nombre_cliente', 'No especificado')}
Teléfono: {cita_info.get('telefono', 'No especificado')}
Notas: {'Pedido' if es_porfirianna else 'Cita'} agendado automáticamente desde WhatsApp
            """.strip(),
            'start': {
                'dateTime': start_time,
                'timeZone': 'America/Mexico_City',
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'America/Mexico_City',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 30},
                    {'method': 'email', 'minutes': 24 * 60},  # 1 día antes
                ],
            },
        }
        
        calendar_id = os.getenv('GOOGLE_CALENDAR_ID', 'primary')
        event = service.events().insert(calendarId=calendar_id, body=event).execute()
        
        app.logger.info(f'Evento creado: {event.get("htmlLink")}')
        return event.get('id')  # Retorna el ID del evento
        
    except HttpError as error:
        app.logger.error(f'Error al crear evento: {error}')
        return None
    
def validar_datos_cita_completos(info_cita, config=None):
    """
    Valida que la información de la cita/pedido tenga todos los datos necesarios
    Devuelve (True, None) si está completa, (False, mensaje_error) si faltan datos
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    # Determinar el tipo de negocio
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    
    datos_requeridos = []
    
    # Validar servicio solicitado (siempre requerido)
    if not info_cita.get('servicio_solicitado') or info_cita.get('servicio_solicitado') == 'null':
        if es_porfirianna:
            datos_requeridos.append("qué platillo deseas ordenar")
        else:
            datos_requeridos.append("qué servicio necesitas")
    
    # Validar fecha (solo requerido para Mektia)
    if not es_porfirianna and (not info_cita.get('fecha_sugerida') or info_cita.get('fecha_sugerida') == 'null'):
        datos_requeridos.append("fecha preferida")
    
    # Validar nombre del cliente (siempre requerido)
    if not info_cita.get('nombre_cliente') or info_cita.get('nombre_cliente') == 'null':
        datos_requeridos.append("tu nombre")
    
    if datos_requeridos:
        if es_porfirianna:
            mensaje_error = f"Para tomar tu pedido, necesito que me proporciones: {', '.join(datos_requeridos)}."
        else:
            mensaje_error = f"Para agendar tu cita, necesito que me proporciones: {', '.join(datos_requeridos)}."
        return False, mensaje_error
    
    return True, None

@app.route('/completar_autorizacion')
def completar_autorizacion():
    """Endpoint para completar la autorización con el código"""
    try:
        # Obtener todos los parámetros de la URL
        code = request.args.get('code')
        state = request.args.get('state')
        scope = request.args.get('scope')
        
        app.logger.info(f"🔐 Parámetros recibidos:")
        app.logger.info(f"  - Code: {code[:10] if code else 'None'}...")
        app.logger.info(f"  - State: {state}")
        app.logger.info(f"  - Scope: {scope}")
        
        if not code:
            app.logger.error("❌ No se proporcionó código de autorización")
            return "❌ Error: No se proporcionó código de autorización"
        
        # Definir rutas absolutas
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        client_secret_path = os.path.join(BASE_DIR, 'client_secret.json')
        token_path = os.path.join(BASE_DIR, 'token.json')
        
        # Verificar que el archivo client_secret.json existe
        if not os.path.exists(client_secret_path):
            app.logger.error(f"❌ No se encuentra {client_secret_path}")
            return f"❌ Error: No se encuentra el archivo de configuración de Google"
        
        # Obtener el host actual de la solicitud
        host = request.host
        app.logger.info(f"🔍 Host actual: {host}")
        
        # Construir la URI de redirección basada en el host actual
        redirect_uri = f'https://{host}/completar-autorizacion'
        app.logger.info(f"🔐 URI de redirección: {redirect_uri}")
        
        SCOPES = ['https://www.googleapis.com/auth/calendar']
        
        # Crear el flujo de OAuth
        app.logger.info("🔄 Creando flujo de OAuth...")
        flow = InstalledAppFlow.from_client_secrets_file(
            client_secret_path, 
            SCOPES,
            redirect_uri=redirect_uri
        )
        
        # Intercambiar código por token
        app.logger.info("🔄 Intercambiando código por token...")
        flow.fetch_token(code=code)
        creds = flow.credentials
        
        app.logger.info("✅ Token obtenido correctamente")
        
        # Guardar token
        app.logger.info(f"💾 Guardando token en: {token_path}")
        
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
        
        app.logger.info("✅ Autorización completada correctamente")
        return """
        <html>
        <head>
            <title>Autorización Completada</title>
            <style>
                body { font-family: Arial, sans-serif; text-align: center; margin-top: 50px; }
                .success { color: green; font-size: 24px; }
                .info { margin: 20px; }
            </style>
        </head>
        <body>
            <h1 class="success">✅ Autorización completada correctamente</h1>
            <div class="info">
                <p>Ya puedes usar Google Calendar para agendar citas.</p>
                <p>Puedes cerrar esta ventana y volver a la aplicación.</p>
            </div>
        </body>
        </html>
        """
        
    except Exception as e:
        app.logger.error(f"❌ Error en completar_autorizacion: {str(e)}")
        app.logger.error(traceback.format_exc())
        return f"""
        <html>
        <head>
            <title>Error de Autorización</title>
            <style>
                body {{ font-family: Arial, sans-serif; text-align: center; margin-top: 50px; }}
                .error {{ color: red; font-size: 24px; }}
                .info {{ margin: 20px; }}
                pre {{ background: #f5f5f5; padding: 10px; text-align: left; margin: 20px auto; max-width: 80%; }}
            </style>
        </head>
        <body>
            <h1 class="error">❌ Error en la autorización</h1>
            <div class="info">
                <p>Ocurrió un error al procesar la autorización de Google:</p>
                <pre>{str(e)}</pre>
                <p>Por favor, contacta al administrador del sistema.</p>
            </div>
        </body>
        </html>
        """
         
def convertir_audio(audio_path):
    try:
        output_path = audio_path.replace('.ogg', '.mp3')
        audio = AudioSegment.from_file(audio_path, format='ogg')
        audio.export(output_path, format='mp3')
        app.logger.info(f"🔄 Audio convertido a: {output_path}")
        return output_path
    except Exception as e:
        app.logger.error(f"🔴 Error convirtiendo audio: {str(e)}")
        return None

def extraer_info_cita_mejorado(mensaje, numero, historial=None, config=None):
    """Versión mejorada que usa el historial de conversación para extraer información"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    if historial is None:
        historial = obtener_historial(numero, limite=5, config=config)
    
    # Construir contexto del historial
    contexto_historial = ""
    for i, msg in enumerate(historial):
        if msg['mensaje']:
            contexto_historial += f"Usuario: {msg['mensaje']}\n"
        if msg['respuesta']:
            contexto_historial += f"Asistente: {msg['respuesta']}\n"
    
    try:
        # 🔥 MEJORAR EL PROMPT PARA LA PORFIRIANNA
        prompt_cita = f"""
        Eres un asistente para La Porfirianna (restaurante de comida). 
        Extrae la información del PEDIDO solicitado basándote en este mensaje.
        
        MENSAJE ACTUAL: "{mensaje}"
        
        HISTORIAL DE CONVERSACIÓN:
        {contexto_historial}
        
        Devuélvelo en formato JSON con estos campos:
        - servicio_solicitado (string: ej. "chilaquiles", "tacos", "caviar", etc.)
        - fecha_sugerida (null - no aplica para pedidos de comida)
        - hora_sugerida (null - no aplica para pedidos de comida)  
        - nombre_cliente (string o null)
        - telefono (string: {numero})
        - estado (siempre "pendiente")
        - datos_completos (boolean: true si tiene servicio y nombre)
        
        Si el mensaje es un saludo o no contiene información de pedido, devuelve servicio_solicitado: null.
        """
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt_cita}],
            "temperature": 0.3,
            "max_tokens": 500
        }
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        respuesta_ia = data['choices'][0]['message']['content'].strip()
        
        # Extraer JSON de la respuesta
        json_match = re.search(r'\{.*\}', respuesta_ia, re.DOTALL)
        if json_match:
            info_cita = json.loads(json_match.group())
            return info_cita
        else:
            return None
            
    except Exception as e:
        app.logger.error(f"Error extrayendo info de pedido: {e}")
        return None
    
@app.route('/debug-headers')
def debug_headers():
    headers = {k: v for k, v in request.headers.items()}
    config = obtener_configuracion_por_host()
    return jsonify({
        'headers': headers,
        'detected_host': request.headers.get('Host'),
        'config_dominio': config.get('dominio'),
        'config_db_name': config.get('db_name')
    })

@app.route('/debug-dominio')
def debug_dominio():
    host = request.headers.get('Host', 'desconocido')
    user_agent = request.headers.get('User-Agent', 'desconocido')
    
    return f"""
    <h1>Información del Dominio</h1>
    <p><strong>Dominio detectado:</strong> {host}</p>
    <p><strong>User-Agent:</strong> {user_agent}</p>
    <p><strong>Hora:</strong> {datetime.now()}</p>
    
    <h2>Probar ambos dominios:</h2>
    <ul>
        <li><a href="https://mektia.com/debug-dominio">mektia.com</a></li>
        <li><a href="https://laporfirianna.mektia.com/debug-dominio">laporfirianna.mektia.com</a></li>
    </ul>
    """

def get_country_flag(numero):
    if not numero:
        return None
    numero = str(numero)
    if numero.startswith('+'):
        numero = numero[1:]
    for i in range(3, 0, -1):
        prefijo = numero[:i]
        if prefijo in PREFIJOS_PAIS:
            codigo = PREFIJOS_PAIS[prefijo]
            return f"https://flagcdn.com/24x18/{codigo}.png"
    return None

# ——— Subpestañas válidas ———
SUBTABS = ['negocio', 'personalizacion', 'precios']

@app.route('/kanban/data') 
def kanban_data(config = None):
    """Endpoint que devuelve los datos del Kanban en formato JSON"""
    config = obtener_configuracion_por_host()
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)

        # 1) Cargar las columnas Kanban
        cursor.execute("SELECT * FROM kanban_columnas ORDER BY orden;")
        columnas = cursor.fetchall()

        # 2) Datos de los chats
        cursor.execute("""
            SELECT 
                cm.numero,
                cm.columna_id,
                MAX(c.timestamp) AS ultima_fecha,
                (SELECT mensaje FROM conversaciones 
                WHERE numero = cm.numero 
                ORDER BY timestamp DESC LIMIT 1) AS ultimo_mensaje,
                (SELECT imagen_url FROM contactos 
                WHERE numero_telefono = cm.numero 
                ORDER BY id DESC LIMIT 1) AS avatar,
                MAX(cont.plataforma) AS canal,
                COALESCE(MAX(cont.alias), MAX(cont.nombre), cm.numero) AS nombre_mostrado,
                (SELECT COUNT(*) FROM conversaciones 
                WHERE numero = cm.numero AND respuesta IS NULL) AS sin_leer
            FROM chat_meta cm
            LEFT JOIN contactos cont ON cont.numero_telefono = cm.numero
            LEFT JOIN conversaciones c ON c.numero = cm.numero
            GROUP BY cm.numero, cm.columna_id
            ORDER BY ultima_fecha DESC;
        """)
        chats = cursor.fetchall()

        # Convertir timestamps a hora de México
        for chat in chats:
            if chat.get('ultima_fecha'):
                if chat['ultima_fecha'].tzinfo is not None:
                    chat['ultima_fecha'] = chat['ultima_fecha'].astimezone(tz_mx)
                else:
                    chat['ultima_fecha'] = pytz.utc.localize(chat['ultima_fecha']).astimezone(tz_mx)
                
                # Formatear fecha para JSON
                chat['ultima_fecha'] = chat['ultima_fecha'].isoformat()

        cursor.close()
        conn.close()

        return jsonify({
            'columnas': columnas,
            'chats': chats,
            'timestamp': datetime.now().isoformat(),
            'total_chats': len(chats)
        })
        
    except Exception as e:
        app.logger.error(f"🔴 Error en kanban_data: {e}")
        return jsonify({'error': str(e)}), 500

# ——— Configuración en MySQL ———
def load_config(config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuracion (
            id INT PRIMARY KEY DEFAULT 1,
            ia_nombre VARCHAR(100),
            negocio_nombre VARCHAR(100),
            descripcion TEXT,
            url VARCHAR(255),
            direccion VARCHAR(255),
            telefono VARCHAR(50),
            correo VARCHAR(100),
            que_hace TEXT,
            tono VARCHAR(50),
            lenguaje VARCHAR(50)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')
    cursor.execute("SELECT * FROM configuracion WHERE id = 1;")
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        return {'negocio': {}, 'personalizacion': {}}

    negocio = {
        'ia_nombre': row['ia_nombre'],
        'negocio_nombre': row['negocio_nombre'],
        'descripcion': row['descripcion'],
        'url': row['url'],
        'direccion': row['direccion'],
        'telefono': row['telefono'],
        'correo': row['correo'],
        'que_hace': row['que_hace'],
    }
    personalizacion = {
        'tono': row['tono'],
        'lenguaje': row['lenguaje'],
    }
    return {'negocio': negocio, 'personalizacion': personalizacion}

def crear_tabla_citas(config=None):
    """Crea la tabla para almacenar las citas"""
    conn = get_db_connection(config)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS citas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            numero_cliente VARCHAR(20),
            servicio_solicitado VARCHAR(200),
            fecha_propuesta DATE,
            hora_propuesta TIME,
            nombre_cliente VARCHAR(100),
            telefono VARCHAR(20),
            estado ENUM('pendiente', 'confirmada', 'cancelada') DEFAULT 'pendiente',
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            fecha_confirmacion DATETIME NULL,
            notas TEXT,
            FOREIGN KEY (numero_cliente) REFERENCES contactos(numero_telefono)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()

def guardar_cita(info_cita, config=None):
    """Guarda la cita en la base de datos y agenda en Google Calendar"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO citas (
                numero_cliente, servicio_solicitado, fecha_propuesta,
                hora_propuesta, nombre_cliente, telefono, estado
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (
            info_cita.get('telefono'),
            info_cita.get('servicio_solicitado'),
            info_cita.get('fecha_sugerida'),
            info_cita.get('hora_sugerida'),
            info_cita.get('nombre_cliente'),
            info_cita.get('telefono'),
            'pendiente'
        ))
        
        conn.commit()
        cita_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        # Agendar en Google Calendar
        service = autenticar_google_calendar(config)
        if service:
            evento_id = crear_evento_calendar(service, info_cita, config)
            if evento_id:
                # Guardar el ID del evento en la base de datos
                conn = get_db_connection(config)
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE citas SET evento_calendar_id = %s WHERE id = %s
                ''', (evento_id, cita_id))
                conn.commit()
                cursor.close()
                conn.close()
                app.logger.info(f"✅ Evento de calendar guardado: {evento_id}")
        
        return cita_id
        
    except Exception as e:
        app.logger.error(f"Error guardando cita: {e}")
        return None
    
def enviar_confirmacion_cita(numero, info_cita, cita_id, config=None):
    """Envía confirmación de cita por WhatsApp"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    # Determinar el tipo de negocio
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    tipo_solicitud = "pedido" if es_porfirianna else "cita"
    
    try:
        mensaje_confirmacion = f"""
        📅 *Confirmación de {tipo_solicitud}* - ID: #{cita_id}

        ¡Hola! Hemos recibido tu solicitud de {tipo_solicitud}:

        *{'Platillo' if es_porfirianna else 'Servicio'}:* {info_cita.get('servicio_solicitado', 'Por confirmar')}
        *Fecha sugerida:* {info_cita.get('fecha_sugerida', 'Por confirmar')}
        *Hora sugerida:* {info_cita.get('hora_sugerida', 'Por confirmar')}

        📞 *Tu número:* {numero}

        ⏰ *Próximos pasos:*
        Nos pondremos en contacto contigo dentro de las próximas 24 horas para confirmar la disponibilidad.

        ¿Necesitas hacer algún cambio? Responde a este mensaje.

        ¡Gracias por confiar en nosotros! 🙏
        """
        
        enviar_mensaje(numero, mensaje_confirmacion, config)
        app.logger.info(f"✅ Confirmación de {tipo_solicitud} enviada a {numero}, ID: {cita_id}")
        
    except Exception as e:
        app.logger.error(f"Error enviando confirmación de {tipo_solicitud}: {e}")

def enviar_alerta_cita_administrador(info_cita, cita_id, config=None):
    """Envía alerta al administrador sobre nueva cita"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    # Determinar el tipo de negocio
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    tipo_solicitud = "pedido" if es_porfirianna else "cita"
    
    try:
        mensaje_alerta = f"""
        🚨 *NUEVA SOLICITUD DE {tipo_solicitud.upper()}* - ID: #{cita_id}

        *Cliente:* {info_cita.get('nombre_cliente', 'No especificado')}
        *Teléfono:* {info_cita.get('telefono')}

        *{'Platillo' if es_porfirianna else 'Servicio'} solicitado:* {info_cita.get('servicio_solicitado', 'No especificado')}
        *Fecha sugerida:* {info_cita.get('fecha_sugerida', 'No especificada')}
        *Hora sugerida:* {info_cita.get('hora_sugerida', 'No especificada')}

        ⏰ *Fecha de solicitud:* {datetime.now().strftime('%d/%m/%Y %H:%M')}

        📋 *Acción requerida:* Contactar al cliente para confirmar disponibilidad.
        """
        
        # Enviar a ambos números
        enviar_mensaje(ALERT_NUMBER, mensaje_alerta, config)
        enviar_mensaje('5214493432744', mensaje_alerta, config)
        app.logger.info(f"✅ Alerta de {tipo_solicitud} enviada a ambos administradores, ID: {cita_id}")
        
    except Exception as e:
        app.logger.error(f"Error enviando alerta de {tipo_solicitud}: {e}")


@app.route('/uploads/<filename>')
def serve_uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# Crear directorio de uploads al inicio
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def extraer_servicio_del_mensaje(mensaje, config=None):
    """Extrae el servicio del mensaje usando keywords simples"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    mensaje_lower = mensaje.lower()
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    
    if es_porfirianna:
        # Palabras clave para La Porfirianna
        platillos = ['gordita', 'taco', 'quesadilla', 'sope', 'torta', 'comida', 'platillo']
        for platillo in platillos:
            if platillo in mensaje_lower:
                return mensaje  # Devolver el mensaje completo como descripción
        return None
    else:
        # Palabras clave para Mektia
        servicios = ['página web', 'sitio web', 'app', 'aplicación', 'software', 
                    'marketing', 'diseño', 'hosting', 'ecommerce', 'tienda online']
        for servicio in servicios:
            if servicio in mensaje_lower:
                return servicio
        return None

def extraer_fecha_del_mensaje(mensaje):
    """Extrae fechas relativas simples del mensaje"""
    mensaje_lower = mensaje.lower()
    
    hoy = datetime.now()
    
    if 'mañana' in mensaje_lower:
        return (hoy + timedelta(days=1)).strftime('%Y-%m-%d')
    elif 'pasado mañana' in mensaje_lower:
        return (hoy + timedelta(days=2)).strftime('%Y-%m-%d')
    elif 'lunes' in mensaje_lower:
        # Calcular próximo lunes
        dias_hasta_lunes = (7 - hoy.weekday()) % 7
        if dias_hasta_lunes == 0:
            dias_hasta_lunes = 7
        return (hoy + timedelta(days=dias_hasta_lunes)).strftime('%Y-%m-%d')
    # Agregar más patrones según necesites
    
    return None

def extraer_nombre_del_mensaje(mensaje):
    """Intenta extraer un nombre del mensaje"""
    # Patrón simple para nombres (2-3 palabras)
    patron_nombre = r'^[A-Za-zÁáÉéÍíÓóÚúÑñ]{2,20} [A-Za-zÁáÉéÍíÓóÚúÑñ]{2,20}( [A-Za-zÁáÉéÍíÓóÚúÑñ]{2,20})?$'
    
    if re.match(patron_nombre, mensaje.strip()):
        return mensaje.strip()
    
    return None

def solicitar_datos_faltantes_cita(numero, info_cita, config=None):
    """
    Solicita al usuario los datos faltantes para completar la cita/pedido
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    # Determinar el tipo de negocio
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    
    # Identificar qué datos faltan
    datos_faltantes = []
    
    # Validar servicio solicitado (siempre requerido)
    if not info_cita.get('servicio_solicitado') or info_cita.get('servicio_solicitado') == 'null':
        if es_porfirianna:
            datos_faltantes.append("qué platillo deseas ordenar")
        else:
            datos_faltantes.append("qué servicio necesitas")
    
    # Validar fecha (solo requerido para Mektia)
    if not es_porfirianna and (not info_cita.get('fecha_sugerida') or info_cita.get('fecha_sugerida') == 'null'):
        datos_faltantes.append("fecha preferida")
    
    # Validar nombre del cliente (siempre requerido)
    if not info_cita.get('nombre_cliente') or info_cita.get('nombre_cliente') == 'null':
        datos_faltantes.append("tu nombre")
    
    # Construir mensaje personalizado según lo que falte
    if datos_faltantes:
        if es_porfirianna:
            mensaje = f"¡Perfecto! Para tomar tu pedido, necesito que me proporciones: {', '.join(datos_faltantes)}."
        else:
            mensaje = f"¡Excelente! Para agendar tu cita, necesito que me proporciones: {', '.join(datos_faltantes)}."
        
        # Agregar ejemplos según lo que falte
        if "qué platillo deseas ordenar" in datos_faltantes or "qué servicio necesitas" in datos_faltantes:
            if es_porfirianna:
                mensaje += "\n\nPor ejemplo: 'Quiero ordenar 4 gorditas de chicharrón y 2 tacos'"
            else:
                mensaje += "\n\nPor ejemplo: 'Necesito una página web para mi negocio'"
        
        if "fecha preferida" in datos_faltantes:
            mensaje += "\n\nPor ejemplo: 'El próximo lunes' o 'Para el 15 de octubre'"
        
        if "tu nombre" in datos_faltantes:
            mensaje += "\n\nPor ejemplo: 'Mi nombre es Juan Pérez'"
        
        enviar_mensaje(numero, mensaje, config)
        app.logger.info(f"📋 Solicitando datos faltantes a {numero}: {', '.join(datos_faltantes)}")
    else:
        # Todos los datos están completos (no debería llegar aquí)
        if es_porfirianna:
            enviar_mensaje(numero, "¡Gracias! He registrado tu pedido y nos pondremos en contacto contigo pronto.", config)
        else:
            enviar_mensaje(numero, "¡Gracias! He agendado tu cita y nos pondremos en contacto contigo pronto.", config)

@app.route('/autorizar-google')
def autorizar_google():
    """Endpoint para autorizar manualmente con Google"""
    service = autenticar_google_calendar()
    if service:
        flash('✅ Autorización con Google Calendar exitosa', 'success')
    else:
        flash('❌ Error en la autorización con Google Calendar', 'error')
    return redirect(url_for('configuracion_tab', tab='negocio'))

@app.route('/citas')
def ver_citas(config=None):
    """Endpoint para ver citas pendientes"""
    if config is None:
        config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('''
        SELECT c.*, co.nombre, co.alias 
        FROM citas c 
        LEFT JOIN contactos co ON c.numero_cliente = co.numero_telefono 
        ORDER BY c.fecha_creacion DESC
    ''')
    citas = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('citas.html', citas=citas)

def save_config(cfg_all, config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    neg = cfg_all.get('negocio', {})
    per = cfg_all.get('personalizacion', {})

    conn = get_db_connection(config)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO configuracion
            (id, ia_nombre, negocio_nombre, descripcion, url, direccion,
             telefono, correo, que_hace, tono, lenguaje)
        VALUES
            (1, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            ia_nombre = VALUES(ia_nombre),
            negocio_nombre = VALUES(negocio_nombre),
            descripcion = VALUES(descripcion),
            url = VALUES(url),
            direccion = VALUES(direccion),
            telefono = VALUES(telefono),
            correo = VALUES(correo),
            que_hace = VALUES(que_hace),
            tono = VALUES(tono),
            lenguaje = VALUES(lenguaje);
    ''', (
        neg.get('ia_nombre'),
        neg.get('negocio_nombre'),
        neg.get('descripcion'),
        neg.get('url'),
        neg.get('direccion'),
        neg.get('telefono'),
        neg.get('correo'),
        neg.get('que_hace'),
        per.get('tono'),
        per.get('lenguaje'),
    ))
    conn.commit()
    cursor.close()
    conn.close()

# ——— CRUD y helpers para 'precios' ———
def obtener_todos_los_precios(config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS precios (
            id INT AUTO_INCREMENT PRIMARY KEY,
            servicio VARCHAR(100) NOT NULL,
            descripcion TEXT,
            precio DECIMAL(10,2) NOT NULL,
            moneda CHAR(3) NOT NULL,
            UNIQUE(servicio)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')
    cursor.execute("SELECT * FROM precios ORDER BY servicio;")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

def obtener_precio_por_id(pid, config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM precios WHERE id=%s;", (pid,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row

def obtener_precio(servicio_nombre: str, config):
    if config is None:
        config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT precio, moneda
        FROM precios
        WHERE LOWER(servicio)=LOWER(%s)
        LIMIT 1;
    """, (servicio_nombre,))
    res = cursor.fetchone()
    cursor.close()
    conn.close()
    if res:
        return Decimal(res[0]), res[1]
    return None

# ——— Memoria de conversación ———
# REEMPLAZA la función obtener_historial con esta versión mejorada
def obtener_historial(numero, limite=5, config=None):
    """Función compatible con la estructura actual de la base de datos"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT mensaje, respuesta, timestamp 
            FROM conversaciones 
            WHERE numero = %s 
            ORDER BY timestamp DESC 
            LIMIT %s
        """, (numero, limite))
        
        historial = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Invertir el orden para tener cronológico
        historial.reverse()
        
        app.logger.info(f"📚 Historial obtenido para {numero}: {len(historial)} mensajes")
        return historial
        
    except Exception as e:
        app.logger.error(f"❌ Error al obtener historial: {e}")
        return []
    
# ——— Función IA con contexto y precios ———
def responder_con_ia(mensaje_usuario, numero, es_imagen=False, imagen_base64=None, es_audio=False, transcripcion_audio=None, config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    cfg = load_config(config)
    neg = cfg['negocio']
    ia_nombre = neg.get('ia_nombre', 'Asistente')
    negocio_nombre = neg.get('negocio_nombre', '')
    descripcion = neg.get('descripcion', '')
    que_hace = neg.get('que_hace', '')
    estado_actual = obtener_estado_conversacion(numero, config)
    if estado_actual and estado_actual.get('contexto') == 'SOLICITANDO_CITA':
        return manejar_secuencia_cita(mensaje_usuario, numero, estado_actual, config)
    precios = obtener_todos_los_precios(config)
    lista_precios = "\n".join(
        f"- {p['servicio']}: {p['precio']} {p['moneda']}"
        for p in precios
    )

    # En la función responder_con_ia, modifica el system_prompt:
    system_prompt = f"""
    Eres **{ia_nombre}**, asistente virtual de **{negocio_nombre}**.
    Descripción del negocio:
    {descripcion}

    Tus responsabilidades:  
    {que_hace} 

    Servicios y tarifas actuales:
    {lista_precios}

    INSTRUCCIONES IMPORTANTES:
    1. No permitas que los usuarios agenden {'pedidos' if 'laporfirianna' in config.get('dominio', '') else 'citas'} sin haber obtenido todos los datos necesarios, si no los tienes no insistas solo manda un mensaje para recordar y ya no le digas de nuevo
    2. Los datos obligatorios para un {'pedido' if 'laporfirianna' in config.get('dominio', '') else 'cita'} son:
    - Servicio solicitado (siempre requerido)
    {'- Fecha sugerida (requerido)' if not 'laporfirianna' in config.get('dominio', '') else ''}
    - Nombre del cliente (siempre requerido)
    3. Si el usuario quiere hacer un {'pedido' if 'laporfirianna' in config.get('dominio', '') else 'agendar una cita'} pero faltan datos, pídelos amablemente
    4. Mantén siempre un tono profesional y conciso
    """.strip()

    historial = obtener_historial(numero, config=config)
    
    # 🔥 CORRECCIÓN: Definir messages_chain correctamente
    messages_chain = [{'role': 'system', 'content': system_prompt}]
    
    # 🔥 FILTRO CRÍTICO: Eliminar mensajes con contenido NULL o vacío
    for entry in historial:
        # Solo agregar mensajes de usuario con contenido válido
        if entry['mensaje'] and str(entry['mensaje']).strip() != '':
            messages_chain.append({'role': 'user', 'content': entry['mensaje']})
        
        # Solo agregar respuestas de IA con contenido válido
        if entry['respuesta'] and str(entry['respuesta']).strip() != '':
            messages_chain.append({'role': 'assistant', 'content': entry['respuesta']})
    
    # Agregar el mensaje actual (si es válido)
    if mensaje_usuario and str(mensaje_usuario).strip() != '':
        if es_imagen and imagen_base64:
            # ✅ Asegúrate de que imagen_base64 ya incluye el prefijo
            messages_chain.append({
                'role': 'user',
                'content': [
                    {"type": "text", "text": mensaje_usuario},
                    {
                        "type": "image_url", 
                        "image_url": {
                            "url": imagen_base64,  # Ya debería incluir "data:image/jpeg;base64,"
                            "detail": "auto"
                        }
                    }
                ]
            })
        elif es_audio and transcripcion_audio:
            # Para audio: incluir la transcripción
            messages_chain.append({
                'role': 'user',
                'content': f"[Audio transcrito] {transcripcion_audio}\n\nMensaje adicional: {mensaje_usuario}" if mensaje_usuario else f"[Audio transcrito] {transcripcion_audio}"
            })
        else:
            # Para texto normal
            messages_chain.append({'role': 'user', 'content': mensaje_usuario})

    try:
        if len(messages_chain) <= 1:
            return "¡Hola! ¿En qué puedo ayudarte hoy?"
        
        if es_imagen:
            # Usar OpenAI para imágenes
            headers = {
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "gpt-4o",
                "messages": messages_chain,  # ✅ Ahora messages_chain está definida
                "temperature": 0.7,
                "max_tokens": 1000,
            }
            
            app.logger.info(f"🖼️ Enviando imagen a OpenAI con gpt-4o")
            response = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
            
            data = response.json()
            return data['choices'][0]['message']['content'].strip()
        
        else:
            # Usar DeepSeek para texto (o audio transcrito)
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "deepseek-chat",
                "messages": messages_chain,  # ✅ Ahora messages_chain está definida
                "temperature": 0.7,
                "max_tokens": 2000
            }
            
            response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            return data['choices'][0]['message']['content'].strip()
    
    except requests.exceptions.RequestException as e:
        app.logger.error(f"🔴 API error: {e}")
        if hasattr(e, 'response') and e.response:
            app.logger.error(f"🔴 Response: {e.response.text}")
        return 'Lo siento, hubo un error con la IA.'
    except Exception as e: 
        app.logger.error(f"🔴 Error inesperado: {e}")
        return 'Lo siento, hubo un error con la IA.'

# Agregar esta función para manejar el estado de la conversación
def actualizar_estado_conversacion(numero, contexto, accion, datos=None, config=None):
    """
    Actualiza el estado de la conversación para mantener contexto
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    cursor = conn.cursor()
    
    # Crear tabla de estados si no existe
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS estados_conversacion (
            id INT AUTO_INCREMENT PRIMARY KEY,
            numero VARCHAR(20),
            contexto VARCHAR(50),
            accion VARCHAR(50),
            datos JSON,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_numero (numero),
            INDEX idx_contexto (contexto)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')
    
    # Insertar o actualizar estado
    # Insertar o actualizar estado
    cursor.execute('''
            INSERT INTO estados_conversacion (numero, contexto, accion, datos)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                contexto = VALUES(contexto),
                accion = VALUES(accion),
                datos = VALUES(datos),
                timestamp = CURRENT_TIMESTAMP
        ''', (numero, contexto, accion, json.dumps(datos) if datos else None))
    conn.commit()
    cursor.close()
    conn.close()

def manejar_secuencia_cita(mensaje, numero, estado_actual, config=None):
    """Maneja la secuencia de solicitud de cita paso a paso"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    paso_actual = estado_actual.get('datos', {}).get('paso', 0)
    datos_guardados = estado_actual.get('datos', {})
    
    # Determinar tipo de negocio
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    
    if paso_actual == 0:  # Primer paso: servicio
        # Extraer servicio del mensaje
        servicio = extraer_servicio_del_mensaje(mensaje, config)
        if servicio:
            datos_guardados['servicio'] = servicio
            datos_guardados['paso'] = 1
            actualizar_estado_conversacion(numero, "SOLICITANDO_CITA", "solicitar_fecha", datos_guardados, config)
            
            if es_porfirianna:
                return "¡Perfecto! ¿Para cuándo quieres tu pedido? (puedes decir 'hoy', 'mañana' o una fecha específica)"
            else:
                return "¡Excelente! ¿Qué fecha te viene bien para la cita? (puedes decir 'mañana', 'próximo lunes', etc.)"
        else:
            if es_porfirianna:
                return "No entendí qué platillo quieres ordenar. ¿Podrías ser más específico? Por ejemplo: 'Quiero 4 gorditas de chicharrón'"
            else:
                return "No entendí qué servicio necesitas. ¿Podrías ser más específico? Por ejemplo: 'Necesito una página web'"
    
    elif paso_actual == 1:  # Segundo paso: fecha
        fecha = extraer_fecha_del_mensaje(mensaje)
        if fecha:
            datos_guardados['fecha'] = fecha
            datos_guardados['paso'] = 2
            actualizar_estado_conversacion(numero, "SOLICITANDO_CITA", "solicitar_nombre", datos_guardados, config)
            return "¡Genial! ¿Cuál es tu nombre completo?"
        else:
            return "No entendí la fecha. ¿Podrías intentarlo de nuevo? Por ejemplo: 'mañana a las 3pm' o 'el viernes 15'"
    
    elif paso_actual == 2:  # Tercer paso: nombre
        nombre = extraer_nombre_del_mensaje(mensaje)
        if nombre:
            datos_guardados['nombre'] = nombre
            datos_guardados['paso'] = 3
            actualizar_estado_conversacion(numero, "SOLICITANDO_CITA", "confirmar_datos", datos_guardados, config)
            
            # Confirmar todos los datos
            if es_porfirianna:
                confirmacion = f"📋 *Resumen de tu pedido:*\n\n"
                confirmacion += f"🍽️ *Platillo:* {datos_guardados['servicio']}\n"
                confirmacion += f"📅 *Fecha:* {datos_guardados['fecha']}\n"
                confirmacion += f"👤 *Nombre:* {nombre}\n\n"
                confirmacion += "¿Todo correcto? Responde 'sí' para confirmar o 'no' para modificar."
            else:
                confirmacion = f"📋 *Resumen de tu cita:*\n\n"
                confirmacion += f"🛠️ *Servicio:* {datos_guardados['servicio']}\n"
                confirmacion += f"📅 *Fecha:* {datos_guardados['fecha']}\n"
                confirmacion += f"👤 *Nombre:* {nombre}\n\n"
                confirmacion += "¿Todo correcto? Responde 'sí' para confirmar o 'no' para modificar."
            
            return confirmacion
        else:
            return "No entendí tu nombre. ¿Podrías escribirlo de nuevo?"
    
    elif paso_actual == 3:  # Confirmación final
        if mensaje.lower() in ['sí', 'si', 'sip', 'correcto', 'ok']:
            # Guardar cita completa
            info_cita = {
                'servicio_solicitado': datos_guardados['servicio'],
                'fecha_sugerida': datos_guardados['fecha'],
                'nombre_cliente': datos_guardados['nombre'],
                'telefono': numero,
                'estado': 'pendiente'
            }
            
            cita_id = guardar_cita(info_cita, config)
            actualizar_estado_conversacion(numero, "CITA_CONFIRMADA", "cita_agendada", {"cita_id": cita_id}, config)
            
            if es_porfirianna:
                return f"✅ *Pedido confirmado* - ID: #{cita_id}\n\nHemos registrado tu pedido. Nos pondremos en contacto contigo pronto. ¡Gracias!"
            else:
                return f"✅ *Cita confirmada* - ID: #{cita_id}\n\nHemos agendado tu cita. Nos pondremos en contacto contigo pronto. ¡Gracias!"
        
        elif mensaje.lower() in ['no', 'cancelar', 'modificar']:
            actualizar_estado_conversacion(numero, "SOLICITANDO_CITA", "reiniciar", {}, config)
            return "De acuerdo, empecemos de nuevo. ¿Qué servicio necesitas?"
        
        else:
            return "Por favor responde 'sí' para confirmar o 'no' para modificar."

def obtener_estado_conversacion(numero, config=None):
    """Obtiene el estado actual de la conversación"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('''
        SELECT contexto, accion, datos, timestamp 
        FROM estados_conversacion 
        WHERE numero = %s 
        ORDER BY timestamp DESC 
        LIMIT 1
    ''', (numero,))
    
    estado = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if estado and estado['datos']:
        try:
            estado['datos'] = json.loads(estado['datos'])
        except:
            estado['datos'] = {}
    
    # Si el estado es muy viejo (más de 1 hora), ignorarlo
    if estado and estado.get('timestamp'):
        tiempo_transcurrido = datetime.now() - estado['timestamp']
        if tiempo_transcurrido.total_seconds() > 3600:  # 1 hora
            return None
    
    return estado

def obtener_imagen_whatsapp(image_id, config=None):
    """Obtiene la imagen de WhatsApp, la convierte a base64 y guarda localmente"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # 1. Obtener metadata de la imagen
        url_metadata = f"https://graph.facebook.com/v18.0/{image_id}"
        headers = {
            'Authorization': f'Bearer {config["whatsapp_token"]}',
            'Content-Type': 'application/json'
        }
        
        app.logger.info(f"🖼️ Obteniendo metadata de imagen WhatsApp: {url_metadata}")
        response_metadata = requests.get(url_metadata, headers=headers, timeout=30)
        response_metadata.raise_for_status()
        
        metadata = response_metadata.json()
        download_url = metadata.get('url')
        mime_type = metadata.get('mime_type', 'image/jpeg')
        
        if not download_url:
            app.logger.error(f"🔴 No se encontró URL de descarga de imagen: {metadata}")
            return None, None
            
        app.logger.info(f"🖼️ URL de descarga: {download_url}")
        
        # 2. Descargar la imagen
        image_response = requests.get(download_url, headers=headers, timeout=30)
        if image_response.status_code != 200:
            app.logger.error(f"🔴 Error descargando imagen: {image_response.status_code}")
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
        
        app.logger.info(f"✅ Imagen guardada: {filepath}")
        app.logger.info(f"🌐 URL web: {public_url}")
        
        return base64_string, public_url
        
    except Exception as e:
        app.logger.error(f"🔴 Error en obtener_imagen_whatsapp: {str(e)}")
        app.logger.error(traceback.format_exc())
        return None, None

@app.route('/procesar-codigo', methods=['POST'])
def procesar_codigo():
    """Procesa el código de autorización manualmente"""
    try:
        code = request.form.get('codigo')
        if not code:
            return "❌ Error: No se proporcionó código"
        
        # En app.py, la función autenticar_google_calendar()
        SCOPES = ['https://www.googleapis.com/auth/calendar']  # Este scope está correcto
        
        flow = InstalledAppFlow.from_client_secrets_file(
            'client_secret.json', 
            SCOPES,
            redirect_uri='https://www.mektia.com/completar-autorizacion'
        )
        
        # Intercambiar código por token
        flow.fetch_token(code=code)
        creds = flow.credentials
        
        # Guardar token
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
        
        return '''
        <h1>✅ ¡Autorización completada!</h1>
        <p>Google Calendar está ahora configurado correctamente.</p>
        <p>Puedes cerrar esta ventana y probar agendar una cita.</p>
        <a href="/">Volver al inicio</a>
        '''
        
    except Exception as e:
        return f"❌ Error: {str(e)}<br><a href='/autorizar-manual'>Intentar de nuevo</a>"  

def procesar_fecha_relativa(fecha_str):
    """
    Función simple de procesamiento de fechas relativas
    """
    if not fecha_str or fecha_str == 'null':
        return None
    
    # Si ya es formato YYYY-MM-DD, devolver tal cual
    if re.match(r'\d{4}-\d{2}-\d{2}', fecha_str):
        return fecha_str
    
    # Lógica básica de procesamiento
    hoy = datetime.now()
    mapping = {
        'próximo lunes': hoy + timedelta(days=(7 - hoy.weekday()) % 7),
        'mañana': hoy + timedelta(days=1),
        'pasado mañana': hoy + timedelta(days=2),
    }
    
    fecha_lower = fecha_str.lower()
    for termino, fecha_calculada in mapping.items():
        if termino in fecha_lower:
            return fecha_calculada.strftime('%Y-%m-%d')
    
    return None

def extraer_info_intervencion(mensaje, numero, historial, config=None):
    """Extrae información relevante para intervención humana"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # Construir contexto del historial
        contexto_historial = "\n".join([
            f"Usuario: {msg['mensaje']}\nAsistente: {msg['respuesta']}" 
            for msg in historial if msg['mensaje'] and msg['respuesta']
        ])
        
        prompt = f"""
        El usuario ha solicitado hablar con un humano. Analiza el mensaje y el historial para extraer información clave.
        
        MENSAJE ACTUAL: "{mensaje}"
        
        HISTORIAL RECIENTE:
        {contexto_historial}
        
        Extrae esta información:
        1. ¿Cuál es el problema o necesidad principal?
        2. ¿Qué ha intentado el usuario hasta ahora?
        3. ¿Hay urgencia o frustración evidente?
        4. ¿Qué información sería útil para un agente humano?
        
        Devuelve un JSON con esta estructura:
        {{
            "problema_principal": "string",
            "intentos_previos": "string",
            "urgencia": "alta/media/baja",
            "informacion_util": "string",
            "resumen": "string"
        }}
        """
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 500
        }
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        respuesta_ia = data['choices'][0]['message']['content'].strip()
        
        # Extraer JSON de la respuesta
        json_match = re.search(r'\{.*\}', respuesta_ia, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            # Fallback si no puede extraer JSON
            return {
                "problema_principal": mensaje,
                "intentos_previos": "No detectados",
                "urgencia": "media",
                "informacion_util": f"Usuario {numero} solicita intervención humana",
                "resumen": f"Usuario solicita humano después de mensaje: {mensaje}"
            }
            
    except Exception as e:
        app.logger.error(f"Error extrayendo info de intervención: {e}")
        return {
            "problema_principal": mensaje,
            "intentos_previos": "Error en análisis",
            "urgencia": "media",
            "informacion_util": f"Usuario {numero} necesita ayuda humana",
            "resumen": f"Solicitud de intervención humana: {mensaje}"
        }

def enviar_alerta_intervencion_humana(info_intervencion, config=None):
    """Envía alerta de intervención humana al administrador"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        mensaje = f"""🚨 *SOLICITUD DE INTERVENCIÓN HUMANA*

📞 *Cliente:* {info_intervencion.get('telefono', 'Número no disponible')}
⏰ *Hora:* {datetime.now().strftime('%d/%m/%Y %H:%M')}
🚨 *Urgencia:* {info_intervencion.get('urgencia', 'media').upper()}

📋 *Problema principal:*
{info_intervencion.get('problema_principal', 'No especificado')}

🔍 *Intentos previos:*
{info_intervencion.get('intentos_previos', 'No detectados')}

💡 *Información útil:*
{info_intervencion.get('informacion_util', 'Sin información adicional')}

📝 *Resumen:*
{info_intervencion.get('resumen', 'Solicitud de intervención humana')}

⚠️ *Acción requerida:* Contactar al cliente urgentemente.
"""
        
        # Enviar a ambos números de administración
        enviar_mensaje(ALERT_NUMBER, mensaje, config)
        enviar_mensaje('5214493432744', mensaje, config)
        
        app.logger.info(f"✅ Alerta de intervención humana enviada a administradores")
        
    except Exception as e:
        app.logger.error(f"Error enviando alerta de intervención: {e}")

# REEMPLAZA la llamada a procesar_mensaje en el webhook con:
def procesar_mensaje_normal(msg, numero, texto, es_imagen, es_audio, config, imagen_base64=None, transcripcion=None, es_mi_numero=False):
    """Procesa mensajes normales (no citas/intervenciones)"""
    try:
        # IA normal
        IA_ESTADOS.setdefault(numero, {'activa': True, 'prefiere_voz': False})
        respuesta = ""
        
        if IA_ESTADOS[numero]['activa']:
            # 🆕 DETECTAR PREFERENCIA DE VOZ
            if "envíame audio" in texto.lower() or "respuesta en audio" in texto.lower():
                IA_ESTADOS[numero]['prefiere_voz'] = True
                app.logger.info(f"🎵 Usuario {numero} prefiere respuestas de voz")
            
            responder_con_voz = IA_ESTADOS[numero]['prefiere_voz'] or es_audio
            
            # Obtener respuesta de IA
            respuesta = responder_con_ia(texto, numero, es_imagen, imagen_base64, es_audio, transcripcion, config)
            
            # 🆕 ENVÍO DE RESPUESTA (VOZ O TEXTO)
            if responder_con_voz and not es_imagen:
                # Intentar enviar respuesta de voz
                audio_filename = f"respuesta_{numero}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                audio_url_local = texto_a_voz(respuesta, audio_filename, config)
                
                if audio_url_local:
                    # URL pública del audio (ajusta según tu configuración)
                    audio_url_publica = f"https://{config.get('dominio', 'mektia.com')}/static/audio/respuestas/{audio_filename}.mp3"
                    
                    if enviar_mensaje_voz(numero, audio_url_publica, config):
                        app.logger.info(f"✅ Respuesta de voz enviada a {numero}")
                        guardar_conversacion(numero, texto, respuesta, config=config)
                    else:
                        # Fallback a texto
                        enviar_mensaje(numero, respuesta, config)
                        guardar_conversacion(numero, texto, respuesta, config=config)
                else:
                    # Fallback a texto
                    enviar_mensaje(numero, respuesta, config)
                    guardar_conversacion(numero, texto, respuesta, config=config)
            else:
                # Respuesta normal de texto
                enviar_mensaje(numero, respuesta, config)
                guardar_conversacion(numero, texto, respuesta, config=config)
            
            # 🔄 DETECCIÓN DE INTERVENCIÓN HUMANA (para mensajes normales también)
            if not es_mi_numero and detectar_intervencion_humana_ia(texto, numero, config):
                app.logger.info(f"🚨 Intervención humana detectada en mensaje normal para {numero}")
                resumen = resumen_rafa(numero, config)
                enviar_alerta_humana(numero, texto, resumen, config)
        
        # KANBAN AUTOMÁTICO
        meta = obtener_chat_meta(numero, config)
        if not meta:
            inicializar_chat_meta(numero, config)
        
        nueva_columna = evaluar_movimiento_automatico(numero, texto, respuesta, config)
        actualizar_columna_chat(numero, nueva_columna, config)
        
    except Exception as e:
        app.logger.error(f"🔴 Error procesando mensaje normal: {e}")


def obtener_audio_whatsapp(audio_id, config=None):
    try:
        url = f"https://graph.facebook.com/v18.0/{audio_id}"
        headers = {'Authorization': f'Bearer {config["whatsapp_token"]}'}
        app.logger.info(f"📥 Solicitando metadata de audio: {url}")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        metadata = response.json()
        download_url = metadata.get('url')
        app.logger.info(f"🔗 URL de descarga: {download_url}")
        
        audio_response = requests.get(download_url, headers=headers, timeout=30)
        audio_response.raise_for_status()
        
        # Verificar tipo de contenido
        content_type = audio_response.headers.get('content-type')
        app.logger.info(f"🎧 Tipo de contenido: {content_type}")
        if 'audio' not in content_type:
            app.logger.error(f"🔴 Archivo no es audio: {content_type}")
            return None, None
        
        # Guardar archivo
        audio_path = os.path.join(UPLOAD_FOLDER, f"audio_{audio_id}.ogg")
        with open(audio_path, 'wb') as f:
            f.write(audio_response.content)
        app.logger.info(f"💾 Audio guardado en: {audio_path}")
        
        # Generar URL pública
        audio_url = f"https://{config['dominio']}/uploads/audio_{audio_id}.ogg"
        return audio_path, audio_url
    except Exception as e:
        app.logger.error(f"🔴 Error en obtener_audio_whatsapp: {str(e)}")
        return None, None
      
def transcribir_audio_con_openai(audio_path):
    try:
        app.logger.info(f"🎙️ Enviando audio para transcripción: {audio_path}")
        
        # Usar el cliente OpenAI correctamente (nueva versión)
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        with open(audio_path, 'rb') as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="es"
            )
            
        app.logger.info(f"✅ Transcripción exitosa: {transcription.text}")
        return transcription.text
        
    except Exception as e:
        app.logger.error(f"🔴 Error en transcripción: {str(e)}")
        if hasattr(e, 'response'):
            try:
                error_response = e.response.json()
                app.logger.error(f"🔴 Respuesta de OpenAI: {error_response}")
            except:
                app.logger.error(f"🔴 Respuesta de OpenAI: {e.response.text}")
        return None
    
# AGREGAR esta función para gestionar conexiones a BD
def obtener_conexion_db(config):
    """Obtiene conexión a la base de datos correcta según la configuración"""
    try:
        if 'porfirianna' in config.get('dominio', ''):
            # Conectar a base de datos de La Porfirianna
            conn = mysql.connector.connect(
                host=config.get('db_host', 'localhost'),
                user=config.get('db_user', 'root'),
                password=config.get('db_password', ''),
                database=config.get('db_name', 'laporfirianna_db')
            )
        else:
            # Conectar a base de datos de Mektia (por defecto)
            conn = mysql.connector.connect(
                host=config.get('db_host', 'localhost'),
                user=config.get('db_user', 'root'),
                password=config.get('db_password', ''),
                database=config.get('db_name', 'mektia_db')
            )
        
        return conn
        
    except Exception as e:
        app.logger.error(f"❌ Error conectando a BD {config.get('db_name')}: {e}")
        raise

def obtener_configuracion_numero(numero_whatsapp):
    """Obtiene la configuración específica para un número de WhatsApp"""
    # Buscar en la configuración multi-tenant
    for numero_config, config in NUMEROS_CONFIG.items():
        if numero_whatsapp.endswith(numero_config) or numero_whatsapp == numero_config:
            return config
    
    # Fallback a configuración por defecto (Mektia)
    return NUMEROS_CONFIG['524495486142']

def obtener_imagen_perfil_alternativo(numero, config = None):
    """Método alternativo para obtener la imagen de perfil"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    try:
        # Intentar con el endpoint específico para contactos
        phone_number_id = "799540293238176"
        
        url = f"https://graph.facebook.com/v18.0/{MI_NUMERO_BOT}/contacts"
        
        params = {
            'fields': 'profile_picture_url',
            'user_numbers': f'[{numero}]',
            'access_token': 'whatsapp_token'
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'data' in data and len(data['data']) > 0:
                contacto = data['data'][0]
                if 'profile_picture_url' in contacto:
                    return contacto['profile_picture_url']
        
        return None
        
    except Exception as e:
        app.logger.error(f"🔴 Error en método alternativo: {e}")
        return None
# ——— Envío WhatsApp y guardado de conversación ———
# REEMPLAZA tu función enviar_mensaje con esta versión corregida
def enviar_mensaje(numero, texto, config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    
    # Validar texto
    if not texto or str(texto).strip() == '':
        app.logger.error("🔴 ERROR: Texto de mensaje vacío")
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
        app.logger.info(f"📤 Enviando: {texto_limpio[:50]}...")
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if r.status_code == 200:
            app.logger.info("✅ Mensaje enviado")
            return True
        else:
            app.logger.error(f"🔴 Error {r.status_code}: {r.text}")
            return False
            
    except Exception as e:
        app.logger.error(f"🔴 Exception: {e}")
        return False

@app.route('/actualizar-contactos')
def actualizar_contactos():
    """Endpoint para actualizar información de todos los contactos"""
    config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT numero_telefono FROM contactos")
    numeros = [row[0] for row in cursor.fetchall()]
    
    for numero in numeros:
        actualizar_info_contacto(numero, config)
    
    cursor.close()
    conn.close()
    
    return f"✅ Actualizados {len(numeros)} contactos"
       
# REEMPLAZA la función guardar_conversacion con esta versión mejorada
def guardar_conversacion(numero, mensaje, respuesta, config=None, imagen_url=None, es_imagen=False):
    """Función compatible con la estructura actual de la base de datos"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # Primero asegurar que el contacto existe con su información actualizada
        actualizar_info_contacto(numero, config)
        
        conn = get_db_connection(config)
        cursor = conn.cursor()
        
        # Usar los nombres de columna existentes en tu BD
        cursor.execute("""
            INSERT INTO conversaciones (numero, mensaje, respuesta, timestamp, imagen_url, es_imagen)
            VALUES (%s, %s, %s, NOW(), %s, %s)
        """, (numero, mensaje, respuesta, imagen_url, es_imagen))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        app.logger.info(f"💾 Conversación guardada para {numero}")
        return True
        
    except Exception as e:
        app.logger.error(f"❌ Error al guardar conversación: {e}")
        return False
    
def detectar_intencion_mejorado(mensaje, numero, historial=None, config=None):
    """
    Detección mejorada de intenciones con contexto
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    if historial is None:
        historial = obtener_historial(numero, limite=5, config=config)
    
    # Obtener estado actual de la conversación
    estado_actual = obtener_estado_conversacion(numero, config)
    
    # Construir contexto del historial
    contexto_historial = ""
    for i, msg in enumerate(historial):
        if msg['mensaje']:
            contexto_historial += f"Usuario: {msg['mensaje']}\n"
        if msg['respuesta']:
            contexto_historial += f"Asistente: {msg['respuesta']}\n"
    
    try:
        prompt_intencion = f"""
        Analiza el mensaje del usuario y determina su intención principal considerando el historial de conversación.

        HISTORIAL DE CONVERSACIÓN:
        {contexto_historial}

        MENSAJE ACTUAL: "{mensaje}"

        ESTADO ACTUAL: {estado_actual['contexto'] if estado_actual else 'Sin estado previo'}

        OPCIONES DE INTENCIÓN:
        - NUEVA_CITA: El usuario quiere crear una cita completamente nueva
        - MODIFICAR_CITA: El usuario quiere modificar una cita existente
        - CONSULTAR_SERVICIOS: El usuario pregunta sobre servicios disponibles
        - CANCELAR_CITA: El usuario quiere cancelar una cita
        - OTRO: Otra intención no relacionada con citas

        Responde en formato JSON:
        {{
            "intencion": "NUEVA_CITA|MODIFICAR_CITA|CONSULTAR_SERVICIOS|CANCELAR_CITA|OTRO",
            "confianza": 0.0-1.0,
            "detalles": {{...}}  // Información adicional relevante
        }}

        Ejemplo si dice "quiero hacer otro pedido" después de tener una cita:
        {{
            "intencion": "NUEVA_CITA",
            "confianza": 0.9,
            "detalles": {{"tipo": "nueva_solicitud"}}
        }}
        """
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt_intencion}],
            "temperature": 0.3,
            "max_tokens": 500
        }
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        respuesta_ia = data['choices'][0]['message']['content'].strip()
        
        # Extraer JSON de la respuesta
        json_match = re.search(r'\{.*\}', respuesta_ia, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            return {"intencion": "OTRO", "confianza": 0.0, "detalles": {}}
            
    except Exception as e:
        app.logger.error(f"Error detectando intención: {e}")
        return {"intencion": "OTRO", "confianza": 0.0, "detalles": {}}

def manejar_solicitud_cita_mejorado(numero, mensaje, info_cita, config=None):
    """
    Manejo mejorado de solicitudes de cita con prevención de ciclos
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    # 🔥 VERIFICAR SI ESTAMOS EN MEDIO DE UNA SOLICITUD
    estado_actual = obtener_estado_conversacion(numero, config)
    
    if estado_actual and estado_actual.get('contexto') == 'EN_CITA':
        # Ya estamos en proceso de cita, usar lógica de continuación
        return continuar_proceso_cita(numero, mensaje, estado_actual, config)
    
    # 🔥 DETECCIÓN MÁS ESTRICTA DE NUEVAS SOLICITUDES
    es_nueva_solicitud = (
        detectar_solicitud_cita_keywords(mensaje) and 
        not es_respuesta_a_pregunta(mensaje) and
        not estado_actual  # No hay estado previo
    )
    
    if not es_nueva_solicitud:
        # No es una nueva solicitud, dejar que la IA normal responda
        return None
    
    app.logger.info(f"📅 Nueva solicitud de cita detectada de {numero}")
    
    # Iniciar nuevo proceso de cita
    actualizar_estado_conversacion(numero, "EN_CITA", "solicitar_servicio", 
                                 {"paso": 1, "intentos": 0}, config)
    
    # Determinar tipo de negocio
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    
    if es_porfirianna:
        return "¡Hola! 👋 Para tomar tu pedido, necesito que me digas:\n\n1. ¿Qué platillos deseas ordenar?\n2. ¿Para cuándo lo quieres?\n3. ¿Cuál es tu nombre?\n\nPuedes responder todo en un solo mensaje. 😊"
    else:
        return "¡Hola! 👋 Para agendar tu cita, necesito que me digas:\n\n1. ¿Qué servicio necesitas?\n2. ¿Qué fecha te viene bien?\n3. ¿Cuál es tu nombre?\n\nPuedes responder todo en un solo mensaje. 😊"
    
def obtener_citas_pendientes(numero, config=None):
    """
    Obtiene las citas pendientes de un cliente
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('''
        SELECT * FROM citas 
        WHERE numero_cliente = %s AND estado = 'pendiente'
        ORDER BY fecha_creacion DESC
    ''', (numero,))
    
    citas = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return citas

def modificar_cita(cita_id, nueva_info, config=None):
    """
    Modifica una cita existente
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE citas SET
                servicio_solicitado = %s,
                fecha_propuesta = %s,
                hora_propuesta = %s,
                nombre_cliente = %s,
                fecha_creacion = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (
            nueva_info.get('servicio_solicitado'),
            nueva_info.get('fecha_sugerida'),
            nueva_info.get('hora_sugerida'),
            nueva_info.get('nombre_cliente'),
            cita_id
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        app.logger.error(f"Error modificando cita {cita_id}: {e}")
        return False

# ——— Detección y alerta ———
# REEMPLAZA la función detectar_intervencion_humana_ia con esta versión mejorada
def detectar_intervencion_humana_ia(mensaje_usuario, numero, config=None):
    """
    Detección mejorada de solicitud de intervención humana usando palabras clave
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    # ⚠️ EVITAR DETECTAR ALERTAS DEL MISMO SISTEMA
    alertas_sistema = [
        "🚨 ALERTA:", "📋 INFORMACIÓN COMPLETA", "👤 Cliente:", 
        "📞 Número:", "💬 Mensaje clave:", "🎯 INFORMACIÓN DEL PROYECTO"
    ]
    
    for alerta in alertas_sistema:
        if alerta in mensaje_usuario:
            return False
    
    # ⚠️ EVITAR TU NÚMERO PERSONAL Y EL NÚMERO DE ALERTA
    if numero == ALERT_NUMBER or numero in ['5214491182201', '524491182201', '5214493432744']:
        return False
    
    mensaje_lower = mensaje_usuario.lower()
    
    # Palabras clave que indican solicitud de humano
    palabras_clave_humano = [
        'humano', 'persona', 'asesor', 'agente', 'ejecutivo', 'representante',
        'operador', 'atendedor', 'atender', 'hablar con alguien', 
        'no eres humano', 'no me entiendes', 'quiero hablar con una persona',
        'atención humana', 'servicio humano', 'ayuda humana', 'asistencia humana',
        'no me ayudas', 'no resuelves', 'no entiendes', 'mejor hablar con',
        'te cambio', 'otra persona', 'supervisor', 'gerente', 'dueño',
        'encargado', 'responsable', 'que me llame', 'llámame', 'hablar por teléfono',
        'número de teléfono', 'contacto directo', 'comunicarme con'
    ]
    
    # Palabras de frustración
    palabras_frustracion = [
        'molesto', 'enojado', 'frustrado', 'cansado', 'harto', 'fastidiado',
        'irritado', 'disgustado', 'no me gusta', 'pésimo servicio', 'mal servicio',
        'pésima atención', 'mala atención', 'terrible', 'horrible', 'pésimo',
        'decepcionado', 'insatisfecho', 'no resuelve', 'no sirve', 'no ayuda',
        'estúpido', 'tonto', 'inútil', 'no funciona', 'no trabaja', 'no sabe'
    ]
    
    # Detectar palabras clave directas
    for palabra in palabras_clave_humano:
        if palabra in mensaje_lower:
            app.logger.info(f"🚨 Intervención humana detectada (palabra clave): {palabra}")
            return True
    
    # Detectar frustración (múltiples palabras de frustración)
    palabras_encontradas = [p for p in palabras_frustracion if p in mensaje_lower]
    if len(palabras_encontradas) >= 2:
        app.logger.info(f"🚨 Intervención humana detectada (frustración): {palabras_encontradas}")
        return True
    
    # Detectar solicitudes explícitas de contacto
    patrones_contacto = [
        r'quiero\s+hablar\s+con',
        r'dame\s+tu\s+número',
        r'pásame\s+con',
        r'necesito\s+hablar',
        r'contacto\s+directo',
        r'llámenme',
        r'mar[qc]enme',
        r'hablemos\s+por\s+teléfono'
    ]
    
    for patron in patrones_contacto:
        if re.search(patron, mensaje_lower):
            app.logger.info(f"🚨 Intervención humana detectada (patrón contacto): {patron}")
            return True
    
    return False
         
def resumen_rafa(numero, config=None):
    """Resumen más completo y eficiente"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT mensaje, respuesta, timestamp FROM conversaciones WHERE numero=%s ORDER BY timestamp DESC LIMIT 8;",
            (numero,)
        )
        historial = cursor.fetchall()
        cursor.close()
        conn.close()
        
        resumen = "🚨 *ALERTA: Intervención Humana Requerida*\n\n"
        resumen += f"📞 *Cliente:* {numero}\n"
        resumen += f"🕒 *Hora:* {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        resumen += "📋 *Últimas interacciones:*\n"
        
        for i, msg in enumerate(historial):
            hora = msg['timestamp'].strftime('%H:%M') if msg.get('timestamp') else 'N/A'
            resumen += f"\n{i+1}. [{hora}] 👤: {msg['mensaje'][:80] if msg['mensaje'] else '[Sin mensaje]'}"
            if msg['respuesta']:
                resumen += f"\n   🤖: {msg['respuesta'][:80]}"
        
        return resumen
        
    except Exception as e:
        app.logger.error(f"Error generando resumen: {e}")
        return f"Error generando resumen para {numero}"

def es_mensaje_repetido(numero, mensaje_actual, config=None):
    """Verifica si el mensaje actual es muy similar al anterior"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute('''
            SELECT mensaje FROM conversaciones 
            WHERE numero = %s 
            ORDER BY timestamp DESC 
            LIMIT 1
        ''', (numero,))
        
        ultimo_mensaje = cursor.fetchone()
        cursor.close()
        conn.close()
        
        # ✅ VERIFICAR SI HAY MENSAJE Y NO ES NONE
        if ultimo_mensaje and ultimo_mensaje.get('mensaje'):
            # Comparar similitud de mensajes
            similitud = calcular_similitud(mensaje_actual, ultimo_mensaje['mensaje'])
            return similitud > 0.8  # Si son más del 80% similares
            
    except Exception as e:
        app.logger.error(f"Error verificando mensaje repetido: {e}")
    
    return False

def calcular_similitud(texto1, texto2):
    """Calcula similitud entre dos textos (simple)"""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, texto1.lower(), texto2.lower()).ratio()

def es_respuesta_a_pregunta(mensaje):
    """
    Detecta si el mensaje es una respuesta a una pregunta previa del asistente
    en lugar de una nueva solicitud de cita/pedido.
    """
    mensaje_lower = mensaje.lower()
    
    # Patrones que indican que es una respuesta, no una nueva solicitud
    patrones_respuesta = [
        'sí', 'si', 'no', 'claro', 'ok', 'vale', 'correcto',
        'está bien', 'de acuerdo', 'perfecto', 'sip', 'nop',
        'mañana', 'hoy', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes',
        'sábado', 'domingo', 'la semana', 'el próximo', 'a las'
    ]
    
    # Si el mensaje contiene alguna de estas palabras, probablemente es una respuesta
    for patron in patrones_respuesta:
        if patron in mensaje_lower:
            return True
    
    # Si es muy corto, probablemente es una respuesta
    if len(mensaje_lower.split()) <= 3:
        return True
    
    return False

def enviar_alerta_humana(numero_cliente, mensaje_clave, resumen, config=None):
    if config is None:
        config = obtener_configuracion_por_host()

    contexto_consulta = obtener_contexto_consulta(numero_cliente, config)
    if config is None:
        app.logger.error("🔴 Configuración no disponible para enviar alerta")
        return
    
    """Envía alerta de intervención humana usando mensaje normal (sin template)"""
    mensaje = f"🚨 *ALERTA: Intervención Humana Requerida*\n\n"
    """Envía alerta de intervención humana usando mensaje normal (sin template)"""
    mensaje = f"🚨 *ALERTA: Intervención Humana Requerida*\n\n"
    mensaje += f"👤 *Cliente:* {numero_cliente}\n"
    mensaje += f"📞 *Número:* {numero_cliente}\n"
    mensaje += f"💬 *Mensaje clave:* {mensaje_clave[:100]}{'...' if len(mensaje_clave) > 100 else ''}\n\n"
    mensaje += f"📋 *Resumen:*\n{resumen[:800]}{'...' if len(resumen) > 800 else ''}\n\n"
    mensaje += f"⏰ *Hora:* {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
    mensaje += f"🎯 *INFORMACIÓN DEL PROYECTO/CONSULTA:*\n"
    mensaje += f"{contexto_consulta}\n\n"
    mensaje += f"_________________________________________\n"
    mensaje += f"📊 Atiende desde el CRM o responde directamente por WhatsApp"
    
    # Enviar mensaje normal (sin template) a tu número personal
    enviar_mensaje(ALERT_NUMBER, mensaje, config)
    enviar_mensaje('5214493432744', mensaje, config)#me quiero enviar un mensaje a mi mismo
    app.logger.info(f"📤 Alerta humana enviada para {numero_cliente} desde {config['dominio']}")

def enviar_informacion_completa(numero_cliente, config=None):
    """Envía toda la información del cliente a ambos números"""
    if config is None:
        config = obtener_configuracion_por_host()
    try:
        # Obtener información del contacto
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM contactos WHERE numero_telefono = %s",
            (numero_cliente,)
        )
        contacto = cursor.fetchone()
        
        # Obtener historial reciente
        cursor.execute(
            "SELECT * FROM conversaciones WHERE numero = %s ORDER BY timestamp DESC LIMIT 10",
            (numero_cliente,)
        )
        historial = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Construir mensaje completo
        mensaje_completo = "📋 *INFORMACIÓN COMPLETA DEL CLIENTE*\n\n"
        mensaje_completo += f"📞 *Número:* {numero_cliente}\n"
        
        if contacto:
            mensaje_completo += f"👤 *Nombre:* {contacto.get('nombre', 'No disponible')}\n"
            mensaje_completo += f"🏷️ *Alias:* {contacto.get('alias', 'No asignado')}\n"
            mensaje_completo += f"🌐 *Plataforma:* {contacto.get('plataforma', 'WhatsApp')}\n"
        
        mensaje_completo += f"\n📊 *Total mensajes:* {len(historial)}\n"
        mensaje_completo += f"🕒 *Última interacción:* {historial[0]['timestamp'].strftime('%d/%m/%Y %H:%M') if historial else 'N/A'}\n\n"
        
        mensaje_completo += "💬 *Últimos mensajes:*\n"
        for i, msg in enumerate(historial[:3]):  # Solo últimos 3 mensajes
            hora_msg = msg['timestamp'].strftime('%H:%M') if msg.get('timestamp') else 'N/A'
            mensaje_completo += f"\n{i+1}. [{hora_msg}] 👤: {msg['mensaje'][:60]}"
            if msg['respuesta']:
                mensaje_completo += f"\n   🤖: {msg['respuesta'][:60]}"
        
        # Enviar mensaje completo a ambos números
        enviar_mensaje(ALERT_NUMBER, mensaje_completo, config)  # Número original
        enviar_mensaje("5214493432744", mensaje_completo, config)  # Nuevo número
        
        app.logger.info(f"📤 Información completa enviada para {numero_cliente} a ambos números")
        
    except Exception as e:
        app.logger.error(f"🔴 Error enviando información completa: {e}")        

# ——— Webhook ———
@app.route('/webhook', methods=['GET'])
def webhook_verification():
    # Obtener el host desde los headers para determinar qué verify token usar
    host = request.headers.get('Host', '')
    
    if 'laporfirianna' in host:
        verify_token = os.getenv("PORFIRIANNA_VERIFY_TOKEN")
    else:
        verify_token = os.getenv("MEKTIA_VERIFY_TOKEN")
    
    if request.args.get('hub.verify_token') == verify_token:
        return request.args.get('hub.challenge')
    return 'Token inválido', 403

# Modifica la función obtener_configuracion_por_phone_number_id
def obtener_configuracion_por_phone_number_id(phone_number_id):
    """Detecta automáticamente la configuración basada en el phone_number_id recibido"""
    for numero, config in NUMEROS_CONFIG.items():
        if str(config['phone_number_id']) == str(phone_number_id):
            return config
    # Fallback to default
    return NUMEROS_CONFIG['524495486142']

@app.route('/reparar-kanban')
def reparar_kanban():
    """Repara todos los contactos que no están en chat_meta"""
    config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    # Encontrar números en conversaciones que no están en chat_meta
    cursor.execute("""
        SELECT DISTINCT numero 
        FROM conversaciones 
        WHERE numero NOT IN (SELECT numero FROM chat_meta)
    """)
    
    numeros_sin_meta = [row['numero'] for row in cursor.fetchall()]
    
    for numero in numeros_sin_meta:
        app.logger.info(f"🔧 Reparando contacto en Kanban: {numero}")
        inicializar_chat_meta(numero, config)
    
    cursor.close()
    conn.close()
    
    return f"✅ Reparados {len(numeros_sin_meta)} contactos en Kanban"

# REEMPLAZA la función webhook con esta versión mejorada
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # ✅ VERIFICACIÓN CRÍTICA - asegurar que tenemos JSON
        if not request.is_json:
            app.logger.error("🔴 Error: No se recibió JSON en el webhook")
            return 'Invalid content type', 400
            
        payload = request.get_json()
        if not payload:
            app.logger.error("🔴 Error: JSON vacío o inválido")
            return 'Invalid JSON', 400
            
        app.logger.info(f"📥 Payload recibido: {json.dumps(payload, indent=2)[:500]}...")
        
        # ✅ VERIFICAR ESTRUCTURA BÁSICA DEL PAYLOAD
        if 'entry' not in payload or not payload['entry']:
            app.logger.error("🔴 Error: Payload sin 'entry'")
            return 'Invalid payload structure', 400
            
        entry = payload['entry'][0]
        if 'changes' not in entry or not entry['changes']:
            app.logger.error("🔴 Error: Entry sin 'changes'")
            return 'Invalid entry structure', 400
            
        change = entry['changes'][0]['value']
        mensajes = change.get('messages', [])
        
        if not mensajes:
            app.logger.info("⚠️ No hay mensajes en el payload")
            return 'OK', 200
            
        msg = mensajes[0]
        numero = msg['from']
        # Agregar esto inmediatamente:
        
       # CORRECCIÓN: Manejo robusto de texto
        texto = ''
        es_imagen = False
        es_audio = False
        es_video = False
        es_documento = False
        es_mi_numero = False  # ← Add this initialization
        # 🔥 DETECTAR CONFIGURACIÓN CORRECTA POR PHONE_NUMBER_ID
        phone_number_id = change.get('metadata', {}).get('phone_number_id')
        app.logger.info(f"📱 Phone Number ID recibido: {phone_number_id}")
        
       
        # 🔥 OBTENER CONFIGURACIÓN CORRECTA
        config = None
        for numero_config, config_data in NUMEROS_CONFIG.items():
            if str(config_data['phone_number_id']) == str(phone_number_id):
                config = config_data
                app.logger.info(f"✅ Configuración encontrada por phone_number_id: {config['dominio']}")
                break
                
        if config is None:
            app.logger.warning(f"⚠️ No se encontró configuración para phone_number_id: {phone_number_id}")
            config = obtener_configuracion_por_host()  # Fallback a detección por host
            app.logger.info(f"🔄 Usando configuración de fallback: {config.get('dominio', 'desconocido')}")
                # 🔥 AGREGAR ESTO - Inicializar el contacto SIEMPRE
        inicializar_chat_meta(numero, config)
        actualizar_info_contacto(numero, config)  # Para obtener nombre e imagen
        inicializar_chat_meta(numero, config)
         
        # 🛑 EVITAR PROCESAR EL MISMO MENSAJE MÚLTIPLES VECES
        message_id = msg.get('id')
        if not message_id:
            app.logger.error("🔴 Mensaje sin ID, no se puede prevenir duplicados")
            return 'OK', 200
            
        # 🛑 EVITAR PROCESAR EL MISMO MENSAJE MÚLTIPLES VECES
        message_id = msg.get('id')
        if not message_id:
            # Si no hay ID, crear uno basado en timestamp y contenido
            timestamp = msg.get('timestamp', '')
            message_id = f"{numero}_{timestamp}_{texto[:50]}"
            
        # Crear un hash único del mensaje para evitar duplicados
        message_hash = hashlib.md5(f"{numero}_{message_id}".encode()).hexdigest()

        # Verificar si ya procesamos este mensaje (solo si no es un audio/imagen para evitar falsos positivos)
        if not es_audio and not es_imagen and message_hash in processed_messages:
            app.logger.info(f"⚠️ Mensaje duplicado ignorado: {message_hash}")
            return 'OK', 200
            
        # Agregar a mensajes procesados (con timestamp para limpieza posterior)
        processed_messages[message_hash] = time.time()

        # Limpiar mensajes antiguos (más de 1 hora)
        current_time = time.time()
        for msg_hash, timestamp in list(processed_messages.items()):
            if current_time - timestamp > 3600:  # 1 hora
                del processed_messages[msg_hash]
        
        image_id = None
        imagen_base64 = None
        public_url = None
        transcripcion = None
        # En el webhook, después de procesar el mensaje:
        actualizar_info_contacto(numero, config)
        if 'text' in msg and 'body' in msg['text']:
            texto = msg['text']['body'].strip()
        elif 'image' in msg:
            es_imagen = True
            image_id = msg['image']['id']
            imagen_base64, public_url = obtener_imagen_whatsapp(image_id, config)
            texto = msg['image'].get('caption', '').strip()
            if not texto:
                texto = "El usuario envió una imagen"
            
            # Guardar solo el mensaje del usuario (sin respuesta aún)
            guardar_conversacion(numero, texto, None, config, public_url, True)
        elif 'audio' in msg:
            es_audio = True
            audio_id = msg['audio']['id']  # ✅ Para audio también
            audio_path, audio_url = obtener_audio_whatsapp(audio_id, config)
            if audio_path:
                transcripcion = transcribir_audio_con_openai(audio_path)
                texto = transcripcion if transcripcion else "No se pudo transcribir el audio"
            else:
                texto = "Error al procesar el audio"
        else:
            texto = f"[{msg.get('type', 'unknown')}] Mensaje no textual"
            
        app.logger.info(f"📝 Mensaje de {numero}: '{texto}' (imagen: {es_imagen}, audio: {es_audio})")
        
        # ⛔ BLOQUEAR MENSAJES DEL SISTEMA DE ALERTAS
        if numero == ALERT_NUMBER and any(tag in texto for tag in ['🚨 ALERTA:', '📋 INFORMACIÓN COMPLETA']):
            app.logger.info(f"⚠️ Mensaje del sistema de alertas, ignorando: {numero}")
            return 'OK', 200
        
        # 🔄 PARA MI NÚMERO PERSONAL: Permitir todo pero sin alertas
        es_mi_numero = numero in ['5214491182201', '524491182201', '5214493432744']
        
        if es_mi_numero:
            app.logger.info(f"🔵 Mensaje de mi número personal, procesando SIN alertas: {numero}")
        
        # ========== DETECCIÓN DE INTENCIONES PRINCIPALES ==========
        
        # 1. DETECTAR SOLICITUD DE CITA/PEDIDO
        if detectar_solicitud_cita_keywords(texto, config) or detectar_solicitud_cita_ia(texto, numero, config):
            app.logger.info(f"📅 Solicitud de {'pedido' if 'porfirianna' in config.get('dominio', '') else 'cita'} detectada de {numero}")
            
            # Obtener historial para contexto
            historial = obtener_historial(numero, limite=5, config=config)
            
            # Extraer información con contexto
            info_cita = extraer_info_cita_mejorado(texto, numero, historial, config)
            
            if info_cita:
                app.logger.info(f"📋 Información extraída: {json.dumps(info_cita, indent=2)}")
                
                # Validar si tenemos datos completos
                datos_completos, mensaje_error = validar_datos_cita_completos(info_cita, config)
                
                if datos_completos:
                    # Guardar la cita/pedido
                    cita_id = guardar_cita(info_cita, config)
                    
                    if cita_id:
                        # Enviar confirmación al cliente
                        enviar_confirmacion_cita(numero, info_cita, cita_id, config)
                        
                        # Enviar alerta al administrador
                        enviar_alerta_cita_administrador(info_cita, cita_id, config)
                        
                        respuesta = f"✅ ¡{'Pedido' if 'porfirianna' in config.get('dominio', '') else 'Cita'} confirmado! Te hemos enviado los detalles por mensaje. ID: #{cita_id}"
                    else:
                        respuesta = "❌ Lo siento, hubo un error al guardar tu solicitud. Por favor, intenta de nuevo."
                else:
                    # Faltan datos, solicitarlos
                    respuesta = mensaje_error
                    solicitar_datos_faltantes_cita(numero, info_cita, config)
            else:
                respuesta = "No pude entender la información de tu solicitud. ¿Podrías ser más específico?"
            
            # Enviar respuesta y guardar conversación
            enviar_mensaje(numero, respuesta, config)
            guardar_conversacion(numero, texto, respuesta, config)
            
            return 'OK', 200
        
        # 2. DETECTAR INTERVENCIÓN HUMANA
        if detectar_intervencion_humana_ia(texto, numero, config):
            app.logger.info(f"🚨 Solicitud de intervención humana detectada de {numero}")
            
            # Obtener historial para contexto
            historial = obtener_historial(numero, limite=5, config=config)
            
            # Extraer información con contexto
            info_intervencion = extraer_info_intervencion(texto, numero, historial, config)
            
            if info_intervencion:
                app.logger.info(f"📋 Información de intervención: {json.dumps(info_intervencion, indent=2)}")
                
                # Enviar alerta al administrador
                enviar_alerta_intervencion_humana(info_intervencion, config)
                
                # Responder al cliente
                respuesta = "🚨 He solicitado la intervención de un agente humano. Un representante se comunicará contigo a la brevedad."
            else:
                respuesta = "He detectado que necesitas ayuda humana. Un agente se contactará contigo pronto."
            
            # Enviar respuesta y guardar conversación
            enviar_mensaje(numero, respuesta, config)
            guardar_conversacion(numero, texto, respuesta, config)
            
            return 'OK', 200
        
        # 3. PROCESAMIENTO NORMAL DEL MENSAJE
        procesar_mensaje_normal(msg, numero, texto, es_imagen, es_audio, config, imagen_base64, transcripcion, es_mi_numero)
        return 'OK', 200
        
    except Exception as e:
        app.logger.error(f"🔴 ERROR CRÍTICO en webhook: {str(e)}")
        app.logger.error(traceback.format_exc())
        return 'Error interno del servidor', 500
    
# REEMPLAZA la función detectar_solicitud_cita_keywords con esta versión mejorada
def detectar_solicitud_cita_keywords(mensaje, config=None):
    """
    Detección mejorada por palabras clave de solicitud de cita/pedido
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    mensaje_lower = mensaje.lower().strip()
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    
    # Palabras clave ESPECÍFICAS para cada negocio
    if es_porfirianna:
        # Palabras clave para La Porfirianna (pedidos de comida)
        palabras_clave = [
            'pedir', 'ordenar', 'quiero', 'deseo', 'me gustaría', 'para llevar',
            'manden', 'envíen', 'comprar', 'quiero comprar', 'deseo comprar',
            'chilaquil', 'taco', 'gordita', 'quesadilla', 'sope', 'torta', 'comida',
            'menú', 'platillo', 'orden', 'pedido'
        ]
        
        # Palabras de confirmación
        palabras_confirmacion = [
            'sí', 'si', 'claro', 'correcto', 'afirmativo', 'ok', 'vale',
            'perfecto', 'exacto', 'así es', 'está bien', 'de acuerdo'
        ]
    else:
        # Palabras clave para Mektia (servicios digitales)
        palabras_clave = [
            'cita', 'agendar', 'consultoría', 'reunión', 'asesoría', 'cotización',
            'presupuesto', 'proyecto', 'servicio', 'contratar', 'quiero contratar',
            'necesito', 'requiero', 'me interesa', 'información', 'solicitar'
        ]
        
        palabras_confirmacion = [
            'sí', 'si', 'claro', 'correcto', 'afirmativo', 'ok', 'vale',
            'perfecto', 'exacto', 'así es', 'está bien', 'de acuerdo'
        ]
    
    # Verificar si es una respuesta de confirmación corta
    es_respuesta_corta = (
        any(palabra in mensaje_lower for palabra in palabras_confirmacion) and 
        len(mensaje_lower.split()) <= 3
    )
    
    # Verificar si contiene palabras clave principales
    contiene_palabras_clave = any(
        palabra in mensaje_lower for palabra in palabras_clave
    )
    
    # Detectar patrones específicos de solicitud
    patrones_solicitud = [
        'quiero un', 'deseo un', 'necesito un', 'me gustaría un',
        'quisiera un', 'puedo tener un', 'agendar una', 'solicitar un'
    ]
    
    contiene_patron = any(
        patron in mensaje_lower for patron in patrones_solicitud
    )
    
    # Es una solicitud si contiene palabras clave O patrones específicos O es respuesta corta de confirmación
    es_solicitud = contiene_palabras_clave or contiene_patron or es_respuesta_corta
    
    if es_solicitud:
        tipo = "pedido" if es_porfirianna else "cita"
        app.logger.info(f"✅ Solicitud de {tipo} detectada por keywords: '{mensaje_lower}'")
    
    return es_solicitud
# ——— UI ———
@app.route('/')
def inicio():
    config = obtener_configuracion_por_host()
    return redirect(url_for('home', config=config))

@app.route('/test-contacto')
def test_contacto(numero = '5214493432744'):
    """Endpoint para probar la obtención de información de contacto"""
    config = obtener_configuracion_por_host()
    nombre, imagen = obtener_nombre_perfil_whatsapp(numero, config)
    nombre, imagen = obtener_imagen_perfil_whatsapp(numero, config)
    return jsonify({
        'numero': numero,
        'nombre': nombre,
        'imagen': imagen,
        'config': config.get('dominio')
    })

def obtener_nombre_perfil_whatsapp(numero, config=None):
    """Obtiene el nombre del perfil de WhatsApp usando la versión CORRECTA de la API"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        numero_formateado = numero.replace('+', '').replace(' ', '')
        app.logger.info(f"🎯 SOLICITANDO NOMBRE para: {numero_formateado}")
        
        # ✅ VERSIÓN CORRECTA: v23.0
        url = f"https://graph.facebook.com/v23.0/{config['phone_number_id']}/contacts"
        app.logger.info(f"🌐 URL: {url}")
        
        # ✅ MÉTODO CORRECTO: POST con JSON body
        payload = {
            "user_numbers": [numero_formateado],
            "fields": ["profile"]  # ✅ Especificar campos que queremos
        }
        
        headers = {
            'Authorization': f'Bearer {config["whatsapp_token"]}',
            'Content-Type': 'application/json'
        }
        
        app.logger.info(f"📦 Payload: {json.dumps(payload)}")
        
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        
        app.logger.info(f"📡 Status: {response.status_code}")
        app.logger.info(f"📦 Response: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            app.logger.info(f"✅ JSON: {json.dumps(data, indent=2)}")
            
            # ✅ ESTRUCTURA CORRECTA para v23.0
            if 'data' in data and data['data']:
                contacto = data['data'][0]
                nombre = contacto.get('profile', {}).get('name')
                app.logger.info(f"👤 Nombre obtenido: {nombre}")
                return nombre
            else:
                app.logger.warning("❌ No hay 'data' en la respuesta")
        else:
            app.logger.error(f"💥 Error de API: {response.status_code}")
            
        return None
        
    except Exception as e:
        app.logger.error(f"🔥 Exception: {str(e)}")
        return None


    
def obtener_imagen_perfil_whatsapp(numero, config=None):
    """Obtiene la URL de la imagen de perfil de WhatsApp correctamente"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # Formatear número correctamente
        numero_formateado = numero.replace('+', '').replace(' ', '')
        
        # Endpoint CORRECTO para obtener imagen de perfil
        url = f"https://graph.facebook.com/v18.0/{config['phone_number_id']}"
        
        params = {
            'fields': 'contacts',
            'user_numbers': f'["{numero_formateado}"]',
            'access_token': config['whatsapp_token']
        }
        
        headers = {'Content-Type': 'application/json'}
        app.logger.info(f"🔍 Solicitando info contacto para: {numero_formateado}")
        response = requests.get(url, params=params, headers=headers, timeout=15)
        
        if response.status_code == 200:
            data = response.json()
            app.logger.info(f"📸 Respuesta imagen perfil: {json.dumps(data, indent=2)}")
            
            if 'contacts' in data and data['contacts']:
                contacto = data['contacts'][0]
                nombre = contacto.get('profile', {}).get('name')
                imagen_url = contacto.get('profile', {}).get('picture', {}).get('url')
                app.logger.info(f"📋 Contacto obtenido - Nombre: {nombre}, Imagen: {imagen_url}")
                
                # 🔥 CORRECCIÓN: Devuelve la URL de la imagen si existe
                if imagen_url:
                    return imagen_url
        
        return None
        
    except Exception as e:
        app.logger.error(f"🔴 Error obteniendo imagen de perfil: {e}")
        return None
    
def obtener_configuracion_por_host():
    """Obtiene la configuración basada en el host de la solicitud de forma robusta"""
    try:
        from flask import has_request_context
        if not has_request_context():
            return NUMEROS_CONFIG['524495486142']  # Default
        
        host = request.headers.get('Host', '').lower()
        referer = request.headers.get('Referer', '').lower()
        url = request.url.lower()
        
        app.logger.info(f"🔍 Config detection - Host: '{host}', Referer: '{referer}', URL: '{url}'")
        
        # Detección PRIORITARIA por subdominio explícito
        if any(dominio in host for dominio in ['laporfirianna', 'porfirianna']):
            app.logger.info("✅ Configuración detectada: La Porfirianna (por host)")
            return NUMEROS_CONFIG['524812372326']
        
        if any(dominio in referer for dominio in ['laporfirianna', 'porfirianna']):
            app.logger.info("✅ Configuración detectada: La Porfirianna (por referer)")
            return NUMEROS_CONFIG['524812372326']
        
        if any(dominio in url for dominio in ['laporfirianna', 'porfirianna']):
            app.logger.info("✅ Configuración detectada: La Porfirianna (por URL)")
            return NUMEROS_CONFIG['524812372326']
        
        # Default a Mektia
        app.logger.info("✅ Configuración por defecto: Mektia")
        return NUMEROS_CONFIG['524495486142']
            
    except Exception as e:
        app.logger.error(f"🔴 Error en obtener_configuracion_por_host: {e}")
        return NUMEROS_CONFIG['524495486142']

@app.route('/diagnostico')
def diagnostico():
    """Endpoint completo de diagnóstico"""
    try:
        config = obtener_configuracion_por_host()
        
        info = {
            'host': request.headers.get('Host'),
            'referer': request.headers.get('Referer'),
            'url': request.url,
            'config_detectada': config.get('dominio'),
            'config_db': config.get('db_name'),
            'timestamp': datetime.now().isoformat()
        }
        
        # Intentar conexión a BD
        try:
            conn = get_db_connection(config)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            info['bd_conexion'] = 'success'
            cursor.close()
            conn.close()
        except Exception as e:
            info['bd_conexion'] = f'error: {str(e)}'
        
        return jsonify(info)
        
    except Exception as e:
        return jsonify({'error': str(e)})    

@app.route('/home')
def home():
    config = obtener_configuracion_por_host()
    period = request.args.get('period', 'week')
    now    = datetime.now()
    start  = now - (timedelta(days=30) if period=='month' else timedelta(days=7))
    # Detectar configuración basada en el host
    period = request.args.get('period', 'week')
    now = datetime.now()
    conn = get_db_connection(config)  # ✅ Usar config
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(DISTINCT numero) FROM conversaciones WHERE timestamp>= %s;",
        (start,)
    )
    chat_counts = cursor.fetchone()[0]

    cursor.execute(
        "SELECT numero, COUNT(*) FROM conversaciones WHERE timestamp>= %s GROUP BY numero;",
        (start,)
    )
    messages_per_chat = cursor.fetchall()

    cursor.execute(
        "SELECT COUNT(*) FROM conversaciones WHERE respuesta<>'' AND timestamp>= %s;",
        (start,)
    )
    total_responded = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    labels = [num for num,_ in messages_per_chat]
    values = [cnt for _,cnt in messages_per_chat]

    return render_template('dashboard.html',
        chat_counts=chat_counts,
        messages_per_chat=messages_per_chat,
        total_responded=total_responded,
        period=period,
        labels=labels,
        values=values
    )

@app.route('/chats')
def ver_chats():
    config = obtener_configuracion_por_host()
    app.logger.info(f"🔧 Configuración detectada para chats: {config.get('dominio', 'desconocido')}")
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT 
          conv.numero, 
          COUNT(*) AS total_mensajes, 
          cont.imagen_url, 
          -- PRIORIDAD: alias > nombre > número
          COALESCE(cont.alias, cont.nombre, conv.numero) AS nombre_mostrado,
          cont.alias,
          cont.nombre,
          (SELECT mensaje FROM conversaciones 
           WHERE numero = conv.numero 
           ORDER BY timestamp DESC LIMIT 1) AS ultimo_mensaje,
          MAX(conv.timestamp) AS ultima_fecha
        FROM conversaciones conv
        LEFT JOIN contactos cont ON conv.numero = cont.numero_telefono
        GROUP BY conv.numero, cont.imagen_url, cont.alias, cont.nombre
        ORDER BY MAX(conv.timestamp) DESC
    """)
    chats = cursor.fetchall()
    # 🔥 CONVERTIR TIMESTAMPS A HORA DE MÉXICO - AQUÍ ESTÁ EL FIX
    for chat in chats:
        if chat.get('ultima_fecha'):
            # Si el timestamp ya tiene timezone info, convertirlo
            if chat['ultima_fecha'].tzinfo is not None:
                chat['ultima_fecha'] = chat['ultima_fecha'].astimezone(tz_mx)
            else:
                # Si no tiene timezone, asumir que es UTC y luego convertir
                chat['ultima_fecha'] = pytz.utc.localize(chat['ultima_fecha']).astimezone(tz_mx)
    cursor.close()
    conn.close()
    
    return render_template('chats.html',
        chats=chats, 
        mensajes=None,
        selected=None, 
        IA_ESTADOS=IA_ESTADOS,
        tenant_config=config
    )

@app.route('/chats/<numero>')
def ver_chat(numero):
    try:
        config = obtener_configuracion_por_host()
        app.logger.info(f"🔧 Configuración para chat {numero}: {config.get('db_name', 'desconocida')}")
        
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        
        # Consulta para los datos del chat
        cursor.execute("""
            SELECT DISTINCT
                conv.numero, 
                cont.imagen_url, 
                COALESCE(cont.alias, cont.nombre, conv.numero) AS nombre_mostrado,
                cont.alias,
                cont.nombre
            FROM conversaciones conv
            LEFT JOIN contactos cont ON conv.numero = cont.numero_telefono
            WHERE conv.numero = %s
            LIMIT 1;
        """, (numero,))
        chats = cursor.fetchall()

        # Consulta para mensajes - INCLUYENDO IMÁGENES
        cursor.execute("""
            SELECT numero, mensaje, respuesta, timestamp, imagen_url, es_imagen
            FROM conversaciones 
            WHERE numero = %s 
            ORDER BY timestamp ASC;
        """, (numero,))
        msgs = cursor.fetchall()

        # Convertir timestamps
        for msg in msgs:
            if msg.get('timestamp'):
                if msg['timestamp'].tzinfo is not None:
                    msg['timestamp'] = msg['timestamp'].astimezone(tz_mx)
                else:
                    msg['timestamp'] = pytz.utc.localize(msg['timestamp']).astimezone(tz_mx)

        cursor.close()
        conn.close()
        
        app.logger.info(f"✅ Chat cargado: {len(chats)} chats, {len(msgs)} mensajes")
        
        return render_template('chats.html',
            chats=chats, 
            mensajes=msgs,
            selected=numero, 
            IA_ESTADOS=IA_ESTADOS,
            tenant_config=config
        )
        
    except Exception as e:
        app.logger.error(f"🔴 ERROR CRÍTICO en ver_chat: {str(e)}")
        app.logger.error(traceback.format_exc())
        return render_template('error.html', 
                             error_message="Error al cargar el chat", 
                             error_details=str(e)), 500
                  
@app.route('/debug-db')
def debug_db():
    """Endpoint para verificar la conexión a la base de datos"""
    try:
        config = obtener_configuracion_por_host()
        app.logger.info(f"🔍 Verificando conexión a: {config.get('db_name')}")
        
        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE() as db, USER() as user")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'database': result[0] if result else 'unknown',
            'user': result[1] if result else 'unknown',
            'config_db': config.get('db_name'),
            'host': request.headers.get('Host')
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'config_db': config.get('db_name') if 'config' in locals() else 'unknown',
            'host': request.headers.get('Host')
        })

@app.before_request
def log_configuracion():
    if request.endpoint and request.endpoint != 'static':
        try:
            host = request.headers.get('Host', '').lower()
            referer = request.headers.get('Referer', '')
            config = obtener_configuracion_por_host()
            app.logger.info(f"🌐 [{request.endpoint}] Host: {host} | Referer: {referer} | BD: {config.get('db_name', 'desconocida')}")
        except Exception as e:
            app.logger.error(f"🔴 Error en log_configuracion: {e}")

@app.route('/toggle_ai/<numero>', methods=['POST'])
def toggle_ai(numero, config=None):
    config = obtener_configuracion_por_host()
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor()

        # Cambiar el valor (si es 1 pasa a 0, si es 0 pasa a 1)
        cursor.execute("""
            UPDATE contactos
            SET ia_activada = NOT COALESCE(ia_activada, 1)
            WHERE numero_telefono = %s
        """, (numero,))

        conn.commit()
        cursor.close()
        conn.close()

        app.logger.info(f"🔘 Estado IA cambiado para {numero}")
    except Exception as e:
        app.logger.error(f"Error al cambiar estado IA: {e}")

    return redirect(url_for('ver_chat', numero=numero))

@app.route('/send-manual', methods=['POST'])
def enviar_manual():
        config = obtener_configuracion_por_host()
        conn = get_db_connection(config)
        # ... código existente ...
        try:
            numero = request.form['numero']
            texto = request.form['texto'].strip()
            
            # Validar que el mensaje no esté vacío
            if not texto:
                flash('❌ El mensaje no puede estar vacío', 'error')
                return redirect(url_for('ver_chat', numero=numero))
            
            app.logger.info(f"📤 Enviando mensaje manual a {numero}: {texto[:50]}...")
            
            # 1. ENVIAR MENSAJE POR WHATSAPP
            enviar_mensaje(numero, texto)
            
            # 2. GUARDAR EN BASE DE DATOS (como mensaje manual)
            conn = get_db_connection(config)
            cursor = conn.cursor()
            
            timestamp_utc = datetime.utcnow()
            # 🔥 USAR TEXTO DESCRIPTIVO EN LUGAR DE NULL
            cursor.execute(
                "INSERT INTO conversaciones (numero, mensaje, respuesta, timestamp) VALUES (%s, %s, %s, %s);",
                (numero, '[Mensaje manual desde web]', texto, timestamp_utc)  # ← Sin NULLs
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            # 3. ACTUALIZAR KANBAN (mover a "Esperando Respuesta")
            try:
                actualizar_columna_chat(numero, 3)  # 3 = Esperando Respuesta
                app.logger.info(f"📊 Chat {numero} movido a 'Esperando Respuesta' en Kanban")
            except Exception as e:
                app.logger.error(f"⚠️ Error actualizando Kanban: {e}")
            
            # 4. MENSAJE DE CONFIRMACIÓN
            flash('✅ Mensaje enviado correctamente', 'success')
            app.logger.info(f"✅ Mensaje manual enviado con éxito a {numero}")
            
        except KeyError:
            flash('❌ Error: Número de teléfono no proporcionado', 'error')
            app.logger.error("🔴 Error: Falta parámetro 'numero' en enviar_manual")
        except Exception as e:
            flash('❌ Error al enviar el mensaje', 'error')
            app.logger.error(f"🔴 Error en enviar_manual: {e}")
        
        return redirect(url_for('ver_chat', numero=numero))
        
@app.route('/chats/<numero>/eliminar', methods=['POST'])
def eliminar_chat(numero):
    config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor()
    
    # Solo eliminar conversaciones, NO contactos
    cursor.execute("DELETE FROM conversaciones WHERE numero=%s;", (numero,))
    
    # Opcional: también eliminar de chat_meta si usas kanban
    try:
        cursor.execute("DELETE FROM chat_meta WHERE numero=%s;", (numero,))
    except:
        pass  # Ignorar si la tabla no existe
    
    conn.commit()
    cursor.close()
    conn.close()
    
    IA_ESTADOS.pop(numero, None)
    return redirect(url_for('ver_chats'))

    # ——— Configuración ———

def limpiar_estados_antiguos():
    """Limpia estados de conversación con más de 2 horas"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM estados_conversacion 
            WHERE timestamp < NOW() - INTERVAL 2 HOUR
        ''')
        conn.commit()
        cursor.close()
        conn.close()
        app.logger.info("🧹 Estados antiguos limpiados")
    except Exception as e:
        app.logger.error(f"Error limpiando estados: {e}")

# Ejecutar esta función periódicamente (puedes usar un scheduler)
def continuar_proceso_pedido(numero, mensaje, estado_actual, config=None):
    """Maneja la continuación de un pedido en proceso"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    datos = estado_actual.get('datos', {})
    paso_actual = datos.get('paso', 0)
    
    app.logger.info(f"🔄 Continuando pedido paso {paso_actual} para {numero}")
    
    if paso_actual == 1:  # Esperando dirección
        if any(palabra in mensaje.lower() for palabra in ['calle', 'avenida', 'número', 'colonia', 'casa', 'departamento']):
            datos['direccion'] = mensaje
            datos['paso'] = 2
            actualizar_estado_conversacion(numero, "EN_PEDIDO", "solicitar_cambio", datos, config)
            return "✅ Dirección registrada. ¿Necesitas que te llevemos cambio? Si sí, ¿con cuánto vas a pagar?"
        else:
            return "🗺️ Por favor, proporciona tu dirección completa (calle, número, colonia)"
    
    elif paso_actual == 2:  # Esperando información de cambio
        datos['info_cambio'] = mensaje
        datos['paso'] = 3
        datos['completado'] = True
        actualizar_estado_conversacion(numero, "PEDIDO_COMPLETO", "pedido_finalizado", datos, config)
        
        # Guardar pedido completo
        guardar_cita(datos, config)
        
        return "🎉 ¡Pedido completado! Tu orden está en proceso. Te enviaremos un mensaje cuando salga para entrega. ¡Gracias!"
    
    # Si no coincide con ningún paso conocido
    return None
@app.route('/configuracion/<tab>', methods=['GET','POST'])
def configuracion_tab(tab):
        config = obtener_configuracion_por_host()
        if tab not in ['negocio','personalizacion']:
            abort(404)

        cfg = load_config(config)
        guardado = False
        if request.method == 'POST':
            if tab == 'negocio':
                cfg['negocio'] = {
                    'ia_nombre':      request.form['ia_nombre'],
                    'negocio_nombre': request.form['negocio_nombre'],
                    'descripcion':    request.form['descripcion'],
                    'url':            request.form['url'],
                    'direccion':      request.form['direccion'],
                    'telefono':       request.form['telefono'],
                    'correo':         request.form['correo'],
                    'que_hace':       request.form['que_hace']
                }
            else:
                cfg['personalizacion'] = {
                    'tono':     request.form['tono'],
                    'lenguaje': request.form['lenguaje']
                }
            save_config(cfg)
            guardado = True

        datos = cfg.get(tab, {})
        return render_template('configuracion.html',
            tabs=SUBTABS, active=tab,
            datos=datos, guardado=guardado
        )

@app.route('/configuracion/precios', methods=['GET'])
def configuracion_precios():
        config = obtener_configuracion_por_host()
        precios = obtener_todos_los_precios(config)
        return render_template('configuracion/precios.html',
            tabs=SUBTABS, active='precios',
            guardado=False,
            precios=precios,
            precio_edit=None
        )

@app.route('/configuracion/precios/editar/<int:pid>', methods=['GET'])
def configuracion_precio_editar(pid):
        config = obtener_configuracion_por_host()
        precios     = obtener_todos_los_precios(config)
        precio_edit = obtener_precio_por_id(pid, config)
        return render_template('configuracion/precios.html',
            tabs=SUBTABS, active='precios',
            guardado=False,
            precios=precios,
            precio_edit=precio_edit
        )

@app.route('/configuracion/precios/guardar', methods=['POST'])
def configuracion_precio_guardar():
        config = obtener_configuracion_por_host()
        data = request.form.to_dict()
        conn   = get_db_connection(config)
        cursor = conn.cursor()
        if data.get('id'):
            cursor.execute("""
                UPDATE precios
                   SET servicio=%s, descripcion=%s, precio=%s, moneda=%s
                 WHERE id=%s;
            """, (
                data['servicio'],
                data.get('descripcion',''),
                data['precio'],
                data['moneda'],
                data['id']
            ))
        else:
            cursor.execute("""
                INSERT INTO precios (servicio, descripcion, precio, moneda)
                VALUES (%s,%s,%s,%s);
            """, (
                data['servicio'],
                data.get('descripcion',''),
                data['precio'],
                data['moneda']
            ))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('configuracion_precios'))

@app.route('/configuracion/precios/borrar/<int:pid>', methods=['POST'])
def configuracion_precio_borrar(pid):
        config = obtener_configuracion_por_host()
        conn   = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM precios WHERE id=%s;", (pid,))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('configuracion_precios'))

    # ——— Kanban ———

def verificar_tablas_bd(config):
    """Verifica que todas las tablas necesarias existan en la base de datos"""
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor()
        
        tablas_requeridas = ['conversaciones', 'contactos', 'chat_meta']
        tablas_existentes = []
        
        cursor.execute("SHOW TABLES")
        for (table_name,) in cursor.fetchall():
            tablas_existentes.append(table_name)
        
        cursor.close()
        conn.close()
        
        faltantes = [tabla for tabla in tablas_requeridas if tabla not in tablas_existentes]
        
        if faltantes:
            app.logger.error(f"❌ Tablas faltantes en {config['db_name']}: {faltantes}")
            return False
        else:
            app.logger.info(f"✅ Todas las tablas existen en {config['db_name']}")
            return True
            
    except Exception as e:
        app.logger.error(f"🔴 Error verificando tablas: {e}")
        return False

# Llama esta función al inicio para ambas bases de datos
with app.app_context():
    # Esta función se ejecutará cuando la aplicación se inicie
    app.logger.info("🔍 Verificando tablas en todas las bases de datos...")
    for nombre, config in NUMEROS_CONFIG.items():
        verificar_tablas_bd(config)
def verificar_todas_tablas():
    app.logger.info("🔍 Verificando tablas en todas las bases de datos...")
    for nombre, config in NUMEROS_CONFIG.items():
        verificar_tablas_bd(config)

@app.route('/kanban')
def ver_kanban(config=None):
    config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)

    # 1) Cargamos las columnas Kanban
    cursor.execute("SELECT * FROM kanban_columnas ORDER BY orden;")
    columnas = cursor.fetchall()

    # 2) CONSULTA DEFINITIVA - compatible con only_full_group_by
    # En ver_kanban(), modifica la consulta para mejor manejo de nombres: 
    cursor.execute("""
        SELECT 
            cm.numero,
            cm.columna_id,
            MAX(c.timestamp) AS ultima_fecha,
            (SELECT mensaje FROM conversaciones 
             WHERE numero = cm.numero 
             ORDER BY timestamp DESC LIMIT 1) AS ultimo_mensaje,
            MAX(cont.imagen_url) AS avatar,
            MAX(cont.plataforma) AS canal,
            -- PRIORIDAD: alias > nombre de perfil > número
            COALESCE(
                MAX(cont.alias), 
                MAX(cont.nombre), 
                cm.numero
            ) AS nombre_mostrado,
            (SELECT COUNT(*) FROM conversaciones 
             WHERE numero = cm.numero AND respuesta IS NULL) AS sin_leer
        FROM chat_meta cm
        LEFT JOIN contactos cont ON cont.numero_telefono = cm.numero
        LEFT JOIN conversaciones c ON c.numero = cm.numero
        GROUP BY cm.numero, cm.columna_id
        ORDER BY ultima_fecha DESC;
    """)
    chats = cursor.fetchall()

    # 🔥 CONVERTIR TIMESTAMPS A HORA DE MÉXICO (igual que en conversaciones)
    for chat in chats:
        if chat.get('ultima_fecha'):
            # Si el timestamp ya tiene timezone info, convertirlo
            if chat['ultima_fecha'].tzinfo is not None:
                chat['ultima_fecha'] = chat['ultima_fecha'].astimezone(tz_mx)
            else:
                # Si no tiene timezone, asumir que es UTC y luego convertir
                chat['ultima_fecha'] = pytz.utc.localize(chat['ultima_fecha']).astimezone(tz_mx)

    cursor.close()
    conn.close()

    return render_template('kanban.html', columnas=columnas, chats=chats)     

@app.route('/kanban/mover', methods=['POST'])
def kanban_mover():
        config = obtener_configuracion_por_host()
        conn = get_db_connection(config)
        data = request.get_json()
        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute(
          "UPDATE chat_meta SET columna_id=%s WHERE numero=%s;",
          (data['columna_id'], data['numero'])
        )
        conn.commit(); cursor.close(); conn.close()
        return '', 204
        
@app.route('/contactos/<numero>/alias', methods=['POST'])
def guardar_alias_contacto(numero, config=None):
        config = obtener_configuracion_por_host()
        alias = request.form.get('alias','').strip()
        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE contactos SET alias=%s WHERE numero_telefono=%s",
            (alias if alias else None, numero)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return '', 204

    # ——— Páginas legales —

@app.route('/proxy-audio/<path:audio_url>')
def proxy_audio(audio_url):
    """Proxy para evitar problemas de CORS con archivos de audio"""
    try:
        response = requests.get(audio_url, timeout=10)
        return Response(response.content, mimetype=response.headers.get('content-type', 'audio/ogg'))
    except Exception as e:
        return str(e), 500

@app.route('/privacy-policy')
def privacy_policy():
        return render_template('privacy_policy.html')

@app.route('/terms-of-service')
def terms_of_service():
        return render_template('terms_of_service.html')

@app.route('/data-deletion')
def data_deletion():
        return render_template('data_deletion.html')

@app.route('/test-alerta')
def test_alerta():
    config = obtener_configuracion_por_host()  # 🔥 OBTENER CONFIG PRIMERO
    enviar_alerta_humana("Prueba", "524491182201", "Mensaje clave", "Resumen de prueba.", config)  # 🔥 AGREGAR config
    return "🚀 Test alerta disparada."

def obtener_chat_meta(numero, config=None):
        if config is None:
            config = obtener_configuracion_por_host()
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM chat_meta WHERE numero = %s;", (numero,))
        meta = cursor.fetchone()
        cursor.close()
        conn.close()
        return meta

def inicializar_chat_meta(numero, config=None):
    """Inicializa el chat meta y asegura que el contacto exista con su nombre e imagen"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    try:
        # 1. Primero verificar si el contacto ya existe
        cursor.execute("SELECT * FROM contactos WHERE numero_telefono = %s", (numero,))
        contacto_existente = cursor.fetchone()
        
        # 2. Obtener información de WhatsApp solo si no existe o está incompleta
        if not contacto_existente or not contacto_existente.get('nombre') or not contacto_existente.get('imagen_url'):
            nombre_perfil = obtener_nombre_perfil_whatsapp(numero, config)
            imagen_perfil = obtener_imagen_perfil_whatsapp(numero, config)
            
            app.logger.info(f"📋 Obteniendo perfil para {numero}: nombre={nombre_perfil}, imagen={imagen_perfil}")
        
        # 3. Insertar/actualizar contacto (CORREGIDO - sin fecha_creacion)
        cursor.execute("""
            INSERT INTO contactos 
                (numero_telefono, nombre, imagen_url, plataforma) 
            VALUES (%s, %s, %s, 'WhatsApp')
            ON DUPLICATE KEY UPDATE 
                nombre = COALESCE(%s, nombre),
                imagen_url = COALESCE(%s, imagen_url)
        """, (numero, nombre_perfil, imagen_perfil, nombre_perfil, imagen_perfil))
        
        # 4. Insertar/actualizar en chat_meta
        cursor.execute("""
            INSERT INTO chat_meta (numero, columna_id) 
            VALUES (%s, 1)
        """, (numero,))
        
        conn.commit()
        app.logger.info(f"✅ Contacto inicializado/actualizado: {numero}")
        
    except Exception as e:
        app.logger.error(f"❌ Error inicializando chat meta para {numero}: {e}")
        conn.rollback()
    
    finally:
        cursor.close()
        conn.close()

@app.route('/reparar-contactos')
def reparar_contactos():
    """Repara todos los contactos que no están en chat_meta"""
    config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    # Encontrar contactos que no están en chat_meta
    cursor.execute("""
        SELECT c.numero_telefono 
        FROM contactos c 
        LEFT JOIN chat_meta cm ON c.numero_telefono = cm.numero 
        WHERE cm.numero IS NULL
    """)
    
    contactos_sin_meta = [row['numero_telefono'] for row in cursor.fetchall()]
    
    for numero in contactos_sin_meta:
        app.logger.info(f"🔧 Reparando contacto: {numero}")
        inicializar_chat_meta(numero, config)
    
    cursor.close()
    conn.close()
    
    return f"✅ Reparados {len(contactos_sin_meta)} contactos sin chat_meta"

def actualizar_columna_chat(numero, columna_id, config=None):
        if config is None:
            config = obtener_configuracion_por_host()
        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE chat_meta SET columna_id = %s 
            WHERE numero = %s;
        """, (columna_id, numero))
        conn.commit()
        cursor.close()
        conn.close()

def actualizar_info_contacto(numero, config=None):
    """Actualiza la información del contacto (nombre e imagen)"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        nombre_perfil = obtener_nombre_perfil_whatsapp(numero, config)
        imagen_perfil = obtener_imagen_perfil_whatsapp(numero, config)
        
        conn = get_db_connection(config)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO contactos (numero_telefono, nombre, imagen_url, plataforma) 
            VALUES (%s, %s, %s, 'WhatsApp')
            ON DUPLICATE KEY UPDATE 
                nombre = COALESCE(VALUES(nombre), nombre),
                imagen_url = COALESCE(VALUES(imagen_url), imagen_url)
        """, (numero, nombre_perfil, imagen_perfil))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        app.logger.info(f"🔄 Contacto actualizado: {numero} - Nombre: {nombre_perfil}")
        
    except Exception as e:
        app.logger.error(f"Error actualizando contacto {numero}: {e}")

def evaluar_movimiento_automatico(numero, mensaje, respuesta, config=None):
        if config is None:
            config = obtener_configuracion_por_host()
    
        historial = obtener_historial(numero, limite=5, config=config)
        
        # Si es primer mensaje, mantener en "Nuevos"
        if len(historial) <= 1:
            return 1  # Nuevos
        
        # Si hay intervención humana, mover a "Esperando Respuesta"
        if detectar_intervencion_humana_ia(mensaje, respuesta, numero):
            return 3  # Esperando Respuesta
        
        # Si tiene más de 2 mensajes, mover a "En Conversación"
        if len(historial) >= 2:
            return 2  # En Conversación
        
        # Si no cumple nada, mantener donde está
        meta = obtener_chat_meta(numero)
        return meta['columna_id'] if meta else 1

def obtener_contexto_consulta(numero, config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        
        # Obtener los últimos mensajes para entender el contexto
        cursor.execute("""
            SELECT mensaje, respuesta 
            FROM conversaciones 
            WHERE numero = %s 
            ORDER BY timestamp DESC 
            LIMIT 5
        """, (numero,))
        
        mensajes = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not mensajes:
            return "No hay historial de conversación reciente."
        
        # Analizar el contexto de la conversación
        contexto = ""
        
        # Buscar menciones de servicios/proyectos
        servicios_mencionados = []
        for msg in mensajes:
            mensaje_texto = msg['mensaje'].lower() if msg['mensaje'] else ""  # 🔥 CORREGIR ACCESO
            for servicio in servicios_clave:
                if servicio in mensaje_texto and servicio not in servicios_mencionados:
                    servicios_mencionados.append(servicio)
        
        if servicios_mencionados:
            contexto += f"📋 *Servicios mencionados:* {', '.join(servicios_mencionados)}\n"
        
        # Extraer información específica del último mensaje
        ultimo_mensaje = mensajes[0]['mensaje'] or "" if mensajes else ""  # 🔥 CORREGIR ACCESO
        if len(ultimo_mensaje) > 10:
            contexto += f"💬 *Último mensaje:* {ultimo_mensaje[:150]}{'...' if len(ultimo_mensaje) > 150 else ''}\n"
        
        # Intentar detectar urgencia o tipo de consulta
        palabras_urgentes = ['urgente', 'rápido', 'inmediato', 'pronto', 'ya']
        if any(palabra in ultimo_mensaje.lower() for palabra in palabras_urgentes):
            contexto += "🚨 *Tono:* Urgente\n"
        
        return contexto if contexto else "No se detectó contexto relevante."
        
    except Exception as e:
        app.logger.error(f"Error obteniendo contexto: {e}")
        return "Error al obtener contexto"

# Agrega estas rutas de diagnóstico ANTES del if __name__ == '__main__':

@app.route('/debug-contacto/<numero>')
def debug_contacto(numero):
    """Endpoint completo de diagnóstico de contacto"""
    config = obtener_configuracion_por_host()
    
    # 1. Probar la función de obtener nombre
    nombre_directo = obtener_nombre_perfil_whatsapp(numero, config)
    
    # 2. Verificar en base de datos
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM contactos WHERE numero_telefono = %s", (numero,))
    contacto_db = cursor.fetchone()
    cursor.close()
    conn.close()
    
    return jsonify({
        'numero': numero,
        'nombre_obtenido_directo': nombre_directo,
        'en_base_datos': contacto_db,
        'config_usada': {
            'dominio': config.get('dominio'),
            'phone_number_id': config.get('phone_number_id'),
            'db_name': config.get('db_name')
        },
        'timestamp': datetime.now().isoformat()
    })

@app.route('/test-api-manual/<numero>')
def test_api_manual(numero):
    """Test manual de la API de WhatsApp - VERSIÓN v23.0"""
    config = obtener_configuracion_por_host()
    
    numero_formateado = numero.replace('+', '').replace(' ', '')
    
    # ✅ VERSIÓN CORRECTA: v23.0
    url = f"https://graph.facebook.com/v23.0/{config
    
    params = {
        'fields': 'contacts',
        'user_numbers': f'["{numero_formateado}"]',
        'access_token': config['whatsapp_token']
    }
    
    try:
        response = requests.get(url, params=params, timeout=15)
        
        # Log detallado para debugging
        app.logger.info(f"🔍 API Request: {response.url}")
        app.logger.info(f"🔍 Status Code: {response.status_code}")
        app.logger.info(f"🔍 Response: {response.text}")
        
        return jsonify({
            'status_code': response.status_code,
            'response': response.json() if response.status_code == 200 else response.text,
            'url_solicitada': response.url,
            'numero_formateado': numero_formateado,
            'params': params
        })
    except Exception as e:
        app.logger.error(f"❌ Error en test-api-manual: {e}")
        return jsonify({'error': str(e)})

@app.route('/forzar-actualizacion/<numero>')
def forzar_actualizacion(numero):
    """Forzar actualización completa del contacto"""
    config = obtener_configuracion_por_host()
    
    try:
        # 1. Eliminar contacto existente si hay
        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM contactos WHERE numero_telefono = %s", (numero,))
        conn.commit()
        cursor.close()
        conn.close()
        
        # 2. Esperar un momento
        time.sleep(1)
        
        # 3. Volver a crear desde cero
        actualizar_info_contacto(numero, config)
        
        # 4. Verificar resultado
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM contactos WHERE numero_telefono = %s", (numero,))
        resultado = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return jsonify({
            'contacto_actualizado': resultado,
            'status': 'forzado'
        })
        
    except Exception as e:
        return jsonify({'error': str(e)})

# También agrega esta ruta simple para verificar que el servidor funciona
@app.route('/status')
def status():
    return jsonify({'status': 'ok', 'server': 'mektia.com', 'time': datetime.now().isoformat()})
    
if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5000, help='Puerto para ejecutar la aplicación')
    args = parser.parse_args()
    
    # Crear tablas necesarias - usar configuración por defecto
    crear_tabla_citas(config=NUMEROS_CONFIG['524495486142'])
    
    app.run(host='0.0.0.0', port=args.port, debug=False)  # ← Cambia a False para producción


