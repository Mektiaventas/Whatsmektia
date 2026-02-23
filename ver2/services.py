import os
import logging
import mysql.connector
from mysql.connector import pooling
from ver2.configuracion import Config

logger = logging.getLogger(__name__)

# Mantenemos tu diccionario de pools global para persistencia entre peticiones
_MYSQL_POOLS = {}

def get_db_connection(config=None):
    """
    Versión evolucionada de tu función original.
    Ahora toma credenciales dinámicas de la clase Config.
    """
    cfg = config if config else {}
    
    # Prioridad: 1. Lo que pase la función | 2. Config global | 3. Default
    db_name = cfg.get('db_name', Config.CLIENTES_DB_NAME)
    db_host = cfg.get('db_host', Config.CLIENTES_DB_HOST)
    user    = cfg.get('db_user', Config.CLIENTES_DB_USER)
    password = cfg.get('db_pass', Config.CLIENTES_DB_PASSWORD)

    # Tu lógica de pool_key es excelente, la mantenemos
    pool_key = f"{db_host}|{user}|{db_name}"
    
    if pool_key not in _MYSQL_POOLS:
        try:
            # Rescatamos tu configuración de pool con charset para Emojis
            _MYSQL_POOLS[pool_key] = pooling.MySQLConnectionPool(
                pool_name=f"v2_{os.getpid()}_{db_name}"[:32],
                pool_size=15, # Subimos a 15 para mayor concurrencia en V2
                host=db_host,
                user=user,
                password=password,
                database=db_name,
                charset='utf8mb4',
                collation='utf8mb4_general_ci'
            )
            logger.info(f"✅ V2: Pool creado para BD: {db_name}")
        except Exception as e:
            logger.error(f"❌ V2: Error en Pool para {db_name}: {e}")
            raise
            
    return _MYSQL_POOLS[pool_key].get_connection()

def get_cliente_by_subdomain(subdominio):
    """
    Rescata tu consulta original pero apuntando a la arquitectura V2.
    """
    try:
        # Forzamos conexión a la DB maestra usando la nueva función
        conn = get_db_connection({'db_name': Config.CLIENTES_DB_NAME})
        cur = conn.cursor(dictionary=True)
        
        query = """
            SELECT 
                id,
                dominio as db_name, 
                wa_token, 
                wa_phone_id, 
                wa_verify_token,
                '127.0.0.1' as db_host
            FROM cliente 
            WHERE dominio = %s OR usuario = %s LIMIT 1
        """
        cur.execute(query, (subdominio, subdominio))
        res = cur.fetchone()
        
        cur.close()
        conn.close() # Importante: devuelve al pool
        return res
    except Exception as e:
        logger.error(f"⚠️ V2: Error consultando maestro: {e}")
        return None
