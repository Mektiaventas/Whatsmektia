from ver2.app import create_app

app = create_app()

if __name__ == "__main__":
    # Forzamos puerto 5003 para pruebas de la V2
    print("🚀 Mektia V2: Iniciando sistema de pruebas en puerto 5003...")
    app.run(host="0.0.0.0", port=5001, debug=True, use_reloader=False)
