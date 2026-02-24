from flask import Blueprint, request, make_response
import json
from openai import OpenAI
from ver2.configuracion import Config
from ver2.services import get_db_connection
from .whatsapp_envio import enviar_texto

webhook_bp = Blueprint('webhook', __name__)
client_ds = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

# --- FUNCIONES DE PERSISTENCIA ---

def obtener_historial(conn, user_phone, limite=10):
    """Punto 1: Lee los últimos mensajes para darle contexto a la IA."""
    cur = conn.cursor(dictionary=True)
    # Obtenemos los últimos registros ordenados por id descendente
    cur.execute("""
        SELECT mensaje, respuesta FROM conversaciones 
        WHERE numero = %s ORDER BY id DESC LIMIT %s
    """, (user_phone, limite))
    rows = cur.fetchall()
    cur.close()
    
    historial = []
    # Los invertimos para que queden en orden cronológico (viejo -> nuevo)
    for row in reversed(rows):
        if row['mensaje']:
            historial.append({"role": "user", "content": row['mensaje']})
        if row['respuesta']:
            historial.append({"role": "assistant", "content": row['respuesta']})
    return historial

def guardar_mensaje(conn, user_phone, user_text, tenant_slug):
    """Punto 2: Registra lo que el usuario escribió."""
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO conversaciones (numero, mensaje, tipo_mensaje, dominio) 
        VALUES (%s, %s, 'texto', %s)
    """, (user_phone, user_text, tenant_slug))
    last_id = cur.lastrowid
    # No cerramos cursor aquí, lo haremos al finalizar la respuesta o usamos commit
    return last_id

def guardar_respuesta(conn, record_id, respuesta_ia):
    """Punto 3: Actualiza el registro con la respuesta de la IA."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE conversaciones SET respuesta = %s, respuesta_tipo_mensaje = 'texto'
        WHERE id = %s
    """, (respuesta_ia, record_id))
    cur.close()

# --- WEBHOOK PRINCIPAL ---

@webhook_bp.route('/webhook', methods=['POST'])
def recibir_mensajes():
    data = request.get_json()
    try:
        entry = data.get('entry', [{}])[0]
        changes = entry.get('changes', [{}])[0]
        value = changes.get('value', {})
        
        if 'messages' in value:
            message = value['messages'][0]
            phone_id_receptor = value.get('metadata', {}).get('phone_number_id')
            raw_phone = message.get('from')
            user_text = message.get('text', {}).get('body')

            user_phone = '52' + raw_phone[3:] if raw_phone.startswith('521') else raw_phone

            # 1. Identificar el Tenant
            tenant_slug = None
            conn_maestra = get_db_connection({'db_name': Config.CLIENTES_DB_NAME})
            cur_m = conn_maestra.cursor(dictionary=True)
            cur_m.execute("SELECT dominio FROM cliente WHERE wa_phone_id = %s", (phone_id_receptor,))
            res_maestra = cur_m.fetchone()
            cur_m.close()
            conn_maestra.close()

            if res_maestra:
                tenant_slug = res_maestra['dominio']
            elif phone_id_receptor == Config.get_tenant_config('API_V2').get('wa_phone_id'):
                tenant_slug = 'API_V2'

            if not tenant_slug:
                return make_response("NOT_FOUND", 200)

            # 2. Conectar a la DB del Tenant para IA y Persistencia
            config_db = Config.get_tenant_config(tenant_slug)
            conn_tenant = get_db_connection(config_db)
            
            # --- FLUJO DE MEMORIA Y GUARDADO ---
            
            # A. Obtener historial previo
            historial_previo = obtener_historial(conn_tenant, user_phone)
            
            # B. Guardar el mensaje del usuario y obtener ID
            mensaje_id = guardar_mensaje(conn_tenant, user_phone, user_text, tenant_slug)
            conn_tenant.commit()

            # C. Obtener configuración (Brain)
            cur_t = conn_tenant.cursor(dictionary=True)
            cur_t.execute("SELECT ia_nombre, negocio_nombre, que_hace, tono, lenguaje, restricciones FROM configuracion LIMIT 1")
            brain = cur_t.fetchone()
            cur_t.close()

            # D. Construir Prompt con Memoria
            messages_ia = [{"role": "system", "content": f"Eres {brain['ia_nombre']}, {brain['que_hace']}. Tono: {brain['tono']}. Restricciones: {brain['restricciones']}"}]
            messages_ia.extend(historial_previo)
            messages_ia.append({"role": "user", "content": user_text})

            # E. Consultar a DeepSeek
            completion = client_ds.chat.completions.create(
                model="deepseek-chat",
                messages=messages_ia
            )
            respuesta_ia = completion.choices[0].message.content

            # F. Guardar la respuesta de la IA
            guardar_respuesta(conn_tenant, mensaje_id, respuesta_ia)
            conn_tenant.commit()
            
            conn_tenant.close()

            # 3. Enviar a WhatsApp
            resultado_meta = enviar_texto(user_phone, respuesta_ia, config_db)
            print(f"✅ {brain['ia_nombre']} respondió a {user_phone} (Tenant: {tenant_slug})")

    except Exception as e:
        print(f"❌ ERROR EN WEBHOOK: {e}")
    
    return make_response("EVENT_RECEIVED", 200)
    
@webhook_bp.route('/webhook', methods=['GET'])
def verificar_webhook():
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')
    token_esperado = Config.get_tenant_config('API_V2')['verify_token']
    if mode == 'subscribe' and token == token_esperado:
        return challenge, 200
    return 'Forbidden', 403
