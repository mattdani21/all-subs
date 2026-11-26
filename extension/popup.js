const dot = document.getElementById('dot');
const statusEl = document.getElementById('status');

(async () => {
  try {
    const cfg = await chrome.storage.sync.get({ backend: 'http://127.0.0.1:8765' });
    const base = (cfg.backend || 'http://127.0.0.1:8765').replace(/\/+$/, '');
    const res = await fetch(base + '/health', { cache: 'no-store' });
    const d = await res.json();
    dot.classList.add(d.ok ? 'ok' : 'err');
    statusEl.textContent = d.ok
      ? `Engine online · v${d.version || '?'} · ${d.jobs} job${d.jobs === 1 ? '' : 's'}`
      : 'Engine offline';
  } catch {
    dot.classList.add('err');
    statusEl.textContent = 'Engine offline — run ./allsubs start';
  }
})();

document.getElementById('open').addEventListener('click', async () => {
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab && tab.id) {
      await chrome.tabs.sendMessage(tab.id, { type: 'allsubs:open' });
    }
  } catch {
    // Ignore restricted tabs where content scripts cannot run.
  }
  window.close();
});
