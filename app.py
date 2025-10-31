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
import math
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
from flask import url_for
from urllib.parse import urlparse
import threading


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
GOOD_MORNING_THREAD_STARTED = False
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
    },
    '1011': {  # Número de Ofitodo - CORREGIDO
        'phone_number_id': os.getenv("MAINDSTEEL_PHONE_NUMBER_ID"),  # ← Cambiado
        'whatsapp_token': os.getenv("MAINDSTEEL_WHATSAPP_TOKEN"),    # ← Cambiado
        'db_host': os.getenv("MAINDSTEEL_DB_HOST"),                  # ← Cambiado
        'db_user': os.getenv("MAINDSTEEL_DB_USER"),                  # ← Cambiado
        'db_password': os.getenv("MAINDSTEEL_DB_PASSWORD"),          # ← Cambiado
        'db_name': os.getenv("MAINDSTEEL_DB_NAME"),                  # ← Cambiado
        'dominio': 'maindsteel.mektia.com'
    },
    '1012': {  # Número de Ofitodo - CORREGIDO
        'phone_number_id': os.getenv("DRASGO_PHONE_NUMBER_ID"),  # ← Cambiado
        'whatsapp_token': os.getenv("DRASGO_WHATSAPP_TOKEN"),    # ← Cambiado
        'db_host': os.getenv("DRASCO_DB_HOST"),                  # ← Cambiado
        'db_user': os.getenv("DRASGO_DB_USER"),                  # ← Cambiado
        'db_password': os.getenv("DRASGO_DB_PASSWORD"),          # ← Cambiado
        'db_name': os.getenv("DRASGO_DB_NAME"),                  # ← Cambiado
        'dominio': 'drasgo.mektia.com'
    },
    '1013': {  # Número de Ofitodo - CORREGIDO
        'phone_number_id': os.getenv("LACSE_PHONE_NUMBER_ID"),  # ← Cambiado
        'whatsapp_token': os.getenv("LACSE_WHATSAPP_TOKEN"),    # ← Cambiado
        'db_host': os.getenv("LACSE_DB_HOST"),                  # ← Cambiado
        'db_user': os.getenv("LACSE_DB_USER"),                  # ← Cambiado
        'db_password': os.getenv("LACSE_DB_PASSWORD"),          # ← Cambiado
        'db_name': os.getenv("LACSE_DB_NAME"),                  # ← Cambiado
        'dominio': 'lacse.mektia.com'
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

DEFAULT_CONFIG = NUMEROS_CONFIG['524495486142']
WHATSAPP_TOKEN = DEFAULT_CONFIG['whatsapp_token']
DB_HOST = DEFAULT_CONFIG['db_host']
DB_USER = DEFAULT_CONFIG['db_user']
DB_PASSWORD = DEFAULT_CONFIG['db_password']
DB_NAME = DEFAULT_CONFIG['db_name']
MI_NUMERO_BOT = DEFAULT_CONFIG['phone_number_id']
PHONE_NUMBER_ID = MI_NUMERO_BOT

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
from whatsapp import (
    obtener_archivo_whatsapp,
    obtener_imagen_whatsapp,
    obtener_audio_whatsapp,
    transcribir_audio_con_openai,
    convertir_audio,
    texto_a_voz,
    enviar_mensaje,
    enviar_imagen,
    enviar_documento,
    enviar_mensaje_voz
)
from files import (extraer_texto_pdf,
extraer_texto_e_imagenes_pdf, extraer_texto_excel,
extraer_texto_csv,
extraer_texto_docx,
extraer_texto_archivo,
extraer_imagenes_embedded_excel,
_extraer_imagenes_desde_zip_xlsx,
get_docs_dir_for_config,
get_productos_dir_for_config, 
determinar_extension
)
ALLOWED_EXTENSIONS = {
    'pdf', 'txt', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg',  # Documentos e imágenes
    'mp4', 'mov', 'webm', 'avi', 'mkv', 'ogg', 'mpeg',     # Videos
    'xlsx', 'xls', 'csv', 'docx'                          # Office y documentos
}
PREFIJOS_PAIS = {
    '52': 'mx', '1': 'us', '54': 'ar', '57': 'co', '55': 'br',
    '34': 'es', '51': 'pe', '56': 'cl', '58': 've', '593': 'ec',
    '591': 'bo', '507': 'pa', '502': 'gt'
}
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

        # If the value contains a path (e.g. "productos/tenant/filename.jpg" or "uploads/productos/tenant/filename.jpg"),
        # use the basename because serve_product_image expects filename (it will search tenant dirs and fallbacks).
        from os.path import basename
        fname = basename(imagen_url)

        # If after basename we have nothing, fallback to original value
        if not fname:
            return imagen_url

        # Build URL to the dedicated product-image serving route
        return url_for('serve_product_image', filename=fname)
    except Exception:
        # Last resort: try to serve from uploads root, or return original
        try:
            return url_for('serve_uploaded_file', filename=imagen_url)
        except Exception:
            return imagen_url

app.add_template_filter(public_image_url, 'public_img')

def get_clientes_conn():
    return mysql.connector.connect(
        host=os.getenv("CLIENTES_DB_HOST"),
        user=os.getenv("CLIENTES_DB_USER"),
        password=os.getenv("CLIENTES_DB_PASSWORD"),
        database=os.getenv("CLIENTES_DB_NAME")
    )

def _find_cliente_in_clientes_by_domain(dominio):
    """Helper: try heuristics to find cliente row in CLIENTES_DB by domain/subdomain."""
    try:
        if not dominio:
            return None
        candidates = [
            dominio,
            dominio.split('.')[0] if '.' in dominio else dominio,
            dominio.replace('.', '_')
        ]
        conn = get_clientes_conn()
        cur = conn.cursor(dictionary=True)
        for c in candidates:
            try:
                cur.execute("""
                    SELECT id_cliente, telefono, entorno, shema, servicio, `user`, password
                    FROM cliente
                    WHERE shema = %s OR entorno = %s OR servicio = %s OR `user` = %s
                    LIMIT 1
                """, (c, c, c, c))
                row = cur.fetchone()
                if row:
                    cur.close(); conn.close()
                    return row
            except Exception:
                continue
        cur.close(); conn.close()
    except Exception as e:
        app.logger.warning(f"⚠️ _find_cliente_in_clientes_by_domain error: {e}")
    return None

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
        try:
            au = session.get('auth_user') or {}
            expected_schema = (au.get('schema') or au.get('shema') or '').strip().lower()
            host = (request.headers.get('Host') or '').lower()
            if expected_schema and expected_schema not in host:
                # Sesión válida pero dominio no autorizado -> cerrar sesión y forzar login
                app.logger.warning(f"🔒 Acceso denegado: usuario '{au.get('user')}' con schema='{expected_schema}' intentó acceder desde host='{host}'")
                session.pop('auth_user', None)
                flash('⚠️ Acceso denegado: este usuario no puede acceder desde este dominio', 'error')
                return redirect(url_for('login', next=request.path))
        except Exception as e:
            app.logger.error(f"🔴 Error validando schema en proteger_rutas: {e}")
        # Si pasa la comprobación, permitir
        return

    # Si llega aquí, no está autorizado -> redirigir al login
    app.logger.info(f"🔒 proteger_rutas: redirect to login for path={request.path} endpoint={request.endpoint}")
    return redirect(url_for('login', next=request.path))

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

@app.before_request
def _heartbeat_sesion_activa():
    try:
        au = session.get('auth_user')
        if au and au.get('user'):
            actualizar_sesion_activa(au['user'])
    except Exception as e:
        app.logger.debug(f"Heartbeat sesión falló: {e}")

@app.route('/admin/sesiones/<username>')
@login_required
def admin_sesiones_username(username):
    count = contar_sesiones_activas(username, within_minutes=30)
    return jsonify({'username': username, 'activos_ultimos_30_min': count})

@app.route('/admin/asignar-plan-dominio', methods=['POST'])
@login_required
def admin_asignar_plan_dominio():
    """
    Admin endpoint to assign a plan to a domain.
    JSON body: { "domain": "laporfirianna.mektia.com", "plan_id": 2 }
    Requires authenticated user with servicio == 'admin'.
    """
    try:
        au = session.get('auth_user') or {}
        if str(au.get('servicio') or '').strip().lower() != 'admin':
            return jsonify({'error': 'Forbidden'}), 403

        data = request.get_json(silent=True) or {}
        domain = (data.get('domain') or '').strip()
        plan_id = data.get('plan_id')
        if not domain or not plan_id:
            return jsonify({'error': 'domain and plan_id required'}), 400

        conn = get_clientes_conn()
        cur = conn.cursor()
        try:
            # Fetch mensajes_incluidos from planes if available
            mensajes = 0
            try:
                cur_pl = conn.cursor(dictionary=True)
                cur_pl.execute("SELECT mensajes_incluidos FROM planes WHERE plan_id = %s LIMIT 1", (plan_id,))
                pr = cur_pl.fetchone()
                if pr and pr.get('mensajes_incluidos') is not None:
                    mensajes = int(pr['mensajes_incluidos'])
                cur_pl.close()
            except Exception:
                pass

            # Upsert domain_plans
            cur.execute("""
                INSERT INTO domain_plans (dominio, plan_id, mensajes_incluidos)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE plan_id = VALUES(plan_id), mensajes_incluidos = VALUES(mensajes_incluidos), updated_at = NOW()
            """, (domain, plan_id, mensajes))
            conn.commit()
        finally:
            cur.close(); conn.close()

        # Try to propagate to cliente row if exists (best-effort)
        propagated = False
        try:
            ok = asignar_plan_a_cliente_por_user(domain, plan_id)
            propagated = bool(ok)
        except Exception:
            propagated = False

        return jsonify({'success': True, 'domain': domain, 'plan_id': plan_id, 'propagated_to_cliente': propagated})
    except Exception as e:
        app.logger.error(f"🔴 admin_asignar_plan_dominio error: {e}")
        return jsonify({'error': str(e)}), 500


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
        'calendar_email': request.form.get('calendar_email'),  # Nuevo campo para correo de notificaciones
        'transferencia_numero': request.form.get('transferencia_numero'),
        'transferencia_nombre': request.form.get('transferencia_nombre'),
        'transferencia_banco': request.form.get('transferencia_banco')
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
    
    # Verificar/crear columnas necesarias (calendar_email + transferencias)
    try:
        required_cols = {
            'calendar_email': "ALTER TABLE configuracion ADD COLUMN calendar_email VARCHAR(255)",
            'transferencia_numero': "ALTER TABLE configuracion ADD COLUMN transferencia_numero VARCHAR(100)",
            'transferencia_nombre': "ALTER TABLE configuracion ADD COLUMN transferencia_nombre VARCHAR(200)",
            'transferencia_banco': "ALTER TABLE configuracion ADD COLUMN transferencia_banco VARCHAR(100)"
        }
        for col, alter_sql in required_cols.items():
            try:
                cursor.execute(f"SHOW COLUMNS FROM configuracion LIKE '{col}'")
                if cursor.fetchone() is None:
                    # Crear la columna si no existe
                    cursor.execute(alter_sql)
                    app.logger.info(f"🔧 Columna creada en configuracion: {col}")
            except Exception as e:
                # Si la tabla no existe todavía u otro error, loguear y continuar
                app.logger.warning(f"⚠️ No se pudo asegurar columna '{col}': {e}")
        conn.commit()
    except Exception as e:
        app.logger.warning(f"⚠️ Error asegurando columnas extra en configuracion: {e}")
        try:
            conn.rollback()
        except:
            pass

    # Verificar si existe una configuración
    try:
        cursor.execute("SELECT COUNT(*) FROM configuracion")
        count = cursor.fetchone()[0]
    except Exception as e:
        app.logger.error(f"🔴 Error consultando configuracion: {e}")
        cursor.close(); conn.close()
        flash("❌ Error interno verificando configuración", "error")
        return redirect(url_for('configuracion_tab', tab='negocio'))

    if count > 0:
        # Actualizar configuración existente
        set_parts = []
        values = []
        
        for key, value in datos.items():
            if value is not None:  # Solo incluir campos con valores (incluye cadena vacía explícita)
                set_parts.append(f"{key} = %s")
                values.append(value)
        
        if set_parts:
            sql = f"UPDATE configuracion SET {', '.join(set_parts)} WHERE id = 1"
            try:
                cursor.execute(sql, values)
            except Exception as e:
                app.logger.error(f"Error al actualizar configuración: {e}")
                # Filtrar columnas que causan problemas
                if "Unknown column" in str(e) or "column" in str(e).lower():
                    try:
                        cursor.execute("SHOW COLUMNS FROM configuracion")
                        columnas_existentes = [col[0] for col in cursor.fetchall()]
                        set_parts = []
                        values = []
                        for key, value in datos.items():
                            if key in columnas_existentes and value is not None:
                                set_parts.append(f"{key} = %s")
                                values.append(value)
                        if set_parts:
                            sql = f"UPDATE configuracion SET {', '.join(set_parts)} WHERE id = 1"
                            cursor.execute(sql, values)
                            conn.commit()
                    except Exception as e2:
                        app.logger.error(f"🔴 Reintento update falló: {e2}")
                else:
                    app.logger.error(f"🔴 Error inesperado en UPDATE configuracion: {e}")
        else:
            app.logger.info("ℹ️ No hay campos nuevos para actualizar en configuracion")
    else:
        # Insertar nueva configuración
        fields = ', '.join(datos.keys())
        placeholders = ', '.join(['%s'] * len(datos))
        sql = f"INSERT INTO configuracion (id, {fields}) VALUES (1, {placeholders})"
        try:
            cursor.execute(sql, [1] + list(datos.values()))
        except Exception as e:
            app.logger.error(f"🔴 Error insertando configuración nueva: {e}")
            # Intentar crear tabla mínima por compatibilidad básica
            try:
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS configuracion (
                        id INT PRIMARY KEY DEFAULT 1
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
                """)
                conn.commit()
                cursor.execute(sql, [1] + list(datos.values()))
            except Exception as e2:
                app.logger.error(f"🔴 Falló intento de reparación al insertar configuracion: {e2}")
    
    try:
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except:
            pass
    finally:
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
            filepath = os.path.join(UPLOAD_FOLDER, filename)
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
            'proveedor': 'proveedor',
            'inscripcion': 'inscripcion',
            'mensualidad': 'mensualidad'
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

        # Ensure subscription columns exist before attempting inserts that reference them
        try:
            _ensure_precios_subscription_columns(config)
        except Exception as e:
            app.logger.warning(f"⚠️ _ensure_precios_subscription_columns execution failed: {e}")

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
            'imagen', 'status_ws', 'catalogo', 'catalogo2', 'catalogo3', 'proveedor','inscripcion', 'mensualidad'
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

                for campo in ['costo', 'precio_mayoreo', 'precio_menudeo','inscripcion','mensualidad']:
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
                    producto.get('proveedor', ''),
                    producto.get('inscripcion', '0.00'),
                    producto.get('mensualidad', '0.00')
                ]

                cursor.execute("""
                    INSERT INTO precios (
                        sku, categoria, subcategoria, linea, modelo,
                        descripcion, medidas, costo, precio_mayoreo, precio_menudeo,
                        imagen, status_ws, catalogo, catalogo2, catalogo3, proveedor, inscripcion, mensualidad
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                        categoria=VALUES(categoria),
                        subcategoria=VALUES(subcategoria),
                        descripcion=VALUES(descripcion),
                        costo=VALUES(costo),
                        precio_mayoreo=VALUES(precio_mayoreo),
                        precio_menudeo=VALUES(precio_menudeo),
                        status_ws=VALUES(status_ws),
                        imagen=VALUES(imagen),
                        inscripcion=VALUES(inscripcion),
                        mensualidad=VALUES(mensualidad)
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

def analizar_pdf_servicios(texto_pdf, config=None):
    """Usa IA para analizar el PDF y extraer servicios y precios - VERSIÓN MEJORADA"""
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        # Limitar el texto para evitar tokens excesivos
        texto_limitado = texto_pdf[:150000]  # Mantenemos un límite razonable
        
        app.logger.info(f"📊 Texto a analizar: {len(texto_limitado)} caracteres")
        
        # Determinar el tipo de negocio para el prompt
        es_porfirianna = 'laporfirianna' in config.get('dominio', '')
        
        # PROMPT MÁS ESTRICTO Y OPTIMIZADO - con menos caracteres para evitar errores
        if es_porfirianna:
            prompt = f"""Extrae los productos del siguiente texto como JSON:
{texto_limitado[:150000]}
Formato: {{"servicios":[{{"sku":"TRAVIS OHE-295negro","categoria":"COMIDA","descripcion":"DESC","precio":"100.00","precio_mayoreo":"90.00","precio_menudeo":"100.00","costo":"70.00","moneda":"MXN","imagen":"","status_ws":"activo","catalogo":"La Porfirianna"}}]}}
"""
        else:
            prompt = f"""Extrae los servicios del siguiente texto como JSON:
{texto_limitado[:150000]}
Formato: {{"servicios":[{{"sku":"TRAVIS OHE-295negro","categoria":"CATEGORIA","descripcion":"DESC","precio":"5000.00","precio_mayoreo":"90.00","precio_menudeo":"100.00","costo":"3500.00","moneda":"MXN","imagen":"","status_ws":"activo","catalogo":"Mektia"}}]}}
"""
        
        headers = {
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        }
        
        # Payload simplificado para evitar errores
        payload = {
            "model": "deepseek-chat",
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 8192
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
        if 'productos' in servicios_extraidos and isinstance(servicios_extraidos['productos'], list):

            app.logger.info(f"✅ JSON válido: {len(servicios_extraidos['productos'])} servicios")
                
            # Limpiar y validar servicios
            servicios_limpios = []
            for servicio in servicios_extraidos['productos']:
                servicio_limpio = validar_y_limpiar_servicio(servicio)
                if servicio_limpio:
                    servicios_limpios.append(servicio_limpio)
                
            servicios_extraidos['productos'] = servicios_limpios
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
    """Valida y limpia los datos de un servicio individual - VERSIÓN ROBUSTA (fix KeyError 'servicio')."""
    try:
        if not isinstance(servicio, dict):
            app.logger.warning("⚠️ Servicio no es diccionario, omitiendo")
            return None

        servicio_limpio = {}

        # Asegurar nombre del servicio (campo obligatorio)
        nombre = servicio.get('servicio') or servicio.get('modelo') or servicio.get('sku') or ''
        nombre = str(nombre).strip() if nombre is not None else ''
        if not nombre:
            app.logger.warning("⚠️ Servicio sin nombre, omitiendo")
            return None
        servicio_limpio['servicio'] = nombre

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
            servicio_limpio[campo] = str(valor).strip() if valor not in (None, '') else valor_default

        # Campos de precio - conversión robusta
        campos_precio = ['precio_mayoreo', 'precio_menudeo', 'costo']
        for campo in campos_precio:
            valor = servicio.get(campo, '0.00')
            precio_limpio = "0.00"
            try:
                if valor not in (None, ''):
                    valor_limpio = re.sub(r'[^\d.]', '', str(valor))
                    if valor_limpio:
                        precio_float = float(valor_limpio)
                        precio_limpio = f"{precio_float:.2f}"
            except (ValueError, TypeError):
                precio_limpio = "0.00"
            servicio_limpio[campo] = precio_limpio

        app.logger.info(f"✅ Servicio validado: {servicio_limpio.get('servicio')}")
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
                    servicio.get('proveedor', '').strip()
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
            filepath = os.path.join(UPLOAD_FOLDER, filename)
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
                # Log detallado (defensivo: evitar excepciones por keys faltantes en la respuesta IA)
                try:
                    app.logger.info("📊 Resumen de servicios extraídos:")
                    svc_list = servicios.get('servicios') if isinstance(servicios, dict) else None
                    if svc_list and isinstance(svc_list, list):
                        for s in svc_list[:10]:
                            try:
                                nombre = (s.get('servicio') or s.get('modelo') or s.get('sku') or '')[:120] if isinstance(s, dict) else str(s)[:120]
                                # precio puede estar en varias claves; preferir precio_menudeo/precio_mayoreo/costo
                                precio = None
                                if isinstance(s, dict):
                                    precio = s.get('precio_menudeo') or s.get('precio') or s.get('precio_mayoreo') or s.get('costo')
                                precio_str = f"${float(re.sub(r'[^\d.]','',str(precio))):,.2f}" if precio not in (None, '') else ""
                                imagen_present = bool(s.get('imagen')) if isinstance(s, dict) else False
                                app.logger.info(f"   - {nombre}{(' - ' + precio_str) if precio_str else ''} - Imagen: {imagen_present}")
                            except Exception as _inner_e:
                                app.logger.warning(f"⚠️ Error procesando entrada de servicio para logging: {_inner_e}")
                        if len(svc_list) > 10:
                            app.logger.info(f"   ... y {len(svc_list) - 10} más")
                    else:
                        app.logger.info("   (No hay lista de servicios estructurada para mostrar)")
                except Exception as e:
                    app.logger.warning(f"⚠️ Error logging servicios summary: {e}")
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

    # Quick safety guard: refuse absurdly large payloads (prevents abuse / extreme DB writes)
    MAX_ICON_PAYLOAD = int(os.getenv("MAX_ICON_PAYLOAD", "20000"))  # characters
    if len(icono) > MAX_ICON_PAYLOAD:
        app.logger.warning(f"⚠️ Icon payload too large ({len(icono)} chars) for columna_id={columna_id}; max allowed {MAX_ICON_PAYLOAD}")
        return jsonify({'error': 'Icon payload too large'}), 413

    conn = get_db_connection(config)
    cursor = conn.cursor()
    try:
        # Ensure the column exists and supports large values (defensive check)
        try:
            cursor.execute("SHOW COLUMNS FROM kanban_columnas LIKE 'icono'")
            col = cursor.fetchone()
            if col:
                col_type = col[1].lower() if len(col) > 1 and col[1] else ''
                if 'text' not in col_type and 'blob' not in col_type:
                    try:
                        cursor.execute("ALTER TABLE kanban_columnas MODIFY COLUMN icono TEXT DEFAULT NULL")
                        conn.commit()
                        app.logger.info("🔧 Upgraded kanban_columnas.icono to TEXT on-the-fly")
                    except Exception:
                        app.logger.warning("⚠️ Could not ALTER kanban_columnas.icono to TEXT (insufficient privileges?)")
        except Exception:
            pass

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
                icono TEXT DEFAULT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        ''')
        # Ensure icono column exists and is TEXT (to support long data URLs)
        try:
            cursor.execute("SHOW COLUMNS FROM kanban_columnas LIKE 'icono'")
            col = cursor.fetchone()
            if col is None:
                cursor.execute("ALTER TABLE kanban_columnas ADD COLUMN icono TEXT DEFAULT NULL")
            else:
                # If the column exists but is a short VARCHAR, alter to TEXT to avoid data-too-long errors
                col_type = col[1].lower() if len(col) > 1 and col[1] else ''
                if 'varchar' in col_type and not ('text' in col_type):
                    try:
                        cursor.execute("ALTER TABLE kanban_columnas MODIFY COLUMN icono TEXT DEFAULT NULL")
                        app.logger.info("🔧 Modified kanban_columnas.icono to TEXT to support longer icon data")
                    except Exception as _:
                        # If MODIFY fails (permissions etc.), continue but warn
                        app.logger.warning("⚠️ Could not modify kanban_columnas.icono to TEXT (insufficient privileges?)")
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

def negocio_contact_block(negocio):
    """
    Formatea los datos de contacto del negocio desde la configuración.
    Si algún campo no está configurado muestra 'No disponible' (evita inventos).
    """
    if not negocio or not isinstance(negocio, dict):
        return "DATOS DEL NEGOCIO:\nDirección: No disponible\nTeléfono: No disponible\nCorreo: No disponible\n\nNota: Los datos no están configurados en el sistema."

    direccion = (negocio.get('direccion') or '').strip()
    telefono = (negocio.get('telefono') or '').strip()
    correo = (negocio.get('correo') or '').strip()

    # Normalizar teléfono para mostrar (no modificar DB)
    telefono_display = telefono or 'No disponible'
    correo_display = correo or 'No disponible'
    direccion_display = direccion or 'No disponible'
    prompt_comentario = f"""
        Te acaban de hacer una solicitud de datos, 
        no me des ningun dato, solo has un comentario agradable expresando
        que estas a su servicio, algo parecido a decir claro que si.
        """
        
    headers = {
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
        "Content-Type": "application/json"
    }
        
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt_comentario}],
        "temperature": 0.3,
        "max_tokens": 500
    }
    response = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
        
    data = response.json()
    respuestita = data['choices'][0]['message']['content'].strip()
    block = (
        f"{respuestita}\n\n"
        "📍 DATOS DEL NEGOCIO:\n\n"
        f"• Dirección: {direccion_display}\n"
        f"• Teléfono: {telefono_display}\n"
        f"• Correo: {correo_display}\n\n"
        "Visitanos pronto!"
    )
    return block

@app.route('/chat/<telefono>/messages')
def get_chat_messages(telefono):
    """Obtener mensajes de un chat específico después de cierto ID"""
    after_id = request.args.get('after', 0, type=int)
    config = obtener_configuracion_por_host()

    # Guardar y validar el parámetro recibido para evitar consultas inválidas
    if not telefono or str(telefono).lower() in ('none', 'null', ''):
        app.logger.warning(f"⚠️ get_chat_messages llamado con telefono inválido: {telefono}")
        return jsonify({'messages': [], 'timestamp': int(time.time() * 1000)})

    conn = get_db_connection(config)
    cursor = conn.cursor(dictionary=True)

    # Consultar solo mensajes más recientes que el ID proporcionado
    # Usar la columna correcta 'numero' y ordenar por 'timestamp'
    cursor.execute("""
        SELECT id, mensaje AS content, timestamp, respuesta
        FROM conversaciones 
        WHERE numero = %s AND id > %s
        ORDER BY timestamp ASC
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
    """Crea un evento en Google Calendar; intenta crear el evento directamente en el calendar_email
    si está configurado y, si falla por permisos, hace fallback al calendario 'primary' y añade
    calendar_email como invitado. Usa sendUpdates='all' para notificar asistentes."""
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
        
        # Detalles del servicio
        detalles_servicio = cita_info.get('detalles_servicio', {})
        descripcion_servicio = detalles_servicio.get('descripcion', 'No hay descripción disponible')
        categoria_servicio = detalles_servicio.get('categoria', 'Sin categoría')
        precio_servicio = detalles_servicio.get('precio_menudeo') or detalles_servicio.get('precio', 'No especificado')
        
        event_title = f"{'Pedido' if es_porfirianna else 'Cita'}: {cita_info.get('servicio_solicitado', 'Servicio')} - {cita_info.get('nombre_cliente', 'Cliente')}"
        
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
                    {'method': 'email', 'minutes': 24 * 60},
                ],
            },
            'colorId': '4' if es_porfirianna else '1',
        }
        
        # Leer calendar_email desde la BD
        app.logger.info(f"📧 Intentando obtener calendar_email de la base de datos")
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT calendar_email FROM configuracion WHERE id = 1")
        result = cursor.fetchone()
        cursor.close()
        conn.close()
        
        calendar_email = None
        if result and result.get('calendar_email'):
            calendar_email = result['calendar_email'].strip()
        
        primary_calendar = os.getenv('GOOGLE_CALENDAR_ID', 'primary')
        
        # Si calendar_email está configurado, intentamos crear directamente en ese calendario primero
        attempted_calendar = calendar_email if calendar_email else primary_calendar
        
        try:
            app.logger.info(f"🌐 Intentando crear evento en calendarId='{attempted_calendar}' (sendUpdates=all)")
            created = service.events().insert(calendarId=attempted_calendar, body=event, sendUpdates='all').execute()
            app.logger.info(f'Evento creado en {attempted_calendar}: {created.get("htmlLink")}')
            return created.get('id')
        except HttpError as he:
            # Permisos o calendario no encontrado -> fallback
            app.logger.warning(f"⚠️ No se pudo crear evento en calendarId='{attempted_calendar}': {he}")
            # Si intentamos en calendar_email y falló, fallback a primary y añadir calendar_email como attendee (si existe)
            if attempted_calendar != primary_calendar:
                if calendar_email:
                    event['attendees'] = [{'email': calendar_email}]
                try:
                    app.logger.info(f"🔁 Intentando crear evento en calendarId='{primary_calendar}' y añadir attendees (sendUpdates=all)")
                    created = service.events().insert(calendarId=primary_calendar, body=event, sendUpdates='all').execute()
                    app.logger.info(f'Evento creado en {primary_calendar}: {created.get("htmlLink")} (attendees: {calendar_email})')
                    return created.get('id')
                except Exception as e2:
                    app.logger.error(f'🔴 Fallback a primary falló: {e2}')
                    return None
            else:
                app.logger.error("🔴 Error creando evento y no hay fallback disponible")
                return None
        except Exception as e:
            app.logger.error(f'🔴 Error inesperado creando evento: {e}')
            return None
        
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
    
    # El nombre ahora es obligatorio
    if not info_cita.get('nombre_cliente') or info_cita.get('nombre_cliente') == 'null':
        datos_faltantes.append("nombre")
    
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
    mensaje_lower = (mensaje or "").lower()
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
            
            # NORMALIZACIÓN ADICIONAL: si el mensaje original contiene palabras relativas, forzarlas
            fecha_rel = extraer_fecha_del_mensaje(mensaje_lower)
            if fecha_rel:
                app.logger.info(f"🔁 Overriding IA fecha_sugerida con fecha relativa extraída del mensaje: {fecha_rel}")
                info_cita['fecha_sugerida'] = fecha_rel
            
            # Procesar fechas relativas ya reconocidas por la IA (hoy/mañana)
            if info_cita.get('fecha_sugerida'):
                fs = str(info_cita['fecha_sugerida']).strip().lower()
                if fs in ['hoy', 'today']:
                    info_cita['fecha_sugerida'] = datetime.now().strftime('%Y-%m-%d')
                elif fs in ['mañana', 'manana', 'tomorrow']:
                    info_cita['fecha_sugerida'] = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
                elif fs in ['pasado mañana', 'pasadomanana']:
                    info_cita['fecha_sugerida'] = (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d')
            
            # Si IA no dio hora y el texto contiene una hora, extraerla
            if not info_cita.get('hora_sugerida'):
                hora_extraida = extraer_hora_del_mensaje(mensaje_lower)
                if hora_extraida:
                    app.logger.info(f"🔁 Hora extraída del mensaje y añadida: {hora_extraida}")
                    info_cita['hora_sugerida'] = hora_extraida
            
            # Añadir teléfono si no viene
            if not info_cita.get('telefono'):
                info_cita['telefono'] = numero
            
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

@app.route('/debug-domain-plan')
def debug_domain_plan():
    try:
        domain = request.args.get('domain') or request.host.split(':')[0]
        # show which CLIENTES_DB connection will be used
        db_name = os.getenv('CLIENTES_DB_NAME')
        dp = get_plan_for_domain(domain)
        return jsonify({
            'domain_checked': domain,
            'env_clientes_db': db_name,
            'domain_plan_row': dp
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

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

SUBTABS = ['negocio', 'personalizacion', 'precios', 'restricciones', 'asesores']
app.add_template_filter(get_country_flag, 'bandera')

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

        # Convertir timestamps a ISO strings en zona tz_mx para JSON
        for chat in chats:
            if chat.get('ultima_fecha'):
                try:
                    if chat['ultima_fecha'].tzinfo is None:
                        chat['ultima_fecha'] = pytz.utc.localize(chat['ultima_fecha']).astimezone(tz_mx).isoformat()
                    else:
                        chat['ultima_fecha'] = chat['ultima_fecha'].astimezone(tz_mx).isoformat()
                except Exception:
                    # Fallback: intentar str() si algo raro ocurre
                    try:
                        chat['ultima_fecha'] = str(chat['ultima_fecha'])
                    except:
                        chat['ultima_fecha'] = None

        cursor.close()
        conn.close()

        return jsonify({
            'columnas': columnas,
            'chats': chats,
            # Use milliseconds epoch so clients that compare with Date.now() work reliably
            'timestamp': int(time.time() * 1000),
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

def eliminar_asesores_extras(config=None, allowed_count=2):
    """
    Actualmente deshabilitado por defecto: evita recortar automáticamente la lista de asesores
    para que no se borren/NULLifiquen columnas en la tabla configuracion.
    Para re-habilitar el recorte automático pon la variable de entorno ENABLE_TRIM_ASESORES=true
    y reinicia la aplicación.

    Si ENABLE_TRIM_ASESORES == 'true' entonces se ejecuta la lógica original (fallbacks y NULL legacy cols).
    """
    # Guard por defecto: NO recortar asesores a menos que se habilite explícitamente
    if os.getenv("ENABLE_TRIM_ASESORES", "false").lower() != "true":
        try:
            cfg = config or obtener_configuracion_por_host()
            app.logger.info(f"ℹ️ eliminar_asesores_extras SKIPPED (env ENABLE_TRIM_ASESORES != 'true') for {cfg.get('dominio') if isinstance(cfg, dict) else cfg}")
        except Exception:
            app.logger.info("ℹ️ eliminar_asesores_extras SKIPPED (env ENABLE_TRIM_ASESORES != 'true')")
        return

    # --- Si se habilita, ejecutar la lógica existente (mantengo la implementación previa) ---
    if config is None:
        config = obtener_configuracion_por_host()
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)

        # Leer row actual
        cursor.execute("SELECT asesores_json FROM configuracion WHERE id = 1 LIMIT 1")
        row = cursor.fetchone()
        if not row:
            cursor.close(); conn.close()
            return

        asesores_json = row.get('asesores_json') or ''
        changed = False

        # 1) Trim JSON list if needed
        if asesores_json:
            try:
                parsed = json.loads(asesores_json)
                if isinstance(parsed, list) and len(parsed) > allowed_count:
                    trimmed = parsed[:allowed_count]
                    cursor.execute("UPDATE configuracion SET asesores_json = %s WHERE id = 1", (json.dumps(trimmed, ensure_ascii=False),))
                    conn.commit()
                    app.logger.info(f"🔧 asesores_json recortado de {len(parsed)} a {allowed_count}")
                    changed = True
            except Exception as e:
                app.logger.warning(f"⚠️ eliminar_asesores_extras: no se pudo parsear asesores_json: {e}")

        # 2) Nullificar columnas legacy que queden fuera del límite (comprobar qué columnas existen)
        try:
            cursor.execute("SHOW COLUMNS FROM configuracion")
            existing = [r[0] for r in cursor.fetchall()]
        except Exception:
            existing = []

        cols_to_null = []
        # consider up to 20 possible legacy columns (safe upper bound)
        for i in range(1, 21):
            if i > allowed_count:
                name_col = f"asesor{i}_nombre"
                phone_col = f"asesor{i}_telefono"
                email_col = f"asesor{i}_email"
                if name_col in existing:
                    cols_to_null.append(f"{name_col} = NULL")
                if phone_col in existing:
                    cols_to_null.append(f"{phone_col} = NULL")
                if email_col in existing:
                    cols_to_null.append(f"{email_col} = NULL")

        if cols_to_null:
            try:
                sql = f"UPDATE configuracion SET {', '.join(cols_to_null)} WHERE id = 1"
                cursor.execute(sql)
                conn.commit()
                app.logger.info(f"🔧 Columnas legacy de asesores > {allowed_count} puestas a NULL")
                changed = True
            except Exception as e:
                app.logger.warning(f"⚠️ eliminar_asesores_extras: no se pudieron nullificar columnas legacy: {e}")

        cursor.close(); conn.close()
        if not changed:
            app.logger.debug("ℹ️ eliminar_asesores_extras: no se aplicó ningún cambio (no había asesores extras)")
    except Exception as e:
        app.logger.error(f"🔴 eliminar_asesores_extras error: {e}")

def obtener_max_asesores_from_planes(default=2, cap=10):
    """
    Lee la tabla `planes` en la BD de clientes y retorna el máximo valor de la columna `asesores`.
    Si falla, devuelve `default`. Se aplica un cap (por seguridad).
    """
    try:
        conn = get_clientes_conn()
        cur = conn.cursor()
        cur.execute("SELECT MAX(asesores) FROM planes")
        row = cur.fetchone()
        cur.close(); conn.close()
        if row and row[0] is not None:
            n = int(row[0])
            if n < 1:
                return default
            return min(n, cap)
    except Exception as e:
        app.logger.warning(f"⚠️ obtener_max_asesores_from_planes falló: {e}")
    return default

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
    """Guarda la cita en la base de datos, la agenda en Google Calendar y registra en notificaciones_ia.
    Only persists a real cita when required fields are complete (validated by validar_datos_cita_completos).
    If data are incomplete, stores a provisional state in estados_conversacion for follow-up and returns None.
    """
    if config is None:
        config = obtener_configuracion_por_host()

    try:
        # Normalize phone fallback keys
        telefono = info_cita.get('telefono') or info_cita.get('numero_cliente')

        # 1) Validate completeness BEFORE attempting to save
        try:
            completos, faltantes = validar_datos_cita_completos(info_cita, config)
        except Exception as e:
            app.logger.warning(f"⚠️ validar_datos_cita_completos falló: {e}")
            completos, faltantes = False, ['validacion_error']

        if not completos:
            # Do NOT create a real cita when data are incomplete.
            app.logger.info(f"⚠️ Cita NO guardada (datos incompletos) para {telefono}. Faltantes: {faltantes}")

            # Persist provisional info in estados_conversacion so the conversation flow can continue
            provisional = {
                'pedido_provisional': info_cita,
                'faltantes': faltantes,
                'timestamp': datetime.now().isoformat()
            }
            try:
                actualizar_estado_conversacion(telefono, "OFRECIENDO_ASESOR", "pedido_provisional", provisional, config)
                app.logger.info(f"🔁 Estado provisional guardado en estados_conversacion para {telefono}")
            except Exception as e:
                app.logger.warning(f"⚠️ No se pudo guardar estado provisional para {telefono}: {e}")

            return None

        # 2) Prevent rapid duplicates: only check when phone + servicio are present
        conn = get_db_connection(config)
        cursor = conn.cursor()
        try:
            svc = (info_cita.get('servicio_solicitado') or '').strip()
            if telefono and svc:
                cursor.execute('''
                    SELECT id FROM citas
                    WHERE numero_cliente = %s
                      AND servicio_solicitado = %s
                      AND fecha_creacion > NOW() - INTERVAL 5 MINUTE
                ''', (telefono, svc))
                existing_cita = cursor.fetchone()
            else:
                existing_cita = None
        except Exception as e:
            app.logger.warning(f"⚠️ Error comprobando duplicados en citas: {e}")
            existing_cita = None

        if existing_cita:
            try:
                cid = existing_cita[0]
            except Exception:
                cid = existing_cita
            app.logger.info(f"⚠️ Cita similar ya existe (ID: {cid}), evitando duplicado")
            try:
                cursor.close()
                conn.close()
            except:
                pass
            return cid  # return existing id

        # 3) Create notificaciones_ia table if needed (kept as before)
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

        # 4) Insert into citas (only when validated as complete)
        cursor.execute('''
            INSERT INTO citas (
                numero_cliente, servicio_solicitado, fecha_propuesta,
                hora_propuesta, nombre_cliente, telefono, estado
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (
            telefono,
            info_cita.get('servicio_solicitado'),
            info_cita.get('fecha_sugerida'),
            info_cita.get('hora_sugerida'),
            info_cita.get('nombre_cliente'),
            telefono,
            'pendiente'
        ))

        conn.commit()
        cita_id = cursor.lastrowid

        # 5) Google Calendar scheduling (enhanced: also try to schedule in advisor's calendar/email)
        evento_id = None
        debe_agendar = False

        if info_cita.get('fecha_sugerida'):
                try:
                    fecha_raw = info_cita.get('fecha_sugerida')
                    fecha_cita = None
                    # intentar parse robusto con dateutil (acepta 'YYYY-MM-DD', '2025-10-24T..', etc.)
                    try:
                        from dateutil import parser as _parser
                        if isinstance(fecha_raw, datetime):
                            fecha_cita = fecha_raw.date()
                        else:
                            # default con timezone México para evitar desfases
                            parsed = _parser.parse(str(fecha_raw), default=datetime.now(tz_mx))
                            fecha_cita = parsed.date()
                    except Exception:
                        # fallback: si viene en formato YYYY-MM-DD simple
                        try:
                            fecha_cita = datetime.strptime(str(fecha_raw), '%Y-%m-%d').date()
                        except Exception:
                            fecha_cita = None

                    if fecha_cita:
                        # usar fecha actual en zona tz_mx para comparación correcta
                        fecha_actual = datetime.now(tz_mx).date()
                        diff_days = (fecha_cita - fecha_actual).days
                        if diff_days >= 0:
                            debe_agendar = True
                            app.logger.info(f"✅ Cita para fecha válida ({fecha_cita}), se agendará en Calendar (diff_days={diff_days})")
                        else:
                            app.logger.info(f"ℹ️ Cita para fecha pasada ({fecha_cita}), no se agendará en Calendar (diff_days={diff_days})")
                    else:
                        app.logger.info(f"ℹ️ No se pudo interpretar fecha_sugerida='{fecha_raw}' como fecha válida; no se agenda automáticamente")
                except Exception as e:
                    app.logger.error(f"Error procesando fecha: {e}")

        # If debe_agendar, attempt calendar actions
        if debe_agendar:
            service = autenticar_google_calendar(config)
            if service:
                try:
                    # Try to get advisor and their email
                    asesor = None
                    try:
                        asesor = obtener_siguiente_asesor(config)
                    except Exception as e:
                        app.logger.warning(f"⚠️ No se pudo obtener asesor para agendar: {e}")
                        asesor = None

                    asesor_email = None
                    if asesor and isinstance(asesor, dict):
                        asesor_email = (asesor.get('email') or '').strip() or None

                    # Build event body (reuse same fields as crear_evento_calendar)
                    es_porfirianna = 'laporfirianna' in config.get('dominio', '')
                    # compute start/end
                    if not es_porfirianna and info_cita.get('fecha_sugerida') and info_cita.get('hora_sugerida'):
                        start_time = f"{info_cita['fecha_sugerida']}T{info_cita['hora_sugerida']}:00"
                        try:
                            end_time_dt = datetime.strptime(f"{info_cita['fecha_sugerida']} {info_cita['hora_sugerida']}",
                                                           "%Y-%m-%d %H:%M") + timedelta(hours=1)
                            end_time = end_time_dt.strftime("%Y-%m-%dT%H:%M:00")
                        except Exception:
                            end_time = (datetime.now() + timedelta(hours=1)).isoformat()
                    else:
                        now = datetime.now()
                        start_time = now.isoformat()
                        end_time = (now + timedelta(hours=1)).isoformat()

                    detalles_servicio = info_cita.get('detalles_servicio', {})
                    descripcion_servicio = detalles_servicio.get('descripcion', 'No hay descripción disponible')
                    categoria_servicio = detalles_servicio.get('categoria', 'Sin categoría')
                    precio_servicio = detalles_servicio.get('precio_menudeo') or detalles_servicio.get('precio', 'No especificado')

                    event_title = f"{'Pedido' if es_porfirianna else 'Cita'}: {info_cita.get('servicio_solicitado', 'Servicio')} - {info_cita.get('nombre_cliente', 'Cliente')}"

                    event_description = f"""
📋 DETALLES DE {'PEDIDO' if es_porfirianna else 'CITA'}:

🔸 {'Platillo' if es_porfirianna else 'Servicio'}: {info_cita.get('servicio_solicitado', 'No especificado')}
🔸 Categoría: {categoria_servicio}
🔸 Precio: ${precio_servicio} {info_cita.get('moneda', 'MXN')}
🔸 Descripción: {descripcion_servicio}

👤 CLIENTE:
🔹 Nombre: {info_cita.get('nombre_cliente', 'No especificado')}
🔹 Teléfono: {info_cita.get('telefono', 'No especificado')}
🔹 WhatsApp: https://wa.me/{info_cita.get('telefono', '').replace('+', '')}

⏰ FECHA/HORA:
🕒 Fecha: {info_cita.get('fecha_sugerida', 'No especificada')}
🕒 Hora: {info_cita.get('hora_sugerida', 'No especificada')}
🕒 Creado: {datetime.now().strftime('%d/%m/%Y %H:%M')}

💬 Notas: {'Pedido' if es_porfirianna else 'Cita'} agendado automáticamente desde WhatsApp
                    """.strip()

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
                                {'method': 'email', 'minutes': 24 * 60},
                            ],
                        },
                        'colorId': '4' if es_porfirianna else '1',
                    }

                    primary_calendar = os.getenv('GOOGLE_CALENDAR_ID', 'primary')

                    # 1) If advisor email exists, try to create the event directly in advisor's calendar (may fail if no permissions)
                    if asesor_email:
                        try:
                            app.logger.info(f"🌐 Intentando crear evento en calendario del asesor: calendarId='{asesor_email}' (sendUpdates=all)")
                            created = service.events().insert(calendarId=asesor_email, body=event, sendUpdates='all').execute()
                            evento_id = created.get('id')
                            app.logger.info(f'✅ Evento creado en calendario del asesor {asesor_email}: {created.get("htmlLink")}')
                        except HttpError as he:
                            app.logger.warning(f"⚠️ No se pudo crear evento en calendarId='{asesor_email}': {he}")
                            # Fallback: try to create in primary calendar and add advisor as attendee (this will send invite to advisor_email)
                            try:
                                event['attendees'] = [{'email': asesor_email}]
                                app.logger.info(f"🔁 Intentando crear evento en calendarId='{primary_calendar}' y añadir asesor como attendee (sendUpdates=all)")
                                created = service.events().insert(calendarId=primary_calendar, body=event, sendUpdates='all').execute()
                                evento_id = created.get('id')
                                app.logger.info(f'✅ Evento creado en {primary_calendar}: {created.get("htmlLink")} (attendee: {asesor_email})')
                            except Exception as e2:
                                app.logger.error(f'🔴 Fallback a primary con attendee falló: {e2}')
                                evento_id = None
                        except Exception as e:
                            app.logger.error(f'🔴 Error inesperado creando evento en calendario del asesor: {e}')
                            evento_id = None
                    else:
                        # 2) No asesor_email -> fall back to crear_evento_calendar which uses configured calendar_email / primary
                        try:
                            evento_id = crear_evento_calendar(service, info_cita, config)
                        except Exception as e:
                            app.logger.error(f"🔴 crear_evento_calendar falló en fallback: {e}")
                            evento_id = None

                    # If still no evento_id, try default behavior (crear_evento_calendar) as last resort
                    if not evento_id:
                        try:
                            evento_id = crear_evento_calendar(service, info_cita, config)
                        except Exception as e:
                            app.logger.error(f"🔴 Último intento crear_evento_calendar falló: {e}")
                            evento_id = None

                except Exception as e:
                    app.logger.error(f"🔴 Error notificando/agendando en Google Calendar para la cita: {e}")
                    evento_id = None

                # persist evento_id in citas if created
                if evento_id:
                    try:
                        cursor.execute("SHOW COLUMNS FROM citas LIKE 'evento_calendar_id'")
                        if cursor.fetchone() is None:
                            cursor.execute("ALTER TABLE citas ADD COLUMN evento_calendar_id VARCHAR(255) DEFAULT NULL")
                            conn.commit()
                            app.logger.info("🔧 Columna 'evento_calendar_id' creada en tabla 'citas'")
                        cursor.execute('UPDATE citas SET evento_calendar_id = %s WHERE id = %s', (evento_id, cita_id))
                        conn.commit()
                        app.logger.info(f"✅ Evento de calendar guardado en cita: {evento_id}")
                    except Exception as e:
                        app.logger.error(f'❌ Error guardando evento_calendar_id en citas: {e}')
            else:
                app.logger.warning("⚠️ autenticar_google_calendar devolvió None; no se intentó agendar en Calendar")

        # 6) Notificaciones al administrador (kept behavior)
        es_porfirianna = 'laporfirianna' in config.get('dominio', '')
        tipo_solicitud = "pedido" if es_porfirianna else "cita"

        detalles_servicio = info_cita.get('detalles_servicio', {})
        descripcion_servicio = detalles_servicio.get('descripcion', '')

        resumen = f"{tipo_solicitud.capitalize()}: {info_cita.get('servicio_solicitado')} - "
        resumen += f"Cliente: {info_cita.get('nombre_cliente')} - "
        resumen += f"Fecha: {info_cita.get('fecha_sugerida')} {info_cita.get('hora_sugerida')}"

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

        try:
            enviar_mensaje(ALERT_NUMBER, mensaje_notificacion, config)
            enviar_mensaje('5214493432744', mensaje_notificacion, config)
            app.logger.info(f"✅ Notificación de cita enviada a administradores, ID: {cita_id}")
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudieron enviar notificaciones por WhatsApp: {e}")

        # Insert notification record
        try:
            cursor.execute('''
                INSERT INTO notificaciones_ia (
                    numero, tipo, resumen, estado, mensaje, evaluacion_ia, calendar_event_id
                ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (
                info_cita.get('telefono'),
                tipo_solicitud,
                resumen,
                'pendiente',
                json.dumps(info_cita),
                json.dumps(evaluacion_ia),
                evento_id
            ))
            conn.commit()
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo insertar notificacion en DB: {e}")

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

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

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
    """Extrae fechas relativas simples del mensaje y devuelve YYYY-MM-DD o None"""
    mensaje_lower = (mensaje or "").lower()

    hoy_dt = datetime.now(tz_mx).date()

    # Manejar "hoy"
    if 'hoy' in mensaje_lower:
        return hoy_dt.strftime('%Y-%m-%d')

    if 'mañana' in mensaje_lower or 'manana' in mensaje_lower:
        return (hoy_dt + timedelta(days=1)).strftime('%Y-%m-%d')
    if 'pasado mañana' in mensaje_lower or 'pasadomanana' in mensaje_lower:
        return (hoy_dt + timedelta(days=2)).strftime('%Y-%m-%d')

    # Días de la semana: calcular próximo día mencionado
    dias_semana = {
        'lunes': 0, 'martes': 1, 'miércoles': 2, 'miercoles': 2,
        'jueves': 3, 'viernes': 4, 'sábado': 5, 'sabado': 5, 'domingo': 6
    }
    for nombre, target_weekday in dias_semana.items():
        if nombre in mensaje_lower:
            hoy_weekday = hoy_dt.weekday()
            dias_hasta = (target_weekday - hoy_weekday) % 7
            if dias_hasta == 0:
                dias_hasta = 7
            return (hoy_dt + timedelta(days=dias_hasta)).strftime('%Y-%m-%d')

    # Intentar parsear fechas explícitas comunes (dd/mm/yyyy, yyyy-mm-dd, etc.)
    try:
        # usar dateutil parser si está disponible
        from dateutil import parser as _parser
        # buscar un token que parezca fecha
        m = re.search(r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4})', mensaje)
        if m:
            parsed = _parser.parse(m.group(1), dayfirst=True, default=datetime.now(tz_mx))
            return parsed.date().strftime('%Y-%m-%d')
        # ISO-like
        m2 = re.search(r'(\d{4}-\d{2}-\d{2})', mensaje)
        if m2:
            return m2.group(1)
    except Exception:
        pass

    return None

def extraer_nombre_del_mensaje(mensaje):
    """Intenta extraer un nombre del mensaje"""
    # Patrón simple para nombres (2-3 palabras)
    patron_nombre = r'^[A-Za-zÁáÉéÍíÓóÚúÑñ]{2,20} [A-Za-zÁáÉéÍíÓóÚúÑñ]{2,20}( [A-Za-zÁáÉéÍíÓóÚúÑñ]{2,20})?$'
    
    if re.match(patron_nombre, mensaje.strip()):
        return mensaje.strip()
    
    return None
    
@app.route('/configuracion/negocio/publicar-pdf', methods=['POST'])
@login_required
def publicar_pdf_configuracion():
    """Recibe un PDF, imagen o video desde la vista de configuración (negocio),
    lo guarda en disk y registra metadatos en la BD."""
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

        # Prefijos distintos según tipo (imagen/pdf/video)
        image_exts = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'svg'}
        video_exts = {'mp4', 'mov', 'webm', 'avi', 'mkv', 'ogg', 'mpeg'}
        if ext in image_exts:
            prefix = 'img'
        elif ext in video_exts:
            prefix = 'video'
        else:
            prefix = 'pdf'  # pdf, docx, txt, xlsx, etc.

        # Nombre seguro y consistente: usar secure_filename para evitar caracteres problemáticos
        sanitized_orig = secure_filename(original_name)
        filename = f"{prefix}_{int(time.time())}_{sanitized_orig}"

        # Tenant-aware docs directory
        docs_dir, tenant_slug = get_docs_dir_for_config(config)
        filepath = os.path.join(docs_dir, filename)

        # Guardar archivo en disco y verificar
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        file.save(filepath)

        # Verificación inmediata y logging claro
        exists = os.path.isfile(filepath)
        size = os.path.getsize(filepath) if exists else 0
        app.logger.info(f"📄 Archivo guardado: {filepath} (exists={exists} size={size}) tenant_slug={tenant_slug}")

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

        # Insert dinámico: guardar el basename y el tenant_slug, filepath relativo (para servir con /uploads/docs/<tenant>/<file>)
        try:
            user = None
            au = session.get('auth_user')
            if au and isinstance(au, dict):
                user = au.get('user') or str(au.get('id') or '')

            # Guardar filepath relativo (desde uploads/docs) para mayor robustez
            # Ej: docs/ofitodo/filename -> almacenamos tenant_slug y filename; filepath campo guarda ruta absoluta por compatibilidad
            db_filepath = filepath  # opcional: guarda absoluta para debugging
            cursor.execute("""
                INSERT INTO documents_publicos (filename, filepath, descripcion, uploaded_by, tenant_slug)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE descripcion=VALUES(descripcion), uploaded_by=VALUES(uploaded_by), filepath=VALUES(filepath), created_at=CURRENT_TIMESTAMP
            """, (filename, db_filepath, descripcion, user, tenant_slug))
            conn.commit()
            app.logger.info(f"💾 Metadato inserted/updated in DB: filename={filename} tenant_slug={tenant_slug}")
        except Exception as e:
            app.logger.error(f"🔴 Error insertando metadato archivo: {e}")
            conn.rollback()
            flash('❌ Error guardando metadatos en la base de datos', 'error')
            try:
                cursor.close(); conn.close()
            except:
                pass
            # eliminar archivo guardado para evitar basura si DB falló
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                    app.logger.info(f"🗑️ Archivo eliminado por rollback: {filepath}")
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

def _ensure_precios_subscription_columns(config=None):
    """Asegura que la tabla `precios` tenga las columnas para suscripciones: inscripcion y mensualidad."""
    try:
        conn = get_db_connection(config)
        cur = conn.cursor()
        cur.execute("SHOW COLUMNS FROM precios LIKE 'inscripcion'")
        if cur.fetchone() is None:
            cur.execute("ALTER TABLE precios ADD COLUMN inscripcion DECIMAL(10,2) DEFAULT 0.00")
        cur.execute("SHOW COLUMNS FROM precios LIKE 'mensualidad'")
        if cur.fetchone() is None:
            cur.execute("ALTER TABLE precios ADD COLUMN mensualidad DECIMAL(10,2) DEFAULT 0.00")
        conn.commit()
        cur.close()
        conn.close()
        app.logger.info("🔧 Columnas 'inscripcion' y 'mensualidad' aseguradas en tabla precios")
    except Exception as e:
        app.logger.warning(f"⚠️ No se pudo asegurar columnas de suscripción en precios: {e}")

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
    Asigna un plan (planes.plan_id en CLIENTES_DB) al cliente identificado por `username`.
    Lee mensajes_incluidos desde la tabla 'planes' en la BD de clientes y lo copia al registro cliente.mensajes_incluidos.
    """
    try:
        # asegurar columnas en cliente
        _ensure_cliente_plan_columns()

        # 1) Obtener cliente en CLIENTES_DB
        conn_cli = get_clientes_conn()
        cur_cli = conn_cli.cursor(dictionary=True)
        cur_cli.execute("SELECT id_cliente, telefono FROM cliente WHERE `user` = %s LIMIT 1", (username,))
        cliente = cur_cli.fetchone()
        if not cliente:
            cur_cli.close(); conn_cli.close()
            app.logger.error(f"🔴 Cliente no encontrado para user={username}")
            return False

        # 2) Obtener mensajes_incluidos y nombre de plan desde tabla 'planes' en la BD de clientes
        mensajes_incluidos = 0
        plan_name = None
        try:
            cur_pl = conn_cli.cursor(dictionary=True)
            cur_pl.execute("SELECT plan_id, categoria, subcategoria, linea, modelo, mensajes_incluidos FROM planes WHERE plan_id = %s LIMIT 1", (plan_id,))
            plan_row = cur_pl.fetchone()
            if plan_row:
                mensajes_incluidos = int(plan_row.get('mensajes_incluidos') or 0)
                # Preferir modelo como nombre representativo, sino categoria, sino plan_id
                plan_name = (plan_row.get('modelo') or plan_row.get('categoria') or f"Plan {plan_id}")
            cur_pl.close()
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo leer plan desde CLIENTES_DB. Error: {e}")

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

def _ensure_domain_plans_table(conn):
    """Ensure domain_plans table exists in CLIENTES_DB (best-effort)."""
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS domain_plans (
                id INT AUTO_INCREMENT PRIMARY KEY,
                dominio VARCHAR(255) NOT NULL UNIQUE,
                plan_id INT NOT NULL,
                mensajes_incluidos INT DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                INDEX idx_plan_id (plan_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        conn.commit()
        cur.close()
    except Exception as e:
        # If creation fails, just log and continue (table might already exist or insufficient privileges)
        try:
            cur.close()
        except:
            pass
        app.logger.warning(f"⚠️ _ensure_domain_plans_table: could not ensure table: {e}")

def get_plan_for_domain(dominio):
    """
    Busca la fila de domain_plans en la BD de clientes por dominio (o heurísticas).
    Retorna dict {id, dominio, plan_id, mensajes_incluidos, created_at,...} o None.
    """
    try:
        if not dominio:
            return None
        conn = get_clientes_conn()
        cur = conn.cursor(dictionary=True)
        candidates = [
            dominio,
            dominio.split('.')[0] if '.' in dominio else dominio,
            dominio.replace('.', '_')
        ]
        for c in candidates:
            try:
                # Asegurar tabla si posible
                _ensure_domain_plans_table(conn)
                cur.execute("SELECT id, dominio, plan_id, mensajes_incluidos, created_at, updated_at FROM domain_plans WHERE dominio = %s LIMIT 1", (c,))
                row = cur.fetchone()
                if row:
                    cur.close(); conn.close()
                    return row
            except Exception:
                # intentar siguiente candidato
                continue
        cur.close(); conn.close()
    except Exception as e:
        app.logger.warning(f"⚠️ get_plan_for_domain error: {e}")
    return None

def get_plan_status_for_user(username, config=None):
    """
    Retorna el estado del plan para el cliente user:
    { 'plan_id', 'plan_name', 'mensajes_incluidos', 'mensajes_consumidos', 'mensajes_disponibles' }

    Cambio: si se pasa `config` (tenant), primero intenta leer plan desde CLIENTES_DB.domain_plans
    usando config['dominio']. Si existe, usa ese plan_id / mensajes_incluidos. Si no existe, mantiene
    la lógica previa (buscar cliente por user en CLIENTES_DB y planes).
    """
    try:
        plan_id = None
        plan_name = None
        mensajes_incluidos = 0

        # 1) If config provided, try to get domain plan first (preferred)
        if config and config.get('dominio'):
            try:
                dp = get_plan_for_domain(config.get('dominio'))
                if dp:
                    plan_id = dp.get('plan_id')
                    mensajes_incluidos = int(dp.get('mensajes_incluidos') or 0)
                    # try to read plan name from planes table if possible
                    try:
                        conn_cli = get_clientes_conn()
                        curp = conn_cli.cursor(dictionary=True)
                        curp.execute("SELECT plan_id, modelo, categoria FROM planes WHERE plan_id = %s LIMIT 1", (plan_id,))
                        plan_row = curp.fetchone()
                        curp.close(); conn_cli.close()
                        if plan_row:
                            plan_name = (plan_row.get('modelo') or plan_row.get('categoria') or f"Plan {plan_id}")
                    except Exception:
                        # ignore and continue with minimal info
                        pass
            except Exception as e:
                app.logger.warning(f"⚠️ get_plan_status_for_user: error obtaining domain plan: {e}")

        # 2) Fallback: if still no plan_id, try old flow (lookup by username in CLIENTES_DB)
        if not plan_id:
            try:
                conn_cli = get_clientes_conn()
                cur_cli = conn_cli.cursor(dictionary=True)
                cur_cli.execute("SELECT id_cliente, telefono, plan_id FROM cliente WHERE `user` = %s LIMIT 1", (username,))
                cliente = cur_cli.fetchone()
                cur_cli.close(); conn_cli.close()
                if cliente:
                    plan_id = cliente.get('plan_id')
                    if plan_id:
                        # read plan metadata from planes
                        try:
                            conn_cli = get_clientes_conn()
                            curp = conn_cli.cursor(dictionary=True)
                            curp.execute("SELECT plan_id, categoria, subcategoria, linea, modelo, descripcion, mensajes_incluidos FROM planes WHERE plan_id = %s LIMIT 1", (plan_id,))
                            plan_row = curp.fetchone()
                            curp.close(); conn_cli.close()
                            if plan_row:
                                plan_name = (plan_row.get('modelo') or plan_row.get('categoria') or f"Plan {plan_id}")
                                mensajes_incluidos = int(plan_row.get('mensajes_incluidos') or 0)
                        except Exception as e:
                            app.logger.warning(f"⚠️ get_plan_status_for_user: could not read planes table: {e}")
                else:
                    app.logger.info(f"ℹ️ get_plan_status_for_user: cliente not found for user={username}")
            except Exception as e:
                app.logger.warning(f"⚠️ get_plan_status_for_user cliente lookup failed: {e}")

        # ---------------------
        # Contar conversaciones (sessions) en la BD del tenant
        # ---------------------
        conversaciones_consumidas = 0
        try:
            if config is None:
                config = obtener_configuracion_por_host()
            conn_t = get_db_connection(config)
            cur_t = conn_t.cursor()

            # Intentar SQL con LAG() y PARTITION BY numero (MySQL 8+)
            sql_sessions = """
                SELECT COALESCE(SUM(is_new),0) FROM (
                  SELECT numero, timestamp,
                    CASE
                      WHEN LAG(timestamp) OVER (PARTITION BY numero ORDER BY timestamp) IS NULL
                        OR TIMESTAMPDIFF(SECOND, LAG(timestamp) OVER (PARTITION BY numero ORDER BY timestamp), timestamp) >= 86400
                      THEN 1 ELSE 0 END AS is_new
                  FROM conversaciones
                ) t
            """
            try:
                cur_t.execute(sql_sessions)
                row = cur_t.fetchone()
                conversaciones_consumidas = int(row[0]) if row and row[0] is not None else 0
                app.logger.info(f"🔎 Conversaciones (SQL LAG) => {conversaciones_consumidas}")
            except Exception as sql_err:
                # Fallback a procesamiento en Python (compatible con MySQL < 8)
                app.logger.warning(f"⚠️ Conteo por SQL LAG falló: {sql_err} — usando fallback en Python")
                cur_t.execute("SELECT numero, timestamp FROM conversaciones ORDER BY numero, timestamp")
                rows = cur_t.fetchall()  # list of tuples (numero, timestamp)
                prev_ts_by_num = {}
                cnt = 0
                for r in rows:
                    try:
                        num = r[0]
                        ts = r[1]
                        if num not in prev_ts_by_num:
                            cnt += 1
                            prev_ts_by_num[num] = ts
                        else:
                            prev = prev_ts_by_num[num]
                            # Asegurar que ts y prev sean datetime
                            try:
                                diff = (ts - prev).total_seconds()
                            except Exception:
                                # si por alguna razón son strings, intentar parsear
                                try:
                                    from dateutil import parser as _parser
                                    prev_dt = _parser.parse(str(prev))
                                    ts_dt = _parser.parse(str(ts))
                                    diff = (ts_dt - prev_dt).total_seconds()
                                    prev_ts_by_num[num] = ts_dt
                                except Exception:
                                    diff = 0
                            if diff >= 86400:  # 24 horas en segundos
                                cnt += 1
                                prev_ts_by_num[num] = ts
                            else:
                                prev_ts_by_num[num] = ts
                    except Exception:
                        continue
                conversaciones_consumidas = cnt
                app.logger.info(f"🔎 Conversaciones (fallback Python) => {conversaciones_consumidas}")

            cur_t.close(); conn_t.close()
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo contar conversaciones en tenant DB: {e}")
            conversaciones_consumidas = 0

        mensajes_disponibles = None
        if mensajes_incluidos is not None:
            mensajes_disponibles = max(0, mensajes_incluidos - conversaciones_consumidas)

        return {
            'plan_id': plan_id,
            'plan_name': plan_name,
            'mensajes_incluidos': mensajes_incluidos,
            'mensajes_consumidos': conversaciones_consumidas,
            'mensajes_disponibles': mensajes_disponibles
        }

    except Exception as e:
        app.logger.error(f"🔴 Error en get_plan_status_for_user: {e}")
        return None

def build_texto_catalogo(precios, limit=20):
    """Construye un texto resumen del catálogo (hasta `limit` items)."""
    if not precios:
        return "No hay productos registrados en el catálogo."
    lines = []
    for p in precios[:limit]:
        sku = (p.get('sku') or '').strip()
        nombre = (p.get('servicio') or p.get('modelo') or '').strip()
        # Preferencia en orden para precio mostrado
        precio = p.get('precio_menudeo') or p.get('precio_mayoreo') or p.get('costo') or ''
        inscripcion = p.get('inscripcion')
        mensualidad = p.get('mensualidad')
        precio_str = ''
        try:
            if precio not in (None, ''):
                precio_str = f" - ${float(precio):,.2f}"
        except Exception:
            precio_str = f" - {precio}"
        extras = []
        try:
            if inscripcion not in (None, '', 0):
                extras.append(f"Inscripción: ${float(inscripcion):,.2f}")
        except Exception:
            extras.append(f"Inscripción: {inscripcion}")
        try:
            if mensualidad not in (None, '', 0):
                extras.append(f"Mensualidad: ${float(mensualidad):,.2f}")
        except Exception:
            extras.append(f"Mensualidad: {mensualidad}")
        extras_str = (f" ({', '.join(extras)})") if extras else ""
        lines.append(f"{nombre or sku}{(' (SKU:'+sku+')') if sku else ''}{precio_str}{extras_str}")
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
            transferencia_numero VARCHAR(100),
            transferencia_nombre VARCHAR(200),
            transferencia_banco VARCHAR(100),
            -- Asesores de ventas (columnas antiguas para compatibilidad)
            asesor1_nombre VARCHAR(100),
            asesor1_telefono VARCHAR(50),
            asesor1_email VARCHAR(150),
            asesor2_nombre VARCHAR(100),
            asesor2_telefono VARCHAR(50),
            asesor2_email VARCHAR(150),
            -- Nueva columna JSON que puede contener lista arbitraria de asesores
            asesores_json TEXT
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    ''')
    cursor.execute("SELECT * FROM configuracion WHERE id = 1;")
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        return {'negocio': {}, 'personalizacion': {}, 'restricciones': {}, 'asesores': {}, 'asesores_list': []}

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
        'calendar_email': row.get('calendar_email', ''),
        'transferencia_numero': row.get('transferencia_numero', ''),
        'transferencia_nombre': row.get('transferencia_nombre', ''),
        'transferencia_banco': row.get('transferencia_banco', '')
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

    # Manejo de asesores: preferir columna JSON si existe, si no usar columnas antiguas
    asesores_list = []
    asesores_map = {}
    try:
        asesores_json = row.get('asesores_json')
        if asesores_json:
            try:
                parsed = json.loads(asesores_json)
                if isinstance(parsed, list):
                    # Ensure each advisor dict includes nombre, telefono, email keys
                    for a in parsed:
                        if isinstance(a, dict):
                            asesores_list.append({
                                'nombre': (a.get('nombre') or '').strip(),
                                'telefono': (a.get('telefono') or '').strip(),
                                'email': (a.get('email') or '').strip()
                            })
                    # Build map for backward compatibility (asesor1_nombre, etc.)
                    for idx, a in enumerate(asesores_list, start=1):
                        asesores_map[f'asesor{idx}_nombre'] = a.get('nombre', '')
                        asesores_map[f'asesor{idx}_telefono'] = a.get('telefono', '')
                        asesores_map[f'asesor{idx}_email'] = a.get('email', '')
            except Exception:
                app.logger.warning("⚠️ No se pudo parsear asesores_json, fallback a columnas individuales")
        if not asesores_list:
            # Fallback: legacy columns (asesor1, asesor2)
            a1n = (row.get('asesor1_nombre') or '').strip()
            a1t = (row.get('asesor1_telefono') or '').strip()
            a1e = (row.get('asesor1_email') or '').strip()
            a2n = (row.get('asesor2_nombre') or '').strip()
            a2t = (row.get('asesor2_telefono') or '').strip()
            a2e = (row.get('asesor2_email') or '').strip()
            if a1n or a1t or a1e:
                asesores_list.append({'nombre': a1n, 'telefono': a1t, 'email': a1e})
                asesores_map['asesor1_nombre'] = a1n
                asesores_map['asesor1_telefono'] = a1t
                asesores_map['asesor1_email'] = a1e
            if a2n or a2t or a2e:
                asesores_list.append({'nombre': a2n, 'telefono': a2t, 'email': a2e})
                asesores_map['asesor2_nombre'] = a2n
                asesores_map['asesor2_telefono'] = a2t
                asesores_map['asesor2_email'] = a2e
    except Exception as e:
        app.logger.warning(f"⚠️ Error procesando asesores: {e}")

    # Return both map (backward compat) and list (preferred)
    return {
        'negocio': negocio,
        'personalizacion': personalizacion,
        'restricciones': restricciones,
        'asesores': asesores_map if 'asesores_map' in locals() else {},
        'asesores_list': asesores_list if 'asesores_list' in locals() else []
    }

def save_config(cfg_all, config=None):
    if config is None:
        config = obtener_configuracion_por_host()
    neg = cfg_all.get('negocio', {})
    per = cfg_all.get('personalizacion', {})
    res = cfg_all.get('restricciones', {})
    ases = cfg_all.get('asesores', {})  # map for backward compat
    ases_json = cfg_all.get('asesores_json', None)  # optional JSON string / structure

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
    if 'transferencia_numero' not in existing_cols:
        alter_statements.append("ADD COLUMN transferencia_numero VARCHAR(100) DEFAULT NULL")
    if 'transferencia_nombre' not in existing_cols:
        alter_statements.append("ADD COLUMN transferencia_nombre VARCHAR(200) DEFAULT NULL")
    if 'transferencia_banco' not in existing_cols:
        alter_statements.append("ADD COLUMN transferencia_banco VARCHAR(100) DEFAULT NULL")
    if 'asesor1_nombre' not in existing_cols:
        alter_statements.append("ADD COLUMN asesor1_nombre VARCHAR(100) DEFAULT NULL")
    if 'asesor1_telefono' not in existing_cols:
        alter_statements.append("ADD COLUMN asesor1_telefono VARCHAR(50) DEFAULT NULL")
    if 'asesor1_email' not in existing_cols:
        alter_statements.append("ADD COLUMN asesor1_email VARCHAR(150) DEFAULT NULL")
    if 'asesor2_nombre' not in existing_cols:
        alter_statements.append("ADD COLUMN asesor2_nombre VARCHAR(100) DEFAULT NULL")
    if 'asesor2_telefono' not in existing_cols:
        alter_statements.append("ADD COLUMN asesor2_telefono VARCHAR(50) DEFAULT NULL")
    if 'asesor2_email' not in existing_cols:
        alter_statements.append("ADD COLUMN asesor2_email VARCHAR(150) DEFAULT NULL")
    if 'asesores_json' not in existing_cols:
        alter_statements.append("ADD COLUMN asesores_json TEXT DEFAULT NULL")

    if alter_statements:
        try:
            sql = f"ALTER TABLE configuracion {', '.join(alter_statements)}"
            cursor.execute(sql)
            conn.commit()
            app.logger.info(f"🔧 configuracion table altered: {alter_statements}")
            cursor.execute("SHOW COLUMNS FROM configuracion")
            existing_cols = {row[0] for row in cursor.fetchall()}
        except Exception as e:
            app.logger.warning(f"⚠️ Could not alter configuracion table: {e}")

    try:
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
            'transferencia_numero': neg.get('transferencia_numero', None),
            'transferencia_nombre': neg.get('transferencia_nombre', None),
            'transferencia_banco': neg.get('transferencia_banco', None),
            # legacy asesor fields (if provided in ases map)
            'asesor1_nombre': ases.get('asesor1_nombre', None),
            'asesor1_telefono': ases.get('asesor1_telefono', None),
            'asesor1_email': ases.get('asesor1_email', None),
            'asesor2_nombre': ases.get('asesor2_nombre', None),
            'asesor2_telefono': ases.get('asesor2_telefono', None),
            'asesor2_email': ases.get('asesor2_email', None),
            'asesores_json': None
        }

        # if caller supplied structured advisors (list or json), normalize to JSON string
        if ases_json is not None:
            if isinstance(ases_json, (list, dict)):
                candidate_map['asesores_json'] = json.dumps(ases_json, ensure_ascii=False)
            else:
                candidate_map['asesores_json'] = str(ases_json)
        else:
            # No explicit asesores_json provided; if ases map contains advisor keys build small JSON list
            advisors_compiled = []
            # look for asesorN in ases map
            i = 1
            while True:
                name_key = f'asesor{i}_nombre'
                phone_key = f'asesor{i}_telefono'
                email_key = f'asesor{i}_email'
                if name_key in ases or phone_key in ases or email_key in ases:
                    name = (ases.get(name_key) or '').strip()
                    phone = (ases.get(phone_key) or '').strip()
                    email = (ases.get(email_key) or '').strip()
                    if name or phone or email:
                        advisors_compiled.append({'nombre': name, 'telefono': phone, 'email': email})
                    i += 1
                    # prevent infinite loop
                    if i > 20:
                        break
                else:
                    break
            if advisors_compiled:
                candidate_map['asesores_json'] = json.dumps(advisors_compiled, ensure_ascii=False)

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

