import os

def crear_estructura_tenant(tenant_slug):
    """
    Crea las 4 subcarpetas esenciales para un cliente si no existen.
    Retorna True si creó algo, False si ya todo existía.
    """
    base_path = "/home/ubuntu/Whatsmektia/uploads"
    folders = ['docs', 'logos', 'pdfs', 'productos']
    se_creo_algo = False
    
    for folder in folders:
        ruta_completa = os.path.join(base_path, folder, tenant_slug)
        if not os.path.exists(ruta_completa):
            os.makedirs(ruta_completa, exist_ok=True)
            se_creo_algo = True
            
    return se_creo_algo

def verificar_carpetas_completas(tenant_slug):
    """
    Revisa si las 4 carpetas existen para saber si deshabilitar el botón.
    """
    base_path = "/home/ubuntu/Whatsmektia/uploads"
    folders = ['docs', 'logos', 'pdfs', 'productos']
    
    return all(os.path.exists(os.path.join(base_path, f, tenant_slug)) for f in folders)
    
from app.config.settings import Config

def allowed_file(filename):
    """Verificar si la extensión del archivo está permitida"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS
