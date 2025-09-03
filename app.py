from datetime import datetime
import pytz
import os
import logging
import requests
import json 
import base64
import mysql.connector
from flask import Flask, request, render_template, redirect, url_for, abort, flash, jsonify
import requests
from dotenv import load_dotenv
from datetime import datetime, timedelta
from decimal import Decimal

tz_mx = pytz.timezone('America/Mexico_City')

load_dotenv()  # Cargar desde archivo específico
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cualquier-cosa")
app.logger.setLevel(logging.INFO)

# ——— Env vars ———
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")  # Nueva variable
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
MI_NUMERO_BOT = os.getenv("MI_NUMERO_BOT")
ALERT_NUMBER = os.getenv("ALERT_NUMBER", "524491182201")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"  # Nueva URL
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"  # URL de DeepSeek
IA_ESTADOS = {}

# Diccionario de prefijos a código de país
PREFIJOS_PAIS = {
    '52': 'mx', '1': 'us', '54': 'ar', '57': 'co', '55': 'br',
    '34': 'es', '51': 'pe', '56': 'cl', '58': 've', '593': 'ec',
    '591': 'bo', '507': 'pa', '502': 'gt'
}

app.jinja_env.filters['bandera'] = lambda numero: get_country_flag(numero)

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

def get_db_connection():
    return mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )

# ——— Configuración en MySQL ———
def load_config():
    conn = get_db_connection()
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

def save_config(cfg_all):
    neg = cfg_all.get('negocio', {})
    per = cfg_all.get('personalizacion', {})

    conn = get_db_connection()
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
def obtener_todos_los_precios():
    conn = get_db_connection()
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

def obtener_precio_por_id(pid):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM precios WHERE id=%s;", (pid,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row

def obtener_precio(servicio_nombre: str):
    conn = get_db_connection()
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
def obtener_historial(numero, limite=10):
    conn = get_db_connection()
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
def responder_con_ia(mensaje_usuario, numero, es_imagen=False, imagen_base64=None):
    cfg = load_config()
    neg = cfg['negocio']
    ia_nombre = neg.get('ia_nombre', 'Asistente')
    negocio_nombre = neg.get('negocio_nombre', '')
    descripcion = neg.get('descripcion', '')
    que_hace = neg.get('que_hace', '')

    precios = obtener_todos_los_precios()
    lista_precios = "\n".join(
        f"- {p['servicio']}: {p['precio']} {p['moneda']}"
        for p in precios
    )

    system_prompt = f"""
Eres **{ia_nombre}**, asistente virtual de **{negocio_nombre}**.
Descripción del negocio:
{descripcion}

Tus responsabilidades:
{que_hace}

Servicios y tarifas actuales:
{lista_precios}

Mantén siempre un tono profesional y conciso.
""".strip()

    historial = obtener_historial(numero)
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
            # Para imágenes: usar base64 en lugar de URL
            messages_chain.append({
                'role': 'user',
                'content': [
                    {"type": "text", "text": mensaje_usuario},
                    {
                        "type": "image_url", 
                        "image_url": {
                            "url": imagen_base64,
                            "detail": "auto"  # "low", "high", o "auto"
                        }
                    }
                ]
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
                "messages": messages_chain,
                "temperature": 0.7,
                "max_tokens": 1000,
            }
            
            app.logger.info(f"🖼️ Enviando imagen a OpenAI con gpt-4o")
            app.logger.info(f"📦 Payload OpenAI: {json.dumps(payload, indent=2)}")
            
            response = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=60)
            app.logger.info(f"📨 Respuesta OpenAI Status: {response.status_code}")
            app.logger.info(f"📨 Respuesta OpenAI Text: {response.text}")
            
            response.raise_for_status()
            
            data = response.json()
            return data['choices'][0]['message']['content'].strip()
        
        else:
            # Usar DeepSeek para texto
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "model": "deepseek-chat",
                "messages": messages_chain,
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
    
