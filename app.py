# ------------------------------
# app.py - simplificado con Multi-Tenant e IA libre
# ------------------------------
import argparse
import os
import json
import logging
import requests
import mysql.connector
import pytz
import requests
from gtts import gTTS
from flask import Flask, request, jsonify
from dotenv import load_dotenv
from datetime import datetime
from openai import OpenAI

# --- Inicialización ---
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cualquier-cosa")
app.logger.setLevel(logging.INFO)

# --- Configuración básica ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
tz_mx = pytz.timezone('America/Mexico_City')

# ------------------------------
# Configuración multi-tenant
# ------------------------------
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


import requests
from gtts import gTTS

@app.route('/kanban/data')
def kanban_data(config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)

        # Obtener columnas
        cursor.execute("SELECT * FROM kanban_columnas ORDER BY orden")
        columnas = cursor.fetchall()

        # Obtener chats con nombres de contactos
        cursor.execute("""
            SELECT 
                cm.numero,
                cm.columna_id,
                MAX(c.timestamp) AS ultima_fecha,
                (SELECT mensaje FROM conversaciones 
                WHERE numero = cm.numero 
                ORDER BY timestamp DESC LIMIT 1) AS ultimo_mensaje,
                COALESCE(MAX(cont.alias), MAX(cont.nombre), cm.numero) AS nombre_mostrado,
                (SELECT COUNT(*) FROM conversaciones 
                WHERE numero = cm.numero AND respuesta IS NULL) AS sin_leer
            FROM chat_meta cm
            LEFT JOIN contactos cont ON cont.numero_telefono = cm.numero
            LEFT JOIN conversaciones c ON c.numero = cm.numero
            GROUP BY cm.numero, cm.columna_id
            ORDER BY ultima_fecha DESC
        """)
        chats = cursor.fetchall()

        # Convertir timestamps
        for chat in chats:
            if chat.get('ultima_fecha'):
                if chat['ultima_fecha'].tzinfo is not None:
                    chat['ultima_fecha'] = chat['ultima_fecha'].astimezone(tz_mx)
                else:
                    chat['ultima_fecha'] = pytz.utc.localize(chat['ultima_fecha']).astimezone(tz_mx)
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

# ------------------------------
# Enviar texto a WhatsApp
# ------------------------------
def enviar_mensaje(numero, texto, config):
    url = f"https://graph.facebook.com/v23.0/{config['phone_number_id']}/messages"
    headers = {
        "Authorization": f"Bearer {config['whatsapp_token']}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": numero,
        "type": "text",
        "text": {"body": texto}
    }
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        r.raise_for_status()
        app.logger.info(f"✅ Mensaje enviado a {numero}")
    except Exception as e:
        app.logger.error(f"🔴 Error enviando mensaje: {e}")

# ------------------------------
# Texto a voz y envío como audio
# ------------------------------
def enviar_mensaje_voz(numero, texto, config):
    try:
        # Convertir texto a mp3
        tts = gTTS(text=texto, lang="es", slow=False)
        filename = f"respuesta_{numero}.mp3"
        filepath = os.path.join("uploads", filename)
        os.makedirs("uploads", exist_ok=True)
        tts.save(filepath)

        # Subir archivo a tu dominio (ej: https://mektia.com/uploads/...)
        MI_DOMINIO = os.getenv("MI_DOMINIO", "https://mektia.com")
        audio_url = f"{MI_DOMINIO}/uploads/{filename}"

        # Enviar por WhatsApp
        url = f"https://graph.facebook.com/v23.0/{config['phone_number_id']}/messages"
        headers = {
            "Authorization": f"Bearer {config['whatsapp_token']}",
            "Content-Type": "application/json"
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": numero,
            "type": "audio",
            "audio": {"link": audio_url}
        }
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        r.raise_for_status()
        app.logger.info(f"🎵 Audio enviado a {numero}")
    except Exception as e:
        app.logger.error(f"🔴 Error enviando voz: {e}")


