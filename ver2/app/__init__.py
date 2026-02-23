from flask import Flask
from ver2.configuracion import Config

def create_app():
    app = Flask(__name__)
    
    # Cargamos la configuración desde nuestra clase Config
    app.config.from_object(Config)
    
    # Inicializamos carpetas y logs definidos en Config
    Config.init_app(app)

    with app.app_context():
        # Aquí registraremos los Blueprints (rutas) más adelante
        # Ejemplo: from .routes import main_bp; app.register_blueprint(main_bp)
        
        @app.route('/check', methods=['GET'])
        def check():
            return {"status": "v2_online", "port": 5003}, 200

    return app
