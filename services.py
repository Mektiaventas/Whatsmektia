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
    Reads env vars: CLIENTES_DB_HOST, CLIENTES_DB_USER, CLIENTES_DB_PASSWORD, CLIENTES_DB_NAME
    """
    try:
        return mysql.connector.connect(
            host=os.getenv("CLIENTES_DB_HOST"),
            user=os.getenv("CLIENTES_DB_USER"),
            password=os.getenv("CLIENTES_DB_PASSWORD"),
            database=os.getenv("CLIENTES_DB_NAME"),
            charset='utf8mb4'
        )
    except Exception as e:
        logger.error(f"❌ get_clientes_conn error: {e}")
        raise

def get_db_connection(config=None):
    """
    Get a DB connection using a small MySQLConnectionPool per tenant (cached).
    Falls back to direct mysql.connector.connect() if pooling fails.
    `config` is expected to be a dict with keys: db_host, db_user, db_password, db_name
    """
    if config is None:
        # Best-effort fallback if caller forgot to pass config
        config = {
            'db_host': os.getenv('DB_HOST', 'localhost'),
            'db_user': os.getenv('DB_USER', 'root'),
            'db_password': os.getenv('DB_PASSWORD', ''),
            'db_name': os.getenv('DB_NAME', '')
        }

    POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
    pool_key = f"{config.get('db_host')}|{config.get('db_user')}|{config.get('db_name')}"

    try:
        if pool_key not in _MYSQL_POOLS:
            logger.info(f"🔧 Creating MySQL pool for {config.get('db_name')} (size={POOL_SIZE})")
            _MYSQL_POOLS[pool_key] = pooling.MySQLConnectionPool(
                pool_name=f"pool_{config.get('db_name')}",
                pool_size=POOL_SIZE,
                host=config['db_host'],
                user=config['db_user'],
                password=config['db_password'],
                database=config['db_name'],
                charset='utf8mb4'
            )
        conn = _MYSQL_POOLS[pool_key].get_connection()
        try:
            if not conn.is_connected():
                conn.reconnect(attempts=2, delay=0.5)
        except Exception:
            pass
        logger.info(f"🗄️ Borrowed connection from pool for {config.get('db_name')}")
        return conn

    except Exception as pool_err:
        logger.warning(f"⚠️ MySQL pool error (fallback to direct connect): {pool_err}")
        try:
            conn = mysql.connector.connect(
                host=config.get('db_host', 'localhost'),
                user=config.get('db_user', 'root'),
                password=config.get('db_password', ''),
                database=config.get('db_name', ''),
                charset='utf8mb4'
            )
            logger.info(f"✅ Direct connection established to {config.get('db_name')}")
            return conn
        except Exception as e:
            logger.error(f"❌ Error connecting to DB {config.get('db_name')}: {e}")
            raise

# services.py

def get_cliente_by_subdomain(subdominio):
    """
    Busca al cliente y prepara el diccionario de configuración final.
    Centraliza la lógica para que app.py no tenga que 'retrabajar'.
    """
    try:
        conn = get_clientes_conn()
        cur = conn.cursor(dictionary=True)
        # Usamos ALIAS (as) para que coincidan con lo que pide get_db_connection
        query = """
            SELECT 
                u.id_cliente, 
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
            # Inyectamos el host aquí mismo
            resultado['db_host'] = os.getenv('DB_HOST', '127.0.0.1')
            return resultado
        return None
    except Exception as e:
        logger.error(f"❌ Error en get_cliente_by_subdomain: {e}")
        return None
        
def _ensure_precios_subscription_columns(config=None):
    """
    Ensure `precios` table has 'inscripcion' and 'mensualidad' columns.
    Safe to call repeatedly.
    """
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
        logger.info("🔧 Columnas 'inscripcion' y 'mensualidad' aseguradas en tabla precios")
    except Exception as e:
        logger.warning(f"⚠️ _ensure_precios_subscription_columns failed: {e}")
