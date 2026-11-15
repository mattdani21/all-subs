# All Subs — production-readiness and direction review

You are reviewing a real, working open-source project. The full relevant code is included below; do not use any tools or fetch anything — answer only from this text. Be concrete and
critical; praise is not useful.

## What it is

A Chrome MV3 extension plus a local Python engine. It puts captions on any video: it first
looks for an existing subtitle track, and only when nothing usable exists does it
transcribe the audio with whisper.cpp and translate it with an LLM.

- Extension: `extension/` — content.js (finds `<video>`, panel, polling), overlay.js
  (shadow-DOM renderer), background.js (proxies API calls), options page.
- Engine: `engine/` — server.py (stdlib ThreadingHTTPServer on 127.0.0.1:8765, job runner),
  captions.py (probe, native subtitle pick, whisper, translation, timing), providers.py
  (Wikidata → IMDb → Wyzie subtitle library + duration gate), cloud_asr.py, local_llm.py.
- CLI: `./allsubs setup|doctor|start|stop|package|handoff`.

## Intent

- Started as a personal tool: a Chinese film on bilibili.tv had no subtitle track.
- Now open-sourced deliberately for reputation (LinkedIn/X post), **not revenue**. The owner
  expects no money from it.
- Target user: someone watching a foreign film that has no subtitles in a language they read.

## Measured state (MacBook Air M3, 8 GB RAM)

- **Rung 1 — retrieve:** existing track via Wikidata → IMDb → Wyzie, gated on runtime
  coverage. 1,072 cues in ~8 s on a 116-minute film. [E]
- **Rung 2 — cloud:** one multimodal call per 60 s audio chunk, translated cues back.
  4.9 s per chunk, ~$0.30 per film. [E]
- **Rung 3 — local ASR:** whisper.cpp large-v3-turbo, 24 chunks, then DeepSeek translates
  cue text. 11–17 min for a 116-minute film; ASR is 94–97% of wall time. [E]
- **Rung 4 — fully local:** whisper + Qwen3-4B via llama.cpp. 9.4 tok/s, visible translation
  quality loss; the 8B model will not load in 8 GB. Offline mode only, gated at 16 GB. [E]
- Translation: deepseek-flash with thinking disabled, 1.7 s per batch, ~80 s per film;
  whole-film "deep pass" 17 s across 6 parallel batches. [E]
- New timing work: onset snapping for ASR cues; a speech-rate gate that drops whisper's
  captions of music (a 30 s segment with 12 characters is not speech); "Check sync" which
  samples three 30 s windows, matches recognised lines to cue text, and shifts a
  same-language track only when it is genuinely out (13 s, 22 matched lines on test). [E]

## Known weaknesses (owner's own list — do not just rediscover these)

1. **Install is terminal-heavy:** Homebrew, a 1.6 GB whisper model, Python, Developer Mode,
   "load unpacked". Fine for the author, fatal for a stranger.
2. **One film validated end-to-end.** A handful of sites tried. No Windows or Linux testing.
3. **No automated end-to-end suite.** Unit tests plus a Playwright harness that loads the
   extension against a local player.
4. **Timing.** Subtitles can lead speech; library tracks come from other releases; music
   gets captioned (partially fixed this week).
5. **Secrets.** Keys stored in `~/.allsubs/config.json` at 0600 and in `.env`; one key was
   pasted into a chat during development.
6. **Legal/ToS.** yt-dlp against streaming sites. DRM (Netflix, Prime) explicitly out of
   scope. The README avoids naming piracy hosts.
7. **Performance.** ASR dominates; local speedups are capped at ~2× on 8 GB.
8. **UX.** Small panel, no onboarding wizard, no cross-tab progress, no Chrome Web Store
   presence.

## The decision the owner faces

The code works but is not "production ready" for strangers. He wants to know what to do
next, with reputation as the success metric (stars, shares, credibility), not revenue.

## Questions, ranked

1. **Top five changes** to get a stranger from "interesting repo" to "it worked on my
   machine", ranked by quality gained per hour of work. Be specific about what to build.
2. **Distribution:** unpacked extension + local engine (today), a signed/notarised Mac app,
   a hosted service, or Chrome Web Store with a native-messaging host. Which maximises
   credibility and adoption for an open-source project with no revenue goal — and what does
   each cost in effort and risk?
3. **Architecture:** is the localhost HTTP engine the right shape, or should inference move
   into the extension (WASM/WebGPU) or into a native host? What breaks first at scale?
4. **What would a critical reviewer attack first?** Give the three strongest objections and
   the cheapest honest way to pre-empt each.
