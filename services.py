import os
import logging
import mysql.connector
from mysql.connector import pooling

logger = logging.getLogger(__name__)

# Cache de pools
_MYSQL_POOLS = {}

def get_db_connection(config=None):
    """
    Conexión automática. Si no hay base de datos especificada, 
    conecta al servidor y permite que el flujo continúe.
    """
    # 1. Extraer valores del config o usar defaults seguros
    # Si config es None, usamos un diccionario vacío para que .get() no falle
    cfg = config if config else {}
    db_host = cfg.get('db_host', 'localhost')
    # Si no hay db_name, conectamos sin base de datos (None) o a 'mysql' 
    # para evitar el error "Unknown database"
    db_name = cfg.get('db_name', None) 
    user = 'mektia'
    passwords_to_try = ['', 'Mektia#2025']
    
    # Si no hay nombre de BD, no usamos Pool (porque el pool requiere una BD fija)
    if not db_name:
        for pwd in passwords_to_try:
            try:
                return mysql.connector.connect(
                    host=db_host,
                    user=user,
                    password=pwd,
                    charset='utf8mb4'
                )
            except:
                continue
    # Si SÍ hay db_name, usamos el Pool que ya teníamos
    pool_key = f"{db_host}|{user}|{db_name}"
    if pool_key not in _MYSQL_POOLS:
        for pwd in passwords_to_try:
            try:
                _MYSQL_POOLS[pool_key] = pooling.MySQLConnectionPool(
                    pool_name=f"pool_{db_name}_{os.getpid()}",
                    pool_size=5,
                    host=db_host,
                    user=user,
                    password=pwd,
                    database=db_name
                )
                break # Logró crear el pool
            except:
                if pwd == passwords_to_try[-1]:
                    # Si falló con todos los passwords y BD, reintentamos sin BD
                    logger.error(f"❌ No se pudo conectar a la BD {db_name}")
                    raise
    return _MYSQL_POOLS[pool_key].get_connection()
def get_cliente_by_subdomain(subdominio):
    """Busca configuración usando el método de conexión robusto."""
    try:
        conn = get_db_connection({'db_name': 'clientes'})
        cur = conn.cursor(dictionary=True)
        
        query = """
            SELECT 
                u.shema as db_name,
                c.wa_token as whatsapp_token, 
                c.wa_phone_id as phone_number_id, 
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
            return resultado
        return None
    except Exception as e:
        logger.error(f"❌ Error en get_cliente_by_subdomain: {e}")
        return None
