import mysql.connector

try:
    conn = mysql.connector.connect(
        host="163.192.142.226",
        port=3306,
        user="flaskuser",
        password="Mektia#2025",
        database="PlataformaIA"
    )
    print("Conexión exitosa")
    conn.close()
except mysql.connector.Error as err:
    print(f"❌ Error: {err}")