5. **Pipeline shape:** whisper ASR → LLM translation is two stages. Would an end-to-end
   speech-translation model be materially better, and where (quality, latency, cost)?
6. **What should be cut?** Which current features are not worth maintaining.

## Evidence rules

Mark every factual claim you make about the project as [E] (seen in the code or README),
[A] (assumption), or [D] (derived). Do not invent metrics. If something is unclear from the
repo, say so instead of guessing.

## Deliverable

A critique memo:

1. Verdict in the first paragraph — is this worth polishing, and toward what?
2. Ranked recommendations with rough effort (hours/days) and what each unlocks.
3. A short "where the owner's assumptions are wrong" section.
4. The three objections a hostile reviewer would lead with.


## README excerpt
# All Subs

**AI captions for any video.** It looks for existing subtitles first — usually in
seconds — and only when nothing usable exists does it transcribe the audio locally with
whisper.cpp and translate it with an LLM.

![All Subs rendering a library subtitle track over Shadow (2018)](docs/hero.png)

Built because a Chinese film on bilibili.tv had no subtitle track and I wanted to watch
it that night.

## It's a router

Every request walks four rungs, cheapest first, and only falls through when the rung
above fails its gate:

| rung | what happens | measured |
|---|---|---|
| **1. retrieve** | existing track via Wikidata → IMDb → Wyzie | **~8 s**, 1,072 cues |
| **2. cloud** | audio chunk → one multimodal call → translated cues | 4.9 s per 60 s clip, ~$0.30/film |
| **3. local ASR** | whisper.cpp + DeepSeek on the cue text | 11–17 min for 116 min |
| **4. fully local** | whisper.cpp + Qwen3-4B, nothing leaves the machine | fine on 16 GB+, slow on 8 GB |

The gates are the product: a retrieved track must span the film (my first one ran 22
minutes past the credits), cloud needs credit and tolerable timestamps, local ASR needs a
translation key, fully-local needs RAM. The overlay badge tells you which rung answered —
*library subs*, *cloud subs*, *AI subs*, or *official*.

## How it works

```
Chrome extension  ──►  local engine (127.0.0.1:8765)
  finds <video>          1. probe: title, duration, subtitle inventory
  draws overlay          2. library lookup: title+year → IMDb → Wyzie → sync gate
  polls cues             3. nothing usable → download audio → 16 kHz mono → whisper.cpp
                         4. chunked ASR (60s/120s/300s) → cues stream as they land
                         5. LLM translates while the next chunk transcribes
                         6. optional deep pass: whole transcript → synopsis + glossary
                            → every cue re-translated with that context
```

![pipeline](docs/allsubs-pipeline.png)

Everything heavy runs on your machine; only cue text goes to the translation API. Jobs are
cached by URL + language, so a second viewing is instant.

## Quick start (macOS)

```bash
git clone https://github.com/mattdani21/all-subs.git
cd all-subs
./allsubs setup     # ffmpeg, whisper-cpp, yt-dlp + the 1.5 GB speech model
./allsubs start     # engine on 127.0.0.1:8765
```

Chrome → `chrome://extensions` → Developer mode → **Load unpacked** → `extension/`.
Open a video and hit **AS** (or `Alt+Shift+A`).

Add keys in the extension's **Settings** page, or drop them in `~/AllSubs/.env`:

- `DEEPSEEK_API_KEY` — translation (required for the generate path)
- `WYZIE_API_KEY` — subtitle library (optional, free at store.wyzie.io/redeem, 1,000/day)

`./allsubs doctor` reports exactly what is missing.

## Speed, measured

116-minute film on an M3 (8 GB):

| what | time |
|---|---|
| library track, after the panel warms | **0.01 s** |
| library track, cold | ~8 s |
| first caption, opening has dialogue | ~20 s |
| first caption, opening is music/rain | ~80 s |
| full ASR + translation | 11–17 min |
| repeat view | instant (cached) |

The panel starts resolving the title, checking libraries and fetching the opening two
minutes as soon as it opens, so by the time you press *Caption this video* most of the
latency is already spent. Chunks are 30 s / 90 s / 180 s / 300 s, so the first lines land
long before the film is finished.

ASR is the floor: whisper large-v3-turbo runs ~7–13× realtime and accounts for 94–97% of
wall time. Greedy decoding, quantised models, flash attention and parallel chunks were all
measured — none move it much. The only real win is not transcribing, which is why the
library path exists.

## Sites

- **YouTube** — native and auto captions are read directly, no audio download, ~2 s.
  Videos with no track fall through to the normal generate path.
