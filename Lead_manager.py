import os
import time
import json
import threading
import pytz
import requests
from datetime import datetime, timedelta
import mysql.connector

# --- IMPORTACIONES NECESARIAS DESDE supercopia.py (Asume que existen) ---
# Se deben manejar las importaciones circulares en el supercopia.py
# Aquí las simulamos asumiendo que serán provistas por el main file.

# Reemplaza estas importaciones placeholder con la lógica real de tu aplicación:
# 1. Necesitas acceso a la configuración multi-tenant (NUMEROS_CONFIG, tz_mx)
# 2. Necesitas acceso a las claves de API (DEEPSEEK_API_KEY, DEEPSEEK_API_URL)
# 3. Necesitas acceso a las funciones de DB (get_db_connection, get_clientes_conn)
# 4. Necesitas acceso a las funciones de mensajería (enviar_mensaje, send_telegram_message, guardar_respuesta_sistema)

# --- PLACEHOLDERS Y CONFIGURACIÓN (Necesitarás pasarlos o importarlos) ---

# Para que este módulo funcione de manera independiente, debe recibir o importar:
# - app.logger (o definir su propio logger)
# - tz_mx
# - DEEPSEEK_API_KEY, DEEPSEEK_API_URL
# - enviar_mensaje, send_telegram_message, guardar_respuesta_sistema
# - get_db_connection, load_config

# Ejemplo de cómo podrías hacer las funciones "importables" desde supercopia:
# (Se asume que estas se pasan como argumentos o se importan desde un módulo de utilidades)

def get_db_connection_placeholder(config):
    # Esto debe ser la función real de supercopia.py
    raise NotImplementedError("get_db_connection debe ser importada/provista.")

def load_config_placeholder(config):
    # Esto debe ser la función real de supercopia.py
    raise NotImplementedError("load_config debe ser importada/provista.")

def enviar_mensaje_placeholder(numero, texto, config):
    # Esto debe ser la función real de supercopia.py
    raise NotImplementedError("enviar_mensaje debe ser importada/provista.")

def send_telegram_message_placeholder(chat_id, text, token):
    # Esto debe ser la función real de supercopia.py
    raise NotImplementedError("send_telegram_message debe ser importada/provista.")

def guardar_respuesta_sistema_placeholder(numero, respuesta, config, respuesta_tipo, respuesta_media_url=None):
    # Esto debe ser la función real de supercopia.py
    raise NotImplementedError("guardar_respuesta_sistema debe ser importada/provista.")

def obtener_historial_placeholder(numero, limite, config):
    # Esto debe ser la función real de supercopia.py
    raise NotImplementedError("obtener_historial debe ser importada/provista.")
    
def actualizar_estado_conversacion_placeholder(numero, contexto, accion, datos, config):
    # Esto debe ser la función real de supercopia.py
    raise NotImplementedError("actualizar_estado_conversacion debe ser importada/provista.")

# --- Funciones de Aseguramiento de Esquema ---

def ensure_columna_interaccion_usuario(config, logger):
    """Crea una columna dedicada a guardar SOLO la fecha del último mensaje del USUARIO."""
    try:
        conn = get_db_connection_placeholder(config)
        cursor = conn.cursor()
        cursor.execute("SHOW COLUMNS FROM contactos LIKE 'ultima_interaccion_usuario'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE contactos ADD COLUMN ultima_interaccion_usuario DATETIME DEFAULT NULL")
            conn.commit()
            logger.info("🔧 Columna 'ultima_interaccion_usuario' creada.")
        cursor.close()
        conn.close()
    except Exception as e:
        logger.warning(f"⚠️ Error columna interaccion usuario: {e}")

def ensure_interes_column(config, logger):
    """Asegura que la tabla contactos tenga la columna interes"""
    try:
        conn = get_db_connection_placeholder(config)
        cursor = conn.cursor()
        cursor.execute("SHOW COLUMNS FROM contactos LIKE 'interes'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE contactos ADD COLUMN interes VARCHAR(20) DEFAULT 'Frío'")
            conn.commit()
            logger.info("🔧 Columna 'interes' creada en tabla 'contactos'")
        cursor.close()
        conn.close()
    except Exception as e:
        logger.warning(f"⚠️ No se pudo asegurar columna interes: {e}")

