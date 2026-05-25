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

  document.addEventListener('submit', function(event) {
    var form = event.target;
    if (!form || form.tagName !== 'FORM') return;

    var message = form.getAttribute('data-confirm');
    if (!message) return;

    if (form.getAttribute('data-confirmed') === 'true') {
      form.removeAttribute('data-confirmed');
      return;
    }

    if (!window.confirm(message)) {
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  });

  document.addEventListener('click', function(event) {
    var button = event.target.closest('[data-confirm-submit]');
    if (!button || button.disabled) return;

    var form = button.form;
    if (!form) return;

    var message = form.getAttribute('data-confirm') || button.getAttribute('data-confirm-submit');
    if (!message) return;

    if (!window.confirm(message)) return;

    form.setAttribute('data-confirmed', 'true');
    if (typeof form.requestSubmit === 'function') {
      form.requestSubmit();
    } else {
      form.submit();
    }
  });
})();
