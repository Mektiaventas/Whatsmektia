import os
from dotenv import load_dotenv

# Localizar el archivo .env en la raíz
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(env_path)

class Config:
    # --- CREDENCIALES MAESTRAS (Globales en tu .env) ---
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    GEMINI_TOKEN = os.getenv('GEMINI_TOKEN')
    DEEPSEEK_API_KEY = os.getenv('DEEPSEEK_API_KEY')
    
    # Base de datos de control (donde está la tabla 'cliente')
    CLIENTES_DB_HOST = os.getenv('CLIENTES_DB_HOST', '127.0.0.1')
    CLIENTES_DB_USER = os.getenv('CLIENTES_DB_USER', 'mektia')
    CLIENTES_DB_PASSWORD = os.getenv('CLIENTES_DB_PASSWORD', 'Mektia#2025')
    CLIENTES_DB_NAME = os.getenv('CLIENTES_DB_NAME', 'clientes')

    # --- RUTAS ---
    BASE_DIR = "/home/ubuntu/Whatsmektia"
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')

    # --- MÉTODO PARA OBTENER CONFIG DE TENANT ESPECÍFICO ---
    @staticmethod
    def get_tenant_config(prefix):
        """
        Busca variables en el .env con el prefijo del cliente.
        Ejemplo: prefix='UNILOVA' -> busca UNILOVA_DB_NAME
        """
        prefix = prefix.upper()
        return {
            'phone_id': os.getenv(f'{prefix}_PHONE_NUMBER_ID'),
            'token': os.getenv(f'{prefix}_WHATSAPP_TOKEN'),
            'db_host': os.getenv(f'{prefix}_DB_HOST', '127.0.0.1'),
            'db_user': os.getenv(f'{prefix}_DB_USER'),
            'db_pass': os.getenv(f'{prefix}_DB_PASSWORD'),
            'db_name': os.getenv(f'{prefix}_DB_NAME'),
            'verify_token': os.getenv(f'{prefix}_VERIFY_TOKEN')
        }
