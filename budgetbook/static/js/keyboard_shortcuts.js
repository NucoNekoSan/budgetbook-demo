// BudgetBook キーボードショートカット
//
// 有効なショートカット:
//   n  : 取引フォームの「日付」or 摘要欄にフォーカス（ダッシュボード上）
//   /  : フィルタ「摘要」フィールドにフォーカス
//   Esc: 編集中フォームをぼかし、open dialog/details を閉じる
//   ?  : ヘルプダイアログ表示
//
// 入力中（textarea, input, select の active）はショートカットを無視する。
(function () {
  'use strict';

  function isEditableTarget(t) {
    if (!t) return false;
    var tag = (t.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') return true;
    if (t.isContentEditable) return true;
    return false;
  }

  function focusOrSkip(selector) {
    var el = document.querySelector(selector);
    if (el) {
      el.focus();
      if (el.scrollIntoView) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
      return true;
    }
    return false;
  }

  function showHelp() {
    var existing = document.getElementById('keyboard-shortcuts-help');
    if (existing) {
      existing.parentElement.removeChild(existing);
      return;
    }
    var d = document.createElement('div');
    d.id = 'keyboard-shortcuts-help';
    d.className = 'shortcut-help';
    d.setAttribute('role', 'dialog');
    d.setAttribute('aria-label', 'キーボードショートカット');
    d.innerHTML = [
      '<div class="shortcut-help__inner">',
      '  <div class="shortcut-help__title">キーボードショートカット</div>',
      '  <ul>',
      '    <li><kbd>n</kbd> 取引追加フォームへフォーカス</li>',
      '    <li><kbd>/</kbd> フィルタ「摘要」へフォーカス</li>',
      '    <li><kbd>Esc</kbd> このヘルプを閉じる / 入力欄を抜ける</li>',
      '    <li><kbd>?</kbd> このヘルプを表示</li>',
      '  </ul>',
      '  <button type="button" class="btn btn--soft btn--sm" data-shortcut-close>閉じる</button>',
      '</div>'
    ].join('');
    document.body.appendChild(d);
    var btn = d.querySelector('[data-shortcut-close]');
    if (btn) btn.addEventListener('click', function () { d.remove(); });
  }

  document.addEventListener('keydown', function (e) {
    // Esc は入力中でも有効（フォームを抜ける用途）
    if (e.key === 'Escape') {
      var help = document.getElementById('keyboard-shortcuts-help');
      if (help) {
        help.remove();
        return;
      }
      if (document.activeElement && document.activeElement.blur) {
        document.activeElement.blur();
      }
      return;
    }
    // 入力中はその他のショートカットを無視
    if (isEditableTarget(e.target)) return;
    // 修飾キーが押されている場合は無視（ブラウザショートカット衝突回避）
    if (e.ctrlKey || e.metaKey || e.altKey) return;

    if (e.key === 'n') {
      e.preventDefault();
      // 取引追加フォーム上の最初の入力欄
      if (!focusOrSkip('#form-panel input[name="date"]')) {
        focusOrSkip('#form-panel input, #form-panel select');
      }
    } else if (e.key === '/') {
      e.preventDefault();
      focusOrSkip('#filter-q');
    } else if (e.key === '?') {
      e.preventDefault();
      showHelp();
    }
  });
})();