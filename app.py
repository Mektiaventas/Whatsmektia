# ------------------------------
# app.py - simplificado con Multi-Tenant e IA libre
# ------------------------------
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
    '524495486142': {  # Mektia
        'db_host': os.getenv("MEKTIA_DB_HOST"),
        'db_user': os.getenv("MEKTIA_DB_USER"),
        'db_password': os.getenv("MEKTIA_DB_PASSWORD"),
        'db_name': os.getenv("MEKTIA_DB_NAME"),
        'dominio': 'mektia.com'
    },
    '524812372326': {  # La Porfirianna
        'db_host': os.getenv("PORFIRIANNA_DB_HOST"),
        'db_user': os.getenv("PORFIRIANNA_DB_USER"),
        'db_password': os.getenv("PORFIRIANNA_DB_PASSWORD"),
        'db_name': os.getenv("PORFIRIANNA_DB_NAME"),
        'dominio': 'laporfirianna.mektia.com'
    }
}

import requests
from gtts import gTTS

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
    cursor.execute("SELECT * FROM configuracion WHERE id = 1;")
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        return {}
    return {
        'ia_nombre': row['ia_nombre'],
        'negocio_nombre': row['negocio_nombre'],
        'descripcion': row['descripcion'],
        'que_hace': row['que_hace'],
        'tono': row['tono'],
        'lenguaje': row['lenguaje']
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
    # 1. Detectar tenant
    config = obtener_configuracion_por_host()

    # 2. Recibir datos del mensaje
    data = request.get_json()
    numero = data.get("numero")
    mensaje = data.get("mensaje")
    es_imagen = data.get("es_imagen", False)
    es_audio = data.get("es_audio", False)
    imagen_base64 = data.get("imagen_base64")
    transcripcion_audio = data.get("transcripcion_audio")

    app.logger.info(f"📥 Mensaje recibido de {numero}: {mensaje}")

    # 3. Obtener respuesta de la IA
    respuesta = responder_con_ia(
        mensaje,
        numero,
        es_imagen=es_imagen,
        imagen_base64=imagen_base64,
        es_audio=es_audio,
        transcripcion_audio=transcripcion_audio,
        config=config
    )

    # 4. Guardar conversación en BD
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversaciones (numero, mensaje, respuesta, timestamp)
            VALUES (%s, %s, %s, %s)
        """, (numero, mensaje, respuesta, datetime.now(tz_mx)))
        conn.commit()
        cursor.close()
        conn.close()
        app.logger.info(f"💾 Conversación guardada para {numero}")
    except Exception as e:
        app.logger.error(f"❌ Error guardando conversación: {e}")

    # 5. Enviar respuesta de texto a WhatsApp
    enviar_mensaje(numero, respuesta, config)

    # 6. (Opcional) Enviar también la respuesta como audio
    # enviar_mensaje_voz(numero, respuesta, config)

    return jsonify({"status": "ok", "respuesta": respuesta})


# ------------------------------
if __name__ == "__main__":
    app.run(port=5000, debug=True)
