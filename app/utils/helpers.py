from app.config.settings import Config

def allowed_file(filename):
    """Verificar si la extensión del archivo está permitida"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS
