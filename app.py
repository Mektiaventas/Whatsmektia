import traceback
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
import hashlib
import time
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import service_account
from mysql.connector import pooling
from flask import render_template_string
import pytz
import os
import logging
import json 
import base64
import argparse
import mysql.connector
from flask import Flask, send_from_directory, Response, request, render_template, redirect, url_for, abort, flash, jsonify, current_app
import requests
from dotenv import load_dotenv
import pandas as pd
import openpyxl
from docx import Document
from datetime import datetime, timedelta
from decimal import Decimal
import re
import io
from werkzeug.utils import secure_filename
from PIL import Image
from openai import OpenAI
import PyPDF2
import fitz 
from werkzeug.utils import secure_filename
import bcrypt
from functools import wraps
from flask import session, g
try:
    # preferred location
    from openpyxl.utils.cell import coordinate_from_string, column_index_from_string
except Exception:
    # fallback for other openpyxl layouts: column_index_from_string may still be available
    from openpyxl.utils import column_index_from_string
    import re
    def coordinate_from_string(coord):
        """Simple fallback parser for coordinates like 'A1' -> ('A', 1)."""
        m = re.match(r'^([A-Za-z]+)(\d+)$', str(coord).strip())
        if not m:
            raise ValueError(f"Invalid coordinate: {coord}")
        return m.group(1), int(m.group(2))


processed_messages = {}

tz_mx = pytz.timezone('America/Mexico_City')
guardado = True
load_dotenv()  # Cargar desde archivo específico
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "cualquier-cosa")
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 50 MB
app.logger.setLevel(logging.INFO)

@app.template_filter('format_time_24h')
def format_time_24h(dt):
    if not dt:
        return ""
    try:
        if dt.tzinfo is None:
            dt = tz_mx.localize(dt)
        else:
            dt = dt.astimezone(tz_mx)
        return dt.strftime('%d/%m %H:%M')
    except Exception as e:
        app.logger.error(f"Error formateando fecha {dt}: {e}")
        return ""
# ——— Env vars ———

GOOGLE_CLIENT_SECRET_FILE = os.getenv("GOOGLE_CLIENT_SECRET_FILE")    
VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ALERT_NUMBER = os.getenv("ALERT_NUMBER")
SECRET_KEY = os.getenv("SECRET_KEY", "cualquier-cosa")
# After app.config[...] and logger setup
MAX_CONCURRENT_SESSIONS = int(os.getenv("MAX_CONCURRENT_SESSIONS", "2"))
SESSION_ACTIVE_WINDOW_MINUTES = int(os.getenv("SESSION_ACTIVE_WINDOW_MINUTES", "60"))
OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
IA_ESTADOS = {}
client = OpenAI(api_key=OPENAI_API_KEY)  # ✅
# ——— Configuración Multi-Tenant ———
NUMEROS_CONFIG = {
    '524495486142': {  # Número de Mektia
        'phone_number_id': os.getenv("MEKTIA_PHONE_NUMBER_ID"),
        'whatsapp_token': os.getenv("MEKTIA_WHATSAPP_TOKEN"),
        'db_host': os.getenv("MEKTIA_DB_HOST"),
        'db_user': os.getenv("MEKTIA_DB_USER"),
        'db_password': os.getenv("MEKTIA_DB_PASSWORD"),
        'db_name': os.getenv("MEKTIA_DB_NAME"),
        'dominio': 'smartwhats.mektia.com'
    },
    '123': {  # Número de Unilova
        'phone_number_id': os.getenv("UNILOVA_PHONE_NUMBER_ID"),
        'whatsapp_token': os.getenv("UNILOVA_WHATSAPP_TOKEN"),
        'db_host': os.getenv("UNILOVA_DB_HOST"),
        'db_user': os.getenv("UNILOVA_DB_USER"),
        'db_password': os.getenv("UNILOVA_DB_PASSWORD"),
        'db_name': os.getenv("UNILOVA_DB_NAME"),
        'dominio': 'unilova.mektia.com'
    },
    '524812372326': {  # Número de La Porfirianna
        'phone_number_id': os.getenv("LAPORFIRIANNA_PHONE_NUMBER_ID"),
        'whatsapp_token': os.getenv("LAPORFIRIANNA_WHATSAPP_TOKEN"),
        'db_host': os.getenv("PORFIRIANNA_DB_HOST"),
        'db_user': os.getenv("PORFIRIANNA_DB_USER"),
        'db_password': os.getenv("PORFIRIANNA_DB_PASSWORD"),
        'db_name': os.getenv("PORFIRIANNA_DB_NAME"),
        'dominio': 'laporfirianna.mektia.com'
    },
    '524495486324': {  # Número de Ofitodo - CORREGIDO
        'phone_number_id': os.getenv("FITO_PHONE_NUMBER_ID"),  # ← Cambiado
        'whatsapp_token': os.getenv("FITO_WHATSAPP_TOKEN"),    # ← Cambiado
        'db_host': os.getenv("FITO_DB_HOST"),                  # ← Cambiado
        'db_user': os.getenv("FITO_DB_USER"),                  # ← Cambiado
        'db_password': os.getenv("FITO_DB_PASSWORD"),          # ← Cambiado
        'db_name': os.getenv("FITO_DB_NAME"),                  # ← Cambiado
        'dominio': 'ofitodo.mektia.com'
    }
}

soli = "cita"
servicios_clave = [
            'página web', 'sitio web', 'ecommerce', 'tienda online',
            'aplicación', 'app', 'software', 'sistema',
            'marketing', 'seo', 'redes sociales', 'publicidad',
            'diseño', 'branding', 'logo', 'identidad visual',
            'hosting', 'dominio', 'mantenimiento', 'soporte',
            'electronica', 'hardware', 'iot', 'internet de las cosas',
        ]    

# Configuración por defecto (para backward compatibility)
# Por esto (valores explícitos en lugar de llamar a la función):
DEFAULT_CONFIG = NUMEROS_CONFIG['524495486142']
WHATSAPP_TOKEN = DEFAULT_CONFIG['whatsapp_token']
DB_HOST = DEFAULT_CONFIG['db_host']
DB_USER = DEFAULT_CONFIG['db_user']
DB_PASSWORD = DEFAULT_CONFIG['db_password']
DB_NAME = DEFAULT_CONFIG['db_name']
MI_NUMERO_BOT = DEFAULT_CONFIG['phone_number_id']
PHONE_NUMBER_ID = MI_NUMERO_BOT
# Agrega esto después de las otras variables de configuración
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# Diccionario de prefijos a código de país
PREFIJOS_PAIS = {
    '52': 'mx', '1': 'us', '54': 'ar', '57': 'co', '55': 'br',
    '34': 'es', '51': 'pe', '56': 'cl', '58': 've', '593': 'ec',
    '591': 'bo', '507': 'pa', '502': 'gt'
}

app.jinja_env.filters['bandera'] = lambda numero: get_country_flag(numero)

PDF_UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads', 'pdfs')
os.makedirs(PDF_UPLOAD_FOLDER, exist_ok=True)
ALLOWED_EXTENSIONS = {
    'pdf', 'xlsx', 'xls', 'csv', 'docx', 'txt',
    'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg',
    'mp4', 'mov', 'webm', 'avi', 'mkv', 'ogg', 'mpeg'
}

# --- Conexión a la BD de clientes (auth) ---
def get_clientes_conn():
    return mysql.connector.connect(
        host=os.getenv("CLIENTES_DB_HOST"),
        user=os.getenv("CLIENTES_DB_USER"),
        password=os.getenv("CLIENTES_DB_PASSWORD"),
        database=os.getenv("CLIENTES_DB_NAME")
    )

