import os
import logging
import mysql.connector
from mysql.connector import pooling

logger = logging.getLogger(__name__)

# Cache de pools
_MYSQL_POOLS = {}

def get_db_connection(config=None):
    """
    Intenta conectar como tú lo haces por SSH (sin password).
    Si falla, usa la credencial 'Mektia#2025'.
    """
    db_name = config.get('db_name', 'mektia') if config else 'mektia'
    db_host = config.get('db_host', 'localhost') if config else 'localhost'
    user = 'mektia'
    
    # Intentamos primero como tú entras por SSH (vacío)
    passwords_to_try = ['', 'Mektia#2025']
    
    pool_key = f"{db_host}|{user}|{db_name}"

    # Si ya tenemos un pool que funciona, lo usamos
    if pool_key in _MYSQL_POOLS:
        try:
            return _MYSQL_POOLS[pool_key].get_connection()
        except:
            del _MYSQL_POOLS[pool_key]

    # Si no hay pool o falló, probamos las contraseñas
    for pwd in passwords_to_try:
        try:
            conn = mysql.connector.connect(
                host=db_host,
                user=user,
                password=pwd,
                database=db_name,
                charset='utf8mb4',
                connect_timeout=2
            )
            # Si funcionó, creamos el pool con ESTA contraseña exitosa
            if pool_key not in _MYSQL_POOLS:
                _MYSQL_POOLS[pool_key] = pooling.MySQLConnectionPool(
                    pool_name=f"pool_{db_name}",
                    pool_size=5,
                    host=db_host,
                    user=user,
                    password=pwd,
                    database=db_name
                )
            return conn
        except mysql.connector.Error as err:
            if pwd == passwords_to_try[-1]: # Si ya es el último intento
                logger.error(f"❌ Fallo total de conexión a {db_name}: {err}")
                raise
            continue

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
