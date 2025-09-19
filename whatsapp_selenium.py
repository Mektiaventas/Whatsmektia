# whatsapp_selenium.py
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time
import os
import base64
import logging

class WhatsAppSelenium:
    def __init__(self):
        self.driver = None
        self.is_logged_in = False
        self.setup_driver()
        
    def setup_driver(self):
        """Configura el driver de Chrome"""
        try:
            options = webdriver.ChromeOptions()
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
            options.add_argument('--user-data-dir=./whatsapp_profile')  # Para persistir sesión
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=options)
            logging.info("✅ Driver de Chrome configurado")
        except Exception as e:
            logging.error(f"❌ Error configurando driver: {e}")
            raise

    def login(self):
        """Inicia sesión en WhatsApp Web"""
        try:
            self.driver.get("https://web.whatsapp.com")
            logging.info("🌐 Abriendo WhatsApp Web...")
            
            # Esperar a que el usuario escanee el QR
            WebDriverWait(self.driver, 120).until(
                EC.presence_of_element_located((By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]'))
            )
            
            self.is_logged_in = True
            logging.info("✅ Sesión iniciada en WhatsApp Web")
            return True
            
        except Exception as e:
            logging.error(f"❌ Error iniciando sesión: {e}")
            return False

    def get_contact_info(self, phone_number):
        """Obtiene nombre e imagen de perfil de un contacto"""
        if not self.is_logged_in:
            if not self.login():
                return None, None
        
        try:
            # Buscar el contacto
            search_box = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]'))
            )
            
            search_box.clear()
            search_box.send_keys(phone_number)
            time.sleep(2)  # Esperar resultados de búsqueda
            
            # Intentar hacer click en el resultado
            try:
                contact_result = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, f'//span[@title="{phone_number}"]'))
                )
                contact_result.click()
            except:
                # Buscar por número sin formato
                contact_result = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, '//span[contains(@title, "+")]'))
                )
                contact_result.click()
            
            time.sleep(3)  # Esperar a que cargue el chat
            
            # Obtener nombre del perfil
            try:
                profile_name = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, '//header//span[@title]'))
                ).get_attribute('title')
            except:
                profile_name = phone_number  # Fallback al número
            
            # Obtener imagen de perfil
            profile_image = None
            try:
                # Hacer click en el header para abrir info de contacto
                header = WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable((By.XPATH, '//header'))
                )
                header.click()
                time.sleep(2)
                
                # Esperar a que aparezca la imagen de perfil grande
                profile_img_element = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, '//header//img[@src]'))
                )
                
                # Obtener la URL de la imagen
                profile_image = profile_img_element.get_attribute('src')
                
                # Cerrar la vista de información
                close_btn = self.driver.find_element(By.XPATH, '//span[@data-icon="x"]')
                close_btn.click()
                
            except Exception as e:
                logging.warning(f"⚠️ No se pudo obtener imagen para {phone_number}: {e}")
                profile_image = None
            
            # Limpiar la búsqueda
            search_box = self.driver.find_element(By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]')
            search_box.clear()
            search_box.send_keys(Keys.ESCAPE)
            
            logging.info(f"✅ Información obtenida para {phone_number}: {profile_name}")
            return profile_name, profile_image
            
        except Exception as e:
            logging.error(f"❌ Error obteniendo info de {phone_number}: {e}")
            return None, None

    def close(self):
        """Cierra el navegador"""
        if self.driver:
            self.driver.quit()
            logging.info("✅ Navegador cerrado")

# Singleton para reutilizar la misma instancia
whatsapp_client = None

def get_whatsapp_client():
    global whatsapp_client
    if whatsapp_client is None:
        whatsapp_client = WhatsAppSelenium()
    return whatsapp_client