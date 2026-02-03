import time
import threading
from datetime import datetime
import pytz

# Configuración de zona horaria
tz_mx = pytz.timezone('America/Mexico_City')

# EL PRINT QUE SOLICITASTE
print("✅ [MODULAR] bot_logic/leads.py está en uso. (Control de duplicados activado)")

def procesar_followups_automaticos(config):
    """
    Revisa la base de datos y envía seguimientos si el cliente está inactivo.
    Incluye lógica para NO enviar mensajes repetidos en el mismo estado.
    """
    # Importaciones locales para evitar ciclos con app.py
    from app import get_db_connection, enviar_mensaje, guardar_respuesta_sistema, generar_mensaje_seguimiento_ia, enviar_plantilla_comodin, app
    
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        
        # Obtenemos candidatos y su estado actual de seguimiento
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
        cursor.close()
        conn.close()

        ahora = datetime.now(tz_mx)

        for chat in candidatos:
            numero = chat['numero']
            
            # --- 🛡️ CANDADO 1: EVITAR SPAM POR TIEMPO (23 HORAS) ---
            # Si ya enviamos un seguimiento hoy, saltamos al siguiente cliente.
            last_f = chat['ultimo_followup']
            if last_f:
                if last_f.tzinfo is None: last_f = pytz.utc.localize(last_f).astimezone(tz_mx)
                else: last_f = last_f.astimezone(tz_mx)
                
                if (ahora - last_f).total_seconds() < 82800: # 23 horas
                    continue 

            # Normalizar tiempo del último mensaje del usuario
            last_msg = chat['ultima_msg']
            if last_msg.tzinfo is None: last_msg = pytz.utc.localize(last_msg).astimezone(tz_mx)
            else: last_msg = last_msg.astimezone(tz_mx)

            # Calcular cuánto tiempo ha pasado
            diferencia = ahora - last_msg
            horas = diferencia.total_seconds() / 3600
            minutos = diferencia.total_seconds() / 60
            
            # Determinar nuevo estado
            tipo_calculado = None
            if horas >= 48: tipo_calculado = 'dormido'
            elif horas >= 15: tipo_calculado = 'frio'
            elif minutos >= 30: tipo_calculado = 'tibio'

            # --- 🛡️ CANDADO 2: EVITAR SPAM POR ESTADO ---
            # Si el estado calculado es el mismo que ya tiene, NO enviamos mensaje.
            # Esto evita los 2 o 3 mensajes seguidos de "Tibio".
            if not tipo_calculado or tipo_calculado == chat.get('estado_seguimiento'):
                continue

            # Si pasó los filtros, generamos y enviamos
            app.logger.info(f"🎯 Iniciando rescate de {numero} (Estado: {tipo_calculado})")
            
            texto = generar_mensaje_seguimiento_ia(numero, config, tipo_calculado)
            if texto:
                enviado = False
                if tipo_calculado == 'dormido':
                    # Para >24h usamos plantilla (WhatsApp policy)
                    enviado = enviar_plantilla_comodin(numero, chat.get('alias') or 'Cliente', texto, config)
                else:
                    enviado = enviar_mensaje(numero, texto, config)
                
                if enviado:
                    guardar_respuesta_sistema(numero, texto, config, respuesta_tipo='followup')
                    # Actualizamos la DB para que el sistema "sepa" que ya cumplió este estado
                    _actualizar_meta_seguimiento(numero, tipo_calculado, config)

    except Exception as e:
        print(f"🔴 Error en Leads Modular: {e}")

def _actualizar_meta_seguimiento(numero, estado, config):
    from app import get_db_connection
    try:
        conn = get_db_connection(config)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO chat_meta (numero, ultimo_followup, estado_seguimiento) 
            VALUES (%s, NOW(), %s)
            ON DUPLICATE KEY UPDATE ultimo_followup = NOW(), estado_seguimiento = %s
        """, (numero, estado, estado))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"🔴 Error actualizando meta: {e}")

def start_followup_scheduler():
    """Lanza el hilo que revisa los seguimientos cada 30 min"""
    def _worker():
        from app import app, NUMEROS_CONFIG
        print("⏰ Scheduler de Leads Modular INICIADO.")
        with app.app_context():
            while True:
                try:
                    for tenant_key in NUMEROS_CONFIG:
                        procesar_followups_automaticos(NUMEROS_CONFIG[tenant_key])
                except Exception as e:
                    print(f"🔴 Error en ciclo de scheduler: {e}")
                time.sleep(1800) # 30 minutos
    
    t = threading.Thread(target=_worker, daemon=True, name="ModularLeadsThread")
    t.start()
