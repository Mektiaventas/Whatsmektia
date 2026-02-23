from flask import Flask
from ver2.configuracion import Config

def create_app():
    # Creamos la instancia de Flask
    app = Flask(__name__)
    
    # 1. Cargamos la configuración respetando tus variables del .env
    app.config.from_object(Config)
    
    # 2. Inicializamos carpetas (uploads, etc.) en el servidor Ubuntu
    Config.init_app(app)

    with app.app_context():
        # 3. Importamos y registramos las rutas (Blueprints)
        # Esto evita que el archivo __init__.py se vuelva un "monstruo"
        from .routes import main_bp
        app.register_blueprint(main_bp)
        
        # Ruta de salud simple para verificar el puerto 5003
        @app.route('/check', methods=['GET'])
        def check():
            return {
                "status": "v2_online", 
                "port": 5003,
                "database_master": Config.CLIENTES_DB_NAME
            }, 200

    return app
