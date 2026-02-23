import os
from ver2.app import create_app

# Creamos la instancia
app = create_app()

if __name__ == "__main__":
    # Puerto 5003 confirmado para convivencia con supercopia
    puerto = 5003
    
    print(f"--- Mektia SaaS V2 ---")
    print(f"🚀 Servidor arrancando en: http://0.0.0.0:{puerto}")
    print(f"📂 Usando .env desde la raíz")
    
    app.run(
        host="0.0.0.0",
        port=puerto,
        debug=True,
        use_reloader=False # Importante para evitar ejecuciones dobles de hilos/schedulers
    )
