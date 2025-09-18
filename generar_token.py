#!/usr/bin/env python3
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import os
import json

SCOPES = ['https://www.googleapis.com/auth/calendar']

def generar_token_localmente():
    print("🔐 Generando token de Google Calendar...")
    
    client_secret_file = 'client_secret.json'
    if not os.path.exists(client_secret_file):
        print(f"❌ Error: {client_secret_file} no encontrado")
        return False
    
    print("✅ client_secret.json encontrado")
    
    flow = InstalledAppFlow.from_client_secrets_file(
        client_secret_file, 
        SCOPES,
        redirect_uri='http://localhost:8080/'  # 🔥 Agrega esto
    )
    
    print("🌐 Abriendo navegador para autenticación...")
    print("⚠️  Si aparece error de redirect, verifica que tengas en Google Cloud Console:")
    print("   - http://localhost:8080/")
    print("   - http://localhost:8080")
    print("   - http://127.0.0.1:8080/") 
    print("   - http://127.0.0.1:8080")
    
    # 🔥 CAMBIA run_console() por run_local_server()
    creds = flow.run_local_server(
        port=8080,
        authorization_prompt_message='Por favor, visita esta URL: {url}',
        success_message='✅ Autenticación exitosa. Puedes cerrar esta ventana.',
        open_browser=True
    )
    
    # Guarda el token
    with open('token.json', 'w') as token:
        token.write(creds.to_json())
    
    print("✅ Token generado y guardado en token.json")
    print("📋 Ahora sube token.json al servidor:")
    print("   scp token.json ubuntu@tu-servidor:/home/ubuntu/Whatsmektia/")
    
    return True

if __name__ == '__main__':
    try:
        success = generar_token_localmente()
        if success:
            print("\n🎉 ¡Token generado exitosamente!")
        else:
            print("\n💥 Error generando token")
    except Exception as e:
        print(f"❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()