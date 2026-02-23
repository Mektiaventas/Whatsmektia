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
        # --- REGISTRO DE BLUEPRINTS ---
        # Los agrupamos aquí para mantener el orden
        from .routes import main_bp
        from .webhook_recepcion import webhook_bp
        
        app.register_blueprint(main_bp)
        app.register_blueprint(webhook_bp)
        
        # --- RUTAS GLOBALES DE SISTEMA ---
        @app.route('/check', methods=['GET'])
        def check():
            return {
                "status": "v2_online", 
                "port": 5003,
                "database_master": Config.CLIENTES_DB_NAME
            }, 200

    return app
