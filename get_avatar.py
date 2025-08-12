import time
import os
import mysql.connector
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

# ---------- CONFIGURACIÓN ----------
DB_HOST = "127.0.0.1"
DB_USER = "flaskuser"
DB_PASSWORD = "Mektia#2025"
DB_NAME = "PlataformaIA"
TABLE_NAME = "contactos"  # Cambia por tu tabla real

CHROME_PROFILE_PATH = os.path.join(os.getcwd(), "whatsapp_session")
PHONE_NUMBER = "5214491281690"  # Número a buscar

# ---------- CONEXIÓN MYSQL ----------
def save_image_url(phone_number, image_url):
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    cursor = conn.cursor()

    query = f"""
    INSERT INTO {TABLE_NAME} (numero_telefono, imagen_url)
    VALUES (%s, %s)
    ON DUPLICATE KEY UPDATE imagen_url = VALUES(imagen_url)
    """
    cursor.execute(query, (phone_number, image_url))
    conn.commit()

    print(f"✅ Imagen guardada o actualizada en DB para {phone_number}")

    cursor.close()
    conn.close()


# ---------- INICIO SELENIUM ----------
options = Options()
options.add_argument(f"user-data-dir={CHROME_PROFILE_PATH}")
options.add_experimental_option("detach", True)  # Mantener abierto
driver = webdriver.Chrome(options=options)

driver.get("https://web.whatsapp.com/")
print("⏳ Esperando que WhatsApp Web cargue...")

# Espera inicial para cargar sesión
time.sleep(15)

# ---------- BUSCAR NÚMERO ----------
search_box = driver.find_element(By.XPATH, '//div[@title="Buscar o empezar un chat nuevo"]')
search_box.click()
time.sleep(1)
search_box.send_keys(PHONE_NUMBER)
time.sleep(3)
search_box.send_keys(Keys.ENTER)
time.sleep(2)

# ---------- ABRIR PERFIL ----------
header = driver.find_element(By.XPATH, '//header')
header.click()
time.sleep(2)

# ---------- OBTENER URL FOTO ----------
try:
    img_element = driver.find_element(By.XPATH, '//div[@role="button"]//img')
    image_url = img_element.get_attribute("src")
    print(f"📷 URL obtenida: {image_url}")

    save_image_url(PHONE_NUMBER, image_url)

except Exception as e:
    print("❌ No se pudo obtener la imagen:", e)

time.sleep(3)
driver.quit()
