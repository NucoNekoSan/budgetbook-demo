/* BudgetBook Service Worker (v1.9.0)
 *
 * Strategy:
 *   - precache: app shell (offline page + minimal static assets)
 *   - GET /static/* : cache-first
 *   - GET HTML (navigations): network-first, fallback to cache, then /offline
 *   - non-GET (POST/PUT/PATCH/DELETE): NEVER intercept (data freshness > offline)
 *
 * Caches are versioned. activate purges old caches.
 */
const CACHE_VERSION = 'bb-v1.9.0-1';
const APP_SHELL = [
  '/offline',
  '/static/css/style.css',
  '/static/js/htmx_config.js',
  '/static/js/theme_toggle.js',
  '/static/icons/icon.svg',
  '/static/icons/icon-192.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_VERSION).then((cache) => cache.addAll(APP_SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_VERSION).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);
  if (url.origin !== self.location.origin) return;

  // Never cache /healthz (operational endpoint) or /sw.js (always fresh)
  if (url.pathname === '/healthz' || url.pathname === '/sw.js') return;

  // Static assets → cache-first
  if (url.pathname.startsWith('/static/')) {
    event.respondWith(
      caches.match(req).then((cached) =>
        cached || fetch(req).then((resp) => {
          if (resp.ok) {
            const copy = resp.clone();
            caches.open(CACHE_VERSION).then((cache) => cache.put(req, copy));
          }
          return resp;
        }).catch(() => cached)
      )
    );
    return;
  }

  // HTML navigations → network-first
  const accept = req.headers.get('accept') || '';
  if (req.mode === 'navigate' || accept.includes('text/html')) {
    event.respondWith(
      fetch(req).catch(() =>
        caches.match(req).then((cached) => cached || caches.match('/offline'))
      )
    );
    return;
  }

  // Everything else: passthrough (no caching)
});