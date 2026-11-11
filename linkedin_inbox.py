"""
Bandeja de LinkedIn (solo lectura).

Cada 2 minutos revisa, para cada cliente que conectó LinkedIn en Configuración → Redes sociales,
los correos de aviso de mensajes (messaging-digest-noreply@linkedin.com) y llama a un "manejador"
de la app por cada persona que escribió. Los correos se leen sin marcarlos como leídos.

El correo de LinkedIn NO incluye el texto del mensaje: solo quién escribió, su cargo,
la liga a su perfil y la liga directa a la conversación.
"""
import datetime
import email
import hashlib
import logging
import re
import threading
import time
from email.header import decode_header, make_header
from email.utils import parseaddr

import canales

logger = logging.getLogger(__name__)

REMITENTE = 'messaging-digest-noreply@linkedin.com'
INTERVALO_SEG = 120
DIAS_PRIMERA_VEZ = 3

_RE_SEPARADOR = re.compile(r'^\s*\.{8,}\s*$', re.M)
_RE_HILO = re.compile(r'https://www\.linkedin\.com/(?:comm/)?messaging/thread/([^\s?/]+)')
_RE_PERFIL = re.compile(r'https://[a-z]{0,3}\.?linkedin\.com/in/[^\s?)]+')
_RE_TOTAL = re.compile(r'Tienes\s+(\d+)\s+mensajes?|You have\s+(\d+)\s+new message', re.I)


def _dec(v):
    try:
        return str(make_header(decode_header(v or '')))
    except Exception:
        return v or ''


def _texto_plano(msg):
    for part in msg.walk():
        if part.get_content_type() == 'text/plain':
            return part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', 'replace')
    for part in msg.walk():   # respaldo: HTML sin etiquetas
        if part.get_content_type() == 'text/html':
            html = part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', 'replace')
            html = re.sub(r'<a [^>]*href="([^"]+)"[^>]*>', r' \1 ', html)
            return re.sub(r'<[^>]+>', '\n', html)
    return ''


def numero_para_hilo(hilo_id):
    return 'li_' + hashlib.sha1(hilo_id.encode()).hexdigest()[:14]


def parsear_correo(raw_bytes):
    """Devuelve [{'nombre','titular','perfil_url','hilo_id','hilo_url'}...] (uno por persona)."""
    msg = email.message_from_bytes(raw_bytes)
    nombre_remitente = parseaddr(_dec(msg.get('From')))[0]
    nombre_remitente = re.sub(r'\s+(a través de|via|vía|en)\s+LinkedIn\s*$', '', nombre_remitente, flags=re.I).strip()
    txt = _texto_plano(msg)

    personas = []
    for bloque in _RE_SEPARADOR.split(txt):
        hilo = _RE_HILO.search(bloque)
        if not hilo:
            continue
        lineas = [l.strip() for l in bloque.splitlines() if l.strip() and not l.strip().startswith('(http')]
        primera = lineas[0] if lineas else ''
        if primera.lower().startswith(('ver mensajes', 'view message')):
            primera = ''
        m = re.match(r'^(.*?)\s*\((.*)\)\s*$', primera)
        nombre, titular = (m.group(1), m.group(2)) if m else (primera, '')
        perfil = _RE_PERFIL.search(bloque)
        hilo_id = hilo.group(1)
        personas.append({
            'nombre': (nombre or nombre_remitente or 'Contacto de LinkedIn')[:100],
            'titular': titular[:200],
            'perfil_url': perfil.group(0) if perfil else '',
            'hilo_id': hilo_id,
            'hilo_url': f"https://www.linkedin.com/messaging/thread/{hilo_id}/",
        })

    if not personas:   # formato desconocido: al menos avisar con la bandeja general
        personas.append({'nombre': nombre_remitente or 'Contacto de LinkedIn', 'titular': '',
                         'perfil_url': '', 'hilo_id': 'sin-hilo-' + (msg.get('Message-ID') or str(time.time())),
                         'hilo_url': 'https://www.linkedin.com/messaging/'})
    total = _RE_TOTAL.search(txt)
    n = int(next(g for g in total.groups() if g)) if total else 0
    return personas, n