def obtener_configuracion_por_host():
    host = request.host if request else None
    if not host:
        return NUMEROS_CONFIG['524495486142']
    for cfg in NUMEROS_CONFIG.values():
        if cfg['dominio'] in host:
            return cfg
    return NUMEROS_CONFIG['524495486142']

# ------------------------------
# Conexión DB
# ------------------------------
def get_db_connection(config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    return mysql.connector.connect(
        host=config['db_host'],
        user=config['db_user'],
        password=config['db_password'],
        database=config['db_name']
    )

# ------------------------------
# Cargar configuración del negocio
# ------------------------------
def load_config(config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    # Cargar configuración básica
    cursor.execute("SELECT * FROM configuracion WHERE id = 1;")
    config_row = cursor.fetchone()
    
    # Cargar menú REAL desde la tabla PRECIOS
    cursor.execute("SELECT servicio, descripcion, precio FROM precios WHERE precio IS NOT NULL ORDER BY id;")
    menu_items = cursor.fetchall()
    
    cursor.close()
    conn.close()

    if not config_row:
        return {}
    
    # Formatear menú exacto como está en la base de datos
    menu_texto = "MENÚ DISPONIBLE (PRECIOS ACTUALES):\n"
    for item in menu_items:
        precio = f"${item['precio']}" if item['precio'] else "Consultar precio"
        menu_texto += f"• {item['servicio']} - {precio}: {item['descripcion']}\n"
    
    if not menu_items:
        menu_texto = "Menú en preparación, por favor pregunta por nuestros platillos disponibles."

    return {
        'ia_nombre': config_row['ia_nombre'],
        'negocio_nombre': config_row['negocio_nombre'],
        'descripcion': config_row['descripcion'],
        'que_hace': config_row['que_hace'],
        'tono': config_row['tono'],
        'lenguaje': config_row['lenguaje'],
        'menu_real': menu_texto  # ← Esto contendrá tu menú exacto
    }
# ------------------------------
# Historial de conversación
# ------------------------------
def obtener_historial(numero, limite=5, config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT mensaje, respuesta
        FROM conversaciones
        WHERE numero = %s
        ORDER BY timestamp DESC
        LIMIT %s
    """, (numero, limite))
    historial = cursor.fetchall()
    cursor.close()
    conn.close()
    historial.reverse()
    return historial

# ------------------------------
# IA: Responder libremente (texto, imágenes, audio)
# ------------------------------
def responder_con_ia(mensaje_usuario, numero, es_imagen=False, imagen_base64=None, es_audio=False, transcripcion_audio=None, config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    cfg = load_config(config)
    ia_nombre = cfg.get('ia_nombre', 'Asistente')
    negocio_nombre = cfg.get('negocio_nombre', '')
    descripcion = cfg.get('descripcion', '')
    que_hace = cfg.get('que_hace', '')
    tono = cfg.get('tono', 'amistoso')

    # Prompt generado desde configuración
    system_prompt = f"""
    Eres {ia_nombre}, asistente virtual de {negocio_nombre}.
    Descripción: {descripcion}
    Tu rol: {que_hace}
    Tono: {tono}.
    Responde con naturalidad y fluidez, sin pasos rígidos.
    """

    historial = obtener_historial(numero, config=config)
    messages_chain = [{'role': 'system', 'content': system_prompt}]

    for h in historial:
        if h['mensaje']:
            messages_chain.append({'role': 'user', 'content': h['mensaje']})
        if h['respuesta']:
            messages_chain.append({'role': 'assistant', 'content': h['respuesta']})

    # Mensaje actual
    if mensaje_usuario:
        if es_imagen and imagen_base64:
            messages_chain.append({
                'role': 'user',
                'content': [
                    {"type": "text", "text": mensaje_usuario},
                    {"type": "image_url", "image_url": {"url": imagen_base64, "detail": "auto"}}
                ]
            })
        elif es_audio and transcripcion_audio:
            messages_chain.append({
                'role': 'user',
                'content': f"[Audio transcrito] {transcripcion_audio}\n\n{mensaje_usuario or ''}"
            })
        else:
            messages_chain.append({'role': 'user', 'content': mensaje_usuario})

    try:
        if es_imagen:
            # Imágenes → GPT-4o
            headers = {"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"}
            payload = {"model": "gpt-4o", "messages": messages_chain, "temperature": 0.7, "max_tokens": 1000}
            response = requests.post(OPENAI_API_URL, headers=headers, json=payload, timeout=60)
        else:
            # Texto/audio → DeepSeek
            headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
            payload = {"model": "deepseek-chat", "messages": messages_chain, "temperature": 0.7, "max_tokens": 1500}
            response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)

        response.raise_for_status()
        data = response.json()
        return data['choices'][0]['message']['content'].strip()
    except Exception as e:
        app.logger.error(f"Error IA: {e}")
        return "Lo siento, hubo un error con la IA."

# ------------------------------
# Endpoint para recibir mensajes
# ------------------------------
@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    app.logger.info(f"📥 Payload recibido: {json.dumps(data, indent=2)}")

    numero_cliente = None
    mensaje = None
    es_imagen = False
    es_audio = False
    imagen_base64 = None
    transcripcion_audio = None
    config = None

    try:
        entry = data['entry'][0]
        change = entry['changes'][0]['value']

        # 1. Identificar desde qué phone_number_id llegó el mensaje
        business_number_id = change.get("metadata", {}).get("phone_number_id")
        if business_number_id:
            # Buscar el tenant correcto por phone_number_id
            for cfg in NUMEROS_CONFIG.values():
                if cfg['phone_number_id'] == business_number_id:
                    config = cfg
                    break
        if not config:
            app.logger.error("❌ No se encontró config para este phone_number_id")
            return jsonify({"status": "error", "msg": "config no encontrada"})

        # 2. Extraer mensaje del usuario
        messages = change.get('messages')
        if messages:
            msg = messages[0]
            numero_cliente = msg.get("from")

            # Texto
            if "text" in msg:
                mensaje = msg["text"]["body"]

            # Imagen
            elif "image" in msg:
                mensaje = "📷 Imagen recibida"
                es_imagen = True
                # Nota: aquí podrías descargar la imagen si quieres analizarla
                # image_id = msg["image"]["id"]

            # Audio
            elif "audio" in msg:
                mensaje = "🎵 Audio recibido"
                es_audio = True
                # Para transcripción deberías descargar el audio con la API de Meta
                # y luego pasarlo a Whisper o a OpenAI
                # Por ahora lo dejamos simulado:
                transcripcion_audio = "Transcripción de audio no implementada"
    except Exception as e:
        app.logger.error(f"❌ Error parseando mensaje: {e}")

    app.logger.info(f"📥 Mensaje recibido de {numero_cliente}: {mensaje}")

    if not numero_cliente or not mensaje:
        return jsonify({"status": "ignored"})

    # 3. Obtener respuesta de la IA
    respuesta = responder_con_ia(
        mensaje,
        numero_cliente,
        es_imagen=es_imagen,
        imagen_base64=imagen_base64,
        es_audio=es_audio,
        transcripcion_audio=transcripcion_audio,
        config=config
    )

    # 4. Guardar conversación en DB
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversaciones (numero, mensaje, respuesta, timestamp)
            VALUES (%s, %s, %s, %s)
        """, (numero_cliente, mensaje, respuesta, datetime.now(tz_mx)))
        conn.commit()
        cursor.close()
        conn.close()
        app.logger.info(f"💾 Conversación guardada para {numero_cliente}")
    except Exception as e:
        app.logger.error(f"❌ Error guardando conversación: {e}")

    # 5. Responder al cliente desde el MISMO número de negocio
    enviar_mensaje(numero_cliente, respuesta, config)

    return jsonify({"status": "ok", "respuesta": respuesta})


# ------------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5000, help='Puerto para ejecutar la aplicación')
    args = parser.parse_args()
    app.run(host='0.0.0.0', port=args.port, debug=False)  # ← Cambia a False para producción