def obtener_cliente_por_user(username):
    conn = get_clientes_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT id_cliente, telefono, entorno, shema, servicio, `user`, password
        FROM cliente
        WHERE `user` = %s
        LIMIT 1
    """, (username,))
    row = cur.fetchone()
    cur.close(); conn.close()
    return row

def verificar_password(password_plano, password_guardado):
    return password_plano == password_guardado

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('auth_user'):
            return redirect(url_for('login', next=request.path))
        g.auth_user = session.get('auth_user')
        return f(*args, **kwargs)
    return wrapper

# Rutas públicas que NO requieren login (añade más si hace falta)
RUTAS_PUBLICAS = {
    'login', 'logout', 'webhook', 'webhook_verification',
    'static', 'debug_headers', 'debug_dominio', 'diagnostico'
}
@app.before_request
def proteger_rutas():
    """
    Protección global: permite endpoints públicos y prefijos públicos (p.ej. /uploads/)
    Debe registrarse *antes* de otras funciones @app.before_request que puedan redirigir.
    """
    app.logger.debug(f"🔐 proteger_rutas check: path={request.path} endpoint={request.endpoint}")

    # Endpoints explícitamente públicos por nombre
    if request.endpoint in RUTAS_PUBLICAS:
        return

    # Permitir archivos estáticos gestionados por Flask
    if request.endpoint and request.endpoint.startswith('static'):
        return

    # Permitir accesos directos a rutas públicas por path (uploads y subpaths)
    public_path_prefixes = (
        '/uploads/',
        '/uploads',   # cubrir '/uploads' sin slash final
        '/static/images/',
        '/static/audio/',
    )
    if request.path and any(request.path.startswith(p) for p in public_path_prefixes):
        return

    # Endpoints que sirven archivos/depuración (si los tienes)
    public_endpoints = {
        'serve_product_image',
        'serve_uploaded_file',
        'debug_image',
        'debug_image_full',
        'proxy_audio',
        'debug_headers',
        'debug_dominio',
        'diagnostico'
    }
    if request.endpoint in public_endpoints:
        return

    # Si ya está autenticado, permitir
    if session.get('auth_user'):
        return

    # Si llega aquí, no está autorizado -> redirigir al login
    app.logger.info(f"🔒 proteger_rutas: redirect to login for path={request.path} endpoint={request.endpoint}")
    return redirect(url_for('login', next=request.path))

def extraer_imagenes_embedded_excel(filepath, output_dir=None, config=None):
    """
    Extrae imágenes embebidas de un archivo Excel (.xlsx) y las guarda en output_dir.
    Soporta multi-tenant: si no se pasa output_dir, usa get_productos_dir_for_config(config)
    para guardar en uploads/productos/<tenant_slug>.
    Retorna lista de dicts: {'filename','path','sheet','anchor','row','col'}
    """
    try:
        # Determine tenant-aware output dir when none provided
        if output_dir is None:
            try:
                productos_dir, tenant_slug = get_productos_dir_for_config(config)
                output_dir = productos_dir
            except Exception as e:
                # Fallback to legacy dir if tenant helper fails
                app.logger.warning(f"⚠️ get_productos_dir_for_config falló, usando legacy. Error: {e}")
                output_dir = os.path.join(UPLOAD_FOLDER, 'productos')

        os.makedirs(output_dir, exist_ok=True)

        wb = openpyxl.load_workbook(filepath)
        imagenes_extraidas = []

        for sheet in wb.worksheets:
            for idx, img in enumerate(getattr(sheet, '_images', [])):
                try:
                    img_obj = img.image
                    img_format = (img_obj.format or 'PNG').lower()
                    img_filename = f"excel_img_{sheet.title}_{idx+1}_{int(time.time())}.{img_format}"
                    img_path = os.path.join(output_dir, img_filename)

                    # Guardar imagen en disco
                    try:
                        img_obj.save(img_path)
                    except Exception as e:
                        app.logger.warning(f"⚠️ No se pudo guardar imagen en disco {img_filename}: {e}")
                        continue

                    # Intentar leer la ancla (fila/col) de varias formas
                    row = None
                    col = None
                    anchor = getattr(img, 'anchor', None)
                    try:
                        marker = None
                        # Common attribute names in different openpyxl versions
                        for attr in ('_from', 'from', 'from_', 'anchor_from'):
                            marker = getattr(anchor, attr, None)
                            if marker:
                                break

                        if marker:
                            # marker usually tiene row, col (0-based)
                            row_candidate = getattr(marker, 'row', None)
                            col_candidate = getattr(marker, 'col', None)
                            # Algunas versiones devuelven atributos como tuples o listas
                            if row_candidate is None and hasattr(marker, '__len__') and len(marker) >= 1:
                                # try tuple-like (col, row) or (row, col)
                                try:
                                    maybe = list(marker)
                                    # buscar primer int
                                    ints = [m for m in maybe if isinstance(m, int)]
                                    if len(ints) >= 1:
                                        row_candidate = ints[0]
                                except Exception:
                                    pass

                            if isinstance(row_candidate, int):
                                row = int(row_candidate) + 1
                            if isinstance(col_candidate, int):
                                col = int(col_candidate) + 1

                        # Si anchor es string con coordenada (ej. "A2"), parsearla
                        if row is None and isinstance(anchor, str):
                            try:
                                col_letter, row_num = coordinate_from_string(anchor)
                                col = column_index_from_string(col_letter)
                                row = int(row_num)
                            except Exception:
                                pass
                    except Exception:
                        row = None
                        col = None

                    imagenes_extraidas.append({
                        'filename': img_filename,
                        'path': img_path,
                        'sheet': sheet.title,
                        'anchor': anchor,
                        'row': row,
                        'col': col
                    })
                    app.logger.info(f"✅ Imagen extraída: {img_filename} (sheet={sheet.title} row={row} col={col}) tenant_dir={output_dir}")
                except Exception as e:
                    app.logger.warning(f"⚠️ Error extrayendo imagen en sheet {sheet.title} idx {idx}: {e}")
                    continue

        return imagenes_extraidas

    except Exception as e:
        app.logger.error(f"🔴 Error en extraer_imagenes_embedded_excel: {e}")
        app.logger.error(traceback.format_exc())
        return []

# Put below sesiones_activas helpers
def desactivar_sesiones_antiguas(username, within_minutes=SESSION_ACTIVE_WINDOW_MINUTES):
    """Marks old sessions as inactive to avoid blocking new logins by stale entries."""
    try:
        conn = get_clientes_conn()
        _ensure_sesiones_table(conn)
        cur = conn.cursor()
        umbral = datetime.now() - timedelta(minutes=within_minutes)
        cur.execute("""
            UPDATE sesiones_activas
               SET is_active = 0
             WHERE user = %s
               AND last_seen < %s
        """, (username, umbral))
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        app.logger.error(f"Error desactivando sesiones antiguas: {e}")



# Replace your current /login handler with this version (same logic + session limit)
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        usuario = request.form.get('usuario', '').strip()
        password = request.form.get('password', '')
        cliente = obtener_cliente_por_user(usuario)

        if cliente and verificar_password(password, cliente['password']):
            # 1) Cleanup stale sessions to avoid false positives
            desactivar_sesiones_antiguas(cliente['user'], SESSION_ACTIVE_WINDOW_MINUTES)

            # 2) Enforce concurrent sessions limit
            active_count = contar_sesiones_activas(cliente['user'], within_minutes=SESSION_ACTIVE_WINDOW_MINUTES)
            if active_count >= MAX_CONCURRENT_SESSIONS:
                flash(f"❌ Este usuario ya tiene {active_count} sesiones activas. Cierra una sesión para continuar.", 'error')
                return render_template('login.html'), 429

            # 3) Proceed with login
            session['auth_user'] = {
                'id': cliente['id_cliente'],
                'user': cliente['user'],
                'entorno': cliente['entorno'],
                'schema': cliente['shema'],
                'servicio': cliente['servicio'],
            }
            registrar_sesion_activa(cliente['user'])
            flash('✅ Inicio de sesión correcto', 'success')
            destino = request.args.get('next') or url_for('home')
            return redirect(destino)

        flash('❌ Usuario o contraseña incorrectos', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    try:
        au = session.get('auth_user')
        if au and au.get('user'):
            cerrar_sesion_actual(au['user'])
    except Exception as e:
        app.logger.warning(f"No se pudo cerrar sesión activa: {e}")
    session.pop('auth_user', None)
    flash('Sesión cerrada', 'info')
    return redirect(url_for('login'))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def obtener_archivo_whatsapp(media_id, config=None):
    """Obtiene archivos de WhatsApp y los guarda localmente"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # 1. Obtener metadata del archivo
        url_metadata = f"https://graph.facebook.com/v18.0/{media_id}"
        headers = {
            'Authorization': f'Bearer {config["whatsapp_token"]}',
            'Content-Type': 'application/json'
        }
        
        app.logger.info(f"📎 Obteniendo metadata de archivo: {url_metadata}")
        response_metadata = requests.get(url_metadata, headers=headers, timeout=30)
        response_metadata.raise_for_status()
        
        metadata = response_metadata.json()
        download_url = metadata.get('url')
        mime_type = metadata.get('mime_type', 'application/octet-stream')
        filename = metadata.get('filename', f'archivo_{media_id}')
        
        if not download_url:
            app.logger.error(f"🔴 No se encontró URL de descarga: {metadata}")
            return None, None, None
            
        app.logger.info(f"📎 Descargando archivo: {filename} ({mime_type})")
        
        # 2. Descargar el archivo
        file_response = requests.get(download_url, headers=headers, timeout=60)
        if file_response.status_code != 200:
            app.logger.error(f"🔴 Error descargando archivo: {file_response.status_code}")
            return None, None, None
        
        # 3. Determinar extensión y guardar
        extension = determinar_extension(mime_type, filename)
        safe_filename = secure_filename(f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{filename}")
        filepath = os.path.join(UPLOAD_FOLDER, safe_filename)
        
        with open(filepath, 'wb') as f:
            f.write(file_response.content)
        
        app.logger.info(f"✅ Archivo guardado: {filepath}")
        return filepath, safe_filename, extension
        
    except Exception as e:
        app.logger.error(f"🔴 Error obteniendo archivo WhatsApp: {str(e)}")
        return None, None, None

# --- Sesiones activas (en BD de clientes) ---
def _get_or_create_session_id():
    sid = session.get('sid')
    if not sid:
        sid = os.urandom(16).hex()
        session['sid'] = sid
    return sid

def _ensure_sesiones_table(conn):
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS sesiones_activas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user VARCHAR(100) NOT NULL,
            session_id VARCHAR(64) NOT NULL,
            ip VARCHAR(45),
            user_agent VARCHAR(255),
            is_active TINYINT(1) DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_seen DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uq_user_session (user, session_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    """)
    conn.commit()
    cur.close()

def registrar_sesion_activa(username):
    try:
        conn = get_clientes_conn()
        _ensure_sesiones_table(conn)
        cur = conn.cursor()
        sid = _get_or_create_session_id()
        ip = request.remote_addr
        ua = request.headers.get('User-Agent', '')[:255]
        cur.execute("""
            INSERT INTO sesiones_activas (user, session_id, ip, user_agent, is_active, last_seen)
            VALUES (%s, %s, %s, %s, 1, NOW())
            ON DUPLICATE KEY UPDATE
                is_active = 1,
                ip = VALUES(ip),
                user_agent = VALUES(user_agent),
                last_seen = NOW()
        """, (username, sid, ip, ua))
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        app.logger.error(f"Error registrando sesión activa: {e}")

def actualizar_sesion_activa(username):
    try:
        if not username:
            return
        conn = get_clientes_conn()
        _ensure_sesiones_table(conn)
        cur = conn.cursor()
        sid = _get_or_create_session_id()
        ip = request.remote_addr
        ua = request.headers.get('User-Agent', '')[:255]
        cur.execute("""
            UPDATE sesiones_activas
               SET last_seen = NOW(), ip = %s, user_agent = %s
             WHERE user = %s AND session_id = %s AND is_active = 1
        """, (ip, ua, username, sid))
        conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        app.logger.error(f"Error actualizando sesión activa: {e}")

def cerrar_sesion_actual(username):
    try:
        conn = get_clientes_conn()
        _ensure_sesiones_table(conn)
        cur = conn.cursor()
        sid = session.get('sid')
        if sid:
            cur.execute("""
                UPDATE sesiones_activas
                   SET is_active = 0, last_seen = NOW()
                 WHERE user = %s AND session_id = %s
            """, (username, sid))
            conn.commit()
        cur.close(); conn.close()
    except Exception as e:
        app.logger.error(f"Error cerrando sesión actual: {e}")

def contar_sesiones_activas(username, within_minutes=30):
    try:
        conn = get_clientes_conn()
        _ensure_sesiones_table(conn)
        cur = conn.cursor()
        umbral = datetime.now() - timedelta(minutes=within_minutes)
        cur.execute("""
            SELECT COUNT(*)
              FROM sesiones_activas
             WHERE user = %s
               AND is_active = 1
               AND last_seen >= %s
        """, (username, umbral))
        count = cur.fetchone()[0]
        cur.close(); conn.close()
        return count
    except Exception as e:
        app.logger.error(f"Error contando sesiones activas: {e}")
        return 0

# Heartbeat de sesión en cada request autenticado
@app.before_request
def _heartbeat_sesion_activa():
    try:
        au = session.get('auth_user')
        if au and au.get('user'):
            actualizar_sesion_activa(au['user'])
    except Exception as e:
        app.logger.debug(f"Heartbeat sesión falló: {e}")

# Endpoint rápido para ver conteo por username (protegido)
@app.route('/admin/sesiones/<username>')
@login_required
def admin_sesiones_username(username):
    count = contar_sesiones_activas(username, within_minutes=30)
    return jsonify({'username': username, 'activos_ultimos_30_min': count})

@app.route('/configuracion/negocio', methods=['POST'])
def guardar_configuracion_negocio():
    config = obtener_configuracion_por_host()
    # Agregar logging para ver qué datos se reciben
    app.logger.info(f"📧 Formulario recibido: {request.form}")
    app.logger.info(f"📧 Calendar email recibido: {request.form.get('calendar_email')}")
    
    # Recopilar todos los datos del formulario
    datos = {
        'ia_nombre': request.form.get('ia_nombre'),
        'negocio_nombre': request.form.get('negocio_nombre'),
        'descripcion': request.form.get('descripcion'),
        'url': request.form.get('url'),
        'direccion': request.form.get('direccion'),
        'telefono': request.form.get('telefono'),
        'correo': request.form.get('correo'),
        'que_hace': request.form.get('que_hace'),
        'calendar_email': request.form.get('calendar_email')  # Nuevo campo para correo de notificaciones
    }
    
    # Manejar la subida del logo
    if 'app_logo' in request.files and request.files['app_logo'].filename != '':
        logo = request.files['app_logo']
        filename = secure_filename(f"logo_{int(time.time())}_{logo.filename}")
        upload_path = os.path.join(app.config['UPLOAD_FOLDER'], 'logos', filename)
        
        # Asegúrate de que la carpeta existe
        os.makedirs(os.path.dirname(upload_path), exist_ok=True)
        
        # Guardar el archivo
        logo.save(upload_path)
        
        # Guardar la ruta en la BD
        datos['app_logo'] = f"/static/uploads/logos/{filename}"
    elif request.form.get('app_logo_actual'):
        # Mantener el logo existente
        datos['app_logo'] = request.form.get('app_logo_actual')
    
    # Guardar en la base de datos
    conn = get_db_connection(config)
    cursor = conn.cursor()
    
    # Verificar si existe la columna calendar_email
    try:
        cursor.execute("SHOW COLUMNS FROM configuracion LIKE 'calendar_email'")
        calendar_email_existe = cursor.fetchone() is not None
        
        # Crear la columna si no existe
        if not calendar_email_existe:
            cursor.execute("ALTER TABLE configuracion ADD COLUMN calendar_email VARCHAR(255)")
        
        conn.commit()
    except Exception as e:
        app.logger.error(f"Error verificando/creando columna calendar_email: {e}")
    
    # Verificar si existe una configuración
    cursor.execute("SELECT COUNT(*) FROM configuracion")
    count = cursor.fetchone()[0]
    
    if count > 0:
        # Actualizar configuración existente
        set_parts = []
        values = []
        
        for key, value in datos.items():
            if value is not None:  # Solo incluir campos con valores
                set_parts.append(f"{key} = %s")
                values.append(value)
        
        sql = f"UPDATE configuracion SET {', '.join(set_parts)} WHERE id = 1"
        try:
            cursor.execute(sql, values)
        except Exception as e:
            app.logger.error(f"Error al actualizar configuración: {e}")
            # Filtrar columnas que causan problemas
            if "Unknown column" in str(e):
                # Obtener las columnas existentes
                cursor.execute("SHOW COLUMNS FROM configuracion")
                columnas_existentes = [col[0] for col in cursor.fetchall()]
                
                # Filtrar y volver a intentar
                set_parts = []
                values = []
                for key, value in datos.items():
                    if key in columnas_existentes and value is not None:
                        set_parts.append(f"{key} = %s")
                        values.append(value)
                
                if set_parts:
                    sql = f"UPDATE configuracion SET {', '.join(set_parts)} WHERE id = 1"
                    cursor.execute(sql, values)
    else:
        # Insertar nueva configuración
        fields = ', '.join(datos.keys())
        placeholders = ', '.join(['%s'] * len(datos))
        sql = f"INSERT INTO configuracion (id, {fields}) VALUES (1, {placeholders})"
        cursor.execute(sql, [1] + list(datos.values()))
    
    conn.commit()
    cursor.close()
    conn.close()
    
    flash("✅ Configuración guardada correctamente", "success")
    return redirect(url_for('configuracion_tab', tab='negocio', guardado=True))

@app.context_processor
def inject_app_config():
    # Obtener de la BD
    config = obtener_configuracion_por_host()
    
    # Conectar a la BD
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM configuracion WHERE id = 1")
        cfg = cursor.fetchone()
        cursor.close()
        conn.close()
        
        if cfg:
            # Usar ia_nombre como nombre de la aplicación
            return {
                'app_nombre': cfg.get('ia_nombre', 'SmartWhats'),
                'app_logo': cfg.get('app_logo')
            }
    except Exception as e:
        app.logger.error(f"Error obteniendo configuración: {e}")
    
    # Valores por defecto
    return {
        'app_nombre': 'SmartWhats',
        'app_logo': None
    }

def determinar_extension(mime_type, filename):
    """Determina la extensión del archivo basado en MIME type y nombre"""
    mime_to_extension = {
        'application/pdf': 'pdf',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',
        'application/vnd.ms-excel': 'xls',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
        'text/csv': 'csv',
        'text/plain': 'txt'
    }
    
    # Primero intentar por MIME type
    extension = mime_to_extension.get(mime_type)
    
    # Si no se encuentra, intentar por extensión del nombre de archivo
    if not extension and '.' in filename:
        extension = filename.split('.')[-1].lower()
    
    return extension or 'bin'

def extraer_texto_e_imagenes_pdf(file_path):
    """Extrae texto e imágenes de un archivo PDF"""
    try:
        texto = ""
        imagenes = []
        
        # Abrir el PDF con PyMuPDF
        doc = fitz.open(file_path)
        
        # Crear directorio para imágenes si no existe (tenant-aware fallback)
        try:
            productos_dir, tenant_slug = get_productos_dir_for_config()
            img_dir = productos_dir
        except Exception as e:
            app.logger.warning(f"⚠️ get_productos_dir_for_config falló, usando legacy uploads/productos. Error: {e}")
            img_dir = os.path.join(UPLOAD_FOLDER, 'productos')
        os.makedirs(img_dir, exist_ok=True)
        
        for page_num in range(len(doc)):
            page = doc.load_page(page_num)
            
            # Extraer texto
            texto += page.get_text()
            
            # Extraer imágenes
            image_list = page.get_images(full=True)
            for img_idx, img_info in enumerate(image_list):
                try:
                    xref = img_info[0]
                    
                    # Verificar si la imagen es válida antes de procesarla
                    try:
                        base_img = doc.extract_image(xref)
                        
                        # Obtener la imagen en bytes
                        imagen_bytes = base_img["image"]
                        
                        # Determinar formato de imagen
                        extension = base_img["ext"]
                        
                        # Crear nombre único para la imagen
                        img_filename = f"producto_{page_num+1}_{img_idx+1}_{int(time.time())}.{extension}"
                        img_path = os.path.join(img_dir, img_filename)
                        
                        # Guardar la imagen
                        with open(img_path, "wb") as img_file:
                            img_file.write(imagen_bytes)
                        
                        # Intentar obtener el rectángulo de la imagen de manera segura
                        try:
                            rect = page.get_image_bbox(xref)
                        except ValueError:
                            # Si falla, usar un rectángulo vacío
                            rect = fitz.Rect(0, 0, 0, 0)
                        
                        # Agregar a la lista de imágenes con metadatos útiles
                        imagenes.append({
                            'filename': img_filename,
                            'path': img_path,
                            'page': page_num,
                            'size': len(imagen_bytes),
                            'position': img_info[1:],  # Info de posición para asociar con texto
                            'xref': xref,
                            'rect': rect
                        })
                        
                        app.logger.info(f"✅ Imagen extraída: {img_filename} (tenant_dir={img_dir})")
                        
                    except Exception as e:
                        app.logger.warning(f"⚠️ Error extrayendo imagen específica {xref}: {e}")
                        continue
                        
                except Exception as e:
                    app.logger.warning(f"⚠️ Error procesando imagen {img_idx} en página {page_num+1}: {e}")
                    continue
        
        doc.close()
        
        app.logger.info(f"✅ Texto extraído: {len(texto)} caracteres")
        app.logger.info(f"🖼️ Imágenes extraídas: {len(imagenes)}")
        
        return texto.strip(), imagenes
        
    except Exception as e:
        app.logger.error(f"🔴 Error extrayendo contenido PDF: {e}")
        app.logger.error(traceback.format_exc())
        
        # Intenta al menos extraer el texto usando el método anterior
        try:
            texto = extraer_texto_pdf(file_path)
            app.logger.info(f"✅ Se pudo extraer texto con método alternativo: {len(texto)} caracteres")
            return texto, []  # Devolver texto pero sin imágenes
        except:
            return None, []

@app.route('/configuracion/precios/importar-excel', methods=['POST'])
def importar_excel_directo():
    """Importa datos directamente desde Excel sin análisis de IA"""
    config = obtener_configuracion_por_host()
    
    try:
        if 'excel_file' not in request.files:
            flash('❌ No se seleccionó ningún archivo', 'error')
            return redirect(url_for('configuracion_precios'))
        
        file = request.files['excel_file']
        if file.filename == '':
            flash('❌ No se seleccionó ningún archivo', 'error')
            return redirect(url_for('configuracion_precios'))
        
        if file and allowed_file(file.filename):
            # Guardar archivo temporalmente
            filename = secure_filename(f"excel_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
            filepath = os.path.join(PDF_UPLOAD_FOLDER, filename)
            file.save(filepath)
            # After file.save(filepath)
            imagenes_embedded = extraer_imagenes_embedded_excel(filepath)
            app.logger.info(f"🖼️ Imágenes embebidas extraídas: {len(imagenes_embedded)}")
            app.logger.info(f"📄 Excel guardado: {filepath}")
            
            # Procesar el archivo Excel
            productos_importados = importar_productos_desde_excel(filepath, config)
            
            # Eliminar el archivo temporal
            try:
                os.remove(filepath)
            except:
                pass
                
            if productos_importados > 0:
                flash(f'✅ {productos_importados} productos importados exitosamente', 'success')
            else:
                flash('⚠️ No se pudieron importar productos. Revisa el formato del archivo.', 'warning')
                
        else:
            flash('❌ Tipo de archivo no permitido. Solo se aceptan XLSX, XLS y CSV', 'error')
        
        return redirect(url_for('configuracion_precios'))
        
    except Exception as e:
        app.logger.error(f"🔴 Error importando Excel: {e}")
        app.logger.error(traceback.format_exc())
        flash(f'❌ Error procesando el archivo: {str(e)}', 'error')
        return redirect(url_for('configuracion_precios'))

def _extraer_imagenes_desde_zip_xlsx(filepath, output_dir):
    """
    Fallback: extrae imágenes desde el ZIP de un .xlsx leyendo xl/media/.
    Retorna lista de dicts compatible con extraer_imagenes_embedded_excel.
    """
    import zipfile, shutil
    os.makedirs(output_dir, exist_ok=True)
    imagenes = []
    try:
        with zipfile.ZipFile(filepath, 'r') as z:
            media_files = [f for f in z.namelist() if f.startswith('xl/media/')]
            for idx, media_path in enumerate(media_files):
                try:
                    ext = os.path.splitext(media_path)[1].lstrip('.').lower() or 'bin'
                    timestamp = int(time.time())
                    filename = f"excel_unzip_img_{idx+1}_{timestamp}.{ext}"
                    dest_path = os.path.join(output_dir, filename)
                    with z.open(media_path) as src, open(dest_path, 'wb') as dst:
                        shutil.copyfileobj(src, dst)
                    imagenes.append({
                        'filename': filename,
                        'path': dest_path,
                        'sheet': None,
                        'anchor': None,
                        'row': None,
                        'col': None
                    })
                    app.logger.info(f"✅ Imagen (zip) extraída: {filename} from {media_path}")
                except Exception as e:
                    app.logger.warning(f"⚠️ No se pudo extraer {media_path} desde zip: {e}")
    except zipfile.BadZipFile:
        app.logger.warning("⚠️ Archivo no es un .xlsx válido o está corrupto; zip fallback falló")
    except Exception as e:
        app.logger.warning(f"⚠️ Error extrayendo imágenes desde zip: {e}")
    return imagenes

def get_docs_dir_for_config(config=None):
    """Return (docs_dir, tenant_slug). Ensures uploads/docs/<tenant_slug> exists."""
    if config is None:
        try:
            from flask import has_request_context
            if has_request_context():
                config = obtener_configuracion_por_host()
            else:
                config = NUMEROS_CONFIG['524495486142']
        except Exception:
            config = NUMEROS_CONFIG['524495486142']

    dominio = (config.get('dominio') or '').strip().lower()
    tenant_slug = dominio.split('.')[0] if dominio else 'default'
    docs_dir = os.path.join(app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER), 'docs', tenant_slug)
    try:
        os.makedirs(docs_dir, exist_ok=True)
    except Exception as e:
        app.logger.warning(f"⚠️ No se pudo crear docs_dir {docs_dir}: {e}")
        # fallback to a shared docs dir
        docs_dir = os.path.join(app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER), 'docs')
        os.makedirs(docs_dir, exist_ok=True)
    return docs_dir, tenant_slug

def importar_productos_desde_excel(filepath, config=None):
    """Importa productos desde Excel; guarda metadatos de imágenes y usa fallback unzip si openpyxl no encuentra imágenes."""
    if config is None:
        config = obtener_configuracion_por_host()

    try:
        extension = os.path.splitext(filepath)[1].lower()
        if extension in ['.xlsx', '.xls']:
            df = pd.read_excel(filepath, sheet_name=0)
            wb = openpyxl.load_workbook(filepath, data_only=True)
            sheet_name = wb.sheetnames[0]
        elif extension == '.csv':
            df = pd.read_csv(filepath)
            sheet_name = None
            wb = None
        else:
            app.logger.error(f"Formato de archivo no soportado: {extension}")
            return 0

        df.columns = [col.lower().strip() if isinstance(col, str) else col for col in df.columns]
        app.logger.info(f"Columnas disponibles en el archivo: {list(df.columns)}")

        column_mapping = {
            'sku': 'sku',
            'categoria': 'categoria',
            'subcategoria': 'subcategoria',
            'linea': 'linea',
            'modelo': 'modelo',
            'descripcion': 'descripcion',
            'medidas': 'medidas',
            'costo': 'costo',
            'precio mayoreo': 'precio_mayoreo',
            'precio menudeo': 'precio_menudeo',
            'imagen': 'imagen',
            'status ws': 'status_ws',
            'catalogo': 'catalogo',
            'catalogo 2': 'catalogo2',
            'catalogo 3': 'catalogo3',
            'proveedor': 'proveedor'
        }

        for excel_col, db_col in column_mapping.items():
            if excel_col in df.columns:
                df = df.rename(columns={excel_col: db_col})
                app.logger.info(f"Columna mapeada: {excel_col} -> {db_col}")

        app.logger.info(f"Primeras 2 filas para verificar:\n{df.head(2).to_dict('records')}")

        # 1) Intento principal con openpyxl
        imagenes_embedded = extraer_imagenes_embedded_excel(filepath)
        app.logger.info(f"🖼️ Imágenes detectadas por openpyxl: {len(imagenes_embedded)}")

        # 2) Fallback: si ninguna imagen detectada y .xlsx, extraer desde zip (xl/media) usando tenant dir
        if not imagenes_embedded and extension == '.xlsx':
            try:
                output_dir, tenant_slug = get_productos_dir_for_config(config)
            except Exception as e:
                app.logger.warning(f"⚠️ get_productos_dir_for_config falló para fallback ZIP, usando legacy. Error: {e}")
                output_dir = os.path.join(UPLOAD_FOLDER, 'productos')
            imagenes_zip = _extraer_imagenes_desde_zip_xlsx(filepath, output_dir)
            if imagenes_zip:
                imagenes_embedded = imagenes_zip
                app.logger.info(f"🖼️ Fallback ZIP: imágenes extraídas desde xl/media -> {len(imagenes_embedded)} (dir={output_dir})")
            else:
                app.logger.info("⚠️ Fallback ZIP no encontró imágenes")

        # Preparar conexión (se usará tanto para registrar imágenes como para insertar productos)
        conn = get_db_connection(config)
        cursor = conn.cursor()

        # Crear tabla para metadatos de imágenes si no existe
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS imagenes_productos (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    sku VARCHAR(100) DEFAULT NULL,
                    filename VARCHAR(255) NOT NULL,
                    path VARCHAR(512) NOT NULL,
                    sheet VARCHAR(128),
                    row_num INT DEFAULT NULL,
                    col_num INT DEFAULT NULL,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_filename (filename)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            conn.commit()
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo asegurar tabla imagenes_productos: {e}")

        # Insertar/Actualizar metadatos de las imágenes extraídas en la BD
        try:
            for img in imagenes_embedded:
                filename = img.get('filename')
                path = img.get('path')
                sheet = img.get('sheet')
                row_num = img.get('row')
                col_num = img.get('col')
                try:
                    cursor.execute("""
                        INSERT INTO imagenes_productos (sku, filename, path, sheet, row_num, col_num)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            path=VALUES(path),
                            sheet=VALUES(sheet),
                            row_num=VALUES(row_num),
                            col_num=VALUES(col_num),
                            created_at = CURRENT_TIMESTAMP
                    """, (None, filename, path, sheet, row_num, col_num))
                except Exception as e:
                    app.logger.warning(f"⚠️ Error insertando metadato imagen {filename}: {e}")
            conn.commit()
            app.logger.info(f"🗄️ Metadatos de {len(imagenes_embedded)} imágenes guardados/actualizados en BD")
        except Exception as e:
            app.logger.error(f"🔴 Error guardando metadatos de imágenes: {e}")

        # Build map by (sheet, row) from extracted list (fallback local)
        images_map = {}
        for img in imagenes_embedded:
            s = img.get('sheet')
            r = img.get('row')
            # If sheet is None (zip fallback), we cannot map by row -> keep for fallback list
            if r is not None:
                images_map[(s, r)] = img['filename']

        app.logger.info(f"🖼️ Imágenes con ancla detectadas: {len(images_map)}")

        # If no images had anchors, we'll fallback to index-based assignment
        fallback_by_index = []
        if imagenes_embedded and not images_map:
            fallback_by_index = [img['filename'] for img in imagenes_embedded]
            app.logger.info(f"⚠️ No se detectaron anclas; usando fallback por orden con {len(fallback_by_index)} imágenes")

        if df.empty:
            app.logger.error("El archivo no contiene datos (está vacío)")
            cursor.close(); conn.close()
            return 0

        app.logger.info(f"Total de filas encontradas: {len(df)}")
        df = df.fillna('')

        campos_esperados = [
            'sku', 'categoria', 'subcategoria', 'linea', 'modelo',
            'descripcion', 'medidas', 'costo', 'precio_mayoreo', 'precio_menudeo',
            'imagen', 'status_ws', 'catalogo', 'catalogo2', 'catalogo3', 'proveedor'
        ]

        productos_importados = 0
        filas_procesadas = 0
        filas_omitidas = 0

        header_row = 1
        for idx, row in df.iterrows():
            filas_procesadas += 1
            try:
                producto = {}
                excel_row_number = header_row + 1 + idx  # idx 0-based
                assigned_image = ''

                # 1) prefer column value if present
                if 'imagen' in df.columns and str(row.get('imagen', '')).strip():
                    assigned_image = str(row.get('imagen')).strip()
                else:
                    # 2) try anchored image
                    if sheet_name and images_map.get((sheet_name, excel_row_number)):
                        assigned_image = images_map.get((sheet_name, excel_row_number))
                    else:
                        # 3) fallback by index order if available
                        if fallback_by_index and idx < len(fallback_by_index):
                            assigned_image = fallback_by_index[idx]
                        else:
                            assigned_image = ''

                for campo in campos_esperados:
                    if campo == 'imagen':
                        producto['imagen'] = assigned_image or ''
                        continue
                    if campo in df.columns:
                        producto[campo] = row.get(campo, '') if row.get(campo, '') is not None else ''
                    else:
                        producto[campo] = ''

                tiene_datos = any(str(value).strip() for value in producto.values())
                if not tiene_datos:
                    app.logger.warning(f"Fila {idx} omitida: sin ningún dato")
                    filas_omitidas += 1
                    continue

                for campo in campos_esperados:
                    if not str(producto.get(campo, '')).strip():
                        producto[campo] = " "

                for campo in ['costo', 'precio_mayoreo', 'precio_menudeo']:
                    try:
                        valor = producto.get(campo, '')
                        valor_str = str(valor).strip()
                        if not valor_str:
                            producto[campo] = '0.00'
                        else:
                            match = re.search(r'(\d+(?:\.\d+)?)', valor_str)
                            if match:
                                valor_numerico = float(match.group(1))
                                producto[campo] = f"{valor_numerico:.2f}"
                            else:
                                producto[campo] = '0.00'
                    except Exception:
                        producto[campo] = '0.00'

                if producto.get('status_ws', '').startswith('nadita'):
                    producto['status_ws'] = 'activo'

                values = [
                    producto.get('sku', ''),
                    producto.get('categoria', ''),
                    producto.get('subcategoria', ''),
                    producto.get('linea', ''),
                    producto.get('modelo', ''),
                    producto.get('descripcion', ''),
                    producto.get('medidas', ''),
                    producto.get('costo', '0.00'),
                    producto.get('precio_mayoreo', '0.00'),
                    producto.get('precio_menudeo', '0.00'),
                    producto.get('imagen', ''),
                    producto.get('status_ws', 'activo'),
                    producto.get('catalogo', ''),
                    producto.get('catalogo2', ''),
                    producto.get('catalogo3', ''),
                    producto.get('proveedor', '')
                ]

                cursor.execute("""
                    INSERT INTO precios (
                        sku, categoria, subcategoria, linea, modelo,
                        descripcion, medidas, costo, precio_mayoreo, precio_menudeo,
                        imagen, status_ws, catalogo, catalogo2, catalogo3, proveedor
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                        categoria=VALUES(categoria),
                        subcategoria=VALUES(subcategoria),
                        descripcion=VALUES(descripcion),
                        costo=VALUES(costo),
                        precio_mayoreo=VALUES(precio_mayoreo),
                        precio_menudeo=VALUES(precio_menudeo),
                        status_ws=VALUES(status_ws),
                        imagen=VALUES(imagen)
                """, values)

                # Si asignamos una imagen, actualizar también la fila de imagenes_productos.sku con el sku recién insertado
                try:
                    if producto.get('imagen'):
                        sku_val = producto.get('sku', '').strip() or None
                        if sku_val:
                            cursor.execute("""
                                UPDATE imagenes_productos
                                   SET sku = %s
                                 WHERE filename = %s
                            """, (sku_val, producto.get('imagen')))
                except Exception as e:
                    app.logger.warning(f"⚠️ No se pudo actualizar SKU en imagenes_productos para {producto.get('imagen')}: {e}")

                productos_importados += 1
                app.logger.info(f"✅ Producto importado: {producto.get('sku')[:50]}... imagen={producto.get('imagen')}")
            except Exception as e:
                app.logger.error(f"Error procesando fila {idx}: {e}")
                app.logger.error(traceback.format_exc())
                filas_omitidas += 1
                continue

        conn.commit()
        cursor.close()
        conn.close()

        app.logger.info(f"📊 Resumen de importación: {productos_importados} productos importados, {filas_procesadas} filas procesadas, {filas_omitidas} filas omitidas")
        return productos_importados

    except Exception as e:
        app.logger.error(f"🔴 Error en importar_productos_desde_excel: {e}")
        app.logger.error(traceback.format_exc())
        return 0

def obtener_imagenes_por_sku(sku, config=None):
    """Obtiene todas las imágenes asociadas a un SKU específico"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT filename, path, sheet, row_num, col_num, created_at
            FROM imagenes_productos
            WHERE sku = %s
            ORDER BY created_at DESC
        """, (sku,))
        
        imagenes = cursor.fetchall()
        cursor.close()
        conn.close()
        
        return imagenes
    except Exception as e:
        app.logger.error(f"Error obteniendo imágenes para SKU {sku}: {e}")
        return []

@app.route('/uploads/productos/<filename>')
def serve_product_image(filename):
    """Sirve imágenes de productos desde la carpeta tenant-aware:
       uploads/productos/<tenant_slug>/<filename>
       Hace fallback a uploads/productos/ y luego a uploads/ si no se encuentra."""
    try:
        config = obtener_configuracion_por_host()
        productos_dir, tenant_slug = get_productos_dir_for_config(config)

        # 1) Intentar carpeta tenant específica
        candidate = os.path.join(productos_dir, filename)
        if os.path.isfile(candidate):
            return send_from_directory(productos_dir, filename)

        # 2) Fallback: carpeta legacy uploads/productos/
        legacy_dir = os.path.join(app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER), 'productos')
        candidate_legacy = os.path.join(legacy_dir, filename)
        if os.path.isfile(candidate_legacy):
            return send_from_directory(legacy_dir, filename)

        # 3) Fallback adicional: raíz de uploads/
        root_candidate = os.path.join(app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER), filename)
        if os.path.isfile(root_candidate):
            return send_from_directory(app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER), filename)

        # No encontrado
        app.logger.info(f"❌ Imagen no encontrada: {filename} (tenant={tenant_slug})")
        abort(404)
    except Exception as e:
        app.logger.error(f"🔴 Error sirviendo imagen {filename}: {e}")
        abort(500)

def asociar_imagenes_productos(servicios, imagenes):
    """Asocia imágenes extraídas con los productos correspondientes usando IA"""
    if not imagenes or not servicios or not servicios.get('servicios'):
        return servicios
    
    try:
        app.logger.info(f"🔄 Asociando {len(imagenes)} imágenes con {len(servicios['servicios'])} productos")
        
        # Asignar imágenes a productos según su posición en la lista
        # Esta es una asignación simple; podría mejorarse con análisis de contenido
        for i, servicio in enumerate(servicios['servicios']):
            # Asignar una imagen si está disponible (rotación cíclica si hay menos imágenes que productos)
            if imagenes:
                img_index = i % len(imagenes)
                img_filename = imagenes[img_index]['filename']
                servicio['imagen'] = img_filename
                app.logger.info(f"✅ Producto '{servicio['servicio']}' asociado con imagen: {img_filename}")
            else:
                servicio['imagen'] = ''
        
        return servicios
        
    except Exception as e:
        app.logger.error(f"🔴 Error asociando imágenes: {e}")
        return servicios

def asociar_imagenes_con_ia(servicios, imagenes, texto_pdf):
    """Versión avanzada: Usa OpenAI para asociar imágenes a productos basado en contexto"""
    if not imagenes or not servicios or not servicios.get('servicios'):
        return servicios
    
    try:
        # Convertir algunas imágenes a base64 para análisis con OpenAI
        imagenes_analisis = []
        for idx, img in enumerate(imagenes[:min(5, len(imagenes))]):  # Analizar máximo 5 imágenes
            try:
                with open(img['path'], 'rb') as img_file:
                    img_data = base64.b64encode(img_file.read()).decode('utf-8')
                    imagenes_analisis.append({
                        'index': idx,
                        'filename': img['filename'],
                        'base64': f"data:image/jpeg;base64,{img_data}"
                    })
            except Exception as e:
                app.logger.error(f"Error codificando imagen {img['path']}: {e}")
        
        if not imagenes_analisis:
            return servicios
        
        # Preparar prompt para OpenAI
        productos_texto = "\n".join([
            f"{i+1}. {p.get('servicio', 'Producto')}: {p.get('descripcion', 'Sin descripción')}"
            for i, p in enumerate(servicios['servicios'][:20])  # Máximo 20 productos
        ])
        
        prompt = f"""
        Analiza estas imágenes de productos y asocia cada una con el producto correcto de la lista.
        
        PRODUCTOS DETECTADOS:
        {productos_texto}
        
        Para cada imagen, responde con el formato JSON:
        {{
            "imagen_filename": "nombre_archivo.jpg",
            "producto_index": 3,  # índice del producto en la lista (comenzando desde 1)
            "confianza": 0.85,  # qué tan seguro estás (0-1)
            "razon": "Breve explicación"
        }}
        
        Responde SOLO con un array JSON de estas asociaciones.
        """
        
        # Configurar payload para GPT-4V
        client = OpenAI(api_key=OPENAI_API_KEY)
        messages = [{"role": "user", "content": []}]
        
        # Agregar texto del prompt
        messages[0]["content"].append({"type": "text", "text": prompt})
        
        # Agregar imágenes
        for img in imagenes_analisis:
            messages[0]["content"].append({
                "type": "image_url",
                "image_url": {"url": img['base64']}
            })
        
        # Realizar la consulta
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=2000
        )
        
        # Procesar respuesta
        text_response = response.choices[0].message.content
        
        # Extraer JSON
        json_match = re.search(r'\[.*\]', text_response, re.DOTALL)
        if json_match:
            asociaciones = json.loads(json_match.group())
            
            # Asociar imágenes según análisis de AI
            for asoc in asociaciones:
                if asoc.get('confianza', 0) > 0.6:  # Solo asociaciones con confianza razonable
                    img_filename = asoc.get('imagen_filename')
                    producto_idx = asoc.get('producto_index')
                    
                    if producto_idx and 1 <= producto_idx <= len(servicios['servicios']):
                        servicios['servicios'][producto_idx-1]['imagen'] = img_filename
                        app.logger.info(f"✅ IA asoció '{img_filename}' con '{servicios['servicios'][producto_idx-1].get('servicio')}' (confianza: {asoc.get('confianza')})")
        
        return servicios
        
    except Exception as e:
        app.logger.error(f"🔴 Error en asociación IA: {e}")
        app.logger.error(traceback.format_exc())
        # Fallback a asociación simple
        return asociar_imagenes_productos(servicios, imagenes)

# Nueva función: analiza una imagen (base64) junto con contexto y devuelve texto de respuesta
def analizar_imagen_y_responder(numero, imagen_base64, caption, public_url=None, config=None):
    """
    Analiza una imagen recibida por WhatsApp y genera una respuesta usando IA.
    - numero: número del usuario que envió la imagen
    - imagen_base64: data:image/...;base64,... (string) o None
    - caption: texto que acompañó la imagen
    - public_url: ruta pública donde se guardó la imagen (opcional)
    - config: tenant config opcional
    Retorna: texto de respuesta (string) o None si falla
    """
    if config is None:
        config = obtener_configuracion_por_host()

    try:
        # 1) Obtener catálogo resumido para contexto (limitado para no exceder tokens)
        precios = obtener_todos_los_precios(config) or []
        productos_lines = []
        for p in precios[:1000]:
            nombre = (p.get('servicio') or p.get('modelo') or p.get('sku') or '')[:120]
            sku = (p.get('sku') or '').strip()
            precio = p.get('precio_menudeo') or p.get('precio') or p.get('costo') or ''
            imagen = p.get('imagen') or ''
            productos_lines.append(f"- {nombre} | SKU:{sku} | Precio:{precio} | Imagen:{imagen}")

        productos_texto = "\n".join(productos_lines) if productos_lines else "No hay productos cargados."

        # 2) Construir prompt claro para la IA multimodal
        system_prompt = (
            "Eres un asistente que identifica productos y contexto a partir de imágenes recibidas por WhatsApp. "
            "Usa SOLO la información disponible en el catálogo y el historial para responder al cliente. "
            "Si la imagen coincide con un producto del catálogo, responde con el nombre del producto, SKU, precio y una breve recomendación. "
            "Si no puedes identificar, pregunta al usuario por más detalles (por ejemplo: '¿Qué SKU o nombre tiene este producto?'). "
            "Mantén la respuesta breve y orientada al cliente."
        )

        user_content = [
            {"type": "text", "text": f"Usuario: {numero}\nCaption: {caption or ''}\nCatalogo (resumido):\n{productos_texto}"},
        ]

        # 3) Adjuntar la imagen (si viene base64) para que el modelo la analice
        if imagen_base64:
            user_content.append({
                "type": "image_url",
                "image_url": {"url": imagen_base64}
            })
        elif public_url:
            # fallback a la URL pública si no hay base64
            user_content.append({
                "type": "image_url",
                "image_url": {"url": public_url}
            })

        # 4) Llamada al cliente OpenAI (misma forma que ya usas en otras funciones)
        client_local = OpenAI(api_key=OPENAI_API_KEY)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        # Preferir modelo multimodal disponible en tu stack (ejemplo re-uso de gpt-4o en el repo)
        response = client_local.chat.completions.create(
            model="gpt-4o",  # ajusta si usas otro modelo
            messages=messages,
            max_tokens=800,
            temperature=0.2
        )

        # Extraer texto resultante
        text_response = ""
        try:
            text_response = response.choices[0].message.content
            if isinstance(text_response, list):
                # si viene como estructura multimodal, concatenar textos
                parts = []
                for item in text_response:
                    if isinstance(item, dict) and item.get('type') == 'text' and item.get('text'):
                        parts.append(item.get('text'))
                    elif isinstance(item, str):
                        parts.append(item)
                text_response = "\n".join(parts)
        except Exception:
            # Fallback a raw string si la estructura es diferente
            try:
                text_response = str(response)
            except:
                text_response = None

        if not text_response:
            app.logger.info("ℹ️ IA no devolvió texto útil al analizar la imagen")
            return None

        # 5) Post-procesado: limpiar espacios excesivos
        text_response = re.sub(r'\n\s+\n', '\n\n', text_response).strip()
        return text_response

    except Exception as e:
        app.logger.error(f"🔴 Error en analizar_imagen_y_responder: {e}")
        app.logger.error(traceback.format_exc())
        return None

def extraer_texto_archivo(filepath, extension):
    """Extrae texto de diferentes tipos de archivos"""
    try:
        if extension == 'pdf':
            return extraer_texto_pdf(filepath)
        
        elif extension in ['xlsx', 'xls']:
            return extraer_texto_excel(filepath)
        
        elif extension == 'csv':
            return extraer_texto_csv(filepath)
        
        elif extension == 'docx':
            return extraer_texto_docx(filepath)
        
        elif extension == 'txt':
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        
        else:
            app.logger.warning(f"⚠️ Formato no soportado: {extension}")
            return None
            
    except Exception as e:
        app.logger.error(f"🔴 Error extrayendo texto de {extension}: {e}")
        return None

def extraer_texto_excel(filepath):
    """Extrae texto de archivos Excel"""
    try:
        texto = ""
        
        # Leer todas las hojas
        if filepath.endswith('.xlsx'):
            workbook = openpyxl.load_workbook(filepath)
            for sheet_name in workbook.sheetnames:
                sheet = workbook[sheet_name]
                texto += f"\n--- Hoja: {sheet_name} ---\n"
                
                for row in sheet.iter_rows(values_only=True):
                    fila_texto = " | ".join(str(cell) for cell in row if cell is not None)
                    if fila_texto.strip():
                        texto += fila_texto + "\n"
        
        # Alternativa con pandas para mejor compatibilidad
        try:
            excel_file = pd.ExcelFile(filepath)
            for sheet_name in excel_file.sheet_names:
                df = pd.read_excel(filepath, sheet_name=sheet_name)
                texto += f"\n--- Hoja: {sheet_name} (Pandas) ---\n"
                texto += df.to_string() + "\n"
        except Exception as e:
            app.logger.warning(f"⚠️ Pandas falló: {e}")
        
        return texto.strip() if texto.strip() else None
        
    except Exception as e:
        app.logger.error(f"🔴 Error procesando Excel: {e}")
        return None

def extraer_texto_csv(filepath):
    """Extrae texto de archivos CSV"""
    try:
        df = pd.read_csv(filepath)
        return df.to_string()
    except Exception as e:
        app.logger.error(f"🔴 Error leyendo CSV: {e}")
        # Intentar lectura simple
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read()
        except:
            return None

def extraer_texto_docx(filepath):
    """Extrae texto de archivos Word"""
    try:
        doc = Document(filepath)
        texto = ""
        for paragraph in doc.paragraphs:
            texto += paragraph.text + "\n"
        return texto.strip() if texto.strip() else None
    except Exception as e:
        app.logger.error(f"🔴 Error leyendo DOCX: {e}")
        return None

def analizar_archivo_con_ia(texto_archivo, tipo_negocio, config=None):
    """Analiza el contenido del archivo usando IA"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        if tipo_negocio == 'laporfirianna':
            prompt = f"""
            Eres un asistente especializado en analizar documentos para restaurantes.
            Analiza el siguiente contenido extraído de un archivo y proporciona un resumen útil:
            
            CONTENIDO DEL ARCHIVO:
            {texto_archivo[:80000]}  # Limitar tamaño para evitar tokens excesivos
            
            Proporciona un análisis en este formato:
            
            📊 **ANÁLISIS DEL DOCUMENTO**
            
            **Tipo de contenido detectado:** [Menú, Inventario, Pedidos, etc.]
            
            **Información clave encontrada:**
            - Platillos/productos principales
            - Precios (si están disponibles)
            - Cantidades o inventarios
            - Fechas o periodos relevantes
            
            **Resumen ejecutivo:** [2-3 frases con lo más importante]
            
            **Recomendaciones:** [Cómo podría usar esta información]
            """
        else:
            prompt = f"""
            Eres un asistente especializado en analizar documentos para servicios digitales.
            Analiza el siguiente contenido extraído de un archivo y proporciona un resumen útil:
            
            CONTENIDO DEL ARCHIVO:
            {texto_archivo[:80000]}
            
            Proporciona un análisis en este formato:
            
            📊 **ANÁLISIS DEL DOCUMENTO**
            
            **Tipo de contenido detectado:** [Cotización, Requerimientos, Proyecto, etc.]
            
            **Información clave encontrada:**
            - Servicios solicitados
            - Presupuestos o costos
            - Especificaciones técnicas
            - Plazos o fechas importantes
            
            **Resumen ejecutivo:** [2-3 frases con lo más importante]
            
            **Recomendaciones:** [Siguientes pasos sugeridos]
            """
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 1500
        }
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        
        data = response.json()
        analisis = data['choices'][0]['message']['content'].strip()
        
        app.logger.info("✅ Archivo analizado con IA exitosamente")
        return analisis
        
    except Exception as e:
        app.logger.error(f"🔴 Error analizando archivo con IA: {e}")
        return "❌ No pude analizar el archivo en este momento. Por favor, describe brevemente qué contiene."


def extraer_texto_pdf(file_path):
    """Extrae texto de un archivo PDF"""
    try:
        texto = ""
        
        # Intentar con PyMuPDF primero (más robusto)
        try:
            doc = fitz.open(file_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                texto += page.get_text()
            doc.close()
            app.logger.info(f"✅ Texto extraído con PyMuPDF: {len(texto)} caracteres")
            return texto.strip()
        except Exception as e:
            app.logger.warning(f"⚠️ PyMuPDF falló, intentando con PyPDF2: {e}")
        
        # Fallback a PyPDF2
        with open(file_path, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                texto += page.extract_text()
        
        app.logger.info(f"✅ Texto extraído con PyPDF2: {len(texto)} caracteres")
        return texto.strip()
        
    except Exception as e:
        app.logger.error(f"🔴 Error extrayendo texto PDF: {e}")
        return None


def analizar_pdf_servicios(texto_pdf, config=None):
    """Usa IA para analizar el PDF y extraer servicios y precios - VERSIÓN MEJORADA"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # Limitar el texto para evitar tokens excesivos
        texto_limitado = texto_pdf[:40000]  # Mantenemos un límite razonable
        
        app.logger.info(f"📊 Texto a analizar: {len(texto_limitado)} caracteres")
        
        # Determinar el tipo de negocio para el prompt
        es_porfirianna = 'laporfirianna' in config.get('dominio', '')
        
        # PROMPT MÁS ESTRICTO Y OPTIMIZADO - con menos caracteres para evitar errores
        if es_porfirianna:
            prompt = f"""Extrae los productos del siguiente texto como JSON:
{texto_limitado[:15000]}
Formato: {{"servicios":[{{"sku":"","servicio":"NOMBRE_PLATILLO","categoria":"COMIDA","descripcion":"DESC","precio":"100.00","precio_mayoreo":"","precio_menudeo":"","costo":"70.00","moneda":"MXN","imagen":"","status_ws":"activo","catalogo":"La Porfirianna"}}]}}
Solo extrae hasta 20 productos principales."""
        else:
            prompt = f"""Extrae los servicios del siguiente texto como JSON:
{texto_limitado[:15000]}
Formato: {{"servicios":[{{"sku":"","servicio":"NOMBRE_SERVICIO","categoria":"CATEGORIA","descripcion":"DESC","precio":"5000.00","precio_mayoreo":"","precio_menudeo":"","costo":"3500.00","moneda":"MXN","imagen":"","status_ws":"activo","catalogo":"Mektia"}}]}}
Solo extrae hasta 20 servicios principales."""
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Payload simplificado para evitar errores
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 4000
        }
        
        app.logger.info("🔄 Enviando PDF a IA para análisis...")
        
        # Añadir más logs para diagnóstico
        app.logger.info(f"🔍 API URL: {DEEPSEEK_API_URL}")
        app.logger.info(f"🔍 Headers: {json.dumps({k: '***' if k == 'Authorization' else v for k, v in headers.items()})}")
        app.logger.info(f"🔍 Payload: {json.dumps(payload)[:500]}...")
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=180)
        
        # Log detallado de la respuesta para diagnóstico
        app.logger.info(f"🔍 Response status: {response.status_code}")
        
        if response.status_code != 200:
            app.logger.error(f"🔴 Error response from API: {response.text[:1000]}")
            return None
            
        response.raise_for_status()
        
        data = response.json()
        respuesta_ia = data['choices'][0]['message']['content'].strip()
        
        app.logger.info(f"✅ Respuesta IA recibida: {len(respuesta_ia)} caracteres")
        
        # INTENTAR MÚLTIPLES MÉTODOS DE EXTRACCIÓN JSON
        servicios_extraidos = None
        
        # Método 1: Buscar JSON con regex
        json_match = re.search(r'\{.*\}', respuesta_ia, re.DOTALL)
        if json_match:
            try:
                json_str = json_match.group()
                servicios_extraidos = json.loads(json_str)
                app.logger.info("✅ JSON extraído con regex")
            except json.JSONDecodeError as e:
                app.logger.warning(f"⚠️ JSON regex falló: {e}")
        
        # Método 2: Intentar parsear directamente
        if not servicios_extraidos:
            try:
                servicios_extraidos = json.loads(respuesta_ia)
                app.logger.info("✅ JSON parseado directamente")
            except json.JSONDecodeError as e:
                app.logger.warning(f"⚠️ JSON directo falló: {e}")
        
        # Validar estructura final
        if servicios_extraidos and 'servicios' in servicios_extraidos:
            if isinstance(servicios_extraidos['servicios'], list):
                app.logger.info(f"✅ JSON válido: {len(servicios_extraidos['servicios'])} servicios")
                
                # Limpiar y validar servicios
                servicios_limpios = []
                for servicio in servicios_extraidos['servicios']:
                    servicio_limpio = validar_y_limpiar_servicio(servicio)
                    if servicio_limpio:
                        servicios_limpios.append(servicio_limpio)
                
                servicios_extraidos['servicios'] = servicios_limpios
                app.logger.info(f"🎯 Servicios después de limpieza: {len(servicios_limpios)}")
                
                return servicios_extraidos
        
        # Si llegamos aquí, todos los métodos fallaron
        app.logger.error("❌ Todos los métodos de extracción JSON fallaron")
        app.logger.error(f"📄 Respuesta IA problemática (primeros 1000 chars): {respuesta_ia[:1000]}...")
        return None
            
    except requests.exceptions.Timeout:
        app.logger.error("🔴 Timeout analizando PDF con IA")
        return None
    except requests.exceptions.RequestException as e:
        app.logger.error(f"🔴 Error de conexión con IA: {e}")
        if hasattr(e, 'response') and e.response:
            app.logger.error(f"🔴 Detalles de error: {e.response.text[:1000]}")
        return None
    except Exception as e:
        app.logger.error(f"🔴 Error inesperado analizando PDF: {e}")
        app.logger.error(traceback.format_exc())
        return None
def validar_y_limpiar_servicio(servicio):
    """Valida y limpia los datos de un servicio individual - VERSIÓN ROBUSTA"""
    try:
        if not isinstance(servicio, dict):
            app.logger.warning("⚠️ Servicio no es diccionario, omitiendo")
            return None
        
        servicio_limpio = {}
        
        # Campos obligatorios mínimos
        if not servicio.get('servicio'):
            app.logger.warning("⚠️ Servicio sin nombre, omitiendo")
            return None
        
        # Campos de texto con valores por defecto
        campos_texto = {
            'sku': '',
            'categoria': 'General',
            'subcategoria': '',
            'linea': '',
            'modelo': '',
            'descripcion': '',
            'medidas': '',
            'imagen': '',
            'status_ws': 'activo',
            'catalogo': '',
            'catalogo2': '',
            'catalogo3': '',
            'proveedor': ''
        }
        
        for campo, valor_default in campos_texto.items():
            valor = servicio.get(campo, valor_default)
            servicio_limpio[campo] = str(valor).strip() if valor else valor_default
        
        # Campos de precio - conversión robusta
        campos_precio = ['precio_mayoreo', 'precio_menudeo', 'costo']  # Agregado "costo"
        for campo in campos_precio:
            valor = servicio.get(campo, '0.00')
            precio_limpio = "0.00"
            
            try:
                if valor:
                    # Remover todo excepto números y punto
                    valor_limpio = re.sub(r'[^\d.]', '', str(valor))
                    if valor_limpio:
                        # Convertir a float y formatear
                        precio_float = float(valor_limpio)
                        precio_limpio = f"{precio_float:.2f}"
            except (ValueError, TypeError):
                pass  # Mantener "0.00" en caso de error
            
            servicio_limpio[campo] = precio_limpio
        
        app.logger.info(f"✅ Servicio validado: {servicio_limpio['servicio']}")
        return servicio_limpio
        
    except Exception as e:
        app.logger.error(f"🔴 Error validando servicio: {e}")
        return None

def guardar_servicios_desde_pdf(servicios, config=None):
    """Guarda los servicios extraídos del PDF en la base de datos"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        if not servicios or not servicios.get('servicios'):
            app.logger.error("❌ No hay servicios para guardar")
            return 0
        
        conn = get_db_connection(config)
        cursor = conn.cursor()
        servicios_guardados = 0
        
        # Verificar columna costo
        try:
            cursor.execute("SHOW COLUMNS FROM precios LIKE 'costo'")
            columna_existe = cursor.fetchone()
            
            if not columna_existe:
                app.logger.info("🔧 Columna 'costo' no existe, creándola...")
                cursor.execute("ALTER TABLE precios ADD COLUMN costo DECIMAL(10,2) DEFAULT 0.00 AFTER precio")
                conn.commit()
        except Exception as e:
            app.logger.error(f"❌ Error verificando/creando columna 'costo': {e}")
        
        for servicio in servicios['servicios']:
            try:
                # Handle image if present
                imagen_nombre = servicio.get('imagen', '')
                if imagen_nombre:
                    # Check if image exists
                    img_path = os.path.join(UPLOAD_FOLDER, 'productos', imagen_nombre)
                    if os.path.exists(img_path):
                        app.logger.info(f"✅ Imagen encontrada para {servicio.get('servicio')}: {imagen_nombre}")
                    else:
                        imagen_nombre = ''  # Reset if image doesn't exist
                        app.logger.warning(f"⚠️ Imagen no encontrada: {img_path}")
            
                # Preparar campos
                campos = [
                    servicio.get('sku', '').strip(),
                    servicio.get('categoria', '').strip(),
                    servicio.get('subcategoria', '').strip(),
                    servicio.get('linea', '').strip(),
                    servicio.get('modelo', '').strip(),
                    servicio.get('descripcion', '').strip(),
                    servicio.get('medidas', '').strip(),
                    servicio.get('costo', '0.00'),
                    servicio.get('precio_mayoreo', '0.00'),
                    servicio.get('precio_menudeo', '0.00'),
                    imagen_nombre,
                    servicio.get('status_ws', 'activo').strip(),
                    servicio.get('catalogo', '').strip(),
                    servicio.get('catalogo2', '').strip(),
                    servicio.get('catalogo3', '').strip(),
                    servicio.get('proveedor', '').strip(),
                ]
            
                # Validar precios
                for i in [8, 9, 10, 11]:  # índices de precios y costo
                    try:
                        precio_limpio = re.sub(r'[^\d.]', '', str(campos[i]))
                        campos[i] = f"{float(precio_limpio):.2f}" if precio_limpio else "0.00"
                    except (ValueError, TypeError):
                        campos[i] = "0.00"
                
                cursor.execute("""
                    INSERT INTO precios (
                        sku, categoria, subcategoria, linea, modelo,
                        descripcion, medidas, costo, precio_mayoreo, precio_menudeo,
                         imagen, status_ws, catalogo, catalogo2, catalogo3, proveedor
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
       
                        categoria=VALUES(categoria),
                        subcategoria=VALUES(subcategoria),
                        descripcion=VALUES(descripcion),
                        costo=VALUES(costo),
                        precio_mayoreo=VALUES(precio_mayoreo),
                        precio_menudeo=VALUES(precio_menudeo),
                        imagen=VALUES(imagen),
                        status_ws=VALUES(status_ws)
                """, campos)
                
                servicios_guardados += 1
                app.logger.info(f"✅ Servicio guardado: {servicio.get('servicio')}")
                
            except Exception as e:
                app.logger.error(f"🔴 Error guardando servicio individual: {e}")
                continue
        
        conn.commit()
        cursor.close()
        conn.close()
        
        app.logger.info(f"📊 Total servicios guardados: {servicios_guardados}")
        return servicios_guardados
        
    except Exception as e:
        app.logger.error(f"🔴 Error guardando servicios en BD: {e}")
        return 0

@app.route('/configuracion/precios/subir-pdf', methods=['POST'])
def subir_pdf_servicios():
    """Endpoint para subir PDF y extraer servicios y sus imágenes automáticamente"""
    config = obtener_configuracion_por_host()
    
    try:
        if 'pdf_file' not in request.files:
            flash('❌ No se seleccionó ningún archivo', 'error')
            return redirect(url_for('configuracion_precios'))
        
        file = request.files['pdf_file']
        if file.filename == '':
            flash('❌ No se seleccionó ningún archivo', 'error')
            return redirect(url_for('configuracion_precios'))
        
        if file and allowed_file(file.filename):
            # Guardar archivo
            filename = secure_filename(f"servicios_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{file.filename}")
            filepath = os.path.join(PDF_UPLOAD_FOLDER, filename)
            file.save(filepath)
            
            app.logger.info(f"📄 PDF guardado: {filepath}")
            
            # Extraer texto e imágenes del PDF
            texto_pdf, imagenes_pdf = extraer_texto_e_imagenes_pdf(filepath)
            
            if not texto_pdf:
                flash('❌ Error extrayendo texto del PDF. El archivo puede estar dañado o ser una imagen.', 'error')
                try:
                    os.remove(filepath)
                except:
                    pass
                return redirect(url_for('configuracion_precios'))
            
            if len(texto_pdf) < 50:  # Muy poco texto extraído
                flash('❌ Se extrajo muy poco texto del PDF. ¿Está escaneado como imagen?', 'error')
                try:
                    os.remove(filepath)
                except:
                    pass
                return redirect(url_for('configuracion_precios'))
            
            # Analizar con IA
            servicios = analizar_pdf_servicios(texto_pdf, config)
            if not servicios or not servicios.get('servicios'):
                flash('❌ No se pudieron identificar servicios en el PDF. Revisa el formato.', 'error')
                try:
                    os.remove(filepath)
                except:
                    pass
                return redirect(url_for('configuracion_precios'))
            
            # Asociar imágenes con productos
            servicios = asociar_imagenes_productos(servicios, imagenes_pdf)
            
            # Guardar en base de datos
            servicios_guardados = guardar_servicios_desde_pdf(servicios, config)
            
            # Limpiar archivo
            try:
                os.remove(filepath)
            except:
                pass
            
            if servicios_guardados > 0:
                flash(f'✅ {servicios_guardados} servicios extraídos con imágenes y guardados exitosamente', 'success')
                # Log detallado
                app.logger.info(f"📊 Resumen de servicios extraídos:")
                for servicio in servicios.get('servicios', [])[:10]:  # Mostrar primeros 10
                    app.logger.info(f"   - {servicio.get('servicio')}: ${servicio.get('precio')} - Imagen: {bool(servicio.get('imagen'))}")
                if len(servicios.get('servicios', [])) > 10:
                    app.logger.info(f"   ... y {len(servicios.get('servicios', [])) - 10} más")
            else:
                flash('⚠️ No se pudieron guardar los servicios en la base de datos', 'warning')
                
        else:
            flash('❌ Tipo de archivo no permitido. Solo se aceptan PDF y TXT', 'error')
        
        return redirect(url_for('configuracion_precios'))
        
    except Exception as e:
        app.logger.error(f"🔴 Error procesando PDF: {e}")
        app.logger.error(traceback.format_exc())
        flash('❌ Error interno procesando el archivo', 'error')
        # Limpiar archivo en caso de error
        try:
            if 'filepath' in locals():
                os.remove(filepath)
        except:
            pass
        return redirect(url_for('configuracion_precios'))

def get_productos_dir_for_config(config=None):
    """Return (productos_dir, tenant_slug). Ensures uploads/productos/<tenant_slug> exists."""
    if config is None:
        config = obtener_configuracion_por_host()
    dominio = (config.get('dominio') or '').strip().lower()
    tenant_slug = dominio.split('.')[0] if dominio else 'default'
    productos_dir = os.path.join(app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER), 'productos', tenant_slug)
    os.makedirs(productos_dir, exist_ok=True)
    return productos_dir, tenant_slug

def get_db_connection(config=None):
    """
    Get a DB connection using a small MySQLConnectionPool per tenant (cached).
    Falls back to direct mysql.connector.connect() if pooling fails.
    """
    if config is None:
        try:
            from flask import has_request_context
            if has_request_context():
                config = obtener_configuracion_por_host()
            else:
                config = NUMEROS_CONFIG['524495486142']
        except Exception as e:
            app.logger.error(f"Error obteniendo configuración: {e}")
            config = NUMEROS_CONFIG['524495486142']

    # pool size can be tuned via env var
    POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))
    pool_key = f"{config.get('db_host')}|{config.get('db_user')}|{config.get('db_name')}"

    # module-level cache for pools
    global _MYSQL_POOLS
    try:
        _MYSQL_POOLS
    except NameError:
        _MYSQL_POOLS = {}

    try:
        # create pool if not present
        if pool_key not in _MYSQL_POOLS:
            app.logger.info(f"🔧 Creating MySQL pool for {config.get('db_name')} (size={POOL_SIZE})")
            _MYSQL_POOLS[pool_key] = pooling.MySQLConnectionPool(
                pool_name=f"pool_{config.get('db_name')}",
                pool_size=POOL_SIZE,
                host=config['db_host'],
                user=config['db_user'],
                password=config['db_password'],
                database=config['db_name'],
                charset='utf8mb4'
            )
        conn = _MYSQL_POOLS[pool_key].get_connection()
        # ensure the connection is alive
        try:
            if not conn.is_connected():
                conn.reconnect(attempts=2, delay=0.5)
        except Exception:
            pass
        app.logger.info(f"🗄️ Borrowed connection from pool for {config.get('db_name')}")
        return conn

    except Exception as pool_err:
        # Pooling might not be supported or failed: fallback to direct connect
        app.logger.warning(f"⚠️ MySQL pool error (fallback to direct connect): {pool_err}")
        try:
            conn = mysql.connector.connect(
                host=config['db_host'],
                user=config['db_user'],
                password=config['db_password'],
                database=config['db_name'],
                charset='utf8mb4'
            )
            app.logger.info(f"✅ Direct connection established to {config['db_name']}")
            return conn
        except Exception as e:
            app.logger.error(f"❌ Error connectando a BD {config['db_name']}: {e}")
            raise

@app.route('/kanban/columna/<int:columna_id>/renombrar', methods=['POST'])
def renombrar_columna_kanban(columna_id):
    config = obtener_configuracion_por_host()
    nuevo_nombre = request.json.get('nombre', '').strip()
    if not nuevo_nombre:
        return jsonify({'error': 'Nombre vacío'}), 400

    conn = get_db_connection(config)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE kanban_columnas SET nombre=%s WHERE id=%s",
        (nuevo_nombre, columna_id)
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True, 'nombre': nuevo_nombre})

@app.route('/kanban/columna/agregar', methods=['POST'])
def agregar_columna_kanban():
    config = obtener_configuracion_por_host()
    data = request.get_json(silent=True) or {}
    after_id = data.get('after_id')

    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    try:
        default_icon = '/static/icons/default-avatar.png'
        color_nueva = '#007bff'
        if after_id:
            cursor.execute("SELECT orden, color FROM kanban_columnas WHERE id=%s", (after_id,))
            row = cursor.fetchone()
            if not row:
                return jsonify({'error': 'Columna after_id no existe'}), 404
            after_orden = row['orden']
            color_nueva = row.get('color') or color_nueva
            cursor.execute("UPDATE kanban_columnas SET orden = orden + 1 WHERE orden > %s", (after_orden,))
            nombre = f"Etapa {after_orden + 1}"
            cursor.execute("""
                INSERT INTO kanban_columnas (nombre, orden, color, icono)
                VALUES (%s, %s, %s, %s)
            """, (nombre, after_orden + 1, color_nueva, default_icon))
        else:
            cursor.execute("SELECT COALESCE(MAX(orden), 0) + 1 AS next_ord FROM kanban_columnas")
            next_ord = cursor.fetchone()['next_ord']
            nombre = f"Etapa {next_ord}"
            cursor.execute("""
                INSERT INTO kanban_columnas (nombre, orden, color, icono)
                VALUES (%s, %s, %s, %s)
            """, (nombre, next_ord, color_nueva, default_icon))

        conn.commit()
        new_id = cursor.lastrowid
        cursor.execute("SELECT id, nombre, orden, color, icono FROM kanban_columnas WHERE id=%s", (new_id,))
        nueva = cursor.fetchone()
        return jsonify({'success': True, **nueva})
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error agregando columna Kanban: {e}")
        return jsonify({'error': 'Error interno'}), 500
    finally:
        cursor.close(); conn.close()

