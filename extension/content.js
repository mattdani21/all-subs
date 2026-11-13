/* All Subs — in-page controller: finds the video, talks to the local engine,
   and feeds cues to the overlay renderer. */
(function () {
  if (window.__allSubsContent) return;
  window.__allSubsContent = true;
  window.addEventListener('error', function (e) {
    try {
      document.documentElement.setAttribute(
        'data-allsubs-error', (e.message || 'error') + ' @' + (e.lineno || 0));
    } catch (err) { /* noop */ }
  });

  const DEFAULTS = {
    backend: 'http://127.0.0.1:8765',
    target: 'en',
    bilingual: true,
    deep: false,
    local: false,
    cloudAsr: false
  };
  const LANGS = [
    ['en', 'English'], ['zh', 'Chinese'], ['ko', 'Korean'], ['ja', 'Japanese'],
    ['es', 'Spanish'], ['fr', 'French'], ['de', 'German'], ['pt', 'Portuguese'],
    ['ru', 'Russian'], ['ar', 'Arabic'], ['hi', 'Hindi'], ['id', 'Indonesian']
  ];

  let cfg = Object.assign({}, DEFAULTS);
  try {
    chrome.storage.sync.get(DEFAULTS, function (v) { cfg = Object.assign(cfg, v); paintConfig(); });
    chrome.storage.onChanged.addListener(function (changes) {
      Object.keys(changes).forEach(function (k) { if (k in cfg) cfg[k] = changes[k].newValue; });
      paintConfig();
    });
  } catch (e) { /* test page without chrome APIs */ }

  const S = {
    video: null, overlay: null, host: null, root: null,
    job: null, cues: [], total: 0, version: -1, pass2: false,
    polling: null, panelOpen: false, busy: false, lastError: ''
  };

  const CSS = `
    :host { all: initial; }
    * { box-sizing: border-box; }
    .launcher {
      position: absolute; right: 14px; bottom: 74px; width: 40px; height: 40px;
      border-radius: 12px; border: 1px solid rgba(255,255,255,.16);
      background: rgba(12,14,18,.82); color: #fff; font: 600 12px/1 -apple-system, system-ui, sans-serif;
      letter-spacing: .06em; cursor: pointer; display: flex; align-items: center; justify-content: center;
      backdrop-filter: blur(10px); box-shadow: 0 6px 24px rgba(0,0,0,.45);
      transition: transform .15s ease, background .15s ease;
    }
    .launcher:hover { transform: translateY(-1px); background: rgba(28,32,40,.92); }
    .launcher.live { border-color: rgba(120,220,160,.55); color: #9df0c0; }
    .panel {
      position: absolute; right: 14px; bottom: 122px; width: 322px;
      background: rgba(12,14,18,.96); color: #e8ecf2; border: 1px solid rgba(255,255,255,.12);
      border-radius: 14px; box-shadow: 0 18px 60px rgba(0,0,0,.6);
      font: 13px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      backdrop-filter: blur(14px); overflow: hidden;
    }
    .panel[hidden] { display: none; }
    .head { display: flex; align-items: center; gap: 8px; padding: 12px 14px 10px; }
    .mark { width: 22px; height: 22px; border-radius: 6px; background: #fff; color: #0b0d10;
      font: 800 10px/22px -apple-system, sans-serif; text-align: center; letter-spacing: .02em; }
    .name { font-weight: 650; font-size: 13.5px; letter-spacing: .01em; }
    .spacer { flex: 1; }
    .dot { width: 7px; height: 7px; border-radius: 50%; background: #6b7280; }
    .dot.ok { background: #43d98b; box-shadow: 0 0 8px rgba(67,217,139,.6); }
    .dot.err { background: #f87171; }
    .x { background: none; border: 0; color: #8b94a3; font-size: 18px; cursor: pointer; padding: 0 2px; line-height: 1; }
    .x:hover { color: #fff; }
    .body { padding: 2px 14px 14px; }
    .title { color: #fff; font-weight: 600; font-size: 13px; margin: 2px 0 2px;
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .status { color: #9aa4b2; font-size: 12px; min-height: 17px; margin-bottom: 10px; }
    .status.err { color: #fca5a5; }
    .row { display: flex; align-items: center; gap: 8px; margin: 8px 0; }
    label { color: #9aa4b2; font-size: 12px; }
    select {
      flex: 1; background: #1a1e25; color: #e8ecf2; border: 1px solid rgba(255,255,255,.12);
      border-radius: 8px; padding: 6px 8px; font: 12px -apple-system, sans-serif; outline: none;
    }
    .check { display: flex; align-items: center; gap: 7px; color: #cbd3df; font-size: 12px; cursor: pointer; }
    .check input { accent-color: #43d98b; }
    .go {
      width: 100%; margin-top: 10px; padding: 9px 10px; border-radius: 9px; border: 0;
      background: #e8ecf2; color: #0b0d10; font: 650 12.5px -apple-system, sans-serif;
      cursor: pointer; letter-spacing: .01em;
    }
    .go:hover { background: #fff; }
    .go:disabled { opacity: .5; cursor: default; }
    .bar { height: 3px; border-radius: 2px; background: rgba(255,255,255,.08); overflow: hidden; margin: 10px 0 2px; }
    .bar > i { display: block; height: 100%; width: 0; background: #43d98b; transition: width .4s ease; }
    .foot { display: flex; gap: 6px; align-items: center; margin-top: 10px; flex-wrap: wrap; }
    .mini {
      background: #171b21; color: #cbd3df; border: 1px solid rgba(255,255,255,.1);
      border-radius: 7px; padding: 4px 8px; font: 11px -apple-system, sans-serif; cursor: pointer;
    }
    .mini:hover { background: #1f242c; }
    .mini.on { border-color: rgba(67,217,139,.5); color: #9df0c0; }
    .meta { color: #6b7280; font-size: 11px; margin-top: 8px; }
    a { color: #9fb4d0; }
  `;

  function el(tag, cls) { const n = document.createElement(tag); if (cls) n.className = cls; return n; }

  function buildUI() {
    if (S.host) return;
    const host = el('div');
    host.setAttribute('data-allsubs-ui', '1');
    host.style.cssText = 'position:fixed;z-index:2147483647;pointer-events:none;';
    const root = host.attachShadow({ mode: 'open' });
    const style = el('style');
    style.textContent = CSS;

    const launch = el('button', 'launcher');
    launch.textContent = 'AS';
    launch.title = 'All Subs — AI captions (Alt+Shift+A)';
    launch.style.pointerEvents = 'auto';
    launch.addEventListener('click', function (e) { e.stopPropagation(); togglePanel(); });

    const panel = el('div', 'panel');
    panel.hidden = true;
    panel.style.pointerEvents = 'auto';
    panel.innerHTML = [
      '<div class="head"><div class="mark">AS</div><div class="name">All Subs</div>',
      '<div class="spacer"></div><div class="dot" data-el="dot" title="engine"></div>',
      '<button class="x" data-el="close" title="Close">×</button></div>',
      '<div class="body">',
      '<div class="title" data-el="title">No video selected</div>',
      '<div class="status" data-el="status">Ready.</div>',
      '<div class="row"><label>Captions in</label><select data-el="lang"></select></div>',
      '<div class="row"><label class="check"><input type="checkbox" data-el="deep"> Deep read (the model watches the whole film first)</label></div>',
      '<div class="row"><label class="check"><input type="checkbox" data-el="local"> Translate offline on this Mac (4B model, slower)</label></div>',
      '<button class="go" data-el="go">Caption this video</button>',
      '<div class="bar"><i data-el="bar"></i></div>',
      '<div class="foot">',
      '<button class="mini" data-el="bilingual">Bilingual</button>',
      '<button class="mini" data-el="minus">−0.3s</button>',
      '<button class="mini" data-el="plus">+0.3s</button>',
      '<button class="mini" data-el="reload">Re-sync</button>',
      '<button class="mini" data-el="settings">Settings</button>',
      '</div>',
      '<div class="meta" data-el="meta"></div>',
      '</div>'
    ].join('');

    root.appendChild(style);
    root.appendChild(launch);
    root.appendChild(panel);
    document.documentElement.appendChild(host);

    const q = function (name) { return root.querySelector('[data-el="' + name + '"]'); };
    const sel = q('lang');
    LANGS.forEach(function (pair) {
      const o = document.createElement('option');
      o.value = pair[0]; o.textContent = pair[1];
      sel.appendChild(o);
    });
    sel.addEventListener('change', function () {
      cfg.target = sel.value;
      saveCfg();
    });
    q('deep').addEventListener('change', function () { cfg.deep = this.checked; saveCfg(); });
    q('local').addEventListener('change', function () { cfg.local = this.checked; saveCfg(); });
    q('close').addEventListener('click', function () { togglePanel(false); });
    q('go').addEventListener('click', function () { startJob(); });
    q('bilingual').addEventListener('click', function () {
      cfg.bilingual = !cfg.bilingual; saveCfg(); paintConfig();
      if (S.overlay) S.overlay.setBilingual(cfg.bilingual);
    });
    q('minus').addEventListener('click', function () { adjustOffset(-0.3); });
    q('plus').addEventListener('click', function () { adjustOffset(0.3); });
    q('settings').addEventListener('click', function () {
      if (chrome.runtime.openOptionsPage) chrome.runtime.openOptionsPage();
    });
    q('reload').addEventListener('click', function () {
      if (S.job) { S.cues = []; S.version = -1; refresh(true); }
    });

    S.host = host; S.root = root; S.panel = panel; S.launch = launch;
    paintConfig();
    checkHealth();
  }

  function saveCfg() {
    try { chrome.storage.sync.set(cfg); } catch (e) { /* noop */ }
  }

  // All engine traffic goes through the background worker when running as an
  // extension: an HTTPS page cannot fetch http://127.0.0.1 directly.
  function api(path, opts) {
    opts = opts || {};
    return new Promise(function (resolve, reject) {
      let routed = false;
      try {
        if (chrome && chrome.runtime && chrome.runtime.sendMessage) {
          routed = true;
          chrome.runtime.sendMessage({
            type: 'allsubs:api', path: path,
            method: opts.method || 'GET', body: opts.body || null
          }, function (resp) {
            if (chrome.runtime.lastError) {
              return reject(new Error(chrome.runtime.lastError.message));
            }
            if (!resp) return reject(new Error('no response from engine proxy'));
            if (!resp.ok) return reject(new Error(resp.error || ('engine ' + resp.status)));
            resolve(resp.data);
          });
        }
      } catch (e) { routed = false; }
      if (routed) return;
      const init = { cache: 'no-store', method: opts.method || 'GET' };
      if (opts.body) {
        init.headers = { 'Content-Type': 'application/json' };
        init.body = JSON.stringify(opts.body);
      }
      fetch(cfg.backend + path, init).then(function (r) {
        if (!r.ok) throw new Error('engine ' + r.status);
        return r.json();
      }).then(resolve).catch(reject);
    });
  }

  function paintConfig() {
    if (!S.root) return;
    const sel = S.root.querySelector('[data-el="lang"]');
    if (sel && sel.value !== cfg.target) sel.value = cfg.target;
    const deep = S.root.querySelector('[data-el="deep"]');
    if (deep) deep.checked = !!cfg.deep;
    const local = S.root.querySelector('[data-el="local"]');
    if (local) local.checked = !!cfg.local;
    const bi = S.root.querySelector('[data-el="bilingual"]');
    if (bi) bi.classList.toggle('on', !!cfg.bilingual);
  }

  function adjustOffset(delta) {
    cfg.offset = Math.round(((cfg.offset || 0) + delta) * 10) / 10;
    if (S.overlay) S.overlay.setOffset(cfg.offset);
    setStatus('Delay ' + (cfg.offset > 0 ? '+' : '') + cfg.offset.toFixed(1) + 's');
  }

  function setStatus(text, isErr) {
    if (!S.root) return;
    const n = S.root.querySelector('[data-el="status"]');
    n.textContent = text;
    n.classList.toggle('err', !!isErr);
  }

  function setProgress(p) {
    if (!S.root) return;
    S.root.querySelector('[data-el="bar"]').style.width = Math.round(p * 100) + '%';
  }

  function setEngine(ok) {
    if (!S.root) return;
    const dot = S.root.querySelector('[data-el="dot"]');
    dot.classList.toggle('ok', !!ok);
    dot.classList.toggle('err', ok === false);
    dot.title = ok ? 'Local engine connected' : 'Local engine offline';
  }

  async function checkHealth() {
    try {
      const d = await api('/health');
      setEngine(!!d.ok);
      const localBox = S.root.querySelector('[data-el="local"]');
      if (localBox) {
        const tooSmall = d.ram_gb && d.ram_gb < 15;
        localBox.disabled = d.local === false || tooSmall;
        localBox.parentElement.title = d.local === false
          ? 'No local model — run ./allsubs local-model'
          : (tooSmall ? 'Offline mode needs 16 GB+ for GPU offload' : '');
      }
      if (!d.model) {
        setStatus('Speech model missing — run: cd ~/AllSubs && ./allsubs setup', true);
      } else if (d.deepseek_key === false) {
        setStatus('No translation key — open Settings to add one.', true);
      } else if (!S.job) {
        setStatus('Engine online — ready when you are.');
      }
      return !!d.ok;
    } catch (e) {
      setEngine(false);
      if (!S.job) setStatus('Local engine offline: cd ~/AllSubs && ./allsubs start', true);
      return false;
    }
  }

  function togglePanel(force) {
    buildUI();
    S.panelOpen = force === undefined ? !S.panelOpen : !!force;
    S.panel.hidden = !S.panelOpen;
    if (S.panelOpen) {
      const t = S.root.querySelector('[data-el="title"]');
      t.textContent = S.video ? (document.title || 'This page') : 'No video found';
      checkHealth();
      // warm the router while the user reads the panel: probe + library lookup
      if (S.video && S.video.duration) {
        api('/api/prefetch', {
          method: 'POST',
          body: { url: location.href, target: cfg.target,
                  duration: Math.round(S.video.duration) }
        }).catch(function () {});
      }
    }
  }

  // ------------------------------------------------------------ video finding

  function area(v) {
    const r = v.getBoundingClientRect();
    const style = getComputedStyle(v);
    if (style.display === 'none' || style.visibility === 'hidden' || r.width < 240) return 0;
    return r.width * r.height;
  }

  function pickVideo() {
    const vids = Array.prototype.slice.call(document.querySelectorAll('video'));
    const usable = vids.filter(function (v) { return v.readyState > 0 || v.currentSrc; });
    usable.sort(function (a, b) { return area(b) - area(a); });
    return usable[0] || null;
  }

  function attachVideo(v) {
    if (!v || v === S.video) return;
    S.video = v;
    if (S.overlay) S.overlay.destroy();
    S.overlay = window.AllSubsOverlay.mount(v);
    S.overlay.setBilingual(cfg.bilingual);
    S.overlay.setOffset(cfg.offset || 0);
    if (S.cues.length) S.overlay.setCues(S.cues);
  }

  function positionHost() {
    if (!S.host) return;
    const v = S.video;
    if (!v || !document.contains(v) || area(v) === 0) {
      S.host.style.display = 'none';
      return;
    }
    S.host.style.display = 'block';
    const r = v.getBoundingClientRect();
    S.host.style.left = r.left + 'px';
    S.host.style.top = r.top + 'px';
    S.host.style.width = r.width + 'px';
    S.host.style.height = r.height + 'px';
  }

  // ------------------------------------------------------------ job flow

  function mediaCandidate() {
    const v = S.video;
    const src = v && (v.currentSrc || v.src || '');
    if (src && /^https?:/i.test(src)) return src;
    try {
      const urls = performance.getEntriesByType('resource')
        .map(function (e) { return e.name; })
        .filter(function (u) { return /\.m3u8(\?|$)|\/manifest|\.mp4(\?|$)/i.test(u); });
      if (urls.length) return urls[urls.length - 1];
    } catch (e) { /* no resource timing */ }
    return null;
  }

  async function startJob() {
    if (S.busy) return;
    buildUI();
    if (!S.video) { setStatus('No video found on this page.', true); return; }
    const url = location.href;
    S.busy = true;
    S.root.querySelector('[data-el="go"]').disabled = true;
    setStatus('Talking to the local engine…');
    setProgress(0.02);
    try {
      const job = await api('/api/jobs', {
        method: 'POST',
        body: {
          url: url, target: cfg.target, mode: cfg.deep ? 'deep' : 'fast',
          translator: cfg.local ? 'local' : 'cloud',
          asr: cfg.cloudAsr ? 'cloud' : 'local',
          duration: Math.round((S.video && S.video.duration) || 0),
          media_url: mediaCandidate(),
          title: (document.title || '').slice(0, 200),
          cookies: /(^|\.)youtube\.com$|(^|\.)youtu\.be$/.test(location.hostname)
        }
      });
      S.job = job.id;
      S.cues = []; S.version = -1; S.pass2 = false;
      if (S.overlay) S.overlay.setCues([]);
      setStatus(job.created ? 'Starting…' : 'Resuming existing job…');
      if (S.launch) S.launch.classList.add('live');
      startPolling();
      togglePanel(false);   // get out of the way while watching
    } catch (e) {
      S.busy = false;
      setEngine(false);
      setStatus('Engine offline. Run: cd ~/AllSubs && ./allsubs start', true);
      S.root.querySelector('[data-el="go"]').disabled = false;
    }
  }

  function startPolling() {
    if (S.polling) clearInterval(S.polling);
    refresh(true);
    S.polling = setInterval(function () { refresh(false); }, 2500);
  }

  function stopPolling() {
    if (S.polling) clearInterval(S.polling);
    S.polling = null;
    S.busy = false;
    if (S.root) S.root.querySelector('[data-el="go"]').disabled = false;
  }

  async function refresh(force) {
    if (!S.job) return;
    try {
      const d = await api('/api/jobs/' + S.job);
      setEngine(true);
      if (S.overlay && d.source) {
        S.overlay.setBadge(d.source === 'native' ? 'official subs' : (d.source === 'wyzie' ? 'library subs' : (d.source === 'cloud' ? 'cloud subs' : 'AI subs')));
      }
      setStatus(d.stage + (d.error ? ' — ' + d.error : ''), d.status === 'error');
      setProgress(d.progress || 0);
      const meta = S.root.querySelector('[data-el="meta"]');
      if (meta) {
        meta.textContent = [
          d.title || '',
          d.lang ? 'heard: ' + d.lang : '',
          d.count ? d.count + ' cues' : '',
          d.pass2 ? 'whole-film pass done' : ''
        ].filter(Boolean).join(' · ');
        if (d.count && S.job) {
          const a = document.createElement('a');
          a.href = cfg.backend + '/api/jobs/' + S.job + '.vtt';
          a.textContent = ' download .vtt';
          a.target = '_blank';
          meta.appendChild(a);
        }
      }
      await pullCues(d, force);
      if (d.status === 'done' || d.status === 'error') stopPolling();
      if (d.status === 'done' && S.launch) S.launch.classList.add('live');
    } catch (e) {
      setEngine(false);
      setStatus('Lost the local engine — is it still running?', true);
      stopPolling();
    }
  }

  async function pullCues(status, force) {
    if (!status.count) return;
    const needFull = force || status.pass2 !== S.pass2 || status.count < S.cues.length;
    let from = needFull ? 0 : S.cues.length;
    let guard = 0;
    const collected = needFull ? [] : S.cues.slice();
    while (guard++ < 40) {
      let d;
      try {
        d = await api('/api/jobs/' + S.job + '/cues?from=' + from);
      } catch (e) { break; }
      Array.prototype.push.apply(collected, d.cues || []);
      if (!d.cues || !d.cues.length) break;
      if (d.next >= d.total) break;
      from = d.next;
    }
    S.cues = collected;
    S.pass2 = !!status.pass2;
    S.total = collected.length;
    if (S.overlay) S.overlay.setCues(collected);
  }

  // ------------------------------------------------------------ boot

  function boot() {
    const v = pickVideo();
    if (v) {
      attachVideo(v);
      buildUI();
    }
    setInterval(function () {
      const next = pickVideo();
      if (next && next !== S.video) {
        attachVideo(next);
        if (S.cues.length && S.overlay) S.overlay.setCues(S.cues);
      }
      if (next) buildUI();
      positionHost();
    }, 1200);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  try {
    chrome.runtime.onMessage.addListener(function (msg) {
      if (msg && msg.type === 'allsubs:toggle') togglePanel();
      if (msg && msg.type === 'allsubs:open') togglePanel(true);
      return false;
    });
  } catch (e) { /* test page */ }

  // exposed for the local test harness
  window.__allSubs = { state: S, startJob: startJob, togglePanel: togglePanel, refresh: refresh };
})();