def obtener_max_asesores_from_planes(default=2, cap=10):
    """
    Lee la tabla `planes` en la BD de clientes y retorna el máximo valor de la columna `asesores`.
    Si falla, devuelve `default`. Se aplica un cap (por seguridad).
    """
    try:
        conn = get_clientes_conn()
        cur = conn.cursor()
        cur.execute("SELECT MAX(asesores) FROM planes")
        row = cur.fetchone()
        cur.close(); conn.close()
        if row and row[0] is not None:
            n = int(row[0])
            if n < 1:
                return default
            return min(n, cap)
    except Exception as e:
        app.logger.warning(f"⚠️ obtener_max_asesores_from_planes falló: {e}")
    return default

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
        
def obtener_datos_de_transferencia(config):
    try:
        db = get_db_connection(config)
        cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM configuracion
            ORDER BY transferencia_numero, transferencia_nombre, transferencia_banco;
        """)
        datos_transferencia = cursor.fetchall()
        cursor.close()
        db.close()
        return datos_transferencia

    except Exception as e:
        print(f"Error obteniendo datos de transferencia: {str(e)}")
        return []
        
def obtener_producto_por_sku_o_nombre(query, config=None):
    """
    Busca un producto en la tabla `precios` por SKU, modelo o servicio que coincida con `query`.
    Retorna la fila completa (dict) o None.
    """
    if config is None:
        config = obtener_configuracion_por_host()
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)

        q = (query or '').strip()
        if not q:
            cursor.close(); conn.close()
            return None

        # Intentos: SKU exacto -> modelo exacto -> servicio LIKE -> modelo LIKE -> sku LIKE
        # Normalizar posibles formatos
        candidates = [
            ("SELECT * FROM precios WHERE sku = %s LIMIT 1", (q,)),
            ("SELECT * FROM precios WHERE LOWER(modelo) = LOWER(%s) LIMIT 1", (q,)),
            ("SELECT * FROM precios WHERE LOWER(servicio) LIKE LOWER(CONCAT('%', %s, '%')) LIMIT 1", (q,)),
            ("SELECT * FROM precios WHERE LOWER(modelo) LIKE LOWER(CONCAT('%', %s, '%')) LIMIT 1", (q,)),
            ("SELECT * FROM precios WHERE LOWER(sku) LIKE LOWER(CONCAT('%', %s, '%')) LIMIT 1", (q,)),
        ]

        for sql, params in candidates:
            try:
                cursor.execute(sql, params)
                row = cursor.fetchone()
                if row:
                    cursor.close(); conn.close()
                    return row
            except Exception:
                # ignora errores en cada intento y sigue con el siguiente
                continue

        cursor.close(); conn.close()
        return None
    except Exception as e:
        app.logger.error(f"🔴 obtener_producto_por_sku_o_nombre error: {e}")
        return None

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

def obtener_siguiente_asesor(config=None):
    """
    Retorna el siguiente asesor disponible en forma round-robin.
    Ahora también:
      - Intenta inferir el usuario/cliente dueño del tenant (CLIENTES_DB) para obtener
        el límite de asesores del plan y, si hay más asesores en la BD que los
        permitidos por el plan, recorta automáticamente (eliminar_asesores_extras).
      - Soporta lista JSON en `asesores_json` y columnas legacy `asesorN_nombre`/telefono.
    Devuelve dict {'nombre','telefono'} o None si no hay asesores configurados.
    """
    if config is None:
        config = obtener_configuracion_por_host()

    def _infer_cliente_user_for_config(cfg):
        """Intenta encontrar el `user` en CLIENTES_DB asociado al tenant (heurístico)."""
        try:
            conn_cli = get_clientes_conn()
            cur = conn_cli.cursor(dictionary=True)
            # Heurísticas: buscar por shema/db_name, por dominio (entorno) o por servicio
            candidates = (cfg.get('db_name'), cfg.get('dominio'), cfg.get('dominio'))
            cur.execute("""
                SELECT `user`
                  FROM cliente
                 WHERE shema = %s OR entorno = %s OR servicio = %s
                 LIMIT 1
            """, candidates)
            row = cur.fetchone()
            cur.close(); conn_cli.close()
            return row.get('user') if row and row.get('user') else None
        except Exception:
            return None

    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)

        # Asegurar columna asesor_next_index
        try:
            cursor.execute("SHOW COLUMNS FROM configuracion LIKE 'asesor_next_index'")
            if cursor.fetchone() is None:
                cursor.execute("ALTER TABLE configuracion ADD COLUMN asesor_next_index INT DEFAULT 1")
                conn.commit()
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo asegurar columna asesor_next_index: {e}")

        # Leer fila actual
        cursor.execute("SELECT * FROM configuracion WHERE id = 1 LIMIT 1")
        row = cursor.fetchone()
        if not row:
            cursor.close(); conn.close()
            return None

        # Build advisors list (from JSON preferred, otherwise legacy columns)
        def _build_asesores_from_row(r):
            ases = []
            ases_json = r.get('asesores_json')
            if ases_json:
                try:
                    parsed = json.loads(ases_json)
                    if isinstance(parsed, list):
                        for a in parsed:
                            if isinstance(a, dict):
                                nombre = (a.get('nombre') or '').strip()
                                telefono = (a.get('telefono') or '').strip()
                                email = (a.get('email') or '').strip()
                                if nombre or telefono or email:
                                    ases.append({'nombre': nombre, 'telefono': telefono, 'email': email})
                except Exception:
                    app.logger.warning("⚠️ obtener_siguiente_asesor: no se pudo parsear asesores_json, fallback a columnas legacy")
            if not ases:
                # legacy dynamic columns
                temp = {}
                pattern = re.compile(r'^asesor(\d+)_nombre$')
                for k, v in r.items():
                    if not k:
                        continue
                    m = pattern.match(k)
                    if m:
                        idx = int(m.group(1))
                        nombre = (v or '').strip()
                        telefono = (r.get(f'asesor{idx}_telefono') or '').strip()
                        email = (r.get(f'asesor{idx}_email') or '').strip()
                        if nombre or telefono or email:
                            temp[idx] = {'nombre': nombre, 'telefono': telefono, 'email': email}
                for idx in sorted(temp.keys()):
                    ases.append(temp[idx])
            return ases

        asesores = _build_asesores_from_row(row)

        # Infer allowed_count: try per-client plan (best effort); fallback to global max
        allowed_count = None
        try:
            usuario_propietario = _infer_cliente_user_for_config(config)
            if usuario_propietario:
                allowed_count = obtener_asesores_por_user(usuario_propietario, default=1, cap=50)
            else:
                # fallback: use global max from planes (safe default 1)
                allowed_count = obtener_max_asesores_from_planes(default=1, cap=50)
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo inferir allowed_count para asesores: {e}")
            allowed_count = obtener_max_asesores_from_planes(default=1, cap=50)

        # If DB has more advisors than allowed by plan, trim them (and reload)
        try:
            if asesores and allowed_count is not None and len(asesores) > allowed_count:
                app.logger.info(f"⚠️ Hay {len(asesores)} asesores en BD pero el plan permite {allowed_count}. Recortando...")
                eliminar_asesores_extras(config, allowed_count)
                # reload row and rebuild list
                cursor.execute("SELECT * FROM configuracion WHERE id = 1 LIMIT 1")
                row = cursor.fetchone()
                asesores = _build_asesores_from_row(row)
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo recortar asesores automáticamente: {e}")

        if not asesores:
            cursor.close(); conn.close()
            return None

        # Índice actual (1-based). Si no existe en row, usar 1.
        try:
            idx_actual = int(row.get('asesor_next_index') or 1)
        except Exception:
            idx_actual = 1

        n = len(asesores)
        elegido_index0 = (idx_actual - 1) % n
        elegido = asesores[elegido_index0]

        # Calcular siguiente índice 1-based y persistirlo
        siguiente = (elegido_index0 + 1) + 1
        if siguiente > n:
            siguiente = 1

        try:
            cursor.execute("UPDATE configuracion SET asesor_next_index = %s WHERE id = 1", (siguiente,))
            conn.commit()
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo actualizar asesor_next_index: {e}")

        cursor.close(); conn.close()
        return elegido

    except Exception as e:
        app.logger.error(f"🔴 obtener_siguiente_asesor error: {e}")
        return None

def pasar_contacto_asesor(numero_cliente, config=None, notificar_asesor=True):
    """
    Envía al cliente SOLO UN asesor (round-robin). Retorna True si se envió.
    También notifica al asesor seleccionado (opcional).
    """
    if config is None:
        config = obtener_configuracion_por_host()
    try:
        asesor = obtener_siguiente_asesor(config)
        if not asesor:
            app.logger.info("ℹ️ No hay asesores configurados para pasar contacto")
            return False

        nombre = asesor.get('nombre') or 'Asesor'
        telefono = asesor.get('telefono') or ''

        texto_cliente = f"📞 Te comparto el contacto de un asesor:\n\n• {nombre}\n• WhatsApp: {telefono}"
        enviado = enviar_mensaje(numero_cliente, texto_cliente, config)
        if enviado:
            guardar_conversacion(numero_cliente, f"Solicitud de asesor (rotación)", texto_cliente, config)
            app.logger.info(f"✅ Contacto de asesor enviado a {numero_cliente}: {nombre} {telefono}")
        else:
            app.logger.warning(f"⚠️ No se pudo enviar el contacto del asesor a {numero_cliente}")

        if notificar_asesor and telefono:
            try:
                # Obtener nombre mostrado del cliente
                cliente_mostrado = obtener_nombre_mostrado_por_numero(numero_cliente, config) or numero_cliente

                # Preparar historial para resumen
                historial = obtener_historial(numero_cliente, limite=8, config=config) or []
                partes = []
                for h in historial:
                    if h.get('mensaje'):
                        partes.append(f"Usuario: {h.get('mensaje')}")
                    if h.get('respuesta'):
                        partes.append(f"Asistente: {h.get('respuesta')}")
                historial_text = "\n".join(partes) or "Sin historial previo."

                # Preguntar a la IA por un resumen breve (1-3 líneas)
                resumen = None
                try:
                    prompt = f"""
