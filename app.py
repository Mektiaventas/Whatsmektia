# Agrega esto con los otros imports al inicio
import traceback
import pytz
import os
import logging
import json 
import base64
import argparse
import mysql.connector
from flask import Flask, request, render_template, redirect, url_for, abort, flash, jsonify
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
from decimal import Decimal
import re
import io
from PIL import Image

tz_mx = pytz.timezone('America/Mexico_City')
guardado = True
load_dotenv()  # Cargar desde archivo específico
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cualquier-cosa")
app.logger.setLevel(logging.INFO)

# ——— Env vars ———
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ALERT_NUMBER = os.getenv("ALERT_NUMBER")
SECRET_KEY = os.getenv("SECRET_KEY", "cualquier-cosa")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
IA_ESTADOS = {}

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

if not NUMEROS_CONFIG['524495486142']:
    soli = "cita"
    servicios_clave = [
            'página web', 'sitio web', 'ecommerce', 'tienda online',
            'aplicación', 'app', 'software', 'sistema',
            'marketing', 'seo', 'redes sociales', 'publicidad',
            'diseño', 'branding', 'logo', 'identidad visual',
            'hosting', 'dominio', 'mantenimiento', 'soporte',
            'electronica', 'hardware', 'iot', 'internet de las cosas',
        ]
else:
    soli = "orden"
    servicios_clave = [
            'gorditas', 'antojitos', 'tacos', 'comida mexicana', 'catering', 'gordita',
            'sopes', 'quesadillas', 'tlacoyos', 'huaraches', 'antojitos mexicanos'
        ]

# Configuración por defecto (para backward compatibility)
WHATSAPP_TOKEN = os.getenv("MEKTIA_WHATSAPP_TOKEN")  # Para funciones que aún no están adaptadas
DB_HOST = os.getenv("MEKTIA_DB_HOST")
DB_USER = os.getenv("MEKTIA_DB_USER")
DB_PASSWORD = os.getenv("MEKTIA_DB_PASSWORD")
DB_NAME = os.getenv("MEKTIA_DB_NAME")
MI_NUMERO_BOT = os.getenv("MEKTIA_PHONE_NUMBER_ID")
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
        # Detectar configuración basada en el host
        config = obtener_configuracion_por_host()
    
    app.logger.info(f"🗄️ Conectando a BD: {config['db_name']}")
    
    return mysql.connector.connect(
        host=config['db_host'],
        user=config['db_user'],
        password=config['db_password'],
        database=config['db_name']
    )

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

def extraer_info_cita_mejorado(mensaje, numero, historial=None, config=None):
    """
    Versión mejorada que usa el historial de conversación para extraer información
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    # Determinar el tipo de negocio
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    
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
        if es_porfirianna:
            prompt_cita = f"""
            Extrae la información del pedido solicitado basándote en este mensaje y el historial de conversación.
            
            MENSAJE ACTUAL: "{mensaje}"
            
            HISTORIAL DE CONVERSACIÓN:
            {contexto_historial}
            
            Devuélvelo en formato JSON con estos campos:
            - servicio_solicitado (string: el platillo o comida solicitada, o null si no se especifica)
            - fecha_sugerida (string en formato YYYY-MM-DD o null - opcional para pedidos)
            - hora_sugerida (string en formato HH:MM o null - opcional para pedidos)
            - nombre_cliente (string o null si no se especifica)
            - telefono (string, usar este número: {numero})
            - estado (siempre "pendiente")
            - datos_completos (boolean: true si tiene todos los datos necesarios)
            
            Datos necesarios para considerar completo un pedido:
            - servicio_solicitado: siempre requerido (qué platillo quiere)
            - nombre_cliente: siempre requerido
            
            Para La Porfirianna (comida), los campos de fecha y hora son opcionales.
            """
        else:
            prompt_cita = f"""
            Extrae la información de la cita solicitada basándote en este mensaje y el historial de conversación.
            
            MENSAJE ACTUAL: "{mensaje}"
            
            HISTORIAL DE CONVERSACIÓN:
            {contexto_historial}
            
            Devuélvelo en formato JSON con estos campos:
            - servicio_solicitado (string: tipo de servicio solicitado o null si no se especifica)
            - fecha_sugerida (string en formato YYYY-MM-DD o null si no se especifica)
            - hora_sugerida (string en formato HH:MM o null si no se especifica)
            - nombre_cliente (string o null si no se especifica)
            - telefono (string, usar este número: {numero})
            - estado (siempre "pendiente")
            - datos_completos (boolean: true si tiene todos los datos necesarios)
            
            Datos necesarios para considerar completa una cita:
            - servicio_solicitado: siempre requerido
            - fecha_sugerida: requerido para citas
            - nombre_cliente: siempre requerido
            - hora_sugerida: opcional pero recomendado
            
            Para Mektia (servicios), se necesitan todos los datos básicos.
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
        app.logger.error(f"Error extrayendo info de {'pedido' if es_porfirianna else 'cita'}: {e}")
        return None
    
def detectar_solicitud_cita_ia(mensaje, numero, config=None):
    """
    Usa DeepSeek para detectar si el mensaje es una solicitud de cita/pedido
    Devuelve True si la IA detecta intención de agendar cita/hacer pedido
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    # Primero verificar con la lista de palabras clave existente (más rápida)
    if detectar_solicitud_cita_keywords(mensaje):
        return True
    
    # Si no se detectó con keywords, usar IA para análisis semántico
    try:
        prompt = f"""
        Evalúa si el siguiente mensaje indica que el usuario quiere agendar una {soli} o hacer un pedido.
        Responde SOLO con "SI" o "NO".
        
        Mensaje: "{mensaje}"
        
        Considera que podría ser una solicitud de {soli} si:
        - Pide agendar, reservar, programar una cita, consulta, sesión o servicio
        - Solicita horarios, disponibilidad, turnos
        - Quiere hacer un pedido, ordenar, comprar, encargar
        - Pregunta por menú, precios, servicios disponibles
        - Menciona necesidad de atención, evaluación, asesoría
        - Solicita información para contratar un servicio
        - Pide cotización, presupuesto o información comercial
        
        Responde "SI" solo si hay una clara intención de agendar {soli} o hacer pedido.
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
        
        app.logger.info(f"🔍 IA detectó solicitud de {soli}: {respuesta_ia} para mensaje: {mensaje[:50]}...")
        
        return "SI" in respuesta_ia
        
    except Exception as e:
        app.logger.error(f"Error en detección IA de {soli}: {e}")
        # Fallback a detección por keywords si la IA falla
        return detectar_solicitud_cita_keywords(mensaje)

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

