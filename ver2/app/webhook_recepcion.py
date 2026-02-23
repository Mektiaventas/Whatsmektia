from flask import Blueprint, request, make_response
import logging
import os
from openai import OpenAI
from ver2.configuracion import Config
from .whatsapp_envio import enviar_texto, marcar_leido

logger = logging.getLogger(__name__)
webhook_bp = Blueprint('webhook', __name__)

# Inicializamos el cliente de DeepSeek usando tu variable global del .env
client_ds = OpenAI(
    api_key=Config.DEEPSEEK_API_KEY, 
    base_url="https://api.deepseek.com"
)

@webhook_bp.route('/webhook', methods=['GET'])
def verificar_webhook():
    """Validación obligatoria para el Dashboard de Meta."""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    # Usamos el prefijo 'API_V2' que definimos en tu .env para el webhook maestro
    token_esperado = Config.get_tenant_config('API_V2')['verify_token']

    if mode == 'subscribe' and token == token_esperado:
        return challenge, 200
    return 'Forbidden', 403

@webhook_bp.route('/webhook', methods=['POST'])
def recibir_mensajes():
    """Recibe mensajes, consulta a DeepSeek y responde."""
    data = request.get_json()
    
    try:
        # Extraemos la estructura básica de Meta
        entry = data.get('entry', [{}])[0]
        changes = entry.get('changes', [{}])[0]
        value = changes.get('value', {})
        
        if 'messages' in value:
            message = value['messages'][0]
            numero_usuario = message.get('from')
            texto_usuario = message.get('text', {}).get('body')
            msg_id = message.get('id')

            if texto_usuario:
                # 1. Marcar como leído (opcional, da profesionalismo)
                credenciales_v2 = Config.get_tenant_config('API_V2')
                marcar_leido(msg_id, credenciales_v2)

                # 2. Llamada a DeepSeek
                completion = client_ds.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": "Eres Mektia V2, un asistente inteligente."},
                        {"role": "user", "content": texto_usuario}
                    ]
                )
                respuesta_ia = completion.choices[0].message.content

                # 3. Enviar respuesta de vuelta
                enviar_texto(numero_usuario, respuesta_ia, credenciales_v2)
                
    except Exception as e:
        logger.error(f"❌ Error procesando webhook: {e}")

    return make_response("EVENT_RECEIVED", 200)
