/* All Subs — subtitle overlay renderer (shadow DOM, no site CSS leakage). */
(function () {
  if (window.__allSubsOverlay) return;

  const STYLE = `
    :host { all: initial; }
    .wrap {
      position: absolute; inset: 0; display: flex; align-items: flex-end;
      justify-content: center; pointer-events: none;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      transition: opacity .18s ease;
    }
    .stack { width: min(92%, 1100px); margin-bottom: 7.5%; text-align: center; }
    .src, .dst {
      display: inline-block; max-width: 100%; padding: .18em .5em;
      border-radius: .35em; line-height: 1.3; letter-spacing: .01em;
      background: rgba(8, 10, 14, .72); color: #fff;
      text-shadow: 0 1px 2px rgba(0,0,0,.9);
      box-decoration-break: clone; -webkit-box-decoration-break: clone;
      white-space: pre-wrap;
    }
    .src { font-size: .72em; color: #ffd479; background: rgba(8,10,14,.55); margin-bottom: .25em; }
    .dst { font-size: 1em; font-weight: 500; }
    .hidden { opacity: 0; }
    .badge {
      position: absolute; top: .6em; right: .6em; font-size: 10px; letter-spacing: .08em;
      text-transform: uppercase; color: #9aa4b2; background: rgba(8,10,14,.6);
      padding: 2px 6px; border-radius: 4px;
    }
  `;

  function el(tag, cls) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    return n;
  }

  function toSeconds(cue) { return cue.s; }

  function findCue(cues, t) {
    let lo = 0, hi = cues.length - 1, best = -1;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (cues[mid].s <= t) { best = mid; lo = mid + 1; } else { hi = mid - 1; }
    }
    if (best < 0) return null;
    const c = cues[best];
    return t < c.e ? c : null;
  }

  function mount(video, opts) {
    opts = opts || {};
    const host = el('div');
    host.setAttribute('data-allsubs-overlay', '1');
    host.style.cssText = 'position:fixed;left:0;top:0;width:0;height:0;z-index:2147483646;pointer-events:none;';
    const root = host.attachShadow({ mode: 'open' });
    const style = el('style');
    style.textContent = STYLE;
    const wrap = el('div', 'wrap');
    const stack = el('div', 'stack');
    const srcLine = el('div', 'src hidden');
    const dstLine = el('div', 'dst hidden');
    const badge = el('div', 'badge');
    badge.style.display = 'none';
    stack.appendChild(srcLine);
    stack.appendChild(dstLine);
    wrap.appendChild(stack);
    root.appendChild(style);
    root.appendChild(wrap);
    root.appendChild(badge);

    let cues = [], offset = 0, bilingual = true, enabled = true;
    let lastKey = '', visible = false, raf = 0;
    const state = { size: null };

    function attachHost() {
      const fs = document.fullscreenElement;
      if (fs && fs !== document.body && fs.tagName !== 'VIDEO') {
        if (host.parentNode !== fs) fs.appendChild(host);
      } else if (host.parentNode !== document.body) {
        document.body.appendChild(host);
      }
    }

    function layout() {
      attachHost();
      const r = video.getBoundingClientRect();
      host.style.left = r.left + 'px';
      host.style.top = r.top + 'px';
      host.style.width = r.width + 'px';
      host.style.height = r.height + 'px';
      const px = Math.max(15, Math.min(46, Math.round(r.width * 0.027)));
      if (px !== state.size) {
        state.size = px;
        dstLine.style.fontSize = px + 'px';
        srcLine.style.fontSize = px + 'px';
      }
    }

    function render() {
      layout();
      raf = requestAnimationFrame(render);
      if (!enabled || !cues.length || !video) return;
      const t = video.currentTime + offset;
      const cue = findCue(cues, t);
      if (!cue) {
        if (visible) {
          visible = false;
          wrap.classList.add('hidden');
          srcLine.classList.add('hidden');
          dstLine.classList.add('hidden');
        }
        return;
      }
      const key = cue.i + '|' + (cue.t || '') + '|' + bilingual;
      if (key !== lastKey) {
        lastKey = key;
        const target = (cue.t || '').trim();
        const source = (cue.x || '').trim();
        dstLine.textContent = target || source;
        const showSrc = bilingual && target && source && target !== source;
        srcLine.textContent = showSrc ? source : '';
        srcLine.classList.toggle('hidden', !showSrc);
        dstLine.classList.toggle('hidden', !(target || source));
      }
      if (!visible) {
        visible = true;
        wrap.classList.remove('hidden');
        dstLine.classList.remove('hidden');
      }
    }

    document.addEventListener('fullscreenchange', attachHost);
    attachHost();
    raf = requestAnimationFrame(render);

    return {
      setCues(next) { cues = (next || []).slice().sort((a, b) => a.s - b.s); lastKey = ''; },
      setOffset(s) { offset = s; },
      setBilingual(on) {
        bilingual = !!on;
        lastKey = '';
      },
      setEnabled(on) {
        enabled = !!on;
        if (!enabled) { wrap.classList.add('hidden'); }
      },
      setBadge(text) {
        if (!text) { badge.style.display = 'none'; return; }
        badge.textContent = text;
        badge.style.display = 'block';
      },
      destroy() {
        cancelAnimationFrame(raf);
        document.removeEventListener('fullscreenchange', attachHost);
        host.remove();
      }
    };
  }

  window.__allSubsOverlay = true;
  window.AllSubsOverlay = { mount: mount };
})();
