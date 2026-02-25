import mysql.connector

def buscar_productos(conn, query_texto):
    """
    Esta función hace una búsqueda inteligente en la tabla precios.
    Filtra por SKU o Descripción para no saturar a la IA.
    """
    cur = conn.cursor(dictionary=True)
    # Limpiamos el texto para evitar caracteres raros
    terminos = query_texto.split()
    
    # Construimos una búsqueda flexible
    sql = "SELECT sku, categoria, descripcion, precio_menudeo, moneda FROM precios WHERE "
    condiciones = []
    valores = []
    
    for t in terminos:
        condiciones.append("(descripcion LIKE %s OR sku LIKE %s OR categoria LIKE %s)")
        val = f"%{t}%"
        valores.extend([val, val, val])
    
    sql += " AND ".join(condiciones) + " LIMIT 8" # Limitamos a 8 para no saturar
    
    cur.execute(sql, valores)
    resultados = cur.fetchall()
    cur.close()
    
    if not resultados:
        return "No se encontraron productos exactos con esos términos."
    
    return str(resultados)

def derivar_a_asesor(motivo):
    """Marca la conversación para que un humano intervenga."""
    return f"Se ha solicitado la intervención de un asesor humano por: {motivo}"
