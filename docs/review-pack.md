# CODE PACK

## README.md
```markdown
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
  missing key, and rejected subtitle tracks.

## Limits

- macOS-first. Engine is stdlib Python + brew binaries; Linux should work, Windows has no
  install path yet.
- `yt-dlp` is refused by YouTube's bot check; bilibili and direct video hosts work.
- Overlay can't attach to a bare `<video>` in fullscreen — only container fullscreen.
- Library subtitles occasionally come from a different release; the duration gate catches
  the obvious mismatches, not every offset. Use `Check sync` for same-language tracks, or
  the ±0.1 s nudge otherwise.
- Alpha quality: unsigned, no auto-update.

## Controls

- `Alt+Shift+A` — open/close the panel
- Bilingual — original line above the translation
- `−0.1s` / `+0.1s` — timing nudge; the correction is saved per site
- Re-sync — refetch cues (after the deep pass rewrites them)
- Check sync — re-listens to three 30-second samples and shifts the track if it is out

## API (engine)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | engine, model, keys, RAM |
| GET/POST | `/api/config` | read setup state / store keys (written 0600) |
| POST | `/api/jobs` | `{url, target, mode, duration}` |
| GET | `/api/jobs/{id}` | status, stage, progress |
| GET | `/api/jobs/{id}/cues?from=N` | `{i,s,e,x,t}` |
| POST | `/api/jobs/{id}/refine` | re-run the whole-film pass only |
| POST | `/api/jobs/{id}/align` | content-matched timing check; shifts cues if genuinely out |
| GET | `/api/jobs/{id}.vtt` | WebVTT export |

## Offline mode (experimental)

`./allsubs local-model` pulls Qwen3-4B (~2.5 GB) and the panel gains an offline toggle.
Whisper runs first, then llama-server, so the two never share RAM. Fits 16 GB+; on an
8 GB machine it is CPU-only and impractically slow. Cloud translation stays the default.

## Layout

```
engine/captions.py    probe, native subs, audio, whisper, translation
engine/providers.py   Wikidata → Wyzie resolution + sync gate
engine/server.py      HTTP API, job runner, cache
engine/local_llm.py   offline translation via llama.cpp
extension/            MV3: overlay.js, content.js, options, popup
test/                 unit tests, local harness, Playwright e2e
```

## Licence

MIT. The film in the screenshot is *Shadow* (2018), used only to demonstrate the tool.

```

## engine/providers.py
```python
"""Existing-subtitle providers.

Chain: title + year -> Wikidata -> IMDb id -> Wyzie download -> sync gate.
No API key for resolution (Wikidata is open), one free key for Wyzie.
A track is accepted only when its timing plausibly covers the film; otherwise the
caller falls back to ASR.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request

import captions

WYZIE_DOWNLOAD = "https://sub.wyzie.io/download"
WIKIDATA = "https://query.wikidata.org/sparql"
UA = "AllSubs/0.1 (local subtitle resolver)"

AD_PATTERNS = ("wyzie", "free plan", "sub.wyzie.io")


def clean_title(raw):
    """'Shadow.2018 - (CHINESE MOVE'S CINEMA HD' -> ('Shadow', 2018)."""
    text = raw or ""
    year = None
    m = re.search(r"(19|20)\d{2}", text)
    if m:
        year = int(m.group(0))
        text = text[:m.start()]
    text = re.split(r"\s+-\s+|\s*\|\s*|\s*\(", text)[0]
    text = text.replace(".", " ").replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip(" -:,")
    return text, year


def wikidata_imdb(title, year, timeout=20):
    if not title:
        return None
    label = json.dumps(title)
    year_filter = ""
    if year:
        year_filter = "FILTER(YEAR(?date) = %d)" % year
    query = (
        "SELECT ?film ?imdb ?date WHERE { "
        "?film wdt:P31/wdt:P279* wd:Q11424; rdfs:label %s@en; "
        "wdt:P577 ?date; wdt:P345 ?imdb. %s "
        "} ORDER BY DESC(?date) LIMIT 5" % (label, year_filter))
    url = WIKIDATA + "?format=json&query=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except Exception:
        return None
    rows = data.get("results", {}).get("bindings") or []
    return rows[0]["imdb"]["value"] if rows else None


def _key():
    captions.load_env()
    return os.environ.get("WYZIE_API_KEY")


def wyzie_download(imdb_id, language="en", timeout=30):
    key = _key()
    if not key or not imdb_id:
        return None
    params = urllib.parse.urlencode({
        "id": imdb_id, "language": language, "to": "vtt", "key": key})
    req = urllib.request.Request(WYZIE_DOWNLOAD + "?" + params,
                                 headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception:
        return None


def strip_ads(cues):
    out = []
    for c in cues:
        text = (c.get("src") or "").lower()
        if any(p in text for p in AD_PATTERNS):
            continue
        out.append(c)
    return out


def accept(cues, duration):
    """Sync gate: a track must plausibly span the film, or we do not trust it."""
    if not cues or not duration:
        return False, "no duration to check against"
    if len(cues) < 50:
        return False, "only %d cues" % len(cues)
    first = min(c["start"] for c in cues)
    last = max(c["end"] for c in cues)
    if last < duration * 0.70:
        return False, "ends at %d min for a %d min film" % (last / 60, duration / 60)
    if last > duration * 1.05:
        return False, "runs %d min past the film" % ((last - duration) / 60)
    if first > duration * 0.35:
        return False, "starts %d min in" % (first / 60)
    return True, "covers %.0f-%.0f of %.0f min" % (first / 60, last / 60, duration / 60)


def find(title, duration, target="en"):
    """Return (cues, provider, language, note) or None."""
    name, year = clean_title(title)
    if not name:
        return None
    imdb_id = wikidata_imdb(name, year)
    if not imdb_id:
        return None
    text = wyzie_download(imdb_id, target)
    if not text or not text.lstrip().startswith("WEBVTT"):
        return None
    cues = captions.parse_vtt(text)
    cues = strip_ads(cues)
    ok, note = accept(cues, duration)
    if not ok:
        return {"rejected": True, "note": note, "imdb": imdb_id}
    for i, c in enumerate(cues):
        c["i"] = i
    return {"cues": cues, "imdb": imdb_id, "lang": target, "note": note}

```

