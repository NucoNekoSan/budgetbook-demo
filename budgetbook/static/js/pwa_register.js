/* PWA Service Worker registration.
 * HTTPS / localhost でのみ Service Worker は登録できる (ブラウザの制約)。
 * LAN 内 HTTP では navigator.serviceWorker は無く / register は失敗する。
 */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(function (err) {
      console.warn('SW registration failed:', err);
    });
  });
}
