import mysql.connector
import logging
import re

logger = logging.getLogger(__name__)

def buscar_productos(conn, query_texto):
    """
    MASTER FUNCTION V2: Motor de búsqueda unificado con ponderación multicapa.
    Centraliza SKU, Categorías, Modelos y Descripción.
    """
    try:
        q = query_texto.strip().lower()
        if not q:
            return "Por favor, escribe el nombre o SKU del producto."

        print(f"🚀 MASTER SEARCH: '{q}'")
        cur = conn.cursor(dictionary=True)

        # 1. Limpieza y Tokenización (Palabras clave)
        # Filtramos palabras comunes que ensucian la búsqueda
        stop_words = {'un', 'una', 'el', 'la', 'de', 'con', 'para', 'quiero', 'comprar', 'venden', 'tienen'}
        palabras = [p for p in q.split() if p not in stop_words and len(p) > 1]
        
        if not palabras:
            palabras = [q] # Fallback al texto completo

        # 2. Construcción de Ponderación (Scoring)
        # Esta lógica da puntos extra si el término aparece en lugares clave
        relevancia_parts = []
        where_parts = []
        params = []

        # PESOS DE PUNTUACIÓN
        # SKU Exacto: 500 pts | Modelo Exacto: 300 pts | SKU parcial: 100 pts | Desc parcial: 50 pts
        for p in palabras:
            term_like = f"%{p}%"
            
            relevancia_parts.append(f"""
                CASE 
                    WHEN LOWER(sku) = %s THEN 500
                    WHEN LOWER(modelo) = %s THEN 300
                    WHEN LOWER(categoria) LIKE %s THEN 150
                    WHEN LOWER(sku) LIKE %s THEN 100
                    WHEN LOWER(modelo) LIKE %s THEN 80
                    WHEN LOWER(descripcion) LIKE %s THEN 50
                    ELSE 0 
                END""")
            
            where_parts.append("(sku LIKE %s OR modelo LIKE %s OR descripcion LIKE %s OR categoria LIKE %s)")
            
            # 6 parámetros para el CASE y 4 para el WHERE por cada palabra
            params.extend([p, p, term_like, term_like, term_like, term_like])

        # Parámetros para la sección WHERE
        params_where = []
        for p in palabras:
            term_like = f"%{p}%"
            params_where.extend([term_like, term_like, term_like, term_like])

        sql = f"""
            SELECT sku, descripcion, precio_menudeo, moneda, imagen, modelo, categoria, subcategoria,
            ({' + '.join(relevancia_parts)}) AS score
            FROM precios
            WHERE ({' AND '.join(where_parts)})
            AND (status_ws IS NULL OR status_ws = 'activo' OR status_ws = ' ' OR status_ws = '1')
            HAVING score > 0
            ORDER BY score DESC
            LIMIT 12
        """

        cur.execute(sql, params + params_where)
        resultados = cur.fetchall()

        # 3. Lógica de Decisión Post-Búsqueda
        if not resultados:
            cur.close()
            return "No encontré resultados exactos. ¿Podrías darme más detalles o el SKU?"

        # Filtro de Calidad (Umbral)
        # Si el primer resultado es muy fuerte (ej. un SKU exacto), 
        # no mostramos "basura" que tenga un score muy bajo.
        max_score = resultados[0]['score']
        # Umbral dinámico: Solo lo que se parezca al menos al 60% del mejor resultado
        umbral = max_score * 0.6
        final_list = [r for r in resultados if r['score'] >= umbral][:4]

        cur.close()
        print(f"✅ Búsqueda finalizada. Top score: {max_score}. Mostrando: {len(final_list)}")

        # 4. Formatear para la IA
        # Enviamos un string limpio para que la IA decida cómo responderle al humano
        return str(final_list)

    except Exception as e:
        logger.error(f"❌ Error en Master Search: {e}")
        return "Error interno al buscar en el catálogo."

def derivar_a_asesor(motivo):
    return f"SOLICITUD DE ASESOR HUMANO: {motivo}"