## engine/server.py (routing + align endpoint)
```python
def run_job(job):
    with SEM:
        try:
            _run_job(job)
        except Exception as exc:  # keep the daemon alive, surface the error
            log("job %s failed: %s\n%s" % (job.id, exc, traceback.format_exc()))
            job.set(status="error", stage="Failed", error=str(exc)[:500])
            job.to_disk()


def _run_job(job):
    job.set(status="probing", stage="Reading page")
    log("job %s: probing %s" % (job.id, job.url))

    if job.title_hint:
        job.set(title=job.title_hint)

    # YouTube usually already has captions: use them instead of downloading audio
    if captions.youtube_id(job.url):
        job.set(status="searching", stage="Reading YouTube captions", progress=0.1)
        yt = captions.youtube_cues(job.url, job.target)
        if yt:
            cues = captions.split_display([dict(c) for c in yt["cues"]])
            if (yt.get("lang") or "").startswith(job.target):
                for c in cues:
                    c["dst"] = c["src"]
            else:
                translated = captions.translate_cues(
                    cues, job.target, {"title": job.title})
                for c in cues:
                    c["dst"] = translated.get(c["i"], c["src"])
            job.add_cues(cues)
            job.set(status="done", stage="Captions ready (YouTube)", progress=1.0,
                    source="youtube", lang=yt.get("lang"),
                    duration=job.duration_hint or 0)
            job.to_disk()
            _cache(job)
            log("job %s: youtube captions, %d cues" % (job.id, len(cues)))
            return

    pre = PREFETCH.get(job.id)
    if pre and time.time() - pre["at"] < 900:
        job.set(title=pre.get("title") or "", duration=pre.get("duration") or 0)
        if pre.get("found") and pre["found"].get("cues"):
            cues = pre["found"]["cues"]
            for c in cues:
                c["dst"] = c["src"]
            job.add_cues(cues)
            job.set(status="done", stage="Captions ready (library)", progress=1.0,
                    source="wyzie", lang=pre["found"].get("lang"),
                    duration=pre.get("duration") or 0)
            job.to_disk()
            _cache(job)
            log("job %s: prefetched library track (%d cues)" % (job.id, len(cues)))
            return
        meta = {"title": pre.get("title") or "", "duration": pre.get("duration") or 0,
                "subtitles": {}, "automatic_captions": {}}
        log("job %s: using prefetched metadata" % job.id)
    else:
        try:
            meta = captions.probe(job.url, cookies=job.cookies)
        except Exception as exc:
            if not job.media_url:
                raise
            log("job %s: page probe failed (%s); using stream URL" % (job.id, exc))
            meta = {"title": job.title_hint or "", "duration": 0, "subtitles": {},
                    "automatic_captions": {}}
    job.set(title=meta["title"] or job.title_hint or "",
            duration=meta["duration"] or 0)
    log("job %s: %s (%ss) native subs=%s" % (
        job.id, meta["title"], meta["duration"], list(meta["subtitles"].keys())))

    target_name = captions.TARGET_NAMES.get(job.target, job.target)

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
            _cache(job)
            log("job %s: done (cloud), %d cues" % (job.id, len(job.cues)))
            return
        except Exception as exc:
            log("job %s: cloud pass failed (%s); falling back to local" % (job.id, exc))
            with job.lock:
```

