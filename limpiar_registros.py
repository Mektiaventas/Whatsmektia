import mysql.connector

def limpiar_todo():
    # Configuración de acceso
    config = {
        'host': '127.0.0.1',
        'user': 'mektia',
        'password': 'Mektia#2025'
    }
    
    # Lista de bases de datos a limpiar
    bases_de_datos = ['ofitodo', 'unilova']
    
    for bd in bases_de_datos:
        print(f"--- Procesando base de datos: {bd} ---")
        try:
            # Conexión
            conn = mysql.connector.connect(**config, database=bd)
            cursor = conn.cursor()

            # Query para limpiar registros que buscan audios donde no hay
            query = "UPDATE mensajes SET archivo = NULL WHERE archivo LIKE '%uploads/audios/%'"
            cursor.execute(query)
            
            filas = cursor.rowcount
            conn.commit()
            
            print(f"✅ Éxito: Se limpiaron {filas} registros fantasma en {bd}.")
            
            cursor.close()
            conn.close()
        except mysql.connector.Error as err:
            print(f"❌ Error en {bd}: {err}")
        print("\n")

if __name__ == "__main__":
    limpiar_todo()
