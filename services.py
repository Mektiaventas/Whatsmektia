import os
import logging
import mysql.connector
from mysql.connector import pooling
from flask import request

logger = logging.getLogger(__name__)
_MYSQL_POOLS = {}

def get_db_connection(config=None):
    cfg = config if config else {}
    
    # --- LÓGICA DE AUTO-CORRECCIÓN ---
    # Si db_name es 'mektia' o está vacío, intentamos rescatar el nombre real
    db_name = cfg.get('db_name')
    if not db_name or db_name == 'mektia':
        # Intentamos obtener el host actual (ej: unilova.mektia.com)
        try:
            host = request.host.split(':')[0]
            # Si el host tiene subdominio, lo usamos como nombre de BD
            if '.' in host and not host.startswith('www'):
                db_name = host.split('.')[0]
            else:
                db_name = 'mektia_db' # Tu base principal según la imagen
        except:
            db_name = 'mektia_db'

    # Corrección final: si después de todo sigue siendo 'mektia', usamos la real
    if db_name == 'mektia': db_name = 'mektia_db'
    # ---------------------------------

    db_host = cfg.get('db_host', 'localhost')
    user = 'mektia'
    passwords_to_try = ['', 'Mektia#2025']
    
    pool_key = f"{db_host}|{user}|{db_name}"

    if pool_key not in _MYSQL_POOLS:
        for pwd in passwords_to_try:
            try:
                _MYSQL_POOLS[pool_key] = pooling.MySQLConnectionPool(
                    pool_name=f"p_{os.getpid()}_{db_name}"[:32],
                    pool_size=10,
                    host=db_host,
                    user=user,
                    password=pwd,
                    database=db_name,
                    charset='utf8mb4'
                )
                logger.info(f"✅ Conectado automáticamente a la BD: {db_name}")
                break
            except Exception as e:
                if pwd == passwords_to_try[-1]:
                    logger.error(f"❌ Error conectando a {db_name}: {e}")
                    raise
    
    return _MYSQL_POOLS[pool_key].get_connection()

def get_cliente_by_subdomain(subdominio):
    # Esta función ya la tienes bien, mantenla igual para buscar en la tabla 'clientes'
    try:
        conn = get_db_connection({'db_name': 'clientes'})
        cur = conn.cursor(dictionary=True)
        query = "SELECT u.shema as db_name, c.wa_token, c.dominio FROM usuarios u JOIN cliente c ON u.id_cliente = c.id WHERE c.dominio = %s OR u.shema = %s LIMIT 1"
        cur.execute(query, (subdominio, subdominio))
        res = cur.fetchone()
        cur.close()
        conn.close()
        return res
    except:
        return None
