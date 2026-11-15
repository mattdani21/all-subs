# Review by deepseek-v4-pro

# Critique memo: All Subs

## Verdict

Worth polishing, but only as a credible developer/portfolio artifact, not as a product for non-technical strangers. The router idea — existing subtitles first, ASR only when needed — is a genuinely useful shape, and the timing gates are the most product-like part of the repo [E]. But today the project optimizes for the owner’s own setup, not for a stranger’s first run. I would not add new inference rungs or a hosted service. I would spend the next few weeks on install reliability, a deterministic demo, security boundary, CI validation, and automatic correction of the worst timing failure. The success metric is “a skeptical developer cloned it and got captions on a known test clip in under ten minutes,” not “more pipeline diagrams.”

---

## Top five changes, ranked by quality gained per hour

### 1. Make `./allsubs setup` and `./allsubs doctor` idempotent and diagnostic
**Effort: 2–3 days**

The current setup is the fatal step: Homebrew, a 1.6 GB whisper model, Python, Developer Mode, and “load unpacked” [E]. A stranger will hit one missing tool, a too-new macOS, a wrong path, or a brew cask conflict and silently fail.

Build this into the CLI:

- `setup` should detect architecture, macOS version, and already-installed brew packages.
- Install only missing pieces: `ffmpeg`, `whisper-cpp`, `yt-dlp`, Python.
- Download the speech model to a stable path, verify checksum, and write the actual paths into a generated local config.
- Use `set -euo pipefail` for shell paths and print exactly which command failed.
- `doctor` should emit one paste-able diagnostic block: `echo "uname=..."; sw_vers; brew list --versions ffmpeg whisper-cpp yt-dlp; df -h` etc.
- After setup, print the exact Chrome instructions with the absolute path to `extension/`.

This is the highest-leverage work in the repo. It converts “interesting but failed here” into a legitimate bug report.

### 2. Add `./allsubs demo`
**Effort: 1–2 days**

The README hero image implies it works, but there is no deterministic, local, small end-to-end check.

Add a short public-domain or CC0 clip plus a known VTT fixture. `./allsubs demo` should:

- Start the engine.
- Open a local HTML page containing a `<video>` pointing at the fixture.
- The page should exercise the extension overlay against a local player.
- Print expected result: “You should see captions within X seconds.”

This gives the owner and every stranger the same validation story. It also becomes the basis for the Playwright harness already partially present [E].

### 3. Add an authentication boundary to the local HTTP engine
**Effort: 1–3 days**

The routing snippets show `/health`, `/api/config`, and `/api/jobs` with no auth check [E]. The API can store keys and start jobs [E]. At minimum:

- Bind only to `127.0.0.1`, enforce it explicitly.
- Generate a random API token on start, store it in a file the extension can read during setup.
- Require `Authorization: Bearer ...` on every non-health route.
- Stop accepting secrets from arbitrary local callers.
- Prefer macOS Keychain over `~/.allsubs/config.json` for API keys; keep `.env` as a developer fallback only.

This is cheap and pre-empts the first hostile review question.

### 4. Put the existing Playwright harness in CI with a fixture
**Effort: 3–5 days**

The owner’s known weakness list says there are unit tests plus a Playwright harness, but no automated end-to-end suite [E]. That is the widest credibility gap.

Add a GitHub Actions job that:

- Runs the Python engine.
- Runs the Playwright extension test against the local fixture from `./allsubs demo`.
- Runs the existing unit tests.
- Produces a public CI badge.
- Uses a macOS runner at first; add Linux and Windows later for Python-only pieces.

This is not just testing; it is the public proof that the project is not a one-film mirage.

### 5. Automatically align same-language library and native tracks
**Effort: 2–4 days**

The manual “Check sync” endpoint already does real work: it samples windows, matches recognized lines, and shifts cues when genuinely out [E]. But it is opt-in.

Library tracks can come from different releases and can lead speech [E]. The alignment logic should run automatically before a same-language library/native track is shown:

- Sample one or two 60-second windows.
- Run `align_by_content`.
- If confidence criteria pass — the current code uses `abs(offset) >= 0.4`, `matches >= 8`, `mad <= 1.2` [E] — apply the shift.
- If criteria fail, do not shift, and leave manual sync as a fallback.

This directly removes the most user-visible quality defect, using existing code, for modest effort.

---

## Distribution: stay local, delay the Chrome Web Store

**Recommendation: keep the unpacked extension + local engine as the primary distribution for now. Do not build a hosted service or a full signed Mac app yet.**

- **Unpacked extension + local engine:** cheap, developer-compatible, but not enough for strangers.
- **Signed/notarised Mac app:** high polish, high effort, low open-source credibility return. It also creates consumer expectations: support, auto-update, security reviews.
- **Hosted service:** maximum adoption but recurring cost, audio/ToS risk, key management, and support burden. It contradicts the no-revenue goal and greatly increases legal exposure.
- **Chrome Web Store + native-messaging host:** the best long-term choice, because CWS gives auto-update and social proof, and a native host removes the localhost HTTP attack surface. But it does not remove the engine install problem. It is only worth doing after the top five changes are done and real users ask for one-click install.

For reputation, a clean CI-passing repo with a reproducible demo is stronger than an unsigned “load unpacked” extension or a half-finished packaged app.

---

