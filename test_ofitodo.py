# test_ofitodo_only.py
import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

def test_connection():
    print("🔍 Probando conexión a OFITODO...")
    print(f"Host: {os.getenv('FITO_DB_HOST')}")
    print(f"User: {os.getenv('FITO_DB_USER')}")
    print(f"DB: {os.getenv('FITO_DB_NAME')}")
    print(f"Password length: {len(os.getenv('FITO_DB_PASSWORD', ''))}")
    
    try:
        conn = mysql.connector.connect(
            host=os.getenv("FITO_DB_HOST"),
            user=os.getenv("FITO_DB_USER"),
            password=os.getenv("FITO_DB_PASSWORD"),
            database=os.getenv("FITO_DB_NAME")
        )
        print("✅ Conexión EXITOSA")
        
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        print(f"📊 Tablas encontradas: {len(tables)}")
        for table in tables:
            print(f"   - {table[0]}")
        
        cursor.close()
        conn.close()
        return True
        
    except mysql.connector.Error as e:
        print(f"❌ Error MySQL: {e}")
        return False
    except Exception as e:
        print(f"❌ Error general: {e}")
        return False

if __name__ == "__main__":
    test_connection()