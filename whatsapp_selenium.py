# whatsapp_selenium.py
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import os
import base64
import logging
import qrcode
from io import BytesIO
from flask import send_file

class WhatsAppSelenium:
    def __init__(self):
        self.driver = None
        self.is_logged_in = False
        self.qr_code = None
        self.qr_generated_time = None
        self.setup_driver()
        
    def setup_driver(self):
        """Configura el driver de Chrome para servidor"""
        try:
            chrome_options = Options()
            
            # Configuración para servidor headless (sin interfaz gráfica)
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
            chrome_options.add_argument('--user-data-dir=./whatsapp_profile')
            
            # Para evitar problemas de autenticación
            chrome_options.add_argument('--disable-web-security')
            chrome_options.add_argument('--allow-running-insecure-content')
            chrome_options.add_argument('--disable-extensions')
            chrome_options.add_argument('--disable-popup-blocking')
            
            service = Service(ChromeDriverManager().install())
            self.driver = webdriver.Chrome(service=service, options=chrome_options)
            logging.info("✅ Driver de Chrome configurado en modo headless")
        except Exception as e:
            logging.error(f"❌ Error configurando driver: {e}")
            raise

    def generate_qr_code(self):
        """Genera y muestra el código QR para escanear"""
        try:
            self.driver.get("https://web.whatsapp.com")
            logging.info("🌐 Abriendo WhatsApp Web...")
            
            # Esperar a que aparezca el QR
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.XPATH, '//canvas[@aria-label="Scan me!"]'))
            )
            
            # Obtener el elemento del QR
            qr_element = self.driver.find_element(By.XPATH, '//canvas[@aria-label="Scan me!"]')
            
            # Tomar screenshot del QR
            qr_screenshot = qr_element.screenshot_as_png
            
            # Crear código QR alternativo con información
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )
            qr.add_data("WhatsApp Web QR - Escanea para conectar")
            qr.make(fit=True)
            
            qr_img = qr.make_image(fill_color="black", back_color="white")
            buffered = BytesIO()
            qr_img.save(buffered, format="PNG")
            self.qr_code = base64.b64encode(buffered.getvalue()).decode()
            self.qr_generated_time = time.time()
            
            logging.info("✅ Código QR generado")
            return self.qr_code
            
        except Exception as e:
            logging.error(f"❌ Error generando QR: {e}")
            return None

    def check_login_status(self):
        """Verifica si el login fue exitoso"""
        try:
            # Verificar si estamos logueados buscando elementos de la app
            elements = self.driver.find_elements(By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]')
            if elements:
                self.is_logged_in = True
                self.qr_code = None  # Limpiar QR una vez logueado
                logging.info("✅ Login exitoso detectado")
                return True
            return False
        except:
            return False

    def wait_for_login(self, timeout=120):
        """Espera a que el usuario complete el login"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.check_login_status():
                return True
            
            # Verificar si el QR expiró (más de 2 minutos)
            if self.qr_generated_time and time.time() - self.qr_generated_time > 120:
                logging.info("🔄 QR expirado, generando nuevo...")
                self.generate_qr_code()
                
            time.sleep(5)
        
        return False

    def get_contact_info(self, phone_number):
        """Obtiene nombre e imagen de perfil de un contacto"""
        if not self.is_logged_in:
            if not self.check_login_status():
                return None, None
        
        try:
            # Buscar el contacto
            search_box = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]'))
            )
            
            search_box.clear()
            search_box.send_keys(phone_number)
            time.sleep(2)
            
            # Buscar y hacer click en el contacto
            try:
                contact_xpath = f'//span[contains(@title, "{phone_number}") or contains(@title, "+{phone_number}")]'
                contact_result = WebDriverWait(self.driver, 5).until(
                    EC.element_to_be_clickable((By.XPATH, contact_xpath))
                )
                contact_result.click()
            except:
                logging.warning(f"⚠️ No se encontró contacto exacto para {phone_number}")
                return None, None
            
            time.sleep(3)
            
            # Obtener nombre del perfil
            try:
                profile_name = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, '//header//span[@title]'))
                ).get_attribute('title')
            except:
                profile_name = phone_number
            
            # Obtener imagen de perfil (intentamos desde la miniatura)
            profile_image = None
            try:
                img_element = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, '//header//img[@src]'))
                )
                profile_image = img_element.get_attribute('src')
            except:
                logging.warning(f"⚠️ No se pudo obtener imagen para {phone_number}")
            
            # Limpiar búsqueda
            search_box.clear()
            search_box.send_keys(Keys.ESCAPE)
            
            return profile_name, profile_image
            
        except Exception as e:
            logging.error(f"❌ Error obteniendo info de {phone_number}: {e}")
            return None, None

    def close(self):
        """Cierra el navegador"""
        if self.driver:
            self.driver.quit()
            logging.info("✅ Navegador cerrado")

# Singleton
whatsapp_client = None

def get_whatsapp_client():
    global whatsapp_client
    if whatsapp_client is None:
        whatsapp_client = WhatsAppSelenium()
    return whatsapp_client