"""
Redes sociales / canales por cliente (pestaña "Redes sociales" de Configuración).

- Se guardan en la Base Maestra: clientes.cliente_canales (un renglón por cliente y canal).
- Tokens y contraseñas van CIFRADOS con la llave CANALES_KEY del .env (Fernet).
- WhatsApp sigue guardándose en clientes.cliente (wa_phone_id / wa_token), como siempre.
- Si un cliente no ha llenado su pestaña, el código sigue usando NUMEROS_CONFIG / .env.
"""
import hashlib
import imaplib
import json
import logging
import os
import time

import requests

from services import get_db_connection

logger = logging.getLogger(__name__)

CANALES = ('whatsapp', 'messenger', 'telegram', 'linkedin', 'instagram')
GRAPH = "https://graph.facebook.com/v21.0"
_TABLA_LISTA = False
_CACHE = {}          # dominio -> (hora, tokens) para no consultar la BD en cada petición
_CACHE_SEG = 60


# ==================== Cifrado ====================
def _fernet():
    key = (os.getenv('CANALES_KEY') or '').strip()
    if not key:
        return None
    from cryptography.fernet import Fernet
    return Fernet(key.encode())


def cifrado_listo():
    try:
        return _fernet() is not None
    except Exception:
        return False


def _cifrar(d):
    f = _fernet()
    if not f:
        raise RuntimeError('Falta CANALES_KEY en el .env del servidor')
    return f.encrypt(json.dumps(d).encode()).decode()


def _descifrar(txt):
    if not txt:
        return {}
    f = _fernet()
    if not f:
        logger.warning("🔐 CANALES_KEY no configurada: no se pueden leer secretos")
        return {}
    try:
        return json.loads(f.decrypt(txt.encode()).decode())
    except Exception as e:
        logger.error(f"🔐 No se pudo descifrar un secreto de canal: {e}")
        return {}


def _hash(valor):
    return hashlib.sha256((valor or '').encode()).hexdigest()


def enmascarar(valor):
    v = valor or ''
    return ('•' * 8 + v[-4:]) if len(v) > 4 else ('•' * len(v))


# ==================== Base de datos ====================
def _conn():
    return get_db_connection({'db_name': 'clientes'})


def _asegurar_tabla():
    global _TABLA_LISTA
    if _TABLA_LISTA:
        return
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS cliente_canales (
                dominio VARCHAR(100) NOT NULL,
                canal VARCHAR(30) NOT NULL,
                datos TEXT NULL,
                secreto TEXT NULL,
                buscar VARCHAR(255) NULL,
                activo TINYINT(1) DEFAULT 1,
                estado VARCHAR(20) DEFAULT 'sin_probar',
                mensaje VARCHAR(255) NULL,
                actualizado DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                PRIMARY KEY (dominio, canal),
                INDEX idx_buscar (canal, buscar)
            ) DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        cur.close()
        _TABLA_LISTA = True
    finally:
        conn.close()


def obtener_canal(dominio, canal, con_secreto=False):
    _asegurar_tabla()
    conn = _conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT * FROM cliente_canales WHERE dominio=%s AND canal=%s", (dominio, canal))
        fila = cur.fetchone()
        cur.close()
    finally:
        conn.close()
    if not fila:
        return None
    fila['datos'] = json.loads(fila.get('datos') or '{}')
    fila['secreto'] = _descifrar(fila.get('secreto')) if con_secreto else None
    return fila


