import os
import time
import json
import mysql.connector
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import NoSuchElementException, WebDriverException

# ---------- CONFIGURACIÓN ----------
DB_HOST = "127.0.0.1"
DB_USER = "flaskuser"
DB_PASSWORD = "Mektia#2025"
DB_NAME = "PlataformaIA"
TABLE_NAME = "contactos"

COOKIES_FILE = os.path.join(os.getcwd(), "cookies.json")
PHONE_NUMBER = "5214491182201"  # Número con el que nos conectamos
SEARCH_NUMBER = "5214812372326"  # Número al que buscamos foto

# ---------- CONEXIÓN MYSQL ----------
def get_last_avatar_update(phone_number):
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    cursor = conn.cursor()
    query = f"""
        SELECT avatar_actualizado_en FROM {TABLE_NAME}
        WHERE numero_telefono = %s
        LIMIT 1
    """
    cursor.execute(query, (phone_number,))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    if result and result[0]:
        return result[0]
    return None

def update_avatar_info(phone_number, image_url):
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    cursor = conn.cursor()
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    query = f"""
        UPDATE {TABLE_NAME}
        SET imagen_url = %s, avatar_actualizado_en = %s
        WHERE numero_telefono = %s
    """
    cursor.execute(query, (image_url, now_str, phone_number))
    conn.commit()
    cursor.close()
    conn.close()
    print(f"✅ Foto y fecha actualizadas en DB para {phone_number}")

# ---------- INICIO SELENIUM ----------
def start_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option("detach", False)
    driver = webdriver.Chrome(options=options)
    driver.get("https://web.whatsapp.com/")
    time.sleep(5)
    return driver

def login_whatsapp(driver):
    if os.path.exists(COOKIES_FILE):
        print("📂 Intentando iniciar sesión con cookies...")
        try:
            with open(COOKIES_FILE, "r") as f:
                cookies = json.load(f)
            for cookie in cookies:
                driver.add_cookie(cookie)
            driver.refresh()
            time.sleep(8)
            # Verificar si carga la barra de búsqueda
            driver.find_element(By.XPATH, '//div[@title="Buscar o empezar un chat nuevo"]')
            print("✅ Sesión restaurada con éxito.")
            return True
        except (NoSuchElementException, WebDriverException):
            print("⚠️ Cookies inválidas o caducadas. Se pedirá QR.")
            os.remove(COOKIES_FILE)

    # Si no hay cookies o están mal, pedir QR
    print("📷 Escanea el QR de WhatsApp Web en el navegador...")
    input("Presiona ENTER cuando hayas escaneado el QR y WhatsApp Web esté listo...")
    cookies = driver.get_cookies()
    with open(COOKIES_FILE, "w") as f:
        json.dump(cookies, f)
    print("💾 Nueva sesión guardada en cookies.json")
    return True

def search_and_get_image(driver, phone_number):
    search_box = driver.find_element(By.XPATH, '//div[@title="Buscar o empezar un chat nuevo"]')
    search_box.click()
    time.sleep(1)
    search_box.send_keys(phone_number)
    time.sleep(3)
    search_box.send_keys(Keys.ENTER)
    time.sleep(2)

    # Abrir perfil
    header = driver.find_element(By.XPATH, '//header')
    header.click()
    time.sleep(2)

    # Obtener URL de foto
    try:
        img_element = driver.find_element(By.XPATH, '//div[@role="button"]//img')
        image_url = img_element.get_attribute("src")
        print(f"📷 URL obtenida: {image_url}")
        return image_url
    except Exception as e:
        print("❌ No se pudo obtener la imagen:", e)
        return None

if __name__ == "__main__":
    # Verificamos si debemos actualizar (28 días)
    last_update = get_last_avatar_update(SEARCH_NUMBER)
    update_needed = True
    if last_update:
        if isinstance(last_update, str):
            # Por si es string, parseamos a datetime
            try:
                last_update = datetime.strptime(last_update, "%Y-%m-%d %H:%M:%S")
            except:
                last_update = None
        if last_update:
            dias_pasados = (datetime.now() - last_update).days
            print(f"Última actualización avatar: {last_update} ({dias_pasados} días atrás)")
            if dias_pasados < 28:
                print("🛑 La imagen se actualizó hace menos de 28 días. No se actualizará.")
                update_needed = False

    if update_needed:
        # Detectar si hay entorno gráfico
        has_display = os.getenv("DISPLAY") is not None or os.name == 'nt'  # Windows as GUI
        driver = start_driver(headless=not has_display)
        if login_whatsapp(driver):
            image_url = search_and_get_image(driver, SEARCH_NUMBER)
            if image_url:
                update_avatar_info(SEARCH_NUMBER, image_url)
        time.sleep(3)
        driver.quit()
    else:
        print("Proceso terminado sin actualizaciones.")