Resume en 1-5 líneas en español, con lenguaje natural, el contexto principal de la conversación
del cliente para que un asesor humano lo entienda rápidamente. Usa SOLO el historial a continuación.
No incluyas números de teléfono ni direcciones.

HISTORIAL:
{historial_text}

Devuelve únicamente el resumen breve (1-3 líneas).
"""
                    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
                    payload = {
                        "model": "deepseek-chat",
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.2,
                        "max_tokens": 200
                    }
                    r = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=10)
                    r.raise_for_status()
                    d = r.json()
                    raw = d['choices'][0]['message']['content']
                    if isinstance(raw, list):
                        raw = " ".join([(it.get('text') if isinstance(it, dict) else str(it)) for it in raw])
                    resumen = str(raw).strip()
                    # Keep it compact
                    resumen = re.sub(r'\s*\n\s*', ' ', resumen)[:400]
                except Exception as e:
                    app.logger.warning(f"⚠️ No se pudo generar resumen IA para asesor: {e}")
                    # Fallback: usar primer/último mensaje corto
                    if historial:
                        ultimo = historial[-1].get('mensaje') or ''
                        resumen = (ultimo[:200] + '...') if len(ultimo) > 200 else ultimo
                    else:
                        resumen = "Sin historial disponible."

                texto_asesor = (
                    f"ℹ️ Se compartió tu contacto con cliente {numero_cliente} ({cliente_mostrado}).\n\n"
                    f"🔎 Resumen rápido del chat para que lo atiendas:\n{resumen}\n\n"
                    "Por favor, estate atento para contactarlo si corresponde."
                )

                enviar_mensaje(telefono, texto_asesor, config)
                app.logger.info(f"📤 Notificación enviada al asesor {telefono}")
            except Exception as e:
                app.logger.warning(f"⚠️ No se pudo notificar al asesor {telefono}: {e}")

        return enviado
    except Exception as e:
        app.logger.error(f"🔴 pasar_contacto_asesor error: {e}")
        return False

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
    
    # Convert timestamps to ISO format for JSON and ensure timezone consistency
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
        # <-- RETURN TIMESTAMP IN MILLISECONDS to match client Date.now() units
        'timestamp': int(time.time() * 1000),
        'total_chats': len(chats)
    })

@app.route('/uploads/docs/<path:relpath>')
def serve_public_docs(relpath):
    """Serve published files from uploads/docs/<tenant_slug>/<filename> (tenant-aware).
    Accepts paths like 'tenant_slug/filename.pdf' so Facebook can fetch the file_url built by enviar_catalogo.
    """
    from werkzeug.exceptions import HTTPException
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
        app.logger.debug(f"🔍 serve_public_docs debug: docs_base={docs_base} safe_relpath={safe_relpath} full_path={full_path}")

        if not os.path.isfile(full_path):
            # List tenant dir contents to help debugging
            tenant_dir = os.path.dirname(full_path)
            try:
                dir_list = os.listdir(tenant_dir)
            except Exception:
                dir_list = []
            app.logger.info(f"❌ Public doc not found: {full_path} | tenant_dir_contents_count={len(dir_list)} sample={dir_list[:50]}")
            abort(404)

        directory = os.path.dirname(full_path)
        filename = os.path.basename(full_path)
        return send_from_directory(directory, filename)
    except HTTPException:
        # Re-raise HTTP exceptions (abort(404) -> preserved)
        raise
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

def obtener_asesores_por_user(username, default=2, cap=20):
    """
    Retorna el número de asesores permitido para el cliente identificado por `username`.
    - Lee cliente en CLIENTES_DB para obtener plan_id.
    - Lee la fila correspondiente en `planes` y retorna el campo `asesores` si existe.
    - Si falla, devuelve `default`. Aplica un cap por seguridad.
    """
    try:
        if not username:
            return default
        conn = get_clientes_conn()
        cur = conn.cursor(dictionary=True)
        # Obtener plan_id del cliente
        cur.execute("SELECT plan_id FROM cliente WHERE `user` = %s LIMIT 1", (username,))
        row = cur.fetchone()
        plan_id = row.get('plan_id') if row else None
        cur.close(); conn.close()

        if not plan_id:
            return default

        conn = get_clientes_conn()
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT asesores FROM planes WHERE plan_id = %s LIMIT 1", (plan_id,))
        plan_row = cur.fetchone()
        cur.close(); conn.close()

        if plan_row and plan_row.get('asesores') is not None:
            try:
                n = int(plan_row.get('asesores') or 0)
                if n < 1:
                    return default
                return min(n, cap)
            except Exception:
                return default

        return default
    except Exception as e:
        app.logger.warning(f"⚠️ obtener_asesores_por_user falló para user={username}: {e}")
        return default

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

def obtener_nombre_mostrado_por_numero(numero, config=None):
    """
    Retorna el nombre a mostrar para un número de contacto.
    Prioriza alias, luego nombre, y si no hay ninguno devuelve el propio número.
    """
    if not numero:
        return numero or ''
    if config is None:
        config = obtener_configuracion_por_host()
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT alias, nombre
            FROM contactos
            WHERE numero_telefono = %s
            LIMIT 1
        """, (numero,))
        row = cursor.fetchone()
        cursor.close()
        conn.close()
        if row:
            return (row.get('alias') or row.get('nombre') or numero)
    except Exception as e:
        app.logger.debug(f"⚠️ obtener_nombre_mostrado_por_numero error: {e}")
    return numero

