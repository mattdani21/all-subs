const DEFAULT_ENGINE = 'http://127.0.0.1:8765';
const LOOPBACK_RE = /^http:\/\/(127\.0\.0\.1|localhost)(:\d{1,5})?$/;

chrome.runtime.onInstalled.addListener(async () => {
  try {
    const existing = await chrome.storage.sync.get({
      backend: DEFAULT_ENGINE,
      target: 'en',
      bilingual: true,
      deep: false,
      local: false,
      mode: 'local'
    });
    await chrome.storage.sync.set(existing);
  } catch (err) {
    console.error('All Subs init failed:', err);
  }
});

chrome.commands.onCommand.addListener(async (command) => {
  if (command !== 'toggle-panel') return;
  try {
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab || !tab.id) return;
    await chrome.tabs.sendMessage(tab.id, { type: 'allsubs:toggle' });
  } catch {
    // Content script may not be loaded on chrome:// or restricted pages.
  }
});

// Engine proxy: content scripts cannot fetch the loopback engine from an HTTPS
// page (mixed content / private-network blocking), so all API calls go here.
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (!msg || msg.type !== 'allsubs:api') return false;
  (async () => {
    try {
      const rawBase = typeof msg.backend === 'string' ? msg.backend.replace(/\/+$/, '') : '';
      const base = LOOPBACK_RE.test(rawBase) ? rawBase : DEFAULT_ENGINE;
      const path = typeof msg.path === 'string' && msg.path.startsWith('/') ? msg.path : '/';
      const init = { method: msg.method || 'GET', cache: 'no-store' };
      if (msg.body) {
        init.headers = { 'Content-Type': 'application/json' };
        init.body = JSON.stringify(msg.body);
      }
      const res = await fetch(base + path, init);
      const text = await res.text();
      let data = text;
      try {
        data = JSON.parse(text);
      } catch {
        // Non-JSON response (e.g. WebVTT or plain text error).
      }
      sendResponse({ ok: res.ok, status: res.status, data });
    } catch (err) {
      sendResponse({ ok: false, error: String(err) });
    }
  })();
  return true; // keep the channel open for the async response
});
