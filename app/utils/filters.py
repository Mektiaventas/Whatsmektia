"""
Template filters para la aplicación
"""
import re
from flask import url_for, current_app
from datetime import datetime
import pytz

# Configurar zona horaria de México
tz_mx = pytz.timezone('America/Mexico_City')

# Necesitaremos importar PREFIJOS_PAIS desde algún lugar
# Por ahora lo definimos como variable global que se configurará después
PREFIJOS_PAIS = {}


def format_time_24h(dt):
    """Convierte datetime a formato 'día/mes hora:minuto' en zona horaria México"""
    if not dt:
        return ""
    try:
        if dt.tzinfo is None:
            dt = tz_mx.localize(dt)
        else:
            dt = dt.astimezone(tz_mx)
        return dt.strftime('%d/%m %H:%M')
    except Exception as e:
        current_app.logger.error(f"Error formateando fecha {dt}: {e}")
        return ""


def whatsapp_format(text):
    """Convierte formato de WhatsApp (*texto* -> negrita, _texto_ -> cursiva) a HTML"""
    if not text:
        return ""
    
    # ELIMINAR ESPACIOS INICIALES
    text = text.lstrip()
    
    # Negritas: *texto* -> <strong>texto</strong>
    text = re.sub(r'\*(.*?)\*', r'<strong>\1</strong>', text)
    
    # Cursivas: _texto_ -> <em>texto</em>
    text = re.sub(r'_(.*?)_', r'<em>\1</em>', text)
    
    # Tachado: ~texto~ -> <del>texto</del>
    text = re.sub(r'~(.*?)~', r'<del>\1</del>', text)
    
    return text


def public_image_url(imagen_url):
    """Normalize image reference for templates: robust handling of filenames, subpaths and absolute URLs."""
    try:
        if not imagen_url:
            return ''
        imagen_url = str(imagen_url).strip()

        # Keep data URIs and absolute URLs
        if imagen_url.startswith('data:') or imagen_url.startswith('http://') or imagen_url.startswith('https://'):
            return imagen_url

        # Keep app-absolute paths (already public)
        if imagen_url.startswith('/uploads/') or imagen_url.startswith('/static/') or imagen_url.startswith('/'):
            return imagen_url

        from os.path import basename
        fname = basename(imagen_url)

        if not fname:
            return imagen_url

        # Priorizar la búsqueda en la carpeta de subidas general /uploads/
        # (para chats de usuarios) y si falla, buscar en /uploads/productos/
        try:
            # Intento 1: Servir desde /uploads/ (usando 'serve_uploaded_file')
            return url_for('serve_product_image', filename=fname)
        except Exception:
            # Intento 2: Fallback a /uploads/productos/ (usando 'serve_product_image')
            try:
                return url_for('serve_uploaded_file', filename=fname)
            except Exception:
                # Si ambos fallan, devuelve el nombre del archivo (probablemente roto)
                return imagen_url

    except Exception:
        # Último recurso si todo el bloque 'try' principal falla
        return imagen_url


def get_country_flag(numero):
    """
    Determina la URL de la bandera o ícono de la plataforma basado en el número.
    Prioridad: 1. Telegram Icono, 2. Bandera de País, 3. Icono de WhatsApp por defecto.
    """
    if not numero:
        return None
    numero = str(numero)
    
    # 1. LÓGICA: ÍCONO DE TELEGRAM (MÁXIMA PRIORIDAD)
    if numero.startswith('tg_'):
        # Devuelve la URL estática del ícono de Telegram
        return url_for('static', filename='icons/telegram-icon.png')
    
    # 2. LÓGICA: BANDERA DE PAÍS (WHATSAPP)
    # Limpia el número quitando el '+' si existe (ej. +52449...)
    numero_limpio = numero.lstrip('+')
    
    # Busca el prefijo de país más largo posible (3, 2 o 1 dígito)
    for i in range(3, 0, -1):
        prefijo = numero_limpio[:i]
        
        # Asume que PREFIJOS_PAIS es un diccionario global
        if prefijo in PREFIJOS_PAIS:
            codigo = PREFIJOS_PAIS[prefijo]
            # Devuelve la bandera del país
            return f"https://flagcdn.com/24x18/{codigo}.png"
            
    # 3. LÓGICA: IMAGEN LOCAL POR DEFECTO PARA WHATSAPP (FALLBACK)
    # Si no se detectó prefijo de país conocido ni era Telegram
    return url_for('static', filename='icons/whatsapp-icon.png')