def enviar_notificacion_pedido_cita(numero, mensaje, analisis_pedido, config=None):
    """
    Envía notificación al administrador cuando se detecta un pedido o cita.
    Ahora muestra nombre del cliente (si está disponible) en lugar del número.
    """
    if config is None:
        config = obtener_configuracion_por_host()
    
    try:
        es_porfirianna = 'laporfirianna' in config.get('dominio', '')
        tipo_solicitud = "pedido" if es_porfirianna else "cita"
        
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
        
        cursor.execute('''
            INSERT INTO notificaciones_ia (numero, tipo, resumen)
            VALUES (%s, %s, %s)
        ''', (numero, tipo_solicitud, resumen))
        conn.commit()
        notificacion_id = cursor.lastrowid
        cursor.close()
        conn.close()
        
        # use display name instead of raw number
        cliente_mostrado = obtener_nombre_mostrado_por_numero(numero, config)
        
        mensaje_alerta = f"""🔔 *NUEVA SOLICITUD DE {tipo_solicitud.upper()}*

👤 *Cliente:* {cliente_mostrado}
📞 *Número:* {numero}
⏰ *Hora:* {datetime.now().strftime('%d/%m/%Y %H:%M')}
💬 *Mensaje:* {mensaje[:150]}{'...' if len(mensaje) > 150 else ''}

📝 *Resumen:* {resumen}

🔄 *Estado:* Pendiente de atención
🆔 *ID Notificación:* {notificacion_id}
"""
        enviar_mensaje(ALERT_NUMBER, mensaje_alerta, config)
        enviar_mensaje('5214493432744', mensaje_alerta, config)
        
        app.logger.info(f"✅ Notificación de {tipo_solicitud} enviada para {numero} (mostrar: {cliente_mostrado})")
        return True
        
    except Exception as e:
        app.logger.error(f"Error enviando notificación de pedido/cita: {e}")
        return False

def enviar_alerta_humana(numero_cliente, mensaje_clave, resumen, config=None):
    if config is None:
        config = obtener_configuracion_por_host()

    contexto_consulta = obtener_contexto_consulta(numero_cliente, config)
    if config is None:
        app.logger.error("🔴 Configuración no disponible para enviar alerta")
        return
    
    try:
        cliente_mostrado = obtener_nombre_mostrado_por_numero(numero_cliente, config)
    except Exception:
        cliente_mostrado = numero_cliente

    mensaje = f"🚨 *ALERTA: Intervención Humana Requerida*\n\n"
    mensaje += f"👤 *Cliente:* {cliente_mostrado}\n"
    mensaje += f"📞 *Número:* {numero_cliente}\n"
    mensaje += f"💬 *Mensaje clave:* {mensaje_clave[:100]}{'...' if len(mensaje_clave) > 100 else ''}\n\n"
    mensaje += f"📋 *Resumen:*\n{resumen[:800]}{'...' if len(resumen) > 800 else ''}\n\n"
    mensaje += f"⏰ *Hora:* {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
    mensaje += f"🎯 *INFORMACIÓN DEL PROYECTO/CONSULTA:*\n"
    mensaje += f"{contexto_consulta}\n\n"
    mensaje += f"_________________________________________\n"
    mensaje += f"📊 Atiende desde el CRM o responde directamente por WhatsApp"
    
    enviar_mensaje(ALERT_NUMBER, mensaje, config)
    enviar_mensaje('5214493432744', mensaje, config)
    app.logger.info(f"📤 Alerta humana enviada para {numero_cliente} (mostrar: {cliente_mostrado}) desde {config.get('dominio')}")

def resumen_rafa(numero, config=None):
    """Resumen más completo y eficiente (muestra nombre si existe)"""
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
        
        cliente_mostrado = obtener_nombre_mostrado_por_numero(numero, config)
        
        resumen = "🚨 *ALERTA: Intervención Humana Requerida*\n\n"
        resumen += f"📞 *Cliente:* {cliente_mostrado}\n"
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
        'humano', 'persona', 'agente', 'ejecutivo', 'representante',
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

