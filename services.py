import os
import logging
import mysql.connector
from mysql.connector import pooling
from flask import request

logger = logging.getLogger(__name__)
_MYSQL_POOLS = {}

def get_db_connection(config=None):
    cfg = config if config else {}
    
    # Si no especifican BD, el default ahora es 'mektia' (la nueva limpia)
    db_name = cfg.get('db_name', 'mektia')
    db_host = cfg.get('db_host', 'localhost')
    user = 'mektia'
    password = 'Mektia#2025'
    
    pool_key = f"{db_host}|{user}|{db_name}"

    if pool_key not in _MYSQL_POOLS:
        try:
            _MYSQL_POOLS[pool_key] = pooling.MySQLConnectionPool(
                pool_name=f"p_{os.getpid()}_{db_name}"[:32],
                pool_size=10,
                host=db_host,
                user=user,
                password=password,
                database=db_name,
                charset='utf8mb4'
            )
            logger.info(f"✅ Pool de conexiones creado para: {db_name}")
        except Exception as e:
            logger.error(f"❌ Error crítico conectando a {db_name}: {e}")
            raise
    
    return _MYSQL_POOLS[pool_key].get_connection()
def get_cliente_by_subdomain(subdominio):
    try:
        # Conectamos a la base maestra 'clientes'
        conn = get_db_connection({'db_name': 'clientes'})
        cur = conn.cursor(dictionary=True)
        
        # Buscamos por la columna 'dominio'
        query = """
            SELECT 
                dominio as db_name, 
                wa_token, 
                wa_phone_id, 
                wa_verify_token,
                'localhost' as db_host
            FROM cliente 
            WHERE dominio = %s LIMIT 1
        """
        cur.execute(query, (subdominio,))
        res = cur.fetchone()
        
        cur.close()
        conn.close()
        return res
    except Exception as e:
        logger.error(f"⚠️ Error consultando tabla clientes.cliente: {e}")
        return None