@app.route('/kanban/columna/<int:columna_id>/eliminar', methods=['POST'])
def eliminar_columna_kanban(columna_id):
    config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)

    # Obtener todas las columnas
    cursor.execute("SELECT id FROM kanban_columnas ORDER BY orden")
    columnas = cursor.fetchall()
    if len(columnas) <= 1:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'error': 'No se puede eliminar la última columna'}), 400

    # Ver a cuál columna transferir (elige la primera distinta)
    otras = [c['id'] for c in columnas if c['id'] != columna_id]
    if not otras:
        cursor.close()
        conn.close()
        return jsonify({'success': False, 'error': 'No hay otra columna a la cual transferir los chats'}), 400
    columna_destino = otras[0]

    # Transferir los chats
    cursor.execute("UPDATE chat_meta SET columna_id=%s WHERE columna_id=%s", (columna_destino, columna_id))
    # Eliminar la columna
    cursor.execute("DELETE FROM kanban_columnas WHERE id=%s", (columna_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True, 'columna_destino': columna_destino})

@app.route('/kanban/columna/<int:columna_id>/icono', methods=['POST'])
def actualizar_icono_columna(columna_id):
    config = obtener_configuracion_por_host()
    data = request.get_json(silent=True) or {}
    icono = (data.get('icono') or '').strip()
    if not icono:
        return jsonify({'error': 'Icono vacío'}), 400
    conn = get_db_connection(config)
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE kanban_columnas SET icono=%s WHERE id=%s", (icono, columna_id))
        conn.commit()
        return jsonify({'success': True})
    except Exception as e:
        conn.rollback()
        app.logger.error(f"Error actualizando icono: {e}")
        return jsonify({'error': 'Error actualizando icono'}), 500
    finally:
        cursor.close(); conn.close()
def crear_tablas_kanban(config=None):
    """Crea las tablas necesarias para el Kanban en la base de datos especificada"""
    if config is None:
        config = obtener_configuracion_por_host()
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS kanban_columnas (
                id INT AUTO_INCREMENT PRIMARY KEY,
                nombre VARCHAR(100) NOT NULL,
                orden INT NOT NULL DEFAULT 0,
                color VARCHAR(20) DEFAULT '#007bff',
                icono VARCHAR(512) DEFAULT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        ''')
        # Asegurar columna icono si tabla ya existía
        try:
            cursor.execute("SHOW COLUMNS FROM kanban_columnas LIKE 'icono'")
            if cursor.fetchone() is None:
                cursor.execute("ALTER TABLE kanban_columnas ADD COLUMN icono VARCHAR(512) DEFAULT NULL")
        except Exception as _:
            pass

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_meta (
                numero VARCHAR(20) PRIMARY KEY,
                columna_id INT DEFAULT 1,
                fecha_actualizacion TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                FOREIGN KEY (columna_id) REFERENCES kanban_columnas(id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        ''')

        cursor.execute("SELECT COUNT(*) FROM kanban_columnas")
        if cursor.fetchone()[0] == 0:
            default_icon = '/static/icons/default-avatar.png'
            columnas_default = [
                (1, 'Nuevos', 1, '#28a745', default_icon),
                (2, 'En Conversación', 2, '#17a2b8', default_icon),
                (3, 'Esperando Respuesta', 3, '#ffc107', default_icon),
                (4, 'Resueltos', 4, '#6c757d', default_icon)
            ]
            cursor.executemany(
                "INSERT INTO kanban_columnas (id, nombre, orden, color, icono) VALUES (%s,%s,%s,%s,%s)",
                columnas_default
            )

        conn.commit()
        cursor.close(); conn.close()
        app.logger.info(f"✅ Tablas Kanban creadas/verificadas en {config['db_name']}")
    except Exception as e:
        app.logger.error(f"❌ Error creando tablas Kanban en {config['db_name']}: {e}")

app.route('/inicializar-kanban', methods=['POST'])
def inicializar_kanban_multitenant():
    """Inicializa el sistema Kanban en todas las bases de datos configuradas"""
    app.logger.info("🔧 Inicializando Kanban para todos los tenants...")
    
    for nombre_tenant, config in NUMEROS_CONFIG.items():
        try:
            crear_tablas_kanban(config)
            app.logger.info(f"✅ Kanban inicializado para {config['dominio']}")
        except Exception as e:
            app.logger.error(f"❌ Error inicializando Kanban para {config['dominio']}: {e}")

# ——— Función para enviar mensajes de voz ———
def enviar_mensaje_voz(numero, audio_url, config=None):
    """Envía un mensaje de voz por WhatsApp"""
    if config is None:
        config = obtener_configuracion_por_host()
    if config is None:
        config = obtener_configuracion_numero(numero)
    
    url = f"https://graph.facebook.com/v23.0/{config['phone_number_id']}/messages"
    headers = {
        'Authorization': f'Bearer {config['whatsapp_token']}',
        'Content-Type': 'application/json'
    }
    
    payload = {
        'messaging_product': 'whatsapp',
        'to': numero,
        'type': 'audio',
        'audio': {
            'link': audio_url
        }
    }
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        app.logger.info(f"✅ Audio enviado a {numero}")
        return True
    except Exception as e:
        app.logger.error(f"🔴 Error enviando audio: {e}")
        return False
    
def texto_a_voz(texto, filename,config=None):
    """Convierte texto a audio usando Google TTS"""
    if config is None:
        config = obtener_configuracion_por_host()
    try:
        from gtts import gTTS
        import os
        
        # ✅ Ruta ABSOLUTA para evitar problemas
        base_dir = os.path.dirname(os.path.abspath(__file__))
        audio_dir = os.path.join(base_dir, 'static', 'audio', 'respuestas')
        
        # Crear directorio si no existe
        os.makedirs(audio_dir, exist_ok=True)
        
        # Ruta completa del archivo
        filepath = os.path.join(audio_dir, f"{filename}.mp3")
        
        # Convertir texto a voz
        tts = gTTS(text=texto, lang='es', slow=False)
        tts.save(filepath)
        
        # ✅ URL PÚBLICA - Usa tu dominio real
        MI_DOMINIO = os.getenv('MI_DOMINIO', 'https://tu-dominio.com')
        audio_url = f"{MI_DOMINIO}/static/audio/respuestas/{filename}.mp3"
        
        app.logger.info(f"🎵 Audio guardado en: {filepath}")
        app.logger.info(f"🌐 URL pública: {audio_url}")
        
        return audio_url
        
    except Exception as e:
        app.logger.error(f"Error en texto a voz: {e}")
        return None

def detectar_pedido_inteligente(mensaje, numero, historial=None, config=None):
    """Detección inteligente de pedidos que interpreta contexto y datos faltantes"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    app.logger.info(f"🎯 Analizando mensaje para pedido inteligente: '{mensaje}'")
    
    # Primero verificar con detección básica
    deteccion_basica = detectar_solicitud_cita_keywords(mensaje, config)
    app.logger.info(f"🔍 Detección básica: {deteccion_basica}")
    
    if not deteccion_basica:
        return False
    
    try:
        # Obtener historial para contexto
        if historial is None:
            historial = obtener_historial(numero, limite=3, config=config)
        
        # Construir contexto del historial
        contexto_historial = ""
        for i, msg in enumerate(historial[-2:]):  # Últimos 2 mensajes
            if msg['mensaje']:
                contexto_historial += f"Usuario: {msg['mensaje']}\n"
            if msg['respuesta']:
                contexto_historial += f"Asistente: {msg['respuesta']}\n"
        
        # Prompt mejorado para detección inteligente
        prompt = f"""
        Eres un asistente para La Porfirianna (restaurante). Analiza si el mensaje es un pedido y qué datos faltan.

        HISTORIAL RECIENTE:
        {contexto_historial}

        MENSAJE ACTUAL: "{mensaje}"

        Responde en formato JSON:
        {{
            "es_pedido": true/false,
            "confianza": 0.0-1.0,
            "datos_obtenidos": {{
                "platillos": ["lista de platillos detectados"],
                "cantidades": ["cantidades especificadas"],
                "especificaciones": ["con todo", "sin cebolla", etc.],
                "nombre_cliente": "nombre si se menciona",
                "direccion": "dirección si se menciona"
            }},
            "datos_faltantes": ["lista de datos que faltan"],
            "siguiente_pregunta": "pregunta natural para solicitar dato faltante"
        }}

        Datos importantes para un pedido completo:
        - Platillos específicos (gorditas, tacos, quesadillas, etc.)
        - Cantidades de cada platillo
        - Especificaciones (guisados, ingredientes, preparación)
        - Dirección de entrega
        - Forma de pago (efectivo, transferencia)
        - Nombre del cliente

        Ejemplo si dice "quiero 2 gorditas":
        {{
            "es_pedido": true,
            "confianza": 0.9,
            "datos_obtenidos": {{
                "platillos": ["gorditas"],
                "cantidades": ["2"],
                "especificaciones": [],
                "nombre_cliente": null,
                "direccion": null
            }},
            "datos_faltantes": ["guisados para las gorditas", "dirección"],
            "siguiente_pregunta": "¡Perfecto! ¿De qué guisado quieres las gorditas? Tenemos chicharrón, tinga, papa, etc."
        }}
        """
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 800
        }
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        respuesta_ia = data['choices'][0]['message']['content'].strip()
        
        # Extraer JSON de la respuesta
        json_match = re.search(r'\{.*\}', respuesta_ia, re.DOTALL)
        if json_match:
            analisis = json.loads(json_match.group())
            app.logger.info(f"🔍 Análisis inteligente: {json.dumps(analisis, indent=2)}")
            
            # Considerar pedido si confianza > 0.7
            return analisis if analisis.get('es_pedido', False) and analisis.get('confianza', 0) > 0.7 else None
        else:
            return None
            
    except Exception as e:
        app.logger.error(f"Error en detección inteligente de pedido: {e}")
        # Fallback a detección básica
        return {"es_pedido": True, "confianza": 0.8, "datos_faltantes": ["todos"], "siguiente_pregunta": "¿Qué platillos deseas ordenar?"} if deteccion_basica else None

def manejar_pedido_automatico(numero, mensaje, analisis_pedido, config=None):
    """Maneja automáticamente el pedido detectado por la IA"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # Obtener estado actual de la conversación
        estado_actual = obtener_estado_conversacion(numero, config)
        
        # Si ya estamos en proceso de pedido, continuar
        if estado_actual and estado_actual.get('contexto') == 'EN_PEDIDO':
            return continuar_proceso_pedido(numero, mensaje, estado_actual, config)
        
        # Si es un nuevo pedido, iniciar proceso
        app.logger.info(f"🔄 Iniciando proceso automático de pedido para {numero}")
        
        # Guardar análisis del pedido en el estado
        datos_pedido = {
            'paso': 1,
            'analisis_inicial': analisis_pedido,
            'datos_obtenidos': analisis_pedido.get('datos_obtenidos', {}),
            'timestamp': datetime.now().isoformat()
        }
        
        actualizar_estado_conversacion(numero, "EN_PEDIDO", "iniciar_pedido", datos_pedido, config)
        
        # Usar la pregunta sugerida por la IA o una por defecto
        siguiente_pregunta = analisis_pedido.get('siguiente_pregunta')
        if not siguiente_pregunta:
            # Generar pregunta basada en datos faltantes
            datos_faltantes = analisis_pedido.get('datos_faltantes', [])
            if 'guisados' in str(datos_faltantes).lower():
                siguiente_pregunta = "¡Perfecto! ¿De qué guisado quieres tus platillos? Tenemos chicharrón, tinga, papa, mole, etc."
            elif 'dirección' in str(datos_faltantes):
                siguiente_pregunta = "¿A qué dirección debemos llevar tu pedido?"
            elif 'nombre' in str(datos_faltantes):
                siguiente_pregunta = "¿Cuál es tu nombre para el pedido?"
            else:
                siguiente_pregunta = "¿Qué más necesitas agregar a tu pedido?"
        
        return siguiente_pregunta
        
    except Exception as e:
        app.logger.error(f"Error manejando pedido automático: {e}")
        return "¡Gracias por tu pedido! ¿Qué más deseas agregar?"
    
def autenticar_google_calendar(config=None):
    """Autentica con OAuth usando client_secret.json con soporte para múltiples cuentas.
    Busca tokens en ruta absoluta y hace fallback a token.json; refresca si es posible."""
    if config is None:
        config = obtener_configuracion_por_host()

    SCOPES = ['https://www.googleapis.com/auth/calendar']
    creds = None

    try:
        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        tenant_token_filename = f"token_{config['dominio'].replace('.', '_')}.json"
        tenant_token_path = os.path.join(BASE_DIR, tenant_token_filename)
        generic_token_path = os.path.join(BASE_DIR, 'token.json')

        app.logger.info(f"🔐 Intentando autenticar Google Calendar para {config.get('dominio')} (buscar: {tenant_token_path} then {generic_token_path})")

        # Prefer tenant-specific token
        token_path_to_use = None
        if os.path.exists(tenant_token_path):
            token_path_to_use = tenant_token_path
            app.logger.info(f"✅ Usando token tenant-specific: {tenant_token_path}")
        elif os.path.exists(generic_token_path):
            token_path_to_use = generic_token_path
            app.logger.warning(f"⚠️ No se encontró token tenant-specific, usando fallback: {generic_token_path}")
        else:
            app.logger.warning(f"⚠️ No se encontró ningún token OAuth para {config.get('dominio')} (esperado: {tenant_token_path})")
            return None

        try:
            creds = Credentials.from_authorized_user_file(token_path_to_use, SCOPES)
            if creds and creds.valid:
                service = build('calendar', 'v3', credentials=creds)
                app.logger.info(f"✅ Token válido cargado desde {token_path_to_use}")
                return service
            elif creds and creds.expired and creds.refresh_token:
                app.logger.info("🔄 Token expirado, intentando refresh...")
                creds.refresh(Request())
                # Guardar en el archivo tenant-specific (intentar preservar tenant filename)
                save_path = tenant_token_path if token_path_to_use != generic_token_path else generic_token_path
                with open(save_path, 'w') as token_file:
                    token_file.write(creds.to_json())
                app.logger.info(f"✅ Token refrescado y guardado en {save_path}")
                service = build('calendar', 'v3', credentials=creds)
                return service
            else:
                app.logger.warning(f"⚠️ Token encontrado en {token_path_to_use} pero no es válido ni refrescable")
                return None
        except Exception as e:
            app.logger.error(f"❌ Error leyendo/refresh token en {token_path_to_use}: {e}")
            app.logger.error(traceback.format_exc())
            return None

    except Exception as e:
        app.logger.error(f"❌ Error inesperado en autenticar_google_calendar: {e}")
        app.logger.error(traceback.format_exc())
        return None

@app.route('/chat/<telefono>/messages')
def get_chat_messages(telefono):
    """Obtener mensajes de un chat específico después de cierto ID"""
    after_id = request.args.get('after', 0, type=int)
    config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    # Consultar solo mensajes más recientes que el ID proporcionado
    cursor.execute("""
        SELECT id, mensaje as content, fecha as timestamp, direccion as direction, respuesta
        FROM mensajes 
        WHERE telefono = %s AND id > %s
        ORDER BY fecha ASC
    """, (telefono, after_id))
    
    messages = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return jsonify({
        'messages': messages,
        'timestamp': int(time.time() * 1000)
    })

@app.route('/autorizar-porfirianna')
def autorizar_porfirianna():
    """Endpoint específico para autorizar La Porfirianna con Google"""
    try:
        # Usar explícitamente la configuración de La Porfirianna
        config = NUMEROS_CONFIG['524812372326']
        SCOPES = ['https://www.googleapis.com/auth/calendar']
        tenant_id = config['dominio'].replace('.', '_')
        
        if not os.path.exists('client_secret.json'):
            return "❌ Error: No se encuentra client_secret.json"
        
        # Usar explícitamente el dominio de La Porfirianna para el redirect
        redirect_uri = 'https://www.laporfirianna.mektia.com/completar-autorizacion'
        app.logger.info(f"🔐 URI de redirección específica para La Porfirianna: {redirect_uri}")
        
        flow = InstalledAppFlow.from_client_secrets_file(
            'client_secret.json', 
            SCOPES,
            redirect_uri=redirect_uri
        )
        
        # Generar URL de autorización
        auth_url, _ = flow.authorization_url(
            prompt='consent', 
            access_type='offline',
            include_granted_scopes='true',
            state=tenant_id  # Incluir el tenant en el estado
        )
        
        app.logger.info(f"🌐 URL de autorización generada: {auth_url}")
        
        return f'''
        <h1>✅ Autorización Google Calendar para La Porfirianna</h1>
        <p>Por favor visita esta URL para autorizar:</p>
        <a href="{auth_url}" target="_blank" class="btn btn-primary">{auth_url}</a>
        <p>Después de autorizar, serás redirigido automáticamente.</p>
        '''
        
    except Exception as e:
        app.logger.error(f"❌ Error en autorización La Porfirianna: {str(e)}")
        return f"❌ Error: {str(e)}"

@app.route('/autorizar-manual')
def autorizar_manual():
    """Endpoint para autorizar manualmente con Google"""
    try:
        config = obtener_configuracion_por_host()
        SCOPES = ['https://www.googleapis.com/auth/calendar']
        tenant_id = config['dominio'].replace('.', '_')
        
        if not os.path.exists('client_secret.json'):
            return "❌ Error: No se encuentra client_secret.json"
        
        # Obtener el host actual de la solicitud
        host = request.host
        app.logger.info(f"🔍 Host actual en autorizar_manual: {host}")
        
        # Construir la URI de redirección basada en el host actual
        redirect_uri = f'https://{host}/completar-autorizacion'
        app.logger.info(f"🔐 URI de redirección en autorizar_manual: {redirect_uri}")
        
        flow = InstalledAppFlow.from_client_secrets_file(
            'client_secret.json', 
            SCOPES,
            redirect_uri=redirect_uri
        )
        
        # Generar URL de autorización
        auth_url, _ = flow.authorization_url(
            prompt='consent', 
            access_type='offline',
            include_granted_scopes='true',
            state=tenant_id  # Incluir el tenant en el estado
        )
        
        app.logger.info(f"🌐 URL de autorización generada: {auth_url}")
        
        return f'''
        <h1>✅ Autorización Google Calendar</h1>
        <p>Por favor visita esta URL para autorizar:</p>
        <a href="{auth_url}" target="_blank">{auth_url}</a>
        <p>Después de autorizar, Google te dará un código. Pégalo aquí:</p>
        <form action="/procesar-codigo" method="post">
            <input type="text" name="codigo" placeholder="Pega el código aquí" size="50">
            <input type="submit" value="Enviar">
        </form>
        '''
        
    except Exception as e:
        app.logger.error(f"❌ Error en autorización manual: {str(e)}")
        return f"❌ Error: {str(e)}"
    
def crear_evento_calendar(service, cita_info, config=None):
    """Crea un evento en Google Calendar para la cita con más detalles del servicio"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # Determinar el tipo de negocio
        es_porfirianna = 'laporfirianna' in config.get('dominio', '')
        
        # Formatear fecha y hora
        if not es_porfirianna and cita_info.get('fecha_sugerida') and cita_info.get('hora_sugerida'):
            start_time = f"{cita_info['fecha_sugerida']}T{cita_info['hora_sugerida']}:00"
            end_time_dt = datetime.strptime(f"{cita_info['fecha_sugerida']} {cita_info['hora_sugerida']}", 
                                          "%Y-%m-%d %H:%M") + timedelta(hours=1)
            end_time = end_time_dt.strftime("%Y-%m-%dT%H:%M:00")
        else:
            # Para La Porfirianna o si no hay fecha/hora específica
            now = datetime.now()
            start_time = now.isoformat()
            end_time = (now + timedelta(hours=1)).isoformat()
        
        # Obtener detalles adicionales del servicio
        detalles_servicio = cita_info.get('detalles_servicio', {})
        descripcion_servicio = detalles_servicio.get('descripcion', 'No hay descripción disponible')
        categoria_servicio = detalles_servicio.get('categoria', 'Sin categoría')
        precio_servicio = detalles_servicio.get('precio_menudeo') or detalles_servicio.get('precio', 'No especificado')
        
        # Título del evento más descriptivo
        event_title = f"{'Pedido' if es_porfirianna else 'Cita'}: {cita_info.get('servicio_solicitado', 'Servicio')} - {cita_info.get('nombre_cliente', 'Cliente')}"
        
        # Descripción más detallada del evento
        event_description = f"""
📋 DETALLES DE {'PEDIDO' if es_porfirianna else 'CITA'}:

🔸 {'Platillo' if es_porfirianna else 'Servicio'}: {cita_info.get('servicio_solicitado', 'No especificado')}
🔸 Categoría: {categoria_servicio}
🔸 Precio: ${precio_servicio} {cita_info.get('moneda', 'MXN')}
🔸 Descripción: {descripcion_servicio}

👤 CLIENTE:
🔹 Nombre: {cita_info.get('nombre_cliente', 'No especificado')}
🔹 Teléfono: {cita_info.get('telefono', 'No especificado')}
🔹 WhatsApp: https://wa.me/{cita_info.get('telefono', '').replace('+', '')}

⏰ FECHA/HORA:
🕒 Fecha: {cita_info.get('fecha_sugerida', 'No especificada')}
🕒 Hora: {cita_info.get('hora_sugerida', 'No especificada')}
🕒 Creado: {datetime.now().strftime('%d/%m/%Y %H:%M')}

💬 Notas: {'Pedido' if es_porfirianna else 'Cita'} agendado automáticamente desde WhatsApp
        """.strip()
        
        # Crear el evento con información ampliada
        event = {
            'summary': event_title,
            'location': config.get('direccion', ''),
            'description': event_description,
            'start': {
                'dateTime': start_time,
                'timeZone': 'America/Mexico_City',
            },
            'end': {
                'dateTime': end_time,
                'timeZone': 'America/Mexico_City',
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 30},
                    {'method': 'email', 'minutes': 24 * 60},  # 1 día antes
                ],
            },
            'colorId': '4' if es_porfirianna else '1',  # Rojo para Porfirianna, Azul para otros
        }
        
        # Obtener el correo para notificaciones de Calendar
        app.logger.info(f"📧 Intentando obtener calendar_email de la base de datos")
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT calendar_email FROM configuracion WHERE id = 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        calendar_email = None
        if result and result.get('calendar_email'):
            calendar_email = result['calendar_email']
            
        # Agregar el correo como asistente si está configurado
        if calendar_email:
            event['attendees'] = [{'email': calendar_email}]
            app.logger.info(f"✉️ Notificación de Calendar configurada para: {calendar_email}")
        
        calendar_id = os.getenv('GOOGLE_CALENDAR_ID', 'primary')
        event = service.events().insert(calendarId=calendar_id, body=event).execute()
        
        app.logger.info(f'Evento creado: {event.get("htmlLink")}')
        return event.get('id')  # Retorna el ID del evento
        
    except Exception as e:
        app.logger.error(f'Error al crear evento: {e}')
        app.logger.error(traceback.format_exc())
        return None
    
def validar_datos_cita_completos(info_cita, config=None):
    """
    Valida que la información de la cita/pedido tenga todos los datos necesarios
    Devuelve (True, None) si está completa, (False, lista_faltantes) si faltan datos
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    # Determinar el tipo de negocio
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    
    datos_faltantes = []
    
    # Validar servicio solicitado (siempre requerido)
    if not info_cita.get('servicio_solicitado') or info_cita.get('servicio_solicitado') == 'null':
        datos_faltantes.append("servicio")
    
    # Para La Porfirianna, la hora es importante; para servicios digitales, necesitamos fecha y hora
    if es_porfirianna:
        if not info_cita.get('hora_sugerida') or info_cita.get('hora_sugerida') == 'null':
            datos_faltantes.append("hora")
    else:
        if not info_cita.get('fecha_sugerida') or info_cita.get('fecha_sugerida') == 'null':
            datos_faltantes.append("fecha")
        if not info_cita.get('hora_sugerida') or info_cita.get('hora_sugerida') == 'null':
            datos_faltantes.append("hora")
    
    # El nombre es opcional pero útil
    if not info_cita.get('nombre_cliente') or info_cita.get('nombre_cliente') == 'null':
        # No lo añadimos a datos_faltantes porque es opcional
        app.logger.info("ℹ️ Nombre de cliente no proporcionado, pero no es obligatorio")
    
    if datos_faltantes:
        return False, datos_faltantes
    return True, None

@app.route('/completar-autorizacion')
def completar_autorizacion():
    """Endpoint para completar la autorización con el código — guarda token tenant-specific en BASE_DIR"""
    try:
        code = request.args.get('code')
        state = request.args.get('state')  # intentamos usar state como tenant identifier
        scope = request.args.get('scope')

        # Determinar tenant desde el state si viene, sino por host
        tenant_domain = None
        if state:
            # state fue generado como tenant_id = dominio.replace('.', '_')
            tenant_domain = state.replace('_', '.')
            app.logger.info(f"🔍 Tenant desde state: {tenant_domain}")
        else:
            config_host = obtener_configuracion_por_host()
            tenant_domain = config_host.get('dominio')

        if not code:
            app.logger.error("❌ No se proporcionó código de autorización")
            return "❌ Error: No se proporcionó código de autorización"

        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        client_secret_path = os.path.join(BASE_DIR, 'client_secret.json')
        if not os.path.exists(client_secret_path):
            app.logger.error(f"❌ No se encuentra {client_secret_path}")
            return f"❌ Error: No se encuentra el archivo client_secret.json en {BASE_DIR}"

        # Construir redirect_uri basado en host actual (mantener compatibilidad)
        host = request.host
        redirect_uri = f'https://{host}/completar-autorizacion'
        SCOPES = ['https://www.googleapis.com/auth/calendar']

        app.logger.info("🔄 Creando flujo de OAuth...")
        flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES, redirect_uri=redirect_uri)

        app.logger.info("🔄 Intercambiando código por token...")
        flow.fetch_token(code=code)
        creds = flow.credentials

        # Guardar token en ruta absoluta tenant-specific
        token_filename = f"token_{tenant_domain.replace('.', '_')}.json"
        token_path = os.path.join(BASE_DIR, token_filename)

        with open(token_path, 'w') as token:
            token.write(creds.to_json())
        app.logger.info(f"✅ Token guardado en: {token_path} para tenant {tenant_domain}")

        return """
        <html>
        <head><title>Autorización Completada</title></head>
        <body>
            <h1>✅ Autorización completada correctamente</h1>
            <p>Ya puedes usar Google Calendar para agendar citas.</p>
            <p>Puedes cerrar esta ventana y volver a la aplicación.</p>
        </body>
        </html>
        """

    except Exception as e:
        app.logger.error(f"❌ Error en completar_autorizacion: {e}")
        app.logger.error(traceback.format_exc())
        return f"❌ Error: {str(e)}"
         
def convertir_audio(audio_path):
    try:
        output_path = audio_path.replace('.ogg', '.mp3')
        audio = AudioSegment.from_file(audio_path, format='ogg')
        audio.export(output_path, format='mp3')
        app.logger.info(f"🔄 Audio convertido a: {output_path}")
        return output_path
    except Exception as e:
        app.logger.error(f"🔴 Error convirtiendo audio: {str(e)}")
        return None