@app.route('/chats/<numero>/marcar-leido', methods=['POST'])
def marcar_leido_chat(numero):
    """
    Marca como 'leído' todos los mensajes entrantes (respuesta IS NULL) de un chat.
    Esto pone `respuesta = ''` para que la columna sin_leer calculada en kanban_data pase a 0.
    """
    config = obtener_configuracion_por_host()
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE conversaciones
               SET respuesta = ''
             WHERE numero = %s AND respuesta IS NULL
        """, (numero,))
        updated = cursor.rowcount
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({'success': True, 'updated': updated})
    except Exception as e:
        app.logger.error(f"🔴 Error marcando mensajes como leídos para {numero}: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

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
        # Basic validation
        if not request.is_json:
            app.logger.error("🔴 Webhook: no JSON payload")
            return 'Invalid content type', 400
        payload = request.get_json()
        if not payload:
            app.logger.error("🔴 Webhook: empty JSON")
            return 'Invalid JSON', 400

        app.logger.info(f"📥 Webhook payload: {json.dumps(payload)[:800]}")

        # Basic structure checks
        if 'entry' not in payload or not payload['entry']:
            app.logger.error("🔴 Webhook: missing entry")
            return 'Invalid payload structure', 400
        entry = payload['entry'][0]
        if 'changes' not in entry or not entry['changes']:
            app.logger.error("🔴 Webhook: missing changes")
            return 'Invalid entry structure', 400

        change = entry['changes'][0]['value']
        mensajes = change.get('messages', [])
        if not mensajes:
            app.logger.info("⚠️ Webhook: no messages in payload")
            return 'OK', 200

        # Try to persist contact info if provided (contacts structure)
        try:
            if ('contacts' in entry['changes'][0]['value']):
                contact = entry['changes'][0]['value']['contacts'][0]
                wa_id = contact.get('wa_id')
                name = (contact.get('profile') or {}).get('name')
                if wa_id:
                    cfg_tmp = obtener_configuracion_por_host()
                    conn = get_db_connection(cfg_tmp)
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO contactos (numero_telefono, nombre, plataforma)
                        VALUES (%s, %s, 'WhatsApp')
                        ON DUPLICATE KEY UPDATE
                            nombre = COALESCE(%s, nombre),
                            fecha_actualizacion = CURRENT_TIMESTAMP
                    """, (wa_id, name, name))
                    conn.commit(); cur.close(); conn.close()
                    app.logger.info(f"✅ Contact saved from webhook: {wa_id} - {name}")
        except Exception as e:
            app.logger.warning(f"⚠️ Could not save contact from webhook: {e}")

        # Main message
        msg = mensajes[0]
        numero = msg.get('from')
        if not numero:
            app.logger.error("🔴 Webhook: message without 'from'")
            return 'OK', 200

        # Determine tenant config from phone_number_id if available
        phone_number_id = change.get('metadata', {}).get('phone_number_id')
        config = obtener_configuracion_por_phone_number_id(phone_number_id) if phone_number_id else obtener_configuracion_por_host()
        if not config:
            config = obtener_configuracion_por_host()

        # Ensure kanban/chat meta/contact are present (quick pre-check)
        try:
            inicializar_chat_meta(numero, config)
            actualizar_info_contacto(numero, config)
        except Exception as e:
            app.logger.warning(f"⚠️ pre-processing kanban/contact failed: {e}")

        # Deduplication by message id
        message_id = msg.get('id')
        if not message_id:
            app.logger.error("🔴 Webhook: message without id, cannot dedupe reliably")
            return 'OK', 200
        message_hash = hashlib.md5(f"{numero}_{message_id}".encode()).hexdigest()
        # quick duplicate check
        if message_hash in processed_messages:
            app.logger.info(f"⚠️ Duplicate webhook delivery ignored: {message_hash}")
            return 'OK', 200
        processed_messages[message_hash] = time.time()
        # cleanup old keys
        now_ts = time.time()
        for h, ts in list(processed_messages.items()):
            if now_ts - ts > 3600:
                del processed_messages[h]

        # Parse incoming content (text / image / audio / document)
        texto = ''
        es_imagen = es_audio = es_archivo = False
        imagen_base64 = None
        public_url = None
        transcripcion = None

        if 'text' in msg and 'body' in msg['text']:
            texto = (msg['text']['body'] or '').strip()
        elif 'image' in msg:
            es_imagen = True
            image_id = msg['image'].get('id')
            try:
                imagen_base64, public_url = obtener_imagen_whatsapp(image_id, config)
            except Exception as e:
                app.logger.warning(f"⚠️ obtener_imagen_whatsapp failed: {e}")
            texto = (msg.get('image', {}).get('caption') or "El usuario envió una imagen").strip()
        elif 'audio' in msg:
            es_audio = True
            audio_id = msg['audio'].get('id')
            try:
                audio_path, audio_url = obtener_audio_whatsapp(audio_id, config)
                if audio_path:
                    transcripcion = transcribir_audio_con_openai(audio_path)
                    texto = transcripcion or "No se pudo transcribir el audio"
                else:
                    texto = "Error al procesar el audio"
            except Exception as e:
                app.logger.warning(f"⚠️ audio processing failed: {e}")
                texto = "Error al procesar el audio"
        elif 'document' in msg:
            es_archivo = True
            texto = (msg.get('document', {}).get('caption') or f"Archivo: {msg.get('document', {}).get('filename','sin nombre')}").strip()
        else:
            texto = f"[{msg.get('type', 'unknown')}] Mensaje no textual"

        app.logger.info(f"📝 Incoming {numero}: '{(texto or '')[:200]}' (imagen={es_imagen}, audio={es_audio}, archivo={es_archivo})")

        # --- GUARDO EL MENSAJE DEL USUARIO INMEDIATAMENTE para que el Kanban y la lista de chats lo reflejen ---
        try:
            guardar_mensaje_inmediato(numero, texto, config, imagen_url=public_url, es_imagen=es_imagen)
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo guardar mensaje inmediato en webhook: {e}")

        # Delegate ALL business logic to procesar_mensaje_unificado (single place to persist/respond).
        # Indicar a la función que el mensaje ya fue guardado (incoming_saved=True)
        processed_ok = procesar_mensaje_unificado(
            msg=msg,
            numero=numero,
            texto=texto,
            es_imagen=es_imagen,
            es_audio=es_audio,
            config=config,
            imagen_base64=imagen_base64,
            transcripcion=transcripcion,
            incoming_saved=True
        )

        if processed_ok:
            app.logger.info(f"✅ procesar_mensaje_unificado handled message {message_id} for {numero}")
            return 'OK', 200

        # If processing failed, we already saved the incoming message earlier; nothing more to do.
        app.logger.info(f"⚠️ procesar_mensaje_unificado returned False for {message_id}; message already persisted.")
        return 'OK', 200

    except Exception as e:
        app.logger.error(f"🔴 CRITICAL error in webhook: {e}")
        app.logger.error(traceback.format_exc())
        return 'Internal server error', 500

def registrar_respuesta_bot(numero, mensaje, respuesta, config=None, imagen_url=None, es_imagen=False, incoming_saved=False):
    """
    Save the bot response in a way that avoids duplicating the incoming user message.
    - If incoming_saved is True, try to update the existing incoming message row with respuesta using actualizar_respuesta().
    - Otherwise insert a new row using guardar_conversacion().
    Returns True on success, False otherwise.
    """
    try:
        if incoming_saved:
            try:
                # Prefer updating the existing incoming message so we don't insert a duplicate user row
                return actualizar_respuesta(numero, mensaje, respuesta, config)
            except Exception as e:
                app.logger.warning(f"⚠️ actualizar_respuesta failed, falling back to guardar_conversacion: {e}")
                # fallback to insert if update fails
                return guardar_conversacion(numero, mensaje, respuesta, config, imagen_url=imagen_url, es_imagen=es_imagen)
        else:
            return guardar_conversacion(numero, mensaje, respuesta, config, imagen_url=imagen_url, es_imagen=es_imagen)
    except Exception as e:
        app.logger.error(f"❌ registrar_respuesta_bot error: {e}")
        return False

def manejar_guardado_cita_unificado(save_cita, intent, numero, texto, historial, catalog_list, respuesta_text, incoming_saved, config):
    """
    Extrae y ejecuta la lógica que antes estaba inline dentro de:
        if save_cita or intent == "COMPRAR_PRODUCTO":
    Retorna True siempre que el flujo fue procesado (igual comportamiento previo).
    """
    try:
        # Ensure we have a mutable dict to work with (IA may return null)
        if not isinstance(save_cita, dict):
            save_cita = {}

        # Always ensure phone is present
        save_cita.setdefault('telefono', numero)

        info_cita = {
            'servicio_solicitado': save_cita.get('servicio_solicitado') or save_cita.get('servicio') or '',
            'fecha_sugerida': save_cita.get('fecha_sugerida'),
            'hora_sugerida': save_cita.get('hora_sugerida'),
            'nombre_cliente': save_cita.get('nombre_cliente') or save_cita.get('nombre'),
            'telefono': save_cita.get('telefono'),
            'detalles_servicio': save_cita.get('detalles_servicio') or {}
        }

        # Validate before saving
        try:
            completos, faltantes = validar_datos_cita_completos(info_cita, config)
        except Exception as _e:
            app.logger.warning(f"⚠️ validar_datos_cita_completos falló durante guardado unificado: {_e}")
            completos, faltantes = False, ['validacion_error']

        if not completos:
            app.logger.info(f"ℹ️ Datos iniciales incompletos para cita (faltantes: {faltantes}), intentando enriquecer desde mensaje/historial")
            try:
                enriquecido = extraer_info_cita_mejorado(texto or "", numero, historial=historial, config=config)
                if enriquecido and isinstance(enriquecido, dict):
                    # Merge only missing fields (do not overwrite existing valid values)
                    if not info_cita.get('servicio_solicitado') and enriquecido.get('servicio_solicitado'):
                        info_cita['servicio_solicitado'] = enriquecido.get('servicio_solicitado')
                    if not info_cita.get('fecha_sugerida') and enriquecido.get('fecha_sugerida'):
                        info_cita['fecha_sugerida'] = enriquecido.get('fecha_sugerida')
                    if not info_cita.get('hora_sugerida') and enriquecido.get('hora_sugerida'):
                        info_cita['hora_sugerida'] = enriquecido.get('hora_sugerida')
                    if not info_cita.get('nombre_cliente') and enriquecido.get('nombre_cliente'):
                        info_cita['nombre_cliente'] = enriquecido.get('nombre_cliente')
                    if enriquecido.get('detalles_servicio'):
                        info_cita.setdefault('detalles_servicio', {}).update(enriquecido.get('detalles_servicio') or {})
                    app.logger.info("🔁 Info cita enriquecida: %s", json.dumps({k: v for k, v in info_cita.items() if k in ['servicio_solicitado','fecha_sugerida','hora_sugerida','nombre_cliente']}))
                else:
                    app.logger.info("⚠️ Enriquecimiento no devolvió datos útiles")
            except Exception as _e:
                app.logger.warning(f"⚠️ Enriquecimiento de cita falló: {_e}")

        # Final attempt to save (may still return None -> handled as before)
        try:
            cita_id = guardar_cita(info_cita, config)
        except Exception as e:
            app.logger.error(f"🔴 Error guardando cita desde unificado: {e}")
            cita_id = None

        if cita_id:
            app.logger.info(f"✅ Cita guardada (unificada) ID: {cita_id}")
            if respuesta_text:
                enviar_mensaje(numero, respuesta_text, config)
                registrar_respuesta_bot(numero, texto, respuesta_text, config, incoming_saved=incoming_saved)
            try:
                enviar_alerta_cita_administrador(info_cita, cita_id, config)
            except Exception as e:
                app.logger.warning(f"⚠️ enviar_alerta_cita_administrador falló: {e}")
        else:
            try:
                completos2, faltantes2 = validar_datos_cita_completos(info_cita, config)
            except Exception:
                completos2, faltantes2 = False, ['fecha', 'hora', 'servicio']

            preguntas = []
            if 'servicio' in (faltantes2 or []):
                preguntas.append("¿Qué servicio o modelo te interesa? (ej. 'página web', 'silla escolar', SKU o nombre)")
            if 'fecha' in (faltantes2 or []):
                preguntas.append("¿Qué fecha prefieres? (ej. 'hoy', 'mañana' o '2025-11-10')")
            if 'hora' in (faltantes2 or []):
                preguntas.append("¿A qué hora te acomoda? (ej. 'a las 18:00' o '6pm')")
            if 'nombre' in (faltantes2 or []):
                preguntas.append("¿Cuál es tu nombre completo?")
            if not preguntas:
                preguntas = ["Faltan datos para completar la cita. ¿Puedes proporcionar la fecha y hora, por favor?"]

            follow_up = "Para agendar necesito lo siguiente:\n\n" + "\n".join(f"- {p}" for p in preguntas)
            follow_up += "\n\nResponde con los datos cuando puedas."

            enviar_mensaje(numero, follow_up, config)
            registrar_respuesta_bot(numero, texto, follow_up, config, incoming_saved=incoming_saved)

            app.logger.warning("⚠️ guardar_cita devolvió None — se solicitó al usuario los datos faltantes")
        return True

    except Exception as e:
        app.logger.error(f"🔴 Error inesperado en manejar_guardado_cita_unificado: {e}")
        return True  # Mantener comportamiento anterior: consumir la intención y devolver True

