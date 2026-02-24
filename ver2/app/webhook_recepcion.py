from flask import Blueprint, request, make_response
import json
from openai import OpenAI
from ver2.configuracion import Config
from ver2.services import get_db_connection, get_cliente_by_subdomain
from .whatsapp_envio import enviar_texto

webhook_bp = Blueprint('webhook', __name__)
client_ds = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

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

            # 1. Ajuste de número México
            user_phone = '52' + raw_phone[3:] if raw_phone.startswith('521') else raw_phone

            # 2. IDENTIFICAR TENANT por phone_id
            # Buscamos en la DB maestra quién es el dueño de este número
            conn_maestra = get_db_connection({'db_name': Config.CLIENTES_DB_NAME})
            cur = conn_maestra.cursor(dictionary=True)
            cur.execute("SELECT dominio FROM cliente WHERE wa_phone_id = %s", (phone_id_receptor,))
            tenant_data = cur.fetchone()
            cur.close()
            conn_maestra.close()

            if not tenant_data:
                print(f"❌ Phone ID {phone_id_receptor} no asociado a ningún cliente.")
                return make_response("NOT_FOUND", 200)

            tenant_slug = tenant_data['dominio'] # Ejemplo: 'lacse'
            
            # 3. OBTENER CONFIGURACIÓN DEL CLIENTE (Cristal, Lacse, etc.)
            # Conectamos a lacse_db usando tus servicios
            config_cliente = Config.get_tenant_config(tenant_slug)
            conn_cliente = get_db_connection(config_cliente)
            cur_c = conn_cliente.cursor(dictionary=True)
            cur_c.execute("SELECT ia_nombre, negocio_nombre, que_hace, tono FROM configuracion LIMIT 1")
            ia_config = cur_c.fetchone()
            cur_c.close()
            conn_cliente.close()

            # 4. CONSULTAR A LA IA CON SU NUEVA PERSONALIDAD
            prompt_sistema = (
                f"Eres {ia_config['ia_nombre']}, asistente de {ia_config['negocio_nombre']}. "
                f"Instrucciones: {ia_config['que_hace']}. Tono: {ia_config['tono']}. "
                f"Responde de forma concisa."
            )

            completion = client_ds.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": user_text}
                ]
            )
            respuesta_ia = completion.choices[0].message.content

            # 5. ENVIAR RESPUESTA
            enviar_texto(user_phone, respuesta_ia, config_cliente)
            print(f"✅ Respondido como {ia_config['ia_nombre']} para el cliente {tenant_slug}")

    except Exception as e:
        print(f"❌ ERROR: {e}")
    
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
