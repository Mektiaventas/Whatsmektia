from flask import Blueprint, request, jsonify
from ver2.services import get_cliente_by_subdomain, get_db_connection
from ver2.configuracion import Config

main_bp = Blueprint('main', __name__)

@main_bp.route('/v2/test_tenant', methods=['GET'])
def test_tenant():
    tenant_slug = request.args.get('d') # Ej: unilova
    if not tenant_slug:
        return jsonify({"error": "Falta parametro d"}), 400

    # 1. Buscamos en la maestra para saber que el tenant existe
    cliente_info = get_cliente_by_subdomain(tenant_slug)
    if not cliente_info:
        return jsonify({"error": "Tenant no encontrado en DB maestra"}), 404

    # 2. Obtenemos las credenciales REALES del .env usando el prefijo
    # Esto buscara UNILOVA_DB_USER, UNILOVA_DB_PASSWORD, etc.
    credenciales = Config.get_tenant_config(tenant_slug)

    try:
        # Intentamos la conexión con los datos reales del .env
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
        return jsonify({
            "status": "error",
            "msg": str(e),
            "debug_info": {
                "user_intentado": credenciales['db_user'],
                "db_intentada": credenciales['db_name']
            }
        }), 500
