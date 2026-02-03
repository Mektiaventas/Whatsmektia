import time
import threading
from datetime import datetime
import pytz
import mysql.connector
import requests
import logging

# Configurar logging para ver qué pasa en la consola
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

tz_mx = pytz.timezone('America/Mexico_City')

print("🚀 [MODULAR] bot_logic/leads.py: Corrigiendo rutas de importación...")

def procesar_followups_automaticos(config):
    # Importaciones de envío (usando la ruta completa para evitar errores)
    try:
        from whatsapp import enviar_mensaje, enviar_plantilla_comodin
    except ImportError:
        # Si falla la anterior, intentamos importación directa si están en el mismo nivel
        import whatsapp
        enviar_mensaje = whatsapp.enviar_mensaje
        enviar_plantilla_comodin = whatsapp.enviar_plantilla_comodin

    try:
        conn = mysql.connector.connect(
            host=config['db_host'],
            user=config['db_user'],
            password=config['db_password'],
            database=config['db_name']
        )
        cursor = conn.cursor(dictionary=True)
        
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

            if ultimo_estado_db == 'Caliente': continue

            if last_f:
                if last_f.tzinfo is None: last_f = pytz.utc.localize(last_f).astimezone(tz_mx)
                if (ahora - last_f).total_seconds() < 82800: continue

            u_msg = chat['ultima_msg']
            if u_msg.tzinfo is None: u_msg = pytz.utc.localize(u_msg).astimezone(tz_mx)
            
            diff_minutos = (ahora - u_msg).total_seconds() / 60
            horas = diff_minutos / 60
            
            tipo_calculado = None
            if horas >= 48: tipo_calculado = 'dormido'
            elif horas >= 15: tipo_calculado = 'frio'
            elif diff_minutos >= 30: tipo_calculado = 'tibio'

            if not tipo_calculado or tipo_calculado == ultimo_estado_db:
                continue

            # Usamos una función de texto más robusta
            texto_ia = _generar_texto_ia_leads(tipo_calculado, config)
            
            enviado = False
            if str(numero).startswith('tg_'):
                enviado = _send_telegram_direct(numero.replace('tg_', ''), texto_ia, config.get('telegram_token'))
            else:
                if tipo_calculado == 'dormido':
                    enviado = enviar_plantilla_comodin(numero, nombre_cliente, texto_ia, config)
                else:
                    enviado = enviar_mensaje(numero, texto_ia, config)

            if enviado:
                _registrar_followup_db(cursor, conn, numero, tipo_calculado, texto_ia)
                logger.info(f"✅ Seguimiento {tipo_calculado} enviado a {numero}")

        cursor.close()
        conn.close()
    except Exception as e:
        logger.error(f"🔴 Error en ciclo de leads: {e}")

def _generar_texto_ia_leads(tipo, config):
    # Aquí puedes poner tu API KEY de DeepSeek directamente para que no falle al importar
    api_key = "TU_DEEPSEEK_API_KEY_AQUI" 
    try:
        prompt = f"Eres un asistente de ventas de {config.get('ia_nombre', 'la empresa')}. El cliente está en estado '{tipo}'. Escribe un mensaje corto para retomar la charla."
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "system", "content": prompt}],
            "temperature": 0.7
        }
        r = requests.post("https://api.deepseek.com/v1/chat/completions", 
                         json=payload, 
                         headers={"Authorization": f"Bearer {api_key}"}, 
                         timeout=10)
        return r.json()['choices'][0]['message']['content']
    except:
        return "¿Sigues interesado en la información que te enviamos? Quedo a tus órdenes."

def _send_telegram_direct(chat_id, text, token):
    if not token: return False
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", 
                      json={"chat_id": chat_id, "text": text}, timeout=10)
        return True
    except: return False

def _registrar_followup_db(cursor, conn, numero, estado, texto):
    try:
        cursor.execute("INSERT INTO mensajes_ia (numero, mensaje, tipo) VALUES (%s, %s, 'followup')", (numero, texto))
        cursor.execute("""
            INSERT INTO chat_meta (numero, ultimo_followup, estado_seguimiento) 
            VALUES (%s, NOW(), %s) ON DUPLICATE KEY UPDATE ultimo_followup = NOW(), estado_seguimiento = %s
        """, (numero, estado, estado))
        conn.commit()
    except: pass

def start_followup_scheduler(config_global):
    return
    """
    Ahora recibe NUMEROS_CONFIG directamente desde app.py
    evitando que este archivo tenga que importar nada de fuera.
    """
    def _worker():
        print("⏰ Scheduler de Seguimiento INICIADO con configuración inyectada.")
        while True:
            try:
                # Usamos la config que nos pasaron desde app.py
                for tenant_key in config_global:
                    procesar_followups_automaticos(config_global[tenant_key])
            except Exception as e:
                print(f"Error en ciclo de leads: {e}")
            time.sleep(1800)
    
    t = threading.Thread(target=_worker, daemon=True)
    t.start()
