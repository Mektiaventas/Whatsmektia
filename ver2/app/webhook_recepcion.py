from flask import Blueprint, request, make_response
import json
from openai import OpenAI
from ver2.configuracion import Config
from ver2.services import get_db_connection
from .whatsapp_envio import enviar_texto

webhook_bp = Blueprint('webhook', __name__)
client_ds = OpenAI(api_key=Config.DEEPSEEK_API_KEY, base_url="https://api.deepseek.com")

@webhook_bp.route('/webhook', methods=['POST'])
def recibir_mensajes():
    data = request.get_json()
    try:
        # Extraer datos básicos del JSON de Meta
        entry = data.get('entry', [{}])[0]
        changes = entry.get('changes', [{}])[0]
        value = changes.get('value', {})
        
        if 'messages' in value:
            message = value['messages'][0]
            phone_id_receptor = value.get('metadata', {}).get('phone_number_id')
            raw_phone = message.get('from')
            user_text = message.get('text', {}).get('body')

            # 1. Limpieza de número (Parche México)
            user_phone = '52' + raw_phone[3:] if raw_phone.startswith('521') else raw_phone

            # 2. Identificar el Tenant (Cliente)
            # Buscamos en la DB maestra quién tiene este wa_phone_id
            tenant_slug = None
            conn_maestra = get_db_connection({'db_name': Config.CLIENTES_DB_NAME})
            cur = conn_maestra.cursor(dictionary=True)
            cur.execute("SELECT dominio FROM cliente WHERE wa_phone_id = %s", (phone_id_receptor,))
            res_maestra = cur.fetchone()
            cur.close()
            conn_maestra.close()

            if res_maestra:
                tenant_slug = res_maestra['dominio']
            elif phone_id_receptor == Config.get_tenant_config('API_V2').get('wa_phone_id'):
                # Si es el ID de test que configuramos como API_V2
                tenant_slug = 'API_V2'

            if not tenant_slug:
                print(f"⚠️ El Phone ID {phone_id_receptor} no está registrado.")
                return make_response("NOT_FOUND", 200)

            # 3. Obtener el "Cerebro" de la IA dinámicamente
            config_db = Config.get_tenant_config(tenant_slug)
            conn_tenant = get_db_connection(config_db)
            cur_t = conn_tenant.cursor(dictionary=True)
            cur_t.execute("""
                SELECT ia_nombre, negocio_nombre, que_hace, tono, lenguaje, restricciones 
                FROM configuracion LIMIT 1
            """)
            brain = cur_t.fetchone()
            cur_t.close()
            conn_tenant.close()

            # 4. Construir el Prompt (Ahora usa brain['ia_nombre'] real)
            prompt_sistema = (
                f"Eres {brain['ia_nombre']}, {brain['que_hace']}. "
                f"Tu negocio es {brain['negocio_nombre']}. "
                f"Tono: {brain['tono']}. Lenguaje: {brain['lenguaje']}. "
                f"RESTRICCIONES IMPORTANTES: {brain['restricciones']}. "
            )

            # 5. Consultar a DeepSeek
            completion = client_ds.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": prompt_sistema},
                    {"role": "user", "content": user_text}
                ]
            )
            respuesta_ia = completion.choices[0].message.content

            # 6. Enviar a WhatsApp y ver el resultado real
            resultado_meta = enviar_texto(user_phone, respuesta_ia, config_db)
            
            # EL PRINT AHORA ES DINÁMICO
            print(f"✅ {brain['ia_nombre']} respondió a {user_phone} (Tenant: {tenant_slug})")
            print(f"📩 Resultado Meta: {resultado_meta}")

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