def extraer_info_cita_mejorado(mensaje, numero, historial=None, config=None):
    """Versión mejorada que usa el historial de conversación para extraer información y detalles del servicio"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    if historial is None:
        historial = obtener_historial(numero, limite=5, config=config)
    
    # Construir contexto del historial
    contexto_historial = ""
    for i, msg in enumerate(historial):
        if msg['mensaje']:
            contexto_historial += f"Usuario: {msg['mensaje']}\n"
        if msg['respuesta']:
            contexto_historial += f"Asistente: {msg['respuesta']}\n"
    
    # MEJORA: Detectar si este es un mensaje de confirmación/respuesta a una pregunta previa
    mensaje_lower = mensaje.lower()
    es_confirmacion = False
    if mensaje_lower.startswith(('si', 'sí', 'claro', 'ok')) or 'a las' in mensaje_lower:
        es_confirmacion = True
        app.logger.info(f"✅ Detectado mensaje de confirmación: '{mensaje}'")
    
    try:
        # Obtener productos/servicios de la BD para referencia
        precios = obtener_todos_los_precios(config)
        servicios_nombres = [p['servicio'] for p in precios if p.get('servicio')]
        servicios_texto = ", ".join(servicios_nombres[:20])  # Limitar para evitar tokens excesivos
        
        # Determinar tipo de negocio
        es_porfirianna = 'laporfirianna' in config.get('dominio', '')
        
        # MEJORA: Ajustar prompt para mensajes de confirmación
        if es_confirmacion:
            prompt_cita = f"""
            Eres un asistente para {es_porfirianna and 'La Porfirianna (restaurante)' or 'servicios digitales'}.
            Este parece ser un mensaje de CONFIRMACIÓN a una consulta previa sobre {es_porfirianna and 'un pedido' or 'una cita'}.
            
            HISTORIAL RECIENTE:
            {contexto_historial}
            
            MENSAJE DE CONFIRMACIÓN: "{mensaje}"
            
            Basándote en el historial y la confirmación, extrae la información completa de {es_porfirianna and 'orden/pedido' or 'cita/servicio'}.
            
            SERVICIOS/PRODUCTOS DISPONIBLES:
            {servicios_texto}
            
            Devuelve un JSON con estos campos:
            - servicio_solicitado (string: nombre del servicio que desea, extrae del historial si es necesario)
            - fecha_sugerida (string formato YYYY-MM-DD, usa la fecha de HOY si confirma "hoy")
            - hora_sugerida (string formato HH:MM, extrae del mensaje o historial)
            - nombre_cliente (string o null, intenta extraer del historial)
            - telefono (string: {numero})
            - estado (siempre "pendiente")
            - datos_completos (boolean: true si tiene todos los datos necesarios)
            """
        else:
            prompt_cita = f"""
            Eres un asistente para {es_porfirianna and 'La Porfirianna (restaurante)' or 'servicios digitales'}.
            Extrae la información de la {es_porfirianna and 'orden/pedido' or 'cita/servicio'} solicitado basándote en este mensaje y el historial.
            
            MENSAJE ACTUAL: "{mensaje}"
            
            HISTORIAL DE CONVERSACIÓN:
            {contexto_historial}
            
            SERVICIOS/PRODUCTOS DISPONIBLES:
            {servicios_texto}
            
            Devuelve un JSON con estos campos:
            - servicio_solicitado (string: nombre del servicio que desea, debe coincidir con alguno disponible)
            - fecha_sugerida (string formato YYYY-MM-DD o null)
            - hora_sugerida (string formato HH:MM o null)
            - nombre_cliente (string o null)
            - telefono (string: {numero})
            - estado (siempre "pendiente")
            - datos_completos (boolean: true si tiene todos los datos necesarios)
            
            Si el mensaje no contiene información de pedido/cita, devuelve servicio_solicitado: null.
            """
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt_cita}],
            "temperature": 0.3,
            "max_tokens": 500
        }
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        respuesta_ia = data['choices'][0]['message']['content'].strip()
        
        # Extraer JSON de la respuesta
        json_match = re.search(r'\{.*\}', respuesta_ia, re.DOTALL)
        if json_match:
            info_cita = json.loads(json_match.group())
            
            # MEJORA: Procesar fechas relativas como "hoy" y "mañana"
            if info_cita.get('fecha_sugerida'):
                if info_cita['fecha_sugerida'].lower() in ['hoy', 'today']:
                    info_cita['fecha_sugerida'] = datetime.now().strftime('%Y-%m-%d')
                elif info_cita['fecha_sugerida'].lower() in ['mañana', 'tomorrow']:
                    info_cita['fecha_sugerida'] = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
            
            # Buscar información adicional del servicio
            if info_cita.get('servicio_solicitado'):
                servicio_nombre = info_cita['servicio_solicitado']
                # Buscar detalles adicionales del servicio en la tabla precios
                for producto in precios:
                    if producto.get('servicio') and servicio_nombre.lower() in producto['servicio'].lower():
                        info_cita['detalles_servicio'] = {
                            'descripcion': producto.get('descripcion', ''),
                            'categoria': producto.get('categoria', ''),
                            'precio': str(producto.get('precio', '0')),
                            'precio_menudeo': str(producto.get('precio_menudeo', '0')) if producto.get('precio_menudeo') else None
                        }
                        break
            
            app.logger.info(f"📅 Información de cita extraída: {json.dumps(info_cita)}")
            return info_cita
        else:
            app.logger.warning(f"⚠️ No se pudo extraer JSON de la respuesta IA")
            return None
            
    except Exception as e:
        app.logger.error(f"Error extrayendo info de cita: {e}")
        return None

@app.route('/debug-headers')
def debug_headers():
    headers = {k: v for k, v in request.headers.items()}
    config = obtener_configuracion_por_host()
    return jsonify({
        'headers': headers,
        'detected_host': request.headers.get('Host'),
        'config_dominio': config.get('dominio'),
        'config_db_name': config.get('db_name')
    })

@app.route('/debug-dominio')
def debug_dominio():
    host = request.headers.get('Host', 'desconocido')
    user_agent = request.headers.get('User-Agent', 'desconocido')
    
    return f"""
    <h1>Información del Dominio</h1>
    <p><strong>Dominio detectado:</strong> {host}</p>
    <p><strong>User-Agent:</strong> {user_agent}</p>
    <p><strong>Hora:</strong> {datetime.now()}</p>
    
    <h2>Probar ambos dominios:</h2>
    <ul>
        <li><a href="https://smartwhats.mektia.com/debug-dominio">smartwhats.mektia.com</a></li>
        <li><a href="https://laporfirianna.mektia.com/debug-dominio">laporfirianna.mektia.com</a></li>
    </ul>
    """

def get_country_flag(numero):
    if not numero:
        return None
    numero = str(numero)
    if numero.startswith('+'):
        numero = numero[1:]
    for i in range(3, 0, -1):
        prefijo = numero[:i]
        if prefijo in PREFIJOS_PAIS:
            codigo = PREFIJOS_PAIS[prefijo]
            return f"https://flagcdn.com/24x18/{codigo}.png"
    return None

# ——— Subpestañas válidas ———
SUBTABS = ['negocio', 'personalizacion', 'precios', 'restricciones', 'asesores']

@app.route('/kanban/data')
def kanban_data(config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)

        # Obtener columnas
        cursor.execute("SELECT * FROM kanban_columnas ORDER BY orden")
        columnas = cursor.fetchall()

        # Obtener chats con nombres de contactos
        cursor.execute("""
            SELECT 
                cm.numero,
                cm.columna_id,
                MAX(c.timestamp) AS ultima_fecha,
                (SELECT mensaje FROM conversaciones 
                WHERE numero = cm.numero 
                ORDER BY timestamp DESC LIMIT 1) AS ultimo_mensaje,
                COALESCE(MAX(cont.alias), MAX(cont.nombre), cm.numero) AS nombre_mostrado,
                (SELECT COUNT(*) FROM conversaciones 
                WHERE numero = cm.numero AND respuesta IS NULL) AS sin_leer
            FROM chat_meta cm
            LEFT JOIN contactos cont ON cont.numero_telefono = cm.numero
            LEFT JOIN conversaciones c ON c.numero = cm.numero
            GROUP BY cm.numero, cm.columna_id
            ORDER BY ultima_fecha DESC
        """)
        chats = cursor.fetchall()

        # Convertir timestamps
        for chat in chats:
            if chat.get('ultima_fecha'):
                if chat['ultima_fecha'].tzinfo is None:
                    chat['ultima_fecha'] = tz_mx.localize(chat['ultima_fecha'])
                else:
                    chat['ultima_fecha'] = chat['ultima_fecha'].astimezone(tz_mx)

        cursor.close()
        conn.close()

        return jsonify({
            'columnas': columnas,
            'chats': chats,
            'timestamp': datetime.now().isoformat(),
            'total_chats': len(chats)
        })
        
    except Exception as e:
        app.logger.error(f"🔴 Error en kanban_data: {e}")
        return jsonify({'error': str(e)}), 500

def sanitize_whatsapp_text(text):
    """
    Limpia artefactos típicos de extracción desde Excel (p.ej. excel_unzip_img_...),
    colapsa espacios y mantiene links intactos.
    """
    if not text:
        return text

    try:
        # 1) Eliminar tokens generados por el unzip de .xlsx (con o sin extensión)
        text = re.sub(r'excel(?:_unzip)?_img_[\w\-\._]+(?:\.[a-zA-Z]{2,4})?', ' ', text, flags=re.IGNORECASE)

        # 2) Eliminar repeticiones sobrantes de la misma cadena (por si quedó repetido)
        text = re.sub(r'(\b\s){2,}', ' ', text)

        # 3) Reemplazar múltiples saltos de línea/espacios por uno solo y limpiar espacios alrededor de saltos
        text = re.sub(r'\s*\n\s*', '\n', text)
        text = re.sub(r'[ \t]{2,}', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        # 4) Quitar espacios duplicados resultantes y trim
        text = re.sub(r' {2,}', ' ', text).strip()

        # 5) Si la línea contiene solo "Imagen:" o "Imagen: " repetido, normalizar
        text = re.sub(r'(Imagen:\s*){2,}', 'Imagen: ', text, flags=re.IGNORECASE)

        return text
    except Exception as e:
        app.logger.warning(f"⚠️ sanitize_whatsapp_text falló: {e}")
        return text.strip() if isinstance(text, str) else text

def load_config(config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS configuracion (
            id INT PRIMARY KEY DEFAULT 1,
            ia_nombre VARCHAR(100),
            negocio_nombre VARCHAR(100),
            descripcion TEXT,
            url VARCHAR(255),
            direccion VARCHAR(255),
            telefono VARCHAR(50),
            correo VARCHAR(100),
            que_hace TEXT,
            tono VARCHAR(50),
            lenguaje VARCHAR(50),
            restricciones TEXT,
            palabras_prohibidas TEXT,
            max_mensajes INT DEFAULT 10,
            tiempo_max_respuesta INT DEFAULT 30,
            logo_url VARCHAR(255),
            nombre_empresa VARCHAR(100),
            app_logo VARCHAR(255),
            calendar_email VARCHAR(255),
            -- Asesores de ventas
            asesor1_nombre VARCHAR(100),
            asesor1_telefono VARCHAR(50),
            asesor2_nombre VARCHAR(100),
            asesor2_telefono VARCHAR(50)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')
    cursor.execute("SELECT * FROM configuracion WHERE id = 1;")
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        return {'negocio': {}, 'personalizacion': {}, 'restricciones': {}, 'asesores': {}}

    negocio = {
        'ia_nombre': row.get('ia_nombre'),
        'negocio_nombre': row.get('negocio_nombre'),
        'descripcion': row.get('descripcion'),
        'url': row.get('url'),
        'direccion': row.get('direccion'),
        'telefono': row.get('telefono'),
        'correo': row.get('correo'),
        'que_hace': row.get('que_hace'),
        'logo_url': row.get('logo_url', ''),
        'nombre_empresa': row.get('nombre_empresa', 'SmartWhats'),
        'app_logo': row.get('app_logo', ''),
        'calendar_email': row.get('calendar_email', '')
    }
    personalizacion = {
        'tono': row.get('tono'),
        'lenguaje': row.get('lenguaje'),
    }
    restricciones = {
        'restricciones': row.get('restricciones', ''),
        'palabras_prohibidas': row.get('palabras_prohibidas', ''),
        'max_mensajes': row.get('max_mensajes', 10),
        'tiempo_max_respuesta': row.get('tiempo_max_respuesta', 30)
    }
    asesores = {
        'asesor1_nombre': row.get('asesor1_nombre', ''),
        'asesor1_telefono': row.get('asesor1_telefono', ''),
        'asesor2_nombre': row.get('asesor2_nombre', ''),
        'asesor2_telefono': row.get('asesor2_telefono', '')
    }
    return {'negocio': negocio, 'personalizacion': personalizacion, 'restricciones': restricciones, 'asesores': asesores}

def crear_tabla_citas(config=None):
    """Crea la tabla para almacenar las citas"""
    conn = get_db_connection(config)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS citas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            numero_cliente VARCHAR(20),
            servicio_solicitado VARCHAR(200),
            fecha_propuesta DATE,
            hora_propuesta TIME,
            nombre_cliente VARCHAR(100),
            telefono VARCHAR(20),
            estado ENUM('pendiente', 'confirmada', 'cancelada') DEFAULT 'pendiente',
            fecha_creacion DATETIME DEFAULT CURRENT_TIMESTAMP,
            fecha_confirmacion DATETIME NULL,
            notas TEXT,
            FOREIGN KEY (numero_cliente) REFERENCES contactos(numero_telefono)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')
    
    conn.commit()
    cursor.close()
    conn.close()

def guardar_cita(info_cita, config=None):
    """Guarda la cita en la base de datos, la agenda en Google Calendar y registra en notificaciones_ia"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor()
        # NUEVO: Verificar si existe una cita similar en los últimos minutos
        cursor.execute('''
            SELECT id FROM citas
            WHERE numero_cliente = %s 
            AND servicio_solicitado = %s 
            AND fecha_creacion > NOW() - INTERVAL 5 MINUTE
        ''', (
            info_cita.get('telefono'),
            info_cita.get('servicio_solicitado')
        ))
        
        existing_cita = cursor.fetchone()
        if existing_cita:
            app.logger.info(f"⚠️ Cita similar ya existe (ID: {existing_cita[0]}), evitando duplicado")
            cursor.close()
            conn.close()
            return existing_cita[0]  # Retorna el ID de la cita existente
        

        # Crear tabla notificaciones_ia si no existe con la estructura requerida
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notificaciones_ia (
                id INT AUTO_INCREMENT PRIMARY KEY,
                numero VARCHAR(20),
                tipo VARCHAR(20),
                resumen TEXT,
                estado VARCHAR(20) DEFAULT 'pendiente',
                mensaje TEXT,
                evaluacion_ia JSON,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                calendar_event_id VARCHAR(255),
                INDEX idx_numero (numero),
                INDEX idx_timestamp (timestamp)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        ''')
        conn.commit()

        # Asegurarnos de que las columnas esperadas EXISTAN (por si la tabla venía de esquema antiguo)
        try:
            cursor.execute("SHOW COLUMNS FROM notificaciones_ia")
            existing_cols = {row[0] for row in cursor.fetchall()}
            required = {
                'tipo': "VARCHAR(20)",
                'resumen': "TEXT",
                'estado': "VARCHAR(20) DEFAULT 'pendiente'",
                'mensaje': "TEXT",
                'evaluacion_ia': "JSON",
                'calendar_event_id': "VARCHAR(255)"
            }
            alters = []
            for col, col_def in required.items():
                if col not in existing_cols:
                    alters.append(f"ADD COLUMN {col} {col_def}")
            if alters:
                sql = f"ALTER TABLE notificaciones_ia {', '.join(alters)}"
                cursor.execute(sql)
                conn.commit()
                app.logger.info(f"🔧 Columnas añadidas a notificaciones_ia: {', '.join([a.split()[2] for a in alters])}")
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo asegurar columnas en notificaciones_ia: {e}")

        # Guardar en tabla citas
        cursor.execute('''
            INSERT INTO citas (
                numero_cliente, servicio_solicitado, fecha_propuesta,
                hora_propuesta, nombre_cliente, telefono, estado
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (
            info_cita.get('telefono'),
            info_cita.get('servicio_solicitado'),
            info_cita.get('fecha_sugerida'),
            info_cita.get('hora_sugerida'),
            info_cita.get('nombre_cliente'),
            info_cita.get('telefono'),
            'pendiente'
        ))
        
        conn.commit()
        cita_id = cursor.lastrowid
        
        # Determinar si la cita es para un día futuro (al menos 1 día después)
        evento_id = None
        debe_agendar = False
        
        if info_cita.get('fecha_sugerida'):
            try:
                fecha_cita = datetime.strptime(info_cita.get('fecha_sugerida'), '%Y-%m-%d').date()
                fecha_actual = datetime.now().date()
                
                # Solo agendar si la fecha es al menos un día después
                if (fecha_cita - fecha_actual).days >= -30:
                    debe_agendar = True
                    app.logger.info(f"✅ Cita para fecha futura ({fecha_cita}), se agendará en Calendar")
                else:
                    app.logger.info(f"ℹ️ Cita para hoy o pasada ({fecha_cita}), no se agendará en Calendar")
            except Exception as e:
                app.logger.error(f"Error procesando fecha: {e}")
        
        # Agendar en Google Calendar solo si es para un día futuro
        if debe_agendar:
            service = autenticar_google_calendar(config)
            if service:
                evento_id = crear_evento_calendar(service, info_cita, config)
                if evento_id:
                    # Asegurarnos de que la columna exista antes de actualizar citas
                    try:
                        cursor.execute("SHOW COLUMNS FROM citas LIKE 'evento_calendar_id'")
                        if cursor.fetchone() is None:
                            cursor.execute("ALTER TABLE citas ADD COLUMN evento_calendar_id VARCHAR(255) DEFAULT NULL")
                            conn.commit()
                            app.logger.info("🔧 Columna 'evento_calendar_id' creada en tabla 'citas'")

                        cursor.execute('''
                            UPDATE citas SET evento_calendar_id = %s WHERE id = %s
                        ''', (evento_id, cita_id))
                        conn.commit()
                        app.logger.info(f"✅ Evento de calendar guardado: {evento_id}")
                    except Exception as e:
                        app.logger.error(f'❌ Error guardando evento_calendar_id en citas: {e}')
        
        # Guardar en notificaciones_ia
        es_porfirianna = 'laporfirianna' in config.get('dominio', '')
        tipo_solicitud = "pedido" if es_porfirianna else "cita"
        
        # Crear resumen para la notificación
        detalles_servicio = info_cita.get('detalles_servicio', {})
        descripcion_servicio = detalles_servicio.get('descripcion', '')
        
        resumen = f"{tipo_solicitud.capitalize()}: {info_cita.get('servicio_solicitado')} - "
        resumen += f"Cliente: {info_cita.get('nombre_cliente')} - "
        resumen += f"Fecha: {info_cita.get('fecha_sugerida')} {info_cita.get('hora_sugerida')}"
        
        # Construir evaluación IA en formato JSON
        evaluacion_ia = {
            'servicio_solicitado': info_cita.get('servicio_solicitado'),
            'detalles_servicio': detalles_servicio,
            'fecha_sugerida': info_cita.get('fecha_sugerida'),
            'hora_sugerida': info_cita.get('hora_sugerida'),
            'nombre_cliente': info_cita.get('nombre_cliente'),
            'cita_id': cita_id,
            'calendar_event_id': evento_id
        }
        mensaje_notificacion = f"""🆕 *NUEVA CITA REGISTRADA* - ID: #{cita_id}

        👤 *Cliente:* {info_cita.get('nombre_cliente', 'No especificado')}
        📞 *Teléfono:* {info_cita.get('telefono')}
        🛠️ *Servicio:* {info_cita.get('servicio_solicitado', 'No especificado')}
        📅 *Fecha:* {info_cita.get('fecha_sugerida', 'No especificada')}
        ⏰ *Hora:* {info_cita.get('hora_sugerida', 'No especificada')}

        ⏰ *Registrada:* {datetime.now().strftime('%d/%m/%Y %H:%M')}

        💼 *Dominio:* {config.get('dominio', 'smartwhats.mektia.com')}
        """

        # Enviar mensaje al número específico
        enviar_mensaje('5214493432744', mensaje_notificacion, config)
        enviar_mensaje('5214491182201', mensaje_notificacion, config)
        app.logger.info(f"✅ Notificación de cita enviada a 5214493432744, ID: {cita_id}")
        
        
        # Guardar en notificaciones_ia
        cursor.execute('''
            INSERT INTO notificaciones_ia (
                numero, tipo, resumen, estado, mensaje, evaluacion_ia, calendar_event_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (
            info_cita.get('telefono'),
            tipo_solicitud,
            resumen,
            'pendiente',
            json.dumps(info_cita),  # Guardar toda la info de la cita como mensaje
            json.dumps(evaluacion_ia),
            evento_id
        ))
        conn.commit()
        cursor.close()
        conn.close()
        
        return cita_id
        
    except Exception as e:
        app.logger.error(f"Error guardando cita: {e}")
        app.logger.error(traceback.format_exc())
        return None
    
def enviar_confirmacion_cita(numero, info_cita, cita_id, config=None):
    """Envía confirmación de cita por WhatsApp"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    # Determinar el tipo de negocio
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    tipo_solicitud = "pedido" if es_porfirianna else "cita"
    
    try:
        mensaje_confirmacion = f"""
        📅 *Confirmación de {tipo_solicitud}* - ID: #{cita_id}

        ¡Hola! Hemos recibido tu solicitud de {tipo_solicitud}:

        *{'Platillo' if es_porfirianna else 'Servicio'}:* {info_cita.get('servicio_solicitado', 'Por confirmar')}
        *Fecha sugerida:* {info_cita.get('fecha_sugerida', 'Por confirmar')}
        *Hora sugerida:* {info_cita.get('hora_sugerida', 'Por confirmar')}

        📞 *Tu número:* {numero}

        ⏰ *Próximos pasos:*
        Nos pondremos en contacto contigo dentro de las próximas 24 horas para confirmar la disponibilidad.

        ¿Necesitas hacer algún cambio? Responde a este mensaje.

        ¡Gracias por confiar en nosotros! 🙏
        """
        
        enviar_mensaje(numero, mensaje_confirmacion, config)
        app.logger.info(f"✅ Confirmación de {tipo_solicitud} enviada a {numero}, ID: {cita_id}")
        
    except Exception as e:
        app.logger.error(f"Error enviando confirmación de {tipo_solicitud}: {e}")

def enviar_alerta_cita_administrador(info_cita, cita_id, config=None):
    """Envía alerta al administrador sobre nueva cita con más detalles del servicio"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    # Determinar el tipo de negocio
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    tipo_solicitud = "pedido" if es_porfirianna else "cita"
    
    try:
        # Obtener detalles adicionales del servicio si existen
        detalles_servicio = info_cita.get('detalles_servicio', {})
        descripcion_servicio = detalles_servicio.get('descripcion', 'No hay descripción disponible')
        categoria_servicio = detalles_servicio.get('categoria', 'Sin categoría')
        precio_servicio = detalles_servicio.get('precio_menudeo') or detalles_servicio.get('precio', 'No especificado')
        
        mensaje_alerta = f"""
        🚨 *NUEVA SOLICITUD DE {tipo_solicitud.upper()}* - ID: #{cita_id}

        *Cliente:* {info_cita.get('nombre_cliente', 'No especificado')}
        *Teléfono:* {info_cita.get('telefono')}

        *{'Platillo' if es_porfirianna else 'Servicio'} solicitado:* {info_cita.get('servicio_solicitado', 'No especificado')}
        *Categoría:* {categoria_servicio}
        *Precio:* ${precio_servicio} {info_cita.get('moneda', 'MXN')}
        
        *Descripción:* {descripcion_servicio[:150]}{'...' if len(descripcion_servicio) > 150 else ''}

        *Fecha sugerida:* {info_cita.get('fecha_sugerida', 'No especificada')}
        *Hora sugerida:* {info_cita.get('hora_sugerida', 'No especificada')}

        ⏰ *Fecha de solicitud:* {datetime.now().strftime('%d/%m/%Y %H:%M')}

        📋 *Acción requerida:* Contactar al cliente para confirmar disponibilidad.
        """
        
        # Enviar a ambos números
        enviar_mensaje(ALERT_NUMBER, mensaje_alerta, config)
        enviar_mensaje('5214493432744', mensaje_alerta, config)
        app.logger.info(f"✅ Alerta de {tipo_solicitud} enviada a ambos administradores, ID: {cita_id}")
        
    except Exception as e:
        app.logger.error(f"Error enviando alerta de {tipo_solicitud}: {e}")

@app.route('/uploads/<filename>')
def serve_uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)

# Crear directorio de uploads al inicio
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Also create the logos subdirectory
os.makedirs(os.path.join(UPLOAD_FOLDER, 'logos'), exist_ok=True)

def extraer_servicio_del_mensaje(mensaje, config=None):
    """Extrae el servicio del mensaje usando keywords simples"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    mensaje_lower = mensaje.lower()
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    
    if es_porfirianna:
        # Palabras clave para La Porfirianna
        platillos = ['gordita', 'taco', 'quesadilla', 'sope', 'torta', 'comida', 'platillo']
        for platillo in platillos:
            if platillo in mensaje_lower:
                return mensaje  # Devolver el mensaje completo como descripción
        return None
    else:
        # Palabras clave para Mektia
        servicios = ['página web', 'sitio web', 'app', 'aplicación', 'software', 
                    'marketing', 'diseño', 'hosting', 'ecommerce', 'tienda online']
        for servicio in servicios:
            if servicio in mensaje_lower:
                return servicio
        return None

def extraer_fecha_del_mensaje(mensaje):
    """Extrae fechas relativas simples del mensaje"""
    mensaje_lower = mensaje.lower()
    
    hoy = datetime.now()
    
    if 'mañana' in mensaje_lower:
        return (hoy + timedelta(days=1)).strftime('%Y-%m-%d')
    elif 'pasado mañana' in mensaje_lower:
        return (hoy + timedelta(days=2)).strftime('%Y-%m-%d')
    elif 'lunes' in mensaje_lower:
        # Calcular próximo lunes
        dias_hasta_lunes = (7 - hoy.weekday()) % 7
        if dias_hasta_lunes == 0:
            dias_hasta_lunes = 7
        return (hoy + timedelta(days=dias_hasta_lunes)).strftime('%Y-%m-%d')
    # Agregar más patrones según necesites
    
    return None

def extraer_nombre_del_mensaje(mensaje):
    """Intenta extraer un nombre del mensaje"""
    # Patrón simple para nombres (2-3 palabras)
    patron_nombre = r'^[A-Za-zÁáÉéÍíÓóÚúÑñ]{2,20} [A-Za-zÁáÉéÍíÓóÚúÑñ]{2,20}( [A-Za-zÁáÉéÍíÓóÚúÑñ]{2,20})?$'
    
    if re.match(patron_nombre, mensaje.strip()):
        return mensaje.strip()
    
    return None

def solicitar_datos_faltantes_cita(numero, info_cita, config=None):
    """
    Solicita al usuario los datos faltantes para completar la cita/pedido
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    # Determinar el tipo de negocio
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    
    # Identificar qué datos faltan
    datos_faltantes = []
    
    # Validar servicio solicitado (siempre requerido)
    if not info_cita.get('servicio_solicitado') or info_cita.get('servicio_solicitado') == 'null':
        if es_porfirianna:
            datos_faltantes.append("qué platillo deseas ordenar")
        else:
            datos_faltantes.append("qué servicio necesitas")
    
    # Validar fecha (solo requerido para Mektia)
    if not es_porfirianna and (not info_cita.get('fecha_sugerida') or info_cita.get('fecha_sugerida') == 'null'):
        datos_faltantes.append("fecha preferida")
    
    # Validar nombre del cliente (siempre requerido)
    if not info_cita.get('nombre_cliente') or info_cita.get('nombre_cliente') == 'null':
        datos_faltantes.append("tu nombre")
    
@app.route('/configuracion/negocio/publicar-pdf', methods=['POST'])
@login_required
def publicar_pdf_configuracion():
    """Recibe un PDF, imagen o video desde la vista de configuración (negocio), lo guarda en disk y registra metadatos en la BD."""
    config = obtener_configuracion_por_host()
    try:
        if 'public_pdf' not in request.files or request.files['public_pdf'].filename == '':
            flash('❌ No se seleccionó ningún archivo', 'error')
            return redirect(url_for('configuracion_tab', tab='negocio'))

        file = request.files['public_pdf']
        original_name = file.filename or 'uploaded_file'
        # Determinar extensión y si está permitida
        ext = ''
        if '.' in original_name:
            ext = original_name.rsplit('.', 1)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            flash('❌ Tipo de archivo no permitido. Usa PDF, imágenes, videos o documentos permitidos.', 'error')
            return redirect(url_for('configuracion_tab', tab='negocio'))

        # Prefijos distintos según tipo (imagen/pdf/video) — facilita depuración y lectura
        image_exts = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
        video_exts = {'mp4', 'mov', 'webm', 'avi', 'mkv', 'ogg', 'mpeg'}
        if ext in image_exts:
            prefix = 'img'
        elif ext in video_exts:
            prefix = 'video'
        else:
            prefix = 'pdf'  # pdf, docx, txt, xlsx, etc.

        filename = secure_filename(f"{prefix}_{int(time.time())}_{original_name}")

        # Tenant-aware docs directory
        docs_dir, tenant_slug = get_docs_dir_for_config(config)
        filepath = os.path.join(docs_dir, filename)
        file.save(filepath)

        descripcion = (request.form.get('public_pdf_descripcion') or '').strip()

        # Guardar metadatos en tabla documents_publicos (crear si no existe)
        conn = get_db_connection(config)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS documents_publicos (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    filename VARCHAR(255) NOT NULL,
                    filepath VARCHAR(512) NOT NULL,
                    descripcion TEXT,
                    uploaded_by VARCHAR(100),
                    tenant_slug VARCHAR(128),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE KEY uq_filename (filename, tenant_slug)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
            conn.commit()
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo asegurar tabla documents_publicos (CREATE): {e}")

        # Asegurarse de que la columna tenant_slug exista; si no, intentar añadirla.
        try:
            cursor.execute("SHOW COLUMNS FROM documents_publicos")
            existing_cols = [row[0] for row in cursor.fetchall()]
            if 'tenant_slug' not in existing_cols:
                try:
                    cursor.execute("ALTER TABLE documents_publicos ADD COLUMN tenant_slug VARCHAR(128) DEFAULT NULL AFTER uploaded_by")
                    conn.commit()
                    existing_cols.append('tenant_slug')
                    app.logger.info("🔧 Columna 'tenant_slug' añadida a documents_publicos")
                except Exception as e:
                    app.logger.warning(f"⚠️ No se pudo añadir la columna tenant_slug a documents_publicos: {e}")
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo inspeccionar columns de documents_publicos: {e}")

        try:
            user = None
            au = session.get('auth_user')
            if au and isinstance(au, dict):
                user = au.get('user') or str(au.get('id') or '')

            # Insert dinámico según columnas disponibles (robusto ante esquemas antiguos)
            cursor.execute("SHOW COLUMNS FROM documents_publicos")
            cols_info = cursor.fetchall()
            cols = [row[0] for row in cols_info]

            insert_cols = ['filename', 'filepath', 'descripcion', 'uploaded_by']
            values = [filename, filepath, descripcion, user]

            if 'tenant_slug' in cols:
                insert_cols.append('tenant_slug')
                values.append(tenant_slug)

            placeholders = ', '.join(['%s'] * len(values))
            cols_sql = ', '.join(insert_cols)

            sql = f"INSERT INTO documents_publicos ({cols_sql}) VALUES ({placeholders}) ON DUPLICATE KEY UPDATE descripcion=VALUES(descripcion), uploaded_by=VALUES(uploaded_by), filepath=VALUES(filepath), created_at=CURRENT_TIMESTAMP"
            cursor.execute(sql, values)
            conn.commit()
        except Exception as e:
            app.logger.error(f"🔴 Error insertando metadato archivo: {e}")
            conn.rollback()
            flash('❌ Error guardando metadatos en la base de datos', 'error')
            try:
                cursor.close(); conn.close()
            except:
                pass
            # eliminar archivo guardado para evitar basura
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
            except:
                pass
            return redirect(url_for('configuracion_tab', tab='negocio'))

        cursor.close(); conn.close()

        flash('✅ Archivo publicado correctamente', 'success')
        return redirect(url_for('configuracion_tab', tab='negocio'))

    except Exception as e:
        app.logger.error(f"🔴 Error en publicar_pdf_configuracion: {e}")
        app.logger.error(traceback.format_exc())
        flash('❌ Error procesando el archivo', 'error')
        return redirect(url_for('configuracion_tab', tab='negocio')) 


# Insertar cerca de otros helpers de BD (por ejemplo después de get_clientes_conn y get_db_connection)

def _ensure_cliente_plan_columns():
    """Asegura que la tabla `cliente` en la BD de clientes tenga columnas para plan_id y mensajes_incluidos."""
    try:
        conn = get_clientes_conn()
        cur = conn.cursor()
        # Crear columnas si no existen
        cur.execute("SHOW COLUMNS FROM cliente LIKE 'plan_id'")
        if cur.fetchone() is None:
            cur.execute("ALTER TABLE cliente ADD COLUMN plan_id INT DEFAULT NULL")
        cur.execute("SHOW COLUMNS FROM cliente LIKE 'mensajes_incluidos'")
        if cur.fetchone() is None:
            cur.execute("ALTER TABLE cliente ADD COLUMN mensajes_incluidos INT DEFAULT 0")
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        app.logger.warning(f"⚠️ No se pudo asegurar columnas plan en cliente: {e}")

def _ensure_precios_plan_column(config=None):
    """Asegura que la tabla `precios` del tenant tenga la columna mensajes_incluidos (opcional para definir planes)."""
    try:
        conn = get_db_connection(config)
        cur = conn.cursor()
        cur.execute("SHOW COLUMNS FROM precios LIKE 'mensajes_incluidos'")
        if cur.fetchone() is None:
            cur.execute("ALTER TABLE precios ADD COLUMN mensajes_incluidos INT DEFAULT 0")
            conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        app.logger.warning(f"⚠️ No se pudo asegurar columna mensajes_incluidos en precios: {e}")

def asignar_plan_a_cliente_por_user(username, plan_id, config=None):
    """
    Asigna un plan (precios.id) al cliente identificado por `username` (en CLIENTES_DB).
    Copia mensajes_incluidos desde precios (tenant) al registro cliente.mensajes_incluidos.
    """
    try:
        # asegurar columnas
        _ensure_cliente_plan_columns()
        if config is None:
            config = obtener_configuracion_por_host()
        _ensure_precios_plan_column(config)

        # 1) Obtener cliente en CLIENTES_DB
        conn_cli = get_clientes_conn()
        cur_cli = conn_cli.cursor(dictionary=True)
        cur_cli.execute("SELECT id_cliente, telefono FROM cliente WHERE `user` = %s LIMIT 1", (username,))
        cliente = cur_cli.fetchone()
        if not cliente:
            cur_cli.close(); conn_cli.close()
            app.logger.error(f"🔴 Cliente no encontrado para user={username}")
            return False

        # 2) Obtener mensajes_incluidos desde tabla precios del tenant (si existe el plan)
        mensajes_incluidos = 0
        plan_name = None
        try:
            conn_tenant = get_db_connection(config)
            cur_t = conn_tenant.cursor(dictionary=True)
            cur_t.execute("SELECT id, servicio, mensajes_incluidos FROM precios WHERE id = %s LIMIT 1", (plan_id,))
            plan_row = cur_t.fetchone()
            if plan_row:
                mensajes_incluidos = int(plan_row.get('mensajes_incluidos') or 0)
                plan_name = plan_row.get('servicio')
            cur_t.close(); conn_tenant.close()
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo leer plan desde precios (tenant): {e}")

        # 3) Actualizar cliente en CLIENTES_DB
        try:
            cur_cli.execute("""
                UPDATE cliente
                   SET plan_id = %s, mensajes_incluidos = %s
                 WHERE id_cliente = %s
            """, (plan_id, mensajes_incluidos, cliente['id_cliente']))
            conn_cli.commit()
        except Exception as e:
            app.logger.error(f"🔴 Error actualizando cliente con plan: {e}")
            conn_cli.rollback()
            cur_cli.close(); conn_cli.close()
            return False

        cur_cli.close(); conn_cli.close()
        app.logger.info(f"✅ Plan id={plan_id} asignado a user={username} (mensajes_incluidos={mensajes_incluidos}) plan_name={plan_name}")
        return True

    except Exception as e:
        app.logger.error(f"🔴 Excepción en asignar_plan_a_cliente_por_user: {e}")
        return False

def get_plan_status_for_user(username, config=None):
    """
    Retorna el estado del plan para el cliente user:
    { 'plan_id', 'plan_name', 'mensajes_incluidos', 'mensajes_consumidos' }

    Mejora: intenta múltiples variantes del teléfono (limpieza, prefijos 52/521, +) y
    un fallback por coincidencia de últimos dígitos para evitar 0s debidos a formatos.
    """
    try:
        # Obtener cliente desde CLIENTES_DB
        conn_cli = get_clientes_conn()
        cur_cli = conn_cli.cursor(dictionary=True)
        cur_cli.execute("SELECT id_cliente, telefono, plan_id, mensajes_incluidos FROM cliente WHERE `user` = %s LIMIT 1", (username,))
        cliente = cur_cli.fetchone()
        cur_cli.close(); conn_cli.close()
        if not cliente:
            app.logger.info(f"ℹ️ get_plan_status_for_user: cliente no encontrado para user={username}")
            return None

        plan_id = cliente.get('plan_id')
        mensajes_incluidos = int(cliente.get('mensajes_incluidos') or 0)
        plan_name = None

        telefono = (cliente.get('telefono') or '').strip()
        app.logger.info(f"🔍 get_plan_status_for_user: user={username} telefono='{telefono}'")

        mensajes_consumidos = 0
        try:
            if config is None:
                config = obtener_configuracion_por_host()
            conn_t = get_db_connection(config)
            cur_t = conn_t.cursor()

            # Helper: limpiar dígitos
            def only_digits(s):
                return re.sub(r'\D', '', s or '')

            clean_tel = only_digits(telefono)
            tried = []

            # 1) Intentar coincidencia exacta con varias variantes
            variants = []
            if telefono:
                variants.append(telefono)
            if clean_tel:
                variants.append(clean_tel)
                variants.append('+' + clean_tel)
                # Mexico common prefix 52 / 521
                if not clean_tel.startswith('52'):
                    variants.append('52' + clean_tel)
                    variants.append('521' + clean_tel)  # celular formato en algunos sistemas
            # dedupe
            variants = [v for i, v in enumerate(variants) if v and v not in variants[:i]]

            for v in variants:
                tried.append(('exact', v))
                cur_t.execute("SELECT COUNT(*) FROM conversaciones WHERE numero = %s", (v,))
                row = cur_t.fetchone()
                cnt = int(row[0]) if row and row[0] is not None else 0
                app.logger.info(f"🔎 Conteo exact match numero='{v}' => {cnt}")
                if cnt > 0:
                    mensajes_consumidos = cnt
                    break

            # 2) Si sigue 0: intentar comparar solo los últimos dígitos (fallback razonable)
            if mensajes_consumidos == 0 and clean_tel:
                for n in (9, 8, 7):  # probar last 9,8,7 digits
                    last_n = clean_tel[-n:]
                    pattern = f"%{last_n}"
                    tried.append(('like_last', last_n))
                    # Usamos REPLACE para normalizar número en la consulta (quitar +, espacios, guiones)
                    sql = """
                        SELECT COUNT(*) FROM conversaciones
                        WHERE REPLACE(REPLACE(REPLACE(REPLACE(numero, '+', ''), '-', ''), ' ', ''), '(', '') LIKE %s
                    """
                    cur_t.execute(sql, (pattern,))
                    row = cur_t.fetchone()
                    cnt = int(row[0]) if row and row[0] is not None else 0
                    app.logger.info(f"🔎 Conteo LIKE ...{last_n} => {cnt}")
                    if cnt > 0:
                        mensajes_consumidos = cnt
                        break

            # 3) último recurso: contar todas las filas si telefono está vacío (defensivo)
            if mensajes_consumidos == 0 and not telefono:
                app.logger.warning("⚠️ get_plan_status_for_user: telefono vacío, mensajes_consumidos queda 0")
                mensajes_consumidos = 0

            cur_t.close(); conn_t.close()

            app.logger.info(f"✅ get_plan_status_for_user resultados: tried={tried} mensajes_consumidos={mensajes_consumidos}")

        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo contar conversaciones en tenant DB: {e}")
            mensajes_consumidos = 0

        # Intentar leer nombre de plan desde tabla precios si plan_id está presente
        if plan_id:
            try:
                if config is None:
                    config = obtener_configuracion_por_host()
                conn_t2 = get_db_connection(config)
                cur_t2 = conn_t2.cursor(dictionary=True)
                cur_t2.execute("SELECT servicio FROM precios WHERE id = %s LIMIT 1", (plan_id,))
                pr = cur_t2.fetchone()
                if pr:
                    plan_name = pr.get('servicio')
                cur_t2.close(); conn_t2.close()
            except Exception as e:
                app.logger.warning(f"⚠️ No se pudo leer servicio/plan desde precios: {e}")

        return {
            'plan_id': plan_id,
            'plan_name': plan_name,
            'mensajes_incluidos': mensajes_incluidos,
            'mensajes_consumidos': mensajes_consumidos,
            'mensajes_disponibles': max(0, mensajes_incluidos - mensajes_consumidos) if mensajes_incluidos is not None else None
        }

    except Exception as e:
        app.logger.error(f"🔴 Error en get_plan_status_for_user: {e}")
        return None

# --- NEW: helpers to send catalog PDF or textual catalog via WhatsApp --- 
def enviar_documento(numero, file_url, filename, config=None):
    """
    Envía un documento (PDF) por WhatsApp usando Graph API.
    file_url debe ser una URL pública accesible (https://.../uploads/docs/filename).
    """
    if config is None:
        config = obtener_configuracion_por_host()
    try:
        url = f"https://graph.facebook.com/v23.0/{config['phone_number_id']}/messages"
        headers = {
            'Authorization': f'Bearer {config["whatsapp_token"]}',
            'Content-Type': 'application/json'
        }
        payload = {
            'messaging_product': 'whatsapp',
            'to': numero,
            'type': 'document',
            'document': {
                'link': file_url,
                'filename': filename
            }
        }
        app.logger.info(f"📤 Enviando documento a {numero}: {file_url}")
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        app.logger.info(f"📥 Graph API status: {r.status_code} response: {r.text[:1000]}")
        if r.status_code in (200, 201, 202):
            app.logger.info(f"✅ Documento enviado a {numero}: {filename}")
            return True
        else:
            app.logger.error(f"🔴 Error enviando documento ({r.status_code}): {r.text}")
            return False
    except Exception as e:
        app.logger.error(f"🔴 Exception en enviar_documento: {e}")
        return False

def build_texto_catalogo(precios, limit=20):
    """Construye un texto resumen del catálogo (hasta `limit` items)."""
    if not precios:
        return "No hay productos registrados en el catálogo."
    lines = []
    for p in precios[:limit]:
        sku = (p.get('sku') or '').strip()
        nombre = (p.get('servicio') or p.get('modelo') or '').strip()
        precio = p.get('precio_menudeo') or p.get('precio_mayoreo') or p.get('costo') or ''
        precio_str = ''
        try:
            if precio not in (None, ''):
                precio_str = f" - ${float(precio):,.2f}"
        except Exception:
            precio_str = f" - {precio}"
        lines.append(f"{nombre or sku}{(' (SKU:'+sku+')') if sku else ''}{precio_str}")
    texto = "📚 Catálogo (resumen):\n" + "\n".join(lines)
    if len(precios) > limit:
        texto += f"\n\n... y {len(precios)-limit} productos más. Pide 'catálogo completo' para recibir el PDF si está publicado."
    return texto

def seleccionar_mejor_doc(docs, query):
    """
    Selecciona el documento más relevante de la lista `docs` comparando `query`
    contra los campos filename y descripcion. Retorna el row dict seleccionado
    o None si no hay una coincidencia significativa.
    """
    try:
        if not docs:
            return None
        if not query or not str(query).strip():
            return docs[0]

        q = str(query).lower()
        q_tokens = set(re.findall(r'\w{3,}', q))

        best = None
        best_score = 0.0
        now_ts = time.time()

        for d in docs:
            score = 0.0
            desc = (d.get('descripcion') or '').lower()
            fname = (d.get('filename') or '').lower()

            # tokens overlap with description (más peso)
            desc_tokens = set(re.findall(r'\w{3,}', desc))
            common_desc = q_tokens & desc_tokens
            score += len(common_desc) * 3.0

            # tokens overlap with filename (menos peso)
            fname_tokens = set(re.findall(r'\w{3,}', fname.replace('_', ' ')))
            common_fname = q_tokens & fname_tokens
            score += len(common_fname) * 1.5

            # Si la query incluye palabras exactas de la descripción más puntuación
            for t in q_tokens:
                if t and t in desc:
                    score += 0.5

            # Ligero bonus por recencia (favor documentos más recientes)
            try:
                created = d.get('created_at')
                if created:
                    # normalized recency bonus (0..1)
                    age_seconds = (now_ts - created.timestamp()) if hasattr(created, 'timestamp') else 0
                    recency_bonus = max(0, 1 - (age_seconds / (60 * 60 * 24 * 30)))  # 30 días
                    score += recency_bonus * 0.5
            except Exception:
                pass

            if score > best_score:
                best_score = score
                best = d

        # Umbral mínimo para considerar "relevante"
        if best_score >= 1.0:
            app.logger.info(f"📚 seleccionar_mejor_doc: mejor score={best_score} filename={best.get('filename') if best else None}")
            return best

        app.logger.info(f"📚 seleccionar_mejor_doc: ningún documento con score suficiente (best={best_score}), usar el más reciente")
        return docs[0]
    except Exception as e:
        app.logger.warning(f"⚠️ seleccionar_mejor_doc error: {e}")
        return docs[0] if docs else None


def enviar_catalogo(numero, original_text=None, config=None):
    """
    Intenta enviar el PDF público más relevante (documents_publicos),
    si no existe envía un resumen textual del catálogo (primeros 20 productos).
    Usa la descripción del PDF para decidir cuál enviar.
    """
    from flask import has_request_context, request
    if config is None:
        config = obtener_configuracion_por_host()
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SHOW TABLES LIKE 'documents_publicos'")
        if cursor.fetchone():
            cursor.execute("""
                SELECT id, filename, filepath, descripcion, uploaded_by, created_at, tenant_slug
                FROM documents_publicos
                ORDER BY created_at DESC
                LIMIT 20
            """)
            docs = cursor.fetchall()
        else:
            docs = []
        cursor.close(); conn.close()

        usuario_texto = original_text or "[Solicitud de catálogo]"

        if docs:
            # Seleccionar el doc más relevante usando descripción/filename
            mejor = seleccionar_mejor_doc(docs, usuario_texto)
            if not mejor:
                mejor = docs[0]

            filename = mejor.get('filename')
            descripcion = mejor.get('descripcion') or ''

            # Build tenant-aware file_url
            base = None
            try:
                if has_request_context():
                    base = request.url_root.rstrip('/')
                else:
                    dominio = config.get('dominio', os.getenv('MI_DOMINIO', 'localhost')).rstrip('/')
                    base = dominio if dominio.startswith('http') else f"https://{dominio}"
            except Exception:
                dominio = config.get('dominio', os.getenv('MI_DOMINIO', 'localhost')).rstrip('/')
                base = dominio if dominio.startswith('http') else f"https://{dominio}"

            tenant_slug = mejor.get('tenant_slug') or (config.get('dominio') or '').split('.')[0] or 'default'
            file_url = f"{base}/uploads/docs/{tenant_slug}/{filename}"
            app.logger.info(f"📚 Enviar catálogo seleccionado -> file_url: {file_url} (descripcion: {descripcion[:120]})")

            sent = enviar_documento(numero, file_url, filename, config)
            respuesta_text = (f"Te envío el catálogo: {descripcion}" if descripcion else f"Te envío el catálogo: {filename}") if sent else f"Intenté enviar el catálogo pero no fue posible. Puedes descargarlo aquí: {file_url}"

            # Actualizar la fila de mensaje entrante con la respuesta para evitar duplicados
            try:
                actualizar_respuesta(numero, usuario_texto, respuesta_text, config)
            except Exception as e:
                app.logger.warning(f"⚠️ actualizar_respuesta falló, fallback a guardar_conversacion: {e}")
                guardar_conversacion(numero, usuario_texto, respuesta_text, config, imagen_url=file_url if sent else file_url, es_imagen=False)

            return sent
        else:
            # Fallback a texto resumen del catálogo
            precios = obtener_todos_los_precios(config) or []
            texto_catalogo = build_texto_catalogo(precios, limit=20)
            enviar_mensaje(numero, texto_catalogo, config)
            try:
                actualizar_respuesta(numero, usuario_texto, texto_catalogo, config)
            except Exception as e:
                app.logger.warning(f"⚠️ actualizar_respuesta falló en fallback textual: {e}")
                guardar_conversacion(numero, usuario_texto, texto_catalogo, config)
            return True

    except Exception as e:
        app.logger.error(f"🔴 Error en enviar_catalogo: {e}")
        try:
            precios = obtener_todos_los_precios(config) or []
            texto_catalogo = build_texto_catalogo(precios, limit=10)
            enviar_mensaje(numero, texto_catalogo, config)
            try:
                actualizar_respuesta(numero, original_text or "[Solicitud de catálogo]", texto_catalogo, config)
            except:
                guardar_conversacion(numero, original_text or "[Solicitud de catálogo]", texto_catalogo, config)
            return True
        except Exception as ex:
            app.logger.error(f"🔴 Fallback también falló: {ex}")
            return False

@app.route('/autorizar-google')
def autorizar_google():
    """Endpoint para autorizar manualmente con Google"""
    service = autenticar_google_calendar()
    if service:
        flash('✅ Autorización con Google Calendar exitosa', 'success')
    else:
        flash('❌ Error en la autorización con Google Calendar', 'error')
    return redirect(url_for('configuracion_tab', tab='negocio'))

@app.route('/citas')
def ver_citas(config=None):
    """Endpoint para ver citas pendientes"""
    if config is None:
        config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('''
        SELECT c.*, co.nombre, co.alias 
        FROM citas c 
        LEFT JOIN contactos co ON c.numero_cliente = co.numero_telefono 
        ORDER BY c.fecha_creacion DESC
    ''')
    citas = cursor.fetchall()
    
    cursor.close()
    conn.close()
    
    return render_template('citas.html', citas=citas)

def save_config(cfg_all, config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    neg = cfg_all.get('negocio', {})
    per = cfg_all.get('personalizacion', {})
    res = cfg_all.get('restricciones', {})
    ases = cfg_all.get('asesores', {})

    conn = get_db_connection(config)
    cursor = conn.cursor()

    # Asegurar columnas nuevas mínimas (no rompe si ya existen)
    try:
        cursor.execute("SHOW COLUMNS FROM configuracion")
        existing_cols = {row[0] for row in cursor.fetchall()}
    except Exception as e:
        app.logger.warning(f"⚠️ Could not inspect configuracion table columns: {e}")
        existing_cols = set()

    alter_statements = []
    if 'logo_url' not in existing_cols:
        alter_statements.append("ADD COLUMN logo_url VARCHAR(255) DEFAULT NULL")
    if 'calendar_email' not in existing_cols:
        alter_statements.append("ADD COLUMN calendar_email VARCHAR(255) DEFAULT NULL")
    if 'asesor1_nombre' not in existing_cols:
        alter_statements.append("ADD COLUMN asesor1_nombre VARCHAR(100) DEFAULT NULL")
    if 'asesor1_telefono' not in existing_cols:
        alter_statements.append("ADD COLUMN asesor1_telefono VARCHAR(50) DEFAULT NULL")
    if 'asesor2_nombre' not in existing_cols:
        alter_statements.append("ADD COLUMN asesor2_nombre VARCHAR(100) DEFAULT NULL")
    if 'asesor2_telefono' not in existing_cols:
        alter_statements.append("ADD COLUMN asesor2_telefono VARCHAR(50) DEFAULT NULL")

    if alter_statements:
        try:
            sql = f"ALTER TABLE configuracion {', '.join(alter_statements)}"
            cursor.execute(sql)
            conn.commit()
            app.logger.info(f"🔧 configuracion table altered: {alter_statements}")
            # refresh existing_cols
            cursor.execute("SHOW COLUMNS FROM configuracion")
            existing_cols = {row[0] for row in cursor.fetchall()}
        except Exception as e:
            app.logger.warning(f"⚠️ Could not alter configuracion table: {e}")

    try:
        # Mapear posibles campos a valores desde cfg_all
        candidate_map = {
            'ia_nombre': neg.get('ia_nombre'),
            'negocio_nombre': neg.get('negocio_nombre'),
            'descripcion': neg.get('descripcion'),
            'url': neg.get('url'),
            'direccion': neg.get('direccion'),
            'telefono': neg.get('telefono'),
            'correo': neg.get('correo'),
            'que_hace': neg.get('que_hace'),
            'tono': per.get('tono'),
            'lenguaje': per.get('lenguaje'),
            'restricciones': res.get('restricciones'),
            'palabras_prohibidas': res.get('palabras_prohibidas'),
            'max_mensajes': int(res.get('max_mensajes', 10)) if res.get('max_mensajes') is not None else 10,
            'tiempo_max_respuesta': int(res.get('tiempo_max_respuesta', 30)) if res.get('tiempo_max_respuesta') is not None else 30,
            'logo_url': neg.get('logo_url', None) or neg.get('app_logo', None),
            'app_logo': neg.get('app_logo', None),
            'app_nombre': neg.get('ia_nombre', None),
            'nombre_empresa': neg.get('nombre_empresa', None),
            'calendar_email': neg.get('calendar_email', None),
            'asesor1_nombre': ases.get('asesor1_nombre', None),
            'asesor1_telefono': ases.get('asesor1_telefono', None),
            'asesor2_nombre': ases.get('asesor2_nombre', None),
            'asesor2_telefono': ases.get('asesor2_telefono', None)
        }

        # Usar solo columnas que existen en la tabla
        cols_to_write = [col for col in candidate_map.keys() if col in existing_cols]
        if not cols_to_write:
            app.logger.warning("⚠️ No hay columnas conocidas para escribir en configuracion; abortando save_config")
            cursor.close()
            conn.close()
            return

        # Construir listas de columnas/valores y el SQL dinámico
        cols_sql = ', '.join(cols_to_write)
        placeholders = ', '.join(['%s'] * len(cols_to_write))
        values = [candidate_map[c] for c in cols_to_write]

        update_parts = ', '.join([f"{c}=VALUES({c})" for c in cols_to_write])

        sql = f"INSERT INTO configuracion (id, {cols_sql}) VALUES (1, {placeholders}) ON DUPLICATE KEY UPDATE {update_parts}"
        cursor.execute(sql, values)
        conn.commit()
        cursor.close()
        conn.close()
        app.logger.info("✅ Configuración guardada (save_config)")

    except Exception as e:
        app.logger.error(f"🔴 Error guardando configuración (save_config): {e}")
        try:
            cursor.close()
            conn.close()
        except:
            pass
        raise

def obtener_todos_los_precios(config):
    try:
        db = get_db_connection(config)
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM precios
            ORDER BY sku, categoria, modelo;
        """)
        precios = cursor.fetchall()
        cursor.close()
        db.close()
        return precios
    except Exception as e:
        print(f"Error obteniendo precios: {str(e)}")
        return []
        
    except Exception as e:
        print(f"Error obteniendo precios: {str(e)}")
        return []

def obtener_precio_por_id(pid, config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM precios WHERE id=%s;", (pid,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return row

def obtener_precio(servicio_nombre: str, config):
    if config is None:
        config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor()
    cursor.execute("""
        SELECT precio_mayoreo, precio_menudeo
        FROM precios
        WHERE LOWER(servicio)=LOWER(%s)
        LIMIT 1;
    """, (servicio_nombre,))
    res = cursor.fetchone()
    cursor.close()
    conn.close()
    if res:
        return Decimal(res[0]), res[1]
    return None

# ——— Memoria de conversación ———
# REEMPLAZA la función obtener_historial con esta versión mejorada
def obtener_historial(numero, limite=5, config=None):
    """Función compatible con la estructura actual de la base de datos"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT mensaje, respuesta, timestamp 
            FROM conversaciones 
            WHERE numero = %s 
            ORDER BY timestamp DESC 
            LIMIT %s
        """, (numero, limite))
        
        historial = cursor.fetchall()
        cursor.close()
        conn.close()
        
        # Invertir el orden para tener cronológico
        historial.reverse()
        
        app.logger.info(f"📚 Historial obtenido para {numero}: {len(historial)} mensajes")
        return historial
        
    except Exception as e:
        app.logger.error(f"❌ Error al obtener historial: {e}")
        return []
    
# ... existing code ...

def responder_con_ia(mensaje_usuario, numero, es_imagen=False, imagen_base64=None, es_audio=False, transcripcion_audio=None, config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    cfg = load_config(config)
    neg = cfg['negocio']
    ia_nombre = neg.get('ia_nombre', 'Asistente')
    negocio_nombre = neg.get('negocio_nombre', '')
    descripcion = neg.get('descripcion', '')
    que_hace = neg.get('que_hace', '')
    estado_actual = obtener_estado_conversacion(numero, config)
    if estado_actual and estado_actual.get('contexto') == 'SOLICITANDO_CITA':
        return manejar_secuencia_cita(mensaje_usuario, numero, estado_actual, config)
    info_cita = None  # Initialize to avoid UnboundLocalError
    
    # 🔥 INTERCEPTAR SOLICITUDES DE CITA ANTES DE LA IA NORMAL
    if detectar_solicitud_cita_keywords(mensaje_usuario, config):
        app.logger.info(f"📅 Solicitud de cita detectada para {numero}: '{mensaje_usuario}'")
        
        info_cita = extraer_info_cita_mejorado(mensaje_usuario, numero, obtener_historial(numero, limite=5, config=config), config)
        
        if info_cita and info_cita.get('servicio_solicitado'):
            datos_completos, faltantes = validar_datos_cita_completos(info_cita, config)
            
            if datos_completos:
                # Guardar cita completa
                cita_id = guardar_cita(info_cita, config)
                if cita_id:
                    enviar_alerta_cita_administrador(info_cita, cita_id, config)
                    enviar_confirmacion_cita(numero, info_cita, cita_id, config)
                    return f"✅ Cita agendada exitosamente. ID: #{cita_id}. Te hemos enviado una confirmación y agendado en el calendario."
            else:
                # Pedir datos faltantes de manera conversacional
                mensaje_faltantes = "¡Perfecto! Para agendar tu cita, necesito un poco más de información:\n\n"
                
                if 'fecha' in faltantes:
                    mensaje_faltantes += "📅 ¿Qué fecha prefieres? (ej: mañana, 15/10/2023)\n"
                if 'hora' in faltantes:
                    mensaje_faltantes += "⏰ ¿A qué hora te viene bien?\n"
                if 'nombre' in faltantes:
                    mensaje_faltantes += "👤 ¿Cuál es tu nombre completo?\n"
                
                mensaje_faltantes += "\nPor favor, responde con esta información y agendo tu cita automáticamente."
                return mensaje_faltantes
        else:
            # No hay información específica, pedir general
            es_porfirianna = 'laporfirianna' in config.get('dominio', '')
            if es_porfirianna:
                return "¡Claro! Me gustaría tomar tu pedido. ¿Qué platillos deseas ordenar y cuándo te gustaría?"
            else:
                return "¡Claro! Me gustaría agendar una cita para ti. ¿Qué servicio necesitas y cuándo te gustaría?"
    
    # ... existing code continues ...
    # Fetch detailed products/services data from the precios table
    precios = obtener_todos_los_precios(config)
    
    # Format products using the canonical DB fields ...
    productos_formateados = []
    dominio_publico = config.get('dominio', os.getenv('MI_DOMINIO', 'localhost')).rstrip('/')
    
    # 🔥 FUNCIÓN DE LIMPIEZA - FUERA DEL LOOP
    def _clean_field(val, imagen_name):
        if not val:
            return ''
        try:
            s = str(val).strip()
            if not imagen_name:
                return s
            img = str(imagen_name).strip()
            # eliminar coincidencias exactas del nombre de la imagen
            if img and img in s:
                s = s.replace(img, '')
            # eliminar patrones comunes generados por el unzip (ej. excel_unzip_img_289_1760130819)
            s = re.sub(r'excel(_unzip)?_img_[\w\-\._]+', '', s, flags=re.IGNORECASE)
            # limpiar espacios sobrantes
            s = re.sub(r'\s{2,}', ' ', s).strip()
            return s
        except Exception:
            return str(val).strip()
    
    for p in precios[:1000]:
        try:
            # 🔥 OBTENER IMAGEN PRIMERO PARA USARLA EN LA LIMPIEZA
            imagen = (p.get('imagen') or '').strip()
            
            # 🔥 LIMPIAR TODOS LOS CAMPOS DE TEXTO CON LA FUNCIÓN
            sku = _clean_field(p.get('sku'), imagen)
            modelo = _clean_field(p.get('modelo'), imagen)
            titulo = modelo or sku or 'Sin identificador'
            categoria = _clean_field(p.get('categoria'), imagen)
            subcategoria = _clean_field(p.get('subcategoria'), imagen)
            linea = _clean_field(p.get('linea'), imagen)
            descripcion_p = _clean_field(p.get('descripcion'), imagen)
            medidas = _clean_field(p.get('medidas'), imagen)
            proveedor = _clean_field(p.get('proveedor'), imagen)
            status = _clean_field(p.get('status_ws'), imagen) or 'activo'
            catalogo = _clean_field(p.get('catalogo'), imagen)
            
            # 🔥 GENERAR URL DE IMAGEN (SIN LIMPIAR ESTA PARTE)
            if imagen:
                if imagen.lower().startswith('http'):
                    imagen_url = imagen
                else:
                    if dominio_publico.startswith('http'):
                        base = dominio_publico.rstrip('/')
                    else:
                        base = f"https://{dominio_publico}"
                    imagen_url = f"{base}/uploads/productos/{imagen}"
            else:
                imagen_url = ''
                
            precio_menudeo = p.get('precio_menudeo') or p.get('precio_mayoreo') or p.get('costo') or None
            precio_str = ''
            if precio_menudeo:
                try:
                    precio_str = f"${float(precio_menudeo):,.2f}"
                except Exception:
                    precio_str = str(precio_menudeo)
                    
            parts = [f"{titulo}"]
            if sku:
                parts.append(f"(SKU: {sku})")
            if categoria:
                parts.append(f"Categoria: {categoria}")
            if subcategoria:
                parts.append(f"Subcategoria: {subcategoria}")
            if linea:
                parts.append(f"Linea: {linea}")
            if precio_str:
                parts.append(f"Precio: {precio_str}")
            if medidas:
                parts.append(f"Medidas: {medidas}")
            if proveedor:
                parts.append(f"Proveedor: {proveedor}")
            if catalogo:
                parts.append(f"Catalogo: {catalogo}")
            if imagen_url:
                parts.append(f"Imagen: {imagen_url}")
            elif imagen:
                parts.append(f"Imagen: {imagen}")
            if descripcion_p:
                parts.append(f"Descripcion: {descripcion_p[:140]}{'...' if len(descripcion_p) > 140 else ''}")
            producto_line = " | ".join(parts)
            producto_line += f" | Status: {status}"
            
        except Exception:
            producto_line = "Sin datos legibles de producto"
        productos_formateados.append(f"- {producto_line}")
        
    productos_texto = "\n".join(productos_formateados)
    if len(precios) > 40:
        productos_texto += f"\n... y {len(precios) - 40} productos/servicios más."

    # 🔥 AÑADIR INSTRUCCIÓN ESPECÍFICA AL SYSTEM PROMPT
    system_prompt = f"""
    Eres {ia_nombre}, asistente virtual de {negocio_nombre}.
    Descripción del negocio: {descripcion}

    Dispones de la siguiente lista de productos/servicios:

    {productos_texto}

    REGLAS IMPORTANTES:
    1. Cuando el usuario pregunte por un producto, responde usando exclusivamente los campos provistos arriba.
    2. NUNCA incluyas en tus respuestas textos como "excel_unzip_img_335_1760366786.png" - estos son errores de base de datos y debes omitirlos completamente.
    3. Si encuentras textos corruptos como "excel_unzip_img_" en las descripciones, omítelos y reconstruye el texto de manera coherente.
    4. Para imágenes, usa las URLs proporcionadas en el campo "Imagen:".
    5. Mantén las respuestas limpias y profesionales.

    Ejemplo de cómo limpiar textos:
    - Texto corrupto: "Mesa redonda alta con base... excel_unzip_img_335_1760366786.png"
    - Texto limpio: "Mesa redonda alta con base..."

    Si el usuario expresa intención de comprar, solicita sus datos para agendar cita.
    """

    # ... el resto de tu función se mantiene igual ...
    historial = obtener_historial(numero, config=config)

    info_cita = extraer_info_cita_mejorado(mensaje_usuario, numero, historial, config)
    if info_cita and info_cita.get('servicio_solicitado'):
        app.logger.info(f"✅ Información de cita detectada: {json.dumps(info_cita)}")
        datos_completos, faltantes = validar_datos_cita_completos(info_cita, config)
        if datos_completos:
            cita_id = guardar_cita(info_cita, config)
            if cita_id:
                app.logger.info(f"✅ Cita guardada con ID: {cita_id}")
                enviar_alerta_cita_administrador(info_cita, cita_id, config)
                enviar_confirmacion_cita(numero, info_cita, cita_id, config)
                es_porfirianna = 'laporfirianna' in config.get('dominio', '')
                confirmacion = f"✅ ¡{es_porfirianna and 'Pedido' or 'Cita'} confirmado(a)! Te envié un mensaje con los detalles y pronto nos pondremos en contacto contigo."
                return confirmacion

    messages_chain = [{'role': 'system', 'content': system_prompt}]
    for entry in historial:
        if entry['mensaje'] and str(entry['mensaje']).strip() != '':
            messages_chain.append({'role': 'user', 'content': entry['mensaje']})
        if entry['respuesta'] and str(entry['respuesta']).strip() != '':
            messages_chain.append({'role': 'assistant', 'content': entry['respuesta']})
    if mensaje_usuario and str(mensaje_usuario).strip() != '':
        if es_imagen and imagen_base64:
            messages_chain.append({
                'role': 'user',
                'content': [
                    {"type": "text", "text": mensaje_usuario},
                    {
                        "type": "image_url", 
                        "image_url": {
                            "url": imagen_base64,
                            "detail": "auto"
                        }
                    }
                ]
            })
        elif es_audio and transcripcion_audio:
            try:
                tu = mensaje_usuario.strip() if mensaje_usuario else ""
                ta = transcripcion_audio.strip() if transcripcion_audio else ""
                if tu and ta and tu != ta:
                    content = f"{ta}\n\n[Mensaje adicional]: {tu}"
                else:
                    content = ta or tu
            except Exception:
                content = transcripcion_audio or mensaje_usuario
            messages_chain.append({'role': 'user', 'content': content})
        elif es_audio and not transcripcion_audio and mensaje_usuario:
            messages_chain.append({'role': 'user', 'content': mensaje_usuario})
        else:
            messages_chain.append({'role': 'user', 'content': mensaje_usuario})

    try:
        if len(messages_chain) <= 1:
            return "¡Hola! ¿En qué puedo ayudarte hoy?"
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "deepseek-chat",
            "messages": messages_chain,
            "temperature": 0.7,
            "max_tokens": 2000
        }
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        data = response.json()
        respuesta = data['choices'][0]['message']['content'].strip()
        respuesta = aplicar_restricciones(respuesta, numero, config)
        return respuesta

    except requests.exceptions.RequestException as e:
        app.logger.error(f"🔴 API error: {e}")
        if hasattr(e, 'response') and e.response:
            app.logger.error(f"🔴 Response: {e.response.text}")
        return 'Lo siento, hubo un error con la IA.'
    except Exception as e: 
        app.logger.error(f"🔴 Error inesperado: {e}")
        return 'Lo siento, hubo un error con la IA.'

# New helpers: enviar_imagen and buscar_sku_en_texto
def enviar_imagen(numero, imagen_ref, config=None):
    """
    Envía una imagen por WhatsApp usando la API de Graph.
    imagen_ref puede ser:
      - URL absoluta (empieza con http)
      - filename almacenado en uploads/productos (enviará https://{dominio}/uploads/productos/{filename})
    Retorna True si la API respondió OK.
    """
    if config is None:
        config = obtener_configuracion_por_host()

    try:
        if not imagen_ref:
            app.logger.warning("🔍 enviar_imagen: imagen_ref vacío")
            return False

        # Determinar URL pública
        if str(imagen_ref).lower().startswith('http'):
            image_url = imagen_ref
        else:
            dominio = config.get('dominio', os.getenv('MI_DOMINIO', '')).rstrip('/')
            # fallback to host-based URL if dominio appears not to be a full domain
            if not dominio.startswith('http'):
                image_url = f"https://{dominio}/uploads/productos/{imagen_ref}"
            else:
                image_url = f"{dominio}/uploads/productos/{imagen_ref}"

        url = f"https://graph.facebook.com/v23.0/{config['phone_number_id']}/messages"
        headers = {
            'Authorization': f'Bearer {config["whatsapp_token"]}',
            'Content-Type': 'application/json'
        }
        payload = {
            'messaging_product': 'whatsapp',
            'to': numero,
            'type': 'image',
            'image': {
                'link': image_url
            }
        }

        app.logger.info(f"📤 Enviando imagen a {numero}: {image_url[:200]}")
        r = requests.post(url, headers=headers, json=payload, timeout=15)
        if r.status_code == 200:
            app.logger.info("✅ Imagen enviada correctamente")
            return True
        else:
            app.logger.error(f"🔴 Error enviando imagen ({r.status_code}): {r.text}")
            return False

    except Exception as e:
        app.logger.error(f"🔴 Exception en enviar_imagen: {e}")
        return False


def buscar_sku_en_texto(texto, precios):
    """
    Busca un SKU presente en 'precios' dentro de 'texto'.
    Devuelve el primer SKU encontrado (exact match substring) o None.
    """
    if not texto or not precios:
        return None
    texto_lower = texto.lower()
    for p in precios:
        sku = (p.get('sku') or '').strip()
        modelo = (p.get('modelo') or '').strip()
        # Check SKU and modelo presence (case-insensitive)
        if sku and sku.lower() in texto_lower:
            return sku
        if modelo and modelo.lower() in texto_lower:
            # prefer returning SKU if exists for that product
            return sku or modelo
    return None

# Agregar esta función para manejar el estado de la conversación
def actualizar_estado_conversacion(numero, contexto, accion, datos=None, config=None):
    """
    Actualiza el estado de la conversación para mantener contexto
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    cursor = conn.cursor()
    
    # Crear tabla de estados si no existe
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS estados_conversacion (
            id INT AUTO_INCREMENT PRIMARY KEY,
            numero VARCHAR(20),
            contexto VARCHAR(50),
            accion VARCHAR(50),
            datos JSON,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_numero (numero),
            INDEX idx_contexto (contexto)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')
    
    # Insertar o actualizar estado
    # Insertar o actualizar estado
    cursor.execute('''
            INSERT INTO estados_conversacion (numero, contexto, accion, datos)
            VALUES (%s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                contexto = VALUES(contexto),
                accion = VALUES(accion),
                datos = VALUES(datos),
                timestamp = CURRENT_TIMESTAMP
        ''', (numero, contexto, accion, json.dumps(datos) if datos else None))
    conn.commit()
    cursor.close()
    conn.close()

def manejar_secuencia_cita(mensaje, numero, estado_actual, config=None):
    """Maneja la secuencia de solicitud de cita/pedido paso a paso"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    paso_actual = estado_actual.get('datos', {}).get('paso', 0)
    datos_guardados = estado_actual.get('datos', {})
    
    # Determinar tipo de negocio
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    
    app.logger.info(f"🔄 Procesando paso {paso_actual} para {numero}: '{mensaje}'")
    
    if paso_actual == 0:  # Inicio - Detectar si es solicitud de cita/pedido
        if detectar_solicitud_cita_keywords(mensaje, config):
            datos_guardados['paso'] = 1
            actualizar_estado_conversacion(numero, "SOLICITANDO_CITA", "solicitar_servicio", datos_guardados, config)
            
            if es_porfirianna:
                return "¡Hola! 👋 Veo que quieres hacer un pedido. ¿Qué platillos te gustaría ordenar?"
            else:
                return "¡Hola! 👋 Veo que quieres agendar una cita. ¿Qué servicio necesitas?"
        else:
            # No es una solicitud de cita, dejar que la IA normal responda
            return None
    
    elif paso_actual == 1:  # Paso 1: Servicio/Platillo
        servicio = extraer_servicio_del_mensaje(mensaje, config)
        if servicio:
            datos_guardados['servicio'] = servicio
            datos_guardados['paso'] = 2
            actualizar_estado_conversacion(numero, "SOLICITANDO_CITA", "solicitar_fecha", datos_guardados, config)
            
            if es_porfirianna:
                return f"¡Perfecto! ¿Para cuándo quieres tu pedido de {servicio}? (puedes decir 'hoy', 'mañana' o una fecha específica)"
            else:
                return f"¡Excelente! ¿Qué fecha te viene bien para la cita de {servicio}? (puedes decir 'mañana', 'próximo lunes', etc.)"
        else:
            if es_porfirianna:
                return "No entendí qué platillo quieres ordenar. ¿Podrías ser más específico? Por ejemplo: 'Quiero 2 gorditas de chicharrón'"
            else:
                return "No entendí qué servicio necesitas. ¿Podrías ser más específico? Por ejemplo: 'Necesito una página web'"
    
    elif paso_actual == 2:  # Paso 2: Fecha
        fecha = extraer_fecha_del_mensaje(mensaje)
        if fecha:
            datos_guardados['fecha'] = fecha
            datos_guardados['paso'] = 3
            actualizar_estado_conversacion(numero, "SOLICITANDO_CITA", "solicitar_nombre", datos_guardados, config)
            
            if es_porfirianna:
                return f"¡Genial! ¿A qué hora prefieres recibir tu pedido el {fecha}? (por ejemplo: 'a las 2pm', 'en la tarde')"
            else:
                return f"¡Bien! ¿A qué hora prefieres la cita el {fecha}? (por ejemplo: 'a las 10am', 'por la tarde')"
        else:
            return "No entendí la fecha. ¿Podrías intentarlo de nuevo? Por ejemplo: 'mañana a las 3pm' o 'el viernes 15'"
    
    elif paso_actual == 3:  # Paso 3: Hora
        # Extraer hora del mensaje (función simple)
        hora = extraer_hora_del_mensaje(mensaje)
        if hora:
            datos_guardados['hora'] = hora
            datos_guardados['paso'] = 4
            actualizar_estado_conversacion(numero, "SOLICITANDO_CITA", "solicitar_nombre", datos_guardados, config)
            
            return "¡Perfecto! ¿Cuál es tu nombre completo?"
        else:
            return "No entendí la hora. ¿Podrías intentarlo de nuevo? Por ejemplo: 'a las 3 de la tarde' o 'a las 10am'"
    
    elif paso_actual == 4:  # Paso 4: Nombre
        nombre = extraer_nombre_del_mensaje(mensaje)
        if nombre:
            datos_guardados['nombre'] = nombre
            datos_guardados['paso'] = 5
            actualizar_estado_conversacion(numero, "SOLICITANDO_CITA", "confirmar_datos", datos_guardados, config)
            
            # Confirmar todos los datos
            if es_porfirianna:
                confirmacion = f"📋 *Resumen de tu pedido:*\n\n"
                confirmacion += f"🍽️ *Platillo:* {datos_guardados['servicio']}\n"
                confirmacion += f"📅 *Fecha:* {datos_guardados['fecha']}\n"
                confirmacion += f"⏰ *Hora:* {datos_guardados.get('hora', 'Por confirmar')}\n"
                confirmacion += f"👤 *Nombre:* {nombre}\n\n"
                confirmacion += "¿Todo correcto? Responde 'sí' para confirmar o 'no' para modificar."
            else:
                confirmacion = f"📋 *Resumen de tu cita:*\n\n"
                confirmacion += f"🛠️ *Servicio:* {datos_guardados['servicio']}\n"
                confirmacion += f"📅 *Fecha:* {datos_guardados['fecha']}\n"
                confirmacion += f"⏰ *Hora:* {datos_guardados.get('hora', 'Por confirmar')}\n"
                confirmacion += f"👤 *Nombre:* {nombre}\n\n"
                confirmacion += "¿Todo correcto? Responde 'sí' para confirmar o 'no' para modificar."
            
            return confirmacion
        else:
            return "No entendí tu nombre. ¿Podrías escribirlo de nuevo? Por ejemplo: 'Juan Pérez'"
    
    elif paso_actual == 5:  # Confirmación final
        if mensaje.lower() in ['sí', 'si', 'sip', 'correcto', 'ok', 'confirmar']:
            # Guardar cita/pedido completo
            info_cita = {
                'servicio_solicitado': datos_guardados['servicio'],
                'fecha_sugerida': datos_guardados['fecha'],
                'hora_sugerida': datos_guardados.get('hora', '12:00'),
                'nombre_cliente': datos_guardados['nombre'],
                'telefono': numero,
                'estado': 'pendiente'
            }
            
            cita_id = guardar_cita(info_cita, config)
            actualizar_estado_conversacion(numero, "CITA_CONFIRMADA", "cita_agendada", {"cita_id": cita_id}, config)
            
            if es_porfirianna:
                return f"✅ *Pedido confirmado* - ID: #{cita_id}\n\nHemos registrado tu pedido. Nos pondremos en contacto contigo pronto para confirmar. ¡Gracias! 🎉"
            else:
                return f"✅ *Cita confirmada* - ID: #{cita_id}\n\nHemos agendado tu cita. Nos pondremos en contacto contigo pronto para confirmar. ¡Gracias! 🎉"
        
        elif mensaje.lower() in ['no', 'cancelar', 'modificar']:
            # Preguntar qué dato modificar
            datos_guardados['paso'] = 6  # Paso de modificación
            actualizar_estado_conversacion(numero, "SOLICITANDO_CITA", "modificar_datos", datos_guardados, config)
            
            return "¿Qué dato quieres modificar?\n- 'servicio' para cambiar el servicio/platillo\n- 'fecha' para cambiar la fecha\n- 'hora' para cambiar la hora\n- 'nombre' para cambiar tu nombre\n- 'todo' para empezar de nuevo"
        
        else:
            return "Por favor responde 'sí' para confirmar o 'no' para modificar."
    
    elif paso_actual == 6:  # Modificación de datos específicos
        if 'servicio' in mensaje.lower():
            datos_guardados['paso'] = 1
            actualizar_estado_conversacion(numero, "SOLICITANDO_CITA", "modificar_servicio", datos_guardados, config)
            return "De acuerdo. ¿Qué servicio/platillo deseas entonces?"
        
        elif 'fecha' in mensaje.lower():
            datos_guardados['paso'] = 2
            actualizar_estado_conversacion(numero, "SOLICITANDO_CITA", "modificar_fecha", datos_guardados, config)
            return "De acuerdo. ¿Qué fecha prefieres?"
        
        elif 'hora' in mensaje.lower():
            datos_guardados['paso'] = 3
            actualizar_estado_conversacion(numero, "SOLICITANDO_CITA", "modificar_hora", datos_guardados, config)
            return "De acuerdo. ¿A qué hora prefieres?"
        
        elif 'nombre' in mensaje.lower():
            datos_guardados['paso'] = 4
            actualizar_estado_conversacion(numero, "SOLICITANDO_CITA", "modificar_nombre", datos_guardados, config)
            return "De acuerdo. ¿Cuál es tu nombre?"
        
        elif 'todo' in mensaje.lower():
            actualizar_estado_conversacion(numero, "SOLICITANDO_CITA", "reiniciar", {}, config)
            if es_porfirianna:
                return "De acuerdo, empecemos de nuevo. ¿Qué platillos deseas ordenar?"
            else:
                return "De acuerdo, empecemos de nuevo. ¿Qué servicio necesitas?"
        
        else:
            return "No entendí qué quieres modificar. Por favor elige: servicio, fecha, hora, nombre o todo."
    
    # Si llegamos aquí, hay un error en el estado
    app.logger.error(f"❌ Estado inválido en secuencia de cita: paso {paso_actual}")
    actualizar_estado_conversacion(numero, "SOLICITANDO_CITA", "reiniciar", {}, config)
    return "Hubo un error en el proceso. Vamos a empezar de nuevo. ¿En qué puedo ayudarte?"

def extraer_hora_del_mensaje(mensaje):
    """Extrae la hora del mensaje de forma simple"""
    mensaje_lower = mensaje.lower()# Convertir a minúsculas para facilitar la búsqueda
    
    # Patrones simples para horas
    patrones_hora = [
        (r'(\d{1,2})\s*(?:am|a\.m\.)', lambda x: f"{int(x):02d}:00"),
        (r'(\d{1,2})\s*(?:pm|p\.m\.)', lambda x: f"{int(x) + 12 if int(x) < 12 else int(x):02d}:00"),
        (r'a las (\d{1,2})', lambda x: f"{int(x):02d}:00"),
        (r'(\d{1,2}):(\d{2})', lambda x, y: f"{int(x):02d}:{y}"),
    ]
    
    for patron, conversion in patrones_hora:
        match = re.search(patron, mensaje_lower)
        if match:
            try:
                grupos = match.groups()
                if len(grupos) == 1:
                    return conversion(grupos[0])
                elif len(grupos) == 2:
                    return conversion(grupos[0], grupos[1])
            except:
                continue
    
    # Horas relativas
    if 'mañana' in mensaje_lower:
        return "09:00"
    elif 'tarde' in mensaje_lower:
        return "15:00"
    elif 'noche' in mensaje_lower:
        return "19:00"
    
    return None
def obtener_estado_conversacion(numero, config=None):
    """Obtiene el estado actual de la conversación"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('''
        SELECT contexto, accion, datos, timestamp 
        FROM estados_conversacion 
        WHERE numero = %s 
        ORDER BY timestamp DESC 
        LIMIT 1
    ''', (numero,))
    
    estado = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if estado and estado['datos']:
        try:
            estado['datos'] = json.loads(estado['datos'])
        except:
            estado['datos'] = {}
    
    # Si el estado es muy viejo (más de 1 hora), ignorarlo
    if estado and estado.get('timestamp'):
        tiempo_transcurrido = datetime.now() - estado['timestamp']
        if tiempo_transcurrido.total_seconds() > 3600:  # 1 hora
            return None
    
    return estado

def obtener_imagen_whatsapp(image_id, config=None):
    """Obtiene la imagen de WhatsApp, la convierte a base64 y guarda localmente"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # 1. Obtener metadata de la imagen
        url_metadata = f"https://graph.facebook.com/v18.0/{image_id}"
        headers = {
            'Authorization': f'Bearer {config["whatsapp_token"]}',
            'Content-Type': 'application/json'
        }
        
        app.logger.info(f"🖼️ Obteniendo metadata de imagen WhatsApp: {url_metadata}")
        response_metadata = requests.get(url_metadata, headers=headers, timeout=30)
        response_metadata.raise_for_status()
        
        metadata = response_metadata.json()
        download_url = metadata.get('url')
        mime_type = metadata.get('mime_type', 'image/jpeg')
        
        if not download_url:
            app.logger.error(f"🔴 No se encontró URL de descarga de imagen: {metadata}")
            return None, None
            
        app.logger.info(f"🖼️ URL de descarga: {download_url}")
        
        # 2. Descargar la imagen
        image_response = requests.get(download_url, headers=headers, timeout=30)
        if image_response.status_code != 200:
            app.logger.error(f"🔴 Error descargando imagen: {image_response.status_code}")
            return None, None
        
        # 3. Guardar la imagen en directorio estático para mostrarla en web
        static_images_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'images', 'whatsapp')
        os.makedirs(static_images_dir, exist_ok=True)
        
        # Nombre seguro para el archivo
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = secure_filename(f"whatsapp_image_{timestamp}.jpg")
        filepath = os.path.join(static_images_dir, filename)
        
        with open(filepath, 'wb') as f:
            f.write(image_response.content)
        
        # 4. Convertir a base64 para OpenAI (si es necesario)
        image_base64 = base64.b64encode(image_response.content).decode('utf-8')
        base64_string = f"data:{mime_type};base64,{image_base64}"
        
        # 5. URL pública para mostrar en web
        public_url = f"/static/images/whatsapp/{filename}"
        
        app.logger.info(f"✅ Imagen guardada: {filepath}")
        app.logger.info(f"🌐 URL web: {public_url}")
        
        return base64_string, public_url
        
    except Exception as e:
        app.logger.error(f"🔴 Error en obtener_imagen_whatsapp: {str(e)}")
        app.logger.error(traceback.format_exc())
        return None, None

@app.route('/procesar-codigo', methods=['POST'])
def procesar_codigo():
    """Procesa el código de autorización manualmente y guarda token tenant-specific en BASE_DIR"""
    try:
        code = request.form.get('codigo')
        if not code:
            return "❌ Error: No se proporcionó código"

        # Determinar tenant por host actual (la autorización manual se inició desde el host correcto)
        config = obtener_configuracion_por_host()
        tenant_domain = config.get('dominio', 'default')

        BASE_DIR = os.path.dirname(os.path.abspath(__file__))
        client_secret_path = os.path.join(BASE_DIR, 'client_secret.json')
        if not os.path.exists(client_secret_path):
            return f"❌ Error: No se encuentra client_secret.json en {BASE_DIR}"

        SCOPES = ['https://www.googleapis.com/auth/calendar']
        redirect_uri = f'https://{request.host}/completar-autorizacion'

        flow = InstalledAppFlow.from_client_secrets_file(client_secret_path, SCOPES, redirect_uri=redirect_uri)
        flow.fetch_token(code=code)
        creds = flow.credentials

        token_filename = f"token_{tenant_domain.replace('.', '_')}.json"
        token_path = os.path.join(BASE_DIR, token_filename)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())

        app.logger.info(f"✅ Token guardado en {token_path} para tenant {tenant_domain}")

        return '''
        <h1>✅ ¡Autorización completada!</h1>
        <p>Google Calendar está ahora configurado correctamente para este dominio.</p>
        <p>Puedes cerrar esta ventana y probar agendar una cita.</p>
        <a href="/">Volver al inicio</a>
        '''

    except Exception as e:
        app.logger.error(f"🔴 Error en procesar_codigo: {e}")
        app.logger.error(traceback.format_exc())
        return f"❌ Error: {str(e)}<br><a href='/autorizar-manual'>Intentar de nuevo</a>"

def procesar_fecha_relativa(fecha_str):
    """
    Función simple de procesamiento de fechas relativas
    """
    if not fecha_str or fecha_str == 'null':
        return None
    
    # Si ya es formato YYYY-MM-DD, devolver tal cual
    if re.match(r'\d{4}-\d{2}-\d{2}', fecha_str):
        return fecha_str
    
    # Lógica básica de procesamiento
    hoy = datetime.now()
    mapping = {
        'próximo lunes': hoy + timedelta(days=(7 - hoy.weekday()) % 7),
        'mañana': hoy + timedelta(days=1),
        'pasado mañana': hoy + timedelta(days=2),
    }
    
    fecha_lower = fecha_str.lower()
    for termino, fecha_calculada in mapping.items():
        if termino in fecha_lower:
            return fecha_calculada.strftime('%Y-%m-%d')
    
    return None

def extraer_info_intervencion(mensaje, numero, historial, config=None):
    """Extrae información relevante para intervención humana"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # Construir contexto del historial
        contexto_historial = "\n".join([
            f"Usuario: {msg['mensaje']}\nAsistente: {msg['respuesta']}" 
            for msg in historial if msg['mensaje'] and msg['respuesta']
        ])
        
        prompt = f"""
        El usuario ha solicitado hablar con un humano. Analiza el mensaje y el historial para extraer información clave.
        
        MENSAJE ACTUAL: "{mensaje}"
        
        HISTORIAL RECIENTE:
        {contexto_historial}
        
        Extrae esta información:
        1. ¿Cuál es el problema o necesidad principal?
        2. ¿Qué ha intentado el usuario hasta ahora?
        3. ¿Hay urgencia o frustración evidente?
        4. ¿Qué información sería útil para un agente humano?
        
        Devuelve un JSON con esta estructura:
        {{
            "problema_principal": "string",
            "intentos_previos": "string",
            "urgencia": "alta/media/baja",
            "informacion_util": "string",
            "resumen": "string"
        }}
        """
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 500
        }
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        respuesta_ia = data['choices'][0]['message']['content'].strip()
        
        # Extraer JSON de la respuesta
        json_match = re.search(r'\{.*\}', respuesta_ia, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            # Fallback si no puede extraer JSON
            return {
                "problema_principal": mensaje,
                "intentos_previos": "No detectados",
                "urgencia": "media",
                "informacion_util": f"Usuario {numero} solicita intervención humana",
                "resumen": f"Usuario solicita humano después de mensaje: {mensaje}"
            }
            
    except Exception as e:
        app.logger.error(f"Error extrayendo info de intervención: {e}")
        return {
            "problema_principal": mensaje,
            "intentos_previos": "Error en análisis",
            "urgencia": "media",
            "informacion_util": f"Usuario {numero} necesita ayuda humana",
            "resumen": f"Solicitud de intervención humana: {mensaje}"
        }

def actualizar_info_contacto_con_nombre(numero, nombre, config=None):
    """
    Actualiza la información del contacto usando el nombre proporcionado desde el webhook
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO contactos 
                (numero_telefono, nombre, plataforma, fecha_actualizacion) 
            VALUES (%s, %s, 'WhatsApp', NOW())
            ON DUPLICATE KEY UPDATE 
                nombre = VALUES(nombre),
                fecha_actualizacion = NOW()
        """, (numero, nombre))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        app.logger.info(f"✅ Contacto actualizado con nombre desde webhook: {numero} -> {nombre}")
        
    except Exception as e:
        app.logger.error(f"🔴 Error actualizando contacto con nombre: {e}")

def guardar_respuesta_imagen(numero, imagen_url, config=None, nota='[Imagen enviada]'):
    """Guarda una entrada en conversaciones representando una respuesta del BOT que contiene una imagen.
    - numero: número del chat
    - imagen_url: URL pública (o ruta) de la imagen
    - nota: texto que se guardará en campo 'respuesta' (por ejemplo '[Imagen enviada]')
    """
    if config is None:
        config = obtener_configuracion_por_host()
    try:
        # Asegurar contacto
        actualizar_info_contacto(numero, config)

        conn = get_db_connection(config)
        cursor = conn.cursor()

        # Insertar como respuesta del BOT: mensaje vacío, respuesta = nota, imagen_url y es_imagen = True
        cursor.execute("""
            INSERT INTO conversaciones (numero, mensaje, respuesta, timestamp, imagen_url, es_imagen)
            VALUES (%s, %s, %s, NOW(), %s, %s)
        """, (numero, '', nota, imagen_url, True))

        conn.commit()
        cursor.close()
        conn.close()

        app.logger.info(f"💾 [BOT] Imagen registrada en conversaciones: {imagen_url} (numero={numero})")
        return True
    except Exception as e:
        app.logger.error(f"❌ Error guardando respuesta-imagen para {numero}: {e}")
        return False

# Replace the existing procesar_mensaje_normal function with this enhanced version
def procesar_mensaje_normal(msg, numero, texto, es_imagen, es_audio, config, imagen_base64=None, transcripcion=None, es_mi_numero=False, es_archivo=False):
    """Procesa mensajes normales (no citas/intervenciones) — ahora envía imagen si el usuario la solicita y existe."""
    try:
        # IA normal
        if numero not in IA_ESTADOS:
            IA_ESTADOS[numero] = {'activa': True, 'prefiere_voz': False}
        elif 'prefiere_voz' not in IA_ESTADOS[numero]:
            IA_ESTADOS[numero]['prefiere_voz'] = False
        respuesta = ""
        responder_con_voz = False
        if IA_ESTADOS[numero]['activa']:
            # 🆕 DETECTAR PREFERENCIA DE VOZ
            if "envíame audio" in texto.lower() or "respuesta en audio" in texto.lower():
                IA_ESTADOS[numero]['prefiere_voz'] = True
                app.logger.info(f"🎵 Usuario {numero} prefiere respuestas de voz")

            responder_con_voz = IA_ESTADOS[numero]['prefiere_voz'] or es_audio

            # Obtener respuesta de IA
            respuesta = responder_con_ia(texto, numero, es_imagen, imagen_base64, es_audio, transcripcion, config)

        # If user asked explicitly for an image (keywords) or IA returned an image markdown/link, try to send the product image
        # --- INSERT: quick catalog request detection in procesar_mensaje_normal ---
        # Localiza la función procesar_mensaje_normal(...) y, cerca del inicio (después de obtener/normalizar 'texto'),
        # agrega este bloque para interceptar peticiones de catálogo antes de llamar a la IA.

        # QUICK CHECK: user asked for the catalog/PDF -> send it and stop (no IA)
        try:
            text_lower = (texto or "").lower()
            catalog_keywords = [
                'catálogo', 'catalogo', 'mostrar catálogo', 'mostrar catalogo',
                'muestrame catálogo', 'muestrame catalogo', 'envíame catálogo', 'envia catálogo',
                'manda catálogo', 'enviame catalogo', 'catalogo completo', 'catálogo completo',
                'ver catálogo', 'ver catalogo', 'catalog'
            ]
            if any(k in text_lower for k in catalog_keywords):
                app.logger.info(f"📚 Petición de catálogo detectada en mensaje: '{texto[:80]}'")
                enviado = enviar_catalogo(numero, original_text=texto, config=config)
                if enviado:
                    # ya guardado dentro de enviar_catalogo -> terminar aquí
                    return
                else:
                    # si no se pudo enviar como documento, se intentó enviar el resumen; terminar
                    return
        except Exception as e:
            app.logger.warning(f"⚠️ Error detectando/enviando catálogo: {e}")
        try:
            precios = obtener_todos_los_precios(config)
            sku_encontrado = buscar_sku_en_texto(texto, precios)
            imagen_encontrada = None

            # 1) Detect markdown image syntax in IA response: ![alt](file_or_url)
            md_match = None
            if isinstance(respuesta, str):
                md = re.search(r'!\[.*?\]\(([^)]+)\)', respuesta)
                if md:
                    md_match = md.group(1).strip()
                    app.logger.info(f"🔍 Markdown image detected in IA response: {md_match}")

            # 2) If user asked (keywords), try to find SKU and image
            keywords_imagen = ['imagen', 'foto', 'foto del', 'muestra', 'muestrame', 'muestra la', 'muéstrame', 'envía la imagen', 'envia la imagen', 'mostrar imagen', 'mostrar foto']
            user_asked_image = any(k in texto.lower() for k in keywords_imagen)

            if user_asked_image and sku_encontrado:
                # Buscar producto por SKU y obtener campo imagen
                for p in precios:
                    if (p.get('sku') or '').strip().lower() == sku_encontrado.lower():
                        imagen_encontrada = p.get('imagen')
                        break

            # 3) Prefer the markdown/image returned by IA (it may include filename or URL)
            if md_match:
                imagen_encontrada = md_match

            # 4) If IA response contains "Imagen: filename" pattern
            if not imagen_encontrada and isinstance(respuesta, str):
                m = re.search(r'Imagen[:\s]*([^\s,;\)\]]+)', respuesta, re.IGNORECASE)
                if m:
                    imagen_encontrada = m.group(1).strip()

            if imagen_encontrada:
                # Normalize: if it's a relative path like /uploads/productos/..., extract filename
                if imagen_encontrada.startswith('/uploads/productos/'):
                    imagen_encontrada = os.path.basename(imagen_encontrada)

                # Confirm file exists locally or it's an absolute URL
                file_path_local = os.path.join(UPLOAD_FOLDER, 'productos', imagen_encontrada)
                file_path_root = os.path.join(UPLOAD_FOLDER, imagen_encontrada)

                sent = False
                if os.path.isfile(file_path_local) or os.path.isfile(file_path_root):
                    # send image by WhatsApp (Graph API image message with link)
                    sent = enviar_imagen(numero, imagen_encontrada, config)
                    if sent:
                        public_path = f"/uploads/productos/{imagen_encontrada}" if os.path.isfile(file_path_local) else f"/uploads/{imagen_encontrada}"
                        # Save as a BOT response (no longer as a user message)
                        guardar_respuesta_imagen(numero, public_path, config, nota=f"[Imagen enviada: {imagen_encontrada} ]")
                        app.logger.info(f"✅ Imagen {imagen_encontrada} enviada a {numero} automáticamente")
                        # Remove image reference from textual response to avoid sending path
                        if isinstance(respuesta, str):
                            respuesta = re.sub(r'!\[.*?\]\([^\)]+\)', '', respuesta)  # remove markdown
                            respuesta = re.sub(re.escape(imagen_encontrada), '', respuesta)
                    else:
                        # fallback: send text with public URL and record as BOT response
                        dominio = config.get('dominio', os.getenv('MI_DOMINIO', '')).rstrip('/')
                        if not dominio.startswith('http'):
                            dominio = f"https://{dominio}"
                        image_url = f"{dominio}/uploads/productos/{imagen_encontrada}"
                        enviar_mensaje(numero, f"No pude enviar la imagen directamente. Puedes verla aquí: {image_url}", config)
                        guardar_respuesta_imagen(numero, image_url, config, nota=f"[Imagen (URL) enviada: {image_url}]")
                else:
                    # If imagen_encontrada is an absolute URL, try sending it
                    if imagen_encontrada.lower().startswith('http'):
                        sent = enviar_imagen(numero, imagen_encontrada, config)
                        if sent:
                            guardar_respuesta_imagen(numero, imagen_encontrada, config, nota=f"[Imagen enviada: {imagen_encontrada}]")
                            # strip url from textual response
                            if isinstance(respuesta, str):
                                respuesta = respuesta.replace(imagen_encontrada, '')
                        else:
                            enviar_mensaje(numero, f"No pude enviar la imagen. Aquí está la ruta: {imagen_encontrada}", config)
                            # Record fallback message as bot text
                            guardar_respuesta_imagen(numero, imagen_encontrada, config, nota=f"[Imagen (URL) mostrada: {imagen_encontrada}]")
                    else:
                        # Try to find by filename in imagenes_productos table
                        imgs = obtener_imagenes_por_sku(sku_encontrado, config) if sku_encontrado else []
                        if imgs:
                            first = imgs[0].get('filename')
                            if first:
                                sent = enviar_imagen(numero, first, config)
                                if sent:
                                    public_path = f"/uploads/productos/{first}"
                                    guardar_respuesta_imagen(numero, public_path, config, nota=f"[Imagen enviada: {first}]")
                                    if isinstance(respuesta, str):
                                        respuesta = respuesta.replace(imagen_encontrada, first)
                        else:
                            # No local image found; inform user (record as bot response)
                            app.logger.info(f"ℹ️ No se encontró físicamente la imagen: {imagen_encontrada}")
                            guardar_respuesta_imagen(numero, '', config, nota="[Imagen no encontrada]")
            else:
                app.logger.debug("ℹ️ No se detectó imagen para enviar automáticamente")
        except Exception as e:
            app.logger.warning(f"⚠️ Error intentando enviar imagen automática: {e}")

        # 🆕 DETECCIÓN Y PROCESAMIENTO DE ARCHIVOS
        if es_archivo and 'document' in msg:
            app.logger.info(f"📎 Procesando archivo enviado por {numero}")

            # Obtener el archivo de WhatsApp
            media_id = msg['document']['id']
            filepath, filename, extension = obtener_archivo_whatsapp(media_id, config)

            if filepath and extension:
                # Extraer texto del archivo
                texto_archivo = extraer_texto_archivo(filepath, extension)

                if texto_archivo:
                    # Determinar tipo de negocio
                    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
                    tipo_negocio = 'laporfirianna' if es_porfirianna else 'mektia'

                    # Analizar con IA
                    analisis = analizar_archivo_con_ia(texto_archivo, tipo_negocio, config)

                    # Construir respuesta
                    respuesta = f"""📎 **He analizado tu archivo** ({filename})

{analisis}

¿Te gustaría que haga algo específico con esta información?"""

                else:
                    respuesta = f"❌ No pude extraer texto del archivo {filename}. ¿Podrías describirme qué contiene?"

                # Limpiar archivo temporal
                try:
                    os.remove(filepath)
                except:
                    pass

            else:
                respuesta = "❌ No pude descargar el archivo. ¿Podrías intentar enviarlo de nuevo?"

            # Enviar respuesta y actualizar conversación existente
            enviar_mensaje(numero, respuesta, config)
            actualizar_respuesta(numero, texto, respuesta, config)  # FIX: corrected variable name
            return

        # 🆕 ENVÍO DE RESPUESTA (VOZ O TEXTO)
        if responder_con_voz and not es_imagen:
            # Intentar enviar respuesta de voz
            audio_filename = f"respuesta_{numero}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            audio_url_local = texto_a_voz(respuesta, audio_filename, config)
            actualizar_respuesta(numero, texto, respuesta, config)  # FIX: corrected variable name
            if audio_url_local:
                # URL pública del audio (ajusta según tu configuración)
                audio_url_publica = f"https://{config.get('dominio', 'smartwhats.mektia.com')}/static/audio/respuestas/{audio_filename}.mp3"

                if enviar_mensaje_voz(numero, audio_url_publica, config):
                    app.logger.info(f"✅ Respuesta de voz enviada a {numero}")
                else:
                    # Fallback a texto
                    enviar_mensaje(numero, respuesta, config)
            else:
                # Fallback a texto
                enviar_mensaje(numero, respuesta, config)
        else:
            # Respuesta normal de texto
            enviar_mensaje(numero, respuesta, config)
            actualizar_respuesta(numero, texto, respuesta, config)  # FIX: corrected variable name

        # 🔄 DETECCIÓN DE INTERVENCIÓN HUMANA (para mensajes normales también)
        if detectar_intervencion_humana_ia(texto, numero, config):
            app.logger.info(f"🚨 Intervención humana detectada en mensaje normal para {numero}")
            resumen = resumen_rafa(numero, config)
            enviar_alerta_humana(numero, texto, resumen, config)

        # KANBAN AUTOMÁTICO
        meta = obtener_chat_meta(numero, config)
        if not meta:
            inicializar_chat_meta(numero, config)

        nueva_columna = evaluar_movimiento_automatico(numero, texto, respuesta, config)
        actualizar_columna_chat(numero, nueva_columna, config)

    except Exception as e:
        app.logger.error(f"🔴 Error procesando mensaje normal: {e}")
@app.route('/chats/data')
def obtener_datos_chat():
    """Endpoint para obtener datos actualizados de la lista de chats"""
    config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    # Query to get chat list data
    cursor.execute("""
        SELECT 
          conv.numero, 
          COUNT(*) AS total_mensajes, 
          cont.imagen_url, 
          COALESCE(cont.alias, cont.nombre, conv.numero) AS nombre_mostrado,
          cont.alias,
          cont.nombre,
          (SELECT mensaje FROM conversaciones 
           WHERE numero = conv.numero 
           ORDER BY timestamp DESC LIMIT 1) AS ultimo_mensaje,
          (SELECT CASE WHEN es_imagen THEN 'imagen' ELSE 'texto' END
           FROM conversaciones 
           WHERE numero = conv.numero 
           ORDER BY timestamp DESC LIMIT 1) AS tipo_mensaje,
          MAX(conv.timestamp) AS ultima_fecha
        FROM conversaciones conv
        LEFT JOIN contactos cont ON conv.numero = cont.numero_telefono
        GROUP BY conv.numero, cont.imagen_url, cont.alias, cont.nombre
        ORDER BY MAX(conv.timestamp) DESC
    """)
    chats = cursor.fetchall()
    
    # Convert timestamps to ISO format for JSON
    for chat in chats:
        if chat.get('ultima_fecha'):
            if chat['ultima_fecha'].tzinfo is not None:
                chat['ultima_fecha'] = chat['ultima_fecha'].astimezone(tz_mx).isoformat()
            else:
                chat['ultima_fecha'] = pytz.utc.localize(chat['ultima_fecha']).astimezone(tz_mx).isoformat()
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'chats': chats,
        'timestamp': datetime.now().timestamp(),
        'total_chats': len(chats)
    })

@app.route('/uploads/docs/<path:relpath>')
def serve_public_docs(relpath):
    """Serve published files from uploads/docs/<tenant_slug>/<filename> (tenant-aware).
    Accepts paths like 'tenant_slug/filename.pdf' so Facebook can fetch the file_url built by enviar_catalogo.
    """
    try:
        # Base docs dir
        docs_base = os.path.join(app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER), 'docs')
        # Avoid path traversal attacks by normalizing
        safe_relpath = os.path.normpath(relpath)
        # If normalized path tries to go above docs_base, block it
        if safe_relpath.startswith('..') or os.path.isabs(safe_relpath):
            app.logger.warning(f"⚠️ Attempted path traversal in serve_public_docs: {relpath}")
            abort(404)

        full_path = os.path.join(docs_base, safe_relpath)
        if not os.path.isfile(full_path):
            app.logger.info(f"❌ Public doc not found: {full_path}")
            abort(404)

        directory = os.path.dirname(full_path)
        filename = os.path.basename(full_path)
        return send_from_directory(directory, filename)
    except Exception as e:
        app.logger.error(f"🔴 Error serving public doc {relpath}: {e}")
        abort(500)

def actualizar_respuesta(numero, mensaje, respuesta, config=None):
    """Actualiza la respuesta para un mensaje ya guardado"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # Asegurar que el contacto existe
        actualizar_info_contacto(numero, config)
        
        conn = get_db_connection(config)
        cursor = conn.cursor()
        
        # Log before update
        app.logger.info(f"🔄 TRACKING: Actualizando respuesta para mensaje de {numero}, timestamp: {datetime.now(tz_mx).isoformat()}")
        
        # Actualizar el registro más reciente que tenga este mensaje y respuesta NULL
        cursor.execute("""
            UPDATE conversaciones 
            SET respuesta = %s 
            WHERE numero = %s 
              AND mensaje = %s 
              AND respuesta IS NULL 
            ORDER BY timestamp DESC 
            LIMIT 1
        """, (respuesta, numero, mensaje))
        
        # Log results of update
        if cursor.rowcount > 0:
            app.logger.info(f"✅ TRACKING: Respuesta actualizada para mensaje existente de {numero}")
        else:
            app.logger.info(f"⚠️ TRACKING: No se encontró mensaje para actualizar, insertando nuevo para {numero}")
            cursor.execute("""
                INSERT INTO conversaciones (numero, mensaje, respuesta, timestamp) 
                VALUES (%s, %s, %s, NOW())
            """, (numero, mensaje, respuesta))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        app.logger.info(f"💾 TRACKING: Operación completada para mensaje de {numero}")
        return True
        
    except Exception as e:
        app.logger.error(f"❌ TRACKING: Error al actualizar respuesta: {e}")
        # Fallback a guardar conversación normal
        guardar_conversacion(numero, mensaje, respuesta, config)
        return False

def obtener_audio_whatsapp(audio_id, config=None):
    try:
        url = f"https://graph.facebook.com/v18.0/{audio_id}"
        headers = {'Authorization': f'Bearer {config["whatsapp_token"]}'}
        app.logger.info(f"📥 Solicitando metadata de audio: {url}")
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        metadata = response.json()
        download_url = metadata.get('url')
        app.logger.info(f"🔗 URL de descarga: {download_url}")
        
        audio_response = requests.get(download_url, headers=headers, timeout=30)
        audio_response.raise_for_status()
        
        # Verificar tipo de contenido
        content_type = audio_response.headers.get('content-type')
        app.logger.info(f"🎧 Tipo de contenido: {content_type}")
        if 'audio' not in content_type:
            app.logger.error(f"🔴 Archivo no es audio: {content_type}")
            return None, None
        
        # Guardar archivo
        audio_path = os.path.join(UPLOAD_FOLDER, f"audio_{audio_id}.ogg")
        with open(audio_path, 'wb') as f:
            f.write(audio_response.content)
        app.logger.info(f"💾 Audio guardado en: {audio_path}")
        
        # Generar URL pública
        audio_url = f"https://{config['dominio']}/uploads/audio_{audio_id}.ogg"
        return audio_path, audio_url
    except Exception as e:
        app.logger.error(f"🔴 Error en obtener_audio_whatsapp: {str(e)}")
        return None, None
      
def transcribir_audio_con_openai(audio_path):
    try:
        app.logger.info(f"🎙️ Enviando audio para transcripción: {audio_path}")
        
        # Usar el cliente OpenAI correctamente (nueva versión)
        client = OpenAI(api_key=OPENAI_API_KEY)
        
        with open(audio_path, 'rb') as audio_file:
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="es"
            )
            
        app.logger.info(f"✅ Transcripción exitosa: {transcription.text}")
        return transcription.text
        
    except Exception as e:
        app.logger.error(f"🔴 Error en transcripción: {str(e)}")
        if hasattr(e, 'response'):
            try:
                error_response = e.response.json()
                app.logger.error(f"🔴 Respuesta de OpenAI: {error_response}")
            except:
                app.logger.error(f"🔴 Respuesta de OpenAI: {e.response.text}")
        return None
    
# AGREGAR esta función para gestionar conexiones a BD
def obtener_conexion_db(config):
    """Obtiene conexión a la base de datos correcta según la configuración"""
    try:
        if 'porfirianna' in config.get('dominio', ''):
            # Conectar a base de datos de La Porfirianna
            conn = mysql.connector.connect(
                host=config.get('db_host', 'localhost'),
                user=config.get('db_user', 'root'),
                password=config.get('db_password', ''),
                database=config.get('db_name', 'laporfirianna_db')
            )
        else:
            # Conectar a base de datos de Mektia (por defecto)
            conn = mysql.connector.connect(
                host=config.get('db_host', 'localhost'),
                user=config.get('db_user', 'root'),
                password=config.get('db_password', ''),
                database=config.get('db_name', 'mektia_db')
            )
        
        return conn
        
    except Exception as e:
        app.logger.error(f"❌ Error conectando a BD {config.get('db_name')}: {e}")
        raise

def obtener_configuracion_numero(numero_whatsapp):
    """Obtiene la configuración específica para un número de WhatsApp"""
    # Buscar en la configuración multi-tenant
    for numero_config, config in NUMEROS_CONFIG.items():
        if numero_whatsapp.endswith(numero_config) or numero_whatsapp == numero_config:
            return config
    
    # Fallback a configuración por defecto (Mektia)
    return NUMEROS_CONFIG['524495486142']

def obtener_imagen_perfil_alternativo(numero, config=None):
    """Método alternativo para obtener la imagen de perfil"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    try:
        # ❌ ESTO ESTÁ MAL - usa la configuración dinámica
        phone_number_id = config['phone_number_id']  # ← USA LA CONFIGURACIÓN CORRECTA
        whatsapp_token = config['whatsapp_token']    # ← USA LA CONFIGURACIÓN CORRECTA
        
        url = f"https://graph.facebook.com/v18.0/{phone_number_id}/contacts"
        
        params = {
            'fields': 'profile_picture_url',
            'user_numbers': f'[{numero}]',
            'access_token': whatsapp_token  # ← USA EL TOKEN CORRECTO
        }
        
        response = requests.get(url, params=params, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            if 'data' in data and len(data['data']) > 0:
                contacto = data['data'][0]
                if 'profile_picture_url' in contacto:
                    return contacto['profile_picture_url']
        
        return None
        
    except Exception as e:
        app.logger.error(f"🔴 Error en método alternativo: {e}")
        return None
    finally:
        conn.close()
# ——— Envío WhatsApp y guardado de conversación ———
def enviar_notificacion_pedido_cita(numero, mensaje, analisis_pedido, config=None):
    """
    Envía notificación al administrador cuando se detecta un pedido o cita
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # Determinar si es un pedido o una cita según el negocio
        es_porfirianna = 'laporfirianna' in config.get('dominio', '')
        tipo_solicitud = "pedido" if es_porfirianna else "cita"
        
        # Crear tabla notificaciones_ia si no existe
        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS notificaciones_ia (
                id INT AUTO_INCREMENT PRIMARY KEY,
                numero VARCHAR(20),
                tipo VARCHAR(20),
                resumen TEXT,
                estado VARCHAR(20) DEFAULT 'pendiente',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        ''')
        conn.commit()
        
        # Extraer información útil del análisis
        if analisis_pedido:
            datos = analisis_pedido.get('datos_obtenidos', {})
            resumen = f"Detalles: "
            if es_porfirianna:
                platillos = ", ".join(datos.get('platillos', ['No especificado']))
                resumen += f"Platillos: {platillos}"
            else:
                resumen += f"Servicio: {mensaje[:100]}"
        else:
            resumen = f"Mensaje original: {mensaje[:100]}"
        
        # Guardar en base de datos
        cursor.execute('''
            INSERT INTO notificaciones_ia (numero, tipo, resumen)
            VALUES (%s, %s, %s)
        ''', (numero, tipo_solicitud, resumen))
        conn.commit()
        notificacion_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        # Construir mensaje de notificación para el administrador
        mensaje_alerta = f"""🔔 *NUEVA SOLICITUD DE {tipo_solicitud.upper()}*

👤 *Cliente:* {numero}
⏰ *Hora:* {datetime.now().strftime('%d/%m/%Y %H:%M')}
💬 *Mensaje:* {mensaje[:150]}{'...' if len(mensaje) > 150 else ''}

📝 *Resumen:* {resumen}

🔄 *Estado:* Pendiente de atención
🆔 *ID Notificación:* {notificacion_id}
"""
        
        # Enviar notificación a los números de alerta
        enviar_mensaje(ALERT_NUMBER, mensaje_alerta, config)
        enviar_mensaje('5214493432744', mensaje_alerta, config)
        
        app.logger.info(f"✅ Notificación de {tipo_solicitud} enviada para {numero}")
        return True
        
    except Exception as e:
        app.logger.error(f"Error enviando notificación de pedido/cita: {e}")
        return False
# REEMPLAZA tu función enviar_mensaje con esta versión corregida
def enviar_mensaje(numero, texto, config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    
    # Validar texto
    if not texto or str(texto).strip() == '':
        app.logger.error("🔴 ERROR: Texto de mensaje vacío")
        return False
    
    texto_limpio = str(texto).strip()
    
    url = f"https://graph.facebook.com/v23.0/{config['phone_number_id']}/messages"
    headers = {
        'Authorization': f'Bearer {config["whatsapp_token"]}',
        'Content-Type': 'application/json'
    }
    
    # ✅ PAYLOAD CORRECTO
    payload = {
        'messaging_product': 'whatsapp',
        'to': numero,
        'type': 'text',
        'text': {
            'body': texto_limpio
        }
    }

    try:
        app.logger.info(f"📤 Enviando: {texto_limpio[:50]}...")
        r = requests.post(url, headers=headers, json=payload, timeout=10)
        
        if r.status_code == 200:
            app.logger.info("✅ Mensaje enviado")
            return True
        else:
            app.logger.error(f"🔴 Error {r.status_code}: {r.text}")
            return False
            
    except Exception as e:
        app.logger.error(f"🔴 Exception: {e}")
        return False

@app.route('/actualizar-contactos')
def actualizar_contactos():
    """Endpoint para actualizar información de todos los contactos"""
    config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor()
    
    cursor.execute("SELECT DISTINCT numero_telefono FROM contactos")
    numeros = [row[0] for row in cursor.fetchall()]
    
    for numero in numeros:
        actualizar_info_contacto(numero, config)
    
    cursor.close()
    conn.close()
    
    return f"✅ Actualizados {len(numeros)} contactos"
       
# REEMPLAZA la función guardar_conversacion con esta versión mejorada
def guardar_conversacion(numero, mensaje, respuesta, config=None, imagen_url=None, es_imagen=False):
    """Función compatible con la estructura actual de la base de datos.
    Sanitiza el texto entrante para eliminar artefactos como 'excel_unzip_img_...'
    antes de guardarlo."""
    if config is None:
        config = obtener_configuracion_por_host()

    try:
        # Sanitize inputs
        mensaje_limpio = sanitize_whatsapp_text(mensaje) if mensaje else mensaje
        respuesta_limpia = sanitize_whatsapp_text(respuesta) if respuesta else respuesta

        # Primero asegurar que el contacto existe con su información actualizada
        timestamp_local = datetime.now(tz_mx)
        actualizar_info_contacto(numero, config)

        conn = get_db_connection(config)
        cursor = conn.cursor()

        # Usar los nombres de columna existentes en tu BD
        cursor.execute("""
            INSERT INTO conversaciones (numero, mensaje, respuesta, timestamp, imagen_url, es_imagen)
            VALUES (%s, %s, %s, NOW(), %s, %s)
        """, (numero, mensaje_limpio, respuesta_limpia, imagen_url, es_imagen))

        conn.commit()
        cursor.close()
        conn.close()

        app.logger.info(f"💾 Conversación guardada para {numero}")
        return True

    except Exception as e:
        app.logger.error(f"❌ Error al guardar conversación: {e}")
        return False
    
def detectar_intencion_mejorado(mensaje, numero, historial=None, config=None):
    """
    Detección mejorada de intenciones con contexto
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    if historial is None:
        historial = obtener_historial(numero, limite=5, config=config)
    
    # Obtener estado actual de la conversación
    estado_actual = obtener_estado_conversacion(numero, config)
    
    # Construir contexto del historial
    contexto_historial = ""
    for i, msg in enumerate(historial):
        if msg['mensaje']:
            contexto_historial += f"Usuario: {msg['mensaje']}\n"
        if msg['respuesta']:
            contexto_historial += f"Asistente: {msg['respuesta']}\n"
    
    try:
        prompt_intencion = f"""
        Analiza el mensaje del usuario y determina su intención principal considerando el historial de conversación.

        HISTORIAL DE CONVERSACIÓN:
        {contexto_historial}

        MENSAJE ACTUAL: "{mensaje}"

        ESTADO ACTUAL: {estado_actual['contexto'] if estado_actual else 'Sin estado previo'}

        OPCIONES DE INTENCIÓN:
        - NUEVA_CITA: El usuario quiere crear una cita completamente nueva
        - MODIFICAR_CITA: El usuario quiere modificar una cita existente
        - CONSULTAR_SERVICIOS: El usuario pregunta sobre servicios disponibles
        - CANCELAR_CITA: El usuario quiere cancelar una cita
        - OTRO: Otra intención no relacionada con citas

        Responde en formato JSON:
        {{
            "intencion": "NUEVA_CITA|MODIFICAR_CITA|CONSULTAR_SERVICIOS|CANCELAR_CITA|OTRO",
            "confianza": 0.0-1.0,
            "detalles": {{...}}  // Información adicional relevante
        }}

        Ejemplo si dice "quiero hacer otro pedido" después de tener una cita:
        {{
            "intencion": "NUEVA_CITA",
            "confianza": 0.9,
            "detalles": {{"tipo": "nueva_solicitud"}}
        }}
        """
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt_intencion}],
            "temperature": 0.3,
            "max_tokens": 500
        }
        
        response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        data = response.json()
        respuesta_ia = data['choices'][0]['message']['content'].strip()
        
        # Extraer JSON de la respuesta
        json_match = re.search(r'\{.*\}', respuesta_ia, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            return {"intencion": "OTRO", "confianza": 0.0, "detalles": {}}
            
    except Exception as e:
        app.logger.error(f"Error detectando intención: {e}")
        return {"intencion": "OTRO", "confianza": 0.0, "detalles": {}}

def manejar_solicitud_cita_mejorado(numero, mensaje, info_cita, config=None):
    """
    Manejo mejorado de solicitudes de cita con prevención de ciclos
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    # 🔥 VERIFICAR SI ESTAMOS EN MEDIO DE UNA SOLICITUD
    estado_actual = obtener_estado_conversacion(numero, config)
    
    if estado_actual and estado_actual.get('contexto') == 'EN_CITA':
        # Ya estamos en proceso de cita, usar lógica de continuación
        return continuar_proceso_cita(numero, mensaje, estado_actual, config)
    
    # 🔥 DETECCIÓN MÁS ESTRICTA DE NUEVAS SOLICITUDES
    es_nueva_solicitud = (
        detectar_solicitud_cita_keywords(mensaje) and 
        not es_respuesta_a_pregunta(mensaje) and
        not estado_actual  # No hay estado previo
    )
    
    if not es_nueva_solicitud:
        # No es una nueva solicitud, dejar que la IA normal responda
        return None
    
    app.logger.info(f"📅 Nueva solicitud de cita detectada de {numero}")
    
    # Iniciar nuevo proceso de cita
    actualizar_estado_conversacion(numero, "EN_CITA", "solicitar_servicio", 
                                 {"paso": 1, "intentos": 0}, config)
    
    # Determinar tipo de negocio
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    
    if es_porfirianna:
        return "¡Hola! 👋 Para tomar tu pedido, necesito que me digas:\n\n1. ¿Qué platillos deseas ordenar?\n2. ¿Para cuándo lo quieres?\n3. ¿Cuál es tu nombre?\n\nPuedes responder todo en un solo mensaje. 😊"
    else:
        return "¡Hola! 👋 Para agendar tu cita, necesito que me digas:\n\n1. ¿Qué servicio necesitas?\n2. ¿Qué fecha te viene bien?\n3. ¿Cuál es tu nombre?\n\nPuedes responder todo en un solo mensaje. 😊"
    
def obtener_citas_pendientes(numero, config=None):
    """
    Obtiene las citas pendientes de un cliente
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('''
        SELECT * FROM citas 
        WHERE numero_cliente = %s AND estado = 'pendiente'
        ORDER BY fecha_creacion DESC
    ''', (numero,))
    
    citas = cursor.fetchall()
    cursor.close()
    conn.close()
    
    return citas

def modificar_cita(cita_id, nueva_info, config=None):
    """
    Modifica una cita existente
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE citas SET
                servicio_solicitado = %s,
                fecha_propuesta = %s,
                hora_propuesta = %s,
                nombre_cliente = %s,
                fecha_creacion = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (
            nueva_info.get('servicio_solicitado'),
            nueva_info.get('fecha_sugerida'),
            nueva_info.get('hora_sugerida'),
            nueva_info.get('nombre_cliente'),
            cita_id
        ))
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        app.logger.error(f"Error modificando cita {cita_id}: {e}")
        return False

# ——— Detección y alerta ———
# REEMPLAZA la función detectar_intervencion_humana_ia con esta versión mejorada
def detectar_intervencion_humana_ia(mensaje_usuario, numero, config=None):
    """
    Detección mejorada de solicitud de intervención humana usando palabras clave
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    # ⚠️ EVITAR DETECTAR ALERTAS DEL MISMO SISTEMA
    alertas_sistema = [
        "🚨 ALERTA:", "📋 INFORMACIÓN COMPLETA", "👤 Cliente:", 
        "📞 Número:", "💬 Mensaje clave:", "🎯 INFORMACIÓN DEL PROYECTO"
    ]
    
    for alerta in alertas_sistema:
        if alerta in mensaje_usuario:
            return False
    
    # ⚠️ EVITAR TU NÚMERO PERSONAL Y EL NÚMERO DE ALERTA
    if numero == ALERT_NUMBER or numero in ['5214491182201', '524491182201', '5214493432744']:
        return False
    
    mensaje_lower = mensaje_usuario.lower()
    
    # Palabras clave que indican solicitud de humano
    palabras_clave_humano = [
        'humano', 'persona', 'asesor', 'agente', 'ejecutivo', 'representante',
        'operador', 'atendedor', 'atender', 'hablar con alguien', 
        'no eres humano', 'no me entiendes', 'quiero hablar con una persona',
        'atención humana', 'servicio humano', 'ayuda humana', 'asistencia humana',
        'no me ayudas', 'no resuelves', 'no entiendes', 'mejor hablar con',
        'te cambio', 'otra persona', 'supervisor', 'gerente', 'dueño',
        'encargado', 'responsable', 'que me llame', 'llámame', 'hablar por teléfono',
        'número de teléfono', 'contacto directo', 'comunicarme con'
    ]
    
    # Palabras de frustración
    palabras_frustracion = [
        'molesto', 'enojado', 'frustrado', 'cansado', 'harto', 'fastidiado',
        'irritado', 'disgustado', 'no me gusta', 'pésimo servicio', 'mal servicio',
        'pésima atención', 'mala atención', 'terrible', 'horrible', 'pésimo',
        'decepcionado', 'insatisfecho', 'no resuelve', 'no sirve', 'no ayuda',
        'estúpido', 'tonto', 'inútil', 'no funciona', 'no trabaja', 'no sabe'
    ]
    
    # Detectar palabras clave directas
    for palabra in palabras_clave_humano:
        if palabra in mensaje_lower:
            app.logger.info(f"🚨 Intervención humana detectada (palabra clave): {palabra}")
            return True
    
    # Detectar frustración (múltiples palabras de frustración)
    palabras_encontradas = [p for p in palabras_frustracion if p in mensaje_lower]
    if len(palabras_encontradas) >= 2:
        app.logger.info(f"🚨 Intervención humana detectada (frustración): {palabras_encontradas}")
        return True
    
    # Detectar solicitudes explícitas de contacto
    patrones_contacto = [
        r'quiero\s+hablar\s+con',
        r'dame\s+tu\s+número',
        r'pásame\s+con',
        r'necesito\s+hablar',
        r'contacto\s+directo',
        r'llámenme',
        r'mar[qc]enme',
        r'hablemos\s+por\s+teléfono'
    ]
    
    for patron in patrones_contacto:
        if re.search(patron, mensaje_lower):
            app.logger.info(f"🚨 Intervención humana detectada (patrón contacto): {patron}")
            return True
    
    return False
         
def resumen_rafa(numero, config=None):
    """Resumen más completo y eficiente"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT mensaje, respuesta, timestamp FROM conversaciones WHERE numero=%s ORDER BY timestamp DESC LIMIT 8;",
            (numero,)
        )
        historial = cursor.fetchall()
        cursor.close()
        conn.close()
        
        resumen = "🚨 *ALERTA: Intervención Humana Requerida*\n\n"
        resumen += f"📞 *Cliente:* {numero}\n"
        resumen += f"🕒 *Hora:* {datetime.now().strftime('%d/%m/%Y %H:%M')}\n\n"
        resumen += "📋 *Últimas interacciones:*\n"
        
        for i, msg in enumerate(historial):
            hora = msg['timestamp'].strftime('%H:%M') if msg.get('timestamp') else 'N/A'
            resumen += f"\n{i+1}. [{hora}] 👤: {msg['mensaje'][:80] if msg['mensaje'] else '[Sin mensaje]'}"
            if msg['respuesta']:
                resumen += f"\n   🤖: {msg['respuesta'][:80]}"
        
        return resumen
        
    except Exception as e:
        app.logger.error(f"Error generando resumen: {e}")
        return f"Error generando resumen para {numero}"

def es_mensaje_repetido(numero, mensaje_actual, config=None):
    """Verifica si el mensaje actual es muy similar al anterior"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute('''
            SELECT mensaje FROM conversaciones 
            WHERE numero = %s 
            ORDER BY timestamp DESC 
            LIMIT 1
        ''', (numero,))
        
        ultimo_mensaje = cursor.fetchone()
        cursor.close()
        conn.close()
        
        # ✅ VERIFICAR SI HAY MENSAJE Y NO ES NONE
        if ultimo_mensaje and ultimo_mensaje.get('mensaje'):
            # Comparar similitud de mensajes
            similitud = calcular_similitud(mensaje_actual, ultimo_mensaje['mensaje'])
            return similitud > 0.8  # Si son más del 80% similares
            
    except Exception as e:
        app.logger.error(f"Error verificando mensaje repetido: {e}")
    
    return False

def calcular_similitud(texto1, texto2):
    """Calcula similitud entre dos textos (simple)"""
    from difflib import SequenceMatcher
    return SequenceMatcher(None, texto1.lower(), texto2.lower()).ratio()

def es_respuesta_a_pregunta(mensaje):
    """
    Detecta si el mensaje es una respuesta a una pregunta previa del asistente
    en lugar de una nueva solicitud de cita/pedido.
    """
    mensaje_lower = mensaje.lower()
    
    # Palabras que indican que es una respuesta, no una nueva solicitud
    palabras_respuesta = [
        'sí', 'si', 'no', 'claro', 'ok', 'vale', 'correcto', 'afirmativo',
        'está bien', 'de acuerdo', 'perfecto', 'exacto', 'así es', 'sip', 'nop',
        'mañana', 'hoy', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes',
        'sábado', 'domingo', 'la semana', 'el próximo', 'a las', 'por la',
        'juan', 'maría', 'carlos', 'ana', 'luis'  # Nombres comunes
    ]
    
    # Si el mensaje contiene alguna de estas palabras, probablemente es una respuesta
    for palabra in palabras_respuesta:
        if palabra in mensaje_lower:
            return True
    
    # Si es muy corto (1-3 palabras), probablemente es una respuesta
    if len(mensaje_lower.split()) <= 3:
        return True
    
    # Si comienza con artículo o preposición, probablemente es respuesta
    if mensaje_lower.startswith(('el ', 'la ', 'los ', 'las ', 'un ', 'una ', 'a las ', 'para ')):
        return True
    
    return False
def enviar_alerta_humana(numero_cliente, mensaje_clave, resumen, config=None):
    if config is None:
        config = obtener_configuracion_por_host()

    contexto_consulta = obtener_contexto_consulta(numero_cliente, config)
    if config is None:
        app.logger.error("🔴 Configuración no disponible para enviar alerta")
        return
    
    """Envía alerta de intervención humana usando mensaje normal (sin template)"""
    mensaje = f"🚨 *ALERTA: Intervención Humana Requerida*\n\n"
    """Envía alerta de intervención humana usando mensaje normal (sin template)"""
    mensaje = f"🚨 *ALERTA: Intervención Humana Requerida*\n\n"
    mensaje += f"👤 *Cliente:* {numero_cliente}\n"
    mensaje += f"📞 *Número:* {numero_cliente}\n"
    mensaje += f"💬 *Mensaje clave:* {mensaje_clave[:100]}{'...' if len(mensaje_clave) > 100 else ''}\n\n"
    mensaje += f"📋 *Resumen:*\n{resumen[:800]}{'...' if len(resumen) > 800 else ''}\n\n"
    mensaje += f"⏰ *Hora:* {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
    mensaje += f"🎯 *INFORMACIÓN DEL PROYECTO/CONSULTA:*\n"
    mensaje += f"{contexto_consulta}\n\n"
    mensaje += f"_________________________________________\n"
    mensaje += f"📊 Atiende desde el CRM o responde directamente por WhatsApp"
    
    # Enviar mensaje normal (sin template) a tu número personal
    enviar_mensaje(ALERT_NUMBER, mensaje, config)
    enviar_mensaje('5214493432744', mensaje, config)#me quiero enviar un mensaje a mi mismo
    app.logger.info(f"📤 Alerta humana enviada para {numero_cliente} desde {config['dominio']}")

def enviar_informacion_completa(numero_cliente, config=None):
    """Envía toda la información del cliente a ambos números"""
    if config is None:
        config = obtener_configuracion_por_host()
    try:
        # Obtener información del contacto
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM contactos WHERE numero_telefono = %s",
            (numero_cliente,)
        )
        contacto = cursor.fetchone()
        
        # Obtener historial reciente
        cursor.execute(
            "SELECT * FROM conversaciones WHERE numero = %s ORDER BY timestamp DESC LIMIT 10",
            (numero_cliente,)
        )
        historial = cursor.fetchall()
        
        cursor.close()
        conn.close()
        
        # Construir mensaje completo
        mensaje_completo = "📋 *INFORMACIÓN COMPLETA DEL CLIENTE*\n\n"
        mensaje_completo += f"📞 *Número:* {numero_cliente}\n"
        
        if contacto:
            mensaje_completo += f"👤 *Nombre:* {contacto.get('nombre', 'No disponible')}\n"
            mensaje_completo += f"🏷️ *Alias:* {contacto.get('alias', 'No asignado')}\n"
            mensaje_completo += f"🌐 *Plataforma:* {contacto.get('plataforma', 'WhatsApp')}\n"
        
        mensaje_completo += f"\n📊 *Total mensajes:* {len(historial)}\n"
        mensaje_completo += f"🕒 *Última interacción:* {historial[0]['timestamp'].strftime('%d/%m/%Y %H:%M') if historial else 'N/A'}\n\n"
        
        mensaje_completo += "💬 *Últimos mensajes:*\n"
        for i, msg in enumerate(historial[:3]):  # Solo últimos 3 mensajes
            hora_msg = msg['timestamp'].strftime('%H:%M') if msg.get('timestamp') else 'N/A'
            mensaje_completo += f"\n{i+1}. [{hora_msg}] 👤: {msg['mensaje'][:60]}"
            if msg['respuesta']:
                mensaje_completo += f"\n   🤖: {msg['respuesta'][:60]}"
        
        # Enviar mensaje completo a ambos números
        enviar_mensaje(ALERT_NUMBER, mensaje_completo, config)  # Número original
        enviar_mensaje("5214493432744", mensaje_completo, config)  # Nuevo número
        
        app.logger.info(f"📤 Información completa enviada para {numero_cliente} a ambos números")
        
    except Exception as e:
        app.logger.error(f"🔴 Error enviando información completa: {e}")        

# ——— Webhook ———
@app.route('/webhook', methods=['GET'])
def webhook_verification():
    # Obtener el host desde los headers para determinar qué verify token usar
    host = request.headers.get('Host', '')
    
    if 'laporfirianna' in host:
        verify_token = os.getenv("PORFIRIANNA_VERIFY_TOKEN")
    elif 'ofitodo' in host:  
        verify_token = os.getenv("FITO_VERIFY_TOKEN")
    else:
        verify_token = os.getenv("MEKTIA_VERIFY_TOKEN")
    
    if request.args.get('hub.verify_token') == verify_token:
        return request.args.get('hub.challenge')
    return 'Token inválido', 403

# Modifica la función obtener_configuracion_por_phone_number_id
def obtener_configuracion_por_phone_number_id(phone_number_id):
    """Detecta automáticamente la configuración basada en el phone_number_id recibido"""
    for numero, config in NUMEROS_CONFIG.items():
        if str(config['phone_number_id']) == str(phone_number_id):
            return config
    # Fallback to default
    return NUMEROS_CONFIG['524495486142']

@app.route('/reparar-kanban')
def reparar_kanban():
    """Repara todos los contactos que no están en chat_meta"""
    config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    # Encontrar números en conversaciones que no están en chat_meta
    cursor.execute("""
        SELECT DISTINCT numero 
        FROM conversaciones 
        WHERE numero NOT IN (SELECT numero FROM chat_meta)
    """)
    
    numeros_sin_meta = [row['numero'] for row in cursor.fetchall()]
    
    for numero in numeros_sin_meta:
        app.logger.info(f"🔧 Reparando contacto en Kanban: {numero}")
        inicializar_chat_meta(numero, config)
    
    cursor.close()
    conn.close()
    
    return f"✅ Reparados {len(numeros_sin_meta)} contactos en Kanban"

def actualizar_info_contacto_desde_webhook(numero, nombre_contacto, config=None):
    """
    Actualiza la información del contacto usando los datos del webhook de WhatsApp
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor()
        
        # Si tenemos nombre del contacto, actualizamos la base de datos
        if nombre_contacto:
            cursor.execute("""
                INSERT INTO contactos 
                    (numero_telefono, nombre, plataforma, fecha_actualizacion) 
                VALUES (%s, %s, 'WhatsApp', NOW())
                ON DUPLICATE KEY UPDATE 
                    nombre = VALUES(nombre),
                    fecha_actualizacion = NOW()
            """, (numero, nombre_contacto))
            
            app.logger.info(f"✅ Contacto actualizado desde webhook: {numero} -> {nombre_contacto}")
        else:
            # Si no hay nombre, al menos asegurarnos de que el contacto existe
            cursor.execute("""
                INSERT IGNORE INTO contactos 
                    (numero_telefono, plataforma, fecha_actualizacion) 
                VALUES (%s, 'WhatsApp', NOW())
            """, (numero,))
            app.logger.info(f"✅ Contacto registrado (sin nombre): {numero}")
        
        conn.commit()
        cursor.close()
        conn.close()
        
    except Exception as e:
        app.logger.error(f"🔴 Error actualizando contacto desde webhook: {e}")

@app.route('/notificaciones')
def ver_notificaciones():
    """Endpoint para ver notificaciones de pedidos y citas con información ampliada"""
    config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('''
        SELECT n.*,
               COALESCE(c.alias, c.nombre, n.numero) as nombre_cliente,
               c.imagen_url
        FROM notificaciones_ia n
        LEFT JOIN contactos c ON n.numero = c.numero_telefono
        ORDER BY n.timestamp DESC
        LIMIT 50
    ''')
    
    notificaciones = cursor.fetchall()
    
    # Procesar el JSON de evaluacion_ia para la vista
    for notif in notificaciones:
        try:
            if notif.get('evaluacion_ia'):
                notif['evaluacion_data'] = json.loads(notif['evaluacion_ia'])
            else:
                notif['evaluacion_data'] = {}
        except:
            notif['evaluacion_data'] = {}
            
        # Formatear fecha/hora para mejor legibilidad
        if notif.get('timestamp'):
            notif['timestamp_formateado'] = notif['timestamp'].strftime('%d/%m/%Y %H:%M')
    
    cursor.close()
    conn.close()
    
    return render_template('notificaciones.html', notificaciones=notificaciones)

@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        # ✅ VERIFICACIÓN CRÍTICA - asegurar que tenemos JSON
        if not request.is_json:
            app.logger.error("🔴 Error: No se recibió JSON en el webhook")
            return 'Invalid content type', 400
            
        payload = request.get_json()
        if not payload:
            app.logger.error("🔴 Error: JSON vacío o inválido")
            return 'Invalid JSON', 400
            
        app.logger.info(f"📥 Payload recibido: {json.dumps(payload, indent=2)[:500]}...")
        
        # ✅ VERIFICAR ESTRUCTURA BÁSICA DEL PAYLOAD
        if 'entry' not in payload or not payload['entry']:
            app.logger.error("🔴 Error: Payload sin 'entry'")
            return 'Invalid payload structure', 400
            
        entry = payload['entry'][0]
        if 'changes' not in entry or not entry['changes']:
            app.logger.error("🔴 Error: Entry sin 'changes'")
            return 'Invalid entry structure', 400
            
        change = entry['changes'][0]['value']
        mensajes = change.get('messages', [])
        data = request.get_json()
        try:
            # Extraer información del contacto del payload
            if 'contacts' in data['entry'][0]['changes'][0]['value']:
                contact_info = data['entry'][0]['changes'][0]['value']['contacts'][0]
                wa_id = contact_info['wa_id']
                name = contact_info['profile']['name']
            
                # Guardar en la base de datos
                config = obtener_configuracion_por_host()
                conn = get_db_connection(config)
                cursor = conn.cursor()
            
                cursor.execute("""
                    INSERT INTO contactos (numero_telefono, nombre, plataforma) 
                    VALUES (%s, %s, 'WhatsApp')
                    ON DUPLICATE KEY UPDATE 
                        nombre = COALESCE(%s, nombre),
                        fecha_actualizacion = CURRENT_TIMESTAMP
                """, (wa_id, name, name))
            
                conn.commit()
                cursor.close()
                conn.close()
            
                app.logger.info(f"✅ Contacto guardado desde webhook: {wa_id} - {name}")
                actualizar_kanban()
        
            # Continuar con el procesamiento normal del mensaje
        
        except Exception as e:
            app.logger.error(f"Error procesando webhook: {str(e)}")
            return jsonify({"status": "error"}), 500
        if not mensajes:
            app.logger.info("⚠️ No hay mensajes en el payload")
            return 'OK', 200    

        msg = mensajes[0]
        numero = msg['from']
        # Manejo robusto de texto/flags
        actualizar_kanban_inmediato(numero, config)
        texto = ''
        es_imagen = False
        es_audio = False
        es_video = False
        es_archivo = False
        es_documento = False
        es_mi_numero = False
        # 🔥 DETECTAR CONFIGURACIÓN CORRECTA POR PHONE_NUMBER_ID
        phone_number_id = change.get('metadata', {}).get('phone_number_id')
        app.logger.info(f"📱 Phone Number ID recibido: {phone_number_id}")
        
        # 🔥 OBTENER CONFIGURACIÓN CORRECTA
        config = None
        for numero_config, config_data in NUMEROS_CONFIG.items():
            if str(config_data['phone_number_id']) == str(phone_number_id):
                config = config_data
                app.logger.info(f"✅ Configuración encontrada por phone_number_id: {config['dominio']}")
                break
                
        if config is None:
            app.logger.warning(f"⚠️ No se encontró configuración para phone_number_id: {phone_number_id}")
            config = obtener_configuracion_por_host()
            app.logger.info(f"🔄 Usando configuración de fallback: {config.get('dominio', 'desconocido')}")
        
        # 🔥 Inicializar/actualizar contacto y kanban
        nombre_desde_webhook = extraer_nombre_desde_webhook(payload)
        actualizar_info_contacto(numero, config)  # Para obtener nombre e imagen
        inicializar_chat_meta(numero, config)
        actualizar_kanban()
        if nombre_desde_webhook:
            actualizar_info_contacto_con_nombre(numero, nombre_desde_webhook, config)
        else:
            actualizar_info_contacto(numero, config)

        # 🛑 EVITAR PROCESAR EL MISMO MENSAJE MÚLTIPLES VECES
        message_id = msg.get('id')
        if not message_id:
            app.logger.error("🔴 Mensaje sin ID, no se puede prevenir duplicados")
            return 'OK', 200
            
        # Crear hash único
        message_hash = hashlib.md5(f"{numero}_{message_id}".encode()).hexdigest()

        # Verificar duplicados (excepto audio/imagen)
        if not es_audio and not es_imagen and message_hash in processed_messages:
            app.logger.info(f"⚠️ Mensaje duplicado ignorado: {message_hash}")
            return 'OK', 200
            
        # Agregar a mensajes procesados
        processed_messages[message_hash] = time.time()

        # Limpiar mensajes antiguos (más de 1 hora)
        current_time = time.time()
        for msg_hash, ts in list(processed_messages.items()):
            if current_time - ts > 3600:
                del processed_messages[msg_hash]
        
        image_id = None
        imagen_base64 = None
        public_url = None
        transcripcion = None

        # Parsear el mensaje entrante
        actualizar_info_contacto(numero, config)
        if 'text' in msg and 'body' in msg['text']:
            texto = msg['text']['body'].strip()
        elif 'image' in msg:
            es_imagen = True
            image_id = msg['image']['id']
            imagen_base64, public_url = obtener_imagen_whatsapp(image_id, config)
            texto = msg['image'].get('caption', '').strip() or "El usuario envió una imagen"

            # Guardar mensaje entrante (sin respuesta aún)
            guardar_conversacion(numero, texto, None, config, public_url, True)

            # 🔁 ACTUALIZAR KANBAN INMEDIATAMENTE EN RECEPCIÓN
            try:
                meta = obtener_chat_meta(numero, config)
                if not meta:
                    inicializar_chat_meta(numero, config)
                actualizar_columna_chat(numero, 2, config)  # En Conversación
            except Exception as e:
                app.logger.warning(f"⚠️ No se pudo actualizar Kanban en recepción (imagen): {e}")

            # ===== NUEVO: Analizar imagen y responder automáticamente =====
            try:
                respuesta_imagen = analizar_imagen_y_responder(numero, imagen_base64, texto, public_url, config)
                if respuesta_imagen:
                    # Enviar respuesta textual al usuario
                    enviar_mensaje(numero, respuesta_imagen, config)
                    # Guardar la respuesta asociada a la imagen
                    guardar_conversacion(numero, texto, respuesta_imagen, config, public_url, True)
                    app.logger.info(f"✅ Respuesta automática (imagen) enviada a {numero}")
                    return 'OK', 200
                else:
                    app.logger.info("ℹ️ No se generó respuesta automática tras analizar la imagen; el flujo continúa normalmente")
            except Exception as e:
                app.logger.error(f"🔴 Error al analizar/contestar imagen automáticamente: {e}")

        elif 'document' in msg:
            es_archivo = True
            texto = msg['document'].get('caption', f"Archivo: {msg['document'].get('filename', 'sin nombre')}")
            app.logger.info(f"📎 Archivo detectado: {texto}")
            # 🔁 ACTUALIZAR KANBAN INMEDIATAMENTE EN RECEPCIÓN
            try:
                meta = obtener_chat_meta(numero, config)
                if not meta:
                    inicializar_chat_meta(numero, config)
                actualizar_columna_chat(numero, 2, config)  # En Conversación
            except Exception as e:
                app.logger.warning(f"⚠️ No se pudo actualizar Kanban en recepción (documento): {e}")
            # Procesar y salir
            procesar_mensaje_normal(msg, numero, texto, es_imagen, es_audio, config, 
                                   imagen_base64, transcripcion, es_mi_numero, es_archivo)     
            return 'OK', 200
        elif 'audio' in msg:
            es_audio = True
            audio_id = msg['audio']['id']
            audio_path, audio_url = obtener_audio_whatsapp(audio_id, config)
            if audio_path:
                transcripcion = transcribir_audio_con_openai(audio_path)
                texto = transcripcion if transcripcion else "No se pudo transcribir el audio"
            else:
                texto = "Error al procesar el audio"
        else:
            texto = f"[{msg.get('type', 'unknown')}] Mensaje no textual"
        guardar_mensaje_inmediato(numero, texto, config)
        app.logger.info(f"📝 Mensaje de {numero}: '{texto}' (imagen: {es_imagen}, audio: {es_audio})")

        # 🔁 ACTUALIZAR KANBAN INMEDIATAMENTE EN RECEPCIÓN (cualquier tipo)
        try:
            meta = obtener_chat_meta(numero, config)
            if not meta:
                inicializar_chat_meta(numero, config)
            # Si es el primer mensaje de este chat -> Nuevos (1), si no -> En Conversación (2)
            historial = obtener_historial(numero, limite=1, config=config)
            nueva_columna = 1 if not historial else 2
            actualizar_columna_chat(numero, nueva_columna, config)
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo actualizar Kanban en recepción (general): {e}")
        
        # ⛔ BLOQUEAR MENSAJES DEL SISTEMA DE ALERTAS
        if numero == ALERT_NUMBER and any(tag in texto for tag in ['🚨 ALERTA:', '📋 INFORMACIÓN COMPLETA']):
            app.logger.info(f"⚠️ Mensaje del sistema de alertas, ignorando: {numero}")
            return 'OK', 200
        
        
                # ========== DETECCIÓN DE INTENCIONES PRINCIPALES ==========
        # Primero, comprobar si es una cita/pedido usando el análisis mejorado
        info_cita = extraer_info_cita_mejorado(texto, numero, None, config)
            
        if info_cita and info_cita.get('servicio_solicitado'):
            app.logger.info(f"✅ Información de cita/pedido detectada en webhook: {json.dumps(info_cita)}")
                
            # Comprobar si hay suficientes datos
            datos_completos, faltantes = validar_datos_cita_completos(info_cita, config)
            if datos_completos:
                # Guardar la cita y enviar notificaciones
                cita_id = guardar_cita(info_cita, config)
                if cita_id:
                    app.logger.info(f"✅ Cita/pedido guardado con ID: {cita_id}")
                    # Enviar alertas y confirmación
                    enviar_alerta_cita_administrador(info_cita, cita_id, config)
                    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
                    respuesta = f"✅ He registrado tu {es_porfirianna and 'pedido' or 'cita'}. Te enviaré una confirmación con los detalles y nos pondremos en contacto pronto."
                    enviar_mensaje(numero, respuesta, config)
                    guardar_conversacion(numero, texto, respuesta, config)
                    enviar_confirmacion_cita(numero, info_cita, cita_id, config)
                    return 'OK', 200
                
        # Fallback a la detección básica para compatibilidad
        analisis_pedido = detectar_pedido_inteligente(texto, numero, config=config)
        if analisis_pedido and analisis_pedido.get('es_pedido'):
            app.logger.info(f"📦 Pedido inteligente detectado para {numero}")
            # Enviar notificación al administrador
            enviar_notificacion_pedido_cita(numero, texto, analisis_pedido, config)
            # Manejar el pedido automáticamente
            respuesta = manejar_pedido_automatico(numero, texto, analisis_pedido, config)
            # Enviar respuesta y guardar conversación
            enviar_mensaje(numero, respuesta, config)
            guardar_conversacion(numero, texto, respuesta, config)
            return 'OK', 200
            # Continuar con el procesamiento normal
        # 2. DETECTAR INTERVENCIÓN HUMANA
        if detectar_intervencion_humana_ia(texto, numero, config):
            app.logger.info(f"🚨 Solicitud de intervención humana detectada de {numero}")
            historial = obtener_historial(numero, limite=5, config=config)
            info_intervencion = extraer_info_intervencion(texto, numero, historial, config)
            if info_intervencion:
                app.logger.info(f"📋 Información de intervención: {json.dumps(info_intervencion, indent=2)}")
                enviar_alerta_intervencion_humana(info_intervencion, config)
                respuesta = "🚨 He solicitado la intervención de un agente humano. Un representante se comunicará contigo a la brevedad."
            else:
                respuesta = "He detectado que necesitas ayuda humana. Un agente se contactará contigo pronto."
            enviar_mensaje(numero, respuesta, config)
            guardar_conversacion(numero, texto, respuesta, config)
            actualizar_kanban(numero, columna_id=1, config=config)
            return 'OK', 200
        
        # 3. PROCESAMIENTO NORMAL DEL MENSAJE
        procesar_mensaje_normal(msg, numero, texto, es_imagen, es_audio, config, imagen_base64, transcripcion, es_mi_numero)
        # ⛔ Se elimina llamada inválida con columna_id indefinido
        # actualizar_kanban(numero, columna_id, config)  # ← eliminado
        return 'OK', 200 
        
    except Exception as e:
        app.logger.error(f"🔴 ERROR CRÍTICO en webhook: {str(e)}")
        app.logger.error(traceback.format_exc())
        return 'Error interno del servidor', 500


def guardar_mensaje_inmediato(numero, texto, config=None, imagen_url=None, es_imagen=False):
    """Guarda el mensaje del usuario inmediatamente, sin respuesta.
    Aplica sanitización para que la UI muestre el mismo texto legible que llega por WhatsApp."""
    if config is None:
        config = obtener_configuracion_por_host()

    try:
        # Sanitize incoming text
        texto_limpio = sanitize_whatsapp_text(texto) if texto else texto

        # Asegurar que el contacto existe
        actualizar_info_contacto(numero, config)

        conn = get_db_connection(config)
        cursor = conn.cursor()

        # Add detailed logging before saving the message
        app.logger.info(f"📥 TRACKING: Guardando mensaje de {numero}, timestamp: {datetime.now(tz_mx).isoformat()}")

        cursor.execute("""
            INSERT INTO conversaciones (numero, mensaje, respuesta, timestamp, imagen_url, es_imagen)
            VALUES (%s, %s, NULL, NOW(), %s, %s)
        """, (numero, texto_limpio, imagen_url, es_imagen))

        # Get the ID of the inserted message for tracking
        cursor.execute("SELECT LAST_INSERT_ID()")
        msg_id = cursor.fetchone()[0]

        conn.commit()
        cursor.close()
        conn.close()

        app.logger.info(f"💾 TRACKING: Mensaje ID {msg_id} guardado para {numero}")
        return True

    except Exception as e:
        app.logger.error(f"❌ Error al guardar mensaje inmediato: {e}")
        return False
    
def extraer_nombre_desde_webhook(payload):
    """
    Extrae el nombre del contacto directamente desde el webhook de WhatsApp
    """
    try:
        # Verificar si existe la estructura de contacts en el payload
        if ('entry' in payload and 
            payload['entry'] and 
            'changes' in payload['entry'][0] and 
            payload['entry'][0]['changes'] and 
            'contacts' in payload['entry'][0]['changes'][0]['value']):
            
            contacts = payload['entry'][0]['changes'][0]['value']['contacts']
            if contacts and len(contacts) > 0:
                profile = contacts[0].get('profile', {})
                nombre = profile.get('name')
                
                if nombre:
                    app.logger.info(f"✅ Nombre extraído desde webhook: {nombre}")
                    return nombre
        
        app.logger.info("ℹ️ No se encontró nombre en el webhook")
        return None
        
    except Exception as e:
        app.logger.error(f"🔴 Error extrayendo nombre desde webhook: {e}")
        return None

# REEMPLAZA la función detectar_solicitud_cita_keywords con esta versión mejorada
def detectar_solicitud_cita_keywords(mensaje, config=None):
    """
    Detección mejorada por palabras clave de solicitud de cita/pedido
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    mensaje_lower = mensaje.lower().strip()
    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
    
    # Evitar detectar respuestas a preguntas como nuevas solicitudes
    if es_respuesta_a_pregunta(mensaje):
        return False
    
    if es_porfirianna:
        # Palabras clave específicas para pedidos de comida
        palabras_clave = [
            'pedir', 'ordenar', 'orden', 'pedido', 'quiero', 'deseo', 'necesito',
            'comida', 'cenar', 'almorzar', 'desayunar', 'gordita', 'taco', 'quesadilla'
        ]
    else:
        # Palabras clave para servicios digitales
        palabras_clave = [
            'cita', 'agendar', 'consultoría', 'reunión', 'asesoría', 'cotización',
            'presupuesto', 'proyecto', 'servicio', 'contratar', 'quiero contratar', 'solicitar', 'comprar'

        ]
    
    # Verificar si contiene palabras clave principales
    contiene_palabras_clave = any(
        palabra in mensaje_lower for palabra in palabras_clave
    )
    
    # Detectar patrones específicos de solicitud
    patrones_solicitud = [
        'quiero un', 'deseo un', 'necesito un', 'me gustaría un',
        'quisiera un', 'puedo tener un', 'agendar una', 'solicitar un'
    ]
    
    contiene_patron = any(
        patron in mensaje_lower for patron in patrones_solicitud
    )
    
    # Es una solicitud si contiene palabras clave O patrones específicos
    es_solicitud = contiene_palabras_clave or contiene_patron
    
    if es_solicitud:
        tipo = "pedido" if es_porfirianna else "cita"
        app.logger.info(f"✅ Solicitud de {tipo} detectada por keywords: '{mensaje_lower}'")
    
    return es_solicitud
# ——— UI ———
@app.route('/')
def inicio():
    config = obtener_configuracion_por_host()
    return redirect(url_for('home', config=config))

@app.route('/test-calendar')
def test_calendar():
    """Prueba el agendamiento de citas en Google Calendar"""
    config = obtener_configuracion_por_host()
    
    try:
        # Crear información de cita de prueba
        info_cita = {
            'servicio_solicitado': 'Servicio de Prueba',
            'fecha_sugerida': (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d'),
            'hora_sugerida': '10:00',
            'nombre_cliente': 'Cliente de Prueba',
            'telefono': '5214495486142',
            'detalles_servicio': {
                'descripcion': 'Esta es una cita de prueba para verificar la integración con Google Calendar',
                'categoria': 'Prueba',
                'precio': '100.00',
                'precio_menudeo': '100.00'
            }
        }
        
        # Intentar autenticar con Google Calendar
        service = autenticar_google_calendar(config)
        
        if not service:
            return """
            <h1>❌ Error de Autenticación</h1>
            <p>No se pudo autenticar con Google Calendar. Por favor verifica:</p>
            <ul>
                <li>Que hayas autorizado la aplicación con Google Calendar</li>
                <li>Que el archivo token.json exista y sea válido</li>
                <li>Que el archivo client_secret.json esté correctamente configurado</li>
            </ul>
            <p><a href="/autorizar_manual" class="btn btn-primary">Intentar Autorizar de Nuevo</a></p>
            """
        
        # Intentar crear evento
        evento_id = crear_evento_calendar(service, info_cita, config)
        
        if evento_id:
            # Mostrar información del correo configurado
            conn = get_db_connection(config)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT calendar_email FROM configuracion WHERE id = 1")
            result = cursor.fetchone()
            calendar_email = result.get('calendar_email') if result else 'No configurado'
            cursor.close()
            conn.close()
            
            return f"""
            <h1>✅ Evento Creado Exitosamente</h1>
            <p>Se ha creado un evento de prueba en Google Calendar.</p>
            <p><strong>ID del Evento:</strong> {evento_id}</p>
            <p><strong>Servicio:</strong> {info_cita['servicio_solicitado']}</p>
            <p><strong>Fecha:</strong> {info_cita['fecha_sugerida']} a las {info_cita['hora_sugerida']}</p>
            <p><strong>Cliente:</strong> {info_cita['nombre_cliente']}</p>
            <p><strong>Correo para notificaciones:</strong> {calendar_email}</p>
            <p>Verifica tu calendario de Google para confirmar que el evento se haya creado correctamente.</p>
            """
        else:
            return """
            <h1>❌ Error al Crear el Evento</h1>
            <p>La autenticación fue exitosa, pero no se pudo crear el evento en el calendario.</p>
            <p>Revisa los logs del servidor para más información sobre el error.</p>
            """
            
    except Exception as e:
        return f"""
        <h1>❌ Error durante la prueba</h1>
        <p>Ocurrió un error al intentar probar la integración con Google Calendar:</p>
        <pre>{str(e)}</pre>
        """

@app.route('/test-contacto')
def test_contacto(numero = '5214493432744'):
    """Endpoint para probar la obtención de información de contacto"""
    config = obtener_configuracion_por_host()
    nombre, imagen = obtener_nombre_perfil_whatsapp(numero, config)
    nombre, imagen = obtener_imagen_perfil_whatsapp(numero, config)
    return jsonify({
        'numero': numero,
        'nombre': nombre,
        'imagen': imagen,
        'config': config.get('dominio')
    })

def obtener_nombre_perfil_whatsapp(numero, config=None):
    """Obtiene el nombre del contacto desde la base de datos"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT nombre, alias 
        FROM contactos 
        WHERE numero_telefono = %s
        ORDER BY fecha_actualizacion DESC 
        LIMIT 1
    """, (numero,))
    
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if result:
        return result['alias'] or result['nombre']
    return None
  
def obtener_configuracion_por_host():
    """Obtiene la configuración basada en el host"""
    try:
        from flask import has_request_context
        if not has_request_context():
            return NUMEROS_CONFIG['524495486142']  # Default
        
        host = request.headers.get('Host', '').lower()
        
        if 'unilova' in host:
            app.logger.info("✅ Configuración detectada: Ofitodo")
            return NUMEROS_CONFIG['123']
        
        # DETECCIÓN PORFIRIANNA
        if 'laporfirianna' in host:
            app.logger.info("✅ Configuración detectada: Ofitodo")
            return NUMEROS_CONFIG['524812372326']
            
        # DETECCIÓN NUEVO SUBDOMINIO
        if 'ofitodo' in host:
            app.logger.info("✅ Configuración detectada: Ofitodo")
            return NUMEROS_CONFIG['524495486324']
        
        # DEFAULT MEKTIA
        app.logger.info("✅ Configuración por defecto: Mektia")
        return NUMEROS_CONFIG['524495486142']
            
    except Exception as e:
        app.logger.error(f"🔴 Error en obtener_configuracion_por_host: {e}")
        return NUMEROS_CONFIG['524495486142']

@app.route('/diagnostico')
def diagnostico():
    """Endpoint completo de diagnóstico"""
    try:
        config = obtener_configuracion_por_host()
        
        info = {
            'host': request.headers.get('Host'),
            'referer': request.headers.get('Referer'),
            'url': request.url,
            'config_detectada': config.get('dominio'),
            'config_db': config.get('db_name'),
            'timestamp': datetime.now().isoformat()
        }
        
        # Intentar conexión a BD
        try:
            conn = get_db_connection(config)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            info['bd_conexion'] = 'success'
            cursor.close()
            conn.close()
        except Exception as e:
            info['bd_conexion'] = f'error: {str(e)}'
        
        return jsonify(info)
        
    except Exception as e:
        return jsonify({'error': str(e)})    

# Modificar la función home para inyectar plan_info cuando el usuario está autenticado.
# Reemplaza la parte final de home() donde haces render_template(...) por la versión que incluye plan_info.

@app.route('/home')
def home():
    config = obtener_configuracion_por_host()
    period = request.args.get('period', 'week')
    now    = datetime.now()
    start  = now - (timedelta(days=30) if period=='month' else timedelta(days=7))
    # Detectar configuración basada en el host
    period = request.args.get('period', 'week')
    now = datetime.now()
    conn = get_db_connection(config)  # ✅ Usar config
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(DISTINCT numero) FROM conversaciones WHERE timestamp>= %s;",
        (start,)
    )
    chat_counts = cursor.fetchone()[0]

    # 🔁 Unir con contactos y usar alias/nombre si existe
    cursor.execute("""
        SELECT 
            conv.numero,
            COALESCE(cont.alias, cont.nombre, conv.numero) AS nombre_mostrado,
            COUNT(*) AS total
        FROM conversaciones conv
        LEFT JOIN contactos cont ON cont.numero_telefono = conv.numero
        WHERE conv.timestamp >= %s
        GROUP BY conv.numero, nombre_mostrado
        ORDER BY total DESC
    """, (start,))
    messages_per_chat = cursor.fetchall()

    cursor.execute(
        "SELECT COUNT(*) FROM conversaciones WHERE respuesta<>'' AND timestamp>= %s;",
        (start,)
    )
    total_responded = cursor.fetchone()[0]

    cursor.close()
    conn.close()

    labels = [row[1] for row in messages_per_chat]  # nombre_mostrado
    values = [row[2] for row in messages_per_chat]  # total

    # Obtener plan info para el usuario autenticado (si aplica)
    plan_info = None
    try:
        au = session.get('auth_user')
        if au and au.get('user'):
            # obtener plan status
            plan_info = get_plan_status_for_user(au.get('user'), config=config)
    except Exception as e:
        app.logger.warning(f"⚠️ No se pudo obtener plan_info para el usuario: {e}")
        plan_info = None

    return render_template('dashboard.html',
        chat_counts=chat_counts,
        messages_per_chat=messages_per_chat,
        total_responded=total_responded,
        period=period,
        labels=labels,
        values=values,
        plan_info=plan_info
    )

@app.route('/chats')
def ver_chats():
    config = obtener_configuracion_por_host()
    app.logger.info(f"🔧 Configuración detectada para chats: {config.get('dominio', 'desconocido')}")
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT 
          conv.numero, 
          COUNT(*) AS total_mensajes, 
          cont.imagen_url, 
          -- PRIORIDAD: alias > nombre > número
          COALESCE(cont.alias, cont.nombre, conv.numero) AS nombre_mostrado,
          cont.alias,
          cont.nombre,
          (SELECT mensaje FROM conversaciones 
           WHERE numero = conv.numero 
           ORDER BY timestamp DESC LIMIT 1) AS ultimo_mensaje,
          MAX(conv.timestamp) AS ultima_fecha
        FROM conversaciones conv
        LEFT JOIN contactos cont ON conv.numero = cont.numero_telefono
        GROUP BY conv.numero, cont.imagen_url, cont.alias, cont.nombre
        ORDER BY MAX(conv.timestamp) DESC
    """)
    chats = cursor.fetchall()
    # 🔥 CONVERTIR TIMESTAMPS A HORA DE MÉXICO - AQUÍ ESTÁ EL FIX
    for chat in chats:
        if chat.get('ultima_fecha'):
            # Si el timestamp ya tiene timezone info, convertirlo
            if chat['ultima_fecha'].tzinfo is not None:
                chat['ultima_fecha'] = chat['ultima_fecha'].astimezone(tz_mx)
            else:
                # Si no tiene timezone, asumir que es UTC y luego convertir
                chat['ultima_fecha'] = pytz.utc.localize(chat['ultima_fecha']).astimezone(tz_mx)
    cursor.close()
    conn.close()
    
    return render_template('chats.html',
        chats=chats, 
        mensajes=None,
        selected=None, 
        IA_ESTADOS=IA_ESTADOS,
        tenant_config=config
    )

