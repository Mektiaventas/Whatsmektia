// Service worker del panel (PWA).
// A propósito NO guarda en caché chats ni datos: el panel siempre trae información fresca.
// Solo muestra una página amigable cuando no hay internet.
const CACHE = 'vv-pwa-v2';
const OFFLINE_URL = '/static/pwa/offline.html';

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.add(OFFLINE_URL)));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  // Solo intercepta la carga de páginas; todo lo demás (APIs, imágenes, POST) pasa directo.
  if (event.request.mode !== 'navigate') return;
  event.respondWith(fetch(event.request).catch(() => caches.match(OFFLINE_URL)));
});

// ---------- Notificaciones push ----------
self.addEventListener('push', (event) => {
  let d = {};
  try { d = event.data ? event.data.json() : {}; }
  catch (e) { d = { title: 'Vendedor Virtual', body: event.data ? event.data.text() : '' }; }
  const opciones = {
    body: d.body || '',
    icon: '/pwa/icon-192.png',
    data: { url: d.url || '/chats' },
    vibrate: [120, 60, 120],
  };
  if (d.tag) { opciones.tag = d.tag; opciones.renotify = true; }
  event.waitUntil(self.registration.showNotification(d.title || 'Vendedor Virtual', opciones));
});

// Al tocar el aviso: abre (o reutiliza) la app en ese chat
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const destino = new URL((event.notification.data && event.notification.data.url) || '/chats', self.location.origin).href;
  event.waitUntil((async () => {
    const ventanas = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
    for (const v of ventanas) {
      if (v.url.startsWith(self.location.origin)) {
        await v.focus();
        if ('navigate' in v) { try { await v.navigate(destino); } catch (e) {} }
        return;
      }
    }
    await self.clients.openWindow(destino);
  })());
});