## engine/server.py (align endpoint)
```python
        m = re.match(r"^/api/jobs/([a-zA-Z0-9]+)/align$", parsed.path)
        if m:
            job = JOBS.get(m.group(1))
            if not job or not job.cues:
                return self._send(404, {"error": "no such job"})
            t0 = time.time()
            try:
                audio = _job_audio(job)
                total = job.duration or captions.duration_of(audio)
                offset, matches, mad, langs = captions.align_by_content(
                    audio, list(job.cues), total)
            except Exception as exc:
                log("job %s: sync check failed: %s" % (job.id, exc))
                return self._send(500, {"error": str(exc)[:300]})
            applied = False
            if (offset is not None and abs(offset) >= 0.4 and matches >= 8
                    and (mad or 0) <= 1.2):
                with job.lock:
                    for c in job.cues:
                        c["start"] = max(0.0, c["start"] + offset)
                        c["end"] = max(0.0, c["end"] + offset)
                    job.version += 1
                applied = True
            job.set(align={"offset": offset, "matches": matches, "mad": mad,
                           "langs": langs, "applied": applied})
            job.to_disk()
            _cache(job)
            log("job %s: sync check offset=%s matches=%d mad=%s applied=%s (%.0fs)" % (
                job.id, offset, matches, mad, applied, time.time() - t0))
            return self._send(200, {"ok": True, "offset": offset, "matches": matches,
                                    "mad": mad, "langs": langs, "applied": applied,
                                    "version": job.version,
                                    "secs": round(time.time() - t0, 1)})

        m = re.match(r"^/api/jobs/([a-zA-Z0-9]+)/cancel$", parsed.path)
        if m:
            job = JOBS.get(m.group(1))
            if job:
                job.set(status="cancelled", stage="Cancelled")
            return self._send(200, {"ok": True})
```

## engine/captions.py (filter_segments)
```python
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
            continue
        if repeats >= (4 if len(key) <= 3 else 3):
            continue
        if any(a in key for a in (_norm(x) for x in ARTIFACTS)):
            if counts.get(key, 0) >= 2 or (lang and not lang.startswith("en")):
                continue
        if key == last:
            continue
        last = key
        out.append({"start": seg["start"], "end": seg["end"], "src": text})
```

## engine/captions.py (split_display)
```python
def split_display(cues, limit_seconds=None):
    """Break whisper segments into subtitle-sized cues with proportional timing."""
    out = []
    for cue in cues:
        text = cue["src"].strip()
        budget = CUE_MAX_CJK if is_cjk(text) else CUE_MAX_LATIN
        if len(text) <= budget or cue["end"] - cue["start"] < 1.2:
            single = dict(cue)
            if single["end"] - single["start"] > 8.0:
                single["end"] = round(single["start"] + 8.0, 3)
            out.append(single)
            continue
        parts = []
        buf = ""
        for token in re.split(r"(?<=[。！？；，、.!?;,])\s*", text):
            if not token:
                continue
            if len(buf) + len(token) > budget and buf:
                parts.append(buf.strip())
                buf = token
            else:
                buf += token
        if buf.strip():
            parts.append(buf.strip())
        if len(parts) <= 1:
            out.append(dict(cue))
            continue
        span = cue["end"] - cue["start"]
        total_chars = sum(max(len(p), 1) for p in parts)
        t = cue["start"]
        for p in parts:
            share = span * (max(len(p), 1) / total_chars)
            out.append({"start": round(t, 3), "end": round(t + share, 3), "src": p})
            t += share
    # renumber and drop zero-length artefacts
    cleaned = []
    for i, c in enumerate(out):
        if c["end"] - c["start"] < 0.25:
            c["end"] = c["start"] + 0.6
        c["i"] = i
        cleaned.append(c)
    return cleaned


# ---------------------------------------------------------------- LLM

def llm_json(system, user, max_tokens=2600, temperature=0.2, retries=3):
    """JSON-mode chat call. deepseek-flash with thinking off; deepseek-chat fallback."""
    load_env()
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")
    models = [(os.environ.get("ALLSUBS_MODEL", "deepseek-flash"), True)]
    if models[0][0] != "deepseek-chat":
        models.append(("deepseek-chat", False))
    last = None
    for model, no_think in models:
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system},
```

