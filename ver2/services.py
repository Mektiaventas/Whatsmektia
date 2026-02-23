import mysql.connector
from mysql.connector import pooling
from ver2.configuracion import Config

class DatabaseManager:
    _pools = {}

    @classmethod
    def get_pool(cls, db_name, user, password, host):
        """Crea o recupera un pool de conexiones para una DB específica."""
        pool_name = f"pool_{db_name}"
        if pool_name not in cls._pools:
            cls._pools[pool_name] = mysql.connector.pooling.MySQLConnectionPool(
                pool_name=pool_name,
                pool_size=5,  # Mantiene 5 conexiones listas para usar
                host=host,
                user=user,
                password=password,
                database=db_name
            )
        return cls._pools[pool_name]

    @classmethod
    def get_connection(cls, db_config):
        """Obtiene una conexión activa del pool correspondiente."""
        pool = cls.get_pool(
            db_config['db_name'],
            db_config['db_user'],
            db_config['db_pass'],
            db_config['db_host']
        )
        return pool.get_connection()

def get_db_master():
    """Conexión rápida a la base de datos de control de clientes."""
    master_config = {
        'db_name': Config.CLIENTES_DB_NAME,
        'db_user': Config.CLIENTES_DB_USER,
        'db_pass': Config.CLIENTES_DB_PASSWORD,
        'db_host': Config.CLIENTES_DB_HOST
    }
    return DatabaseManager.get_connection(master_config)

def get_tenant_by_domain(dominio):
    """
    Busca en la tabla 'cliente' de la DB maestra la configuración 
    específica según el dominio o subdominio.
    """
    conn = get_db_master()
    cursor = conn.cursor(dictionary=True)
    try:
        query = "SELECT * FROM cliente WHERE dominio = %s OR usuario = %s"
        cursor.execute(query, (dominio, dominio))
        result = cursor.fetchone()
        return result
    finally:
        cursor.close()
        conn.close() # Devuelve la conexión al pool
