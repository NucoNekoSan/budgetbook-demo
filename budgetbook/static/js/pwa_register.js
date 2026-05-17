/* PWA Service Worker registration + auto-update.
 * HTTPS / localhost でのみ Service Worker は登録できる (ブラウザの制約)。
 * LAN 内 HTTP では navigator.serviceWorker は無く / register は失敗する。
 *
 * v1.18.6: 新しい SW が利用可能になったら自動で「リロードして反映」する。
 * これがないと PWA インストール済みユーザーが古いキャッシュに永久に取り残される。
 */
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function () {
    navigator.serviceWorker.register('/sw.js', { scope: '/' }).then(function (reg) {
      // 既に新しい SW が waiting 中の場合 (前回の読み込みで install 済み) → 即 activate
      if (reg.waiting) {
        reg.waiting.postMessage({ type: 'SKIP_WAITING' });
      }
      // 新しい SW が見つかったら追跡
      reg.addEventListener('updatefound', function () {
        var newWorker = reg.installing;
        if (!newWorker) return;
        newWorker.addEventListener('statechange', function () {
          // 旧 SW が controller として存在し、新 SW が installed になった瞬間 = update available
          if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
            newWorker.postMessage({ type: 'SKIP_WAITING' });
          }
        });
      });
      // 6 時間ごとにアップデートチェック (バックグラウンドタブ等で長時間開いたまま用)
      setInterval(function () {
        reg.update().catch(function () { /* offline 等は無視 */ });
      }, 6 * 60 * 60 * 1000);
    }).catch(function (err) {
      console.warn('SW registration failed:', err);
    });

    // 新 SW が controller を引き継いだら一度だけリロード
    var refreshing = false;
    navigator.serviceWorker.addEventListener('controllerchange', function () {
      if (refreshing) return;
      refreshing = true;
      window.location.reload();
    });
  });
}