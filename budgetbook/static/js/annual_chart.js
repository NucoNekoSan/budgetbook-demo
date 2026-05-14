// Annual trend bar+line chart
(function() {
  function initAnnualChart() {
    var el = document.getElementById('annual-chart');
    if (!el || typeof Chart === 'undefined' || typeof BudgetChart === 'undefined') return;
    var dataEl = document.getElementById('annual-trend-data');
    if (!dataEl) return;
    var raw = JSON.parse(dataEl.textContent);
    var labels = raw.map(function(d) { return d.label; });
    var incomes = raw.map(function(d) { return d.income; });
    var expenses = raw.map(function(d) { return d.expense; });
    var nets = raw.map(function(d) { return d.net; });
    new Chart(el, {
      type: 'bar',
      data: {
        labels: labels,
        datasets: [
          {
            label: '\u53ce\u5165',
            data: incomes,
            backgroundColor: 'rgba(22, 101, 52, 0.7)',
            borderRadius: 4,
            order: 2
          },
          {
            label: '\u652f\u51fa',
            data: expenses,
            backgroundColor: 'rgba(185, 28, 28, 0.7)',
            borderRadius: 4,
            order: 2
          },
          {
            label: '\u5dee\u984d',
            data: nets,
            type: 'line',
            borderColor: '#2563eb',
            backgroundColor: 'rgba(37, 99, 235, 0.1)',
            borderWidth: 2,
            pointRadius: 3,
            fill: false,
            order: 1
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom' }
        },
        scales: {
          y: BudgetChart.yAxisConfig([incomes, expenses, nets])
        }
      }
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAnnualChart);
  } else {
    initAnnualChart();
  }
})();
