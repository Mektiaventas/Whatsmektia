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
        print(f"\n🔍 DEBUG: Iniciando búsqueda para: '{query_texto}'")
        palabras = extraer_palabras_clave_inteligente(query_texto)
        if not palabras: 
            print("DEBUG: No se extrajeron palabras clave.")
            return "[]"

        cur = conn.cursor(dictionary=True)
        cur.execute("SHOW COLUMNS FROM precios")
        columnas = [col['Field'] for col in cur.fetchall()]
        
        columnas_ignorar = {'id', 'status_ws', 'creado_en', 'actualizado_en', 'id_tenant'}
        columnas_busqueda = [c for c in columnas if c not in columnas_ignorar]

        relevancia_parts = []
        where_parts = []
        params = []

        for idx, palabra in enumerate(palabras):
            p_like = f"%{palabra}%"
            peso = 100 - (idx * 10)
            case_parts = []
            for col in columnas_busqueda:
                bono = 50 if col.lower() in ['sku', 'modelo', 'codigo'] else 0
                case_parts.append(f"WHEN LOWER({col}) LIKE %s THEN {peso + bono}")
                params.append(p_like)
            
            relevancia_parts.append(f"CASE {' '.join(case_parts)} ELSE 0 END")
            where_parts.append(f"({' OR '.join([f'LOWER({c}) LIKE %s' for c in columnas_busqueda])})")
            params.extend([p_like] * len(columnas_busqueda))

        # CAMBIO: Bajamos LIMIT a 5 para evitar que la IA se atore
        # CAMBIO: Usamos OR en lugar de AND para no ser estrictos
        # Y ordenamos por el score que ya calculamos arriba
        sql = f"""
            SELECT *, ({' + '.join(relevancia_parts)}) AS score
            FROM precios
            WHERE ({' OR '.join(where_parts)})
            AND (status_ws IS NULL OR status_ws IN ('activo', ' ', '1'))
            ORDER BY score DESC
            LIMIT 5
        """
        cur.execute(sql, params)
        resultados = cur.fetchall()

        resultados_limpios = []
        for res in resultados:
            item = {}
            for k, v in res.items():
                if v and k not in columnas_ignorar and k != 'score':
                    val_str = str(v)
                    # Recortamos a 80 caracteres para que el JSON sea ligero
                    item[k] = val_str[:80] + "..." if len(val_str) > 85 else v
            resultados_limpios.append(item)

        cur.close()

        if not resultados_limpios:
            print("DEBUG: Cero resultados. Enviando respuesta amigable formateada.")
            # Le mandamos un objeto que la IA entienda como "No hay, pero ofrece ayuda"
            return "[{'resultado': 'sin_existencias', 'aviso': 'No se encontraron calibradores de interiores de 150mm. Sugiere contactar a un asesor o preguntar por otro modelo.'}]"

        payload = str(resultados_limpios)
        print(f"✅ DEBUG: Búsqueda exitosa. Enviando {len(resultados_limpios)} productos. Tamaño: {len(payload)} chars")
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
