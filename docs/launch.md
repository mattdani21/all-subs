# Sharing & Launch Kit — All Subs v0.4.0

- **Repo**: https://github.com/mattdani21/all-subs
- **Live page**: https://mattdani21.github.io/all-subs/
- **Release (v0.4.0)**: https://github.com/mattdani21/all-subs/releases/tag/v0.4.0

## Ready-to-Attach Media Assets

| Asset | File | Best used for |
|---|---|---|
| **Hero / Social Card** (`2400×1260`) | `docs/social-card.png` | Lead image for X, LinkedIn, & GitHub Social Preview (Repo → Settings → Social preview) |
| **Architecture Diagram** (`3200×1840`) | `docs/router-diagram.png` | Image 2 on LinkedIn carousel / Tweet 3 in X thread |
| **The Four Gates Card** (`2800×1800`) | `docs/media/gates-card.png` | Image 3 on LinkedIn / Tweet 4 ("A router is gates, not if-statements") |
| **Benchmarks & Cost Card** (`2800×1680`) | `docs/media/benchmarks-card.png` | Image 4 on LinkedIn / Tweet 5 (measured numbers & v0.4.0 optimizations) |
| **Real Film Frame** (`1200×499`) | `docs/hero.png` | Tweet 2 or standalone proof-of-work screenshot over *Shadow* (2018) |
| **Clean Artwork** (`16:9`) | `docs/media/artwork-hero.jpg` | Text-free banner / Substack / blog header |

---

## LinkedIn — Primary Post (Recommended)

**Attach 4 images in order** (renders as a clean swipeable visual deck):
1. `docs/social-card.png`
2. `docs/router-diagram.png`
3. `docs/media/gates-card.png`
4. `docs/media/benchmarks-card.png`