def guardar_canal(dominio, canal, datos, secreto_nuevo=None, buscar=None):
    """secreto_nuevo: dict con los secretos; los campos vacíos conservan el valor anterior."""
    _asegurar_tabla()
    _CACHE.pop(dominio, None)
    actual = obtener_canal(dominio, canal, con_secreto=True) or {}
    secreto = dict(actual.get('secreto') or {})
    for k, v in (secreto_nuevo or {}).items():
        if v:
            secreto[k] = v
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO cliente_canales (dominio, canal, datos, secreto, buscar, activo, estado, mensaje)
            VALUES (%s, %s, %s, %s, %s, 1, 'sin_probar', NULL)
            ON DUPLICATE KEY UPDATE datos=VALUES(datos), secreto=VALUES(secreto), buscar=VALUES(buscar),
                                    activo=1, estado='sin_probar', mensaje=NULL
        """, (dominio, canal, json.dumps(datos or {}, ensure_ascii=False),
              _cifrar(secreto) if secreto else None, buscar))
        conn.commit()
        cur.close()
    finally:
        conn.close()
    return secreto


def marcar_estado(dominio, canal, estado, mensaje=''):
    _asegurar_tabla()
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("""INSERT INTO cliente_canales (dominio, canal, estado, mensaje) VALUES (%s, %s, %s, %s)
                       ON DUPLICATE KEY UPDATE estado=VALUES(estado), mensaje=VALUES(mensaje)""",
                    (dominio, canal, estado, (mensaje or '')[:255]))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def desactivar_canal(dominio, canal):
    _asegurar_tabla()
    _CACHE.pop(dominio, None)
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM cliente_canales WHERE dominio=%s AND canal=%s", (dominio, canal))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def dominio_por(canal, valor):
    """Busca qué cliente tiene ese Page ID (messenger) o ese token (telegram, por su hash)."""
    if not valor:
        return None
    _asegurar_tabla()
    clave = _hash(valor) if canal == 'telegram' else str(valor)
    conn = _conn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT dominio FROM cliente_canales WHERE canal=%s AND buscar=%s AND activo=1 LIMIT 1",
                    (canal, clave))
        r = cur.fetchone()
        cur.close()
        return r[0] if r else None
    finally:
        conn.close()


# ==================== WhatsApp (vive en clientes.cliente) ====================
def _whatsapp_actual(dominio):
    conn = _conn()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT wa_phone_id, wa_token FROM cliente WHERE dominio=%s LIMIT 1", (dominio,))
        r = cur.fetchone() or {}
        cur.close()
        return r
    finally:
        conn.close()


def guardar_whatsapp(dominio, phone_id, token=None):
    try:
        marcar_estado(dominio, 'whatsapp', 'sin_probar', '')
    except Exception:
        pass
    conn = _conn()
    try:
        cur = conn.cursor()
        if token:
            cur.execute("UPDATE cliente SET wa_phone_id=%s, wa_token=%s WHERE dominio=%s", (phone_id, token, dominio))
        else:
            cur.execute("UPDATE cliente SET wa_phone_id=%s WHERE dominio=%s", (phone_id, dominio))
        conn.commit()
        n = cur.rowcount
        cur.close()
        return n
    finally:
        conn.close()


# ==================== Resumen para la pantalla ====================
def resumen(dominio):
    """Lo que ve el panel: nunca incluye tokens completos."""
    out = {}
    wa = _whatsapp_actual(dominio)
    wa_estado = obtener_canal(dominio, 'whatsapp') or {}
    out['whatsapp'] = {
        'configurado': bool(wa.get('wa_phone_id') and wa.get('wa_token')),
        'phone_id': wa.get('wa_phone_id') or '',
        'token': enmascarar(wa.get('wa_token')) if wa.get('wa_token') else '',
        'estado': wa_estado.get('estado') or 'sin_probar',
        'mensaje': wa_estado.get('mensaje') or '',
    }
    for canal in ('messenger', 'telegram', 'linkedin'):
        c = obtener_canal(dominio, canal, con_secreto=True)
        if not c:
            out[canal] = {'configurado': False}
            continue
        s = c.get('secreto') or {}
        d = c.get('datos') or {}
        info = {'configurado': True, 'estado': c.get('estado'), 'mensaje': c.get('mensaje') or ''}
        if canal == 'messenger':
            info.update(page_id=d.get('page_id', ''), page_name=d.get('page_name', ''), token=enmascarar(s.get('token')))
        elif canal == 'telegram':
            info.update(bot=d.get('bot_username', ''), token=enmascarar(s.get('token')))
        elif canal == 'linkedin':
            info.update(correo=d.get('correo', ''), password='••••••••' if s.get('password') else '')
        out[canal] = info
    out['cifrado_listo'] = cifrado_listo()
    return out


# ==================== Pruebas de conexión ====================
def _graph_get(path, token, campos):
    r = requests.get(f"{GRAPH}/{path}", params={'fields': campos, 'access_token': token}, timeout=12)
    data = r.json() if r.content else {}
    if r.status_code != 200:
        msg = (data.get('error') or {}).get('message') or f"HTTP {r.status_code}"
        raise ValueError(msg)
    return data


def probar_whatsapp(dominio):
    wa = _whatsapp_actual(dominio)
    if not (wa.get('wa_phone_id') and wa.get('wa_token')):
        raise ValueError('Faltan el Phone ID o el token')
    d = _graph_get(wa['wa_phone_id'], wa['wa_token'], 'display_phone_number,verified_name')
    return f"Conectado: {d.get('verified_name', '')} ({d.get('display_phone_number', '')})"


def probar_messenger(dominio):
    c = obtener_canal(dominio, 'messenger', con_secreto=True)
    if not c or not (c['secreto'] or {}).get('token'):
        raise ValueError('Falta el token de la página')
    d = _graph_get(c['datos'].get('page_id'), c['secreto']['token'], 'name')
    datos = dict(c['datos'], page_name=d.get('name', ''))
    guardar_canal(dominio, 'messenger', datos, buscar=datos.get('page_id'))
    return f"Conectado a la página: {d.get('name', '')}"


def probar_telegram(dominio, url_base):
    """Valida el bot y registra el webhook apuntando a este servidor."""
    c = obtener_canal(dominio, 'telegram', con_secreto=True)
    token = (c or {}).get('secreto', {}).get('token') if c else None
    if not token:
        raise ValueError('Falta el token del bot')
    r = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=12).json()
    if not r.get('ok'):
        raise ValueError(r.get('description') or 'Token inválido')
    usuario = r['result'].get('username', '')
    w = requests.post(f"https://api.telegram.org/bot{token}/setWebhook",
                      data={'url': f"{url_base.rstrip('/')}/telegram_webhook/{token}"}, timeout=12).json()
    if not w.get('ok'):
        raise ValueError('El bot es válido pero no se pudo registrar el webhook: ' + (w.get('description') or ''))
    guardar_canal(dominio, 'telegram', dict(c['datos'], bot_username=usuario), buscar=_hash(token))
    return f"Conectado: @{usuario} (webhook registrado)"


def probar_linkedin(dominio):
    """Entra por IMAP al correo y cuenta los avisos de LinkedIn de los últimos 7 días."""
    c = obtener_canal(dominio, 'linkedin', con_secreto=True)
    correo = (c or {}).get('datos', {}).get('correo') if c else None
    pw = (c or {}).get('secreto', {}).get('password') if c else None
    if not (correo and pw):
        raise ValueError('Faltan el correo o la contraseña de aplicación')
    host = 'imap.gmail.com'
    try:
        m = imaplib.IMAP4_SSL(host, 993, timeout=15)
        m.login(correo, pw.replace(' ', ''))
    except imaplib.IMAP4.error:
        raise ValueError('Google rechazó el acceso. Revisa el correo y la contraseña de aplicación (16 letras).')
    try:
        m.select('INBOX', readonly=True)
        import datetime
        desde = (datetime.date.today() - datetime.timedelta(days=7)).strftime('%d-%b-%Y')
        typ, data = m.search(None, f'(FROM "linkedin.com" SINCE {desde})')
        n = len(data[0].split()) if typ == 'OK' and data and data[0] else 0
    finally:
        try:
            m.logout()
        except Exception:
            pass
    return f"Conectado a {correo}. Avisos de LinkedIn en los últimos 7 días: {n}"


# ==================== Para el resto de la app ====================
def aplicar_a_config(config, dominio):
    """Completa config con los tokens guardados en la pestaña (si existen)."""
    if not config or not dominio:
        return config
    try:
        hit = _CACHE.get(dominio)
        if hit and time.time() - hit[0] < _CACHE_SEG:
            extra = hit[1]
        else:
            extra = {}
            tg = obtener_canal(dominio, 'telegram', con_secreto=True)
            if tg and (tg.get('secreto') or {}).get('token'):
                extra['telegram_token'] = tg['secreto']['token']
            fb = obtener_canal(dominio, 'messenger', con_secreto=True)
            if fb and (fb.get('secreto') or {}).get('token'):
                extra['page_access_token'] = fb['secreto']['token']
                extra['messenger_page_id'] = (fb.get('datos') or {}).get('page_id')
            _CACHE[dominio] = (time.time(), extra)
        config.update(extra)
    except Exception as e:
        logger.warning(f"⚠️ Canales: no se pudieron aplicar a la config de {dominio}: {e}")
    return config
