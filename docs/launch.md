# Launch copy — the routing story

Repo: https://github.com/mattdani21/all-subs
Hero image: `docs/hero.png`

Thesis: **retrieve → cloud → local ASR → fully local.** Each rung is faster or more private
than the one below it, and a gate decides whether that rung's answer is trustworthy.

Numbers: retrieve ~8 s / 1,072 cues; cloud 4.9 s per 60 s of audio (~$0.30 per film); local
ASR 11–17 min for 116 min; fully local needs 16 GB+.

---

## LinkedIn

Most AI features have one setting: generate. Mine has four, and it only generates when it
has to.

I built a Chrome extension that captions any video. Underneath, it's a router:

**Rung 1 — retrieve.** If someone already made it, use it. Title + year → Wikidata → IMDb →
subtitle library, gated so a track that doesn't span the film is rejected. On a 116-minute
film: 1,072 cues in about 8 seconds. Often better than a model, because a human wrote it.

**Rung 2 — cloud.** Nothing usable? Send an audio chunk to a multimodal model and get
timestamped, translated cues back in one pass. Measured: 60 seconds of film in 4.9 seconds,
about $0.30 for a feature film. Fastest rung, but the audio leaves your machine.

**Rung 3 — local ASR.** If the audio must stay put, whisper.cpp runs on the Mac and only the
cue text goes to the LLM for translation. 11–17 minutes for the same film.

**Rung 4 — fully local.** Whisper plus a 4B model on the laptop. Slower, flatter prose,
nothing leaves the machine. Needs 16 GB to be usable.

The interesting part isn't the models. It's the gates:

- A retrieved subtitle must cover 70–105% of the runtime. My first IMDb guess gave a heist
  film's subtitles on a 116-minute movie — the last line landed 22 minutes after the
  credits. That's what the gate is for.
- The cloud rung needs credit and returns coarser timestamps, so every cue is sanity-checked
  (duration bounds, ordering) before it's trusted; if the call fails, the job falls through
  to local whisper instead of dying. That happened during testing — a 402 fell back and
  finished.
- Local needs RAM; the toggle disables itself below 16 GB because whisper and the 4B model
  can't share 8 GB.

Routing is the feature. Retrieval, cloud inference, local inference and on-device models
have completely different cost, latency and privacy curves, and picking one of them as "the
answer" is how you end up paying a model to redo work someone already did.

Open source, MIT. Still needs a Mac and a terminal to install — that's next.

https://github.com/mattdani21/all-subs

---

## X thread

1/
Every AI feature I build now starts with a router, not a model.

Four rungs: retrieve → cloud → local ASR → fully local.

My captioning extension is the cleanest example. (repo at the end)

2/
Rung 1: retrieve.

Title + year → Wikidata → IMDb → subtitle library.
1,072 cues in 8 seconds.

Someone already did the work. Don't pay a model to redo it.

3/
Rung 2: cloud.

60 seconds of film audio → one multimodal call → timestamped, translated cues.
4.9 seconds. About $0.30 for a feature film.

Fastest rung. The audio leaves your machine.

4/
Rung 3: local ASR.

Whisper transcribes on the Mac, only the cue text goes to an LLM.
17 minutes for a 116-minute film.

Audio stays put.

5/
Rung 4: fully local.

Whisper + a 4B model on the laptop. Nothing leaves the machine.
Slower, flatter prose, needs 16 GB.

6/
The models aren't the hard part. The gates are.

• retrieved subs must span 70–105% of the film (my first guess ran 22 min past the credits)
• cloud needs credit, and falls back locally on failure
• local needs 16 GB+

A router is gates, not if-statements.

7/
Open source, MIT. macOS, terminal install, rough edges documented.

https://github.com/mattdani21/all-subs

---

## Short variant

Most AI products jump straight to generation.

All Subs is a router with four rungs:

1. retrieve — existing subtitles, 8 seconds
2. cloud — one multimodal call, ~$0.30/film
3. local ASR — 17 minutes, audio stays local
4. fully local — small model on the machine, nothing leaves

Each rung has a gate that decides if its answer is trustworthy. Routing is the feature.

MIT, link below.

---

## Notes

- Attach `docs/hero.png` — it shows the retrieved track, i.e. rung 1.
- "22 minutes past the credits" is the most quotable line; spin it into its own follow-up.
- The fallback story (cloud 402 → local finished the job) is a good "gates" reply, not a
  headline.
- Don't claim real-time, DRM, or "any site"; the README lists the limits.
- Post LinkedIn Tue–Thu 08:00–09:30 SAST; X thread 15:00–17:00 SAST.
