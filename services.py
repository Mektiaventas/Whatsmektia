import os
import logging
import time
import mysql.connector
from mysql.connector import pooling

logger = logging.getLogger(__name__)

# Module-level pool cache
_MYSQL_POOLS = {}

def get_clientes_conn():
    """
    Connect to the *CLIENTES* database (auth / clients DB).
    """
    try:
        return mysql.connector.connect(
            host=os.getenv("CLIENTES_DB_HOST", "localhost"),
            user=os.getenv("CLIENTES_DB_USER", "mektia"),
            password=os.getenv("CLIENTES_DB_PASSWORD", ""),
            database=os.getenv("CLIENTES_DB_NAME", "clientes"),
            charset='utf8mb4'
        )
    except Exception as e:
        logger.error(f"❌ get_clientes_conn error: {e}")
        raise

def get_cliente_by_subdomain(subdominio):
    """
    Busca al cliente y devuelve el diccionario de configuración.
    """
    try:
        conn = get_clientes_conn()
        cur = conn.cursor(dictionary=True)
        
        query = """
            SELECT 
                u.user as db_user, 
                u.password as db_password, 
                u.shema as db_name,
                c.wa_token as whatsapp_token, 
                c.wa_phone_id as phone_number_id, 
                c.wa_verify_token as verify_token, 
                c.dominio as subdominio_actual
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
            resultado['db_host'] = os.getenv('DB_HOST', 'localhost')
            return resultado
            
        return None
    except Exception as e:
        logger.error(f"❌ Error en get_cliente_by_subdomain: {e}")
        return None

def get_db_connection(config=None):
    """
    Get a DB connection using a pool or direct connection.
    """
    if config is None:
        config = {
            'db_host': os.getenv('DB_HOST', 'localhost'),
            'db_user': 'mektia',
            'db_password': '',
            'db_name': 'mektia'
        }

    pool_key = f"{config.get('db_host')}|{config.get('db_user')}|{config.get('db_name')}"

    try:
        if pool_key not in _MYSQL_POOLS:
            POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
            _MYSQL_POOLS[pool_key] = pooling.MySQLConnectionPool(
                pool_name=f"pool_{config.get('db_name')}",
                pool_size=POOL_SIZE,
                host=config['db_host'],
                user=config['db_user'],
                password=config['db_password'],
                database=config['db_name'],
                charset='utf8mb4'
            )
        return _MYSQL_POOLS[pool_key].get_connection()
    except Exception as pool_err:
        logger.warning(f"⚠️ Fallback to direct connect: {pool_err}")
        return mysql.connector.connect(
            host=config.get('db_host', 'localhost'),
            user=config.get('db_user', 'mektia'),
            password=config.get('db_password', ''),
            database=config.get('db_name', ''),
            charset='utf8mb4'
        )

def _ensure_precios_subscription_columns(config=None):
    try:
        conn = get_db_connection(config)
        cur = conn.cursor()
        cur.execute("SHOW COLUMNS FROM precios LIKE 'inscripcion'")
        if cur.fetchone() is None:
            cur.execute("ALTER TABLE precios ADD COLUMN inscripcion DECIMAL(10,2) DEFAULT 0.00")
        cur.execute("SHOW COLUMNS FROM precios LIKE 'mensualidad'")
        if cur.fetchone() is None:
            cur.execute("ALTER TABLE precios ADD COLUMN mensualidad DECIMAL(10,2) DEFAULT 0.00")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning(f"⚠️ _ensure_precios_subscription_columns failed: {e}")
