import time
import threading
from datetime import datetime
import pytz
import mysql.connector
import requests
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Zona horaria
tz_mx = pytz.timezone('America/Mexico_City')

print("🚀 [MODULAR] bot_logic/leads.py CARGADO: Funcionalidad completa (WA + Telegram + IA)")

def procesar_followups_automaticos(config):
    """
    Versión modular con TODA la funcionalidad original.
    """
    # Importamos herramientas de envío directamente para evitar círculos con app.py
    from whatsapp import enviar_mensaje, enviar_plantilla_comodin
    
    try:
        # Conexión independiente a la base de datos
        conn = mysql.connector.connect(
            host=config['db_host'],
            user=config['db_user'],
            password=config['db_password'],
            database=config['db_name']
        )
        cursor = conn.cursor(dictionary=True)
        
        # Query de candidatos
        query = """
            SELECT c.numero_telefono as numero, c.alias, c.nombre,
                   COALESCE(c.ultima_interaccion_usuario, c.timestamp) as ultima_msg,
                   cm.ultimo_followup, cm.estado_seguimiento
            FROM contactos c
            LEFT JOIN chat_meta cm ON c.numero_telefono = cm.numero
            WHERE c.ultima_interaccion_usuario IS NOT NULL OR c.timestamp IS NOT NULL
        """
        cursor.execute(query)
        candidatos = cursor.fetchall()

        ahora = datetime.now(tz_mx)

        for chat in candidatos:
            numero = chat['numero']
            last_f = chat['ultimo_followup']
            ultimo_estado_db = chat.get('estado_seguimiento')
            nombre_cliente = chat.get('alias') or chat.get('nombre') or 'Cliente'

            # 1. Filtro de seguridad (Caliente no se toca)
            if ultimo_estado_db == 'Caliente': continue

            # 2. Filtro de 23 horas (Evitar SPAM)
            if last_f:
                if last_f.tzinfo is None: last_f = pytz.utc.localize(last_f).astimezone(tz_mx)
                if (ahora - last_f).total_seconds() < 82800: continue

            # 3. Cálculo de degradación de tiempo
            u_msg = chat['ultima_msg']
            if u_msg.tzinfo is None: u_msg = pytz.utc.localize(u_msg).astimezone(tz_mx)
            
            diff_minutos = (ahora - u_msg).total_seconds() / 60
            horas = diff_minutos / 60
            
            tipo_calculado = None
            if horas >= 48: tipo_calculado = 'dormido'
            elif horas >= 15: tipo_calculado = 'frio'
            elif diff_minutos >= 30: tipo_calculado = 'tibio'

            # 4. Filtro: Solo si el estado cambió
            if not tipo_calculado or tipo_calculado == ultimo_estado_db:
                continue

            # 5. Generación de mensaje con IA (DeepSeek)
            # Como no podemos importar de app, hacemos la llamada aquí
            texto_ia = _generar_texto_ia_leads(tipo_calculado, config)
            
            if texto_ia:
                enviado = False
                
                # SOPORTE TELEGRAM
                if str(numero).startswith('tg_'):
                    enviado = _send_telegram_direct(numero.replace('tg_', ''), texto_ia, config.get('telegram_token'))
                
                # SOPORTE WHATSAPP
                else:
                    if tipo_calculado == 'dormido':
                        enviado = enviar_plantilla_comodin(numero, nombre_cliente, texto_ia, config)
                    else:
                        enviado = enviar_mensaje(numero, texto_ia, config)

                if enviado:
                    # Registrar en base de datos
                    _registrar_followup_db(cursor, conn, numero, tipo_calculado, texto_ia)
                    print(f"✅ Seguimiento {tipo_calculado} enviado a {numero}")

        cursor.close()
        conn.close()
    except Exception as e:
        print(f"🔴 Error crítico en Leads Modular: {e}")

def _generar_texto_ia_leads(tipo, config):
    """Llamada directa a DeepSeek para evitar importar de app.py"""
    try:
        prompt = f"Eres un asistente de ventas de {config.get('ia_nombre')}. El cliente está en estado '{tipo}'. Escribe un mensaje corto y amable para retomar la conversación."
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "system", "content": prompt}],
            "temperature": 0.7
        }
        headers = {"Authorization": "Bearer YOUR_DEEPSEEK_KEY", "Content-Type": "application/json"}
        r = requests.post("https://api.deepseek.com/v1/chat/completions", json=payload, headers=headers, timeout=10)
        return r.json()['choices'][0]['message']['content']
    except:
        return "Hola, ¿sigues interesado en nuestra información?"

def _send_telegram_direct(chat_id, text, token):
    """Enviador de Telegram independiente"""
    if not token: return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        r = requests.post(url, json={"chat_id": chat_id, "text": text})
        return r.status_code == 200
    except:
        return False

def _registrar_followup_db(cursor, conn, numero, estado, texto):
    """Guarda el historial y actualiza el meta"""
    # Guardar en historial (mensajes_ia o similar)
    cursor.execute("INSERT INTO mensajes_ia (numero, mensaje, tipo) VALUES (%s, %s, 'followup')", (numero, texto))
    # Actualizar meta
    cursor.execute("""
        INSERT INTO chat_meta (numero, ultimo_followup, estado_seguimiento) 
        VALUES (%s, NOW(), %s) ON DUPLICATE KEY UPDATE ultimo_followup = NOW(), estado_seguimiento = %s
    """, (numero, estado, estado))
    conn.commit()

def start_followup_scheduler():
    def _worker():
        from settings import NUMEROS_CONFIG
        while True:
            for tenant_key in NUMEROS_CONFIG:
                procesar_followups_automaticos(NUMEROS_CONFIG[tenant_key])
            time.sleep(1800)
    
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