- **Plain MP4 / HLS players** — the extension sniffs the media URL from the page
  (`video.currentSrc` plus resource-timing entries ending in `.m3u8` / `.mp4`) and the
  engine pulls that stream directly with yt-dlp. Content scripts run in all frames, so
  players inside a same-site iframe work too. This is the generic path most streaming
  mirrors use.
- **YouTube without captions** falls back to yt-dlp, which YouTube often refuses. Reading
  Chrome's cookies (`--cookies-from-browser`) can fix that but triggers a macOS keychain
  prompt, so it is opt-in: start the engine with `ALLSUBS_YOUTUBE_COOKIES=1`.
- **DRM** (Netflix, Prime Video, Disney+) — not supported. The stream is encrypted, so
  there is nothing to transcribe.
- Mirror sites rotate domains constantly; support is per-stream, not per-domain, which is
  why it works without a site adapter.

## What it is not

- Not a hosted service. There is no server; the engine runs on your Mac.
- Not DRM-capable. It captions video you can already fetch, not Netflix.
- Not silent about failure: the panel distinguishes engine offline, missing model,
  missing key, and rejected s

## engine/server.py routing
    # 1. existing, safe captions win
    native = captions.pick_native_subs(meta, job.target)
    if native:
        code, _kind = native
        job.set(status="fetching", stage="Found %s subtitles" % code, progress=0.3)
        workdir = os.path.join(captions.JOBS_DIR, job.id + "_work")
        os.makedirs(workdir, exist_ok=True)
        text = captions.download_native_subs(job.url, code, os.path.join(workdir, "sub"))
        cues = captions.parse_vtt(text) if text.lstrip().startswith("WEBVTT") else captions.parse_srt(text)
        cues = captions.split_display([dict(c) for c in cues])
        if code.lower().startswith(job.target.lower()):
            for c in cues:
                c["dst"] = c["src"]
        else:
            # found a usable track, but not in the viewer's language: translate it
            translated = captions.translate_cues(cues, job.target, {"title": job.title})
            for c in cues:
                c["dst"] = translated.get(c["i"], c["src"])
        job.add_cues(cues)
        job.set(status="done", stage="Captions ready (%s)" % code, progress=1.0,
                source="native", lang=code)
        job.to_disk()
        _cache(job)
        return

    # 2. search public subtitle libraries before doing any ASR
    if (job.duration_hint and job.duration_hint > 300 and not job.skip_library
            and job.translator != "local"):
        job.set(status="searching", stage="Searching subtitle libraries", progress=0.08)
        try:
            found = providers.find(job.title, job.duration_hint, job.target)
        except Exception as exc:
            found = None
            log("job %s: provider error: %s" % (job.id, exc))
        if found and found.get("rejected"):
            log("job %s: provider rejected track %s (%s)" % (
                job.id, found.get("imdb"), found.get("note")))
        elif found:
            cues = found["cues"]
            if job.target and (found.get("lang") or "").startswith(job.target):
                for c in cues:
                    c["dst"] = c["src"]
            else:
                translated = captions.translate_cues(
                    cues, job.target, {"title": job.title})
                for c in cues:
                    c["dst"] = translated.get(c["i"], c["src"])
            job.add_cues(cues)
            job.set(status="done", stage="Captions ready (library)", progress=1.0,
                    source="wyzie", lang=found.get("lang"), duration=job.duration_hint)
            job.to_disk()
            _cache(job)
            log("job %s: used library track %s (%s)" % (
                job.id, found.get("imdb"), found.get("note")))
            return

    # 3. no usable track -> transcribe, starting with the opening minutes
    job.set(status="audio", stage="Fetching audio", progress=0.05)
    workdir = os.path.join(captions.JOBS_DIR, job.id + "_work")
    os.makedirs(workdir, exist_ok=True)

    full = {}

    def fetch_full():
        try:
            full["path"] = captions.download_audio(
                job.media_url or job.url, workdir, job.id, cookies=job.cookies)
        except Exception as exc:  # reported after the opening is captioned
            full["error"] = exc

    dl = threading.Thread(target=fetch_full, daemon=True)
    dl.start()

    prefix = None
    if job.asr != "cloud":
        try:
            prefix = captions.download_audio_range(
                job.media_url or job.url, workdir, 120, cookies=job.cookies)
        except Exception as exc:
            log("job %s: section fetch failed (%s); using the full download" % (job.id, exc))

    if prefix:
        total = float(job.duration_hint or 0) or 120.0
        if job.limit:
            total = min(total, float(job.limit))
        code, conf = captions.detect_language(prefix, min(total, 120.0),
                                              window_span=min(total, 120.0))
        if not code or conf < 0.85:
            log("job %s: opening language uncertain (%s p=%.2f); waiting for full audio" % (
                job.id, code, conf))
            prefix = None
    if prefix:
        lang = code
        chunks = captions.split_wav(prefix, workdir, limit=job.limit, schedule=[30, 90])
        job.set(lang=lang, duration=total, status="asr",
                stage="Transcribing the opening", progress=0.1, source="asr")
        log("job %s: opening ready (%ss), language %s" % (
            job.id, chunks[0][2] if chunks else 0, lang))
    else:
        dl.join()
        audio = full.get("path")
        if not audio:
            raise RuntimeError("audio download failed: %s" % full.get("error"))
        total = captions.duration_of(audio)
        if job.limit:
            total = min(total, float(job.limit))
        lang, _conf = captions.detect_language(audio, total)
        lang = lang or "auto"
        chunks = captions.split_wav(audio, workdir, limit=job.limit,
                                    schedule=[30, 90, 180, 300])
        job.set(lang=lang, duration=total, status="asr",
                stage="Transcribing 0/%d" % len(chunks), progress=0.1, source="asr")
        log("job %s: %d chunks, %.0fs audio" % (job.id, len(chunks), total))

    if job.asr == "cloud" and cloud_asr.available():
        try:
            _cloud_pass(job, chunks, lang)
            job.set(status="done", stage="Captions ready (cloud)", progress=1.0,
                    source="cloud")
            job.to_disk()