def _datos_canal(dominio):
    c = canales.obtener_canal(dominio, 'linkedin', con_secreto=True)
    if not c or not c.get('activo', 1):
        return None
    return c


def revisar_dominio(dominio, manejador):
    """Lee los avisos nuevos de un cliente y llama manejador(dominio, persona, fecha) por cada persona."""
    c = _datos_canal(dominio)
    if not c:
        return 0
    datos = dict(c.get('datos') or {})
    correo, pw = datos.get('correo'), (c.get('secreto') or {}).get('password')
    if not (correo and pw):
        return 0

    m = canales.conectar_gmail(correo, pw)
    nuevos = 0
    try:
        m.select('INBOX', readonly=True)
        ultimo = int(datos.get('ultimo_uid') or 0)
        if ultimo:
            criterio = f'(FROM "{REMITENTE}" UID {ultimo + 1}:*)'
        else:
            desde = (datetime.date.today() - datetime.timedelta(days=DIAS_PRIMERA_VEZ)).strftime('%d-%b-%Y')
            criterio = f'(FROM "{REMITENTE}" SINCE {desde})'
        typ, data = m.uid('SEARCH', None, criterio)
        uids = sorted(int(u) for u in (data[0].split() if typ == 'OK' and data and data[0] else []))
        uids = [u for u in uids if u > ultimo]   # IMAP devuelve el último aunque no haya nuevos

        for uid in uids:
            typ, d = m.uid('FETCH', str(uid), '(BODY.PEEK[] INTERNALDATE)')
            if typ != 'OK' or not d or not isinstance(d[0], tuple):
                continue
            personas, _ = parsear_correo(d[0][1])
            for p in personas:
                try:
                    manejador(dominio, p)
                    nuevos += 1
                except Exception as e:
                    logger.error(f"🔴 LinkedIn [{dominio}]: no se pudo registrar a {p.get('nombre')}: {e}")
            ultimo = max(ultimo, uid)

        if not datos.get('ultimo_uid') and not uids:
            # Primera vez y sin avisos recientes: arrancar desde el correo más nuevo
            typ, data = m.uid('SEARCH', None, f'(FROM "{REMITENTE}")')
            todos = [int(u) for u in (data[0].split() if typ == 'OK' and data and data[0] else [])]
            ultimo = max(todos) if todos else 0
        if ultimo != int(datos.get('ultimo_uid') or 0) or 'ultimo_uid' not in datos:
            datos['ultimo_uid'] = ultimo
            canales.actualizar_datos(dominio, 'linkedin', datos)
    finally:
        try:
            m.logout()
        except Exception:
            pass
    return nuevos


def revisar_todos(manejador):
    for dominio in canales.dominios_con('linkedin'):
        try:
            n = revisar_dominio(dominio, manejador)
            if n:
                logger.info(f"💼 LinkedIn [{dominio}]: {n} mensaje(s) nuevo(s)")
        except Exception as e:
            logger.warning(f"⚠️ LinkedIn [{dominio}]: {e}")
            try:
                canales.marcar_estado(dominio, 'linkedin', 'error', str(e))
            except Exception:
                pass


_INICIADO = False
_LOCK = None


def iniciar(manejador):
    """Arranca (una vez por servidor) la revisión periódica en segundo plano."""
    global _INICIADO, _LOCK
    if _INICIADO:
        return
    try:
        import fcntl
        _LOCK = open('/tmp/vv_linkedin_inbox.lock', 'w')
        fcntl.flock(_LOCK, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        logger.info("💼 Bandeja LinkedIn ya corre en otro proceso")
        return
    _INICIADO = True

    def _loop():
        time.sleep(45)
        while True:
            try:
                revisar_todos(manejador)
            except Exception as e:
                logger.warning(f"⚠️ Bandeja LinkedIn: {e}")
            time.sleep(INTERVALO_SEG)

    threading.Thread(target=_loop, daemon=True, name='linkedin-inbox').start()
    logger.info(f"💼 Bandeja LinkedIn activa (revisa cada {INTERVALO_SEG // 60} min)")
