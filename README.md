# All Subs

AI captions for any video, in the browser. It finds existing subtitles when a good
track exists; when it doesn't, it listens to the audio, transcribes it locally with
whisper.cpp, and translates it with an LLM — then overlays the result on the player
in real time.

Built for the case that started it: a Chinese film on bilibili.tv with no subtitle
track at all. Verified on that 116-minute film: 1,052 bilingual cues, opening line
at 02:00, whole-film deep pass done, rendered live on the real player.

## How it works

```
Chrome extension  ──►  local engine (127.0.0.1:8765)
  finds <video>          1. probe page (yt-dlp): title, duration, subtitle inventory
  draws overlay          2. existing track?  yes → use it (official subs win, never overwritten)
  polls cues             3. no track → download audio → 16 kHz mono → whisper.cpp
                         4. chunked ASR (5 min) → cues stream to the browser as they land
                         5. LLM translates each chunk with rolling context
                         6. deep mode: LLM reads the whole transcript, builds a
                            synopsis + name glossary, re-translates every line
```

Nothing leaves the machine except the text sent to the translation API.

## Install

```bash
cd ~/AllSubs
./allsubs start              # local caption engine on :8765
```

### New machine (another Mac)

```bash
# copy the project (AirDrop the folder, or: git clone <bundle> AllSubs)
cd AllSubs
./allsubs setup      # installs ffmpeg / whisper-cpp / yt-dlp, downloads the 1.5 GB model
./allsubs doctor     # verifies binaries, model, API key, engine
./allsubs start
```

`setup` is idempotent. The API key is read from `AllSubs/.env` or `~/.hermes/.env`.
To reuse captions already generated elsewhere, copy `~/.allsubs/cache` across too.

### Package for sharing

```bash
./allsubs package      # -> dist/AllSubs-<version>.zip (source only, no media, no .env)
```

The recipient unzips, runs `./allsubs setup`, then loads `extension/` unpacked. That
is the right shape for an alpha with technical users; it is not a consumer install.

Load the extension once:

1. `chrome://extensions` → Developer mode → **Load unpacked**
2. pick `~/AllSubs/extension`

Then open a video page. An **AS** button appears bottom-right of the player.
Click it (or press `Alt+Shift+A`) → *Caption this video*.

## Requirements

- macOS + Apple Silicon (whisper.cpp with Metal)
- `ffmpeg`, `whisper-cli` (brew), `yt-dlp` (`pip install --user yt-dlp`)
- `~/.whisper-models/ggml-large-v3-turbo.bin` (1.5 GB)
- `DEEPSEEK_API_KEY` in `~/.hermes/.env` (or the environment)

## API (engine)

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | engine + model status |
| POST | `/api/jobs` | `{url, target:"en", mode:"fast"\|"deep", limit?: seconds}` |
| GET | `/api/jobs/{id}` | status, stage, progress, cue count |
| GET | `/api/jobs/{id}/cues?from=N` | cue page: `{i,s,e,x,t}` |
| GET | `/api/jobs/{id}.vtt` | downloadable WebVTT |

Jobs are keyed by URL+target and cached in `~/.allsubs/cache`, so revisiting a film
is instant and offline.

## Subtitle libraries

Before any ASR, the engine resolves the film and looks for an existing English (or target
language) track:

```
title + year --Wikidata--> IMDb id --Wyzie--> .vtt --sync gate--> cues
```

- Resolution needs no key (Wikidata is open). Wyzie needs a free key (1,000/day):
  `WYZIE_API_KEY` in `~/AllSubs/.env`.
- A track is accepted only if it spans the film: it must end inside 70-105% of the
  known duration and start in the first third. Wrong-release subtitles are rejected
  and the job falls back to ASR.
- The free tier injects one ad cue at 00:00; it is stripped.
- The browser sends `video.duration` with the job, because site metadata often has no
  duration until media downloads.

Measured on the 116-minute test film: **1,072 cues in ~8 seconds**, versus ~17 minutes
of ASR. That is the difference between "search" and "generate".

## Speed

- Chunks are 60 s / 120 s / then 300 s, so the first caption lands about a minute in
  instead of after the first five-minute chunk.
- Translation runs in a worker thread while the next chunk is being transcribed, so
  the two stages overlap instead of adding up.
- The whole-film deep pass fans out 6 translation batches at once.
- `--debug` numbers land in the engine log per job: `asr`, `translate`, `deep` seconds.

ASR is the floor: whisper large-v3-turbo runs ~7-13x realtime on an M3 depending on how
much speech the chunk contains, and that dominates wall time. Beating it materially needs
either an existing subtitle track (seconds) or a GPU service.

## Offline mode (experimental)

```bash
./allsubs local-model     # Qwen3-4B-Instruct Q4_K_M, ~2.5 GB
```

Tick **Translate offline on this Mac** in the panel. Transcription runs first and
`llama-server` starts only afterwards, so whisper and the small model never share RAM.
Switching this on produces flatter translations ("都督" becomes "Dudu" rather than
"Commander") and is much slower than DeepSeek.

Measured on an 8 GB M3: Metal offload for the 4B model fails with a command-buffer OOM
and the fallback runs CPU-only around 9 tok/s; under real memory pressure a 10-minute
clip managed 20 of 140 cues in 4.5 minutes. The toggle disables itself below 16 GB for
that reason — on 16 GB+ it is usable, just slower than the cloud path.

## Controls

- `Alt+Shift+A` — open/close the panel
- Bilingual — show the original line above the translation
- `−0.3s` / `+0.3s` — nudge subtitle timing when a site's clock drifts
- Re-sync — refetch every cue (used when the deep pass rewrites translations)

## Known limits

- Fullscreen works when the site fullscreens a container (YouTube, bilibili).
  A bare `<video>` going fullscreen can't host the overlay — the overlay is
  hidden until you exit. Fix later via a wrapper element.
- Content scripts only run in the top frame; players inside cross-origin iframes
  need a per-site rule.
- First caption appears after the first 5-minute chunk is transcribed (~40 s on an
  M3 for a 2-hour film's opening chunk); the whole film takes roughly 10–15 min.
- Subtitle search is native tracks only right now. OpenSubtitles/Wyzie lookup is the
  next provider in the chain (see roadmap). YouTube often refuses `yt-dlp` with a bot
  check; bilibili and direct video hosts work.
- ASR runs with `-mc 0` (no cross-window conditioning) because conditioning is what
  makes whisper loop a single line over music; that costs some speed, not accuracy.
- Translation quality depends on the source ASR; the deep pass is markedly better
  for films with many character names.
- Offline mode needs 16 GB+ for GPU offload; on 8 GB it falls back to CPU and is
  impractically slow. Cloud translation stays the default.

## Roadmap

1. OpenSubtitles + Wyzie providers with a "safe" score (sync offset, language match, rating)
2. Per-site adapters (YouTube, Netflix, bilibili) for player hooks and native track preference
3. Streaming ASR from `chrome.tabCapture` for DRM/live content
4. Speaker labels + glossary editor
5. Firefox port

## Layout

```
engine/captions.py   probe, native subs, audio, whisper, translation
engine/server.py     HTTP API + job runner
extension/           MV3: overlay.js (renderer), content.js (controller), popup
test/player.html     local harness that plays a file through the real overlay
```
