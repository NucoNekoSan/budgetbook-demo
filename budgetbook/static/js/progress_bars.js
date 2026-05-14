// 予算進捗バーの幅を data-pct から動的に設定する。
// CSP の inline-style 禁止に対応するため style プロパティは JS から設定。
(function () {
  'use strict';
  function applyProgressBars(root) {
    var bars = (root || document).querySelectorAll('.progress-bar__fill[data-pct]');
    bars.forEach(function (el) {
      var pct = parseFloat(el.getAttribute('data-pct')) || 0;
      // 上限 100% で width を頭打ち。超過時はクラスで色分け（CSS 側）
      var width = Math.min(pct, 100);
      el.style.width = width + '%';
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', function () { applyProgressBars(); });
  } else {
    applyProgressBars();
  }

  // HTMX で部分更新された後にも再適用
  document.body.addEventListener('htmx:afterSwap', function (e) {
    applyProgressBars(e.target);
  });
})();