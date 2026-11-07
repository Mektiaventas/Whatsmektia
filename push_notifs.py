"""
Notificaciones push (Web Push) para la app del Vendedor Virtual.

- Cada cliente (subdominio) guarda en SU base de datos los celulares que activaron avisos
  (tabla push_subscriptions).
- enviar_push_tenant() manda el aviso a todos esos celulares en segundo plano,
  sin frenar el webhook de WhatsApp.
- Las llaves VAPID se leen del .env: VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, VAPID_SUBJECT.
- "Pendiente de asesor": cuando la IA pide un humano, el chat queda marcado (tabla pendientes_asesor)
  hasta que alguien conteste desde el panel o lo marque como atendido. Si nadie lo atiende,
  se vuelve a avisar cada RECORDATORIO_MIN minutos, hasta RECORDATORIO_MAX veces.
"""
import hashlib
import json
import logging
import os
import threading
import time

from services import get_db_connection

logger = logging.getLogger(__name__)

_TABLAS_LISTAS = set()

AVISO_TTL = 24 * 3600        # si el cel está apagado, el aviso espera hasta 24 h
RECORDATORIO_MIN = 30        # minutos entre recordatorios
RECORDATORIO_MAX = 4         # recordatorios máximos por alerta


def vapid_public_key():
    return (os.getenv('VAPID_PUBLIC_KEY') or '').strip()


def push_configurado():
    return bool(vapid_public_key() and (os.getenv('VAPID_PRIVATE_KEY') or '').strip())


def _asegurar_tabla(config):
    db = (config or {}).get('db_name', 'mektia')
    if db in _TABLAS_LISTAS:
        return
    conn = get_db_connection(config)
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                endpoint_hash CHAR(64) NOT NULL UNIQUE,
                endpoint TEXT NOT NULL,
                p256dh VARCHAR(255) NOT NULL,
                auth VARCHAR(100) NOT NULL,
                usuario VARCHAR(100) NULL,
                user_agent VARCHAR(255) NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_ok DATETIME NULL
            ) DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        cur.close()
        _TABLAS_LISTAS.add(db)
    finally:
        conn.close()


def _hash(endpoint):
    return hashlib.sha256(endpoint.encode('utf-8')).hexdigest()