def comprar_producto(numero, config=None, limite_historial=8, modelo="deepseek-chat", max_tokens=700):
    """
    Igual que antes pero:
     - Pide a la IA un resumen (contexto) en sus propias palabras y lo usa en la alerta.
     - NOTA: ya no hace acciones adicionales cuando el método de pago es 'transferencia'.
    Devuelve: respuesta_text (string) o None.
    """
    if config is None:
        config = obtener_configuracion_por_host()

    try:
        # 1) Obtener historial y último mensaje
        historial = obtener_historial(numero, limite=limite_historial, config=config) or []
        ultimo = (historial[-1].get('mensaje') or "").strip() if historial else ""
        partes = []
        for h in historial:
            if h.get('mensaje'):
                partes.append(f"Usuario: {h.get('mensaje')}")
            if h.get('respuesta'):
                partes.append(f"Asistente: {h.get('respuesta')}")
        historial_text = "\n".join(partes) or (f"Usuario: {ultimo}" if ultimo else "Sin historial previo.")

        # 2) Llamada IA: extraer pedido estructurado (mismo prompt estricto de antes)
        prompt = f"""
Eres un extractor estructurado. A partir del historial y del último mensaje del usuario,
devuelve SOLO un JSON con la siguiente estructura EXACTA:

{{
  "respuesta_text": "Texto breve en español para enviar al usuario (1-4 líneas).",
  "productos": [
    {{
      "sku_o_nombre": "CIANI OHE 305",
      "cantidad": 4,
      "precio_unitario": 300.0,
      "precio_total_item": 1200.0
    }}
  ],
  "metodo_pago": "tarjeta" | "transferencia" | "efectivo" | null,
  "direccion": "Texto de dirección completa" | null,
  "nombre_cliente": "Nombre si se detecta" | null,
  "precio_total": 1200.0 | null,
  "ready_to_notify": true|false,
  "confidence": 0.0-1.0
}}

Reglas: NO inventes precios si hay catálogo; incluye todos los productos y cantidades detectadas.
"""
        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": modelo,
            "messages": [{"role": "user", "content": prompt},
                         {"role": "user", "content": f"HISTORIAL:\n{historial_text}\n\nÚLTIMO MENSAJE:\n{ultimo}"}],
            "temperature": 0.0,
            "max_tokens": max_tokens
        }
        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        raw = data['choices'][0]['message']['content']
        if isinstance(raw, list):
            raw = "".join([(r.get('text') if isinstance(r, dict) else str(r)) for r in raw])
        raw = str(raw).strip()

        match = re.search(r'(\{.*\})', raw, re.DOTALL)
        if not match:
            app.logger.warning(f"⚠️ comprar_producto: IA no devolvió JSON estructurado. Raw: {raw[:1000]}")
            fallback_text = re.sub(r'\s+', ' ', raw)[:1000]
            return fallback_text or None

        try:
            extracted = json.loads(match.group(1))
        except Exception as e:
            app.logger.error(f"🔴 comprar_producto: fallo parseando JSON IA: {e} -- raw: {match.group(1)[:1000]}")
            return None

        respuesta_text = extracted.get('respuesta_text') or ""
        productos = extracted.get('productos') or []
        metodo_pago = extracted.get('metodo_pago')
        direccion = extracted.get('direccion')
        nombre_cliente = extracted.get('nombre_cliente')
        precio_total_ia = extracted.get('precio_total')
        ready_to_notify = bool(extracted.get('ready_to_notify')) if extracted.get('ready_to_notify') is not None else False
        confidence = float(extracted.get('confidence') or 0.0)

        # 3) Normalizar/enriquecer productos y calcular totales (mismo comportamiento)
        productos_norm = []
        suma_total = 0.0
        any_price_known = False
        for p in productos:
            try:
                name_raw = (p.get('sku_o_nombre') or p.get('nombre') or p.get('sku') or '').strip()
                qty = int(p.get('cantidad') or 0)
                if qty <= 0:
                    qty = 1
                pu = None
                if p.get('precio_unitario') not in (None, '', 0):
                    try:
                        pu = float(p.get('precio_unitario'))
                    except Exception:
                        pu = None

                producto_db = None
                if name_raw:
                    producto_db = obtener_producto_por_sku_o_nombre(name_raw, config)
                if not pu and producto_db:
                    cand = producto_db.get('precio_menudeo') or producto_db.get('precio') or producto_db.get('costo') or producto_db.get('precio_mayoreo')
                    try:
                        if cand not in (None, ''):
                            pu = float(re.sub(r'[^\d.]', '', str(cand)))
                    except Exception:
                        pu = None

                precio_total_item = None
                if pu is not None:
                    precio_total_item = round(pu * qty, 2)
                    suma_total += precio_total_item
                    any_price_known = True
                else:
                    if p.get('precio_total_item') not in (None, ''):
                        try:
                            precio_total_item = float(re.sub(r'[^\d.]', '', str(p.get('precio_total_item'))))
                            suma_total += precio_total_item
                            any_price_known = True
                        except Exception:
                            precio_total_item = None

                productos_norm.append({
                    "sku_o_nombre": name_raw or None,
                    "cantidad": qty,
                    "precio_unitario": pu,
                    "precio_total_item": precio_total_item,
                    "catalog_row": producto_db
                })
            except Exception as e:
                app.logger.warning(f"⚠️ comprar_producto: error procesando item {p}: {e}")
                continue

        precio_total_calc = round(suma_total, 2) if any_price_known else (float(precio_total_ia) if precio_total_ia not in (None, '') else None)

        datos_compra = {
            "productos": productos_norm,
            "precio_total": precio_total_calc,
            "metodo_pago": metodo_pago or None,
            "direccion": direccion or None,
            "nombre_cliente": nombre_cliente or None,
            "numero_cliente": numero,
            "ready_to_notify": ready_to_notify,
            "confidence": confidence
        }

        app.logger.info(f"🔍 comprar_producto - datos_compra normalizados: {json.dumps({'productos_count': len(productos_norm), 'precio_total': datos_compra['precio_total'], 'ready_to_notify': ready_to_notify, 'confidence': confidence}, ensure_ascii=False)}")

        # 4) Pedir a la IA que resuma el contexto en sus propias palabras (2-4 líneas)
        try:
            resumen_prompt = f"""
Resume en 2-4 líneas en español, con lenguaje natural, el contexto de la conversación
para que un asesor humano entienda rápidamente. Usa SOLO el historial y la lista de productos a continuación.
No incluyas números de teléfono ni direcciones completas en el resumen.

HISTORIAL:
{historial_text}

PRODUCTOS DETECTADOS:
{json.dumps(productos_norm, ensure_ascii=False)[:3000]}

Devuelve únicamente el resumen de 2-4 líneas en español.
"""
            payload_sum = {"model": "deepseek-chat", "messages": [{"role": "user", "content": resumen_prompt}], "temperature": 0.2, "max_tokens": 200}
            rsum = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload_sum, timeout=15)
            rsum.raise_for_status()
            sum_data = rsum.json()
            contexto_resumido = sum_data['choices'][0]['message']['content'].strip()
            if isinstance(contexto_resumido, list):
                contexto_resumido = " ".join([c.get('text') if isinstance(c, dict) else str(c) for c in contexto_resumido])
            contexto_resumido = re.sub(r'\n\s+\n', '\n\n', contexto_resumido).strip()
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo generar resumen IA de contexto: {e}")
            contexto_resumido = historial_text if len(historial_text) <= 1200 else historial_text[-1200:]

        # 5) Evitar re-notificaciones
        estado_actual = obtener_estado_conversacion(numero, config)
        already_notified = False
        try:
            if estado_actual and estado_actual.get('datos') and isinstance(estado_actual.get('datos'), dict):
                if estado_actual['datos'].get('pedido_notificado'):
                    already_notified = False
        except Exception:
            already_notified = False

        # 6) Notificar solo si IA indicó ready_to_notify y datos completos
        # NOTE: treat transferencias as an intent to buy — allow notification even if ready_to_notify==False,
        # so advisors get alerted when user confirmed transfer and required fields exist.
        should_notify = False
        try:
            if datos_compra.get('ready_to_notify'):
                should_notify = True
            else:
                # If payment method is transfer and essential fields are present, notify anyway
                mp = datos_compra.get('metodo_pago') or ''
                if mp and 'transfer' in str(mp).lower():
                    if datos_compra.get('direccion') and datos_compra.get('precio_total') is not None and len(productos_norm) > 0:
                        should_notify = True
                        app.logger.info(f"ℹ️ comprar_producto: metodo_pago='transferencia' detectado -> forzando notificación si campos completos.")
        except Exception:
            should_notify = False

        if should_notify and not already_notified and datos_compra.get('metodo_pago') and datos_compra.get('direccion') and datos_compra['precio_total'] is not None and len(productos_norm) > 0:
            try:
                asesor = obtener_siguiente_asesor(config)
                asesor_tel = asesor.get('telefono') if asesor and isinstance(asesor, dict) else None
                asesor_email = asesor.get('email') if asesor and isinstance(asesor, dict) else None
                cliente_mostrado = obtener_nombre_mostrado_por_numero(numero, config) or (datos_compra.get('nombre_cliente') or 'No especificado')

                # Construir líneas de items legibles
                lineas_items = []
                for it in productos_norm:
                    qty = it.get('cantidad') or 1
                    nombre = it.get('sku_o_nombre') or 'Producto'
                    pu = it.get('precio_unitario')
                    pt = it.get('precio_total_item')
                    if pu is not None:
                        lineas_items.append(f"• {qty} x {nombre} @ ${pu:,.2f} = ${pt:,.2f}")
                    elif pt is not None:
                        lineas_items.append(f"• {qty} x {nombre} = ${pt:,.2f}")
                    else:
                        lineas_items.append(f"• {qty} x {nombre} (precio por confirmar)")

                # Construir mensaje de alerta con el resumen generado por la IA
                mensaje_alerta = (
                    f"🔔 *Pedido confirmado por cliente*\n\n"
                    f"👤 *Cliente:* {cliente_mostrado}\n"
                    f"📞 *Número:* {numero}\n\n"
                    f"🧾 *Detalles del pedido:*\n"
                    f"{chr(10).join(lineas_items)}\n\n"
                    f"• *Precio total:* ${datos_compra['precio_total']:,.2f}\n"
                    f"• *Método de pago:* {datos_compra.get('metodo_pago')}\n"
                    f"• *Dirección:* {datos_compra.get('direccion')}\n\n"
                    f"💬 *Contexto (IA - resumen):*\n{contexto_resumido}\n"
                )

                mensaje_alerta += "\nPor favor, contactar al cliente para procesar pago y entrega."
                if asesor_email:
                    try:
                        service = autenticar_google_calendar(config)
                        if service:
                            # Crear evento mínimo para notificar al asesor por email
                            now_dt = datetime.now(tz_mx)
                            start_iso = now_dt.isoformat()
                            end_iso = (now_dt + timedelta(hours=1)).isoformat()
                            event_for_asesor = {
                                'summary': f"Notificación: pedido de {cliente_mostrado}",
                                'location': config.get('direccion', ''),
                                'description': f"{contexto_resumido}\n\nDetalles del pedido enviado por WhatsApp.\nNúmero cliente: {numero}",
                                'start': {'dateTime': start_iso, 'timeZone': 'America/Mexico_City'},
                                'end': {'dateTime': end_iso, 'timeZone': 'America/Mexico_City'},
                                'attendees': [{'email': asesor_email}],
                                'reminders': {'useDefault': False, 'overrides': [{'method': 'email', 'minutes': 10}]}
                            }
                            try:
                                # Insertar en primary y notificar asistentes (sendUpdates='all')
                                primary_calendar = os.getenv('GOOGLE_CALENDAR_ID', 'primary')
                                created_evt = service.events().insert(calendarId=primary_calendar, body=event_for_asesor, sendUpdates='all').execute()
                                app.logger.info(f"✅ Evento Calendar creado para asesor {asesor_email}: {created_evt.get('htmlLink')}")
                            except Exception as e_evt:
                                app.logger.warning(f"⚠️ No se pudo crear evento Calendar para asesor {asesor_email}: {e_evt}")
                        else:
                            app.logger.warning("⚠️ autenticar_google_calendar devolvió None, no se creó evento para asesor")
                    except Exception as e:
                        app.logger.warning(f"⚠️ Error intentando notificar a asesor por Calendar ({asesor_email}): {e}")

                # Enviar a asesor y al número fijo
                targets = []
                if asesor_tel:
                    targets.append(asesor_tel)
                targets.append("5214493432744")

                # collect successful targets to decide kanban move
                notified_targets = []
                for t in targets:
                    try:
                        sent = enviar_mensaje(t, mensaje_alerta, config)
                        if sent:
                            notified_targets.append(t)
                        app.logger.info(f"✅ Alerta de pedido enviada a {t}")
                    except Exception as e:
                        app.logger.warning(f"⚠️ No se pudo notificar a {t}: {e}")

                # Marcar estado para evitar re-notificaciones
                nuevo_estado = {
                    'pedido_confirmado': datos_compra,
                    'pedido_notificado': True,
                    'timestamp': datetime.now().isoformat()
                }
                actualizar_estado_conversacion(numero, "PEDIDO_CONFIRMADO", "pedido_notificado", nuevo_estado, config)

                # If at least one notification was successfully sent, move the chat to "Resueltos" (closed)
                try:
                    if notified_targets:
                        # 4 = 'Resueltos' as created by crear_tablas_kanban default
                        actualizar_columna_chat(numero, 4, config)
                        app.logger.info(f"✅ Chat {numero} movido a 'Resueltos' (columna 4) tras notificación de pedido")
                    else:
                        app.logger.info(f"ℹ️ comprar_producto: no se notificó a ningún objetivo; no se moverá el Kanban para {numero}")
                except Exception as e:
                    app.logger.warning(f"⚠️ No se pudo mover chat a columna 'Resueltos' para {numero}: {e}")

            except Exception as e:
                app.logger.error(f"🔴 Error notificando asesores tras compra confirmada: {e}")
        else:
            if already_notified:
                app.logger.info("ℹ️ comprar_producto: pedido ya notificado previamente; omitiendo re-notificación.")
            elif not datos_compra['ready_to_notify'] and not (datos_compra.get('metodo_pago') and 'transfer' in str(datos_compra.get('metodo_pago')).lower()):
                app.logger.info("ℹ️ comprar_producto: IA no marcó ready_to_notify -> esperando más confirmación.")
            else:
                app.logger.info("ℹ️ comprar_producto: datos incompletos para notificar (p.ej. falta precio_total/metodo/direccion).")

        # 7) Devolver la respuesta que debe enviarse al cliente (el llamador se encarga de enviar/registrar)
        if respuesta_text:
            respuesta_text = aplicar_restricciones(respuesta_text, numero, config)
        return respuesta_text or None

    except requests.exceptions.RequestException as e:
        app.logger.error(f"🔴 comprar_producto - request error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            app.logger.error(f"🔴 API body: {e.response.text[:1000]}")
        return None
    except Exception as e:
        app.logger.error(f"🔴 comprar_producto error: {e}")
        app.logger.error(traceback.format_exc())
        return None

# Add below existing helper functions (e.g. after other CREATE TABLE helpers)
def _ensure_columnas_precios_table(conn):
    cur = conn.cursor()
    try:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS columnas_precios (
                id INT AUTO_INCREMENT PRIMARY KEY,
                tenant VARCHAR(255) NOT NULL,
                table_name VARCHAR(64) NOT NULL,
                hidden_json JSON DEFAULT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                UNIQUE KEY uq_tenant_table (tenant, table_name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        """)
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except:
            pass
    finally:
        cur.close()

@app.route('/configuracion/precios/columnas', methods=['GET'])
def get_columnas_precios():
    """Return saved hidden columns for current tenant + table (query param 'table')"""
    config = obtener_configuracion_por_host()
    table = request.args.get('table', 'user')
    try:
        conn = get_db_connection(config)
        _ensure_columnas_precios_table(conn)
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT hidden_json FROM columnas_precios WHERE tenant=%s AND table_name=%s LIMIT 1",
                    (config.get('dominio'), table))
        row = cur.fetchone()
        cur.close()
        conn.close()
        hidden = {}
        if row and row.get('hidden_json'):
            try:
                hidden = json.loads(row['hidden_json'])
            except Exception:
                hidden = {}
        return jsonify({'hidden': hidden})
    except Exception as e:
        app.logger.warning(f"⚠️ get_columnas_precios error: {e}")
        return jsonify({'hidden': {}})

@app.route('/configuracion/precios/columnas', methods=['POST'])
def save_columnas_precios():
    """Save hidden columns state for current tenant + table"""
    config = obtener_configuracion_por_host()
    data = request.get_json(silent=True) or {}
    table = (data.get('table') or 'user')
    hidden = data.get('hidden') or {}
    try:
        conn = get_db_connection(config)
        _ensure_columnas_precios_table(conn)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO columnas_precios (tenant, table_name, hidden_json, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON DUPLICATE KEY UPDATE hidden_json = VALUES(hidden_json), updated_at = NOW()
        """, (config.get('dominio'), table, json.dumps(hidden, ensure_ascii=False)))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"🔴 save_columnas_precios error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/configuracion/precios/columnas/restablecer', methods=['POST'])
def reset_columnas_precios():
    """Reset (clear) saved hidden columns for current tenant.
       If JSON body contains 'table' it clears only that table; otherwise clears all tenant entries."""
    config = obtener_configuracion_por_host()
    data = request.get_json(silent=True) or {}
    table = data.get('table')
    try:
        conn = get_db_connection(config)
        _ensure_columnas_precios_table(conn)
        cur = conn.cursor()
        if table:
            cur.execute("DELETE FROM columnas_precios WHERE tenant=%s AND table_name=%s", (config.get('dominio'), table))
        else:
            cur.execute("DELETE FROM columnas_precios WHERE tenant=%s", (config.get('dominio'),))
        conn.commit()
        cur.close()
        conn.close()
        return jsonify({'success': True})
    except Exception as e:
        app.logger.error(f"🔴 reset_columnas_precios error: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

def send_good_morning_to_tenant(config):
    """Send the good morning message to all advisors configured for the given tenant."""
    try:
        cfg = load_config(config)
        asesores = cfg.get('asesores_list') or []
        if not asesores:
            app.logger.info(f"ℹ️ No advisors configured for tenant {config.get('dominio')}")
            return

        negocio_nombre = (cfg.get('negocio') or {}).get('negocio_nombre') or config.get('dominio') or ''
        default_msg = f"¡Buenos días! Les deseo un excelente día de trabajo{(' en ' + negocio_nombre) if negocio_nombre else ''}."
        message = os.getenv("GOOD_MORNING_MESSAGE", default_msg)

        for a in asesores:
            telefono = (a.get('telefono') or '').strip()
            if not telefono:
                app.logger.warning(f"⚠️ Advisor without phone in tenant {config.get('dominio')}: {a}")
                continue
            try:
                enviar_mensaje(telefono, message, config)
                app.logger.info(f"✅ Good morning sent to advisor {telefono} (tenant={config.get('dominio')})")
            except Exception as e:
                app.logger.warning(f"⚠️ Failed to send good morning to {telefono} (tenant={config.get('dominio')}): {e}")
    except Exception as e:
        app.logger.error(f"🔴 send_good_morning_to_tenant error for {config.get('dominio')}: {e}")

def send_good_morning_to_all():
    """Iterate all tenants and send the good morning message to their advisors."""
    app.logger.info("🔔 Running scheduled good-morning job for all tenants...")
    for tenant_key, config in NUMEROS_CONFIG.items():
        try:
            # Use app context because enviar_mensaje / DB functions rely on it
            with app.app_context():
                send_good_morning_to_tenant(config)
        except Exception as e:
            app.logger.error(f"🔴 Error sending good morning for tenant {config.get('dominio')}: {e}")

def start_good_morning_scheduler():
    """Start a background thread that sends a good-morning message every day at configured hour (default 08:00 America/Mexico_City)."""
    global GOOD_MORNING_THREAD_STARTED
    if GOOD_MORNING_THREAD_STARTED:
        app.logger.info("ℹ️ Good morning scheduler already started")
        return

    if os.getenv("GOOD_MORNING_ENABLED", "true").lower() != "true":
        app.logger.info("ℹ️ Good morning scheduler disabled via GOOD_MORNING_ENABLED != 'true'")
        return

    # Accept either "HH:MM" or just "HH" in env var; default to 08:00
    time_str = os.getenv("GOOD_MORNING_TIME", "08:00").strip()
    try:
        if ":" in time_str:
            parts = time_str.split(":")
            hour = int(parts[0]) % 24
            minute = int(parts[1]) % 60
        else:
            hour = int(time_str) % 24
            minute = 0
    except Exception:
        app.logger.warning(f"⚠️ Invalid GOOD_MORNING_TIME='{time_str}', falling back to 08:00")
        hour, minute = 8, 0

    def _worker():
        app.logger.info(f"🕐 Good morning scheduler started (daily at {hour:02d}:{minute:02d} {tz_mx.zone})")
        # small initial delay so server finishes startup tasks
        time.sleep(5)

        while True:
            try:
                now = datetime.now(tz_mx)
                # Build today's target in tz_mx as a naive dt localized to tz_mx
                target_naive = datetime(now.year, now.month, now.day, hour, minute, 0)
                try:
                    target = tz_mx.localize(target_naive)
                except Exception:
                    # if already tz-aware for some reason, fallback
                    target = target_naive.replace(tzinfo=tz_mx)

                # If the target time is already passed for today, schedule for tomorrow
                if now >= target:
                    target = target + timedelta(days=1)

                seconds_to_sleep = (target - now).total_seconds()
                app.logger.info(f"⏳ Sleeping {int(seconds_to_sleep)}s until next good-morning run at {target.isoformat()}")
                # Sleep until scheduled time (will resume after sleep or be interrupted on exception)
                time.sleep(max(1, seconds_to_sleep))

                # At scheduled time: execute job inside app context
                try:
                    with app.app_context():
                        send_good_morning_to_all()
                except Exception as e:
                    app.logger.error(f"🔴 Exception while sending good-morning messages: {e}")
            except Exception as loop_e:
                app.logger.error(f"🔴 Unexpected error in good-morning scheduler loop: {loop_e}")
                # Sleep a short time before retrying loop to avoid tight error loops
                time.sleep(60)

    t = threading.Thread(target=_worker, daemon=True, name="good_morning_scheduler")
    t.start()
    GOOD_MORNING_THREAD_STARTED = True
    app.logger.info("✅ Good morning scheduler thread launched")

def procesar_mensaje_unificado(msg, numero, texto, es_imagen, es_audio, config,
                               imagen_base64=None, transcripcion=None,
                               incoming_saved=False, es_mi_numero=False, es_archivo=False):
    """
    Flujo unificado para procesar un mensaje entrante.
    incoming_saved: boolean indicating the webhook already persisted the incoming message
                    (so callers can avoid double-saving). Default False for backward compatibility.
    """
    try:
        if config is None:
            config = obtener_configuracion_por_host()

        texto_norm = (texto or "").strip().lower()
        #aqui pon el codigo
        # --- Preparar contexto y catálogo ---
        historial = obtener_historial(numero, limite=6, config=config) or []
        historial_text = ""
        for h in historial:
            if h.get('mensaje'):
                historial_text += f"Usuario: {h.get('mensaje')}\n"
            if h.get('respuesta'):
                historial_text += f"Asistente: {h.get('respuesta')}\n"
                # --- DeepSeek prompt: detectar si el mensaje solicita información de producto ---
        producto_aplica = "NO_APLICA"
        try:
            # Build a minimal, strict prompt that forces the model to answer ONLY with SI_APLICA or NO_APLICA
            ds_prompt = (
                "Tu única tarea: leyendo el historial de conversación y el mensaje actual, "
                "decide SI el cliente está pidiendo información sobre un producto (precio, disponibilidad, catálogo, SKU, características, fotos, etc.).\n\n"
                "RESPONDE SOLO CON UNA PALABRA EXACTA: SI_APLICA  o  NO_APLICA\n"
                "No añadas explicaciones, ejemplos, ni signos adicionales.\n\n"
                "HISTORIAL:\n"
                f"{historial_text.strip()}\n\n"
                "MENSAJE ACTUAL:\n"
                f"{texto or ''}\n\n"
                "Si el usuario solicita precio, catálogo, SKU, características técnicas, imágenes del producto, disponibilidad, comparación entre modelos o cómo comprar un producto, responde SI_APLICA. En cualquier otro caso responde NO_APLICA."
            )

            headers_ds = {
                "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                "Content-Type": "application/json"
            }
            payload_ds = {
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": ds_prompt}],
                "temperature": 0.0,
                "max_tokens": 16
            }

            resp_ds = requests.post(DEEPSEEK_API_URL, headers=headers_ds, json=payload_ds, timeout=8)
            resp_ds.raise_for_status()
            ds_data = resp_ds.json()
            raw_ds = ds_data['choices'][0]['message']['content']
            if isinstance(raw_ds, list):
                raw_ds = "".join([(r.get('text') if isinstance(r, dict) else str(r)) for r in raw_ds])
            raw_ds = (raw_ds or "").strip().upper()

            m = re.search(r'\b(SI_APLICA|NO_APLICA)\b', raw_ds)
            if m:
                producto_aplica = m.group(1)
            else:
                # If model responded unexpectedly, apply a conservative fallback
                producto_aplica = "SI_APLICA" if any(
                    kw in (texto or "").lower() for kw in
                    ['precio', 'catalogo', 'catálogo', 'sku', 'disponibilidad', '¿tiene', 'foto', 'imagen', '¿cuánto', 'cotización', 'precio?', 'precio ']
                ) else "NO_APLICA"

            app.logger.info(f"🔎 DeepSeek product-detector -> {producto_aplica} (raw: {raw_ds[:200]})")
        except Exception as e:
            app.logger.warning(f"⚠️ DeepSeek detection failed: {e}; using keyword fallback")
            # Simple fallback: look for product-related tokens in message + history
            combined = (texto or "") + "\n" + (historial_text or "")
            if any(kw in combined.lower() for kw in ['precio', 'catalogo', 'catálogo', 'sku', 'disponibilidad', 'foto', 'imagen', 'cotización', 'precio?', '¿cuánto']):
                producto_aplica = "SI_APLICA"
                app.logger.info("🔎 Fallback product-detector -> SI_APLICA")
            else:
                producto_aplica = "NO_APLICA"
                app.logger.info("🔎 Fallback product-detector -> NO_APLICA")
            app.logger.info(f"🔎 Fallback product-detector -> {producto_aplica}")
        # --- end DeepSeek product detection ---
        precios = obtener_todos_los_precios(config) or []
        texto_catalogo = build_texto_catalogo(precios, limit=40)

        catalog_list = []
        for p in precios:
            try:
                catalog_list.append({
                    "sku": (p.get('sku') or '').strip(),
                    "servicio": (p.get('subcategoria') or p.get('categoria') or p.get('modelo') or '').strip(),
                    "precio_menudeo": str(p.get('precio_menudeo') or p.get('precio') or p.get('costo') or ""),
                    "precio_mayoreo": str(p.get('precio_mayoreo') or ""),
                    "inscripcion": str(p.get('inscripcion') or ""),
                    "mensualidad": str(p.get('mensualidad') or ""),
                    "imagen": str(p.get('imagen') or ""),
                    "descripcion": str(p.get('descripcion') or "")
                })
            except Exception:
                continue
        transferencia = obtener_datos_de_transferencia(config) or []
        transfer_list = []
        for t in transferencia:
            try:
                transfer_list.append({
                    "cuenta_bancaria": (p.get('transferencia_numero') or '').strip(),
                    "nombre_transferencia": (p.get('transferencia_nombre') or '').strip(),
                    "banco_transferencia": str(p.get('transferencia_banco') or "")
                })
            except Exception:
                continue
        cfg_full = load_config(config)
        asesores_block = format_asesores_block(cfg_full)
                 # --- NEW: expose negocio.description and negocio.que_hace to the AI context ---
        try:
            negocio_cfg = (cfg_full.get('negocio') or {})  # may be {}
            negocio_descripcion = (negocio_cfg.get('descripcion') or '').strip()
            negocio_que_hace = (negocio_cfg.get('que_hace') or '').strip()
            # Truncate to keep prompt/token usage reasonable
            MAX_CFG_CHARS = 5000
            negocio_descripcion_short = negocio_descripcion[:MAX_CFG_CHARS]
            negocio_que_hace_short = negocio_que_hace[:MAX_CFG_CHARS]
        except Exception:
            negocio_descripcion_short = ""
            negocio_que_hace_short = ""
        # --- NEW: expose the assistant/business display name from configuration to the system prompt ---
        try:
            ia_nombre = (cfg_full.get('negocio') or {}).get('ia_nombre') or (cfg_full.get('negocio') or {}).get('app_nombre') or "Asistente"
            negocio_nombre = (cfg_full.get('negocio') or {}).get('negocio_nombre') or ""
            
        except Exception:
            ia_nombre = "Asistente"
            negocio_nombre = ""
        multimodal_info = ""
        if es_imagen:
            multimodal_info += "El mensaje incluye una imagen enviada por el usuario.\n"
            if imagen_base64:
                multimodal_info += "Se proporciona la imagen codificada en base64 para análisis.\n"
            if isinstance(msg, dict) and msg.get('image', {}).get('caption'):
                multimodal_info += f"Caption: {msg['image'].get('caption')}\n"
        if es_audio:
            multimodal_info += "El mensaje incluye audio y se ha provisto transcripción.\n"
            if transcripcion:
                multimodal_info += f"Transcripción: {transcripcion}\n"

        # --- System prompt (strict rules to avoid hallucinations) ---
        system_prompt = f"""
Eres el asistente conversacional del negocio. Tu tarea: decidir la intención del usuario y preparar exactamente lo
que el servidor debe ejecutar. Dispones de:
- Historial (últimos mensajes):\n{historial_text}
- Mensaje actual (texto): {texto or '[sin texto]'}
- Datos multimodales: {multimodal_info}
- Catálogo (estructura JSON con sku, servicio, precios): se incluye en el mensaje del usuario.

- Datos de transferencia (estructura JSON): se incluye en el mensaje del usuario.

Reglas ABSOLUTAS — LEE ANTES DE RESPONDER:
1) NO INVENTES NINGÚN PROGRAMA, DIPLOMADO, CARRERA, SKU, NI PRECIO. Solo puedes usar los items EXACTOS que están en el catálogo JSON recibido.
2) Si el usuario pregunta por "programas" o "qué programas tienes", responde listando únicamente los servicios/ SKUs presentes en el catálogo JSON.
3) Si el usuario solicita detalles de un programa, devuelve precios/datos únicamente si el SKU o nombre coincide con una entrada del catálogo. Si no hay coincidencia exacta, responde que "no está en el catálogo" y pregunta si quiere que busques algo similar.
4) Si el usuario solicita un PDF/catálogo/folleto y hay un documento publicado, responde con intent=ENVIAR_DOCUMENTO y document debe contener la URL o el identificador del PDF; si no hay PDF disponible, devuelve intent=RESPONDER_TEXTO y explica que no hay PDF publicado.
5) Responde SOLO con un JSON válido (objeto) en la parte principal de la respuesta. No incluyas texto fuera del JSON.
6) El JSON debe tener estas claves mínimas:
   - intent: one of ["INFORMACION_SERVICIOS_O_PRODUCTOS","DATOS_TRANSFERENCIA","RESPONDER_TEXTO","ENVIAR_IMAGEN","ENVIAR_DOCUMENTO","GUARDAR_CITA","PASAR_ASESOR","COMPRAR_PRODUCTO","SOLICITAR_DATOS","NO_ACTION","ENVIAR_CATALOGO","ENVIAR_TEMARIO","ENVIAR_FLYER","ENVIAR_PDF"]
   - respuesta_text: string
   - image: filename_or_url_or_null
   - document: url_or_null
   - save_cita: object|null
   - notify_asesor: boolean
   - followups: [ ... ]
   - confidence: 0.0-1.0
   - source: "catalog" | "none"
7) Si no estás seguro, usa NO_ACTION con confidence baja (<0.4).
8) Mantén respuesta_text concisa (1-6 líneas) y no incluyas teléfonos ni tokens.
"""

        user_content = {
            "mensaje_actual": texto or "",
            "es_imagen": bool(es_imagen),
            "es_audio": bool(es_audio),
            "transcripcion": transcripcion or "",
            "transferencias": transfer_list,
            "catalogo_texto_resumen": texto_catalogo
        }
        if producto_aplica == "SI_APLICA":
            user_content["catalogo"] = catalog_list
            app.logger.info("🔎 producto_aplica=SI_APLICA -> including full catalog in DeepSeek payload")
        else:
            app.logger.info("🔎 producto_aplica=NO_APLICA -> omitting full catalog from DeepSeek payload")

        payload_messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)}
        ]

        headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "deepseek-chat", "messages": payload_messages, "temperature": 0.2, "max_tokens": 800}

        resp = requests.post(DEEPSEEK_API_URL, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        raw = data['choices'][0]['message']['content']
        if isinstance(raw, list):
            raw = "".join([(r.get('text') if isinstance(r, dict) else str(r)) for r in raw])
        raw = str(raw).strip()

        match = re.search(r'(\{.*\}|\[.*\])', raw, re.DOTALL)
        if not match:
            app.logger.warning("⚠️ IA no devolvió JSON en procesar_mensaje_unificado. Respuesta cruda: " + raw[:300])
            fallback_text = re.sub(r'\s+', ' ', raw)[:1000]
            if fallback_text:
                enviar_mensaje(numero, fallback_text, config)
                registrar_respuesta_bot(numero, texto, fallback_text, config, incoming_saved=incoming_saved)
                return True
            return False

        try:
            decision = json.loads(match.group(1))
        except Exception as e:
            app.logger.error(f"🔴 Error parseando JSON IA: {e} -- raw snippet: {match.group(1)[:500]}")
            return False

        intent = (decision.get('intent') or 'NO_ACTION').upper()
        respuesta_text = decision.get('respuesta_text') or ""
        image_field = decision.get('image')
        document_field = decision.get('document')
        save_cita = decision.get('save_cita')
        notify_asesor = bool(decision.get('notify_asesor'))
        followups = decision.get('followups') or []
        source = decision.get('source') or "none"

        # Seguridad: validar servicio si viene de catálogo
        if source == "catalog" and decision.get('save_cita'):
            svc = decision['save_cita'].get('servicio_solicitado') or ""
            svc_lower = svc.strip().lower()
            found = False
            for item in catalog_list:
                if item.get('sku', '').strip().lower() == svc_lower or item.get('subcategoria', '').strip().lower() == svc_lower:
                    found = True
                    break
            if not found:
                app.logger.warning("⚠️ IA intentó guardar cita con servicio que NO está en catálogo. Abortando guardar.")
                enviar_mensaje(numero, "Lo siento, ese programa no está en nuestro catálogo. ¿Cuál programa te interesa exactamente?", config)
                registrar_respuesta_bot(numero, texto, "Lo siento, ese programa no está en nuestro catálogo.", config, incoming_saved=incoming_saved)
                return True

        # ENVIAR_DOCUMENTO fallback si IA pidió documento pero no lo pasó
        if intent == "ENVIAR_DOCUMENTO" and not document_field:
            app.logger.info("📚 IA requested ENVIAR_DOCUMENTO without document_field -> attempting enviar_catalogo()")
            try:
                sent = enviar_catalogo(numero, original_text=texto, config=config)
                msg_resp = "Te envié el catálogo solicitado." if sent else "No encontré catálogo publicado."
                registrar_respuesta_bot(numero, texto, msg_resp, config, incoming_saved=incoming_saved)
                return True
            except Exception as e:
                app.logger.error(f"🔴 Fallback enviar_catalogo() falló: {e}")
        # GUARDAR CITA
                #Comprar producto
        if intent == "COMPRAR_PRODUCTO":
            comprar_producto_text = comprar_producto(numero, config=config)
            if comprar_producto_text:
                enviar_mensaje(numero, comprar_producto_text, config)
                registrar_respuesta_bot(numero, texto, comprar_producto_text, config, incoming_saved=incoming_saved)
                return True
        # GUARDAR CITA
        if save_cita:
            manejar_guardado_cita_unificado(save_cita, intent, numero, texto, historial, catalog_list, respuesta_text, incoming_saved, config)
            return True
        if (intent == "ENVIAR_CATALOGO") or (intent == "ENVIAR_TEMARIO") or (intent == "ENVIAR_FLYER") or (intent == "ENVIAR_PDF"):
            try:
                sent = enviar_catalogo(numero, original_text=texto, config=config)
                # registrar respuesta evitando duplicados
                msg_resp = "Se envió el catálogo solicitado." if sent else "No se encontró un catálogo para enviar."
                registrar_respuesta_bot(numero, texto, msg_resp, config, incoming_saved=incoming_saved)
                return True
            except Exception as e:
                app.logger.error(f"🔴 Error sending catalog shortcut: {e}")
                # continue to AI flow as fallback
        # ENVIAR IMAGEN
        if intent == "ENVIAR_IMAGEN" and image_field:
            try:
                sent = enviar_imagen(numero, image_field, config)
                if respuesta_text:
                    enviar_mensaje(numero, respuesta_text, config)
                registrar_respuesta_bot(
                    numero, texto, respuesta_text, config,
                    imagen_url=(image_field if isinstance(image_field, str) and image_field.startswith('http') else f"/uploads/productos/{image_field}"),
                    es_imagen=True,
                    incoming_saved=incoming_saved
                )
                return True
            except Exception as e:
                app.logger.error(f"🔴 Error enviando imagen: {e}")

        # ENVIAR DOCUMENTO (explicit)
        if intent == "ENVIAR_DOCUMENTO" and document_field:
            try:
                enviar_documento(numero, document_field, os.path.basename(document_field), config)
                if respuesta_text:
                    enviar_mensaje(numero, respuesta_text, config)
                registrar_respuesta_bot(numero, texto, respuesta_text, config, imagen_url=document_field, es_imagen=False, incoming_saved=incoming_saved)
                return True
            except Exception as e:
                app.logger.error(f"🔴 Error enviando documento: {e}")

        # PASAR A ASESOR
        if intent == "PASAR_ASESOR" or notify_asesor:
            sent = pasar_contacto_asesor(numero, config=config, notificar_asesor=True)
            if respuesta_text:
                enviar_mensaje(numero, respuesta_text, config)
            registrar_respuesta_bot(numero, texto, respuesta_text, config, incoming_saved=incoming_saved)
            return True
        # PASAR DATOS TRANSFERENCIA
        if intent == "DATOS_TRANSFERENCIA":
            sent = enviar_datos_transferencia(numero, config=config)
            if not sent:
                # Si no se pudieron enviar los datos, entonces usar la respuesta de la IA como fallback
                if respuesta_text:
                    enviar_mensaje(numero, respuesta_text, config)
                    registrar_respuesta_bot(numero, texto, respuesta_text, config, incoming_saved=incoming_saved)
            else:
                app.logger.info(f"ℹ️ enviar_datos_transferencia devolvió sent={sent}, omitiendo respuesta_text redundante.")
            return True
        # RESPUESTA TEXTUAL POR DEFECTO
        if respuesta_text:
            respuesta_text = aplicar_restricciones(respuesta_text, numero, config)
            enviar_mensaje(numero, respuesta_text, config)
            registrar_respuesta_bot(numero, texto, respuesta_text, config, incoming_saved=incoming_saved)
            return True

        app.logger.info("ℹ️ procesar_mensaje_unificado: no action required by IA decision")
        return False

    except requests.exceptions.RequestException as e:
        app.logger.error(f"🔴 Error llamando a la API de IA: {e}")
        if hasattr(e, 'response') and e.response is not None:
            app.logger.error(f"🔴 API body: {e.response.text[:1000]}")
        return False
    except Exception as e:
        app.logger.error(f"🔴 Error inesperado en procesar_mensaje_unificado: {e}")
        app.logger.error(traceback.format_exc())
        return False

def enviar_datos_transferencia(numero, config=None):
    """
    Envía al cliente los datos de transferencia tomados desde la configuración del negocio.
    - numero: número destino (string)
    - config: tenant config opcional (dict). Si es None se usa obtener_configuracion_por_host().
    Retorna True si se envió un mensaje, False si no había datos configurados.
    """
    try:
        if config is None:
            config = obtener_configuracion_por_host()

        # Cargar configuración de negocio (usa load_config para respetar columnas/JSON)
        cfg = load_config(config)
        negocio = cfg.get('negocio', {}) or {}

        # Construir bloque de transferencia (usa la función ya existente)
        texto_transferencia = negocio_transfer_block(negocio)

        # Si no hay datos específicos, intentar leer fila completa de configuracion (fallback)
        if not texto_transferencia or 'no hay datos' in texto_transferencia.lower():
            # Try obtener datos directos desde DB as fallback
            datos = obtener_datos_de_transferencia(config) or []
            if datos and len(datos) > 0:
                row = datos[0]
                numero_t = (row.get('transferencia_numero') or negocio.get('transferencia_numero') or '').strip()
                nombre_t = (row.get('transferencia_nombre') or negocio.get('transferencia_nombre') or '').strip()
                banco_t = (row.get('transferencia_banco') or negocio.get('transferencia_banco') or '').strip()
                parts = []
                if numero_t:
                    parts.append(f"• Número / CLABE: {numero_t}")
                if nombre_t:
                    parts.append(f"• Nombre: {nombre_t}")
                if banco_t:
                    parts.append(f"• Banco: {banco_t}")
                if parts:
                    texto_transferencia = "Datos para transferencia:\n" + "\n".join(parts)

        # Si aún no hay datos, avisar al usuario
        if not texto_transferencia or texto_transferencia.strip() == "":
            msg = "Lo siento, no hay datos de transferencia configurados en este negocio. Por favor contacta al administrador."
            enviar_mensaje(numero, msg, config)
            registrar_respuesta_bot(numero, "[Solicitud datos transferencia]", msg, config, incoming_saved=False)
            app.logger.info(f"ℹ️ enviar_datos_transferencia: no hay datos para enviar (numero={numero})")
            return False

        # Enviar el bloque al cliente y registrar la respuesta en conversaciones
        enviar_mensaje(numero, texto_transferencia, config)
        registrar_respuesta_bot(numero, "[Solicitud datos transferencia]", texto_transferencia, config, incoming_saved=False)
        app.logger.info(f"✅ Datos de transferencia enviados a {numero}")
        return True

    except Exception as e:
        app.logger.error(f"🔴 Error en enviar_datos_transferencia: {e}")
        return False

def guardar_mensaje_inmediato(numero, texto, config=None, imagen_url=None, es_imagen=False):
    """Guarda el mensaje del usuario inmediatamente, sin respuesta.
    Aplica sanitización para que la UI muestre el mismo texto legible que llega por WhatsApp.
    Además, fuerza una actualización inmediata del Kanban tras insertar el mensaje.
    """
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
        row = cursor.fetchone()
        msg_id = row[0] if row else None

        conn.commit()
        cursor.close()
        conn.close()

        app.logger.info(f"💾 TRACKING: Mensaje ID {msg_id} guardado para {numero}")

        # Ensure Kanban reflects the new incoming message immediately.
        try:
            actualizar_kanban_inmediato(numero, config)
        except Exception as e:
            app.logger.warning(f"⚠️ actualizar_kanban_inmediato falló tras guardar mensaje: {e}")

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

def format_asesores_block(cfg):
    """
    Devuelve un bloque de texto listo para inyectar en el system prompt
    con la información de los asesores (solo nombres, NO teléfonos) y una regla
    clara: la IA NUNCA debe compartir números de teléfono ni datos de contacto directos.
    Acepta configuración legacy (asesores en columnas) o nueva (asesores_json -> lista).
    """
    try:
        # cfg is the full config returned by load_config()
        # prefer list if available
        asesores_list = []
        if isinstance(cfg, dict):
            # load_config returns 'asesores_list' when available
            if cfg.get('asesores_list'):
                asesores_list = cfg.get('asesores_list') or []
            else:
                # fallback to mapping in cfg['asesores']
                ases_map = cfg.get('asesores', {}) or {}
                # build list from mapping keys asesor1_nombre, etc.
                idx = 1
                while True:
                    name_key = f'asesor{idx}_nombre'
                    phone_key = f'asesor{idx}_telefono'
                    if name_key in ases_map or phone_key in ases_map:
                        nombre = (ases_map.get(name_key) or '').strip()
                        telefono = (ases_map.get(phone_key) or '').strip()
                        if nombre or telefono:
                            asesores_list.append({'nombre': nombre, 'telefono': telefono})
                        idx += 1
                        if idx > 20:
                            break
                    else:
                        break

        lines = []
        for i, a in enumerate(asesores_list, start=1):
            nombre = (a.get('nombre') or '').strip()
            if nombre:
                lines.append(f"• Asesor {i}: {nombre}")

        if not lines:
            return ""

        block = (
            "ASESORES DISPONIBLES (solo nombres; teléfonos NO incluidos aquí):\n"
            + "\n".join(lines) +
            "\n\nREGLA IMPORTANTE: La IA NO debe compartir números de teléfono ni datos de contacto directos. "
            "Si el usuario solicita explícitamente contactar a un asesor, la aplicación servidor (no la IA) enviará "
            "UN SOLO asesor al cliente usando la política round-robin. La IA puede ofrecer describir el perfil del asesor "
            "o preguntar si el usuario prefiere llamada o WhatsApp, pero NO debe revelar teléfonos."
        )
        return block
    except Exception:
        return ""

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

        # DETECCIÓN MAINDSTEEL
        if 'maindsteel' in host:
            app.logger.info("✅ Configuración detectada: Ofitodo")
            return NUMEROS_CONFIG['1011']
        if 'drasgo' in host:
            app.logger.info("✅ Configuración detectada: Ofitodo")
            return NUMEROS_CONFIG['1012']
        if 'lacse' in host:
            app.logger.info("✅ Configuración detectada: Ofitodo")
            return NUMEROS_CONFIG['1013']
        
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

@app.route('/home')
def home():
    config = obtener_configuracion_por_host()
    period = request.args.get('period', 'week')
    now = datetime.now()

    # Default behavior for week/month: keep existing logic (messages per chat)
    if period != 'year':
        start = now - (timedelta(days=30) if period == 'month' else timedelta(days=7))

        conn = get_db_connection(config)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(DISTINCT numero) FROM conversaciones WHERE timestamp>= %s;",
            (start,)
        )
        chat_counts = cursor.fetchone()[0]

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
    else:
        # period == 'year' : compute last 12 months (monthly), counting "conversaciones iniciadas"
        # build list of last 12 month keys in chronological order
        def month_key_from_offset(now_dt, offset):
            total_months = now_dt.year * 12 + now_dt.month - 1
            target = total_months - offset
            y = target // 12
            m = (target % 12) + 1
            return y, m

        months = []
        for offset in range(11, -1, -1):  # 11..0 -> oldest .. current
            y, m = month_key_from_offset(now, offset)
            months.append((y, m))

        # start = first day of oldest month
        earliest_year, earliest_month = months[0]
        start = datetime(earliest_year, earliest_month, 1)

        conn = get_db_connection(config)
        cursor = conn.cursor()

        sql = """
            SELECT YEAR(c1.timestamp) as y, MONTH(c1.timestamp) as m, COUNT(*) as cnt
            FROM conversaciones c1
            WHERE c1.timestamp >= %s
              AND NOT EXISTS (
                SELECT 1 FROM conversaciones c2
                WHERE c2.numero = c1.numero
                  AND c2.timestamp < c1.timestamp
                  AND TIMESTAMPDIFF(SECOND, c2.timestamp, c1.timestamp) < 86400
              )
            GROUP BY y, m
            ORDER BY y, m
        """
        cursor.execute(sql, (start,))
        rows = cursor.fetchall()  # list of tuples (y, m, cnt)

        # build map key 'YYYY-MM' -> count
        counts_map = {}
        for r in rows:
            try:
                y = int(r[0]); m = int(r[1]); cnt = int(r[2] or 0)
            except Exception:
                continue
            key = f"{y}-{m:02d}"
            counts_map[key] = cnt

        # labels as 'Mon YYYY' (en-US style short month)
        labels = []
        values = []
        for y, m in months:
            key = f"{y}-{m:02d}"
            labels.append(datetime(y, m, 1).strftime('%b %Y'))  # e.g. "Oct 2025"
            values.append(counts_map.get(key, 0))

        # keep top-level stats for compatibility (not shown in current template but safe)
        cursor.execute("SELECT COUNT(DISTINCT numero) FROM conversaciones WHERE timestamp >= %s;", (start,))
        chat_counts_row = cursor.fetchone()
        chat_counts = int(chat_counts_row[0]) if chat_counts_row and chat_counts_row[0] is not None else 0

        cursor.execute("SELECT COUNT(*) FROM conversaciones WHERE respuesta<>'' AND timestamp>= %s;", (start,))
        total_responded_row = cursor.fetchone()
        total_responded = int(total_responded_row[0]) if total_responded_row and total_responded_row[0] is not None else 0

        cursor.close()
        conn.close()

    # Obtener plan info para el usuario autenticado (si aplica)
    plan_info = None
    try:
        au = session.get('auth_user')
        if au and au.get('user'):
            plan_info = get_plan_status_for_user(au.get('user'), config=config)
    except Exception as e:
        app.logger.warning(f"⚠️ No se pudo obtener plan_info para el usuario: {e}")
        plan_info = None

    return render_template('dashboard.html',
        chat_counts=chat_counts,
        messages_per_chat=messages_per_chat if period != 'year' else None,
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

    # Determinar si el usuario autenticado tiene servicio == 'admin' en la tabla cliente
    au = session.get('auth_user') or {}
    is_admin = str(au.get('servicio') or '').strip().lower() == 'admin'

    return render_template('chats.html',
        chats=chats, 
        mensajes=None,
        selected=None, 
        IA_ESTADOS=IA_ESTADOS,
        tenant_config=config,
        is_admin=is_admin
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

        # Ensure chat_meta exists and move the chat to "En Conversación" when user opens it.
        # This makes opening the chat immediately reflect the agent activity in the kanban.
        try:
            inicializar_chat_meta(numero, config)
            actualizar_columna_chat(numero, 2, config)  # 2 = "En Conversación"
            app.logger.info(f"📊 Chat {numero} movido a 'En Conversación' (columna 2) al abrir la vista")
        except Exception as e:
            app.logger.warning(f"⚠️ No se pudo mover chat a 'En Conversación' al abrir: {e}")

        # Determinar si el usuario autenticado tiene servicio == 'admin' en la tabla cliente
        au = session.get('auth_user') or {}
        is_admin = str(au.get('servicio') or '').strip().lower() == 'admin'
        
        return render_template('chats.html',
            chats=chats, 
            mensajes=msgs,
            selected=numero, 
            IA_ESTADOS=IA_ESTADOS,
            tenant_config=config,
            is_admin=is_admin
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

def continuar_proceso_pedido(numero, mensaje, estado_actual, config=None):
    """Continúa el proceso de pedido de manera inteligente.
    Añadido: detecta forma de pago y datos de transferencia en las respuestas del usuario.
    """
    if config is None:
        config = obtener_configuracion_por_host()

    datos = estado_actual.get('datos', {})
    paso_actual = datos.get('paso', 1)
    analisis_inicial = datos.get('analisis_inicial', {})

    app.logger.info(f"🔄 Continuando pedido paso {paso_actual} para {numero}")

    # Analizar el nuevo mensaje para extraer información de pedido
    nuevo_analisis = detectar_pedido_inteligente(mensaje, numero, config=config)

    # Merge de cualquier dato extraído automáticamente
    if nuevo_analisis and nuevo_analisis.get('es_pedido'):
        datos_obtenidos = datos.get('datos_obtenidos', {})
        nuevos_datos = nuevo_analisis.get('datos_obtenidos', {})

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
        datos['paso'] = datos.get('paso', 1) + 1

    else:
        # Si la IA no detectó estructura, intentamos extraer forma de pago y datos manualmente del texto
        datos_obtenidos = datos.get('datos_obtenidos', {})

        texto_lower = (mensaje or '').lower()

        # Detectar forma de pago explícita
        if not datos_obtenidos.get('forma_pago'):
            if 'efectivo' in texto_lower or 'pago al entregar' in texto_lower or 'pago en efectivo' in texto_lower:
                datos_obtenidos['forma_pago'] = 'efectivo'
                app.logger.info(f"💳 Forma de pago detectada (efectivo) para {numero}")
            elif 'transfer' in texto_lower or 'transferencia' in texto_lower or 'clabe' in texto_lower or 'clabe interbancaria' in texto_lower:
                datos_obtenidos['forma_pago'] = 'transferencia'
                app.logger.info(f"💳 Forma de pago detectada (transferencia) para {numero}")

        # Si la forma de pago encontrada es transferencia, intentar extraer número/CLABE y nombre
        if datos_obtenidos.get('forma_pago') and 'transfer' in datos_obtenidos.get('forma_pago'):
            # Extraer secuencia de dígitos que podría ser CLABE o número de cuenta (10-22 dígitos)
            clabe_match = re.search(r'(\d{10,22})', mensaje.replace(' ', ''))
            if clabe_match and not datos_obtenidos.get('transferencia_numero'):
                datos_obtenidos['transferencia_numero'] = clabe_match.group(1)
                app.logger.info(f"🔢 CLABE/numero detectado para {numero}: {datos_obtenidos['transferencia_numero']}")

            # Extraer banco por palabras clave comunes
            bancos = ['bbva', 'banorte', 'banamex', 'santander', 'scotiabank', 'hsbc', 'inbursa', 'bajio', 'afirme']
            for b in bancos:
                if b in texto_lower and not datos_obtenidos.get('transferencia_banco'):
                    datos_obtenidos['transferencia_banco'] = b.capitalize()
                    app.logger.info(f"🏦 Banco detectado para {numero}: {datos_obtenidos['transferencia_banco']}")
                    break

            # Intentar extraer nombre del titular (heurística: detrás de 'a nombre de' o 'titular' o en la misma línea)
            nombre_match = re.search(r'(a nombre de|titular)\s*[:\-]?\s*([A-Za-zÁÉÍÓÚÑáéíóúñ\s]{3,60})', mensaje, re.IGNORECASE)
            if nombre_match and not datos_obtenidos.get('transferencia_nombre'):
                datos_obtenidos['transferencia_nombre'] = nombre_match.group(2).strip()
                app.logger.info(f"🧾 Titular detectado para {numero}: {datos_obtenidos['transferencia_nombre']}")

        datos['datos_obtenidos'] = datos_obtenidos

    # Persistir estado actualizado
    actualizar_estado_conversacion(numero, "EN_PEDIDO", "actualizar", datos, config)

    # Verificar si ahora el pedido está completo
    if verificar_pedido_completo(datos.get('datos_obtenidos', {})):
        # Pedido completo, confirmar y guardar
        return confirmar_pedido_completo(numero, datos.get('datos_obtenidos', {}), config)

    # Si no está completo, generar siguiente pregunta
    siguiente_pregunta = generar_pregunta_datos_faltantes(datos.get('datos_obtenidos', {}))
    return siguiente_pregunta

def verificar_pedido_completo(datos_obtenidos):
    """Verifica si el pedido tiene todos los datos necesarios.
    Ahora exige: platillos, direccion y forma de pago.
    Si la forma de pago es 'transferencia' también exige datos de transferencia básicos.
    """
    if not datos_obtenidos:
        return False

    # Campos siempre requeridos
    required = ['platillos', 'direccion', 'forma_pago']
    for campo in required:
        if not datos_obtenidos.get(campo):
            return False

    # Verificar que haya al menos un platillo con cantidad
    platillos = datos_obtenidos.get('platillos', [])
    cantidades = datos_obtenidos.get('cantidades', [])
    if not platillos or len(platillos) != len(cantidades):
        return False

    # Si la forma de pago es transferencia, requerimos datos de transferencia
    forma = str(datos_obtenidos.get('forma_pago', '')).lower()
    if 'transfer' in forma or 'transferencia' in forma:
        # aceptar tanto 'transferencia' como 'transfer'
        # Requerir al menos número/CLABE y nombre del titular
        if not datos_obtenidos.get('transferencia_numero') or not datos_obtenidos.get('transferencia_nombre'):
            return False

    return True

def generar_pregunta_datos_faltantes(datos_obtenidos):
    """Genera preguntas inteligentes para datos faltantes, incluyendo forma de pago."""
    if not datos_obtenidos.get('platillos'):
        return "¿Qué platillos te gustaría ordenar? Tenemos gorditas, tacos, quesadillas, sopes, etc."

    if not datos_obtenidos.get('cantidades') or len(datos_obtenidos['platillos']) != len(datos_obtenidos.get('cantidades', [])):
        platillos = datos_obtenidos.get('platillos', [])
        return f"¿Cuántas {', '.join(platillos)} deseas ordenar?"

    if not datos_obtenidos.get('especificaciones'):
        return "¿Alguna especificación para tu pedido? Por ejemplo: 'con todo', 'sin cebolla', etc."

    if not datos_obtenidos.get('direccion'):
        return "¿A qué dirección debemos llevar tu pedido?"

    # NUEVO: preguntar forma de pago si falta
    if not datos_obtenidos.get('forma_pago'):
        return "¿Cómo prefieres pagar? Responde 'efectivo' (pago al entregar) o 'transferencia' (te pediré los datos bancarios)."

    # Si eligió transferencia pero faltan datos, pedirlos
    forma = str(datos_obtenidos.get('forma_pago', '')).lower()
    if 'transfer' in forma or 'transferencia' in forma:
        if not datos_obtenidos.get('transferencia_numero'):
            return "Por favor proporciona el número o CLABE para la transferencia."
        if not datos_obtenidos.get('transferencia_nombre'):
            return "Por favor indica el nombre del titular de la cuenta para la transferencia."
        if not datos_obtenidos.get('transferencia_banco'):
            return "Si puedes, indica también el banco (ej: BBVA, Banorte, Banamex)."

    if not datos_obtenidos.get('nombre_cliente'):
        return "¿Cuál es tu nombre para el pedido?"

    return "¿Necesitas agregar algo más a tu pedido?"

def confirmar_pedido_completo(numero, datos_pedido, config=None):
    """Confirma el pedido completo. 
    - Si la forma de pago es tarjeta: NO guarda el pedido aún; ofrece conectar con asesor y guarda un pedido provisional en estado.
    - Si es efectivo/transferencia: guarda inmediatamente y confirma.
    """
    if config is None:
        config = obtener_configuracion_por_host()

    try:
        # Crear resumen del pedido
        platillos = datos_pedido.get('platillos', [])
        cantidades = datos_pedido.get('cantidades', [])
        especificaciones = datos_pedido.get('especificaciones', [])
        nombre_cliente = datos_pedido.get('nombre_cliente') or 'Cliente'
        direccion = datos_pedido.get('direccion') or 'Por confirmar'

        resumen_platillos = ""
        for i, platillo in enumerate(platillos):
            cantidad = cantidades[i] if i < len(cantidades) else "1"
            resumen_platillos += f"- {cantidad} {platillo}\n"

        # Preparar estructura de pedido (reutilizable para guardar o provisional)
        info_pedido = {
            'servicio_solicitado': f"Pedido: {', '.join(platillos)}",
            'nombre_cliente': nombre_cliente,
            'telefono': numero,
            'estado': 'pendiente',
            'notas': f"Especificaciones: {', '.join(especificaciones)}\nDirección: {direccion}"
        }

        # Añadir datos de pago al registro (si existen) para referencia
        if datos_pedido.get('forma_pago'):
            info_pedido['forma_pago'] = datos_pedido.get('forma_pago')
        if datos_pedido.get('transferencia_numero'):
            info_pedido['notas'] += f"\nTransferencia - CLABE/numero: {datos_pedido.get('transferencia_numero')}"
        if datos_pedido.get('transferencia_nombre'):
            info_pedido['notas'] += f"\nTitular: {datos_pedido.get('transferencia_nombre')}"
        if datos_pedido.get('transferencia_banco'):
            info_pedido['notas'] += f"\nBanco: {datos_pedido.get('transferencia_banco')}"

        forma = str(datos_pedido.get('forma_pago', '')).lower()

        # Caso: tarjeta -> no pedir tarjeta por chat. Ofrecer asesor y guardar en estado provisional.
        if 'tarjeta' in forma:
            # Guardar pedido provisional en estados_conversacion (no persistir aún en 'citas')
            provisional = {
                'pedido_provisional': info_pedido,
                'timestamp': datetime.now().isoformat()
            }
            actualizar_estado_conversacion(numero, "OFRECIENDO_ASESOR", "ofrecer_asesor", provisional, config)

            # Intentar obtener nombre de un asesor para la oferta (no incluir teléfonos)
            cfg = load_config(config)
            asesores = cfg.get('asesores_list') or []
            asesor_name = asesores[0].get('nombre') if asesores and isinstance(asesores[0], dict) and asesores[0].get('nombre') else "nuestro asesor"

            instrucciones = (
                "Para procesar el pago con tarjeta, por seguridad no pedimos números por WhatsApp.\n\n"
                f"Puedo conectarte con {asesor_name} para completar el pago de forma segura, o si prefieres que yo agende el pedido ahora mismo con los datos que ya tengo, responde 'no'.\n\n"
                "Responde 'sí' para que te pase al asesor, o 'no' para que agende el pedido ahora."
            )

            mensaje_oferta = f"""🎉 *¡Pedido listo para pagar!*

📋 *Resumen de tu pedido:*
{resumen_platillos}

🏠 *Dirección:* {direccion}
👤 *Nombre:* {nombre_cliente}

{instrucciones}
"""
            return mensaje_oferta

        # Caso: transferencia -> guardar y pedir comprobante (se guarda ahora)
        if 'transfer' in forma or 'transferencia' in forma:
            pedido_id = guardar_cita(info_pedido, config)
            instrucciones_pago = ("💳 Forma de pago: Transferencia bancaria.\n"
                                  "Por favor realiza la transferencia y envía el comprobante por este chat.\n"
                                  "Cuando recibamos el comprobante procederemos a preparar tu pedido.")
        else:
            # Efectivo u otros -> guardar y confirmar
            pedido_id = guardar_cita(info_pedido, config)
            instrucciones_pago = "💵 Forma de pago: Efectivo. Pagarás al recibir el pedido."

        # Si llegamos aquí, ya guardamos el pedido
        confirmacion = f"""🎉 *¡Pedido Confirmado!* - ID: #{pedido_id}

📋 *Resumen de tu pedido:*
{resumen_platillos}

🏠 *Dirección:* {direccion}
👤 *Nombre:* {nombre_cliente}

{instrucciones_pago}

⏰ *Tiempo estimado:* 30-45 minutos
Gracias por tu pedido. Te avisaremos cuando esté en camino.
"""
        # Limpiar estado relacionado si existía
        actualizar_estado_conversacion(numero, "PEDIDO_COMPLETO", "pedido_confirmado", {}, config)
        return confirmacion

    except Exception as e:
        app.logger.error(f"Error confirmando pedido: {e}")
        return "¡Pedido recibido! Pero hubo un error al procesarlo. Por favor, contacta directamente al negocio."

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
    if tab not in SUBTABS:
        abort(404)
    guardado = False

    cfg = load_config(config)
    asesores_list = cfg.get('asesores_list', []) or []

    # Determine asesor_count early to avoid UnboundLocalError when we use it below
    au = session.get('auth_user') or {}
    try:
        if au and au.get('user'):
            asesor_count = obtener_asesores_por_user(au.get('user'), default=2, cap=20)
        else:
            asesor_count = obtener_max_asesores_from_planes(default=2, cap=20)
    except Exception as e:
        app.logger.warning(f"⚠️ Error determinando asesor_count: {e}")
        asesor_count = obtener_max_asesores_from_planes(default=2, cap=20)

    # If DB still contains more advisors than the allowed plan limit, trim them now.
    try:
        if isinstance(asesores_list, list) and len(asesores_list) > asesor_count:
            app.logger.info(f"⚠️ Plan reducido: {len(asesores_list)} -> {asesor_count}. Eliminando asesores extras en BD...")
            eliminar_asesores_extras(config, asesor_count)
            # Reload after trimming so template shows the trimmed list
            cfg = load_config(config)
            asesores_list = cfg.get('asesores_list', []) or []
    except Exception as e:
        app.logger.warning(f"⚠️ No se pudo recortar lista de asesores tras guardar: {e}")

    # If showing 'negocio' tab, load published documents for the template (existing logic)
    documents_publicos = []
    if tab == 'negocio':
        try:
            conn = get_db_connection(config)
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SHOW TABLES LIKE 'documents_publicos'")
            if cursor.fetchone():
                cursor.execute("""
                    SELECT id, filename, filepath, descripcion, uploaded_by, created_at, tenant_slug
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

    if request.method == 'POST':
        if tab == 'negocio':
            cfg['negocio'] = {
                'ia_nombre':      request.form.get('ia_nombre'),
                'negocio_nombre': request.form.get('negocio_nombre'),
                'descripcion':    request.form.get('descripcion'),
                'url':            request.form.get('url'),
                'direccion':      request.form.get('direccion'),
                'telefono':       request.form.get('telefono'),
                'correo':         request.form.get('correo'),
                'que_hace':       request.form.get('que_hace'),
                'calendar_email': request.form.get('calendar_email'),
                'transferencia_numero': request.form.get('transferencia_numero'),
                'transferencia_nombre': request.form.get('transferencia_nombre'),
                'transferencia_banco': request.form.get('transferencia_banco')
            }
        elif tab == 'personalizacion':
            cfg['personalizacion'] = {
                'tono':     request.form.get('tono'),
                'lenguaje': request.form.get('lenguaje')
            }
        elif tab == 'restricciones':
            cfg['restricciones'] = {
                'restricciones': request.form.get('restricciones', ''),
                'palabras_prohibidas': request.form.get('palabras_prohibidas', ''),
                'max_mensajes': int(request.form.get('max_mensajes', 10)),
                'tiempo_max_respuesta': int(request.form.get('tiempo_max_respuesta', 30))
            }
        elif tab == 'asesores':
            # Read dynamic number of advisors according to plan (asesor_count)
            advisors_compiled = []
            advisors_map = {}
            for i in range(1, asesor_count + 1):
                name_key = f'asesor{i}_nombre'
                phone_key = f'asesor{i}_telefono'
                email_key = f'asesor{i}_email'
                name = request.form.get(name_key, '').strip()
                phone = request.form.get(phone_key, '').strip()
                email = request.form.get(email_key, '').strip()
                # Build legacy map for first two as fallback
                if i <= 2:
                    advisors_map[f'asesor{i}_nombre'] = name
                    advisors_map[f'asesor{i}_telefono'] = phone
                    advisors_map[f'asesor{i}_email'] = email
                if name or phone or email:
                    advisors_compiled.append({'nombre': name, 'telefono': phone, 'email': email})

            cfg['asesores'] = advisors_map  # legacy map
            # supply structured list to be saved by save_config
            cfg['asesores_json'] = advisors_compiled

        # Persist configuration
        try:
            save_config(cfg, config)
            guardado = True
        except Exception as e:
            app.logger.error(f"🔴 Error guardando configuración desde /configuracion/{tab}: {e}")
            guardado = False

        # Reload config and asesor list after save
        cfg = load_config(config)
        asesores_list = cfg.get('asesores_list', []) or []
        try:
            if au and au.get('user'):
                asesor_count = obtener_asesores_por_user(au.get('user'), default=2, cap=20)
            else:
                asesor_count = obtener_max_asesores_from_planes(default=2, cap=20)
        except Exception:
            asesor_count = obtener_max_asesores_from_planes(default=2, cap=20)

    datos = cfg.get(tab, {})

    # If showing 'negocio' tab, load published documents for the template (existing logic)
    documents_publicos = documents_publicos  # already loaded above when tab == 'negocio'

    return render_template('configuracion.html',
        tabs=SUBTABS, active=tab,
        datos=datos, guardado=guardado,
        documents_publicos=documents_publicos,
        asesor_count=asesor_count,
        asesores_list=asesores_list
    )

def negocio_contact_block(negocio):
    """
    Formatea los datos de contacto del negocio desde la configuración.
    Si algún campo no está configurado muestra 'No disponible'.
    (Versión segura: no hace llamadas externas).
    """
    if not negocio or not isinstance(negocio, dict):
        return ("DATOS DEL NEGOCIO:\n"
                "Dirección: No disponible\n"
                "Teléfono: No disponible\n"
                "Correo: No disponible\n\n"
                "Nota: Los datos no están configurados en el sistema.")
    direccion = (negocio.get('direccion') or '').strip() or 'No disponible'
    telefono = (negocio.get('telefono') or '').strip() or 'No disponible'
    correo = (negocio.get('correo') or '').strip() or 'No disponible'

    block = (
        f"¡Hola! Estoy a tu servicio. Aquí tienes los datos del negocio:\n\n"
        f"• Dirección: {direccion}\n"
        f"• Teléfono: {telefono}\n"
        f"• Correo: {correo}\n\n"
        "Si necesitas otra cosa, dime."
    )
    return block

def negocio_transfer_block(negocio):
    """
    Devuelve un bloque con los datos para transferencia (número/CLABE, nombre y banco)
    sacados directamente de la configuración 'negocio'.
    """
    if not negocio or not isinstance(negocio, dict):
        return "Lo siento, no hay datos de transferencia configurados."

    numero = (negocio.get('transferencia_numero') or '').strip()
    nombre = (negocio.get('transferencia_nombre') or '').strip()
    banco = (negocio.get('transferencia_banco') or '').strip()

    if not (numero or nombre or banco):
        return "Lo siento, no hay datos de transferencia configurados."

    # Presentación clara y breve
    parts = ["Datos para transferencia:"]
    if numero:
        parts.append(f"• Número / CLABE: {numero}")
    if nombre:
        parts.append(f"• Nombre: {nombre}")
    if banco:
        parts.append(f"• Banco: {banco}")
    return "\n".join(parts)

@app.route('/configuracion/precios', methods=['GET'])
def configuracion_precios():
    config = obtener_configuracion_por_host()
    precios = obtener_todos_los_precios(config)

    # Determinar si el usuario autenticado tiene servicio == 'admin' en la tabla cliente
    au = session.get('auth_user') or {}
    is_admin = str(au.get('servicio') or '').strip().lower() == 'admin'

    return render_template('configuracion/precios.html',
        tabs=SUBTABS, active='precios',
        guardado=False,
        precios=precios,
        precio_edit=None,
        is_admin=is_admin
    )

@app.route('/configuracion/precios/editar/<int:pid>', methods=['GET'])
def configuracion_precio_editar(pid):
    config = obtener_configuracion_por_host()
    precios     = obtener_todos_los_precios(config)
    precio_edit = obtener_precio_por_id(pid, config)

    # Determinar si el usuario autenticado tiene servicio == 'admin' en la tabla cliente
    au = session.get('auth_user') or {}
    is_admin = str(au.get('servicio') or '').strip().lower() == 'admin'

    return render_template('configuracion/precios.html',
        tabs=SUBTABS, active='precios',
        guardado=False,
        precios=precios,
        precio_edit=precio_edit,
        is_admin=is_admin
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

        # Ensure subscription columns exist in precios table
        try:
            _ensure_precios_subscription_columns(config)
        except Exception as _:
            app.logger.warning("⚠️ _ensure_precios_subscription_columns falló (continuando)")

        # Process numeric price fields coming from form (empty -> None)
        for f in ['costo', 'precio', 'precio_mayoreo', 'precio_menudeo', 'inscripcion', 'mensualidad']:
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
            'descripcion', 'medidas', 'costo', 'inscripcion', 'mensualidad',
            'precio', 'precio_mayoreo', 'precio_menudeo',
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
    # Determinar si el usuario autenticado tiene servicio == 'admin' en la tabla cliente
    au = session.get('auth_user') or {}
    is_admin = str(au.get('servicio') or '').strip().lower() == 'admin'

    return render_template('kanban.html', columnas=columnas, chats=chats, is_admin=is_admin)     

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

@app.route('/dashboard/conversaciones-data')
def dashboard_conversaciones_data():
    """
    Devuelve JSON con:
    - plan_info (si el usuario está autenticado)
    - active_count: número de chats con actividad en las últimas 24h
    - labels/values: por día (últimos 90 días si ?period=3months), o comportamiento anterior para week/month
    """
    try:
        config = obtener_configuracion_por_host()
        period = request.args.get('period', 'week')
        now = datetime.now()

        conn = get_db_connection(config)
        cursor = conn.cursor()

        # Special case: user asked previously '3months' -> now return up to last 90 days,
        # but start the series at the first day that actually has data within that window.
        if period == '3months':
            # Find last day with data
            try:
                cursor.execute("SELECT DATE(MAX(timestamp)) FROM conversaciones")
                row = cursor.fetchone()
                last_day = None
                if row and row[0]:
                    last_day = row[0]
                    # normalize if returned as string
                    if isinstance(last_day, str):
                        last_day = datetime.strptime(last_day, "%Y-%m-%d").date()
                    else:
                        try:
                            last_day = last_day.date() if hasattr(last_day, 'date') else last_day
                        except Exception:
                            last_day = datetime.now().date()
                else:
                    last_day = datetime.now().date()
            except Exception:
                last_day = datetime.now().date()

            # Window lower bound (maximum 90 days back)
            window_start = last_day - timedelta(days=89)

            # Query: same "conversation started" definition, limited to the date range
            sql = """
                SELECT DATE(c1.timestamp) as dia, COUNT(*) as cnt
                FROM conversaciones c1
                WHERE DATE(c1.timestamp) BETWEEN %s AND %s
                  AND NOT EXISTS (
                    SELECT 1 FROM conversaciones c2
                    WHERE c2.numero = c1.numero
                      AND c2.timestamp < c1.timestamp
                      AND TIMESTAMPDIFF(SECOND, c2.timestamp, c1.timestamp) < 86400
                  )
                GROUP BY DATE(c1.timestamp)
                ORDER BY DATE(c1.timestamp)
            """
            cursor.execute(sql, (window_start, last_day))
            rows = cursor.fetchall()

            # Map counts by date string 'YYYY-MM-DD'
            counts_map = {}
            for r in rows:
                try:
                    dia = r[0]
                    if hasattr(dia, 'strftime'):
                        key = dia.strftime('%Y-%m-%d')
                    else:
                        key = str(dia)
                    cnt = int(r[1] or 0)
                    counts_map[key] = cnt
                except Exception:
                    continue

            # If there are no days with data in the window, return an empty (or single-day) series
            if not counts_map:
                labels = []
                values = []
            else:
                # Find earliest date within counts_map (first day that has data)
                parsed_dates = [datetime.strptime(k, '%Y-%m-%d').date() for k in counts_map.keys()]
                earliest_with_data = min(parsed_dates)

                # Ensure earliest_with_data is not earlier than window_start
                if earliest_with_data < window_start:
                    earliest_with_data = window_start

                # Build labels from earliest_with_data .. last_day (inclusive)
                labels = []
                values = []
                days_range = (last_day - earliest_with_data).days + 1
                for i in range(days_range):
                    d = earliest_with_data + timedelta(days=i)
                    key = d.strftime('%Y-%m-%d')
                    labels.append(key)
                    values.append(counts_map.get(key, 0))

            # Chats activos: distinct numero with message in last 24h
            cursor.execute("SELECT COUNT(DISTINCT numero) FROM conversaciones WHERE timestamp >= NOW() - INTERVAL 1 DAY")
            active_count_row = cursor.fetchone()
            active_count = int(active_count_row[0]) if active_count_row and active_count_row[0] is not None else 0

            cursor.close()
            conn.close()

            # Plan info if user authenticated
            plan_info = None
            try:
                au = session.get('auth_user')
                if au and au.get('user'):
                    plan_info = get_plan_status_for_user(au.get('user'), config=config)
            except Exception:
                plan_info = None

            return jsonify({
                'labels': labels,
                'values': values,
                'active_count': active_count,
                'plan_info': plan_info or {}
            })

        # --- fallback: previous daily behavior for week/month ---
        start = now - (timedelta(days=30) if period == 'month' else timedelta(days=7))

        cursor.execute("""
            SELECT DATE(c1.timestamp) as dia, COUNT(*) as cnt
            FROM conversaciones c1
            WHERE c1.timestamp >= %s
              AND NOT EXISTS (
                SELECT 1 FROM conversaciones c2
                WHERE c2.numero = c1.numero
                  AND c2.timestamp < c1.timestamp
                  AND TIMESTAMPDIFF(SECOND, c2.timestamp, c1.timestamp) < 86400
              )
            GROUP BY DATE(c1.timestamp)
            ORDER BY DATE(c1.timestamp)
        """, (start,))

        rows = cursor.fetchall()
        labels = []
        values = []
        for r in rows:
            dia = r[0]
            if hasattr(dia, 'strftime'):
                labels.append(dia.strftime('%Y-%m-%d'))
            else:
                labels.append(str(dia))
            values.append(int(r[1] or 0))

        cursor.execute("SELECT COUNT(DISTINCT numero) FROM conversaciones WHERE timestamp >= NOW() - INTERVAL 1 DAY")
        active_count_row = cursor.fetchone()
        active_count = int(active_count_row[0]) if active_count_row and active_count_row[0] is not None else 0

        cursor.close()
        conn.close()

        plan_info = None
        try:
            au = session.get('auth_user')
            if au and au.get('user'):
                plan_info = get_plan_status_for_user(au.get('user'), config=config)
        except Exception:
            plan_info = None

        return jsonify({
            'labels': labels,
            'values': values,
            'active_count': active_count,
            'plan_info': plan_info or {}
        })
    except Exception as e:
        app.logger.error(f"🔴 Error en /dashboard/conversaciones-data: {e}")
        return jsonify({'error': str(e)}), 500

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

def actualizar_kanban_inmediato(numero, config=None):
    """Updates the Kanban board immediately when a message is received.

    Behavior:
    - If there are any incoming messages without respuesta (respuesta IS NULL)
      for this numero, set columna = 1 ("Nuevos").
    - Otherwise fall back to previous logic (existing conversation -> columna 2).
    """
    if config is None:
        config = obtener_configuracion_por_host()

    try:
        # Ensure chat_meta exists
        meta = obtener_chat_meta(numero, config)
        if not meta:
            inicializar_chat_meta(numero, config)
            app.logger.info(f"✅ Chat meta initialized for {numero}")

        conn = get_db_connection(config)
        cursor = conn.cursor()

        # Count unread incoming messages (respuesta IS NULL)
        cursor.execute("""
            SELECT COUNT(*) FROM conversaciones
            WHERE numero = %s AND respuesta IS NULL
        """, (numero,))
        row = cursor.fetchone()
        sin_leer = int(row[0]) if row and row[0] is not None else 0

        # Decide target column: if any unread -> Nuevos (1). Else En Conversación (2)
        if sin_leer > 0:
            nueva_columna = 1
            app.logger.info(f"📊 {numero} tiene {sin_leer} mensajes sin leer -> moviendo a 'Nuevos' (1)")
        else:
            # Existing conversation heuristic: put in "En Conversación"
            # If there's no history at all, still default to Nuevos (1)
            cursor.execute("SELECT COUNT(*) FROM conversaciones WHERE numero = %s", (numero,))
            total_msgs = int(cursor.fetchone()[0] or 0)
            if total_msgs == 0:
                nueva_columna = 1
                app.logger.info(f"📊 {numero} sin historial -> moviendo a 'Nuevos' (1)")
            else:
                nueva_columna = 2
                app.logger.info(f"📊 {numero} sin mensajes sin leer -> moviendo a 'En Conversación' (2)")

        # Persist update to chat_meta
        cursor.execute("""
            INSERT INTO chat_meta (numero, columna_id)
            VALUES (%s, %s)
            ON DUPLICATE KEY UPDATE columna_id = VALUES(columna_id), fecha_actualizacion = CURRENT_TIMESTAMP
        """, (numero, nueva_columna))
        conn.commit()
        cursor.close()
        conn.close()

        app.logger.info(f"✅ Kanban updated immediately for {numero} to column {nueva_columna}")
        return True
    except Exception as e:
        app.logger.error(f"❌ Error updating Kanban immediately: {e}")
        try:
            cursor.close()
        except:
            pass
        try:
            conn.close()
        except:
            pass
        return False

def actualizar_columna_chat(numero, columna_id, config=None):
    """
    Safely update chat_meta.columna_id for a given chat.
    - Verifies the target columna_id exists in kanban_columnas.
    - If it doesn't exist, tries to find a column named like 'Resueltos'.
    - If still not found, creates a new 'Resueltos' column and uses its id.
    This prevents foreign-key errors when code attempts to move chats to a hard-coded id
    that may have been deleted in that tenant DB.
    """
    if config is None:
        config = obtener_configuracion_por_host()

    conn = None
    cursor = None
    try:
        conn = get_db_connection(config)
        cursor = conn.cursor()

        # 1) If the target column id does not exist, attempt fallbacks
        cursor.execute("SELECT id FROM kanban_columnas WHERE id = %s LIMIT 1", (columna_id,))
        if cursor.fetchone() is None:
            app.logger.warning(f"⚠️ Target kanban_columnas id={columna_id} not found in DB {config.get('db_name')}. Attempting fallback lookup/create.")

            # Try to find a column named 'Resueltos' (case-insensitive, tolerant)
            cursor.execute("SELECT id FROM kanban_columnas WHERE LOWER(nombre) LIKE LOWER(%s) LIMIT 1", ('%resueltos%',))
            row = cursor.fetchone()
            if row:
                new_col_id = row[0]
                app.logger.info(f"ℹ️ Fallback: found 'Cerrados' column id={new_col_id}. Using it instead of requested id={columna_id}.")
                columna_id = new_col_id
            else:
                # Create a new 'Resueltos' column at the end
                try:
                    cursor.execute("SELECT COALESCE(MAX(orden), 0) + 1 AS next_ord FROM kanban_columnas")
                    next_ord_row = cursor.fetchone()
                    next_ord = int(next_ord_row[0]) if next_ord_row and next_ord_row[0] is not None else 1
                except Exception:
                    next_ord = 1

                default_icon = '/static/icons/default-avatar.png'
                color = '#6c757d'
                cursor.execute(
                    "INSERT INTO kanban_columnas (nombre, orden, color, icono) VALUES (%s, %s, %s, %s)",
                    ('Vendidos', next_ord, color, default_icon)
                )
                conn.commit()
                columna_id = cursor.lastrowid
                app.logger.info(f"✅ Created missing 'Vendidos' column id={columna_id} in DB {config.get('db_name')}")

        # 2) Perform the update now that columna_id is guaranteed to exist
        cursor.execute("""
            UPDATE chat_meta SET columna_id = %s 
            WHERE numero = %s;
        """, (columna_id, numero))
        conn.commit()
        app.logger.info(f"✅ Chat {numero} columna updated to {columna_id} in DB {config.get('db_name')}")

    except Exception as e:
        # Log the underlying DB error for diagnostics
        app.logger.error(f"❌ actualizar_columna_chat failed for numero={numero} columna_id={columna_id} on DB {config.get('db_name')}: {e}")
        try:
            if conn:
                conn.rollback()
        except:
            pass
        raise
    finally:
        try:
            if cursor:
                cursor.close()
            if conn:
                conn.close()
        except:
            pass

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
    """
    Devuelve un bloque de texto con contexto breve del cliente para alertas/handoff.
    - Incluye nombre mostrado (alias/nombre) y últimos mensajes (hasta 8).
    - Retorna una cadena (truncada) y nunca lanza excepción.
    """
    if config is None:
        try:
            config = obtener_configuracion_por_host()
        except Exception:
            config = NUMEROS_CONFIG.get('524495486142')

    try:
        nombre = obtener_nombre_mostrado_por_numero(numero, config) or numero
    except Exception:
        nombre = numero

    try:
        historial = obtener_historial(numero, limite=8, config=config) or []
    except Exception:
        historial = []

    partes = []
    for h in historial:
        try:
            if h.get('mensaje'):
                partes.append(f"Usuario: {h.get('mensaje')}")
            if h.get('respuesta'):
                partes.append(f"Asistente: {h.get('respuesta')}")
        except Exception:
            continue

    if not partes:
        contexto = f"Cliente: {nombre}\n(No hay historial disponible.)"
    else:
        contexto = f"Cliente: {nombre}\nÚltimas interacciones:\n" + "\n".join(partes)

    # Truncar para evitar payloads muy grandes (safety)
    MAX_CHARS = 4000
    if len(contexto) > MAX_CHARS:
        contexto = contexto[:MAX_CHARS - 3] + "..."

    return contexto

with app.app_context():
    # Crear tablas Kanban para todos los tenants
    inicializar_kanban_multitenant()
    start_good_morning_scheduler()
    # Verificar tablas en todas las bases de datos 
    app.logger.info("🔍 Verificando tablas en todas las bases de datos...")
    for nombre, config in NUMEROS_CONFIG.items():
        verificar_tablas_bd(config)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5000, help='Puerto para ejecutar la aplicación')# Puerto para ejecutar la aplicación puede ser
    args = parser.parse_args()
    app.run(host='0.0.0.0', port=args.port)