def ensure_chat_meta_followup_columns(config, logger):
    """Asegura columnas en chat_meta para controlar los seguimientos automáticos."""
    try:
        conn = get_db_connection_placeholder(config)
        cursor = conn.cursor()
        
        cursor.execute("SHOW COLUMNS FROM chat_meta LIKE 'ultimo_followup'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE chat_meta ADD COLUMN ultimo_followup DATETIME DEFAULT NULL")
            
        cursor.execute("SHOW COLUMNS FROM chat_meta LIKE 'estado_seguimiento'")
        if cursor.fetchone() is None:
            cursor.execute("ALTER TABLE chat_meta ADD COLUMN estado_seguimiento VARCHAR(20) DEFAULT NULL")
            
        conn.commit()
        cursor.close()
        conn.close()
        logger.info("🔧 Columnas de seguimiento aseguradas en chat_meta")
    except Exception as e:
        logger.warning(f"⚠️ Error asegurando columnas followup: {e}")

# --- Funciones de Lógica de Leads ---

def generar_mensaje_seguimiento_ia(numero, config, tipo_interes, deepseek_api_key, deepseek_api_url, logger):
    """Genera un mensaje de seguimiento. Prioriza mensaje configurado, sino usa IA."""
    
    try:
        # 1. Cargar configuración para ver si hay mensaje personalizado
        cfg = load_config_placeholder(config)
        leads_cfg = cfg.get('leads', {})
        
        mensaje_personalizado = ""
        if tipo_interes == 'tibio':
            mensaje_personalizado = leads_cfg.get('mensaje_tibio')
        elif tipo_interes == 'frio':
            mensaje_personalizado = leads_cfg.get('mensaje_frio')
        elif tipo_interes == 'dormido':
            mensaje_personalizado = leads_cfg.get('mensaje_dormido')
            
        # Si existe un mensaje configurado por el usuario, USARLO DIRECTAMENTE
        if mensaje_personalizado and mensaje_personalizado.strip():
            logger.info(f"✅ Usando mensaje personalizado de Leads ({tipo_interes}) para {numero}")
            return mensaje_personalizado.strip()

        # 2. Si no hay mensaje configurado, usar IA
        historial = obtener_historial_placeholder(numero, limite=6, config=config)
        if not historial:
            return None 
            
        contexto = "\n".join([f"{'Usuario' if msg['mensaje'] else 'IA'}: {msg['mensaje'] or msg['respuesta']}" for msg in historial])

        # Prompt para la IA
        prompt = f"""
        Eres un asistente de ventas amable y profesional.
        El usuario dejó de responder (Estado: {tipo_interes}). Tu objetivo es reactivar la conversación SIN ser molesto.
        
        HISTORIAL RECIENTE:
        {contexto}
        
        Genera un mensaje corto (máximo 2 frases) para preguntar si sigue interesado.
        Responde SOLO con el texto del mensaje.
        """
        
        headers = {"Authorization": f"Bearer {deepseek_api_key}", "Content-Type": "application/json"}
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.4,
            "max_tokens": 100
        }
        
        response = requests.post(deepseek_api_url, headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        mensaje_seguimiento = response.json()['choices'][0]['message']['content'].strip().replace('"', '')
        
        return mensaje_seguimiento

    except Exception as e:
        logger.error(f"🔴 Error generando seguimiento IA: {e}")
        return "¿Sigues ahí? Avísame si necesitas más información. 👋" # Fallback


def enviar_plantilla_comodin(numero, nombre_cliente, mensaje_libre, config, logger, enviar_mensaje_func):
    """
    Envía una plantilla de utilidad/marketing para reactivar usuarios fuera de las 24h.
    Esta función requiere la implementación de la API de WhatsApp para plantillas.
    Por simplicidad y para evitar circular imports, este código debe **permanecer**
    en el archivo principal (supercopia.py) si necesitas acceder a WHATSAPP_TOKEN,
    o debes pasar todos los parámetros necesarios.
    """
    # Si esta función se queda en leads_manager.py, necesitarás:
    # - config['phone_number_id']
    # - config['whatsapp_token']
    
    # Dado que depende de configuraciones globales de WhatsApp, la mantendremos aquí
    # por ahora, pero usaremos el placeholder de enviar_mensaje
    
    # ⚠️ REGLA: Esta función es un punto de acoplamiento fuerte y es la única que necesita
    # el token de WhatsApp. La dejaremos con el placeholder y la implementas en supercopia.py
    
    logger.info(f"🚨 Placeholder: enviando plantilla comodín a {numero}")
    # Simulamos el envío con un mensaje normal, pero esto DEBE ser una plantilla en producción.
    texto_simulado = f"Hola {nombre_cliente}, {mensaje_libre}"
    return enviar_mensaje_func(numero, texto_simulado, config) # Usa la función de envío real


def procesar_followups_automaticos(config, logger, tz_mx, deepseek_api_key, deepseek_api_url, enviar_mensaje_func, send_telegram_message_func, guardar_respuesta_sistema_func):
    """
    Busca chats que necesiten seguimiento y degrada el estado si es necesario.
    """
    try:
        conn = get_db_connection_placeholder(config)
        cursor = conn.cursor(dictionary=True)
        
        # Obtenemos el estado actual
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

        if not candidatos:
            return

        ahora = datetime.now(tz_mx)

        for chat in candidatos:
            numero = chat['numero']
            nombre_cliente = chat.get('alias') or chat.get('nombre') or 'Cliente'
            
            last_msg = chat['ultima_msg']
            ultimo_estado_db = chat.get('estado_seguimiento')
            
            # --- 🛡️ CANDADO DE SEGURIDAD PARA 'CALIENTE' ---
            if ultimo_estado_db and ultimo_estado_db.lower() == 'caliente':
                continue

            if last_msg:
                if last_msg.tzinfo is None:
                    last_msg = pytz.utc.localize(last_msg).astimezone(tz_mx)
                else:
                    last_msg = last_msg.astimezone(tz_mx)
            else:
                continue

            diferencia = ahora - last_msg
            minutos = diferencia.total_seconds() / 60
            horas = minutos / 60
            
            tipo_interes_calculado = None
            
            # --- REGLAS DE DEGRADACIÓN (Solo si NO era Caliente) ---
            if horas >= 48:
                tipo_interes_calculado = 'dormido'
            elif horas >= 15:
                tipo_interes_calculado = 'frio'
            elif minutos >= 30:
                tipo_interes_calculado = 'tibio'
            
            if tipo_interes_calculado == ultimo_estado_db:
                continue

            if tipo_interes_calculado:
                logger.info(f"💡 Actualizando estado por tiempo ({tipo_interes_calculado}) para {numero}...")
                
                enviado = False
                texto_guardado = ""

                # Lógica de envío (Frio/Dormido)
                if tipo_interes_calculado in ['frio', 'dormido']:
                    texto_followup = generar_mensaje_seguimiento_ia(numero, config, tipo_interes_calculado, deepseek_api_key, deepseek_api_url, logger)
                    
                    if texto_followup:
                        if tipo_interes_calculado == 'dormido':
                            # Usar la función de envío de plantilla comodín
                            enviado = enviar_plantilla_comodin(numero, nombre_cliente, texto_followup, config, logger, enviar_mensaje_func)
                            texto_guardado = f"[Plantilla Reactivación]: {texto_followup}"
                        else:
                            # Enviar mensaje normal si es Frio
                            if numero.startswith('tg_'):
                                token = config.get('telegram_token')
                                if token:
                                    enviado = send_telegram_message_func(numero.replace('tg_',''), texto_followup, token)
                            else:
                                enviado = enviar_mensaje_func(numero, texto_followup, config)
                            texto_guardado = texto_followup

                # Actualizar DB
                conn2 = get_db_connection_placeholder(config)
                cur2 = conn2.cursor()
                
                if enviado:
                    guardar_respuesta_sistema_func(numero, texto_guardado, config, respuesta_tipo='followup')
                    cur2.execute("""
                        INSERT INTO chat_meta (numero, ultimo_followup, estado_seguimiento) 
                        VALUES (%s, NOW(), %s)
                        ON DUPLICATE KEY UPDATE 
                            ultimo_followup = NOW(),
                            estado_seguimiento = %s
                    """, (numero, tipo_interes_calculado, tipo_interes_calculado))
                else:
                    # Solo cambiar estado sin mensaje (ej. paso a Tibio)
                    cur2.execute("""
                        INSERT INTO chat_meta (numero, estado_seguimiento) 
                        VALUES (%s, %s)
                        ON DUPLICATE KEY UPDATE 
                            estado_seguimiento = %s
                    """, (numero, tipo_interes_calculado, tipo_interes_calculado))
                
                conn2.commit()
                cur2.close()
                conn2.close()

    except Exception as e:
        logger.error(f"🔴 Error en procesar_followups_automaticos: {e}")


def start_followup_scheduler(app, NUMEROS_CONFIG, tz_mx, logger, deepseek_api_key, deepseek_api_url, enviar_mensaje_func, send_telegram_message_func, guardar_respuesta_sistema_func):
    """Ejecuta la revisión de seguimientos cada 30 minutos en segundo plano."""
    
    # ⚠️ Esta función debe llamarse UNA SOLA VEZ al iniciar la aplicación.
    
    def _worker():
        logger.info("⏰ Scheduler de Seguimiento (Interés Medio) INICIADO.")
        
        # Asegurar columnas la primera vez
        for config in NUMEROS_CONFIG.values():
             with app.app_context(): # Se asume que app.app_context() está disponible
                ensure_chat_meta_followup_columns(config, logger) 

        while True:
            try:
                # Iterar por todos los tenants
                for tenant_key, config in NUMEROS_CONFIG.items():
                    try:
                        # Procesar en el contexto del tenant
                        with app.app_context(): # Se asume que app.app_context() está disponible
                            # Pasa todas las dependencias necesarias a la función
                            procesar_followups_automaticos(config, logger, tz_mx, deepseek_api_key, deepseek_api_url, enviar_mensaje_func, send_telegram_message_func, guardar_respuesta_sistema_func)
                    except Exception as e:
                        logger.error(f"Error en scheduler tenant {tenant_key}: {e}")
                
                logger.info("💤 Scheduler durmiendo 30 minutos...")
                time.sleep(1800) # 1800 segundos = 30 minutos
                
            except Exception as e:
                logger.error(f"🔴 Error fatal en hilo scheduler: {e}")
                time.sleep(60) # Esperar 1 min antes de reintentar si falla

    t = threading.Thread(target=_worker, daemon=True, name="followup_scheduler")
    t.start()
    logger.info("✅ Followup scheduler thread launched")


def recalcular_interes_lead(numero, nivel_interes_ia, config, logger):
    """
    Define el interés BASE al recibir un mensaje.
    REGLA: Si ya era 'Caliente', se mantiene 'Caliente' para siempre.
    Si no, evalúa reglas normales.
    """
    try:
        conn = get_db_connection_placeholder(config)
        cursor = conn.cursor()
        
        # 1. Verificar estado ACTUAL antes de calcular nada
        cursor.execute("SELECT interes FROM contactos WHERE numero_telefono = %s", (numero,))
        row = cursor.fetchone()
        estado_actual = row[0] if row else None

        # --- 🛡️ CANDADO DE SEGURIDAD ---
        if estado_actual and str(estado_actual).capitalize() == 'Caliente':
            nuevo_interes_db = 'Caliente'
        else:
            # --- LÓGICA DE CÁLCULO NORMAL (Si no era caliente) ---
            
            # Contar mensajes para saber si es el primero
            cursor.execute("SELECT COUNT(*) FROM conversaciones WHERE numero = %s AND mensaje IS NOT NULL AND mensaje != '' AND mensaje NOT LIKE '%%[Mensaje manual%%'", (numero,))
            count_msgs = cursor.fetchone()[0]
            
            nuevo_interes_db = 'Tibio' # Default
            
            # REGLA PARA SER CALIENTE POR PRIMERA VEZ
            if nivel_interes_ia == 'ESPECIFICO' and count_msgs <= 1:
                nuevo_interes_db = 'Caliente'
            elif nivel_interes_ia == 'ESPECIFICO':
                 nuevo_interes_db = 'Caliente' # Si es específico, forzar a Caliente.
            else:
                nuevo_interes_db = 'Tibio'
        
        # Actualizar en Tablas
        cursor.execute("UPDATE contactos SET interes = %s WHERE numero_telefono = %s", (nuevo_interes_db, numero))
        
        # Sincronizar chat_meta para que el scheduler lo sepa
        cursor.execute("""
            INSERT INTO chat_meta (numero, estado_seguimiento) 
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE estado_seguimiento = %s
        """, (numero, nuevo_interes_db.lower(), nuevo_interes_db.lower()))

        conn.commit()
        cursor.close()
        conn.close()
        
        return nuevo_interes_db
    except Exception as e:
        logger.error(f"Error recalculando interés: {e}")
        return 'Tibio'