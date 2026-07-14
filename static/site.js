(function () {
  'use strict';

  document.documentElement.classList.add('js');
  var body = document.body;
  var navToggle = document.querySelector('[data-nav-toggle]');
  var siteNav = document.getElementById('site-nav');

  function setNavigationOpen(open, restoreFocus) {
    body.classList.toggle('nav-open', open);
    if (!navToggle) return;
    navToggle.setAttribute('aria-expanded', String(open));
    navToggle.setAttribute('aria-label', open ? 'メニューを閉じる' : 'メニューを開く');
    if (!open && restoreFocus) navToggle.focus();
  }

  if (navToggle) {
    navToggle.addEventListener('click', function () {
      setNavigationOpen(!body.classList.contains('nav-open'), false);
    });
  }

  document.querySelectorAll('.site-nav a').forEach(function (link) {
    link.addEventListener('click', function () {
      setNavigationOpen(false, false);
    });
  });

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && body.classList.contains('nav-open')) {
      setNavigationOpen(false, true);
    }
  });

  document.addEventListener('pointerdown', function (event) {
    if (!body.classList.contains('nav-open')) return;
    if (siteNav && siteNav.contains(event.target)) return;
    if (navToggle && navToggle.contains(event.target)) return;
    setNavigationOpen(false, false);
  });

  window.addEventListener('resize', function () {
    if (window.innerWidth > 760 && body.classList.contains('nav-open')) {
      setNavigationOpen(false, false);
    }
  });

  document.querySelectorAll('[data-current-year]').forEach(function (element) {
    element.textContent = String(new Date().getFullYear());
  });

  function setStatus(state, message, detail) {
    document.querySelectorAll('[data-service-status]').forEach(function (element) {
      element.classList.remove('is-ready', 'is-error');
      element.classList.add(state);
    });
    document.querySelectorAll('[data-status-message]').forEach(function (element) {
      element.textContent = message;
    });
    document.querySelectorAll('[data-status-detail]').forEach(function (element) {
      element.textContent = detail;
    });
  }

  fetch('/readyz', {cache: 'no-store'})
    .then(function (response) {
      if (!response.ok) throw new Error('not ready');
      return response.json();
    })
    .then(function (payload) {
      setStatus('is-ready', '正常稼働中', payload.detail || 'ready');
    })
    .catch(function () {
      setStatus('is-error', '確認できません', 'not ready');
    });

  if (window.WebFont) {
    var baseUrl = window.location.origin;
    Promise.all([
      window.WebFont.load({
        baseUrl: baseUrl,
        font: 'zen-kaku-regular',
        family: 'Zen Kaku Gothic New',
        selectors: ['body']
      }),
      window.WebFont.load({
        baseUrl: baseUrl,
        font: 'zen-maru-regular',
        family: 'Zen Maru Gothic',
        selectors: ['h1', 'h2', '.brand-mark']
      })
    ]).catch(function () {
      // System font fallbacks keep the information pages usable.
    });
  }
})();
