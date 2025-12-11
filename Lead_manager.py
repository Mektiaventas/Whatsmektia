import os
import time
import json
import threading
import pytz
import requests
import re
from datetime import datetime, timedelta
import mysql.connector

class LeadManager:
    def __init__(self, app, db_connection_func, config_loader_func, messaging_funcs, logger, tz_mx, deepseek_api_key, deepseek_api_url):
        """
        Inicializa el gestor de leads con todas las dependencias necesarias.
        """
        self.app = app
        self.get_db_connection = db_connection_func
        self.load_config = config_loader_func
        self.logger = logger
        self.tz_mx = tz_mx
        self.deepseek_api_key = deepseek_api_key
        self.deepseek_api_url = deepseek_api_url
        
        # Asignar funciones con verificaciones y fallbacks
        self.enviar_mensaje = messaging_funcs.get('enviar_mensaje')
        self.send_telegram_message = messaging_funcs.get('send_telegram_message')
        self.guardar_respuesta_sistema = messaging_funcs.get('guardar_respuesta_sistema')
        self.obtener_historial = messaging_funcs.get('obtener_historial')
        self.actualizar_estado_conversacion = messaging_funcs.get('actualizar_estado_conversacion')
        
        # Verificar y crear fallbacks para funciones críticas
        self._verificar_y_crear_fallbacks()
        
        self.logger.info("✅ Lead Manager inicializado correctamente")
    
    def _verificar_y_crear_fallbacks(self):
        """Verifica funciones críticas y crea fallbacks si no existen."""
        
        # Verificar enviar_mensaje
        if not self.enviar_mensaje:
            self.logger.warning("⚠️ Función 'enviar_mensaje' no disponible, usando fallback")
            self.enviar_mensaje = self._enviar_mensaje_fallback
        
        # Verificar send_telegram_message
        if not self.send_telegram_message:
            self.logger.warning("⚠️ Función 'send_telegram_message' no disponible, usando fallback")
            self.send_telegram_message = self._send_telegram_message_fallback
        
        # Verificar guardar_respuesta_sistema
        if not self.guardar_respuesta_sistema:
            self.logger.warning("⚠️ Función 'guardar_respuesta_sistema' no disponible, usando fallback")
            self.guardar_respuesta_sistema = self._guardar_respuesta_sistema_fallback
        
        # Verificar obtener_historial
        if not self.obtener_historial:
            self.logger.warning("⚠️ Función 'obtener_historial' no disponible, usando fallback")
            self.obtener_historial = self._obtener_historial_fallback
        
        # Verificar actualizar_estado_conversacion
        if not self.actualizar_estado_conversacion:
            self.logger.warning("⚠️ Función 'actualizar_estado_conversacion' no disponible, usando fallback")
            self.actualizar_estado_conversacion = self._actualizar_estado_conversacion_fallback
    
    # -----------------------------------------------------------------
    # FALLBACK FUNCTIONS
    # -----------------------------------------------------------------
    
    def _enviar_mensaje_fallback(self, numero, texto, config):
        """Fallback si enviar_mensaje no existe."""
        self.logger.info(f"📤 Fallback enviar_mensaje: Simulando envío a {numero}")
        return True
    
    def _send_telegram_message_fallback(self, chat_id, text, token):
        """Fallback si send_telegram_message no existe."""
        self.logger.info(f"📤 Fallback Telegram: Simulando envío a {chat_id}")
        return True
    
    def _guardar_respuesta_sistema_fallback(self, numero, respuesta, config, respuesta_tipo, respuesta_media_url=None):
        """Fallback si guardar_respuesta_sistema no existe."""
        try:
            conn = self.get_db_connection(config)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO conversaciones 
                (numero, respuesta, timestamp, respuesta_tipo, respuesta_media_url)
                VALUES (%s, %s, NOW(), %s, %s)
            """, (numero, respuesta, respuesta_tipo, respuesta_media_url))
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            self.logger.error(f"❌ Error fallback guardar_respuesta_sistema: {e}")
            return False
    
    def _obtener_historial_fallback(self, numero, limite, config):
        """Fallback si obtener_historial no existe."""
        try:
            conn = self.get_db_connection(config)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT mensaje, respuesta, timestamp, tipo_mensaje, imagen_url
                FROM conversaciones 
                WHERE numero = %s 
                ORDER BY timestamp DESC 
                LIMIT %s
            """, (numero, limite))
            historial = cursor.fetchall()
            cursor.close()
            conn.close()
            return historial[::-1]  # Invertir para orden cronológico
        except Exception as e:
            self.logger.error(f"❌ Error fallback obtener_historial: {e}")
            return []
    
    def _actualizar_estado_conversacion_fallback(self, numero, contexto, accion, datos, config):
        """Fallback si actualizar_estado_conversacion no existe."""
        try:
            conn = self.get_db_connection(config)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO chat_meta (numero, contexto, accion, datos, actualizado) 
                VALUES (%s, %s, %s, %s, NOW())
                ON DUPLICATE KEY UPDATE 
                    contexto = VALUES(contexto),
                    accion = VALUES(accion),
                    datos = VALUES(datos),
                    actualizado = NOW()
            """, (numero, str(contexto), accion, str(datos)))
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            self.logger.error(f"❌ Error fallback actualizar_estado_conversacion: {e}")
            return False
    
    # -----------------------------------------------------------------
    # FUNCIONES DE DETECCIÓN DE LEADS POR PALABRAS CLAVE
    # -----------------------------------------------------------------
    
    def procesar_mensaje_y_asignar_lead(self, numero, mensaje, config):
        """
        Procesa un mensaje entrante y asigna lead automáticamente basado en palabras clave.
        Esta es la función PRINCIPAL que supercopia debe llamar.
        """
        try:
            self.logger.info(f"🔍 Procesando mensaje para lead: {numero}")
            
            # 1. Actualizar última interacción del USUARIO
            self._actualizar_ultima_interaccion_usuario(numero, config)
            
            # 2. Detectar nivel de interés basado en palabras clave
            nivel_interes = self._detectar_interes_por_palabras_clave(numero, mensaje, config)
            
            # 3. Recalcular y asignar lead
            lead_asignado = self.recalcular_interes_lead(numero, nivel_interes, config)
            
            # 4. Log del resultado
            self.logger.info(f"✅ Lead asignado: {numero} -> {lead_asignado} (nivel: {nivel_interes})")
            
            return {
                'numero': numero,
                'lead_asignado': lead_asignado,
                'nivel_detectado': nivel_interes,
                'mensaje': mensaje[:50] + '...' if len(mensaje) > 50 else mensaje
            }
            
        except Exception as e:
            self.logger.error(f"❌ Error procesando lead: {e}")
            return {'error': str(e), 'numero': numero}
    
    def _detectar_interes_por_palabras_clave(self, numero, mensaje, config):
        """
        Detecta palabras clave en el mensaje y determina el nivel de interés.
        """
        try:
            # Cargar configuración de leads
            config_data = self.load_config(config)
            leads_config = config_data.get('leads_config_list', {})
            
            if not leads_config:
                self.logger.info(f"ℹ️ No hay configuración de leads para {numero}")
                return 'GENERICO'
            
            mensaje_lower = mensaje.lower()
            
            # Definir orden de prioridad: Caliente > Nuevo > Frío
            prioridad = {'caliente': 3, 'nuevo': 2, 'frio': 1}
            
            mejor_lead = None
            mejor_prioridad = 0
            palabras_encontradas = []
            
            # Revisar cada lead configurado
            for lead_name, lead_config in leads_config.items():
                lead_name_lower = lead_name.lower()
                
                # Verificar si este lead tiene IA activada
                if not lead_config.get('usar_ia', False):
                    continue
                
                # Obtener criterio de IA
                criterio_ia = lead_config.get('criterio_ia', '')
                if not criterio_ia:
                    continue
                
                # Extraer palabras clave del criterio
                palabras_clave = self._extraer_palabras_clave(criterio_ia)
                
                # Verificar coincidencias
                for palabra in palabras_clave:
                    if palabra and len(palabra) > 2:
                        # Buscar palabra completa (no subcadenas dentro de otras palabras)
                        pattern = r'\b' + re.escape(palabra) + r'\b'
                        if re.search(pattern, mensaje_lower):
                            palabras_encontradas.append(palabra)
                            
                            # Calcular prioridad
                            prioridad_actual = prioridad.get(lead_name_lower, 0)
                            if prioridad_actual > mejor_prioridad:
                                mejor_prioridad = prioridad_actual
                                mejor_lead = lead_name_lower
            
            # Decidir nivel de interés basado en el mejor lead encontrado
            if mejor_lead:
                self.logger.info(f"🎯 Palabras clave encontradas: {palabras_encontradas} -> Lead: {mejor_lead}")
                
                if mejor_lead == 'caliente':
                    return 'ESPECIFICO'
                elif mejor_lead == 'nuevo':
                    return 'NUEVO'
                elif mejor_lead == 'frio':
                    return 'GENERICO'
            
            # Si no encontró nada, verificar si es primer mensaje
            if self._es_primer_mensaje(numero, config):
                return 'NUEVO'
            
            return 'GENERICO'
            
        except Exception as e:
            self.logger.error(f"Error en detección de palabras clave: {e}")
            return 'GENERICO'
    
    def _extraer_palabras_clave(self, texto):
        """
        Extrae palabras clave de un texto de criterio.
        Ejemplo: "El cliente preguntó por 'servicios premium' o 'planes anuales'"
        -> retorna ['servicios', 'premium', 'planes', 'anuales']
        """
        palabras = []
        
        # Palabras a excluir (artículos, preposiciones, comunes)
        excluir = {
            'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas',
            'de', 'del', 'al', 'por', 'para', 'con', 'sin', 'sobre',
            'entre', 'hacia', 'desde', 'durante', 'mediante',
            'cliente', 'usuario', 'persona', 'pregunto', 'preguntó',
            'dijo', 'mencionó', 'comento', 'comentó', 'solicito', 'solicitó',
            'o', 'y', 'e', 'u', 'a', 'en', 'que', 'qué'
        }
        
        # 1. Extraer texto entre comillas (frases importantes)
        entre_comillas = re.findall(r'["\'](.*?)["\']', texto)
        for frase in entre_comillas:
            # Dividir frase en palabras
            for palabra in frase.lower().split():
                palabra_limpia = palabra.strip('.,:;!?()[]{}"\'-')
                if palabra_limpia and palabra_limpia not in excluir:
                    palabras.append(palabra_limpia)
        
        # 2. Extraer palabras individuales del resto del texto
        # Limpiar el texto (quitar comillas ya procesadas)
        texto_sin_comillas = re.sub(r'["\'].*?["\']', '', texto)
        
        # Tokenizar palabras
        for palabra in texto_sin_comillas.lower().split():
            palabra_limpia = palabra.strip('.,:;!?()[]{}"\'-')
            if (palabra_limpia and 
                len(palabra_limpia) > 2 and 
                palabra_limpia not in excluir and
                palabra_limpia not in palabras):
                palabras.append(palabra_limpia)
        
        return list(set(palabras))  # Eliminar duplicados
    
    def _es_primer_mensaje(self, numero, config):
        """Verifica si es el primer mensaje del usuario."""
        try:
            conn = self.get_db_connection(config)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT COUNT(*) FROM conversaciones 
                WHERE numero = %s AND mensaje IS NOT NULL 
                AND mensaje != '' AND mensaje NOT LIKE '%%[Mensaje manual%%'
            """, (numero,))
            
            count = cursor.fetchone()[0]
            cursor.close()
            conn.close()
            
            return count <= 1
            
        except Exception as e:
            self.logger.error(f"Error verificando primer mensaje: {e}")
            return False
    
    def _actualizar_ultima_interaccion_usuario(self, numero, config):
        """Actualiza la fecha de última interacción del USUARIO."""
        try:
            conn = self.get_db_connection(config)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE contactos 
                SET ultima_interaccion_usuario = NOW() 
                WHERE numero_telefono = %s
            """, (numero,))
            
            conn.commit()
            cursor.close()
            conn.close()
            
        except Exception as e:
            self.logger.warning(f"⚠️ Error actualizando interacción usuario: {e}")
    
    # -----------------------------------------------------------------
    # FUNCIONES DE GESTIÓN DE LEADS (CORE)
    # -----------------------------------------------------------------
    
    def recalcular_interes_lead(self, numero, nivel_interes_ia, config):
        """
        Asigna el lead correspondiente basado en el nivel de interés detectado.
        """
        try:
            conn = self.get_db_connection(config)
            cursor = conn.cursor()
            
            # 1. Verificar estado actual (si ya es Caliente, mantener)
            cursor.execute("SELECT interes FROM contactos WHERE numero_telefono = %s", (numero,))
            row = cursor.fetchone()
            estado_actual = row[0] if row else None

            # REGLA: Si ya es Caliente, se mantiene Caliente PARA SIEMPRE
            if estado_actual and str(estado_actual).capitalize() == 'Caliente':
                nuevo_interes_db = 'Caliente'
                self.logger.info(f"🛡️ {numero} ya era Caliente, manteniendo estado")
            else:
                # LÓGICA DE ASIGNACIÓN NORMAL
                if nivel_interes_ia == 'ESPECIFICO':
                    nuevo_interes_db = 'Caliente'
                elif nivel_interes_ia == 'NUEVO':
                    nuevo_interes_db = 'Nuevo'
                else:  # GENERICO
                    # Contar mensajes para decidir
                    cursor.execute("""
                        SELECT COUNT(*) FROM conversaciones 
                        WHERE numero = %s AND mensaje IS NOT NULL 
                        AND mensaje != '' AND mensaje NOT LIKE '%%[Mensaje manual%%'
                    """, (numero,))
                    count_msgs = cursor.fetchone()[0]
                    
                    if count_msgs <= 1:
                        nuevo_interes_db = 'Nuevo'
                    else:
                        nuevo_interes_db = 'Tibio'
            
            # 2. Actualizar base de datos
            cursor.execute("""
                UPDATE contactos 
                SET interes = %s 
                WHERE numero_telefono = %s
            """, (nuevo_interes_db, numero))
            
            # 3. Sincronizar con chat_meta para el scheduler
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
            self.logger.error(f"❌ Error en recalcular_interes_lead: {e}")
            return 'Tibio'
    
    # -----------------------------------------------------------------
    # FUNCIONES DE SEGUIMIENTO AUTOMÁTICO
    # -----------------------------------------------------------------
    
    def procesar_followups_automaticos(self, config):
        """Procesa seguimientos automáticos para leads."""
        try:
            conn = self.get_db_connection(config)
            cursor = conn.cursor(dictionary=True)
            
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

            ahora = datetime.now(self.tz_mx)

            for chat in candidatos:
                self._procesar_chat_followup(chat, ahora, config)
                
        except Exception as e:
            self.logger.error(f"❌ Error en procesar_followups_automaticos: {e}")
    
    def _procesar_chat_followup(self, chat, ahora, config):
        """Procesa un chat individual para seguimiento."""
        numero = chat['numero']
        
        # CANDADO: Si ya es Caliente, no hacer seguimiento
        if chat.get('estado_seguimiento', '').lower() == 'caliente':
            return
        
        last_msg = chat['ultima_msg']
        if not last_msg:
            return
            
        # Ajustar timezone si es necesario
        if last_msg.tzinfo is None:
            last_msg = pytz.utc.localize(last_msg).astimezone(self.tz_mx)
        else:
            last_msg = last_msg.astimezone(self.tz_mx)
        
        # Calcular tiempo transcurrido
        diferencia = ahora - last_msg
        minutos = diferencia.total_seconds() / 60
        horas = minutos / 60
        
        # Determinar estado por tiempo
        nuevo_estado = None
        if horas >= 48:
            nuevo_estado = 'dormido'
        elif horas >= 15:
            nuevo_estado = 'frio'
        elif minutos >= 30:
            nuevo_estado = 'tibio'
        
        # Si el estado no cambió, salir
        if nuevo_estado == chat.get('estado_seguimiento'):
            return
        
        # Procesar según el nuevo estado
        if nuevo_estado:
            self.logger.info(f"💡 Actualizando {numero} a {nuevo_estado}")
            self._enviar_seguimiento(numero, nuevo_estado, chat, config)
    
    def _enviar_seguimiento(self, numero, estado, chat_info, config):
        """Envía mensaje de seguimiento según el estado."""
        try:
            nombre_cliente = chat_info.get('alias') or chat_info.get('nombre') or 'Cliente'
            
            # Generar mensaje (usa IA o mensaje configurado)
            mensaje = self._generar_mensaje_seguimiento(numero, estado, config)
            
            if not mensaje:
                return
            
            # Enviar según el estado
            enviado = False
            if estado == 'dormido':
                # Plantilla especial para dormidos
                enviado = self._enviar_plantilla_reactivacion(numero, nombre_cliente, mensaje, config)
            else:
                # Mensaje normal
                if numero and isinstance(numero, str) and numero.startswith('tg_'):
                    token = config.get('telegram_token')
                    if token:
                        enviado = self.send_telegram_message(numero.replace('tg_', ''), mensaje, token)
                else:
                    enviado = self.enviar_mensaje(numero, mensaje, config)
            
            # Actualizar base de datos
            if enviado:
                self.guardar_respuesta_sistema(numero, mensaje, config, respuesta_tipo='followup')
                
                conn = self.get_db_connection(config)
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO chat_meta (numero, ultimo_followup, estado_seguimiento) 
                    VALUES (%s, NOW(), %s)
                    ON DUPLICATE KEY UPDATE 
                        ultimo_followup = NOW(),
                        estado_seguimiento = %s
                """, (numero, estado, estado))
                conn.commit()
                cursor.close()
                conn.close()
                
        except Exception as e:
            self.logger.error(f"❌ Error enviando seguimiento: {e}")
    
    def _generar_mensaje_seguimiento(self, numero, tipo_interes, config):
        """Genera mensaje de seguimiento."""
        try:
            # 1. Verificar si hay mensaje configurado
            cfg = self.load_config(config)
            leads_cfg = cfg.get('leads', {})
            
            mensajes_config = {
                'tibio': leads_cfg.get('mensaje_tibio'),
                'frio': leads_cfg.get('mensaje_frio'),
                'dormido': leads_cfg.get('mensaje_dormido')
            }
            
            mensaje_personalizado = mensajes_config.get(tipo_interes)
            if mensaje_personalizado and mensaje_personalizado.strip():
                return mensaje_personalizado.strip()
            
            # 2. Si no hay config, generar con IA
            historial = self.obtener_historial(numero, limite=6, config=config)
            if not historial:
                return None
                
            contexto = "\n".join([
                f"{'Usuario' if msg.get('mensaje') else 'IA'}: {msg.get('mensaje') or msg.get('respuesta', '')}" 
                for msg in historial if msg
            ])
            
            prompt = f"""
            Eres un asistente de ventas amable.
            El usuario dejó de responder (Estado: {tipo_interes}).
            Historial reciente:
            {contexto}
            
            Genera un mensaje corto (máximo 2 frases) para reactivar la conversación.
            Responde SOLO con el texto del mensaje.
            """
            
            headers = {"Authorization": f"Bearer {self.deepseek_api_key}", "Content-Type": "application/json"}
            payload = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.4,
                "max_tokens": 100
            }
            
            response = requests.post(self.deepseek_api_url, headers=headers, json=payload, timeout=20)
            response.raise_for_status()
            return response.json()['choices'][0]['message']['content'].strip().replace('"', '')
            
        except Exception as e:
            self.logger.error(f"❌ Error generando mensaje seguimiento: {e}")
            return "¿Sigues interesado? Estoy aquí para ayudarte. 👋"
    
    def _enviar_plantilla_reactivacion(self, numero, nombre_cliente, mensaje, config):
        """Envía plantilla de reactivación para leads dormidos."""
        # Esta función requiere implementación específica de WhatsApp API
        # Por ahora, envía mensaje normal como fallback
        self.logger.info(f"📨 Enviando reactivación a {numero}")
        return self.enviar_mensaje(numero, f"Hola {nombre_cliente}, {mensaje}", config)
    
    # -----------------------------------------------------------------
    # FUNCIONES DE INICIALIZACIÓN
    # -----------------------------------------------------------------
    
    def ensure_columns(self, config):
        """Asegura que existan todas las columnas necesarias."""
        self.ensure_interes_column(config)
        self.ensure_chat_meta_followup_columns(config)
        self.ensure_columna_interaccion_usuario(config)
    
    def ensure_interes_column(self, config):
        """Asegura columna 'interes' en contactos."""
        try:
            conn = self.get_db_connection(config)
            cursor = conn.cursor()
            cursor.execute("SHOW COLUMNS FROM contactos LIKE 'interes'")
            if cursor.fetchone() is None:
                cursor.execute("ALTER TABLE contactos ADD COLUMN interes VARCHAR(20) DEFAULT 'Frío'")
                conn.commit()
                self.logger.info("✅ Columna 'interes' creada")
            cursor.close()
            conn.close()
        except Exception as e:
            self.logger.warning(f"⚠️ Error columna interes: {e}")
    
    def ensure_chat_meta_followup_columns(self, config):
        """Asegura columnas en chat_meta para seguimiento."""
        try:
            conn = self.get_db_connection(config)
            cursor = conn.cursor()
            
            for columna in ['ultimo_followup', 'estado_seguimiento']:
                cursor.execute(f"SHOW COLUMNS FROM chat_meta LIKE '{columna}'")
                if cursor.fetchone() is None:
                    if columna == 'ultimo_followup':
                        cursor.execute(f"ALTER TABLE chat_meta ADD COLUMN {columna} DATETIME DEFAULT NULL")
                    else:
                        cursor.execute(f"ALTER TABLE chat_meta ADD COLUMN {columna} VARCHAR(20) DEFAULT NULL")
            
            conn.commit()
            cursor.close()
            conn.close()
            self.logger.info("✅ Columnas de seguimiento creadas")
        except Exception as e:
            self.logger.warning(f"⚠️ Error columnas followup: {e}")
    
    def ensure_columna_interaccion_usuario(self, config):
        """Crea columna para última interacción del usuario."""
        try:
            conn = self.get_db_connection(config)
            cursor = conn.cursor()
            cursor.execute("SHOW COLUMNS FROM contactos LIKE 'ultima_interaccion_usuario'")
            if cursor.fetchone() is None:
                cursor.execute("ALTER TABLE contactos ADD COLUMN ultima_interaccion_usuario DATETIME DEFAULT NULL")
                conn.commit()
                self.logger.info("✅ Columna 'ultima_interaccion_usuario' creada")
            cursor.close()
            conn.close()
        except Exception as e:
            self.logger.warning(f"⚠️ Error columna interacción usuario: {e}")
    
    # -----------------------------------------------------------------
    # SCHEDULER
    # -----------------------------------------------------------------
    
    def start_followup_scheduler(self, NUMEROS_CONFIG):
        """Inicia el scheduler de seguimientos."""
        def _worker():
            self.logger.info("🚀 Scheduler de Seguimiento INICIADO")
            
            # Asegurar columnas una vez al inicio
            for config in NUMEROS_CONFIG.values():
                try:
                    self.ensure_columns(config)
                except Exception as e:
                    self.logger.error(f"❌ Error asegurando columnas: {e}")
            
            while True:
                try:
                    for tenant_key, config in NUMEROS_CONFIG.items():
                        try:
                            with self.app.app_context():
                                self.procesar_followups_automaticos(config)
                        except Exception as e:
                            self.logger.error(f"Error tenant {tenant_key}: {e}")
                    
                    self.logger.info("💤 Scheduler durmiendo 30 minutos...")
                    time.sleep(1800)  # 30 minutos
                    
                except Exception as e:
                    self.logger.error(f"❌ Error fatal en scheduler: {e}")
                    time.sleep(60)
        
        t = threading.Thread(target=_worker, daemon=True, name="lead_scheduler")
        t.start()
        self.logger.info("✅ Scheduler iniciado en segundo plano") 