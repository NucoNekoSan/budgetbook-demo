(function () {
  const toggles = document.querySelectorAll('[data-nav-toggle]');
  const openToggle = document.querySelector('.nav-toggle[data-nav-toggle]');
  const backdrop = document.querySelector('[data-nav-backdrop]');
  const nav = document.querySelector('#primary-nav');
  if (!toggles.length || !nav) return;

  const body = document.body;
  let lastFocus = null;

  function setOpen(open) {
    body.classList.toggle('nav-open', open);
    if (openToggle) {
      openToggle.setAttribute('aria-expanded', String(open));
      openToggle.setAttribute('aria-label', open ? 'メニューを閉じる' : 'メニューを開く');
    }
    if (open) {
      lastFocus = document.activeElement;
      const firstLink = nav.querySelector('a, button:not(.nav-close)');
      if (firstLink) firstLink.focus();
    } else if (lastFocus && typeof lastFocus.focus === 'function') {
      lastFocus.focus();
      lastFocus = null;
    }
  }

  toggles.forEach(function (btn) {
    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      setOpen(!body.classList.contains('nav-open'));
    });
  });

  if (backdrop) {
    backdrop.addEventListener('click', function () {
      setOpen(false);
    });
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && body.classList.contains('nav-open')) {
      setOpen(false);
    }
  });

  // Close drawer when navigating via an internal link (single-page anchors etc.)
  nav.addEventListener('click', function (e) {
    const link = e.target.closest('a');
    if (link && body.classList.contains('nav-open')) {
      // Allow the link to navigate; just close the drawer for hash links
      if (link.getAttribute('href') && link.getAttribute('href').startsWith('#')) {
        setOpen(false);
      }
    }
  });

  // Reset drawer state when crossing the mobile breakpoint upward
  const mql = window.matchMedia('(min-width: 769px)');
  mql.addEventListener('change', function (ev) {
    if (ev.matches && body.classList.contains('nav-open')) {
      setOpen(false);
    }
  });
})();