/* All Subs — subtitle overlay renderer (shadow DOM, zero idle CPU, no site CSS leakage). */
(function () {
  if (window.__allSubsOverlay) return;

  const STYLE = `
    :host { all: initial; }
    .wrap {
      position: absolute; inset: 0; display: flex; align-items: flex-end;
      justify-content: center; pointer-events: none;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      transition: opacity .16s ease;
    }
    .stack { width: min(92%, 1100px); margin-bottom: 7.5%; text-align: center; }
    .src, .dst {
      display: inline-block; max-width: 100%; padding: .18em .5em;
      border-radius: .35em; line-height: 1.3; letter-spacing: .01em;
      background: rgba(8, 10, 14, .74); color: #fff;
      text-shadow: 0 1px 2px rgba(0,0,0,.9);
      box-decoration-break: clone; -webkit-box-decoration-break: clone;
      white-space: pre-wrap;
    }
    .src { font-size: .72em; color: #ffd479; background: rgba(8,10,14,.58); margin-bottom: .25em; }
    .dst { font-size: 1em; font-weight: 500; }
    .hidden { opacity: 0; }
    .badge {
      position: absolute; top: .6em; right: .6em; font-size: 10px; letter-spacing: .08em;
      text-transform: uppercase; color: #9aa4b2; background: rgba(8,10,14,.62);
      padding: 2px 6px; border-radius: 4px;
    }
  `;

  function el(tag, cls) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    return n;
  }

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

  function mount(video) {
    const host = el('div');
    host.setAttribute('data-allsubs-overlay', '1');
    host.style.cssText = 'position:fixed;left:0;top:0;width:0;height:0;z-index:2147483646;pointer-events:none;';
    const root = host.attachShadow({ mode: 'open' });
    const style = el('style');
    style.textContent = STYLE;
    const wrap = el('div', 'wrap hidden');
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
    let lastKey = '', visible = false, hasSrc = false;
    let raf = 0, vfc = 0, layoutRaf = 0, destroyed = false;
    const geom = { l: -1, t: -1, w: -1, h: -1, size: -1 };
    const useVfc = typeof video.requestVideoFrameCallback === 'function';

    function attachHost() {
      if (destroyed) return;
      const fs = document.fullscreenElement;
      if (fs && fs !== document.body && fs.tagName !== 'VIDEO') {
        if (host.parentNode !== fs) fs.appendChild(host);
      } else if (document.body && host.parentNode !== document.body) {
        document.body.appendChild(host);
      }
    }

    function syncLayout() {
      layoutRaf = 0;
      if (destroyed || !video) return;
      attachHost();
      const r = video.getBoundingClientRect();
      const l = Math.round(r.left), t = Math.round(r.top);
      const w = Math.round(r.width), h = Math.round(r.height);
      if (l !== geom.l || t !== geom.t || w !== geom.w || h !== geom.h) {
        geom.l = l; geom.t = t; geom.w = w; geom.h = h;
        host.style.left = l + 'px';
        host.style.top = t + 'px';
        host.style.width = w + 'px';
        host.style.height = h + 'px';
        const px = Math.max(15, Math.min(46, Math.round(w * 0.027)));
        if (px !== geom.size) {
          geom.size = px;
          dstLine.style.fontSize = px + 'px';
          srcLine.style.fontSize = Math.max(12, Math.round(px * 0.72)) + 'px';
        }
      }
    }

    function scheduleLayout() {
      if (destroyed || layoutRaf) return;
      layoutRaf = requestAnimationFrame(syncLayout);
    }

    function hideLines() {
      if (!visible) return;
      visible = false;
      wrap.classList.add('hidden');
      srcLine.classList.add('hidden');
      dstLine.classList.add('hidden');
    }

    function paintAtCurrentTime() {
      if (destroyed || !enabled || !cues.length || !video) {
        hideLines();
        return;
      }
      const t = video.currentTime - offset;
      const cue = findCue(cues, t);
      if (!cue) {
        hideLines();
        return;
      }
      const key = cue.i + '|' + (cue.t || '') + '|' + bilingual;
      if (key !== lastKey) {
        lastKey = key;
        const target = (cue.t || '').trim();
        const source = (cue.x || '').trim();
        const primary = target || source;
        dstLine.textContent = primary;
        hasSrc = !!(bilingual && target && source && target !== source);
        srcLine.textContent = hasSrc ? source : '';
        srcLine.classList.toggle('hidden', !hasSrc);
        dstLine.classList.toggle('hidden', !primary);
      }
      if (!visible) {
        visible = true;
        wrap.classList.remove('hidden');
        dstLine.classList.remove('hidden');
        if (hasSrc) srcLine.classList.remove('hidden');
      }
    }

    function stopPlaybackLoop() {
      if (raf) { cancelAnimationFrame(raf); raf = 0; }
      if (vfc && useVfc && typeof video.cancelVideoFrameCallback === 'function') {
        video.cancelVideoFrameCallback(vfc);
        vfc = 0;
      }
    }

    function tick() {
      raf = 0;
      vfc = 0;
      if (destroyed || !enabled || !cues.length || video.paused || video.ended) return;
      paintAtCurrentTime();
      scheduleTick();
    }

    function scheduleTick() {
      if (destroyed || !enabled || !cues.length || video.paused || video.ended) return;
      if (useVfc) {
        if (!vfc) vfc = video.requestVideoFrameCallback(tick);
      } else if (!raf) {
        raf = requestAnimationFrame(tick);
      }
    }

    function onPlay() { syncLayout(); paintAtCurrentTime(); scheduleTick(); }
    function onPause() { stopPlaybackLoop(); paintAtCurrentTime(); }
    function onSeekOrTime() { paintAtCurrentTime(); }
    function onFullscreen() { attachHost(); scheduleLayout(); }

    video.addEventListener('play', onPlay);
    video.addEventListener('playing', onPlay);
    video.addEventListener('pause', onPause);
    video.addEventListener('ended', onPause);
    video.addEventListener('seeked', onSeekOrTime);
    video.addEventListener('timeupdate', onSeekOrTime);
    document.addEventListener('fullscreenchange', onFullscreen);
    window.addEventListener('resize', scheduleLayout, { passive: true });
    window.addEventListener('scroll', scheduleLayout, { passive: true, capture: true });

    let ro = null;
    if (typeof ResizeObserver === 'function') {
      ro = new ResizeObserver(scheduleLayout);
      ro.observe(video);
    }

    attachHost();
    syncLayout();

    return {
      setCues(next) {
        cues = (next || []).slice().sort((a, b) => a.s - b.s);
        lastKey = '';
        syncLayout();
        paintAtCurrentTime();
        if (cues.length && !video.paused && !video.ended) scheduleTick();
        else stopPlaybackLoop();
      },
      setOffset(s) {
        offset = s;
        paintAtCurrentTime();
      },
      setBilingual(on) {
        bilingual = !!on;
        lastKey = '';
        paintAtCurrentTime();
      },
      setEnabled(on) {
        enabled = !!on;
        if (!enabled) {
          stopPlaybackLoop();
          hideLines();
        } else {
          paintAtCurrentTime();
          scheduleTick();
        }
      },
      setBadge(text) {
        if (!text) { badge.style.display = 'none'; return; }
        badge.textContent = text;
        badge.style.display = 'block';
        scheduleLayout();
      },
      destroy() {
        destroyed = true;
        stopPlaybackLoop();
        if (layoutRaf) { cancelAnimationFrame(layoutRaf); layoutRaf = 0; }
        if (ro) ro.disconnect();
        video.removeEventListener('play', onPlay);
        video.removeEventListener('playing', onPlay);
        video.removeEventListener('pause', onPause);
        video.removeEventListener('ended', onPause);
        video.removeEventListener('seeked', onSeekOrTime);
        video.removeEventListener('timeupdate', onSeekOrTime);
        document.removeEventListener('fullscreenchange', onFullscreen);
        window.removeEventListener('resize', scheduleLayout, { passive: true });
        window.removeEventListener('scroll', scheduleLayout, { passive: true, capture: true });
        host.remove();
      }
    };
  }

  window.__allSubsOverlay = true;
  window.AllSubsOverlay = { mount: mount };
})();
