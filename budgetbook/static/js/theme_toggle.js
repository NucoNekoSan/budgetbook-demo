// Theme toggle: auto (prefers-color-scheme) / light / dark
// Stored in localStorage under 'budgetbook-theme'.
(function () {
  'use strict';
  var STORAGE_KEY = 'budgetbook-theme';
  var ALLOWED = ['auto', 'light', 'dark'];

  function readTheme() {
    try {
      var v = localStorage.getItem(STORAGE_KEY);
      return ALLOWED.indexOf(v) >= 0 ? v : 'auto';
    } catch (e) {
      return 'auto';
    }
  }

  function applyTheme(theme) {
    if (theme === 'auto') {
      document.documentElement.removeAttribute('data-theme');
    } else {
      document.documentElement.setAttribute('data-theme', theme);
    }
  }

  function nextTheme(current) {
    var idx = ALLOWED.indexOf(current);
    return ALLOWED[(idx + 1) % ALLOWED.length];
  }

  function labelFor(theme) {
    if (theme === 'dark') return '🌙 ダーク';
    if (theme === 'light') return '☀ ライト';
    return '🖥 自動';
  }

  function init() {
    var current = readTheme();
    applyTheme(current);
    var btn = document.querySelector('[data-theme-toggle]');
    if (!btn) return;
    btn.textContent = labelFor(current);
    btn.setAttribute('aria-label', 'テーマを切替: 現在 ' + labelFor(current));
    btn.addEventListener('click', function () {
      current = nextTheme(current);
      applyTheme(current);
      try { localStorage.setItem(STORAGE_KEY, current); } catch (e) {}
      btn.textContent = labelFor(current);
      btn.setAttribute('aria-label', 'テーマを切替: 現在 ' + labelFor(current));
      // Notify Chart.js / others to re-read CSS vars
      window.dispatchEvent(new CustomEvent('budgetbook:theme-changed', {
        detail: { theme: current }
      }));
    });
  }

  // Apply ASAP to avoid FOUC (flash of unstyled content)
  applyTheme(readTheme());

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();