def extraer_info_cita_mejorado(mensaje, numero, historial=None, config=None):
    """
    Versión mejorada que usa el historial de conversación para extraer información
    """
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
        prompt_cita = f"""
        Extrae la información de la {soli} solicitada basándote en este mensaje y el historial de conversación.
        
        MENSAJE ACTUAL: "{mensaje}"
        
        HISTORIAL DE CONVERSACIÓN:
        {contexto_historial}
        
        Devuélvelo en formato JSON con estos campos:
        - servicio_solicitado (string o null si no se especifica)
        - fecha_sugerida (string en formato YYYY-MM-DD o null si no se especifica)
        - hora_sugerida (string en formato HH:MM o null si no se especifica)
        - nombre_cliente (string o null si no se especifica)
        - telefono (string, usar este número: {numero})
        - estado (siempre "pendiente")
        - datos_completos (boolean: true si tiene todos los datos necesarios)
        
        Datos necesarios para considerar completa una {soli}:
        - servicio_solicitado: siempre requerido
        - fecha_sugerida: requerido para citas, opcional para pedidos
        - nombre_cliente: siempre requerido
        - hora_sugerida: opcional
        - fecha_sugerida: opcional para pedidos
        
        Si no se puede determinar algún campo, usa null.
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
        app.logger.error(f"Error extrayendo info de {soli}: {e}")
        return None

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
                MAX(cont.imagen_url) AS avatar,
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
    """Guarda la cita en la base de datos"""
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
        
        # Corregir esta parte - eliminar la referencia a guardado no definida
        if info_cita.get('servicio_solicitado') is None:
            app.logger.warning(f"⚠️ Guardando cita sin servicio solicitado: {info_cita}")

        conn.commit()
        cita_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        return cita_id
        
    except Exception as e:
        app.logger.error(f"Error guardando cita: {e}")
        return None

    
def enviar_confirmacion_cita(numero, info_cita, cita_id, config=None):
    """Envía confirmación de cita por WhatsApp"""
    if config is None:
        config = obtener_configuracion_por_host()
    try:
        mensaje_confirmacion = f"""
        📅 *Confirmación de {soli}* - ID: #{cita_id}

        ¡Hola! Hemos recibido tu solicitud de cita:

        *Servicio:* {info_cita.get('servicio_solicitado', 'Por confirmar')}
        *Fecha sugerida:* {info_cita.get('fecha_sugerida', 'Por confirmar')}
        *Hora sugerida:* {info_cita.get('hora_sugerida', 'Por confirmar')}

        📞 *Tu número:* {numero}

        ⏰ *Próximos pasos:*
        Nos pondremos en contacto contigo dentro de las próximas 24 horas para confirmar la disponibilidad.

        ¿Necesitas hacer algún cambio? Responde a este mensaje.

        ¡Gracias por confiar en nosotros! 🙏
        """
        
        enviar_mensaje(numero, mensaje_confirmacion, config)
        app.logger.info(f"✅ Confirmación de cita enviada a {numero}, ID: {cita_id}")
        
    except Exception as e:
        app.logger.error(f"Error enviando confirmación de cita: {e}")

def enviar_alerta_cita_administrador(info_cita, cita_id, config=None):
    """Envía alerta al administrador sobre nueva cita"""
    if config is None:
        config = obtener_configuracion_por_host()
    try:
        mensaje_alerta = f"""
        🚨 *NUEVA SOLICITUD DE {soli}* - ID: #{cita_id}

        *Cliente:* {info_cita.get('nombre_cliente', 'No especificado')}
        *Teléfono:* {info_cita.get('telefono')}

        *Servicio solicitado:* {info_cita.get('servicio_solicitado', 'No especificado')}
        *Fecha sugerida:* {info_cita.get('fecha_sugerida', 'No especificada')}
        *Hora sugerida:* {info_cita.get('hora_sugerida', 'No especificada')}

        ⏰ *Fecha de solicitud:* {datetime.now().strftime('%d/%m/%Y %H:%M')}

        📋 *Acción requerida:* Contactar al cliente para confirmar disponibilidad.
        """
        
        # Enviar a ambos números
        enviar_mensaje(ALERT_NUMBER, mensaje_alerta, config)
        enviar_mensaje('5214493432744', mensaje_alerta, config)
        app.logger.info(f"✅ Alerta de cita enviada a ambos administradores, ID: {cita_id}")
        
    except Exception as e:
        app.logger.error(f"Error enviando alerta de cita: {e}")

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
def obtener_historial(numero, limite=10, config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT mensaje, respuesta FROM conversaciones "
        "WHERE numero=%s ORDER BY timestamp DESC LIMIT %s;",
        (numero, limite)
    )
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return list(reversed(rows))

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
    1. No permitas que los usuarios agenden {'pedidos' if 'laporfirianna' in config.get('dominio', '') else 'citas'} sin haber obtenido todos los datos necesarios
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
        
def obtener_imagen_whatsapp(image_id, config=None):
    """Obtiene la imagen de WhatsApp y la convierte a base64 + guarda archivo"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # Usar la configuración correcta
        url = f"https://graph.facebook.com/v18.0/{config['phone_number_id']}"
        
        params = {
            'fields': 'profile_picture',
            'access_token': config['whatsapp_token']  # ← Usar variable de configuración
        }
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {config["whatsapp_token"]}'  # ← Usar variable
        }
        
        app.logger.info(f"🖼️ Obteniendo imagen WhatsApp")
        
        response = requests.get(url, headers=headers, timeout=30)
        
        if response.status_code != 200:
            app.logger.error(f"🔴 Error obteniendo imagen: {response.status_code} - {response.text}")
            return None, None
        
        # 2. Obtener la URL de descarga real
        image_data = response.json()
        download_url = image_data.get('url')
        
        if not download_url:
            app.logger.error(f"🔴 No se encontró URL de descarga de imagen: {image_data}")
            return None, None
            
        # 3. Descargar la imagen con autenticación
        image_response = requests.get(download_url, headers=headers, timeout=30)
        
        if image_response.status_code != 200:
            app.logger.error(f"🔴 Error descargando imagen: {image_response.status_code}")
            return None, None
        
        # 4. Convertir a base64 para OpenAI (formato correcto)
        image_base64 = base64.b64encode(image_response.content).decode('utf-8')
        
        # 5. Guardar la imagen localmente (opcional)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"whatsapp_image_{timestamp}.jpg"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        with open(filepath, "wb") as f:
            f.write(image_response.content)
        
        app.logger.info(f"✅ Imagen procesada: {filepath}")
        
        # 🔥 FORMATO CORRECTO para OpenAI: data:image/jpeg;base64,{base64_string}
        return f"data:image/jpeg;base64,{image_base64}", filename
        
    except Exception as e:
        app.logger.error(f"🔴 Error en obtener_imagen_whatsapp: {str(e)}")
        app.logger.error(traceback.format_exc())
        return None, None
            
