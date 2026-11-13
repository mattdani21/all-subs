chrome.runtime.onInstalled.addListener(function () {
  chrome.storage.sync.get({
    backend: 'http://127.0.0.1:8765',
    target: 'en',
    bilingual: true,
    deep: false,
    local: false,
    cloudAsr: false
  }, function (v) { chrome.storage.sync.set(v); });
});

chrome.commands.onCommand.addListener(function (command) {
  if (command !== 'toggle-panel') return;
  chrome.tabs.query({ active: true, currentWindow: true }, function (tabs) {
    if (!tabs || !tabs[0]) return;
    chrome.tabs.sendMessage(tabs[0].id, { type: 'allsubs:toggle' }, function () {
      void chrome.runtime.lastError;
    });
  });
});

// Engine proxy: content scripts cannot fetch the loopback engine from an HTTPS
// page (mixed content / private-network blocking), so all API calls go here.
const ENGINE = 'http://127.0.0.1:8765';

chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
  if (!msg || msg.type !== 'allsubs:api') return false;
  const init = { method: msg.method || 'GET', cache: 'no-store' };
  if (msg.body) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(msg.body);
  }
  fetch(ENGINE + msg.path, init)
    .then(function (r) { return r.text().then(function (t) { return { r: r, t: t }; }); })
    .then(function (out) {
      let data = null;
      try { data = JSON.parse(out.t); } catch (e) { data = out.t; }
      sendResponse({ ok: out.r.ok, status: out.r.status, data: data });
    })
    .catch(function (e) { sendResponse({ ok: false, error: String(e) }); });
  return true;  // keep the channel open for the async response
});
