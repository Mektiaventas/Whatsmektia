import mysql.connector

def limpiar_conversaciones():
    # Configuración de acceso centralizada
    config = {
        'host': '127.0.0.1',
        'user': 'mektia',
        'password': 'Mektia#2025'
    }
    
    # Lista de tus bases de datos actuales
    bases_de_datos = ['ofitodo', 'unilova']
    
    for bd in bases_de_datos:
        print(f"--- 🔍 Procesando: {bd} ---")
        try:
            conn = mysql.connector.connect(**config, database=bd)
            cursor = conn.cursor()

            # Ajustamos a tu tabla 'conversaciones'
            # Ponemos en NULL la columna 'archivo' si apunta a la carpeta de audios
            query = "UPDATE conversaciones SET archivo = NULL WHERE archivo LIKE '%uploads/audios/%'"
            
            cursor.execute(query)
            filas_afectadas = cursor.rowcount
            conn.commit()
            
            print(f"✅ Saneado: {filas_afectadas} registros limpiados en la tabla 'conversaciones'.")
            
            cursor.close()
            conn.close()
        except mysql.connector.Error as err:
            print(f"❌ Error en {bd}: {err}")
        print("-" * 30 + "\n")

if __name__ == "__main__":
    limpiar_conversaciones()
