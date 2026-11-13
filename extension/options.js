const $ = function (id) { return document.getElementById(id); };
const DEFAULTS = {
  backend: 'http://127.0.0.1:8765',
  target: 'en',
  bilingual: true,
  deep: false,
  local: false
};

let cfg = Object.assign({}, DEFAULTS);

function setDot(key, state) {
  const dot = document.querySelector('.dot[data-k="' + key + '"]');
  if (!dot) return;
  dot.classList.toggle('ok', state === true);
  dot.classList.toggle('err', state === false);
}

function showStatus(text, kind) {
  const el = $('status');
  el.textContent = text || '';
  el.className = 'status' + (kind ? ' ' + kind : '');
}

async function loadState() {
  const base = ($('backend').value || cfg.backend).replace(/\/$/, '');
  setDot('engine', null);
  try {
    const res = await fetch(base + '/api/config', { cache: 'no-store' });
    const d = await res.json();
    setDot('engine', true);
    setDot('whisper', !!d.whisper);
    setDot('model', !!d.model);
    setDot('ytdlp', !!d.ytdlp);
    setDot('deepseek_key', !!d.deepseek_key);
    setDot('wyzie_key', !!d.wyzie_key);
    const missing = [];
    if (!d.model) missing.push('speech model (run ./allsubs setup)');
    if (!d.deepseek_key) missing.push('DeepSeek key');
    showStatus(missing.length ? 'Needs: ' + missing.join(', ') : 'Engine ready.',
               missing.length ? 'err' : 'ok');
    const localBox = $('local');
    const tooSmall = d.ram_gb && d.ram_gb < 15;
    localBox.disabled = !!tooSmall;
    localBox.parentElement.title = tooSmall
      ? 'Offline translation needs 16 GB+ for GPU offload' : '';
    return d;
  } catch (e) {
    ['whisper', 'model', 'ytdlp', 'deepseek_key', 'wyzie_key'].forEach(function (k) { setDot(k, null); });
    setDot('engine', false);
    showStatus('Engine not running — start it with ./allsubs start', 'err');
    return null;
  }
}

function fill() {
  $('backend').value = cfg.backend;
  $('target').value = cfg.target;
  $('bilingual').checked = !!cfg.bilingual;
  $('deep').checked = !!cfg.deep;
  $('local').checked = !!cfg.local;
}

function collectPrefs() {
  return {
    backend: ($('backend').value || DEFAULTS.backend).replace(/\/$/, ''),
    target: $('target').value,
    bilingual: $('bilingual').checked,
    deep: $('deep').checked,
    local: $('local').checked
  };
}

$('save').addEventListener('click', async function () {
  cfg = collectPrefs();
  chrome.storage.sync.set(cfg);
  const body = {};
  const dk = $('deepseek').value.trim();
  const wz = $('wyzie').value.trim();
  if (dk) body.deepseek_api_key = dk;
  if (wz) body.wyzie_api_key = wz;
  if (Object.keys(body).length) {
    try {
      const res = await fetch(cfg.backend + '/api/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      const d = await res.json();
      $('deepseek').value = '';
      $('wyzie').value = '';
      $('saved').textContent = d.saved && d.saved.length
        ? 'Saved: ' + d.saved.join(', ').replace(/_/g, ' ')
        : 'Settings saved.';
      $('saved').className = 'status ok';
    } catch (e) {
      $('saved').textContent = 'Preferences saved, but the engine did not accept the key (offline?).';
      $('saved').className = 'status err';
    }
  } else {
    $('saved').textContent = 'Settings saved.';
    $('saved').className = 'status ok';
  }
  loadState();
});

$('test').addEventListener('click', loadState);
$('close').addEventListener('click', function () { window.close(); });

chrome.storage.sync.get(DEFAULTS, function (v) {
  cfg = Object.assign(cfg, v);
  fill();
  loadState();
});
