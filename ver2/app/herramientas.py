import mysql.connector
import re
import unicodedata
import logging

logger = logging.getLogger(__name__)

# --- TUS FUNCIONES DE APOYO (RESCATADAS) ---
def normalizar_texto_busqueda(texto):
    if not texto: return ""
    texto = texto.lower()
    texto = ''.join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    texto = re.sub(r'[^a-z0-9\s\-]', ' ', texto)
    return ' '.join(texto.split()).strip()

def extraer_palabras_clave_inteligente(texto):
    texto_norm = normalizar_texto_busqueda(texto)
    stopwords = {
        'me', 'puedes', 'pueden', 'puede', 'podria', 'podrias', 'quiero', 'quiere', 'quisiera', 
        'necesito', 'necesita', 'busco', 'buscas', 'busca', 'recomendar', 'recomiendan',
        'mostrar', 'muestra', 'ver', 'tengo', 'tiene', 'hay', 'tienes', 'tenemos', 'favor', 
        'gracias', 'por', 'para', 'con', 'sin', 'de', 'del', 'en', 'un', 'una', 'el', 'la', 
        'mandas', 'manda', 'envia', 'envias', 'imagen', 'foto', 'precio', 'costo', 'cuanto'
    }
    palabras = texto_norm.split()
    return [p for p in palabras if any(c.isdigit() for c in p) or (p not in stopwords and len(p) > 2)]

# --- LA FUNCIÓN PRINCIPAL QUE LLAMA LA IA ---
def buscar_productos(conn, query_texto):
    try:
        print(f"🚀 INICIANDO MASTER SEARCH V2: '{query_texto}'")
        
        # 1. ANALISIS INICIAL
        palabras_clave = extraer_palabras_clave_inteligente(query_texto)
        if not palabras_clave:
            return "No detecté términos de búsqueda claros. ¿Qué equipo buscas?"

        cur = conn.cursor(dictionary=True)
        
        # 2. PRIORIDAD 1: BÚSQUEDA POR SKU EXACTO
        # (Si el usuario pega un código, no queremos que la IA divague)
        cur.execute("SELECT * FROM precios WHERE UPPER(sku) = %s LIMIT 1", (query_texto.strip().upper(),))
        exacto = cur.fetchone()
        if exacto:
            cur.close()
            return str([exacto])

        # 3. PRIORIDAD 2: BÚSQUEDA MULTICAPA CON PONDERACIÓN (TU MAGIA)
        relevancia_parts = []
        where_parts = []
        params = []

        for idx, palabra in enumerate(palabras_clave):
            p_like = f"%{palabra}%"
            peso = 100 - (idx * 10) # La primera palabra es la más importante
            
            relevancia_parts.append(f"""
                CASE 
                    WHEN LOWER(sku) = %s THEN {peso + 100}
                    WHEN LOWER(categoria) LIKE %s THEN {peso + 50}
                    WHEN LOWER(subcategoria) LIKE %s THEN {peso + 40}
                    WHEN LOWER(modelo) LIKE %s THEN {peso + 30}
                    WHEN LOWER(descripcion) LIKE %s THEN {peso}
                    ELSE 0 
                END""")
            
            where_parts.append("(categoria LIKE %s OR subcategoria LIKE %s OR modelo LIKE %s OR sku LIKE %s OR descripcion LIKE %s)")
            # 5 params para el CASE, 5 para el WHERE
            params.extend([palabra, p_like, p_like, p_like, p_like])

        # Construir SQL Final
        sql = f"""
            SELECT *, ({' + '.join(relevancia_parts)}) AS score
            FROM precios
            WHERE ({' AND '.join(where_parts)})
            AND (status_ws IS NULL OR status_ws IN ('activo', ' ', '1'))
            ORDER BY score DESC
            LIMIT 15
        """
        
        # Duplicamos params (una tanda para el SELECT de score y otra para el WHERE)
        params_where = []
        for p in palabras_clave:
            params_where.extend([f"%{p}%"] * 5)
            
        cur.execute(sql, params + params_where)
        resultados = cur.fetchall()

        # 4. FILTRO DE CALIDAD (UMBRAL 90% - PASO 6 DE TU V1)
        if resultados:
            max_score = resultados[0].get('score', 0)
            umbral = max_score * 0.9
            resultados = [r for r in resultados if r.get('score', 0) >= umbral]
            resultados = resultados[:3] # Máximo 3 para WhatsApp

        cur.close()

        if not resultados:
            return "No encontré productos con esos términos exactos."

        return str(resultados)

    except Exception as e:
        logger.error(f"🔴 Error Master Search: {e}")
        return "[]"
def derivar_a_asesor(conn, motivo=None):
    """
    Función para que la IA transfiera el control a un humano.
    Busca los asesores disponibles en la tabla de configuración.
    """
    try:
        cur = conn.cursor(dictionary=True)
        # Obtenemos los datos de los asesores de la configuración
        cur.execute("SELECT asesor1_nombre, asesor1_telefono, asesor2_nombre, asesor2_telefono FROM configuracion LIMIT 1")
        config = cur.fetchone()
        cur.close()

        if config:
            msg = (
                f"Entiendo. He solicitado el apoyo de un asesor técnico.\n\n"
                f"👨‍💻 *{config['asesor1_nombre']}* ({config['asesor1_telefono']}) o "
                f"👩‍💻 *{config['asesor2_nombre']}* ({config['asesor2_telefono']}) "
                f"se pondrán en contacto contigo a la brevedad."
            )
            # Aquí podrías agregar lógica para marcar la conversación como 'atendida_por_humano' en la DB
            return msg
        
        return "He notificado a mis compañeros humanos, pronto te atenderán."

    except Exception as e:
        logger.error(f"❌ Error al derivar a asesor: {e}")
        return "Hubo un problema al contactar al asesor, pero ya he dejado el aviso."
