from flask import Blueprint, request, jsonify
from ver2.services import get_cliente_by_subdomain, get_db_connection

# Definimos el Blueprint
main_bp = Blueprint('main', __name__)

@main_bp.route('/v2/test_tenant', methods=['GET'])
def test_tenant():
    """
    Uso: http://tu-ip:5003/v2/test_tenant?d=unilova
    """
    tenant_slug = request.args.get('d')
    if not tenant_slug:
        return jsonify({"error": "Falta el parámetro 'd' (dominio)"}), 400

    # 1. Buscar en la DB Maestra
    cliente_info = get_cliente_by_subdomain(tenant_slug)
    
    if not cliente_info:
        return jsonify({"error": f"No se encontró el tenant: {tenant_slug}"}), 404

    # 2. Intentar conectar a la DB específica del cliente
    try:
        # Preparamos la config para el pool
        db_config = {
            'db_name': cliente_info['db_name'],
            'db_user': cliente_info['db_name'], # En tu caso suele coincidir
            'db_pass': 'Mektia#2025', # Password estándar según tu .env
            'db_host': '127.0.0.1'
        }
        
        conn = get_db_connection(db_config)
        cur = conn.cursor(dictionary=True)
        
        # 3. Consultar la tabla configuracion del tenant
        cur.execute("SELECT ia_nombre, negocio_nombre, tono FROM configuracion LIMIT 1")
        config_ia = cur.fetchone()
        
        cur.close()
        conn.close()

        return jsonify({
            "status": "success",
            "database_maestra": "conectada",
            "database_tenant": cliente_info['db_name'],
            "datos_ia": config_ia
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "msg": str(e),
            "step": "Conexión a base de datos del cliente"
        }), 500
