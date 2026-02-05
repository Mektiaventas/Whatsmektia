import os
import mysql.connector
from dotenv import load_dotenv

load_dotenv()

def limpiar_adjuntos_fantasma():
    # Conexión a la base de datos (ajusta con tus variables de entorno)
    db = mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database="ofitodo" # Lo haremos para ofitodo que es donde salieron los errores
    )
    cursor = db.cursor(dictionary=True)

    # 1. Buscar mensajes que tienen algo en la columna 'archivo'
    cursor.execute("SELECT id, archivo FROM mensajes WHERE archivo IS NOT NULL AND archivo != ''")
    mensajes = cursor.fetchall()

    borrados = 0
    for m in mensajes:
        ruta_archivo = os.path.join("/home/ubuntu/Whatsmektia", m['archivo'].lstrip('/'))
        
        # Si el registro dice que hay un archivo pero físicamente NO está
        if not os.path.exists(ruta_archivo):
            print(f"❌ Archivo no encontrado: {ruta_archivo}. Limpiando registro ID: {m['id']}")
            cursor.execute("UPDATE mensajes SET archivo = NULL WHERE id = %s", (m['id'],))
            borrados += 1

    db.commit()
    print(f"\n✅ Limpieza terminada. Se sanearon {borrados} registros en 'ofitodo'.")
    cursor.close()
    db.close()

if __name__ == "__main__":
    limpiar_adjuntos_fantasma()
