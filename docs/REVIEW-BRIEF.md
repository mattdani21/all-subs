# All Subs — production-readiness and direction review

You are reviewing a real, working open-source project. Read the code at
https://github.com/mattdani21/all-subs (public, MIT) before answering. Be concrete and
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
