from flask import Blueprint, request, make_response
import logging
from ver2.configuracion import Config

logger = logging.getLogger(__name__)
webhook_bp = Blueprint('webhook', __name__)

@webhook_bp.route('/webhook', methods=['GET'])
def verificar_webhook():
    """Validación obligatoria para el Dashboard de Meta."""
    mode = request.args.get('hub.mode')
    token = request.args.get('hub.verify_token')
    challenge = request.args.get('hub.challenge')

    # Usamos el verify_token de Mektia definido en tu .env
    token_esperado = Config.get_tenant_config('mektia')['verify_token']

    if mode == 'subscribe' and token == token_esperado:
        logger.info("✅ Webhook V2 verificado")
        return challenge, 200
    else:
        logger.warning("❌ Token de verificación incorrecto")
        return 'Forbidden', 403

@webhook_bp.route('/webhook', methods=['POST'])
def recibir_mensajes():
    """Recibe las notificaciones de mensajes de WhatsApp."""
    data = request.get_json()
    
    # Por ahora solo imprimimos el JSON para analizar la estructura de la V22.0
    print("--- NUEVO MENSAJE RECIBIDO ---")
    print(data)
    
    return make_response("EVENT_RECEIVED", 200)
