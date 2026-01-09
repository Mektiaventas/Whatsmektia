from flask import Flask
import os
import pytz
from .utils import helpers, filters
from .config.settings import PREFIJOS_PAIS  # ← Importamos desde settings

def create_app():
    app = Flask(__name__)
    
    # Configuración básica
    app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-key')
    app.config['UPLOAD_FOLDER'] = 'uploads'
    app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB
    
    # Configurar PREFIJOS_PAIS para el filter get_country_flag
    filters.PREFIJOS_PAIS = PREFIJOS_PAIS  # ← Usamos el de settings
    
    # Registrar template filters
    app.jinja_env.filters['format_time_24h'] = filters.format_time_24h
    app.jinja_env.filters['whatsapp_format'] = filters.whatsapp_format
    app.jinja_env.filters['public_img'] = filters.public_image_url
    app.jinja_env.filters['bandera'] = filters.get_country_flag
    
    return app
