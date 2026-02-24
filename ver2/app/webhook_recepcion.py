from flask import Blueprint, request, make_response
import logging
import json
from openai import OpenAI
from ver2.configuracion import Config
from .whatsapp_envio import enviar_texto

# Configuración de logs para verlos en la terminal
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

webhook_bp = Blueprint('webhook', __name__)

# Cliente DeepSeek
client_ds = OpenAI(
    api_key=Config.DEEPSEEK_API_KEY, 
    base_url="https://api.deepseek.com"
)

@webhook_bp.route('/webhook', methods=['POST'])
def recibir_mensajes():
    data = request.get_json()
    
    # 1. Ver qué mandó Meta exactamente
    print("\n--- [DEBUG V2] JSON RECIBIDO ---")
    print(json.dumps(data, indent=2))
    
    try:
        if data.get('object'):
            for entry in data.get('entry', []):
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    if 'messages' in value:
                        message = value['messages'][0]
                        user_phone = message.get('from')
                        # --- EL AJUSTE AQUÍ ---
                        # Meta envía 521 (inválido para envío), nosotros necesitamos 52 (válido)
                        if user_phone.startswith('521'):
                            user_phone = '52' + user_phone[3:]
                            print(f"♻️ Número ajustado de 521 a: {user_phone}")
                        # ----------------------

                        user_text = message.get('text', {}).get('body')
                        
                        print(f"📩 De: {user_phone} | Mensaje: {user_text}")

                        if user_text:
                            # 2. Consultar IA
                            print("🧠 Consultando a DeepSeek...")
                            completion = client_ds.chat.completions.create(
                                model="deepseek-chat",
                                messages=[
                                    {"role": "system", "content": "Eres Mektia V2. Responde en menos de 10 palabras."},
                                    {"role": "user", "content": user_text}
                                ]
                            )
                            respuesta_ia = completion.choices[0].message.content
                            print(f"🤖 IA responde: {respuesta_ia}")

                            # 3. Enviar a WhatsApp usando el prefijo API_V2
                            print("📤 Enviando respuesta a WhatsApp...")
                            credenciales = Config.get_tenant_config('API_V2')
                            res = enviar_texto(user_phone, respuesta_ia, credenciales)
                            print(f"✅ Resultado Meta: {res}")

    except Exception as e:
        print(f"❌ ERROR EN WEBHOOK: {str(e)}")
    
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