@app.route('/chats/<numero>')
def ver_chat(numero):
    try:
        config = obtener_configuracion_por_host()
        app.logger.info(f"🔧 Configuración para chat {numero}: {config.get('db_name', 'desconocida')}")
        
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        
        # Check if number exists in IA_ESTADOS
        if numero not in IA_ESTADOS:
            cursor.execute("SELECT ia_activada FROM contactos WHERE numero_telefono = %s", (numero,))
            result = cursor.fetchone()
            ia_active = True if result is None or result.get('ia_activada') is None else bool(result.get('ia_activada'))
            IA_ESTADOS[numero] = {'activa': ia_active}
            app.logger.info(f"🔍 IA state loaded from database for {numero}: {IA_ESTADOS[numero]}")
        else:
            app.logger.info(f"🔍 Using existing IA state for {numero}: {IA_ESTADOS[numero]}")
        
        app.logger.info(f"🔍 IA state for {numero}: {IA_ESTADOS[numero]}")
        # Consulta para los datos del chat
        cursor.execute("""
            SELECT DISTINCT
                conv.numero, 
                cont.imagen_url, 
                COALESCE(cont.alias, cont.nombre, conv.numero) AS nombre_mostrado,
                cont.alias,
                cont.nombre
            FROM conversaciones conv
            LEFT JOIN contactos cont ON conv.numero = cont.numero_telefono
            WHERE conv.numero = %s
            LIMIT 1;
        """, (numero,))
        chats = cursor.fetchall()

        # Consulta para mensajes - INCLUYENDO IMÁGENES
        cursor.execute("""
            SELECT numero, mensaje, respuesta, timestamp, imagen_url, es_imagen
            FROM conversaciones 
            WHERE numero = %s 
            ORDER BY timestamp ASC;
        """, (numero,))
        msgs = cursor.fetchall()

        # Convertir timestamps
        for msg in msgs:
            if msg.get('timestamp'):
                if msg['timestamp'].tzinfo is None:
                    msg['timestamp'] = tz_mx.localize(msg['timestamp'])
                else:
                    msg['timestamp'] = msg['timestamp'].astimezone(tz_mx)

        cursor.close()
        conn.close()
        
        app.logger.info(f"✅ Chat cargado: {len(chats)} chats, {len(msgs)} mensajes")
        
        return render_template('chats.html',
            chats=chats, 
            mensajes=msgs,
            selected=numero, 
            IA_ESTADOS=IA_ESTADOS,
            tenant_config=config
        )
        
    except Exception as e:
        # Log full traceback and provide a safe inline error page (do not rely on error.html template)
        import traceback as _tb, hashlib as _hash, time as _time
        tb = _tb.format_exc()
        err_id = _hash.md5(f"{_time.time()}_{numero}_{str(e)}".encode()).hexdigest()[:8]
        app.logger.error(f"🔴 ERROR CRÍTICO en ver_chat (id={err_id}): {e}")
        app.logger.error(tb)
        # Avoid rendering a missing template — return a minimal safe page with error id
        html = """
        <html><head><title>Error</title></head><body>
          <h1>Internal server error</h1>
          <p>An internal error occurred while loading the chat. Error ID: <strong>{{ err_id }}</strong></p>
          <p>Please check server logs for details (search for the same Error ID).</p>
        </body></html>
        """
        return render_template_string(html, err_id=err_id), 500
       
