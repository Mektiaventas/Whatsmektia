import mysql.connector

def buscar_productos(conn, query_texto):
    """
    Busca productos en la tabla precios.
    """
    print(f"🔍 BUSCANDO EN DB: {query_texto}")
    
    cur = conn.cursor(dictionary=True)
    
    # Limpiamos el texto y lo dividimos en palabras
    palabras = query_texto.split()
    
    # Esta es la consulta a la base de datos
    sql = "SELECT sku, descripcion, precio_menudeo, moneda FROM precios WHERE "
    condiciones = []
    valores = []
    
    for p in palabras:
        if len(p) > 2: # Solo buscamos palabras de más de 2 letras
            condiciones.append("(descripcion LIKE %s OR sku LIKE %s OR categoria LIKE %s)")
            val = f"%{p}%"
            valores.extend([val, val, val])
    
    # Si no hay palabras válidas, abortamos
    if not condiciones:
        return "No se encontraron términos de búsqueda válidos."

    sql += " AND ".join(condiciones) + " LIMIT 8"
    
    cur.execute(sql, valores)
    resultados = cur.fetchall()
    cur.close()
    
    print(f"📦 RESULTADOS ENCONTRADOS: {len(resultados)}")
    
    if not resultados:
        return "No se encontraron productos en el catálogo con esos términos."
    
    # Convertimos la lista de productos en un texto que la IA entienda
    return str(resultados)

def derivar_a_asesor(motivo):
    return f"SOLICITUD DE ASESOR HUMANO: {motivo}"