def obtener_imagen_whatsapp(image_id):
    """Descarga la imagen de WhatsApp y la convierte a base64 y guarda el archivo"""
    try:
        # 1. Obtener la URL de la imagen con autenticación
        url = f"https://graph.facebook.com/v23.0/{image_id}"
        headers = {
            'Authorization': f'Bearer {WHATSAPP_TOKEN}',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        app.logger.info(f"📷 Descargando imagen WhatsApp: {url}")
        
        response = requests.get(url, headers=headers, timeout=30)
        app.logger.info(f"📷 Status descarga: {response.status_code}")
        
        if response.status_code != 200:
            app.logger.error(f"🔴 Error descargando imagen: {response.status_code} - {response.text}")
            return None, None
        
        # 2. Obtener la URL de descarga real
        image_data = response.json()
        download_url = image_data.get('url')
        
        if not download_url:
            app.logger.error(f"🔴 No se encontró URL de descarga: {image_data}")
            return None, None
            
        app.logger.info(f"📷 URL de descarga: {download_url}")
        
        # 3. Descargar la imagen con autenticación
        image_response = requests.get(download_url, headers=headers, timeout=30)
        
        if image_response.status_code != 200:
            app.logger.error(f"🔴 Error descargando imagen: {image_response.status_code}")
            return None, None
        
        # 4. Convertir a base64 para OpenAI
        image_base64 = base64.b64encode(image_response.content).decode('utf-8')
        
        # 5. Guardar imagen en sistema de archivos
        import uuid
        import os
        
        # Crear directorio si no existe
        os.makedirs('static/images/whatsapp', exist_ok=True)
        
        # Generar nombre único para el archivo
        filename = f"{uuid.uuid4().hex}.jpg"
        filepath = f"static/images/whatsapp/{filename}"
        
        # Guardar imagen
        with open(filepath, 'wb') as f:
            f.write(image_response.content)
        
        app.logger.info(f"✅ Imagen guardada: {filepath}")
        app.logger.info(f"✅ Imagen descargada correctamente. Tamaño: {len(image_base64)} bytes")
        
        return f"data:image/jpeg;base64,{image_base64}", f"/{filepath}"
        
    except Exception as e:
        app.logger.error(f"🔴 Error en obtener_imagen_whatsapp: {e}")
        return None, None
# ——— Envío WhatsApp y guardado de conversación ———
def enviar_mensaje(numero, texto):
    PHONE_NUMBER_ID = "638096866063629"  # Tu Phone Number ID de WhatsApp
    url = f"https://graph.facebook.com/v23.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        'Authorization': f'Bearer {WHATSAPP_TOKEN}',
        'Content-Type': 'application/json'
    }
    payload = {
        'messaging_product': 'whatsapp',
        'to': numero,
        'type': 'text',
        'text': {'body': texto}
    }

    app.logger.info("➡️ [WA SEND] URL: %s", url)
    app.logger.info("➡️ [WA SEND] HEADERS: %s", headers)
    app.logger.info("➡️ [WA SEND] PAYLOAD: %s", payload)
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        app.logger.info("⬅️ [WA SEND] STATUS: %s", r.status_code)
        app.logger.info("⬅️ [WA SEND] RESPONSE: %s", r.text)
    except Exception as e:
        app.logger.error("🔴 [WA SEND] EXCEPTION: %s", e)

