# whatsapp_selenium.py - VERSIÓN CORREGIDA
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
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
from PIL import Image
import io

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WhatsAppSelenium:
    def __init__(self):
        self.driver = None
        self.is_logged_in = False
        self.qr_code = None
        self.qr_generated_time = None
        self.setup_driver()
        
    def setup_driver(self):
    #"""Configura el driver de Selenium para servidor headless"""
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        
        chrome_options = Options()
        
        # Configuración para servidor sin interfaz gráfica
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--headless=new')  # Modo headless moderno
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-extensions')
        chrome_options.add_argument('--disable-software-rasterizer')
        
        # Configuración específica para WhatsApp Web
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36')
        
        # Usar ChromeDriver del sistema
        self.driver = webdriver.Chrome(options=chrome_options)
        
        self.driver.set_page_load_timeout(60)
        self.driver.implicitly_wait(10)
        
        logger.info("✅ Driver configurado en modo headless")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error configurando driver: {e}")
        # Fallback: intentar sin modo headless para debugging
        try:
            chrome_options = Options()
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            self.driver = webdriver.Chrome(options=chrome_options)
            logger.info("✅ Driver configurado sin headless (fallback)")
            return True
        except Exception as e2:
            logger.error(f"❌ Fallback también falló: {e2}")
            return False

    def generate_qr_code(self):
        """Genera el código QR para WhatsApp Web"""
        try:
            self.driver.get("https://web.whatsapp.com")
            logger.info("🌐 Abriendo WhatsApp Web...")
            
            # Esperar a que aparezca el QR
            WebDriverWait(self.driver, 30).until(
                EC.presence_of_element_located((By.XPATH, '//canvas[@aria-label="Scan me!"]'))
            )
            
            # Obtener screenshot del QR
            qr_element = self.driver.find_element(By.XPATH, '//canvas[@aria-label="Scan me!"]')
            qr_screenshot = qr_element.screenshot_as_png
            
            # Convertir a base64 para mostrar en web
            self.qr_code = base64.b64encode(qr_screenshot).decode('utf-8')
            self.qr_generated_time = time.time()
            
            logger.info("✅ Código QR generado")
            return self.qr_code
            
        except Exception as e:
            logger.error(f"❌ Error generando QR: {e}")
            return None

    def check_login_status(self):
        """Verifica si el login fue exitoso"""
        try:
            # Buscar elementos que indican que estamos logueados
            chat_list = self.driver.find_elements(By.XPATH, '//div[@role="grid"]')
            if chat_list:
                self.is_logged_in = True
                self.qr_code = None
                logger.info("✅ Login exitoso detectado")
                return True
            return False
        except Exception as e:
            logger.error(f"❌ Error verificando login: {e}")
            return False

    def wait_for_login(self, timeout=120):
        """Espera a que el usuario complete el login"""
        start_time = time.time()
        
        while time.time() - start_time < timeout:
            if self.check_login_status():
                return True
            
            # Verificar si el QR expiró
            if self.qr_generated_time and time.time() - self.qr_generated_time > 120:
                logger.info("🔄 QR expirado, generando nuevo...")
                self.generate_qr_code()
                
            time.sleep(5)
        
        return False

    def get_contact_info(self, phone_number):
        """Obtiene nombre e imagen de perfil de un contacto"""
        if not self.is_logged_in:
            logger.error("❌ No hay sesión activa de WhatsApp")
            return None, None
        
        try:
            # Formatear número (eliminar espacios y caracteres especiales)
            clean_number = ''.join(filter(str.isdigit, phone_number))
            
            # Buscar el contacto
            search_box = WebDriverWait(self.driver, 15).until(
                EC.element_to_be_clickable((By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]'))
            )
            
            search_box.clear()
            search_box.send_keys(clean_number)
            time.sleep(3)  # Esperar resultados de búsqueda
            
            # Buscar contacto en la lista
            contact_xpath = f'//span[contains(@title, "{clean_number}")]'
            contacts = self.driver.find_elements(By.XPATH, contact_xpath)
            
            if not contacts:
                logger.warning(f"⚠️ No se encontró contacto para {clean_number}")
                # Limpiar búsqueda
                search_box.clear()
                search_box.send_keys(Keys.ESCAPE)
                return None, None
            
            # Hacer click en el primer resultado
            contacts[0].click()
            time.sleep(3)
            
            # Obtener nombre del contacto
            try:
                profile_name_element = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, '//header//span[@title]'))
                )
                profile_name = profile_name_element.get_attribute('title')
            except Exception as e:
                logger.warning(f"⚠️ No se pudo obtener nombre: {e}")
                profile_name = clean_number
            
            # Obtener imagen de perfil
            profile_image = None
            try:
                img_element = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, '//header//img[@src]'))
                )
                profile_image = img_element.get_attribute('src')
                
                # Si es una imagen base64, guardarla como URL accesible
                if profile_image and profile_image.startswith('data:image'):
                    # Extraer base64 y crear archivo
                    image_data = profile_image.split(',')[1]
                    image_bytes = base64.b64decode(image_data)
                    
                    # Guardar imagen localmente
                    images_dir = os.path.join(os.path.dirname(__file__), 'static', 'images', 'profiles')
                    os.makedirs(images_dir, exist_ok=True)
                    
                    filename = f"profile_{clean_number}.jpg"
                    filepath = os.path.join(images_dir, filename)
                    
                    with open(filepath, 'wb') as f:
                        f.write(image_bytes)
                    
                    profile_image = f"/static/images/profiles/{filename}"
                    
            except Exception as e:
                logger.warning(f"⚠️ No se pudo obtener imagen: {e}")
            
            # Limpiar búsqueda
            search_box.clear()
            search_box.send_keys(Keys.ESCAPE)
            time.sleep(1)
            
            logger.info(f"✅ Información obtenida: {profile_name}, {profile_image}")
            return profile_name, profile_image
            
        except Exception as e:
            logger.error(f"❌ Error obteniendo info de {phone_number}: {e}")
            return None, None

    def close(self):
        """Cierra el navegador"""
        if self.driver:
            self.driver.quit()
            logger.info("✅ Navegador cerrado")

# Singleton global
whatsapp_client = None

def get_whatsapp_client():
    global whatsapp_client
    if whatsapp_client is None:
        whatsapp_client = WhatsAppSelenium()
    return whatsapp_client

def init_whatsapp_session():
    """Inicializa la sesión de WhatsApp"""
    client = get_whatsapp_client()
    return client.generate_qr_code()