def procesar_mensaje(texto, image_base64=None, filename=None):
    """Procesa el mensaje con la API de OpenAI, con soporte para imágenes"""
    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {OPENAI_API_KEY}"
        }
        
        # Preparar el payload según si hay imagen o no
        if image_base64:
            app.logger.info("👁️ Procesando mensaje con imagen...")
            
            payload = {
                "model": "gpt-4-vision-preview",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": texto
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_base64}"
                                }
                            }
                        ]
                    }
                ],
                "max_tokens": 1000
            }
        else:
            app.logger.info("💬 Procesando mensaje de texto...")
            
            payload = {
                "model": "gpt-3.5-turbo",
                "messages": [
                    {
                        "role": "system",
                        "content": "Eres un asistente útil que responde preguntas de manera clara y concisa."
                    },
                    {
                        "role": "user",
                        "content": texto
                    }
                ],
                "max_tokens": 500,
                "temperature": 0.7
            }
        
        # Realizar la solicitud
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        
        if response.status_code != 200:
            app.logger.error(f"🔴 Error API OpenAI: {response.status_code} - {response.text}")
            return "Lo siento, hubo un error al procesar tu solicitud."
        
        result = response.json()
        respuesta = result['choices'][0]['message']['content']
        
        app.logger.info(f"✅ Respuesta generada: {respuesta[:100]}...")
        return respuesta
        
    except requests.exceptions.Timeout:
        app.logger.error("🔴 Timeout al conectar con OpenAI API")
        return "Lo siento, el servicio está tardando más de lo esperado. Por favor, intenta de nuevo."
    except Exception as e:
        app.logger.error(f"🔴 Error en procesar_mensaje: {str(e)}")
        return "Lo siento, hubo un error al procesar tu mensaje."  

