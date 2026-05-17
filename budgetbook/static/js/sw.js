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
/* CACHE_VERSION は ledger/views/pwa.py が配信時に '__CACHE_VERSION__' を
   STATIC_VERSION で置換する。直接 ファイルを読み込むと placeholder のままなので、
   必ず /sw.js (Django view 経由) からアクセスすること。
   placeholder 文字列を変更すると pwa.py + test_pwa_sw_view.py の両方の更新が必須。 */
const CACHE_VERSION = '__CACHE_VERSION__';
const APP_SHELL = [
  '/offline',
  // v1.19.0: style.css は 5 ファイル分割。全て precache する。
  '/static/css/_01_base.css',
  '/static/css/_02_layout_cards.css',
  '/static/css/_03_components.css',
  '/static/css/_04_pages_responsive.css',
  '/static/css/_05_features_v119.css',
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

// v1.18.6: pwa_register.js から SKIP_WAITING メッセージを受けたら即 activate.
// updatefound 検知 → postMessage → activate → controllerchange → reload の連鎖で
// 古いキャッシュに残されたユーザーを自動的に最新版へ移行させる。
// v1.19.x: CodeQL js/missing-origin-check 対応 — event.source の origin を明示的検証
// (SW scope は同一 origin に限定されるが、defense in depth として実施)。
self.addEventListener('message', (event) => {
  if (event.source && event.source.url) {
    try {
      const srcOrigin = new URL(event.source.url).origin;
      if (srcOrigin !== self.location.origin) return;
    } catch (_) {
      return;
    }
  }
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
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