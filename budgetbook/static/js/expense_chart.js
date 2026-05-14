// Expense breakdown doughnut charts (monthly + yearly)
(function() {
  var COLORS = [
    '#ef4444','#f97316','#eab308','#22c55e','#14b8a6',
    '#3b82f6','#8b5cf6','#ec4899','#6366f1','#0ea5e9',
    '#f43f5e','#a855f7','#84cc16','#06b6d4','#d946ef'
  ];
  var charts = {};

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
    charts[canvasId] = new Chart(el, {
      type: 'doughnut',
      data: {
        labels: raw.map(function(r) { return r.label || r.category__name; }),
        datasets: [{
          data: raw.map(function(r) { return r.total; }),
          backgroundColor: raw.map(function(_, i) { return COLORS[i % COLORS.length]; }),
          borderWidth: 2,
          borderColor: '#fff'
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
    renderPie('income-ratio-pie', 'income-ratio-pie-data');
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initExpenseCharts);
  } else {
    initExpenseCharts();
  }

  window.addEventListener('load', initExpenseCharts);
})();