def guardar_suscripcion(config, sub, usuario=None, user_agent=None):
    """sub = PushSubscription.toJSON() del navegador: {endpoint, keys:{p256dh, auth}}"""
    endpoint = (sub or {}).get('endpoint') or ''
    keys = (sub or {}).get('keys') or {}
    if not endpoint.startswith('https://') or not keys.get('p256dh') or not keys.get('auth'):
        raise ValueError('Suscripción inválida')
    _asegurar_tabla(config)
    conn = get_db_connection(config)
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO push_subscriptions (endpoint_hash, endpoint, p256dh, auth, usuario, user_agent)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE p256dh=VALUES(p256dh), auth=VALUES(auth),
                                    usuario=VALUES(usuario), user_agent=VALUES(user_agent)
        """, (_hash(endpoint), endpoint, keys['p256dh'], keys['auth'],
              (usuario or '')[:100], (user_agent or '')[:255]))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def borrar_suscripcion(config, endpoint):
    if not endpoint:
        return
    _asegurar_tabla(config)
    conn = get_db_connection(config)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM push_subscriptions WHERE endpoint_hash = %s", (_hash(endpoint),))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def _enviar_ahora(config, payload):
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.error("🔕 PUSH: falta instalar pywebpush (pip install pywebpush)")
        return 0
    if not push_configurado():
        logger.warning("🔕 PUSH: faltan VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY en el .env")
        return 0

    _asegurar_tabla(config)
    conn = get_db_connection(config)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("SELECT id, endpoint, p256dh, auth FROM push_subscriptions")
        subs = cur.fetchall()
        cur.close()
    finally:
        conn.close()

    if not subs:
        logger.info(f"🔕 PUSH [{config.get('db_name')}]: nadie ha activado avisos todavía")
        return 0

    data = json.dumps(payload, ensure_ascii=False)
    privada = os.getenv('VAPID_PRIVATE_KEY').strip()
    sujeto = (os.getenv('VAPID_SUBJECT') or 'mailto:soporte@mektia.com').strip()
    enviados, muertas, ok_ids = 0, [], []

    for s in subs:
        try:
            webpush(
                subscription_info={"endpoint": s['endpoint'],
                                   "keys": {"p256dh": s['p256dh'], "auth": s['auth']}},
                data=data,
                vapid_private_key=privada,
                vapid_claims={"sub": sujeto},   # dict nuevo en cada envío (pywebpush lo modifica)
                ttl=AVISO_TTL,
                timeout=10,
            )
            enviados += 1
            ok_ids.append(s['id'])
        except WebPushException as e:
            code = getattr(getattr(e, 'response', None), 'status_code', None)
            if code in (404, 410):          # el celular desinstaló la app o quitó el permiso
                muertas.append(s['id'])
            else:
                logger.warning(f"⚠️ PUSH error ({code}) en suscripción {s['id']}: {e}")
        except Exception as e:
            logger.warning(f"⚠️ PUSH error en suscripción {s['id']}: {e}")

    if muertas or ok_ids:
        conn = get_db_connection(config)
        try:
            cur = conn.cursor()
            if muertas:
                cur.execute(f"DELETE FROM push_subscriptions WHERE id IN ({','.join(['%s'] * len(muertas))})", muertas)
            if ok_ids:
                cur.execute(f"UPDATE push_subscriptions SET last_ok = NOW() WHERE id IN ({','.join(['%s'] * len(ok_ids))})", ok_ids)
            conn.commit()
            cur.close()
        finally:
            conn.close()

    logger.info(f"🔔 PUSH [{config.get('db_name')}]: '{payload.get('title')}' → {enviados} enviados, {len(muertas)} eliminados")
    return enviados


def enviar_push_tenant(config, titulo, cuerpo, url='/chats', tag=None, esperar=False):
    """Manda un aviso a todos los celulares del cliente (config = config del tenant).
    Por defecto corre en segundo plano para no frenar el webhook."""
    if not config:
        return 0
    cfg = dict(config)  # copia: el hilo no depende del request
    payload = {"title": (titulo or 'Aviso')[:80], "body": (cuerpo or '')[:180], "url": url or '/chats'}
    if tag:
        payload["tag"] = tag

    def _run():
        try:
            return _enviar_ahora(cfg, payload)
        except Exception as e:
            logger.error(f"🔴 PUSH falló: {e}")
            return 0

    if esperar:
        return _run()
    threading.Thread(target=_run, daemon=True).start()
    return None


# ==================== Pendientes de asesor ====================
_PEND_LISTAS = set()


def _asegurar_tabla_pendientes(config):
    db = (config or {}).get('db_name', 'mektia')
    if db in _PEND_LISTAS:
        return
    conn = get_db_connection(config)
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pendientes_asesor (
                numero VARCHAR(64) PRIMARY KEY,
                cliente VARCHAR(120) NULL,
                asesor VARCHAR(120) NULL,
                motivo VARCHAR(255) NULL,
                desde DATETIME DEFAULT CURRENT_TIMESTAMP,
                ultimo_aviso DATETIME DEFAULT CURRENT_TIMESTAMP,
                recordatorios INT DEFAULT 0
            ) DEFAULT CHARSET=utf8mb4
        """)
        conn.commit()
        cur.close()
        _PEND_LISTAS.add(db)
    finally:
        conn.close()