@app.route('/debug-calendar-email')
def debug_calendar_email():
    """Endpoint para verificar si el correo de Calendar está guardado"""
    config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    # Verificar si la columna existe
    cursor.execute("SHOW COLUMNS FROM configuracion LIKE 'calendar_email'")
    column_exists = cursor.fetchone() is not None
    
    # Obtener el valor actual
    calendar_email = None
    if column_exists:
        cursor.execute("SELECT calendar_email FROM configuracion WHERE id = 1")
        result = cursor.fetchone()
        if result:
            calendar_email = result['calendar_email']
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'columna_existe': column_exists,
        'calendar_email': calendar_email,
        'host': request.host,
        'config': config['dominio']
    })    

@app.route('/debug-db')
def debug_db():
    """Endpoint para verificar la conexión a la base de datos"""
    try:
        config = obtener_configuracion_por_host()
        app.logger.info(f"🔍 Verificando conexión a: {config.get('db_name')}")
        
        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute("SELECT DATABASE() as db, USER() as user")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        return jsonify({
            'status': 'success',
            'database': result[0] if result else 'unknown',
            'user': result[1] if result else 'unknown',
            'config_db': config.get('db_name'),
            'host': request.headers.get('Host')
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e),
            'config_db': config.get('db_name') if 'config' in locals() else 'unknown',
            'host': request.headers.get('Host')
        })

