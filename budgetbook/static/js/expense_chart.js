// Expense breakdown doughnut charts (monthly + yearly)
(function() {
  var COLORS = [
    '#ef4444', '#f97316', '#eab308', '#22c55e', '#14b8a6',
    '#3b82f6', '#8b5cf6', '#ec4899', '#6366f1', '#0ea5e9',
    '#f43f5e', '#a855f7', '#84cc16', '#06b6d4', '#d946ef'
  ];
  var CATEGORY_COLORS = {
    '食費': '#22c55e',
    '日用品': '#14b8a6',
    '外食': '#f97316',
    '水道光熱費': '#eab308',
    '通信費': '#0ea5e9',
    '家賃・住宅ローン': '#6366f1',
    '交通費': '#3b82f6',
    '教育費': '#8b5cf6',
    '娯楽': '#ec4899',
    '衣料・美容': '#d946ef',
    '医療費': '#ef4444',
    '交際費': '#a855f7',
    '保険料': '#84cc16',
    '税金': '#f43f5e',
    'サブスク': '#06b6d4'
  };
  var charts = {};

  function colorForLabel(label) {
    if (CATEGORY_COLORS[label]) return CATEGORY_COLORS[label];
    var hash = 0;
    for (var i = 0; i < label.length; i++) {
      hash = ((hash << 5) - hash) + label.charCodeAt(i);
      hash |= 0;
    }
    return COLORS[Math.abs(hash) % COLORS.length];
  }

  function renderPie(canvasId, dataId) {
    var el = document.getElementById(canvasId);
    if (!el) return;
    var dataEl = document.getElementById(dataId);
    if (!dataEl) return;
    var raw = JSON.parse(dataEl.textContent);
    if (!raw.length) return;
    if (charts[canvasId]) {
      charts[canvasId].destroy();
      charts[canvasId] = null;
    }
    var labels = raw.map(function(r) { return r.label || r.category__name; });
    var panelColor = getComputedStyle(document.documentElement).getPropertyValue('--panel').trim() || '#fff';
    charts[canvasId] = new Chart(el, {
      type: 'doughnut',
      data: {
        labels: labels,
        datasets: [{
          data: raw.map(function(r) { return r.total; }),
          backgroundColor: labels.map(colorForLabel),
          borderWidth: 2,
          borderColor: panelColor
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 14, padding: 10 } },
          tooltip: {
            callbacks: {
              label: function(ctx) {
                var v = ctx.parsed;
                var total = ctx.dataset.data.reduce(function(a,b){return a+b;},0);
                var pct = total ? (v/total*100).toFixed(1) : 0;
                return ctx.label + ': \u00a5' + v.toLocaleString('ja-JP') + ' (' + pct + '%)';
              }
            }
          }
        }
      }
    });
  }

  function initExpenseCharts() {
    if (typeof Chart === 'undefined') {
      window.setTimeout(initExpenseCharts, 100);
      return;
    }
    renderPie('monthly-pie', 'monthly-pie-data');
    renderPie('yearly-pie', 'yearly-pie-data');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initExpenseCharts);
  } else {
    initExpenseCharts();
  }

  window.addEventListener('load', initExpenseCharts);
})();
