from datetime import datetime
import pytz
import os
import logging
import requests
import json
import base64
import mysql.connector
from flask import Flask, request, render_template, redirect, url_for, abort, flash, jsonify
from openai import OpenAI
from dotenv import load_dotenv
from datetime import datetime, timedelta
from decimal import Decimal

tz_mx = pytz.timezone('America/Mexico_City')

load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cualquier-cosa")
app.logger.setLevel(logging.INFO)

# ——— Env vars ———
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DB_HOST = os.getenv("DB_HOST")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")
MI_NUMERO_BOT = os.getenv("MI_NUMERO_BOT")
ALERT_NUMBER = os.getenv("ALERT_NUMBER", "524491182201")

client = OpenAI(api_key=OPENAI_API_KEY)
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
def responder_con_ia(mensaje_usuario, numero):
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
    for entry in historial:
        messages_chain.append({'role': 'user', 'content': entry['mensaje']})
        messages_chain.append({'role': 'assistant', 'content': entry['respuesta']})
    messages_chain.append({'role': 'user', 'content': mensaje_usuario})

    try:
        resp = client.chat.completions.create(
            model='gpt-4',
            messages=messages_chain
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        app.logger.error(f"🔴 OpenAI error: {e}")
        return 'Lo siento, hubo un error con la IA.'

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

def guardar_conversacion(numero, mensaje, respuesta):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS conversaciones (
            id INT AUTO_INCREMENT PRIMARY KEY,
            numero VARCHAR(20),
            mensaje TEXT,
            respuesta TEXT,
            timestamp DATETIME
        ) ENGINE=InnoDB;
    ''')

    timestamp_utc = datetime.utcnow()

    cursor.execute(
        "INSERT INTO conversaciones (numero, mensaje, respuesta, timestamp) VALUES (%s, %s, %s, %s);",
        (numero, mensaje, respuesta, timestamp_utc)
    )

    conn.commit()
    cursor.close()
    conn.close()

# ——— Detección y alerta ———
def detectar_intervencion_humana(mensaje_usuario, respuesta_ia, numero):
    """Detección mejorada que previene loops"""
    
    # ⚠️ EVITAR DETECTAR ALERTAS DEL MISMO SISTEMA
    # Mensajes que provienen del sistema de alertas
    alertas_sistema = [
        "🚨 ALERTA: Intervención Humana Requerida",
        "📋 INFORMACIÓN COMPLETA DEL CLIENTE",
        "👤 Cliente:", "📞 Número:", "💬 Mensaje clave:"
    ]
    
    for alerta in alertas_sistema:
        if alerta in mensaje_usuario:
            return False
    
    # ⚠️ EVITAR TU NÚMERO PERSONAL Y EL NÚMERO DE ALERTA
    if numero == ALERT_NUMBER or numero == '5214491182201' or numero == '524491182201':
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
            
        # ⛔ IGNORAR MENSAJES DEL SISTEMA DE ALERTAS
        # ==============================================
        # PREVENCIÓN MEJORADA - EVITAR LOOPS SOLO PARA MI NÚMERO
        # ==============================================
        # ==============================================
        # PREVENCIÓN MEJORADA - SOLO EVITAR ALERTAS PARA MI NÚMERO
        # ==============================================
        msg = mensajes[0]
        numero = msg['from']
        texto = msg.get('text', {}).get('body', '')

        # ⛔ BLOQUEAR COMPLETAMENTE MENSAJES DEL NÚMERO DE ALERTA (para evitar loops)
        if numero == ALERT_NUMBER:
            app.logger.info(f"⚠️ Mensaje del sistema de alertas, ignorando completamente: {numero}")
            return 'OK', 200  # Ignorar completamente
        
        # 🔄 PARA MI NÚMERO PERSONAL: Permitir todo pero sin alertas
        es_mi_numero = numero in ['5214491182201', '524491182201']
        
        if es_mi_numero:
            app.logger.info(f"🔵 Mensaje de mi número personal, procesando SIN alertas: {numero}")
        
        # ========== PROCESAMIENTO NORMAL PARA TODOS LOS NÚMEROS ==========
        # Actualizar contacto
        contactos = change.get('contacts')
        if contactos and len(contactos) > 0:
            profile_name = contactos[0].get('profile', {}).get('name')
            wa_id = contactos[0].get('wa_id')
            if profile_name and wa_id:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO contactos (numero_telefono, nombre, plataforma, imagen_url)
                    VALUES (%s, %s, 'whatsapp', %s)
                    ON DUPLICATE KEY UPDATE 
                    nombre = COALESCE(VALUES(nombre), nombre),
                    imagen_url = COALESCE(VALUES(imagen_url), imagen_url);
                """, (wa_id, profile_name, change.get('profile', {}).get('picture', None)))
                conn.commit()
                cursor.close()
                conn.close()

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
            guardar_conversacion(numero, texto, respuesta)
            return 'OK', 200

        # IA normal
        IA_ESTADOS.setdefault(numero, True)
        respuesta = ""
        if IA_ESTADOS[numero]:
            respuesta = responder_con_ia(texto, numero)
            enviar_mensaje(numero, respuesta)
            # 🔄 SOLO DETECTAR INTERVENCIÓN HUMANA SI NO ES MI NÚMERO
            if not es_mi_numero and detectar_intervencion_humana(texto, respuesta, numero):
                resumen = resumen_rafa(numero)
                enviar_alerta_humana(numero, texto, resumen)
                enviar_informacion_completa(numero)

        guardar_conversacion(numero, texto, respuesta)

        # ========== KANBAN AUTOMÁTICO (para todos) ==========
        meta = obtener_chat_meta(numero)
        if not meta:
            inicializar_chat_meta(numero)
        
        nueva_columna = evaluar_movimiento_automatico(numero, texto, respuesta)
        actualizar_columna_chat(numero, nueva_columna)
        # ==============================================
        # ==============================================

        # Actualizar contacto
        contactos = change.get('contacts')
        if contactos and len(contactos) > 0:
            profile_name = contactos[0].get('profile', {}).get('name')
            wa_id = contactos[0].get('wa_id')
            if profile_name and wa_id:
                conn = get_db_connection()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO contactos (numero_telefono, nombre, plataforma, imagen_url)
                    VALUES (%s, %s, 'whatsapp', %s)
                    ON DUPLICATE KEY UPDATE 
                    nombre = COALESCE(VALUES(nombre), nombre),
                    imagen_url = COALESCE(VALUES(imagen_url), imagen_url);
                """, (wa_id, profile_name, change.get('profile', {}).get('picture', None)))
                conn.commit()
                cursor.close()
                conn.close()

        msg = mensajes[0]
        numero = msg['from']
        texto = msg.get('text', {}).get('body', '')

        # Consultas de precio
        if texto.lower().startswith('precio de '):
            servicio = texto[10:].strip()
            info = obtener_precio(servicio)
            if info:
                precio, moneda = info
                respuesta = f"El precio de *{servicio}* es {precio} {moneda}."
            else:
                respuesta = f"No encontré tarifa para *{servicio}*."
            enviar_mensaje(numero, respuesta)
            guardar_conversacion(numero, texto, respuesta)
            return 'OK', 200

        # IA normal
        IA_ESTADOS.setdefault(numero, True)
        respuesta = ""
        if IA_ESTADOS[numero]:
            respuesta = responder_con_ia(texto, numero)
            enviar_mensaje(numero, respuesta)
            if detectar_intervencion_humana(texto, respuesta, numero):
                resumen = resumen_rafa(numero)
                enviar_alerta_humana(numero, texto, resumen)
                enviar_informacion_completa(numero)

        guardar_conversacion(numero, texto, respuesta)

        # ==============================================
        # INICIO DEL CÓDIGO NUEVO - KANBAN AUTOMÁTICO
        # ==============================================
        
        # Inicializar metadata del chat si no existe
        meta = obtener_chat_meta(numero)
        if not meta:
            inicializar_chat_meta(numero)
        
        # Evaluar movimiento automático basado en las reglas
        nueva_columna = evaluar_movimiento_automatico(numero, texto, respuesta)
        actualizar_columna_chat(numero, nueva_columna)
        
        # ==============================================
        # FIN DEL CÓDIGO NUEVO
        # ==============================================

        return 'OK', 200

    except Exception as e:
        app.logger.error(f"🔴 Error en webhook: {e}")
        return 'Error interno', 500
        
# ——— UI ———
@app.route('/')
def inicio():
    return redirect(url_for('home'))

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
    conn   = get_db_connection()
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
        chats=chats, mensajes=None,
        selected=None, IA_ESTADOS=IA_ESTADOS
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

    # Esta consulta queda igual (para los mensajes)
    cursor.execute(
        "SELECT * FROM conversaciones WHERE numero=%s ORDER BY timestamp ASC;",
        (numero,)
    )
    msgs = cursor.fetchall()

    for msg in msgs:
        if msg.get('timestamp'):
            msg['timestamp'] = msg['timestamp'].replace(tzinfo=pytz.UTC).astimezone(tz_mx)

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
    IA_ESTADOS[numero] = not IA_ESTADOS.get(numero, True)
    return redirect(url_for('ver_chat', numero=numero))

@app.route('/send-manual', methods=['POST'])
def enviar_manual():
    numero    = request.form['numero']
    texto     = request.form['texto']
    respuesta = ""
    if IA_ESTADOS.get(numero, True):
        respuesta = responder_con_ia(texto, numero)
        enviar_mensaje(numero, respuesta)
        if detectar_intervencion_humana(texto, respuesta):
            resumen = resumen_rafa(numero)
            enviar_template_alerta("Sin nombre", numero, texto, resumen)
    guardar_conversacion(numero, texto, respuesta)
    return redirect(url_for('ver_chat', numero=numero))

@app.route('/chats/<numero>/eliminar', methods=['POST'])
def eliminar_chat(numero):
    conn   = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM conversaciones WHERE numero=%s;", (numero,))
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
    enviar_template_alerta("Prueba", "524491182201", "Mensaje clave", "Resumen de prueba.")
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
    if detectar_intervencion_humana(mensaje, respuesta):
        return 3  # Esperando Respuesta
    
    # Si tiene más de 2 mensajes, mover a "En Conversación"
    if len(historial) >= 2:
        return 2  # En Conversación
    
    # Si no cumple nada, mantener donde está
    meta = obtener_chat_meta(numero)
    return meta['columna_id'] if meta else 1
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
    if detectar_intervencion_humana(mensaje, respuesta):
        return 3  # Esperando Respuesta
    
    # Si tiene más de 2 mensajes, mover a "En Conversación"
    if len(historial) >= 2:
        return 2  # En Conversación
    
    # Si no cumple nada, mantener donde está
    meta = obtener_chat_meta(numero)
    return meta['columna_id'] if meta else 1

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)