def obtener_audio_whatsapp(audio_id, config=None):
    """Descarga el audio de WhatsApp y lo convierte a formato compatible con OpenAI"""
    try:
        # 1. Obtener la URL del audio con autenticación
        url = f"https://graph.facebook.com/v23.0/{audio_id}"
        headers = {
            'Authorization': f'Bearer {config["whatsapp_token"]}',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        app.logger.info(f"🎵 Descargando audio WhatsApp: {url}")
        
        response = requests.get(url, headers=headers, timeout=30)
        app.logger.info(f"🎵 Status descarga audio: {response.status_code}")
        
        if response.status_code != 200:
            app.logger.error(f"🔴 Error descargando audio: {response.status_code} - {response.text}")
            return None, None
        
        # 2. Obtener la URL de descarga real
        audio_data = response.json()
        download_url = audio_data.get('url')
        
        if not download_url:
            app.logger.error(f"🔴 No se encontró URL de descarga de audio: {audio_data}")
            return None, None
            
        app.logger.info(f"🎵 URL de descarga audio: {download_url}")
        
        # 3. Descargar el audio con autenticación
        audio_response = requests.get(download_url, headers=headers, timeout=30)
        
        if audio_response.status_code != 200:
            app.logger.error(f"🔴 Error descargando audio: {audio_response.status_code}")
            return None, None
        
        # 4. Guardar audio en sistema de archivos
        import uuid
        import os
        
        # Crear directorio si no existe
        os.makedirs('static/audio/whatsapp', exist_ok=True)
        
        # Generar nombre único para el archivo
        filename = f"{uuid.uuid4().hex}.ogg"  # WhatsApp usa formato OGG
        filepath = f"static/audio/whatsapp/{filename}"
        
        # Guardar audio
        with open(filepath, 'wb') as f:
            f.write(audio_response.content)
        
        app.logger.info(f"✅ Audio guardado: {filepath}")
        
        return filepath, f"/{filepath}"
        
    except Exception as e:
        app.logger.error(f"🔴 Error en obtener_audio_whatsapp: {e}")
        return None, None

def transcribir_audio_con_openai(audio_file_path):
    """Transcribe audio usando Whisper de OpenAI"""
    try:
        # Verificar que el archivo existe
        if not os.path.exists(audio_file_path):
            app.logger.error(f"🔴 Archivo de audio no encontrado: {audio_file_path}")
            return None
        
        # OpenAI Whisper endpoint
        whisper_url = "https://api.openai.com/v1/audio/transcriptions"
        
        headers = {
            "Authorization": f"Bearer {OPENAI_API_KEY}",
        }
        
        # Preparar el archivo para enviar
        with open(audio_file_path, 'rb') as audio_file:
            files = {
                'file': (os.path.basename(audio_file_path), audio_file, 'audio/ogg')
            }
            data = {
                'model': 'whisper-1',
                'language': 'es'  # Opcional: especificar idioma
            }
            
            app.logger.info(f"🎵 Enviando audio a Whisper: {audio_file_path}")
            response = requests.post(whisper_url, headers=headers, files=files, data=data, timeout=60)
            
            app.logger.info(f"🎵 Respuesta Whisper Status: {response.status_code}")
            app.logger.info(f"🎵 Respuesta Whisper Text: {response.text}")
            
            response.raise_for_status()
            
            data = response.json()
            return data.get('text', '').strip()
            
    except Exception as e:
        app.logger.error(f"🔴 Error transcribiendo audio: {e}")
        return None

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
def enviar_mensaje(numero, texto, config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    
    app.logger.info(f"📤 Enviando mensaje usando configuración: {config['dominio']}")
    app.logger.info(f"📤 Phone Number ID: {config['phone_number_id']}")
    app.logger.info(f"📤 Token: {config['whatsapp_token'][:10]}...")
    
    url = f"https://graph.facebook.com/v23.0/{config['phone_number_id']}/messages"
    headers = {
        'Authorization': f'Bearer {config["whatsapp_token"]}',  # 🔥 Corregido: comillas dobles
        'Content-Type': 'application/json'
    }
    payload = {
        'messaging_product': 'whatsapp',
        'to': numero,
        'type': 'text',
        'text': {'body': texto}
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        app.logger.info(f"⬅️ [WA SEND] STATUS: {r.status_code}")
        app.logger.info(f"⬅️ [WA SEND] RESPONSE: {r.text}")
        return r.status_code == 200
    except Exception as e:
        app.logger.error(f"🔴 [WA SEND] EXCEPTION: {e}")
        return False
    
def guardar_conversacion(numero, mensaje, respuesta, es_imagen=False, contenido_extra=None, es_audio=False, config=None):
    # 🔥 VALIDACIÓN: Prevenir NULL antes de guardar
    if mensaje is None:
        mensaje = '[Mensaje vacío]'
    elif isinstance(mensaje, str) and mensaje.strip() == '':
        mensaje = '[Mensaje vacío]'
    
    if respuesta is None:
        respuesta = '[Respuesta vacía]'  
    elif isinstance(respuesta, str) and respuesta.strip() == '':
        respuesta = '[Respuesta vacía]'
    
    # Determinar tipo de mensaje
    if es_imagen:
        tipo_mensaje = 'imagen'
    elif es_audio:
        tipo_mensaje = 'audio'
    else:
        tipo_mensaje = 'texto'
    if config is None:
        config = obtener_configuracion_por_host()

    conn = get_db_connection(config)
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversaciones (
            id INT AUTO_INCREMENT PRIMARY KEY,
            numero VARCHAR(20),
            mensaje TEXT,
            respuesta TEXT,
            timestamp DATETIME,
            tipo_mensaje VARCHAR(10) DEFAULT 'texto',
            contenido_extra TEXT,
            transcripcion_audio TEXT  -- 🆕 NUEVO CAMPO para guardar transcripción
        ) ENGINE=InnoDB;
    ''')

    # 🆕 Guardar transcripción si es audio
    transcripcion = mensaje if es_audio and mensaje.startswith('Transcripción del audio:') else None

    timestamp_utc = datetime.utcnow()

    cursor.execute(
        "INSERT INTO conversaciones (numero, mensaje, respuesta, timestamp, tipo_mensaje, contenido_extra, transcripcion_audio) VALUES (%s, %s, %s, %s, %s, %s, %s);",
        (numero, mensaje, respuesta, timestamp_utc, tipo_mensaje, contenido_extra, transcripcion)
    )

    conn.commit()
    cursor.close()
    conn.close()

# ——— Detección y alerta ———
def detectar_intervencion_humana_ia(mensaje_usuario, numero, config=None):
    """
    Usa DeepSeek para detectar si el usuario quiere hablar con un humano
    Devuelve True si la IA detecta que se solicita intervención humana
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    # ⚠️ EVITAR DETECTAR ALERTAS DEL MISMO SISTEMA
    alertas_sistema = [
        "🚨 ALERTA:", "📋 INFORMACIÓN COMPLETA", "👤 Cliente:", 
        "📞 Número:", "💬 Mensaje clave:"
    ]
    
    for alerta in alertas_sistema:
        if alerta in mensaje_usuario:
            return False
    
    # ⚠️ EVITAR TU NÚMERO PERSONAL Y EL NÚMERO DE ALERTA
    if numero == ALERT_NUMBER or numero in ['5214491182201', '524491182201']:
        return False
    
    # Primero verificar con la lista de palabras clave existente (más rápida)
    if detectar_intervencion_humana_keywords(mensaje_usuario):
        return True
    # Si no se detectó con keywords, usar IA para análisis semántico
    try:
        prompt = f"""
        Evalúa si el siguiente mensaje indica que el usuario quiere hablar con una persona humana en lugar de un chatbot. 
        Responde SOLO con "SI" o "NO".
        
        Mensaje: "{mensaje_usuario}"
        
        Considera que podría ser una solicitud de intervención humana si:
        - Pide explícitamente hablar con una persona, humano, asesor, agente, etc.
        - Expresa frustración con respuestas automatizadas
        - Dice que no está obteniendo la ayuda que necesita
        - Solicita contacto telefónico, número de atención, etc.
        - Menciona que tiene un problema complejo o urgente
        - Pide cotización, presupuesto o información comercial específica
        - Quiere hacer una compra, pedido o transacción
        - Necesita aclarar dudas técnicas complejas
        
        Responde "SI" solo si hay una clara intención de hablar con humano.
        """
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,  # Baja temperatura para respuestas más determinísticas
            "max_tokens": 10
        }
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        
        data = response.json()
        respuesta_ia = data['choices'][0]['message']['content'].strip().upper()
        
        app.logger.info(f"🔍 IA detectó intervención humana: {respuesta_ia} para mensaje: {mensaje_usuario[:50]}...")
        
        return "SI" in respuesta_ia
        
    except Exception as e:
        app.logger.error(f"Error en detección IA de intervención humana: {e}")
        # Fallback a detección por keywords si la IA falla
        return detectar_intervencion_humana_keywords(mensaje_usuario)
    
def detectar_solicitud_cita_ia(mensaje, numero, config=None):
    """
    Usa DeepSeek para detectar si el mensaje es una solicitud de cita/pedido
    Devuelve True si la IA detecta intención de agendar cita/hacer pedido
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    # Determinar el tipo de negocio basado en la configuración
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    
    # Primero verificar con la lista de palabras clave existente (más rápida)
    if detectar_solicitud_cita_keywords(mensaje):
        return True
    
    # Si no se detectó con keywords, usar IA para análisis semántico
    try:
        if es_porfirianna:
            prompt = f"""
            Evalúa si el siguiente mensaje indica que el usuario quiere hacer un pedido de comida.
            Responde SOLO con "SI" o "NO".
            
            Mensaje: "{mensaje}"
            
            Considera que podría ser una solicitud de pedido si:
            - Pide ordenar, pedir, encargar comida
            - Solicita menú, platillos, comidas disponibles
            - Quiere hacer un pedido para llevar o a domicilio
            - Pregunta por precios de platillos
            - Menciona nombres de platillos específicos (gorditas, tacos, etc.)
            - Solicita información sobre horarios de servicio o entrega
            
            Responde "SI" solo si hay una clara intención de hacer un pedido.
            """
        else:
            prompt = f"""
            Evalúa si el siguiente mensaje indica que el usuario quiere agendar una cita o solicitar un servicio.
            Responde SOLO con "SI" o "NO".
            
            Mensaje: "{mensaje}"
            
            Considera que podría ser una solicitud de cita si:
            - Pide agendar, reservar, programar una cita, consulta, sesión o servicio
            - Solicita horarios, disponibilidad, turnos
            - Quiere cotización, presupuesto o información comercial
            - Pregunta por servicios disponibles (páginas web, apps, marketing, etc.)
            - Menciona necesidad de atención, evaluación, asesoría
            - Solicita información para contratar un servicio
            
            Responde "SI" solo si hay una clara intención de agendar cita.
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
        
        app.logger.info(f"🔍 IA detectó solicitud de {'pedido' if es_porfirianna else 'cita'}: {respuesta_ia} para mensaje: {mensaje[:50]}...")
        
        return "SI" in respuesta_ia
        
    except Exception as e:
        app.logger.error(f"Error en detección IA de {'pedido' if es_porfirianna else 'cita'}: {e}")
        # Fallback a detección por keywords si la IA falla
        return detectar_solicitud_cita_keywords(mensaje)
        
def resumen_rafa(numero,config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT mensaje, respuesta FROM conversaciones WHERE numero=%s ORDER BY timestamp DESC LIMIT 10;",
        (numero,)
    )
    historial = cursor.fetchall()
    cursor.close()
    conn.close()
    
    # Resumen más completo y estructurado
    resumen = "🚨 *ALERTA: Intervención Humana Requerida*\n\n"
    resumen += f"📞 *Cliente:* {numero}\n"
    resumen += f"🕒 *Hora:* {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
    resumen += "📋 *Últimas interacciones:*\n"
    
    for i, msg in enumerate(historial[:5]):  # Solo últimos 5 mensajes
        resumen += f"\n{i+1}. 👤 *Usuario:* {msg['mensaje'][:100]}"
        if msg['respuesta']:
            resumen += f"\n   🤖 *IA:* {msg['respuesta'][:100]}"
    
    return resumen
    
def enviar_alerta_humana(numero_cliente, mensaje_clave, resumen, config=None):
    if config is None:
        config = obtener_configuracion_por_host()

    contexto_consulta = obtener_contexto_consulta(numero_cliente, config)
    
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

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        payload = request.get_json()
        app.logger.info(f"📥 Payload recibido: {json.dumps(payload, indent=2)}")
        
        entry = payload['entry'][0]
        change = entry['changes'][0]['value']
        mensajes = change.get('messages')
        
        if not mensajes:
            return 'OK', 200
            
        msg = mensajes[0]
        numero = msg['from']

        # 🔥 CORRECCIÓN: Obtener el phone_number_id que RECIBIÓ el mensaje
        phone_number_id = change.get('metadata', {}).get('phone_number_id')
        
                # 🔥 OBTENER CONFIGURACIÓN CORRECTA BASADA EN EL NÚMERO QUE RECIBIÓ EL MENSAJE
        # 🔥 CORRECCIÓN: Obtener la configuración correcta
        config = obtener_configuracion_por_phone_number_id(phone_number_id)
        app.logger.info(f"🔧 Usando configuración para: {config.get('dominio', 'desconocido')}")
        app.logger.info(f"🔍 Mapeando phone_number_id: {phone_number_id}")

        # 🔥 CORRECCIÓN: Buscar y asignar la configuración correcta
        for numero_config, config_data in NUMEROS_CONFIG.items():
            app.logger.info(f"   ➡️ {numero_config}: {config_data['phone_number_id']}")
            if config_data['phone_number_id'] == phone_number_id:
                config = config_data
                app.logger.info(f"✅ Configuración encontrada: {config['dominio']}")
                break  # Salir del bucle una vez encontrado
                
        if not config:
            # Fallback si no encuentra la configuración
            app.logger.warning(f"⚠️ No se encontró configuración para phone_number_id: {phone_number_id}")
            config = obtener_configuracion_por_host()  # Fallback al host actual
            app.logger.info(f"🔄 Usando configuración de fallback: {config['dominio']}")
            app.logger.info(f"🔧 Usando configuración para: {config.get('dominio', 'desconocido')}")
                # Detectar tipo de mensaje
        es_imagen = False
        es_audio = False
        imagen_base64 = None
        imagen_url = None
        audio_path = None
        audio_url = None
        texto = ""
        transcripcion_audio = None
        
        # En el webhook, después de obtener la imagen:
        if 'image' in msg:
            app.logger.info(f"🖼️ Mensaje de imagen detectado")
            es_imagen = True
            image_id = msg['image']['id']
            app.logger.info(f"🖼️ ID de imagen: {image_id}")
            
            # Obtener la imagen
            imagen_base64, imagen_url = obtener_imagen_whatsapp(image_id, config)
            
            # Usar caption si existe, sino texto por defecto
            if 'caption' in msg['image']:
                texto = msg['image']['caption']
            else:
                texto = "Analiza esta imagen y describe lo que ves"
        elif 'audio' in msg:
            app.logger.info(f"🎵 Mensaje de audio detectado")
            es_audio = True
            audio_id = msg['audio']['id']
            app.logger.info(f"🎵 ID de audio: {audio_id}")
            
            # Obtener y transcribir audio
            audio_path, audio_url = obtener_audio_whatsapp(audio_id, config)
            
            if audio_path:
                transcripcion_audio = transcribir_audio_con_openai(audio_path)
                if transcripcion_audio:
                    texto = transcripcion_audio
                    app.logger.info(f"🎵 Transcripción: {transcripcion_audio}")
                else:
                    texto = "No pude transcribir el audio"
            else:
                texto = "No pude procesar el audio"
                
        elif 'text' in msg:
            app.logger.info(f"📝 Mensaje de texto detectado")
            texto = msg['text']['body']
            app.logger.info(f"📝 Texto: {texto}")
            
        else:
            tipo_mensaje = list(msg.keys())[1] if len(msg.keys()) > 1 else "desconocido"
            texto = f"Recibí un mensaje {tipo_mensaje}. Por favor, envía texto, audio o imagen."
            app.logger.info(f"📦 Mensaje de tipo: {tipo_mensaje}")

        # 🛑 EVITAR PROCESAR EL MISMO MENSAJE MÚLTIPLES VECES
        # 🛑 EVITAR PROCESAR EL MISMO MENSAJE MÚLTIPLES VECES
        if 'id' in msg:
            current_message_id = f"{numero}_{msg['id']}"
        else:
            # For messages without ID, use timestamp + text to avoid false duplicates
            timestamp = msg.get('timestamp', '')
            current_message_id = f"{numero}_{timestamp}_{texto}_{'image' if es_imagen else 'text'}"
        if not hasattr(app, 'ultimos_mensajes'):
            app.ultimos_mensajes = set()
        
        if current_message_id in app.ultimos_mensajes:
            app.logger.info(f"⚠️ Mensaje duplicado ignorado: {current_message_id}")
            return 'OK', 200
        
        app.ultimos_mensajes.add(current_message_id)
        
        if len(app.ultimos_mensajes) > 100:
            app.ultimos_mensajes = set(list(app.ultimos_mensajes)[-100:])
        
        # ⛔ BLOQUEAR MENSAJES DEL SISTEMA DE ALERTAS
        if numero == ALERT_NUMBER and any(tag in texto for tag in ['🚨 ALERTA:', '📋 INFORMACIÓN COMPLETA']):
            app.logger.info(f"⚠️ Mensaje del sistema de alertas, ignorando: {numero}")
            return 'OK', 200
        
        # 🔄 PARA MI NÚMERO PERSONAL: Permitir todo pero sin alertas
        es_mi_numero = numero in ['5214491182201', '524491182201']
        
        if es_mi_numero:
            app.logger.info(f"🔵 Mensaje de mi número personal, procesando SIN alertas: {numero}")
        
        # ========== PROCESAMIENTO NORMAL ==========
        # Actualizar contacto
        contactos = change.get('contacts')
        if contactos and len(contactos) > 0:
            profile_name = contactos[0].get('profile', {}).get('name')
            wa_id = contactos[0].get('wa_id')
            if profile_name and wa_id:
                try:
                    imagen_perfil = obtener_imagen_perfil_whatsapp(wa_id)
                    
                    conn = get_db_connection(config)
                    cursor = conn.cursor()
                    
                    # Eliminar duplicados
                    cursor.execute("""
                        DELETE FROM contactos 
                        WHERE numero_telefono = %s 
                        AND id NOT IN (
                            SELECT MAX(id) FROM (
                                SELECT id FROM contactos WHERE numero_telefono = %s
                            ) AS temp
                        )
                    """, (wa_id, wa_id))
                    
                    # Insertar o actualizar
                    cursor.execute("""
                        INSERT INTO contactos (numero_telefono, nombre, plataforma, imagen_url)
                        VALUES (%s, %s, 'whatsapp', %s)
                        ON DUPLICATE KEY UPDATE 
                            nombre = VALUES(nombre),
                            imagen_url = VALUES(imagen_url)
                    """, (wa_id, profile_name, imagen_perfil))
                    
                    conn.commit()
                    cursor.close()
                    conn.close()
                    app.logger.info(f"✅ Contacto actualizado: {wa_id}")
                    
                except Exception as e:
                    app.logger.error(f"🔴 Error actualizando contacto {wa_id}: {e}")
        
        # Asegurar que el contacto exista
        try:
            conn = get_db_connection(config)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT IGNORE INTO contactos (numero_telefono, plataforma)
                VALUES (%s, 'whatsapp')
            """, (numero,))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            app.logger.error(f"🔴 Error asegurando contacto {numero}: {e}")
        
        # Consultas de precio
        if texto.lower().startswith('precio de '):
            servicio = texto[10:].strip()
            info = obtener_precio(servicio, config)
            if info:
                precio, moneda = info
                respuesta = f"El precio de *{servicio}* es {precio} {moneda}."
            else:
                respuesta = f"No encontré tarifa para *{servicio}*."
            enviar_mensaje(numero, respuesta, config)
            guardar_conversacion(numero, texto, respuesta, es_imagen, imagen_url if 'imagen_url' in locals() else None, config=config)
            enviar_confirmacion_cita(numero, None, None)  # Enviar confirmación genérica
            return 'OK', 200
        
        # 🆕 DETECCIÓN DE CITAS
            # 🆕 DETECCIÓN DE CITAS MEJORADA
        if detectar_solicitud_cita_ia(texto, numero, config):
            app.logger.info(f"📅 Solicitud de {soli} detectada de {numero}")
            
            # Obtener historial para contexto
            historial = obtener_historial(numero, limite=5, config=config)
            
            # Extraer información con contexto
            info_cita = extraer_info_cita_mejorado(texto, numero, historial, config)
            
            if info_cita:
                # Validar si los datos están completos
                es_valida, mensaje_error = validar_datos_cita_completos(info_cita, config)
                
                if es_valida:
                    # Datos completos, guardar cita
                    cita_id = guardar_cita(info_cita, config)
                    
                    if cita_id:
                        enviar_confirmacion_cita(numero, info_cita, cita_id, config)
                        enviar_alerta_cita_administrador(info_cita, cita_id, config)
                        app.logger.info(f"✅ {soli.capitalize()} agendada - ID: {cita_id}")
                        guardar_conversacion(numero, texto, f"{soli.capitalize()} agendada - ID: #{cita_id}", config=config)
                        return 'OK', 200
                    else:
                        app.logger.error(f"❌ Error guardando {soli} en BD")
                        enviar_mensaje(numero, f"Lo siento, hubo un error al guardar tu {soli}. Por favor intenta nuevamente.", config)
                else:
                    # Datos incompletos, solicitar información faltante
                    app.logger.info(f"⚠️ {soli.capitalize()} con datos incompletos, solicitando información")
                    solicitar_datos_faltantes_cita(numero, info_cita, config)
                    
                    # Guardar conversación indicando que está en proceso de agendar
                    guardar_conversacion(numero, texto, f"Procesando {soli} - solicitando datos faltantes", config=config)
                    return 'OK', 200
            else:
                app.logger.error(f"❌ Error extrayendo información de {soli}")
                enviar_mensaje(numero, f"No pude entender la información de tu {soli}. ¿Podrías proporcionar más detalles?", config)
            
            app.logger.warning(f"⚠️ Falló detección de {soli}, continuando con IA normal")
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
            respuesta = responder_con_ia(texto, numero, es_imagen, imagen_base64, es_audio, transcripcion_audio, config)
            
            # 🆕 ENVÍO DE RESPUESTA (VOZ O TEXTO)
            if responder_con_voz:
                # Intentar enviar respuesta de voz
                audio_filename = f"respuesta_{numero}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                audio_url_local = texto_a_voz(respuesta, audio_filename)
                
                if audio_url_local:
                    # URL pública del audio (ajusta según tu configuración)
                    audio_url_publica = f"https://mektia.com{audio_url_local}"
                    
                    if enviar_mensaje_voz(numero, audio_url_publica):
                        app.logger.info(f"✅ Respuesta de voz enviada a {numero}")
                        guardar_conversacion(numero, texto, respuesta, es_imagen, audio_url_local, es_audio=True, config=config)
                    else:
                        # Fallback a texto
                        enviar_mensaje(numero, respuesta, config)
                        app.logger.info(f"✅ Fallback a texto enviado a {numero}")
                        guardar_conversacion(numero, texto, respuesta, es_imagen, audio_url_local, config=config)
                else:
                    # Fallback a texto
                    enviar_mensaje(numero, respuesta, config)
                    app.logger.info(f"✅ Fallback a texto (error TTS) enviado a {numero}")
                    guardar_conversacion(numero, texto, respuesta, es_imagen, None, config=config)
            else:
                # Respuesta normal de texto
                enviar_mensaje(numero, respuesta, config)
                app.logger.info(f"✅ Respuesta de texto enviada a {numero}")
                
                if es_audio:
                    guardar_conversacion(numero, f"[Audio] {texto}", respuesta, False, audio_url, es_audio=True, config=config)
                else:
                    guardar_conversacion(numero, texto, respuesta, es_imagen, imagen_url, config=config)
            
            # 🔄 DETECCIÓN DE INTERVENCIÓN HUMANA
            app.logger.info(f"🔍 Verificando intervención humana para {numero}")
            app.logger.info(f"📝 Mensaje: {texto[:100]}...")
            app.logger.info(f"🤖 Respuesta: {respuesta[:100]}...")
            detectado = detectar_intervencion_humana_ia(texto,numero)
            app.logger.info(f"🎯 Detección resultado: {detectado}")

            if detectado and numero != ALERT_NUMBER:
                app.logger.info(f"🚨 Intervención humana detectada para {numero}")
                resumen = resumen_rafa(numero, config)
                enviar_alerta_humana(numero, texto, resumen, config)
                enviar_informacion_completa(numero, config)
        
        # KANBAN AUTOMÁTICO
        meta = obtener_chat_meta(numero, config)
        if not meta:
            inicializar_chat_meta(numero, config)
        
        nueva_columna = evaluar_movimiento_automatico(numero, texto, respuesta)
        actualizar_columna_chat(numero, nueva_columna, config)
        
        return 'OK', 200

    except Exception as e:
        app.logger.error(f"🔴 Error en webhook: {e}")
        app.logger.error(f"🔴 Traceback: {traceback.format_exc()}")
        return 'Error interno', 500
    
def detectar_solicitud_cita_keywords(mensaje):
    """
    Detección rápida por palabras clave de solicitud de cita/pedido
    """
    mensaje_lower = mensaje.lower()
    
    # Palabras clave para detección de citas/pedidos
    palabras_clave = [
        'cita', 'agendar', 'reservar', 'programar', 'consulta', 'sesión',
        'servicio', 'cotización', 'presupuesto', 'contratar', 'asesoría',
        'evaluación', 'horario', 'disponibilidad', 'turno', 'ordenar',
        'pedido', 'encargar', 'comprar', 'menú', 'precio', 'qué tienes',
        'qué ofrecen', 'quiero', 'necesito', 'me interesa'
    ]
    
    # Verificar si alguna palabra clave está en el mensaje
    for palabra in palabras_clave:
        if palabra in mensaje_lower:
            return True
    
    return False

# ——— UI ———
@app.route('/')
def inicio():
    config = obtener_configuracion_por_host()
    return redirect(url_for('home', config=config))

def obtener_imagen_perfil_whatsapp(numero, config=None):
    """Obtiene la URL de la imagen de perfil de WhatsApp"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    try:
        # Formatear el número correctamente
        numero_formateado = numero.replace('+', '').replace(' ', '')
        
        # Usar el endpoint correcto de WhatsApp Business API
        url = f"https://graph.facebook.com/v18.0/{MI_NUMERO_BOT}"
        
        params = {
            'fields': 'profile_picture',
            'access_token': 'whatsapp_token'
        }
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {'whatsapp_token'}'
        }
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'profile_picture' in data and 'url' in data['profile_picture']:
                imagen_url = data['profile_picture']['url']
                app.logger.info(f"✅ Imagen obtenida: {imagen_url}")
                return imagen_url
            else:
                app.logger.warning(f"⚠️ No se encontró profile_picture en la respuesta: {data}")
        
        # Fallback al método alternativo
        return obtener_imagen_perfil_alternativo(numero_formateado)
        
    except Exception as e:
        app.logger.error(f"🔴 Error obteniendo imagen de perfil: {e}")
        return None 
    
def obtener_configuracion_por_host():
    """Obtiene la configuración basada en el host de la solicitud"""
    try:
        host = request.headers.get('Host', '')
        app.logger.info(f"🌐 Host detectado: {host}")
        
        if 'laporfirianna' in host:
            app.logger.info("🔧 Usando configuración de La Porfirianna")
            return NUMEROS_CONFIG['524812372326']
        else:
            app.logger.info("🔧 Usando configuración de Mektia (por defecto)")
            return NUMEROS_CONFIG['524495486142']
            
    except RuntimeError:
        # ⚠️ Fuera de contexto de request - usar configuración por defecto
        app.logger.warning("⚠️ Fuera de contexto de request, usando Mektia por defecto")
        return NUMEROS_CONFIG['524495486142']

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
def ver_chat(numero, config=None):
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    # CONSULTA ACTUALIZADA - USAR PRIORIDAD
    cursor.execute("""
        SELECT DISTINCT
            conv.numero, 
            cont.imagen_url, 
            -- PRIORIDAD: alias > nombre > número
            COALESCE(cont.alias, cont.nombre, conv.numero) AS nombre_mostrado,
            cont.alias,
            cont.nombre
        FROM conversaciones conv
        LEFT JOIN contactos cont ON conv.numero = cont.numero_telefono
        WHERE conv.numero = %s
        LIMIT 1;
    """, (numero,))
    chats = cursor.fetchall()

    # Esta consulta queda igual (para los mensajes) pero usando CONVERSACIONES
    cursor.execute(
        "SELECT * FROM conversaciones WHERE numero=%s ORDER BY timestamp ASC;",
        (numero,)
    )
    msgs = cursor.fetchall()

    # Convertir timestamps a hora de México
    for msg in msgs:
        if msg.get('timestamp'):
            # Si el timestamp ya tiene timezone info, convertirlo
            if msg['timestamp'].tzinfo is not None:
                msg['timestamp'] = msg['timestamp'].astimezone(tz_mx)
            else:
                # Si no tiene timezone, asumir que es UTC y luego convertir
                msg['timestamp'] = pytz.utc.localize(msg['timestamp']).astimezone(tz_mx)

    cursor.close()
    conn.close()
    
    return render_template('chats.html',
        chats=chats, 
        mensajes=msgs,
        selected=numero, 
        IA_ESTADOS=IA_ESTADOS,
        tenant_config=config  # ← 🔥 AÑADE ESTA LÍNEA
    )        

@app.before_request
def log_configuracion():
    if request.endpoint and request.endpoint != 'static':
        host = request.headers.get('Host', '')
        config = obtener_configuracion_por_host()
        app.logger.info(f"🌐 [{request.endpoint}] Host: {host} | BD: {config['db_name']}")

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

@app.route('/kanban')
def ver_kanban(config=None):
    config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)

    # 1) Cargamos las columnas Kanban
    cursor.execute("SELECT * FROM kanban_columnas ORDER BY orden;")
    columnas = cursor.fetchall()

    # 2) CONSULTA DEFINITIVA - compatible con only_full_group_by
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
            -- PRIORIDAD: alias > nombre > número
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
        enviar_alerta_humana("Prueba", "524491182201", "Mensaje clave", "Resumen de prueba.")
        return "🚀 Test alerta disparada."

    # ——— Funciones para Kanban ———

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
        # Asignar automáticamente a la columna "Nuevos" (id=1)
        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO chat_meta (numero, columna_id) 
            VALUES (%s, 1)
            ON DUPLICATE KEY UPDATE columna_id = VALUES(columna_id);
        """, (numero,))
        conn.commit()
        cursor.close()
        conn.close()

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

def evaluar_movimiento_automatico(numero, mensaje, respuesta, config=None):
        if config is None:
            config = obtener_configuracion_por_host()
    
        historial = obtener_historial(numero, limite=5, config=config)
        
        # Si es primer mensaje, mantener en "Nuevos"
        if len(historial) <= 1:
            return 1  # Nuevos
        
        # Si hay intervención humana, mover a "Esperando Respuesta"
        if detectar_intervencion_humana(mensaje, respuesta, numero):
            return 3  # Esperando Respuesta
        
        # Si tiene más de 2 mensajes, mover a "En Conversación"
        if len(historial) >= 2:
            return 2  # En Conversación
        
        # Si no cumple nada, mantener donde está
        meta = obtener_chat_meta(numero)
        return meta['columna_id'] if meta else 1

@app.route('/test-imagen-personalizada', methods=['GET', 'POST'])

@app.route('/test-imagen')
def test_imagen():
    """Ruta para probar el procesamiento de imágenes con una URL pública"""
    try:
        # Usar una imagen pública de prueba
        url_imagen_prueba = "https://upload.wikimedia.org/wikipedia/commons/thumb/6/6d/Good_Food_Display_-_NCI_Visuals_Online.jpg/800px-Good_Food_Display_-_NCI_Visuals_Online.jpg"
        texto_prueba = "¿Qué alimentos ves en esta imagen?"
        
        respuesta = responder_con_ia(texto_prueba, "524491182201", True, url_imagen_prueba)
        return jsonify({
            "respuesta": respuesta, 
            "status": "success",
            "modelo_utilizado": "gpt-4o"  # ✅ Actualizado
        })
        
    except Exception as e:
        return jsonify({
            "error": str(e), 
            "status": "error"
        })

def obtener_contexto_consulta(numero, config=None):
    """Obtiene el contexto de la consulta o proyecto del cliente"""
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
            mensaje_texto = msg['mensaje'].lower() if msg['mensaje'] else ""
            
            for servicio in servicios_clave:
                if servicio in mensaje_texto and servicio not in servicios_mencionados:
                    servicios_mencionados.append(servicio)
        
        if servicios_mencionados:
            contexto += f"📋 *Servicios mencionados:* {', '.join(servicios_mencionados)}\n"
        
        # Extraer información específica del último mensaje
        ultimo_mensaje = mensajes[0]['mensaje'] or ""
        if len(ultimo_mensaje) > 10:  # Solo si tiene contenido
            contexto += f"💬 *Último mensaje:* {ultimo_mensaje[:150]}{'...' if len(ultimo_mensaje) > 150 else ''}\n"
        
        # Intentar detectar urgencia o tipo de consulta
        palabras_urgentes = ['urgente', 'rápido', 'inmediato', 'pronto', 'ya']
        if any(palabra in ultimo_mensaje.lower() for palabra in palabras_urgentes):
            contexto += "🚨 *Tono:* Urgente\n"
        return contexto if contexto else "No se detectó contexto relevante."
        
    except Exception as e:
        app.logger.error(f"Error obteniendo contexto: {e}")
        return "Error al obtener contexto"

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5000, help='Puerto para ejecutar la aplicación')
    args = parser.parse_args()
    
    # Crear tablas necesarias
    crear_tabla_citas()
    
    app.run(host='0.0.0.0', port=args.port, debug=False)