## engine/captions.py (snap + align_by_content)
```python
def snap_to_onsets(cues, wav_path, max_shift=0.7):
    """Move each cue start to the first speech frame near it, killing lead-in slop."""
    try:
        frames, step = _wav_frames(wav_path)
    except Exception:
        return cues
    if not frames:
        return cues
    floor = sorted(frames)[int(len(frames) * 0.2)] or 1.0
    moved = 0
    for c in cues:
        lo = max(0, int((c["start"] - 0.45) / step))
        hi = min(len(frames) - 1, int((c["start"] + max_shift) / step))
        seg = frames[lo:hi + 1]
        if not seg:
            continue
        peak = max(seg)
        thresh = max(floor * 3.0, peak * 0.18)
        for i, v in enumerate(seg):
            if v >= thresh:
                t = (lo + i) * step
                if t > c["start"] + 0.02:
                    c["start"] = round(t, 3)
                    moved += 1
                break
        if c["end"] <= c["start"]:
            c["end"] = round(c["start"] + 0.8, 3)
    return cues


def is_cjk(text):
    return len(re.findall(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", text)) > len(text) * 0.3


def split_display(cues, limit_seconds=None):
    """Break whisper segments into subtitle-sized cues with proportional timing."""
    out = []
    for cue in cues:
        text = cue["src"].strip()
        budget = CUE_MAX_CJK if is_cjk(text) else CUE_MAX_LATIN
        if len(text) <= budget or cue["end"] - cue["start"] < 1.2:
            single = dict(cue)
            if single["end"] - single["start"] > 8.0:
                single["end"] = round(single["start"] + 8.0, 3)
            out.append(single)
            continue
        parts = []
        buf = ""
        for token in re.split(r"(?<=[。！？；，、.!?;,])\s*", text):
            if not token:
                continue
            if len(buf) + len(token) > budget and buf:
                parts.append(buf.strip())
                buf = token
            else:
                buf += token
        if buf.strip():
            parts.append(buf.strip())
        if len(parts) <= 1:
            out.append(dict(cue))
            continue
        span = cue["end"] - cue["start"]
        total_chars = sum(max(len(p), 1) for p in parts)
        t = cue["start"]
        for p in parts:
            share = span * (max(len(p), 1) / total_chars)
            out.append({"start": round(t, 3), "end": round(t + share, 3), "src": p})
            t += share
    # renumber and drop zero-length artefacts
    cleaned = []
```

## extension/content.js (api + refresh + pull)
```javascript
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
      const hint = S.root.querySelector('[data-el="seghint"]');
      if (hint) hint.textContent = cfg.mode === 'cloud'
        ? 'One multimodal call per chunk. Fastest; audio leaves this Mac (~$0.30 per film).'
        : 'Transcribes with whisper on this Mac. Audio stays local.';
    }
    const bi = S.root.querySelector('[data-el="bilingual"]');
    if (bi) bi.classList.toggle('on', !!cfg.bilingual);
  }

  function adjustOffset(delta) {
    cfg.offset = Math.round(((cfg.offset || 0) + delta) * 10) / 10;
    if (S.overlay) S.overlay.setOffset(cfg.offset);
    setStatus('Shift ' + (cfg.offset > 0 ? '+' : '') + cfg.offset.toFixed(1) + 's later');
    try {
      chrome.storage.local.get({ offsets: {} }, function (v) {
        const offsets = v.offsets || {};
        offsets[location.hostname] = cfg.offset;
        chrome.storage.local.set({ offsets: offsets });
      });
    } catch (e) { /* noop */ }
  }

  function loadSiteOffset() {
    try {
      chrome.storage.local.get({ offsets: {} }, function (v) {
        const saved = (v.offsets || {})[location.hostname];
        if (typeof saved === 'number' && saved !== 0) {
          cfg.offset = saved;
          if (S.overlay) S.overlay.setOffset(saved);
        }
      });
    } catch (e) { /* noop */ }
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
```

## extension/overlay.js (full)
```javascript
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
      const t = video.currentTime - offset;
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

```