def guardar_conversacion(numero, mensaje, respuesta, es_imagen=False, imagen_url=None):
    # 🔥 VALIDACIÓN: Prevenir NULL antes de guardar
    if mensaje is None:
        mensaje = '[Mensaje vacío]'
    elif isinstance(mensaje, str) and mensaje.strip() == '':
        mensaje = '[Mensaje vacío]'
    
    if respuesta is None:
        respuesta = '[Respuesta vacía]'  
    elif isinstance(respuesta, str) and respuesta.strip() == '':
        respuesta = '[Respuesta vacía]'
    
    # Si es imagen, guardar información adicional
    tipo_mensaje = 'imagen' if es_imagen else 'texto'
    contenido_extra = imagen_url if es_imagen else None
    
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversaciones (
            id INT AUTO_INCREMENT PRIMARY KEY,
            numero VARCHAR(20),
            mensaje TEXT,
            respuesta TEXT,
            timestamp DATETIME,
            tipo_mensaje VARCHAR(10) DEFAULT 'texto',
            contenido_extra TEXT
        ) ENGINE=InnoDB;
    ''')

    timestamp_utc = datetime.utcnow()

    cursor.execute(
        "INSERT INTO conversaciones (numero, mensaje, respuesta, timestamp, tipo_mensaje, contenido_extra) VALUES (%s, %s, %s, %s, %s, %s);",
        (numero, mensaje, respuesta, timestamp_utc, tipo_mensaje, contenido_extra)
    )

    conn.commit()
    cursor.close()
    conn.close()
# ——— Detección y alerta ———
def detectar_intervencion_humana(mensaje_usuario, respuesta_ia, numero):
    """Detección mejorada que previene loops"""
    
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
    
    # 📋 DETECCIÓN NORMAL (tu código actual)
    texto = mensaje_usuario.lower()
    if 'hablar con ' in texto or 'ponme con ' in texto:
        return True
        
    disparadores = [
        'hablar con persona', 'hablar con asesor', 'hablar con agente',
        'quiero asesor', 'atención humana', 'soporte técnico',
        'es urgente', 'necesito ayuda humana', 'presupuesto',
        'cotización', 'quiero comprar', 'me interesa'
    ]
    
    for frase in disparadores:
        if frase in texto:
            return True
            
    respuesta = respuesta_ia.lower()
    canalizaciones = [
        'te canalizaré', 'asesor te contactará', 'te paso con'
    ]
    
    for tag in canalizaciones:
        if tag in respuesta:
            return True
            
    return False

def resumen_rafa(numero):
    conn = get_db_connection()
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
    
def enviar_alerta_humana(numero_cliente, mensaje_clave, resumen):
    """Envía alerta de intervención humana usando mensaje normal (sin template)"""
    mensaje = f"🚨 *ALERTA: Intervención Humana Requerida*\n\n"
    mensaje += f"👤 *Cliente:* {numero_cliente}\n"
    mensaje += f"📞 *Número:* {numero_cliente}\n"
    mensaje += f"💬 *Mensaje clave:* {mensaje_clave[:100]}{'...' if len(mensaje_clave) > 100 else ''}\n\n"
    mensaje += f"📋 *Resumen:*\n{resumen[:800]}{'...' if len(resumen) > 800 else ''}\n\n"
    mensaje += f"⏰ *Hora:* {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
    mensaje += f"_________________________________________\n"
    mensaje += f"📊 Atiende desde el CRM o responde directamente por WhatsApp"
    
    # Enviar mensaje normal (sin template) a tu número personal
    enviar_mensaje(ALERT_NUMBER, mensaje)
    app.logger.info(f"📤 Alerta humana enviada para {numero_cliente}")
    
def enviar_informacion_completa(numero_cliente):
    """Envía toda la información del cliente a tu número personal"""
    try:
        # Obtener información del contacto
        conn = get_db_connection()
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
        
        # Enviar mensaje completo
        enviar_mensaje(ALERT_NUMBER, mensaje_completo)
        app.logger.info(f"📤 Información completa enviada para {numero_cliente}")
        
    except Exception as e:
        app.logger.error(f"🔴 Error enviando información completa: {e}")
        
        
# ——— Webhook ———
@app.route('/webhook', methods=['GET'])
def webhook_verification():
    if request.args.get('hub.verify_token') == VERIFY_TOKEN:
        return request.args.get('hub.challenge')
    return 'Token inválido', 403

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
        
        app.logger.info(f"📱 Mensaje recibido de: {numero}")
        app.logger.info(f"📦 Tipo de mensaje: {list(msg.keys())}")
        
        # Detectar si es imagen o texto
        es_imagen = False
        imagen_base64 = None
        imagen_url = None  # ← AÑADIR ESTA LÍNEA
        texto = ""
        
        if 'image' in msg:
            app.logger.info(f"🖼️ Mensaje de imagen detectado")
            es_imagen = True
            image_id = msg['image']['id']
            app.logger.info(f"🖼️ ID de imagen: {image_id}")
            
            # ✅ USAR LA NUEVA FUNCIÓN QUE CONVIERTE A BASE64 Y GUARDA ARCHIVO
            imagen_base64, imagen_url = obtener_imagen_whatsapp(image_id)  # ← Ahora recibe ambos valores
            
            if not imagen_base64:
                app.logger.error("🔴 No se pudo obtener la imagen, enviando mensaje de error")
                texto = "No pude procesar la imagen. Por favor, intenta con otra imagen o envía tu consulta como texto."
                enviar_mensaje(numero, texto)
                guardar_conversacion(numero, texto, "Error al procesar imagen", False, None)
                return 'OK', 200
            # Verificar si hay texto acompañando la imagen
            if 'caption' in msg['image']:
                texto = msg['image']['caption']
                app.logger.info(f"🖼️ Leyenda de imagen: {texto}")
            else:
                texto = "Analiza esta imagen"
                app.logger.info(f"🖼️ Sin leyenda, usando texto por defecto")
                
        elif 'text' in msg:
            app.logger.info(f"📝 Mensaje de texto detectado")
            texto = msg['text']['body']
            app.logger.info(f"📝 Texto: {texto}")
        else:
            # Otro tipo de mensaje (audio, video, etc.)
            tipo_mensaje = list(msg.keys())[1] if len(msg.keys()) > 1 else "desconocido"
            texto = f"Recibí un mensaje {tipo_mensaje}. Por favor, envía texto o imagen."
            app.logger.info(f"📦 Mensaje de tipo: {tipo_mensaje}")
        
# 🛑 EVITAR PROCESAR EL MISMO MENSAJE MÚLTIPLES VECES - VERSIÓN MEJORADA
        current_message_id = f"{numero}_{msg['id']}" if 'id' in msg else f"{numero}_{texto}_{'image' if es_imagen else 'text'}"

        if not hasattr(app, 'ultimos_mensajes'):
                app.ultimos_mensajes = set()

        if current_message_id in app.ultimos_mensajes:
                app.logger.info(f"⚠️ Mensaje duplicado ignorado: {current_message_id}")
                return 'OK', 200

        app.ultimos_mensajes.add(current_message_id)
            # Limitar el tamaño para no consumir mucha memoria
        if len(app.ultimos_mensajes) > 100:
                app.ultimos_mensajes = set(list(app.ultimos_mensajes)[-50:])

        # ⛔ BLOQUEAR COMPLETAMENTE MENSAJES DEL NÚMERO DE ALERTA (para evitar loops)
        if numero == ALERT_NUMBER and any(tag in texto for tag in ['🚨 ALERTA:', '📋 INFORMACIÓN COMPLETA']):
            app.logger.info(f"⚠️ Mensaje del sistema de alertas, ignorando: {numero}")
            return 'OK', 200
        
        # 🔄 PARA MI NÚMERO PERSONAL: Permitir todo pero sin alertas
        es_mi_numero = numero in ['5214491182201', '524491182201']
        
        if es_mi_numero:
            app.logger.info(f"🔵 Mensaje de mi número personal, procesando SIN alertas: {numero}")
        
        # ========== PROCESAMIENTO NORMAL PARA TODOS LOS NÚMEROS ==========
        # Actualizar contacto (VERSIÓN MEJORADA - EVITA DUPLICADOS)
        contactos = change.get('contacts')
        if contactos and len(contactos) > 0:
            profile_name = contactos[0].get('profile', {}).get('name')
            wa_id = contactos[0].get('wa_id')
            if profile_name and wa_id:
                try:

                    # OBTENER IMAGEN DE PERFIL
                    imagen_perfil = obtener_imagen_perfil_whatsapp(wa_id)

                    conn = get_db_connection()
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
                    
                    # Insertar o actualizar CON IMAGEN DE PERFIL
                    cursor.execute("""
                        INSERT INTO contactos (numero_telefono, nombre, plataforma, imagen_url)
                        VALUES (%s, %s, 'whatsapp', %s)
                        ON DUPLICATE KEY UPDATE 
                            nombre = VALUES(nombre),
                            imagen_url = VALUES(imagen_url)
                    """, (wa_id, profile_name, imagen_perfil))  # ← Usar imagen_perfil aquí
                    
                    conn.commit()
                    cursor.close()
                    conn.close()
                    app.logger.info(f"✅ Contacto actualizado: {wa_id}")
                    # Asegurar que el contacto exista incluso si no hay información de perfil
                    try:
                        conn = get_db_connection()
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
                    
                except Exception as e:
                    app.logger.error(f"🔴 Error actualizando contacto {wa_id}: {e}")
                    

        # Consultas de precio (funciona para todos)
        if texto.lower().startswith('precio de '):
            servicio = texto[10:].strip()
            info = obtener_precio(servicio)
            if info:
                precio, moneda = info
                respuesta = f"El precio de *{servicio}* es {precio} {moneda}."
            else:
                respuesta = f"No encontré tarifa para *{servicio}*."
            enviar_mensaje(numero, respuesta)
            guardar_conversacion(numero, texto, respuesta, es_imagen, imagen_url if 'imagen_url' in locals() else None)
            return 'OK', 200

        # IA normal
        IA_ESTADOS.setdefault(numero, True)
        respuesta = ""
        if IA_ESTADOS[numero]:
            # ✅ PASAR imagen_base64 EN LUGAR DE url_imagen
            respuesta = responder_con_ia(texto, numero, es_imagen, imagen_base64)
            enviar_mensaje(numero, respuesta)
            # 🔄 SOLO DETECTAR INTERVENCIÓN HUMANA SI NO ES MI NÚMERO
            if detectar_intervencion_humana(texto, respuesta, numero) and numero != ALERT_NUMBER:
                resumen = resumen_rafa(numero)
                enviar_alerta_humana(numero, texto, resumen)
                enviar_informacion_completa(numero)

        guardar_conversacion(numero, texto, respuesta, es_imagen, imagen_url)

        # ========== KANBAN AUTOMÁTICO (para todos) ==========
        meta = obtener_chat_meta(numero)
        if not meta:
            inicializar_chat_meta(numero)
        
        nueva_columna = evaluar_movimiento_automatico(numero, texto, respuesta)
        actualizar_columna_chat(numero, nueva_columna)
        return 'OK', 200

    except Exception as e:
        app.logger.error(f"🔴 Error en webhook: {e}")
        return 'Error interno', 500
# ——— UI ———
@app.route('/')
def inicio():
    return redirect(url_for('home'))

def obtener_imagen_perfil_whatsapp(numero):
    """Obtiene la URL de la imagen de perfil de WhatsApp CORRECTAMENTE"""
    try:
        # Formatear el número correctamente (eliminar el + y cualquier espacio)
        numero_formateado = numero.replace('+', '').replace(' ', '')
        
        # Phone Number ID de tu negocio de WhatsApp
        phone_number_id = "638096866063629"  # Tu Phone Number ID
        
        # URL correcta de la API de Meta
        url = f"https://graph.facebook.com/v18.0/{phone_number_id}"
        
        params = {
            'fields': f'profile_picture_url({numero_formateado})',
            'access_token': WHATSAPP_TOKEN
        }
        
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {WHATSAPP_TOKEN}'
        }
        
        app.logger.info(f"📸 Intentando obtener imagen para: {numero_formateado}")
        app.logger.info(f"📸 URL: {url}")
        app.logger.info(f"📸 Params: {params}")
        
        response = requests.get(url, params=params, headers=headers, timeout=10)
        
        app.logger.info(f"📸 Status Code: {response.status_code}")
        app.logger.info(f"📸 Response: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            if 'profile_picture_url' in data:
                imagen_url = data['profile_picture_url']
                app.logger.info(f"✅ Imagen obtenida: {imagen_url}")
                return imagen_url
            else:
                app.logger.warning(f"⚠️ No se encontró profile_picture_url en la respuesta: {data}")
        
        # Si falla, intentar con la versión alternativa de la API
        return obtener_imagen_perfil_alternativo(numero_formateado)
        
    except Exception as e:
        app.logger.error(f"🔴 Error obteniendo imagen de perfil: {e}")
        return None

def obtener_imagen_perfil_alternativo(numero):
    """Método alternativo para obtener la imagen de perfil"""
    try:
        # Intentar con el endpoint específico para contactos
        phone_number_id = "638096866063629"
        
        url = f"https://graph.facebook.com/v18.0/{phone_number_id}/contacts"
        
        params = {
            'fields': 'profile_picture_url',
            'user_numbers': f'[{numero}]',
            'access_token': WHATSAPP_TOKEN
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
    
@app.route('/home')
def home():
    period = request.args.get('period', 'week')
    now    = datetime.now()
    start  = now - (timedelta(days=30) if period=='month' else timedelta(days=7))

    conn   = get_db_connection()
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
    conn = get_db_connection()
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
    
    cursor.close()
    conn.close()
    
    return render_template('chats.html',
        chats=chats, 
        mensajes=None,
        selected=None, 
        IA_ESTADOS=IA_ESTADOS
    )

@app.route('/chats/<numero>')
def ver_chat(numero):
    conn = get_db_connection()
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
        IA_ESTADOS=IA_ESTADOS
    )        
@app.route('/toggle_ai/<numero>', methods=['POST'])
def toggle_ai(numero):
    try:
        conn = get_db_connection()
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
            conn = get_db_connection()
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
    conn = get_db_connection()
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
        if tab not in ['negocio','personalizacion']:
            abort(404)

        cfg      = load_config()
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
        precios = obtener_todos_los_precios()
        return render_template('configuracion/precios.html',
            tabs=SUBTABS, active='precios',
            guardado=False,
            precios=precios,
            precio_edit=None
        )

@app.route('/configuracion/precios/editar/<int:pid>', methods=['GET'])
def configuracion_precio_editar(pid):
        precios     = obtener_todos_los_precios()
        precio_edit = obtener_precio_por_id(pid)
        return render_template('configuracion/precios.html',
            tabs=SUBTABS, active='precios',
            guardado=False,
            precios=precios,
            precio_edit=precio_edit
        )
@app.route('/configuracion/precios/guardar', methods=['POST'])
def configuracion_precio_guardar():
        data = request.form.to_dict()
        conn   = get_db_connection()
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
        conn   = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM precios WHERE id=%s;", (pid,))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('configuracion_precios'))

    # ——— Kanban ———
@app.route('/kanban')
def ver_kanban():
    conn = get_db_connection()
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
        data = request.get_json()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
          "UPDATE chat_meta SET columna_id=%s WHERE numero=%s;",
          (data['columna_id'], data['numero'])
        )
        conn.commit(); cursor.close(); conn.close()
        return '', 204
        
@app.route('/contactos/<numero>/alias', methods=['POST'])
def guardar_alias_contacto(numero):
        alias = request.form.get('alias','').strip()
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE contactos SET alias=%s WHERE numero_telefono=%s",
            (alias if alias else None, numero)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return '', 204

    # ——— Páginas legales ———
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
def obtener_chat_meta(numero):
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM chat_meta WHERE numero = %s;", (numero,))
        meta = cursor.fetchone()
        cursor.close()
        conn.close()
        return meta

def inicializar_chat_meta(numero):
        # Asignar automáticamente a la columna "Nuevos" (id=1)
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO chat_meta (numero, columna_id) 
            VALUES (%s, 1)
            ON DUPLICATE KEY UPDATE columna_id = VALUES(columna_id);
        """, (numero,))
        conn.commit()
        cursor.close()
        conn.close()

def actualizar_columna_chat(numero, columna_id):
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE chat_meta SET columna_id = %s 
            WHERE numero = %s;
        """, (columna_id, numero))
        conn.commit()
        cursor.close()
        conn.close()

def evaluar_movimiento_automatico(numero, mensaje, respuesta):
        historial = obtener_historial(numero, limite=5)
        
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
if __name__ == '__main__':
        app.run(host='0.0.0.0', port=5000, debug=True)