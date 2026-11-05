// Service worker del panel (PWA).
// A propósito NO guarda en caché chats ni datos: el panel siempre trae información fresca.
// Solo muestra una página amigable cuando no hay internet.
const CACHE = 'vv-pwa-v1';
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
