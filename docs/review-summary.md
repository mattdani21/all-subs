# Review synthesis — DeepSeek V4 Pro + GPT-6.1 Sol

Two independent frontier reviews of the same brief and code pack (Nov 2026). Raw memos:
`review-deepseek.md`, `review-gpt61.md`.

## Verdict (both agree)

Worth polishing into a **reproducible Mac-first subtitle-recovery tool** — not a universal
captioning platform. Reputation comes from a stranger installing it, recovering captions,
seeing which route ran, and being able to correct a bad result. No new inference modes.

## Verified claims (checked in code, not just asserted by a reviewer)

1. **The four-rung ladder is not automatic.** `_run_job` only takes the cloud path when
   `job.asr == "cloud"`; local ASR is a mode, not a fallback from cloud failure. The README
   and landing page describe automatic fallthrough. [verified]
2. **A subtitle branch can finish with zero cues.** Both native and library paths parse,
   translate, `add_cues`, then set `status="done"` — no non-empty/usability check, so an
   unusable track ends as "Captions ready" with nothing to show. [verified]
3. **"Only cue text leaves the machine" is false in cloud mode**, which uploads audio. The
   README states it without qualification. [verified]
4. **`Check sync` can reuse one cue for several matches.** Each recognised segment picks the
   nearest cue within 8 s independently, so `matches` is not independent evidence and the
   ±8 s window cannot see a large offset. [verified]

## Where the reviewers disagree

| Topic | DeepSeek V4 Pro | GPT-6.1 Sol | Resolution |
|---|---|---|---|
| Sync checking | Auto-run alignment on same-language tracks | Don't market it as release matching; matcher reuses cues; add manual controls | Fix matcher to one-to-one, keep it opt-in, add manual offset/reset |
| Cloud rung | Make it explicitly optional | It isn't a ladder at all — describe the real modes | Fix the description first; consent for cloud spend |
| Fully-local rung | Cut | Demote to experimental | Demote and remove from the headline |

## Ranked actions (owner-tagged)

1. **Truth pass** (~0.5 day, you): README + landing page — route modes as they are, route-specific
   data disclosure, "tested on" instead of "any video", and no "Captions ready" with zero cues.
2. **Retrieval-first install** (~1–2 days): `setup` installs the engine only; whisper model on
   demand with progress and integrity check. The 1.6 GB download should not gate the 8-second route.
3. **Demo + CI gate** (~1–2 days): rights-cleared fixture, `./allsubs demo`, Playwright in
   GitHub Actions with a badge; compatibility table with untested cells left blank.
4. **Engine trust boundary** (~1–2 days): generated bearer token paired with the extension,
   route/method/size limits, bounded jobs and subprocess time, keys out of diagnostics.
5. **Recovery controls** (~1–2 days): wrong film / try another source / generate instead,
   import SRT, reversible offset with reset, retry from an explicit route.
6. **Sync matcher fix** (~0.5 day): one-to-one matching, and optionally a two-parameter fit
   (`t' = α·t + Δ`) for PAL/NTSC drift.

## Cut

Fully-local Qwen3-4B from the headline, the deep pass from the primary UI until it has a
measured quality delta, `ALLSUBS_YOUTUBE_COOKIES`, and `handoff`.

## The three hostile objections to pre-empt

1. "Your privacy story contradicts your implementation." → route-specific disclosure + cloud consent.
2. "One film marketed as universal." → bounded compatibility matrix, reproducible demo, "tested on".
3. "You call a track safe because its runtime is roughly right." → provenance + uncertainty,
   manual reject/regenerate, published failure examples.
