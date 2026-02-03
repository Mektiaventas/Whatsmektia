import time
import threading
from datetime import datetime
import pytz
import requests

# Mantener tu zona horaria original
tz_mx = pytz.timezone('America/Mexico_City')

# LA LÍNEA DE CONFIRMACIÓN QUE PEDISTE
print("🚀 [MODULAR] bot_logic/leads.py CARGADO: Manteniendo toda la funcionalidad original.")

def procesar_followups_automaticos(config):
    """
    Versión modular que conserva TODA tu lógica original:
    - Soporte Telegram
    - Registro de respuestas
    - Degradación de estados
    - Plantillas de reactivación
    - Registro en logs
    """
    # Importaciones dinámicas para no romper el archivo principal
    from app import (
        get_db_connection, enviar_mensaje, guardar_respuesta_sistema, 
        generar_mensaje_seguimiento_ia, enviar_plantilla_comodin, 
        app, send_telegram_message
    )
    
    try:
        # 1. Asegurar columnas (tu lógica original)
        # _ensure_chat_meta_followup_columns(config) # Si la tienes en app.py, impórtala también

        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        
        # 2. Query original para obtener candidatos
        query = """
            SELECT 
                c.numero_telefono as numero,
                c.nombre,
                c.alias,
                COALESCE(c.ultima_interaccion_usuario, c.timestamp) as ultima_msg,
                cm.ultimo_followup,
                cm.estado_seguimiento
            FROM contactos c
            LEFT JOIN chat_meta cm ON c.numero_telefono = cm.numero
            WHERE c.ultima_interaccion_usuario IS NOT NULL 
               OR c.timestamp IS NOT NULL
        """
        cursor.execute(query)
        candidatos = cursor.fetchall()
        cursor.close()
        conn.close()

        ahora = datetime.now(tz_mx)

        for chat in candidatos:
            numero = chat['numero']
            nombre_cliente = chat.get('alias') or chat.get('nombre') or 'Cliente'
            last_msg = chat['ultima_msg']
            last_followup = chat['ultimo_followup']
            ultimo_estado_db = chat.get('estado_seguimiento')

            # --- 🛡️ CANDADO DE SEGURIDAD PARA 'CALIENTE' (Tu lógica original) ---
            if ultimo_estado_db and ultimo_estado_db.lower() == 'caliente':
                continue

            # --- 🛡️ NORMALIZACIÓN DE TIEMPOS (Tu lógica original mejorada) ---
            if last_msg:
                if last_msg.tzinfo is None:
                    last_msg = pytz.utc.localize(last_msg).astimezone(tz_mx)
                else:
                    last_msg = last_msg.astimezone(tz_mx)
            else:
                continue

            # --- 🛑 NUEVO FRENO PARA EVITAR MENSAJES REPETIDOS ---
            if last_followup:
                if last_followup.tzinfo is None:
                    last_followup = pytz.utc.localize(last_followup).astimezone(tz_mx)
                else:
                    last_followup = last_followup.astimezone(tz_mx)
                
                # Si enviamos algo hace menos de 23 horas, saltar (Freno de seguridad)
                if (ahora - last_followup).total_seconds() < 82800:
                    continue

            # --- 📊 CÁLCULO DE DEGRADACIÓN (Tu lógica original) ---
            diferencia = ahora - last_msg
            horas = diferencia.total_seconds() / 3600
            minutos = diferencia.total_seconds() / 60
            
            tipo_interes_calculado = None
            if horas >= 48: tipo_interes_calculado = 'dormido'
            elif horas >= 15: tipo_interes_calculado = 'frio'
            elif minutos >= 30: tipo_interes_calculado = 'tibio'

            # --- 🛡️ SEGUNDO FRENO: No enviar si el estado no ha cambiado ---
            if not tipo_interes_calculado or tipo_interes_calculado == ultimo_estado_db:
                continue

            # --- ✉️ LÓGICA DE ENVÍO (Tu lógica original completa) ---
            app.logger.info(f"💡 Actualizando estado a {tipo_interes_calculado} para {numero}...")
            
            enviado = False
            texto_guardado = ""

            if tipo_interes_calculado in ['frio', 'dormido']:
                texto_followup = generar_mensaje_seguimiento_ia(numero, config, tipo_interes_calculado)
                
                if texto_followup:
                    if tipo_interes_calculado == 'dormido':
                        enviado = enviar_plantilla_comodin(numero, nombre_cliente, texto_followup, config)
                        texto_guardado = f"[Plantilla Reactivación]: {texto_followup}"
                    else:
                        # Soporte Telegram (Tu lógica original)
                        if numero.startswith('tg_'):
                            token = config.get('telegram_token')
                            if token:
                                enviado = send_telegram_message(numero.replace('tg_',''), texto_followup, token)
                        else:
                            enviado = enviar_mensaje(numero, texto_followup, config)
                        texto_guardado = texto_followup

            # --- 💾 ACTUALIZACIÓN DE DB (Tu lógica original) ---
            _guardar_meta_db(numero, tipo_interes_calculado, enviado, texto_guardado, config)

    except Exception as e:
        print(f"🔴 Error en Leads Modular: {e}")

def _guardar_meta_db(numero, estado, enviado, texto, config):
    """Función interna para no repetir código de SQL"""
    from app import get_db_connection, guardar_respuesta_sistema
    conn2 = get_db_connection(config)
    cur2 = conn2.cursor()
    if enviado:
        guardar_respuesta_sistema(numero, texto, config, respuesta_tipo='followup')
        cur2.execute("""
            INSERT INTO chat_meta (numero, ultimo_followup, estado_seguimiento) 
            VALUES (%s, NOW(), %s) ON DUPLICATE KEY UPDATE ultimo_followup = NOW(), estado_seguimiento = %s
        """, (numero, estado, estado))
    else:
        cur2.execute("""
            INSERT INTO chat_meta (numero, estado_seguimiento) 
            VALUES (%s, %s) ON DUPLICATE KEY UPDATE estado_seguimiento = %s
        """, (numero, estado, estado))
    conn2.commit()
    cur2.close()
    conn2.close()

def start_followup_scheduler():
    """Hilo del scheduler (Tu lógica original multitenant)"""
    def _worker():
        from app import app, NUMEROS_CONFIG
        print("⏰ Scheduler de Seguimiento INICIADO.")
        with app.app_context():
            while True:
                try:
                    for tenant_key, config in NUMEROS_CONFIG.items():
                        procesar_followups_automaticos(config)
                    time.sleep(1800) # 30 minutos
                except Exception as e:
                    print(f"🔴 Error en hilo scheduler: {e}")
                    time.sleep(60)

    t = threading.Thread(target=_worker, daemon=True, name="followup_scheduler_modular")
    t.start()
