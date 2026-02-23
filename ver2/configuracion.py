import os
from dotenv import load_dotenv

# Localizar el archivo .env en la raíz (subiendo un nivel desde ver2/)
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(env_path)

class Config:
    # --- CONFIGURACIÓN DE BASE DE DATOS ---
    # Usamos los valores de tu .env o defaults seguros
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_USER = os.getenv('DB_USER', 'mektia')
    DB_PASSWORD = os.getenv('DB_PASSWORD', 'Mektia#2025')
    DB_MASTER = 'clientes'  # Base de datos maestra definida en tu servicios.py

    # --- CREDENCIALES DE APIS ---
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    
    # --- RUTAS DE ARCHIVOS ---
    # Definimos la ruta absoluta de uploads para que coincida con tu servidor Ubuntu
    BASE_DIR = "/home/ubuntu/Whatsmektia"
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    
    # --- SEGURIDAD ---
    # Token para validar el webhook de Meta
    WA_VERIFY_TOKEN = os.getenv('WA_VERIFY_TOKEN', 'mektia_default_token')

    @staticmethod
    def init_app(app):
        # Aseguramos que existan las carpetas necesarias al arrancar
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
