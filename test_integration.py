#!/usr/bin/env python3
import os
import sys
sys.path.append('/home/ubuntu/Whatsmektia')

# Importa las funciones de tu app
from app import autenticar_google_calendar, crear_evento_calendar

def test_integration():
    print("🔍 Probando integración con Google Calendar desde la app...")
    
    try:
        # Prueba la autenticación
        service = autenticar_google_calendar()
        if service:
            print("✅ Autenticación exitosa")
            
            # Prueba crear un evento de prueba
            evento_prueba = {
                'servicio_solicitado': 'Prueba de integración',
                'fecha_sugerida': '2025-09-12',
                'hora_sugerida': '10:00',
                'nombre_cliente': 'Usuario de Prueba',
                'telefono': '521234567890'
            }
            
            evento_id = crear_evento_calendar(service, evento_prueba)
            if evento_id:
                print(f"✅ Evento creado exitosamente: {evento_id}")
                
                # Opcional: borrar el evento de prueba
                try:
                    service.events().delete(calendarId='primary', eventId=evento_id).execute()
                    print("✅ Evento de prueba borrado")
                except:
                    print("⚠️  Evento de prueba no se pudo borrar (puede ignorarse)")
                
                return True
            else:
                print("❌ Error creando evento")
                return False
        else:
            print("❌ Error en autenticación")
            return False
            
    except Exception as e:
        print(f"❌ Error en integración: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == '__main__':
    success = test_integration()
    if success:
        print("\n🎉 ¡Integración con Google Calendar funciona correctamente!")
        sys.exit(0)
    else:
        print("\n💥 La integración falló")
        sys.exit(1)