def marcar_pendiente(config, numero, cliente=None, asesor=None, motivo=None):
    """Marca el chat como 'esperando asesor'. Si ya estaba, conserva la hora original."""
    if not numero:
        return
    _asegurar_tabla_pendientes(config)
    conn = get_db_connection(config)
    try:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO pendientes_asesor (numero, cliente, asesor, motivo, desde, ultimo_aviso, recordatorios)
            VALUES (%s, %s, %s, %s, NOW(), NOW(), 0)
            ON DUPLICATE KEY UPDATE cliente=VALUES(cliente), asesor=VALUES(asesor), motivo=VALUES(motivo),
                                    ultimo_aviso=NOW(), recordatorios=0
        """, (numero[:64], (cliente or '')[:120], (asesor or '')[:120], (motivo or '')[:255]))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def limpiar_pendiente(config, numero):
    if not numero:
        return
    _asegurar_tabla_pendientes(config)
    conn = get_db_connection(config)
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM pendientes_asesor WHERE numero = %s", (numero,))
        conn.commit()
        cur.close()
    finally:
        conn.close()


def listar_pendientes(config):
    _asegurar_tabla_pendientes(config)
    conn = get_db_connection(config)
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute("""SELECT numero, cliente, asesor, motivo,
                              TIMESTAMPDIFF(MINUTE, desde, NOW()) AS minutos
                       FROM pendientes_asesor ORDER BY desde""")
        filas = cur.fetchall()
        cur.close()
        return filas
    finally:
        conn.close()


def _texto_tiempo(minutos):
    m = int(minutos or 0)
    if m < 60:
        return f"{m} min"
    h, r = divmod(m, 60)
    return f"{h} h {r} min" if r else f"{h} h"


def _revisar_recordatorios():
    """Busca en todas las BD de clientes los pendientes que toca recordar."""
    conn = get_db_connection({'db_name': 'mektia'})
    try:
        cur = conn.cursor()
        cur.execute("SELECT table_schema FROM information_schema.tables WHERE table_name = 'pendientes_asesor'")
        bases = [r[0] for r in cur.fetchall()]
        cur.close()
    finally:
        conn.close()

    for db in bases:
        cfg = {'db_name': db}
        try:
            conn = get_db_connection(cfg)
            try:
                cur = conn.cursor(dictionary=True)
                cur.execute("""SELECT numero, cliente, asesor, recordatorios,
                                      TIMESTAMPDIFF(MINUTE, desde, NOW()) AS minutos
                               FROM pendientes_asesor
                               WHERE recordatorios < %s
                                 AND ultimo_aviso <= NOW() - INTERVAL %s MINUTE""",
                            (RECORDATORIO_MAX, RECORDATORIO_MIN))
                filas = cur.fetchall()
                for f in filas:
                    cur.execute("""UPDATE pendientes_asesor SET recordatorios = recordatorios + 1, ultimo_aviso = NOW()
                                   WHERE numero = %s""", (f['numero'],))
                conn.commit()
                cur.close()
            finally:
                conn.close()

            for f in filas:
                n = int(f['recordatorios'] or 0) + 1
                quien = f" · {f['asesor']}" if f.get('asesor') else ""
                ultimo = " (último aviso)" if n >= RECORDATORIO_MAX else ""
                _enviar_ahora(cfg, {
                    "title": f"⏰ Sigue pendiente: {f.get('cliente') or f['numero']}",
                    "body": f"Espera asesor desde hace {_texto_tiempo(f['minutos'])}{quien}. Recordatorio {n}/{RECORDATORIO_MAX}{ultimo}",
                    "url": f"/chats/{f['numero']}",
                    "tag": f"alerta-{f['numero']}",
                })
        except Exception as e:
            logger.warning(f"⚠️ Recordatorios [{db}]: {e}")


_RECORDATORIOS_INICIADOS = False
_LOCK_FILE = None


def iniciar_recordatorios(intervalo_seg=60):
    """Arranca (una sola vez por servidor) el revisor de recordatorios en segundo plano."""
    global _RECORDATORIOS_INICIADOS, _LOCK_FILE
    if _RECORDATORIOS_INICIADOS:
        return
    try:  # candado: si hay más de un proceso, solo uno manda recordatorios
        import fcntl
        _LOCK_FILE = open('/tmp/vv_push_recordatorios.lock', 'w')
        fcntl.flock(_LOCK_FILE, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        logger.info("⏰ Recordatorios ya corren en otro proceso")
        return
    _RECORDATORIOS_INICIADOS = True

    def _loop():
        time.sleep(30)
        while True:
            try:
                _revisar_recordatorios()
            except Exception as e:
                logger.warning(f"⚠️ Recordatorios: {e}")
            time.sleep(intervalo_seg)

    threading.Thread(target=_loop, daemon=True, name='push-recordatorios').start()
    logger.info(f"⏰ Recordatorios de asesor activos (cada {RECORDATORIO_MIN} min, máx {RECORDATORIO_MAX})")