@app.before_request
def log_configuracion():
    if request.endpoint and request.endpoint != 'static':
        try:
            host = request.headers.get('Host', '').lower()
            referer = request.headers.get('Referer', '')
            config = obtener_configuracion_por_host()
            app.logger.info(f"🌐 [{request.endpoint}] Host: {host} | Referer: {referer} | BD: {config.get('db_name', 'desconocida')}")
        except Exception as e:
            app.logger.error(f"🔴 Error en log_configuracion: {e}")

@app.route('/toggle_ai/<numero>', methods=['POST'])
def toggle_ai(numero, config=None):
    config = obtener_configuracion_por_host()
    try:
        app.logger.info(f"🔍 Toggle AI request for {numero}")
        app.logger.info(f"🔍 Current IA_ESTADOS before toggle: {IA_ESTADOS.get(numero, {'activa': True})}")
        
        conn = get_db_connection(config)
        cursor = conn.cursor()

        # First, get the current state
        cursor.execute("SELECT ia_activada FROM contactos WHERE numero_telefono = %s", (numero,))
        result = cursor.fetchone()
        current_state = result[0] if result else True  # Default to True if not found
        
        app.logger.info(f"🔍 Current state in database: {current_state}")
        
        # Toggle the state in database
        new_state = not current_state
        cursor.execute("""
            UPDATE contactos
            SET ia_activada = %s
            WHERE numero_telefono = %s
        """, (new_state, numero))

        conn.commit()
        cursor.close()
        conn.close()

        # IMPORTANT: Update the in-memory state
        IA_ESTADOS[numero] = {'activa': new_state}
        
        app.logger.info(f"🔘 Estado IA cambiado para {numero}: {new_state}")
        app.logger.info(f"🔍 Updated IA_ESTADOS after toggle: {IA_ESTADOS.get(numero)}")
    except Exception as e:
        app.logger.error(f"Error al cambiar estado IA: {e}")

    return redirect(url_for('ver_chat', numero=numero))