## Architecture: localhost HTTP engine is the right shape for now

Keeping inference in a local Python engine is correct.

- whisper.cpp and llama.cpp run native; the extension’s MV3 service worker cannot load or run 1.6 GB models [E].
- WASM/WebGPU inference would require quantized models and would still hit the 8 GB RAM wall. WebGPU support for whisper is nowhere near a drop-in replacement [A].
- A native messaging host is the only serious alternative: it would remove the localhost HTTP port and tighten the security boundary. But it adds packaging and maintenance complexity.
- The localhost HTTP API is fine for a single-user local developer tool, but it breaks first on fixed port collisions, lack of auth, and unclear job/cache semantics when pages reuse URLs.

Do not move inference into the extension. Move the transport to a native host only when packaging becomes the limiting factor.

---

## Where the owner’s assumptions are wrong

1. **“The code works, so the repo is credible.”**  
   For strangers, credibility comes from reproducibility. One validated film [E] is not evidence of correctness. CI, a demo, and an install matrix matter more than more pipeline features.

2. **“More rungs means a stronger product.”**  
   The router idea is strong, but the repo now includes cloud ASR, local ASR, local LLM translation, deep pass, library lookup, YouTube captions, and manual sync. Each rung increases the surface a stranger can hit before success.

3. **“No revenue means no distribution story.”**  
   Distribution is how strangers experience the code. A CWS listing or Homebrew tap is not a revenue play; it is a credibility and adoption play. The current unpacked flow filters out almost everyone.

4. **“Storing keys in a 0600 config is acceptable.”**  
   For a tool that accepts video URLs, downloads audio, and calls external APIs, “keys on disk and a localhost API” is the first thing a security reviewer will attack, even if it is technically local.

5. **“Avoiding piracy hosts protects me.”**  
   The README avoids naming specific piracy sites, but the generic stream sniffer, `yt-dlp` direct fetch, and YouTube cookie workaround [E] still look like circumvention plumbing from outside. The legal reviewer will not care that Netflix is out of scope.

---

## Three hostile reviewer objections and cheapest honest pre-empts

1. **“There is an unauthenticated localhost HTTP server and keys on disk.”**

   The code shows key storage and API routes [E]. A reviewer will assume any local webpage or process can reach it.

   *Pre-empt:* add a random bearer token, bind 127.0.0.1 explicitly, move keys to Keychain, and document the threat model. Cost: 1–3 days.

2. **“One film, one Mac, no real tests.”**

   The current README claims many sites and paths, but the known weakness list admits one end-to-end film [E].

   *Pre-empt:* tone down claims until CI passes; add the demo and Playwright CI; show the public badge in the README. Cost: 3–5 days.

3. **“This is an anti-DRM/stream-ripping toolkit with a privacy wrapper.”**

   The engine detects media URLs, downloads audio with `yt-dlp`, and has an opt-in YouTube cookie-from-browser path [E]. Even with DRM out of scope, a hostile reviewer may label it a circumvention tool.

   *Pre-empt:* remove the cookie-from-browser option by default, require explicit user action before fetching non-YouTube media, and narrow the README examples to content the user has rights to view. Cost: 1–2 days.

---

## Pipeline shape: do not replace ASR + LLM with end-to-end speech translation

End-to-end speech translation would not be materially better for this product.

- The dominant cost is ASR: 94–97% of wall time [E]. A comparable end-to-end model would not reduce that.
- The overlay needs source-language text and target-language text for bilingual display [E]. Most end-to-end systems lose the source text or produce worse timestamps.
- The current LLM translation is cheap, steerable, and benefits from the deep-pass context [E]. An end-to-end model would throw that away.
- The cloud rung is already a form of end-to-end speech translation via a multimodal LLM [E], and it is acceptable only because it is gated and optional.

Specialized end-to-end models could be useful for low-resource languages, but this project’s target is foreign films with readable language support, where ASR + LLM is the safer, more maintainable shape.

---

## What should be cut

### Cut or stop maintaining

- **Rung 4, fully local translation with Qwen3-4B.**  
  It is experimental, has visible quality loss, needs extra model distribution, and is impractical on the target 8 GB hardware [E]. Keep local ASR; keep cloud translation. Hide offline translation behind an experimental flag or remove it from the README’s primary story.

- **Cloud ASR path as a first-class rung.**  
  It adds cost, audio-leaves-the-machine behavior, and another dependency. It is useful for some users, but it should be an explicitly optional provider, not a default fallback that competes with local ASR.

- **YouTube cookie extraction.**  
  The `ALLSUBS_YOUTUBE_COOKIES` path [E] creates keychain prompts and legal risk for a marginal reliability gain. Remove it.

- **`handoff` and any packaging command not tied to the core flow.**  
  From the CLI list [E], handoff appears untested and unexplained. If it is not used by the owner or verified by CI, cut it.

Features worth keeping: the library lookup with duration gate, the automatic ASR hallucination filter, the deep pass if it remains optional, and the content-based sync check. Those are the actual differentiators.

---
_usage: {"prompt_tokens": 12290, "completion_tokens": 10603, "total_tokens": 22893, "prompt_tokens_details": {"cached_tokens": 12288}, "completion_tokens_details": {"reasoning_tokens": 7948}, "prompt_cache_hit_tokens": 12288, "prompt_cache_miss_tokens": 2} · 101s_
