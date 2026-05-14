(function() {
  document.body.addEventListener('htmx:beforeSwap', function(event) {
    if (event.detail.xhr.status === 422 || event.detail.xhr.status === 409) {
      event.detail.shouldSwap = true;
      event.detail.isError = false;
    }
  });

  document.body.addEventListener('budgetbook:scrollTo', function(event) {
    var targetId = event.detail && event.detail.targetId;
    if (!targetId) return;

    window.setTimeout(function() {
      var target = document.getElementById(targetId);
      if (!target) return;
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 0);
  });
})();
