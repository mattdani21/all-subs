const dot = document.getElementById('dot');
const statusEl = document.getElementById('status');

chrome.storage.sync.get({ backend: 'http://127.0.0.1:8765' }, function (cfg) {
  fetch(cfg.backend + '/health', { cache: 'no-store' })
    .then(function (r) { return r.json(); })
    .then(function (d) {
      dot.classList.add(d.ok ? 'ok' : 'err');
      statusEl.textContent = d.ok
        ? 'Engine online · ' + d.jobs + ' job' + (d.jobs === 1 ? '' : 's')
        : 'Engine offline';
    })
    .catch(function () {
      dot.classList.add('err');
      statusEl.textContent = 'Engine offline — run ./allsubs start';
    });
});

document.getElementById('open').addEventListener('click', function () {
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    if (tabs && tabs[0]) {
      chrome.tabs.sendMessage(tabs[0].id, { type: 'allsubs:open' }, function () {
        void chrome.runtime.lastError;
      });
    }
    window.close();
  });
});
