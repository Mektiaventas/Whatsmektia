import os
import base64
import requests
import mysql.connector
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_USER = os.getenv("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD", "admin")
DB_NAME = os.getenv("DB_NAME", "PlataformaIA_CIEA_DB")
SESSION_DIR = "whatsapp_session"

def guardar_avatar_en_db(numero, base64_avatar):
    conn = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    cursor = conn.cursor()
    query = "UPDATE contactos_wa SET avatar_base64 = %s WHERE numero = %s"
    cursor.execute(query, (base64_avatar, numero))
    conn.commit()
    cursor.close()
    conn.close()

def buscar_contacto_y_obtener_avatar(page, numero):
    try:
        # Buscar contacto
        search_box = page.locator('div[title="Buscar o empezar un chat nuevo"]')
        search_box.click()
        search_box.fill(numero)
        page.wait_for_timeout(3000)

        # Seleccionar el contacto
        contact = page.locator(f'text="{numero}"').first
        contact.click()
        page.wait_for_timeout(2000)

        # Abrir perfil
        page.locator('header').locator('button').nth(2).click()
        page.wait_for_timeout(3000)

        # Obtener imagen
        img = page.locator('img[alt="avatar"]')
        img_url = img.get_attribute("src")

        if img_url and "blob:" not in img_url:
            response = requests.get(img_url)
            avatar_base64 = base64.b64encode(response.content).decode("utf-8")
            return avatar_base64
        else:
            print("⚠️ No se encontró imagen de perfil.")
            return None
    except Exception as e:
        print(f"❌ Error al obtener avatar de {numero}: {e}")
        return None

def fetch_and_save_avatar(numero):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(storage_state=f"{SESSION_DIR}/state.json")
        page = context.new_page()
        page.goto("https://web.whatsapp.com/")
        page.wait_for_timeout(6000)

        avatar = buscar_contacto_y_obtener_avatar(page, numero)
        if avatar:
            guardar_avatar_en_db(numero, avatar)
            print(f"✅ Avatar guardado en DB para {numero}")
        else:
            print(f"⚠️ No se pudo guardar avatar para {numero}")

        browser.close()

# --- PRUEBA DIRECTA (opcional) ---
if __name__ == "__main__":
    numero = input("Número a buscar (con código país): ")
    fetch_and_save_avatar(numero)
