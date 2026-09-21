/* SoA EDM Studio – minimal helpers (no external libraries; works offline). */
(function () {
  'use strict';
  // Partial polling: <div data-poll="/jobs/partial" data-interval="4000">
  document.querySelectorAll('[data-poll]').forEach(function (el) {
    var url = el.getAttribute('data-poll');
    var iv = parseInt(el.getAttribute('data-interval') || '4000', 10);
    function tick() {
      if (document.hidden) return;
      fetch(url, { headers: { 'Accept': 'text/html' }, credentials: 'same-origin' })
        .then(function (r) { return r.ok ? r.text() : ''; })
        .then(function (html) { if (html) el.innerHTML = html; })
        .catch(function () {});
    }
    setInterval(tick, iv);
  });
  // Confirm dialogs
  document.querySelectorAll('form[data-confirm]').forEach(function (f) {
    f.addEventListener('submit', function (e) {
      if (!window.confirm(f.getAttribute('data-confirm'))) e.preventDefault();
    });
  });
  // Range value display
  document.querySelectorAll('input[type=range][data-out]').forEach(function (r) {
    var out = document.getElementById(r.getAttribute('data-out'));
    var upd = function () { if (out) out.textContent = r.value; };
    r.addEventListener('input', upd); upd();
  });
  // Service worker
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/sw.js').catch(function () {});
  }
  // Copy buttons
  document.querySelectorAll('[data-copy]').forEach(function (b) {
    b.addEventListener('click', function () {
      var src = document.getElementById(b.getAttribute('data-copy'));
      var text = src ? (src.value !== undefined ? src.value : src.textContent) : '';
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(function () { b.textContent = 'コピーしました'; });
      } else {
        var ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select();
        try { document.execCommand('copy'); b.textContent = 'コピーしました'; } catch (e) {}
        document.body.removeChild(ta);
      }
    });
  });
})();
