# Launch copy — the routing story

Repo: https://github.com/mattdani21/all-subs
Hero image: `docs/hero.png`

Thesis: **retrieve → generate → local.** Each rung is cheaper or more private than the one
below it, and a gate decides whether that rung's answer is trustworthy.

---

## LinkedIn

Most AI features have one setting: generate. Mine has three, and it only generates when it
has to.

I built a Chrome extension that captions any video. Underneath, it's a router:

**Rung 1 — retrieve.** If someone already made the thing, use it. Title + year → Wikidata →
IMDb → subtitle library, with a gate that rejects tracks which don't span the film. On a
116-minute film that returns 1,072 cues in about 8 seconds. Often better than what a model
would produce, because a human translated it.

**Rung 2 — generate.** Nothing usable? Now spend compute. whisper.cpp transcribes the
audio locally in five-minute chunks, an LLM translates each cue while the next chunk is
still being transcribed. 11–17 minutes for the same film.

**Rung 3 — local.** If you don't want the text leaving the machine at all, a 4B model runs
on the laptop. Slower, flatter prose, but it's yours. Runs properly on 16 GB+.

The interesting part isn't the models. It's the gates between rungs:

- A retrieved subtitle must span 70–105% of the runtime, or it's rejected. My first IMDb
  guess gave a heist film's subtitles on a 116-minute movie — the last line landed 22
  minutes after the credits. That's what the gate is for.
- Generation needs a key and a speech model; the panel says which one is missing instead
  of failing silently.
- Local needs RAM; the toggle disables itself below 16 GB because whisper and the 4B model
  can't share 8 GB.

Routing is the feature. Retrieval, generation and local compute have completely different
cost, latency and privacy curves, and pretending one of them is the answer is how you end
up paying a model to redo work someone already did.

Open source, MIT. Still needs a Mac and a terminal to install — that's next.

https://github.com/mattdani21/all-subs

---

## X thread

1/
Every AI feature I build now starts with a router, not a model.

Three rungs: retrieve → generate → local.

My captioning extension is the cleanest example. (repo at the end)

2/
Rung 1: retrieve.

Title + year → Wikidata → IMDb → subtitle library.
1,072 cues in 8 seconds.

Someone already did the work. Don't pay a model to redo it.

3/
Rung 2: generate.

Nothing usable → whisper.cpp transcribes locally, an LLM translates while the next chunk
is still being transcribed.

17 minutes for a 116-minute film. Only now do we spend compute.

4/
Rung 3: local.

Privacy switch: a 4B model on the machine, nothing leaves it.

Slower and flatter prose. But it's yours, and it works on a plane.

5/
The models aren't the hard part. The gates are.

• retrieved subs must span 70–105% of the film (my first guess ran 22 min past the credits)
• generation needs a key
• local needs 16 GB+

A router is gates, not if-statements.

6/
Open source, MIT. macOS, terminal install, rough edges documented.

https://github.com/mattdani21/all-subs

---

## Short variant

Most AI products jump straight to generation.

All Subs is a router with three rungs:

1. retrieve — existing subtitles, 8 seconds
2. generate — whisper + LLM, 17 minutes
3. local — 4B model, nothing leaves your Mac

Each rung has a gate that decides if its answer is trustworthy. Routing is the feature.

MIT, link below.

---

## Notes

- Attach `docs/hero.png`. It shows the *retrieved* track, which fits rung 1.
- "22 minutes past the credits" is the most quotable line — spin it into its own follow-up
  post if the launch gets any traction.
- Don't claim real-time, DRM, or "any site"; the README lists the limits.
- Post LinkedIn Tue–Thu 08:00–09:30 SAST; X thread 15:00–17:00 SAST.