@app.route('/send-manual', methods=['POST'])
def enviar_manual():
        config = obtener_configuracion_por_host()
        conn = get_db_connection(config)
        try:
            numero = request.form['numero']
            texto = request.form['texto'].strip()
        
            # Validar que el mensaje no esté vacío
            if not texto:
                flash('❌ El mensaje no puede estar vacío', 'error')
                return redirect(url_for('ver_chat', numero=numero))
        
            app.logger.info(f"📤 Enviando mensaje manual a {numero}: {texto[:50]}...")
        
            # 1. ENVIAR MENSAJE POR WHATSAPP
            enviar_mensaje(numero, texto)
        
            # 2. GUARDAR EN BASE DE DATOS (como mensaje manual)
            conn = get_db_connection(config)
            cursor = conn.cursor()
        
            # Usar timestamp con zona horaria de México
            timestamp_local = datetime.now(tz_mx)  # Cambiar de utcnow() a now(tz_mx)
        
            cursor.execute(
                "INSERT INTO conversaciones (numero, mensaje, respuesta, timestamp) VALUES (%s, %s, %s, %s);",
                (numero, '[Mensaje manual desde web]', texto, timestamp_local)
            )
        
            conn.commit()
            cursor.close()
            conn.close()
            
            # 3. ACTUALIZAR KANBAN (mover a "Esperando Respuesta")
            try:
                actualizar_columna_chat(numero, 3)  # 3 = Esperando Respuesta
                app.logger.info(f"📊 Chat {numero} movido a 'Esperando Respuesta' en Kanban")
            except Exception as e:
                app.logger.error(f"⚠️ Error actualizando Kanban: {e}")
            
            # 4. MENSAJE DE CONFIRMACIÓN
            flash('✅ Mensaje enviado correctamente', 'success')
            app.logger.info(f"✅ Mensaje manual enviado con éxito a {numero}")
            
        except KeyError:
            flash('❌ Error: Número de teléfono no proporcionado', 'error')
            app.logger.error("🔴 Error: Falta parámetro 'numero' en enviar_manual")
        except Exception as e:
            flash('❌ Error al enviar el mensaje', 'error')
            app.logger.error(f"🔴 Error en enviar_manual: {e}")
        
        return redirect(url_for('ver_chat', numero=numero))
        
@app.route('/chats/<numero>/eliminar', methods=['POST'])
def eliminar_chat(numero):
    config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor()
    
    # Solo eliminar conversaciones, NO contactos
    cursor.execute("DELETE FROM conversaciones WHERE numero=%s;", (numero,))
    
    # Opcional: también eliminar de chat_meta si usas kanban
    try:
        cursor.execute("DELETE FROM chat_meta WHERE numero=%s;", (numero,))
    except:
        pass  # Ignorar si la tabla no existe
    
    conn.commit()
    cursor.close()
    conn.close()
    
    IA_ESTADOS.pop(numero, None)
    return redirect(url_for('ver_chats'))

    # ——— Configuración ———

def limpiar_estados_antiguos():
    """Limpia estados de conversación con más de 2 horas"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('''
            DELETE FROM estados_conversacion 
            WHERE timestamp < NOW() - INTERVAL 2 HOUR
        ''')
        conn.commit()
        cursor.close()
        conn.close()
        app.logger.info("🧹 Estados antiguos limpiados")
    except Exception as e:
        app.logger.error(f"Error limpiando estados: {e}")

# Ejecutar esta función periódicamente (puedes usar un scheduler)
def continuar_proceso_pedido(numero, mensaje, estado_actual, config=None):
    """Continúa el proceso de pedido de manera inteligente"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    datos = estado_actual.get('datos', {})
    paso_actual = datos.get('paso', 1)
    analisis_inicial = datos.get('analisis_inicial', {})
    
    app.logger.info(f"🔄 Continuando pedido paso {paso_actual} para {numero}")
    
    # Analizar el nuevo mensaje para extraer información
    nuevo_analisis = detectar_pedido_inteligente(mensaje, numero, config=config)
    
    if nuevo_analisis and nuevo_analisis.get('es_pedido'):
        # Actualizar datos obtenidos
        datos_obtenidos = datos.get('datos_obtenidos', {})
        nuevos_datos = nuevo_analisis.get('datos_obtenidos', {})
        
        # Combinar datos
        for clave, valor in nuevos_datos.items():
            if valor and valor != 'null':
                if clave == 'platillos' and valor:
                    datos_obtenidos.setdefault('platillos', []).extend(valor)
                elif clave == 'cantidades' and valor:
                    datos_obtenidos.setdefault('cantidades', []).extend(valor)
                elif clave == 'especificaciones' and valor:
                    datos_obtenidos.setdefault('especificaciones', []).extend(valor)
                else:
                    datos_obtenidos[clave] = valor
        
        datos['datos_obtenidos'] = datos_obtenidos
        datos['paso'] += 1
        
        # Verificar si tenemos todos los datos necesarios
        if verificar_pedido_completo(datos_obtenidos):
            # Pedido completo, confirmar
            return confirmar_pedido_completo(numero, datos_obtenidos, config)
        else:
            # Seguir preguntando por datos faltantes
            siguiente_pregunta = nuevo_analisis.get('siguiente_pregunta')
            if not siguiente_pregunta:
                siguiente_pregunta = generar_pregunta_datos_faltantes(datos_obtenidos)
            
            actualizar_estado_conversacion(numero, "EN_PEDIDO", "solicitar_datos", datos, config)
            return siguiente_pregunta
    
    # Si no se detecta información relevante, pedir clarificación
    return "No entendí bien esa información. ¿Podrías ser más específico sobre tu pedido?"

def verificar_pedido_completo(datos_obtenidos):
    """Verifica si el pedido tiene todos los datos necesarios"""
    datos_requeridos = ['platillos', 'direccion']
    for dato in datos_requeridos:
        if not datos_obtenidos.get(dato):
            return False
    
    # Verificar que haya al menos un platillo con cantidad
    platillos = datos_obtenidos.get('platillos', [])
    cantidades = datos_obtenidos.get('cantidades', [])
    
    if not platillos or len(platillos) != len(cantidades):
        return False
    
    return True

def generar_pregunta_datos_faltantes(datos_obtenidos):
    """Genera preguntas inteligentes para datos faltantes"""
    if not datos_obtenidos.get('platillos'):
        return "¿Qué platillos te gustaría ordenar? Tenemos gorditas, tacos, quesadillas, sopes, etc."
    
    if not datos_obtenidos.get('cantidades') or len(datos_obtenidos['platillos']) != len(datos_obtenidos.get('cantidades', [])):
        platillos = datos_obtenidos['platillos']
        return f"¿Cuántas {', '.join(platillos)} deseas ordenar?"
    
    if not datos_obtenidos.get('especificaciones'):
        return "¿Alguna especificación para tu pedido? Por ejemplo: 'con todo', 'sin cebolla', etc."
    
    if not datos_obtenidos.get('direccion'):
        return "¿A qué dirección debemos llevar tu pedido?"
    
    if not datos_obtenidos.get('nombre_cliente'):
        return "¿Cuál es tu nombre para el pedido?"
    
    return "¿Necesitas agregar algo más a tu pedido?"

def confirmar_pedido_completo(numero, datos_pedido, config=None):
    """Confirma el pedido completo y lo guarda"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # Crear resumen del pedido
        platillos = datos_pedido.get('platillos', [])
        cantidades = datos_pedido.get('cantidades', [])
        especificaciones = datos_pedido.get('especificaciones', [])
        
        resumen_platillos = ""
        for i, platillo in enumerate(platillos):
            cantidad = cantidades[i] if i < len(cantidades) else "1"
            resumen_platillos += f"- {cantidad} {platillo}\n"
        
        # Guardar pedido en base de datos
        info_pedido = {
            'servicio_solicitado': f"Pedido: {', '.join(platillos)}",
            'nombre_cliente': datos_pedido.get('nombre_cliente', 'Cliente'),
            'telefono': numero,
            'estado': 'pendiente',
            'notas': f"Especificaciones: {', '.join(especificaciones)}\nDirección: {datos_pedido.get('direccion', 'Por confirmar')}"
        }
        
        pedido_id = guardar_cita(info_pedido, config)
        
        # Mensaje de confirmación
        confirmacion = f"""🎉 *¡Pedido Confirmado!* - ID: #{pedido_id}

📋 *Resumen de tu pedido:*
{resumen_platillos}

🏠 *Dirección:* {datos_pedido.get('direccion', 'Por confirmar')}
👤 *Nombre:* {datos_pedido.get('nombre_cliente', 'Cliente')}

⏰ *Tiempo estimado:* 30-45 minutos
💳 *Forma de pago:* Efectivo al entregar

¡Gracias por tu pedido! Te avisaremos cuando salga para entrega."""
        
        # Limpiar estado
        actualizar_estado_conversacion(numero, "PEDIDO_COMPLETO", "pedido_confirmado", {}, config)
        
        return confirmacion
        
    except Exception as e:
        app.logger.error(f"Error confirmando pedido: {e}")
        return "¡Pedido recibido! Pero hubo un error al guardarlo. Por favor, contacta directamente al restaurante."


@app.route('/configuracion/negocio/borrar-pdf/<int:doc_id>', methods=['POST'])
@login_required
def borrar_pdf_configuracion(doc_id):
    config = obtener_configuracion_por_host()
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT filename, filepath FROM documents_publicos WHERE id = %s LIMIT 1", (doc_id,))
        doc = cursor.fetchone()
        if not doc:
            cursor.close(); conn.close()
            flash('❌ Documento no encontrado', 'error')
            return redirect(url_for('configuracion_tab', tab='negocio'))

        filename = doc.get('filename')
        # Ruta esperada en uploads/docs
        docs_dir = os.path.join(app.config.get('UPLOAD_FOLDER', UPLOAD_FOLDER), 'docs')
        filepath = os.path.join(docs_dir, filename)

        # Intentar eliminar archivo del disco si existe
        try:
            if os.path.isfile(filepath):
                os.remove(filepath)
                app.logger.info(f"🗑️ Archivo eliminado de disco: {filepath}")
            else:
                app.logger.info(f"ℹ️ Archivo no encontrado en disco (posiblemente ya eliminado): {filepath}")
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo eliminar archivo físico: {e}")

        # Eliminar registro DB
        try:
            cursor.execute("DELETE FROM documents_publicos WHERE id = %s", (doc_id,))
            conn.commit()
            flash('✅ Catálogo eliminado correctamente', 'success')
            app.logger.info(f"✅ Registro documents_publicos eliminado: id={doc_id} filename={filename}")
        except Exception as e:
            conn.rollback()
            flash('❌ Error eliminando el registro en la base de datos', 'error')
            app.logger.error(f"🔴 Error eliminando registro documents_publicos: {e}")
        finally:
            cursor.close(); conn.close()

        return redirect(url_for('configuracion_tab', tab='negocio'))

    except Exception as e:
        app.logger.error(f"🔴 Error en borrar_pdf_configuracion: {e}")
        flash('❌ Error eliminando el catálogo', 'error')
        return redirect(url_for('configuracion_tab', tab='negocio'))

@app.route('/configuracion/<tab>', methods=['GET','POST'])
def configuracion_tab(tab):
    config = obtener_configuracion_por_host()
    if tab not in SUBTABS:  # Asegúrate de que 'restricciones' esté en SUBTABS
        abort(404)

    cfg = load_config(config)
    guardado = False
    if request.method == 'POST':
        if tab == 'negocio':
            cfg['negocio'] = {
                'ia_nombre':      request.form['ia_nombre'],
                'negocio_nombre': request.form['negocio_nombre'],
                'descripcion':    request.form['descripcion'],
                'url':            request.form['url'],
                'direccion':      request.form['direccion'],
                'telefono':       request.form['telefono'],
                'correo':         request.form['correo'],
                'que_hace':       request.form['que_hace']
            }
        elif tab == 'personalizacion':
            cfg['personalizacion'] = {
                'tono':     request.form['tono'],
                'lenguaje': request.form['lenguaje']
            }
        elif tab == 'restricciones':
            cfg['restricciones'] = {
                'restricciones': request.form.get('restricciones', ''),
                'palabras_prohibidas': request.form.get('palabras_prohibidas', ''),
                'max_mensajes': int(request.form.get('max_mensajes', 10)),
                'tiempo_max_respuesta': int(request.form.get('tiempo_max_respuesta', 30))
            }
        elif tab == 'asesores':
            cfg['asesores'] = {
                'asesor1_nombre': request.form.get('asesor1_nombre', '').strip(),
                'asesor1_telefono': request.form.get('asesor1_telefono', '').strip(),
                'asesor2_nombre': request.form.get('asesor2_nombre', '').strip(),
                'asesor2_telefono': request.form.get('asesor2_telefono', '').strip()
            }
        save_config(cfg, config)
        guardado = True

    datos = cfg.get(tab, {})

    # Si estamos en la pestaña 'negocio', obtener documentos_publicos para mostrarlos en la plantilla
    documents_publicos = []
    if tab == 'negocio':
        try:
            conn = get_db_connection(config)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SHOW TABLES LIKE 'documents_publicos'")
            if cursor.fetchone():
                cursor.execute("""
                    SELECT id, filename, filepath, descripcion, uploaded_by, created_at
                    FROM documents_publicos
                    ORDER BY created_at DESC
                    LIMIT 50
                """)
                documents_publicos = cursor.fetchall()
            cursor.close()
            conn.close()
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudieron obtener documents_publicos: {e}")
            documents_publicos = []

    return render_template('configuracion.html',
        tabs=SUBTABS, active=tab,
        datos=datos, guardado=guardado,
        documents_publicos=documents_publicos
    )
@app.route('/configuracion/precios', methods=['GET'])
def configuracion_precios():
        config = obtener_configuracion_por_host()
        precios = obtener_todos_los_precios(config)
        return render_template('configuracion/precios.html',
            tabs=SUBTABS, active='precios',
            guardado=False,
            precios=precios,
            precio_edit=None
        )

@app.route('/configuracion/precios/editar/<int:pid>', methods=['GET'])
def configuracion_precio_editar(pid):
        config = obtener_configuracion_por_host()
        precios     = obtener_todos_los_precios(config)
        precio_edit = obtener_precio_por_id(pid, config)
        return render_template('configuracion/precios.html',
            tabs=SUBTABS, active='precios',
            guardado=False,
            precios=precios,
            precio_edit=precio_edit
        )

@app.route('/configuracion/precios/guardar', methods=['POST'])
def configuracion_precio_guardar():
    config = obtener_configuracion_por_host()
    data = request.form.to_dict()
    conn = None
    cursor = None
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor()

        # Process numeric price fields coming from form (empty -> None)
        for f in ['costo', 'precio', 'precio_mayoreo', 'precio_menudeo']:
            if f in data and data.get(f, '').strip() == '':
                data[f] = None

        # Handle image upload (priority over URL)
        imagen_nombre = None
        if 'imagen' in request.files and request.files['imagen'].filename:
            file = request.files['imagen']
            filename = secure_filename(f"{int(time.time())}_{file.filename}")
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            file.save(filepath)
            imagen_nombre = filename
            data['imagen'] = imagen_nombre
        elif data.get('imagen_url') and data.get('imagen_url').strip():
            imagen_url = data.get('imagen_url').strip()
            imagen_nombre = imagen_url
            data['imagen'] = imagen_url

        # Candidate fields in expected order (prefer form names)
        candidate_fields = [
            'sku', 'servicio', 'categoria', 'subcategoria', 'linea', 'modelo',
            'descripcion', 'medidas', 'costo', 'precio', 'precio_mayoreo', 'precio_menudeo',
            'moneda', 'imagen', 'status_ws', 'catalogo', 'catalogo2', 'catalogo3', 'proveedor'
        ]

        # Get actual columns from DB and keep intersection (respect DB schema)
        cursor.execute("SHOW COLUMNS FROM precios")
        existing_cols = [row[0] for row in cursor.fetchall()]

        # Fields we will actually use (preserve order)
        fields_to_use = [f for f in candidate_fields if f in existing_cols]

        if not fields_to_use:
            app.logger.error("❌ Ninguna de las columnas del formulario existe en la tabla 'precios'")
            flash('❌ Error interno: columnas no coinciden con la tabla de precios', 'error')
            return redirect(url_for('configuracion_precios'))

        # Build values array from data (use None when missing)
        values = [data.get(f) for f in fields_to_use]

        # If updating existing record
        if data.get('id'):
            pid = data.get('id')
            # For update, exclude id and only update provided columns
            set_parts = []
            set_values = []
            for i, f in enumerate(fields_to_use):
                set_parts.append(f"{f}=%s")
                set_values.append(values[i])
            sql = f"UPDATE precios SET {', '.join(set_parts)} WHERE id=%s"
            cursor.execute(sql, set_values + [pid])
            conn.commit()
            flash('✅ Producto actualizado correctamente', 'success')
            app.logger.info(f"✅ Precio actualizado (id={pid}) campos: {fields_to_use}")
        else:
            # Insert: build placeholder list
            placeholders = ','.join(['%s'] * len(fields_to_use))
            cols = ','.join(fields_to_use)
            sql = f"INSERT INTO precios ({cols}) VALUES ({placeholders})"
            cursor.execute(sql, values)
            conn.commit()
            flash('✅ Producto agregado correctamente', 'success')
            app.logger.info(f"✅ Nuevo producto insertado campos: {fields_to_use}")

        return redirect(url_for('configuracion_precios'))

    except Exception as e:
        app.logger.error(f"🔴 Error en configuracion_precio_guardar: {e}")
        app.logger.error(traceback.format_exc())
        flash(f'❌ Error guardando producto: {str(e)}', 'error')
        try:
            if conn:
                conn.rollback()
        except:
            pass
        return redirect(url_for('configuracion_precios'))
    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except:
            pass

@app.route('/configuracion/precios/borrar/<int:pid>', methods=['POST'])
def configuracion_precio_borrar(pid):
        config = obtener_configuracion_por_host()
        conn   = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM precios WHERE id=%s;", (pid,))
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('configuracion_precios'))

@app.route('/debug-image/<filename>')
def debug_image(filename):
    """Endpoint to debug image paths and existence"""
    full_path = os.path.join(UPLOAD_FOLDER, filename)
    exists = os.path.isfile(full_path)
    return jsonify({
        'filename': filename,
        'full_path': full_path,
        'exists': exists,
        'url': url_for('serve_uploaded_file', filename=filename, _external=True)
    })

@app.route('/debug-image-full/<path:image_path>')
def debug_image_full(image_path):
    """Enhanced endpoint to debug images with more details"""
    # Check different possible locations
    possible_paths = [
        os.path.join(UPLOAD_FOLDER, image_path),
        os.path.join(app.static_folder, 'images', image_path),
        os.path.join(app.static_folder, 'images', 'whatsapp', image_path),
        os.path.join(UPLOAD_FOLDER, 'productos', image_path),
        os.path.join(app.root_path, image_path)
    ]
    
    results = []
    for path in possible_paths:
        exists = os.path.isfile(path)
        size = os.path.getsize(path) if exists else 0
        mime_type = None
        
        if exists:
            try:
                import magic
                mime_type = magic.from_file(path, mime=True)
            except ImportError:
                # Fallback if python-magic not installed
                if path.lower().endswith(('.jpg', '.jpeg')):
                    mime_type = 'image/jpeg'
                elif path.lower().endswith('.png'):
                    mime_type = 'image/png'
                else:
                    mime_type = 'unknown'
        
        results.append({
            'path': path,
            'exists': exists,
            'size': size,
            'mime_type': mime_type,
            'url': url_for('static', filename=path.replace(app.static_folder, '').lstrip('/'), _external=True) 
                  if path.startswith(app.static_folder) else None
        })
    
    # Also check the original debug info
    original_path = os.path.join(UPLOAD_FOLDER, image_path)
    original_exists = os.path.isfile(original_path)
    
    return jsonify({
        'filename': image_path,
        'results': results,
        'original_path': original_path,
        'original_exists': original_exists,
        'static_folder': app.static_folder,
        'upload_folder': UPLOAD_FOLDER
    })

def aplicar_restricciones(respuesta_ia, numero, config=None):
    """Aplica las restricciones configuradas a las respuestas de la IA"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        cfg = load_config(config)
        restricciones = cfg.get('restricciones', {})
        
        # Verificar palabras prohibidas
        palabras_prohibidas = restricciones.get('palabras_prohibidas', '').lower().split('\n')
        palabras_prohibidas = [p.strip() for p in palabras_prohibidas if p.strip()]
        
        for palabra in palabras_prohibidas:
            if palabra and palabra in respuesta_ia.lower():
                respuesta_ia = respuesta_ia.replace(palabra, '[REDACTADO]')
                app.logger.info(f"🚫 Palabra prohibida detectada y redactada: {palabra}")
        
        # Verificar restricciones específicas
        lista_restricciones = restricciones.get('restricciones', '').split('\n')
        lista_restricciones = [r.strip() for r in lista_restricciones if r.strip()]
        
        # Ejemplo: Si hay restricción sobre agendar citas sin confirmación
        if any('no agendar citas sin confirmación' in r.lower() for r in lista_restricciones):
            if any(palabra in respuesta_ia.lower() for palabra in ['agendo', 'agendado', 'cita confirmada']):
                if 'confirmación' not in respuesta_ia.lower() and 'verific' not in respuesta_ia.lower():
                    respuesta_ia = "Necesito confirmar algunos detalles antes de agendar la cita. ¿Podrías proporcionarme más información?"
                    app.logger.info(f"🔒 Restricción de cita aplicada para {numero}")
        
        # Verificar límite de mensajes
        max_mensajes = restricciones.get('max_mensajes', 10)
        historial = obtener_historial(numero, limite=max_mensajes + 5, config=config)
        
        if len(historial) >= max_mensajes:
            respuesta_ia = "Hemos alcanzado el límite de esta conversación. Por favor, contacta con un agente humano para continuar."
            app.logger.info(f"📊 Límite de mensajes alcanzado para {numero}")
        
        return respuesta_ia
        
    except Exception as e:
        app.logger.error(f"Error aplicando restricciones: {e}")
        return respuesta_ia
    # ——— Kanban ———

def verificar_tablas_bd(config):
    """Verifica que todas las tablas necesarias existan en la base de datos"""
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor()
        
        tablas_requeridas = ['conversaciones', 'contactos', 'chat_meta']
        tablas_existentes = []
        
        cursor.execute("SHOW TABLES")
        for (table_name,) in cursor.fetchall():
            tablas_existentes.append(table_name)
        
        cursor.close()
        conn.close()
        
        faltantes = [tabla for tabla in tablas_requeridas if tabla not in tablas_existentes]
        
        if faltantes:
            app.logger.error(f"❌ Tablas faltantes en {config['db_name']}: {faltantes}")
            return False
        else:
            app.logger.info(f"✅ Todas las tablas existen en {config['db_name']}")
            return True
            
    except Exception as e:
        app.logger.error(f"🔴 Error verificando tablas: {e}")
        return False

# Llama esta función al inicio para ambas bases de datos
with app.app_context():
    # Esta función se ejecutará cuando la aplicación se inicie
    app.logger.info("🔍 Verificando tablas en todas las bases de datos...")
    for nombre, config in NUMEROS_CONFIG.items():
        verificar_tablas_bd(config)
def verificar_todas_tablas():
    app.logger.info("🔍 Verificando tablas en todas las bases de datos...")
    for nombre, config in NUMEROS_CONFIG.items():
        verificar_tablas_bd(config)

@app.route('/kanban')
def ver_kanban(config=None):
    config = obtener_configuracion_por_host()
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)

    # 1) Cargamos las columnas Kanban
    cursor.execute("SELECT * FROM kanban_columnas ORDER BY orden;")
    columnas = cursor.fetchall()

    # 2) CONSULTA DEFINITIVA - compatible con only_full_group_by
    # En ver_kanban(), modifica la consulta para mejor manejo de nombres: 
    cursor.execute("""
        SELECT 
            cm.numero,
            cm.columna_id,
            MAX(c.timestamp) AS ultima_fecha,
            (SELECT mensaje FROM conversaciones 
             WHERE numero = cm.numero 
             ORDER BY timestamp DESC LIMIT 1) AS ultimo_mensaje,
            MAX(cont.imagen_url) AS avatar,
            MAX(cont.plataforma) AS canal,
            -- PRIORIDAD: alias > nombre de perfil > número
            COALESCE(
                MAX(cont.alias), 
                MAX(cont.nombre), 
                cm.numero
            ) AS nombre_mostrado,
            (SELECT COUNT(*) FROM conversaciones 
             WHERE numero = cm.numero AND respuesta IS NULL) AS sin_leer
        FROM chat_meta cm
        LEFT JOIN contactos cont ON cont.numero_telefono = cm.numero
        LEFT JOIN conversaciones c ON c.numero = cm.numero
        GROUP BY cm.numero, cm.columna_id
        ORDER BY ultima_fecha DESC;
    """)
    chats = cursor.fetchall()

    # 🔥 CONVERTIR TIMESTAMPS A HORA DE MÉXICO (igual que en conversaciones)
    for chat in chats:
        if chat.get('ultima_fecha'):
            # Si el timestamp ya tiene timezone info, convertirlo
            if chat['ultima_fecha'].tzinfo is not None:
                chat['ultima_fecha'] = chat['ultima_fecha'].astimezone(tz_mx)
            else:
                # Si no tiene timezone, asumir que es UTC y luego convertir
                chat['ultima_fecha'] = pytz.utc.localize(chat['ultima_fecha']).astimezone(tz_mx)

    cursor.close()
    conn.close()

    return render_template('kanban.html', columnas=columnas, chats=chats)     

@app.route('/kanban/mover', methods=['POST'])
def kanban_mover():
        config = obtener_configuracion_por_host()
        conn = get_db_connection(config)
        data = request.get_json()
        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute(
          "UPDATE chat_meta SET columna_id=%s WHERE numero=%s;",
          (data['columna_id'], data['numero'])
        )
        conn.commit(); cursor.close(); conn.close()
        return '', 204
    
   

@app.route('/contactos/<numero>/alias', methods=['POST'])
def guardar_alias_contacto(numero, config=None):
        config = obtener_configuracion_por_host()
        alias = request.form.get('alias','').strip()
        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE contactos SET alias=%s WHERE numero_telefono=%s",
            (alias if alias else None, numero)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return '', 204

    # ——— Páginas legales —

@app.route('/proxy-audio/<path:audio_url>')
def proxy_audio(audio_url):
    """Proxy para evitar problemas de CORS con archivos de audio"""
    try:
        response = requests.get(audio_url, timeout=10)
        return Response(response.content, mimetype=response.headers.get('content-type', 'audio/ogg'))
    except Exception as e:
        return str(e), 500

@app.route('/privacy-policy')
def privacy_policy():
        return render_template('privacy_policy.html')

@app.route('/terms-of-service')
def terms_of_service():
        return render_template('terms_of_service.html')

@app.route('/data-deletion')
def data_deletion():
        return render_template('data_deletion.html')

@app.route('/test-alerta')
def test_alerta():
    config = obtener_configuracion_por_host()  # 🔥 OBTENER CONFIG PRIMERO
    enviar_alerta_humana("Prueba", "524491182201", "Mensaje clave", "Resumen de prueba.", config)  # 🔥 AGREGAR config
    return "🚀 Test alerta disparada."

def obtener_chat_meta(numero, config=None):
        if config is None:
            config = obtener_configuracion_por_host()
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM chat_meta WHERE numero = %s;", (numero,))
        meta = cursor.fetchone()
        cursor.close()
        conn.close()
        return meta

# ——— Modificar la función inicializar_chat_meta para ser más robusta ———
def inicializar_chat_meta(numero, config=None):
    """Inicializa el chat meta usando información existente del contacto"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    # Asegurar que las tablas Kanban existen
    crear_tablas_kanban(config)
    
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    try:
        # 1. Verificar si el contacto ya existe
        cursor.execute("SELECT * FROM contactos WHERE numero_telefono = %s", (numero,))
        contacto_existente = cursor.fetchone()
        
        # 2. Si no existe, crear el contacto básico
        if not contacto_existente:
            cursor.execute("""
                INSERT INTO contactos 
                    (numero_telefono, plataforma, fecha_creacion) 
                VALUES (%s, 'WhatsApp', NOW())
            """, (numero,))
            app.logger.info(f"✅ Contacto básico creado: {numero}")
        
        # 3. Insertar/actualizar en chat_meta
        cursor.execute("""
            INSERT INTO chat_meta (numero, columna_id) 
            VALUES (%s, 1)
            ON DUPLICATE KEY UPDATE columna_id = VALUES(columna_id)
        """, (numero,))
        
        conn.commit()
        app.logger.info(f"✅ Chat meta inicializado: {numero}")
        
    except Exception as e:
        app.logger.error(f"❌ Error inicializando chat meta para {numero}: {e}")
        conn.rollback()
    
    finally:
        cursor.close()
        conn.close()

# ——— Agregar ruta para reparar Kanban específico ———
@app.route('/reparar-kanban-porfirianna')
def reparar_kanban_porfirianna():
    """Repara específicamente el Kanban de La Porfirianna"""
    config = NUMEROS_CONFIG['524812372326']  # Config de La Porfirianna
    
    try:
        # 1. Crear tablas Kanban
        crear_tablas_kanban(config)
        
        # 2. Reparar contactos
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT c.numero_telefono 
            FROM contactos c 
            LEFT JOIN chat_meta cm ON c.numero_telefono = cm.numero 
            WHERE cm.numero IS NULL
        """)
        
        contactos_sin_meta = [row['numero_telefono'] for row in cursor.fetchall()]
        
        for numero in contactos_sin_meta:
            inicializar_chat_meta(numero, config)
        
        cursor.close()
        conn.close()
        
        return f"✅ Kanban de La Porfirianna reparado: {len(contactos_sin_meta)} contactos actualizados"
        
    except Exception as e:
        return f"❌ Error reparando Kanban: {str(e)}"

@app.route('/reparar-contactos')
def reparar_contactos():
    """Repara todos los contactos que no están en chat_meta"""
    config = obtener_configuracion_por_host()
    
    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)
    
    # Encontrar contactos que no están en chat_meta
    cursor.execute("""
        SELECT c.numero_telefono 
        FROM contactos c 
        LEFT JOIN chat_meta cm ON c.numero_telefono = cm.numero 
        WHERE cm.numero IS NULL
    """)
    
    contactos_sin_meta = [row['numero_telefono'] for row in cursor.fetchall()]
    
    for numero in contactos_sin_meta:
        app.logger.info(f"🔧 Reparando contacto: {numero}")
        inicializar_chat_meta(numero, config)
    
    cursor.close()
    conn.close()
    
    return f"✅ Reparados {len(contactos_sin_meta)} contactos sin chat_meta"

def actualizar_kanban(numero=None, columna_id=None, config=None):
    # Actualiza la base de datos si se pasan parámetros
    if numero and columna_id:
        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO chat_meta (numero, columna_id)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE columna_id = VALUES(columna_id),
                                    fecha_actualizacion = CURRENT_TIMESTAMP
        """, (numero, columna_id))
        conn.commit()
        cursor.close()
        conn.close()
    # No emitas ningún evento aquí

# Add this new function that updates chat_meta immediately when receiving a message
def actualizar_kanban_inmediato(numero, config=None):
    """Updates the Kanban board immediately when a message is received"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # Ensure contact exists in chat_meta
        meta = obtener_chat_meta(numero, config)
        if not meta:
            inicializar_chat_meta(numero, config)
            app.logger.info(f"✅ Chat meta initialized for {numero}")
        
        # Determine appropriate column based on message history
        historial = obtener_historial(numero, limite=2, config=config)
        
        if not historial:
            # First message ever - put in "Nuevos"
            nueva_columna = 1
            app.logger.info(f"📊 First message from {numero} - moving to column 1 (Nuevos)")
        else:
            # Existing conversation - put in "En Conversación"
            nueva_columna = 2
            app.logger.info(f"📊 New message from {numero} - moving to column 2 (En Conversación)")
        
        # Update the database
        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE chat_meta SET columna_id = %s
            WHERE numero = %s
        """, (nueva_columna, numero))
        conn.commit()
        cursor.close()
        conn.close()
        
        app.logger.info(f"✅ Kanban updated immediately for {numero} to column {nueva_columna}")
        return True
    except Exception as e:
        app.logger.error(f"❌ Error updating Kanban immediately: {e}")
        return False

def actualizar_columna_chat(numero, columna_id, config=None):
        if config is None:
            config = obtener_configuracion_por_host()
        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE chat_meta SET columna_id = %s 
            WHERE numero = %s;
        """, (columna_id, numero))
        conn.commit()
        cursor.close()
        conn.close()

def actualizar_info_contacto(numero, config=None):
    """Actualiza la información del contacto, priorizando los datos del webhook"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # Primero verificar si ya tenemos información reciente del webhook
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        
        cursor.execute("""
            SELECT nombre, imagen_url, fecha_actualizacion 
            FROM contactos 
            WHERE numero_telefono = %s
        """, (numero,))
        
        contacto = cursor.fetchone()
        
        # Si el contacto ya tiene nombre y fue actualizado recientemente (últimas 24 horas), no hacer nada
        if contacto and contacto.get('nombre') and contacto.get('fecha_actualizacion'):
            fecha_actualizacion = contacto['fecha_actualizacion']
            if isinstance(fecha_actualizacion, str):
                fecha_actualizacion = datetime.fromisoformat(fecha_actualizacion.replace('Z', '+00:00'))
            
            if (datetime.now() - fecha_actualizacion).total_seconds() < 86400:  # 24 horas
                app.logger.info(f"✅ Información de contacto {numero} ya está actualizada")
                cursor.close()
                conn.close()
                return
        
        cursor.close()
        conn.close()
        
        # Si no tenemos información reciente, intentar con WhatsApp Web como fallback
        try:
            client = get_whatsapp_client()
            if client and client.is_logged_in:
                nombre_whatsapp, imagen_whatsapp = client.get_contact_info(numero)
                if nombre_whatsapp or imagen_whatsapp:
                    app.logger.info(f"✅ Información obtenida via WhatsApp Web para {numero}")
                    
                    conn = get_db_connection(config)
                    cursor = conn.cursor()
                    
                    cursor.execute("""
                        UPDATE contactos 
                        SET nombre = COALESCE(%s, nombre),
                            imagen_url = COALESCE(%s, imagen_url),
                            fecha_actualizacion = NOW()
                        WHERE numero_telefono = %s
                    """, (nombre_whatsapp, imagen_whatsapp, numero))
                    
                    conn.commit()
                    cursor.close()
                    conn.close()
                    return
        except Exception as e:
            app.logger.warning(f"⚠️ WhatsApp Web no disponible: {e}")
        
        app.logger.info(f"ℹ️  Usando información del webhook para {numero}")
            
    except Exception as e:
        app.logger.error(f"Error actualizando contacto {numero}: {e}")

def evaluar_movimiento_automatico(numero, mensaje, respuesta, config=None):
        if config is None:
            config = obtener_configuracion_por_host()
    
        historial = obtener_historial(numero, limite=5, config=config)
        
        # Si es primer mensaje, mantener en "Nuevos"
        if len(historial) <= 1:
            return 1  # Nuevos
        
        # Si hay intervención humana, mover a "Esperando Respuesta"
        if detectar_intervencion_humana_ia(mensaje, respuesta, numero):
            return 3  # Esperando Respuesta
        
        # Si tiene más de 2 mensajes, mover a "En Conversación"
        if len(historial) >= 2:
            return 2  # En Conversación
        
        # Si no cumple nada, mantener donde está
        meta = obtener_chat_meta(numero)
        return meta['columna_id'] if meta else 1

def obtener_contexto_consulta(numero, config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        
        # Obtener los últimos mensajes para entender el contexto
        cursor.execute("""
            SELECT mensaje, respuesta 
            FROM conversaciones 
            WHERE numero = %s 
            ORDER BY timestamp DESC 
            LIMIT 5
        """, (numero,))
        
        mensajes = cursor.fetchall()
        cursor.close()
        conn.close()
        
        if not mensajes:
            return "No hay historial de conversación reciente."
        
        # Analizar el contexto de la conversación
        contexto = ""
        
        # Buscar menciones de servicios/proyectos
        servicios_mencionados = []
        for msg in mensajes:
            mensaje_texto = msg['mensaje'].lower() if msg['mensaje'] else ""  # 🔥 CORREGIR ACCESO
            for servicio in servicios_clave:
                if servicio in mensaje_texto and servicio not in servicios_mencionados:
                    servicios_mencionados.append(servicio) 
        
        if servicios_mencionados:
            contexto += f"📋 *Servicios mencionados:* {', '.join(servicios_mencionados)}\n"
        
        # Extraer información específica del último mensaje, lo que significa que es reciente, si no es reciente, no tiene sentido
        ultimo_mensaje = mensajes[0]['mensaje'] or "" if mensajes else ""  # 🔥 CORREGIR ACCESO
        if len(ultimo_mensaje) > 15: 
            contexto += f"💬 *Último mensaje:* {ultimo_mensaje[:150]}{'...' if len(ultimo_mensaje) > 150 else ''}\n"
        
        # Intentar detectar urgencia o tipo de consulta
        palabras_urgentes = ['urgente', 'rápido', 'inmediato', 'pronto', 'ya']
        if any(palabra in ultimo_mensaje.lower() for palabra in palabras_urgentes):
            contexto += "🚨 *Tono:* Urgente\n"
        
        return contexto if contexto else "No se detectó contexto relevante."
        
    except Exception as e:
        app.logger.error(f"Error obteniendo contexto: {e}")
        return "Error al obtener contexto"

# ——— Inicialización al arrancar la aplicación ———
with app.app_context():
    # Crear tablas Kanban para todos los tenants
    inicializar_kanban_multitenant()
    
    # Verificar tablas en todas las bases de datos
    app.logger.info("🔍 Verificando tablas en todas las bases de datos...")
    for nombre, config in NUMEROS_CONFIG.items():
        verificar_tablas_bd(config)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5000, help='Puerto para ejecutar la aplicación')# Puerto para ejecutar la aplicación puede ser
    args = parser.parse_args()
    app.run(host='0.0.0.0', port=args.port)