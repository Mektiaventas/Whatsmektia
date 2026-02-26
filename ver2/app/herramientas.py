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
    stopwords = {'quiero', 'necesito', 'busco', 'favor', 'precio', 'costo', 'para', 'con', 'del', 'los', 'las'}
    palabras = texto_norm.split()
    
    palabras_procesadas = []
    for p in palabras:
        if p in stopwords or len(p) < 3:
            continue
            
        # Lógica de Raíz (Stemming):
        # Si termina en 'es' (interiores -> interior) o 's' (cursos -> curso)
        # Quitamos la terminación para buscar la "raíz"
        if len(p) > 4:
            if p.endswith('es'):
                p = p[:-2]
            elif p.endswith('s'):
                p = p[:-1]
        
        palabras_procesadas.append(p)
        
    return palabras_procesadas

# --- LA FUNCIÓN PRINCIPAL QUE LLAMA LA IA ---
def buscar_productos(conn, query_texto):
    try:
        print(f"\n🔍 DEBUG: Iniciando búsqueda para: '{query_texto}'")
        # Aquí se usa la nueva función de "recortar palabras" (singular/plural)
        palabras = extraer_palabras_clave_inteligente(query_texto)
        if not palabras: return "[]"

        cur = conn.cursor(dictionary=True)
        
        # Columnas donde buscaremos
        columnas_busqueda = ['sku', 'categoria', 'descripcion', 'modelo', 'subcategoria']
        
        relevancia_parts = []
        params = []

        for idx, palabra in enumerate(palabras):
            p_like = f"%{palabra}%"
            # Prioridad a palabras clave técnicas
            fuerza = 200 if palabra.lower() in ['interior', 'micrometro', 'calibrador'] else 50
            
            case_parts = []
            for col in columnas_busqueda:
                bono = 100 if col in ['sku', 'categoria'] else 20
                case_parts.append(f"WHEN LOWER({col}) LIKE %s THEN {fuerza + bono}")
                params.append(p_like)
            
            relevancia_parts.append(f"CASE {' '.join(case_parts)} ELSE 0 END")

        # SQL con OR y el Stemming (palabras recortadas) hará que encuentre "interior" aunque busquen "interiores"
        sql = f"""
            SELECT sku, descripcion, categoria, precio_menudeo, moneda, ({' + '.join(relevancia_parts)}) AS score
            FROM precios
            WHERE (status_ws IS NULL OR status_ws IN ('activo', ' ', '1'))
            HAVING score > 0
            ORDER BY score DESC
            LIMIT 5
        """

        cur.execute(sql, params)
        resultados = cur.fetchall()
        cur.close()

        if not resultados:
            print("DEBUG: Cero resultados encontrados.")
            return "No hay existencias exactas. Sugiere hablar con un asesor."

        # --- AQUÍ ESTÁ EL CAMBIO DE LIMPIEZA PARA QUE LA IA NO SE MAREE ---
        resultados_cortos = []
        for r in resultados:
            resultados_cortos.append({
                "SKU": r['sku'],
                "Producto": r['descripcion'][:100] if r['descripcion'] else "Sin descripción",
                "Precio": f"{r['precio_menudeo']} {r['moneda']}"
            })
        
        payload = str(resultados_cortos)
        print(f"✅ DEBUG: Búsqueda exitosa. Enviando {len(resultados_cortos)} productos.")
        return payload

    except Exception as e:
        print(f"❌ DEBUG ERROR en buscar_productos: {e}")
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