## captions.filter_segments
def filter_segments(segs, silences, lang=None):
    """Drop ASR hallucinations: silence-backed, artifact, repeated and looping output."""
    if not segs:
        return []
    counts = {}
    for seg in segs:
        counts[_norm(seg["src"])] = counts.get(_norm(seg["src"]), 0) + 1

    out = []
    last = ""
    for seg in segs:
        text = (seg.get("src") or "").strip()
        if not text:
            continue
        key = _norm(text)
        dur = max(seg["end"] - seg["start"], 0.1)
        conf = seg.get("conf", 1.0)
        silent = sum(overlap(seg["start"], seg["end"], b, e) for b, e in silences)
        mid = (seg["start"] + seg["end"]) / 2.0
        mid_silent = any(b <= mid <= e for b, e in silences)

        if conf < 0.40:
            continue
        # Speech rate sanity: a long segment with almost no words is whisper
        # captioning music ("see you in the next video"). 0.4 chars/s over 30 s
        # is not human speech in any language.
        cps = len(text) / dur
        if dur >= 10 and cps < 1.2:
            continue
        if dur >= 6 and cps < 0.8:
            continue
        if silent / dur > 0.6 or (mid_silent and dur > 20):
            continue
        repeats = counts.get(key, 0)
        if repeats >= 2 and dur >= 8:

## captions.align_by_content
def align_by_content(path, cues, total, windows=(0.2, 0.5, 0.8), duration=30):
    """Measure subtitle offset by matching recognised speech to cue text.

    Only meaningful when the subtitle language matches the audio; cross-language
    tracks produce almost no matches, and the caller should report that instead
    of shifting anything.
    """
    diffs = []
    langs = set()
    tmpdir = os.path.dirname(path)
    for i, frac in enumerate(windows):
        start = max(0.0, total * frac - duration / 2.0)
        if start + duration > total:
            start = max(0.0, total - duration)
        clip = os.path.join(tmpdir, "align_%d.wav" % i)
        base = os.path.join(tmpdir, "align_%d" % i)
        try:
            run([FFMPEG, "-y", "-v", "error", "-ss", str(start), "-t", str(duration),
                 "-i", path, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", clip],
                timeout=300)
            segs, lang = transcribe_chunk(clip, base)
        except Exception:
            continue
        if lang:
            langs.add(lang)
        for seg in segs:
            t = seg["start"] + start
            best, score = None, 0.0
            for c in cues:
                if abs(c["start"] - t) > 8.0:
                    continue
                sc = text_sim(seg.get("src", ""), c.get("src", "") or c.get("dst", ""))
                if sc > score:
                    best, score = c, sc
            if best is not None and score >= 0.5:
                diffs.append(t - best["start"])
    if len(diffs) < 6:
        return None, len(diffs), None, sorted(langs)
    diffs.sort()
    med = diffs[len(diffs) // 2]
    mad = sorted(abs(d - med) for d in diffs)[len(diffs) // 2]
    return round(med, 2), len(diffs), round(mad, 2), sorted(langs)


def _wav_frames(path, frame_ms=20):

## content.js api
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
    if (S.root) {
      S.root.querySelectorAll('.segbtn').forEach(function (b) {
        b.classList.toggle('on', b.getAttribute('data-mode') === (cfg.mode || 'local'));
      });