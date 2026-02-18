import os
import logging
import mysql.connector
from mysql.connector import pooling

logger = logging.getLogger(__name__)

_MYSQL_POOLS = {}

def get_db_connection(config=None):
    """
    Conexión dinámica. Usa mektia/sin pass (SSH style) 
    o Mektia#2025 si es necesario.
    """
    cfg = config if config else {}
    # Si no nos pasan DB, usamos 'clientes' para investigar
    db_name = cfg.get('db_name', 'clientes')
    db_host = cfg.get('db_host', 'localhost')
    user = 'mektia'
    passwords_to_try = ['', 'Mektia#2025']
    pool_key = f"{db_host}|{user}|{db_name}"
    if pool_key not in _MYSQL_POOLS:
        for pwd in passwords_to_try:
            try:
                # Intentamos crear el pool con la contraseña que funcione
                _MYSQL_POOLS[pool_key] = pooling.MySQLConnectionPool(
                    pool_name=f"p_{os.getpid()}_{db_name}"[:32],
                    pool_size=10,
                    host=db_host,
                    user=user,
                    password=pwd,
                    database=db_name,
                    charset='utf8mb4'
                )
                logger.info(f"✅ Pool creado con éxito para: {db_name}")
                break
            except Exception as e:
                if pwd == passwords_to_try[-1]:
                    logger.error(f"❌ Error total en {db_name}: {e}")
                    raise
    return _MYSQL_POOLS[pool_key].get_connection()
    
def get_cliente_by_subdomain(subdominio):
    """
    Busca automáticamente el nombre de la BD (shema) en la tabla maestra.
    """
    try:
        # 1. Conecta a la base 'clientes' que vimos en tu imagen
        conn = get_db_connection({'db_name': 'clientes'})
        cur = conn.cursor(dictionary=True)
        
        # 2. Busca el schema real (ej: 'unilova', 'ofitodo', 'mektia_db')
        query = """
            SELECT u.shema as db_name, c.wa_token, c.wa_phone_id, c.dominio 
            FROM usuarios u 
            JOIN cliente c ON u.id_cliente = c.id 
            WHERE c.dominio = %s OR u.shema = %s 
            LIMIT 1
        """
        cur.execute(query, (subdominio, subdominio))
        resultado = cur.fetchone()
        cur.close()
        conn.close()

        if resultado:
            # Agregamos los datos de conexión para que app.py los use
            resultado['db_host'] = 'localhost'
            resultado['db_user'] = 'mektia'
            # No mandamos password aquí para que get_db_connection use su lógica de 'passwords_to_try'
            return resultado
        return None
    except Exception as e:
        logger.error(f"⚠️ Error buscando subdominio {subdominio}: {e}")
        return None
