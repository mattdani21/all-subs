# Launch copy

Repo: https://github.com/mattdani21/all-subs
Hero image: `docs/hero.png` (attach it — posts with an image get far more reach)

---

## LinkedIn

Chinese films on bilibili often ship with no subtitle track at all. I wanted to watch one,
so I built the thing I wanted: a Chrome extension that captions any video.

How it works:

1. It looks for existing subtitles first. Title + year → Wikidata → IMDb id → subtitle
   library, with a timing gate that rejects tracks which don't span the film. On the
   116-minute test film that path returns 1,072 cues in about 8 seconds.
2. Only if nothing usable exists does it transcribe. whisper.cpp on the Mac, 5-minute
   chunks, hallucination filtering, then an LLM translates each cue while the next chunk
   is still being transcribed.
3. An optional "deep pass" makes the model read the whole film first — synopsis, character
   names, register — then re-translate every line with that context.

Things I didn't expect to spend time on:

- Whisper confidently repeating "Thank you" over a film score. The fix was disabling
  cross-window conditioning, not a bigger model.
- Subtitle libraries happily returning the wrong film. My first IMDb guess gave a heist
  movie's subtitles on a 116-minute film; the last line landed 22 minutes after the credits.
  The duration gate now rejects that automatically.
- An HTTPS page cannot fetch http://127.0.0.1. Every API call goes through the extension's
  service worker instead.

Measured honestly: the library path is ~8 seconds, full transcription is 11–17 minutes on
an M3, and whisper is 94–97% of that time. Greedy decoding, quantised models and parallel
chunks all changed nothing. The only real speed-up was not transcribing.

It's open source (MIT). It still needs a Mac and a terminal to install, which is the next
thing to fix.

Repo: https://github.com/mattdani21/all-subs

If you watch foreign films, I'd love to know what breaks.

---

## X / Twitter thread

1/
I wanted to watch a Chinese film with no subtitles.
So I built a Chrome extension that captions any video — finds existing subs first,
otherwise transcribes and translates locally.
Open source, MIT.

https://github.com/mattdani21/all-subs

2/
The fastest caption is one that already exists.

Title + year → Wikidata → IMDb → subtitle library returned 1,072 cues in 8 seconds.
Full ASR of the same film: 17 minutes.

So the pipeline searches before it generates.

3/
When it does transcribe:
• whisper.cpp large-v3-turbo, 5-minute chunks
• -mc 0, because prompt conditioning made it loop "Thank you" over music
• cue text goes to DeepSeek, audio never leaves the Mac

4/
The safety detail that mattered most:

Subtitle libraries return the wrong release all the time. My first IMDb guess gave a heist
film's subs whose last line landed 22 minutes after the credits.

Gate: a track must span 70–105% of the runtime, or it's rejected and we transcribe.

5/
Rough edges, honestly:
• macOS + terminal install
• whisper is 94% of runtime
• YouTube blocks yt-dlp

Next: signed Mac app so installing isn't a command line.

https://github.com/mattdani21/all-subs

---

## Notes

- Post LinkedIn Tue–Thu, 08:00–09:30 SAST; X threads do better around 15:00–17:00 SAST.
- Attach `docs/hero.png`, not the diagram, as the first image.
- Don't claim real-time or Netflix support; the post above doesn't.
- If someone asks "why not just use X", the answer is in the README: library first, local
  ASR fallback, whole-film context pass.