> Every AI tool I build now starts with the same question: has someone already done this work?
>
> I wanted to watch a 116-minute Chinese film on bilibili.tv that had no subtitle track. The obvious instinct was to throw Whisper + an LLM at two hours of audio. Instead, I built **All Subs** as a router that tries *not* to generate captions unless it has to:
>
> 1. **Retrieve first (2–8 s, $0)** — checks YouTube tracks, site-native tracks, and public subtitle libraries (Wikidata → IMDb → Wyzie), gated on runtime coverage.
> 2. **This Mac — default AI (~$0.02–0.04/film)** — runs `whisper.cpp` locally on Apple Silicon so audio never leaves the laptop; only compact, prefix-cached cue batches go to DeepSeek.
> 3. **Cloud — opt-in (~$0.30/film)** — compresses chunks to 32 kbps MP3 for a single multimodal pass (OpenRouter / Gemini Flash), with automatic failover to local Whisper if a call returns 402 or fails.
> 4. **Offline — experimental (16 GB+)** — `whisper.cpp` + local Qwen3-4B. Nothing leaves the machine.
>
> The surprising part wasn't the models. It was the gates:
> - My first library lookup matched a heist movie's subtitles onto a 116-minute film — the last line landed 22 minutes after the credits. That's why tracks must span 70–105% of runtime.
> - Left alone on rain and score, Whisper hallucinates "Thank you for watching" across 30-second stretches. Silent chunks now skip Whisper completely, and a speech-rate gate drops music hallucinations.
> - In v0.4.0 I also cut LLM API calls by 40% (prefix-cached system context + compact JSON), cut browser cue payloads by 91% (gzip), and dropped idle extension CPU to 0 FPS.
>
> Open source (MIT), zero Python dependencies beyond stdlib, macOS + Chrome MV3. Still alpha and terminal-installed (`./allsubs setup --lite` skips the 1.5 GB model if you just want retrieval/cloud).
>
> Code + v0.4.0 release ZIPs in the comments (or directly at https://github.com/mattdani21/all-subs).

*(Tip: on LinkedIn, dropping the raw link in the first comment or keeping it at the very end both work; attaching the 4 images natively gets much higher reach than a bare link preview.)*

---

## LinkedIn — Short / Punchy Variant

**Attach 1 image:** `docs/media/gates-card.png` (or `docs/social-card.png`)

> Most AI features have one button: *generate*.
>
> I open-sourced **All Subs** (Chrome extension + local macOS engine) to caption foreign films that have no subtitles — and the best speedup wasn't a faster model. It was checking whether a human already made the subtitles first.
>
> • Existing track (YouTube / library): **2–8 seconds, $0**
> • Local `whisper.cpp` + prefix-cached DeepSeek: **~$0.02–0.04 / feature film**, audio stays on your Mac
> • Opt-in Cloud multimodal: **4.9 s per 60 s clip**, fails over to local Whisper on 402
>
> The hard engineering isn't calling models — it's the gates: catching a retrieved subtitle track running 22 minutes past the credits, skipping silent chunks before Whisper hallucinates over rain, and 1-to-1 sync verification.
>
> MIT, stdlib Python, zero hosted backend.
> https://github.com/mattdani21/all-subs

---

## X.com — Single Launch Post

**Attach 2 images:** `docs/social-card.png` + `docs/router-diagram.png`

> Built an open-source Chrome extension + local Mac engine that puts bilingual captions on web videos with no subtitle track.
>
> The trick: it tries *not* to run AI.
>
> • Retrieve existing track: 2–8s, $0
> • Local Whisper + prefix-cached DeepSeek: ~$0.02–0.04/film (audio stays local)
> • Opt-in Cloud: 4.9s/min, fails over to local on 402
> • Browser overlay: 0 FPS idle CPU
>
> MIT · v0.4.0: https://github.com/mattdani21/all-subs

---

## X.com — 6-Tweet Technical Thread

### 1/
**Attach:** `docs/social-card.png`

> Most AI apps jump straight to generation.
>
> I built **All Subs** — a Chrome extension + local Mac engine for subtitling foreign films — around the opposite rule:
>
> Check if a human already made the subtitles first. Only run a model when nothing usable exists.
>
> Just shipped v0.4.0 (MIT). Quick breakdown of the router, the gates, and the cost cuts 🧵

### 2/
**Attach:** `docs/hero.png`

> Started because I wanted to watch *Shadow* (2018) on bilibili.tv and it had zero subtitles.
>
> Instead of waiting 15 minutes for local ASR, Route 1 resolves Title + Year → Wikidata → IMDb → Wyzie and overlays 1,072 human-authored cues in ~8 seconds (and ~0.01 s once the panel prefetches).
>
> Don't pay a model to redo work someone already did.

### 3/
**Attach:** `docs/router-diagram.png`

> When no usable track exists (or you click "Use AI instead"), it runs the mode you pick:
>
> • **This Mac (default)**: lazy-sliced chunks → silent-chunk skip → `whisper.cpp` (Metal) → prefix-cached DeepSeek (~$0.02–0.04/film, audio stays local)
> • **Cloud (opt-in)**: 32 kbps MP3 → Gemini Flash (~4.9s/60s, ~$0.30/film), no 1.5 GB model needed
> • **Offline (16 GB+)**: Whisper + local Qwen3-4B

### 4/
**Attach:** `docs/media/gates-card.png`

> Models are the easy part. **A router is gates, not if-statements.**
>
> Four real failures that shaped the code:
> 1. First IMDb match gave a heist movie's subs running **22 min past the credits** → 70–105% coverage gate
> 2. Whisper hallucinated "Thank you for watching" over rain → silence skip + speech-rate gate
> 3. Cloud 402 mid-film → auto-failover to local Whisper
> 4. Cut drift → 3×30s 1-to-1 sync check (±30s)

### 5/
**Attach:** `docs/media/benchmarks-card.png`

> What v0.4.0 did for efficiency & cost (all measured, zero external Python deps):
>
> • −40% LLM API calls (30 → 18 batches / 1,050 cues) + DeepSeek prefix caching
> • −39% smaller cue prompts (compact JSON + non-verbal skip)
> • −91% smaller browser cue stream (121 KB → 10.6 KB gzipped)
> • 29 ms C-speed onset snapping (down from full-file Python loops)
> • 0 FPS idle browser CPU (`ResizeObserver` + `requestVideoFrameCallback` only while playing)

### 6/
*(No image — lets the GitHub / GitHub Pages link card render cleanly via `og:image`!)*

> Honest limits: macOS-first, terminal install (`./allsubs setup --lite` skips the 1.5 GB model for retrieval/cloud), no DRM (Netflix/Prime out of scope), alpha quality.
>
> Source, v0.4.0 release ZIPs, and architecture docs:
> https://mattdani21.github.io/all-subs/
> https://github.com/mattdani21/all-subs

---

## High-Engagement Follow-Up Replies (Optional)

- **"Why stdlib Python instead of Rust?"**
  > 94–97% of wall time on local ASR is already `whisper.cpp` (C++/Metal), and the rest is `ffmpeg` (C), `yt-dlp`, and network I/O. Rewriting the ~1,700-line engine in Rust moves caption latency by <1% while adding a build step. The only place Rust/Swift wins later is a signed macOS menu-bar installer + Chrome Native Messaging bridge.

- **GitHub Repo Polish Checklist (30 seconds in browser)**:
  1. Go to **GitHub → Settings → Social preview → Edit → Upload** `docs/social-card.png` (so pasting `github.com/mattdani21/all-subs` anywhere renders the custom card).
  2. Set the repo **Website** field to `https://mattdani21.github.io/all-subs/`.
  3. Recommended timing: LinkedIn Tue–Thu 08:00–09:30 SAST; X thread 15:00–17:00 SAST.
