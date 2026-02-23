from flask import Blueprint, request, jsonify
from ver2.services import get_cliente_by_subdomain, get_db_connection
from ver2.configuracion import Config
from .whatsapp_envio import enviar_texto, enviar_imagen, enviar_audio

main_bp = Blueprint('main', __name__)

# --- RUTA 1: TEST DE BASE DE DATOS ---
@main_bp.route('/v2/test_tenant', methods=['GET'])
def test_tenant():
    """Prueba la conexión a la DB maestra y a la del cliente."""
    tenant_slug = request.args.get('d')
    if not tenant_slug:
        return jsonify({"error": "Falta parametro d"}), 400

    cliente_info = get_cliente_by_subdomain(tenant_slug)
    if not cliente_info:
        return jsonify({"error": "Tenant no encontrado en DB maestra"}), 404

    credenciales = Config.get_tenant_config(tenant_slug)

    try:
        db_config = {
            'db_name': credenciales['db_name'],
            'db_user': credenciales['db_user'],
            'db_pass': credenciales['db_pass'],
            'db_host': credenciales['db_host']
        }
        
        conn = get_db_connection(db_config)
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT ia_nombre, negocio_nombre FROM configuracion LIMIT 1")
        config_ia = cur.fetchone()
        cur.close()
        conn.close()

        return jsonify({
            "status": "success",
            "msg": "V2 conectada exitosamente",
            "cliente": tenant_slug,
            "datos_db": config_ia
        })
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)}), 500

# --- RUTA 2: TEST DE ENVÍO DE WHATSAPP ---
@main_bp.route('/v2/test_envio', methods=['GET'])
def test_envio():
    """
    Prueba el envío de multimedia.
    Uso: ?d=unilova&num=521XXXXXXXXXX&tipo=texto|imagen|audio
    """
    tenant_slug = request.args.get('d')
    numero = request.args.get('num')
    tipo = request.args.get('tipo', 'texto')
    
    if not tenant_slug or not numero:
        return jsonify({"error": "Faltan parametros d o num"}), 400

    credenciales = Config.get_tenant_config(tenant_slug)
    
    if tipo == 'imagen':
        # Logo de Mektia para prueba
        url_media = "https://mektia.com/static/logo.png"
        res = enviar_imagen(numero, url_media, "Prueba Imagen V22.0", credenciales)
    elif tipo == 'audio':
        # Un .mp3 de prueba (asegúrate de que la URL sea válida)
        url_media = "https://www.soundjay.com/buttons/beep-01a.mp3"
        res = enviar_audio(numero, url_media, credenciales)
    else:
        res = enviar_texto(numero, f"🚀 Mensaje de prueba Mektia V22.0 ({tenant_slug})", credenciales)
    
    return jsonify({
        "status": "request_sent",
        "tenant": tenant_slug,
        "tipo": tipo,
        "meta_response": res
    })
