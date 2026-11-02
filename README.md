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
