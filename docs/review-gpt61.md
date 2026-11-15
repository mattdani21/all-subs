[D] Yes—polish it into a narrowly supported, reproducible macOS caption tool, not a universal caption platform. For reputation, the strongest release is one a stranger can install, understand and recover when it fails. The immediate blockers are not another ASR speedup or a larger panel: I found job-lifecycle failures, inconsistent privacy enforcement and timing bugs beneath the advertised gates. Do not make a broad adoption push before fixing those.

Review basis

[E] Reviewed public commit 9a11ee94346633a1e6e3f9ba325510d3d4716378. Eight unit tests passed. I also ran isolated HTTP, job-runner, browser-message and timing probes against the actual source. No repository files were changed.

[E] These were focused reproductions, not a clean-machine installation or another full-film validation. The film timings in the README remain author-reported measurements, not independently reproduced benchmarks. The browser E2E script is a live-site screenshot/inspection script with no assertions, rather than a regression suite that establishes successful captioning. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/README.md))

Evidence labels: [E] inspected source or reproduced behavior; [D] conclusion or recommendation; [A] unverified assumption or effort estimate. All effort estimates below assume the author implements the change and exclude cross-platform support.

1. Top five changes, ranked by practical return per hour

1) Make retrieval-only use a legitimate successful installation

[A] Effort: roughly one day for the CLI/settings repair; another day for a small onboarding screen.

[E] Setup currently downloads the speech model and treats a missing DeepSeek key as failure. Doctor does not recognise keys saved through the extension’s config mechanism. Settings offers a backend URL, but the background proxy always uses port 8765. These are inconsistencies in the supported path, not merely terminal friction. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/allsubs))

[D] Build a capability-based setup flow:

    Existing subtitles: available / provider key missing.
    Local transcription: binary missing / model missing / ready.
    Translation: unconfigured / configured / last request failed.
    Cloud audio: disabled / explicitly authorised / configured.

[D] Do not require a speech model or translation key to demonstrate retrieval. Download the model only when the user enables local transcription. Use a project venv rather than modifying system Python packages. Give CLI and UI one setup-state implementation.

[E] Model downloads currently write directly to their final filenames; subsequent setup accepts any nonempty file. An interrupted download can therefore be mistaken for an installed model. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/allsubs))

[D] Download to .part, verify a pinned checksum, then rename atomically. The acceptance test is an interrupted installation followed by a successful rerun—not just a successful first download.

[D] Unlock: the lowest-cost caption path also becomes the lowest-cost installation path.

2) Make every job finish, fail or cancel—never silently hang

[A] Effort: one to two days including regression tests.

[E] A translation-worker exception leaves queue items unfinished while the runner waits indefinitely. I reproduced this using the real missing-key path: the job remained active with no reported error. Cancellation also failed a queued-job probe. Cache reuse ignored changed mode and limit. Relevant locations: server.py, translate_worker(), run_job() and get_or_create(). ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/engine/server.py))

[D] Build explicit terminal-state handling:

    Catch worker exceptions and propagate them to the job.
    Call task_done() in finally.
    Bound queue shutdown and subprocess waits.
    Check a cancellation event before work and before publishing results.
    Kill owned subprocesses when cancellation requires it.
    Separate cache identity from the identity of a running attempt.

[D] Include output-affecting options and a pipeline/schema version in cache identity. A short diagnostic run must not become the cached answer for a full-film request.

[E] Settings also reports success after an HTTP error because it does not check res.ok. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/extension/options.js))

[D] Preserve errors, retain unsaved inputs and provide a retry action. Test missing credentials, malformed translation JSON, timeout, cancellation and engine restart without using paid APIs.

[D] Unlock: strangers encounter understandable failure instead of an apparently broken product.

3) Establish a real trust boundary before distributing it further

[A] Effort: one to two days for the immediate boundary and policy fixes; broader security hardening is additional work.

[E] The engine accepts unauthenticated requests with wildcard CORS. An isolated request using a foreign Origin, foreign Host and text/plain successfully changed dummy configuration. Direct website-to-loopback browser reachability was not established. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/engine/server.py))

[E] A separate browser probe found a more concrete extension-side route: page JavaScript could access the open shadow-root controls and synthetically select Cloud and start captioning. The actual content script emitted a cloud-job message; the runtime/backend was mocked, so no audio upload or charge occurred. The relevant controls have no trusted-event check. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/extension/content.js))

[D] Build:

    An installation-scoped pairing token held by extension-owned code.
    Host/Origin validation, strict JSON handling and request-size limits.
    A constrained API-operation allowlist in the background proxy.
    Cloud authorisation in an extension-owned popup/options page.
    Trusted-event checks on privileged in-page actions.
    Escaping of remote metadata in the engine dashboard.

[D] A closed shadow root is defence in depth, not authorisation. Likewise, an authenticated engine does not protect against an authorised extension being tricked into issuing a request.

[E] Offline-selected native-caption translation still reaches the default cloud translator. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/engine/server.py))

[D] Centralise translation routing and enforce a “no external inference” policy across every branch. If strict offline means no network at all, separately disable metadata/provider prefetching. Test that policy by making forbidden network calls fail the test.

[D] Unlock: you can make privacy statements without depending on which branch happened to execute.

4) Fix media identity and temporal correctness before improving translation

[A] Effort: one to two days for the defects below and focused tests.

[E] Replacing the video element preserves the previous job and cues. The overlay’s empty-cue path can leave the previous caption visible. These create wrong-video and stale-caption failures independently of model quality. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/extension/content.js))

[D] Introduce a media-generation identifier. On navigation or source replacement, reset overlay/job state and reject asynchronous responses from the old generation. Test both replacement elements and changing currentSrc on the same element.

[E] In the local pipeline, chunk offsets are added before snap_to_onsets() inspects chunk-local audio. My synthetic probe moved a relative cue correctly but did not apply the equivalent correction after its absolute offset. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/engine/server.py))

[D] Snap in chunk coordinates, then add the offset. Make that invariant explicit in function names and tests.

[E] The Latin-text matcher removes whitespace before extracting words. Consequently, ordinary sentences become single concatenated tokens. My probe returned zero similarity for “hello there my friend” versus the same sentence with “today” appended. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/engine/captions.py))

[D] Tokenise before destructive normalisation. Require distinct matches across multiple sample windows before applying a shift. Scope manual offsets to a video/track, not a hostname.

[D] Unlock: improvements to the caption model are no longer obscured by deterministic playback bugs.

5) Ship a reproducible demonstration and a small assertion-based suite

[A] Effort: one to two days for the first useful version; independent installer testing adds coordination time.

[E] The existing E2E script hardcodes an author-specific checkout/browser path, opens one bilibili URL, prints state and captures screenshots. Missing overlay output is not an assertion failure. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/test/e2e.py))

[D] Build two visibly different demonstrations:

    Retrieval: a legally redistributable clip and known subtitle track.
    Generation: a clip with no track, exercising actual ASR and translation.

[D] Use temporary HOME, profile, cache and engine ports. Assert caption text, timing, source badge, terminal job state, navigation reset, seek-back behavior and error recovery. Mock providers in routine CI; keep opt-in real-provider smoke tests separate.

[D] Add a release checklist with independent clean installations and a published compatibility matrix. Record hardware, versions, cold/warm cache state and failures. A mocked green test proves integration logic; it must never be presented as evidence of model quality.

[D] Unlock: the launch becomes “here is a result you can reproduce,” rather than “here is my screenshot.”

[D] This ranking is return-on-effort, not permission to defer security: recommendations 2 and 3 are public-release gates.

2. Distribution: choose a staged combination, not one exclusive option

[D] Best destination: Chrome Web Store extension plus a signed/notarised Mac companion, with a thin native-messaging bridge. Best next step: repair the source release and validate installation before building that packaging.

Unpacked extension + local engine

[A] Packaging effort after the fixes: hours to a day for a versioned source release and checksums.

[D] Keep it for contributors and the initial technical audience. It gives the best near-term credibility per hour, but should remain explicitly a developer installation—not the promised stranger-friendly experience.

Signed/notarised Mac app

[A] Effort: roughly one to two weeks for a dependable first package, including a bundled runtime, dependency handling, model download/resume, lifecycle and uninstall—not merely wrapping the shell script.

[D] This is the highest-value next distribution investment if nontechnical Mac users actually want the tool. The app should start/stop the engine, show its status and manage models. Do not build an elaborate desktop transcript editor.

Apple lists Developer Program membership at US$99 per year, with regional pricing variations. Notarisation and Developer ID signing are separate distribution work, not a substitute for application testing. ([developer.apple.com](https://developer.apple.com/help/account/membership/program-enrollment?utm_source=openai))

Chrome Web Store + native-messaging host

[A] Effort: several additional days once the companion is packageable; review elapsed time is uncertain.

Chrome native messaging requires an installed host and a host manifest identifying allowed extension origins. The store extension therefore does not eliminate the companion installation. Store publishing also requires developer registration and a one-time fee. ([developer.chrome.com](https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging?authuser=160&utm_source=openai))

[D] This combination has the best eventual adoption story: ordinary extension installation plus an identifiable, managed companion. Use native messaging for commands/status, not as a reason to rewrite inference.

Hosted service

[A] Effort: several weeks for even a responsibly operated version, followed by continuing operational work.

[D] Reject this direction for the stated goal. You would acquire abuse prevention, billing exposure, uploaded-audio privacy, retention and service availability obligations. Moving retrieval server-side would also require revalidating access to streams available in the viewer’s browser.

[D] A static demo and documentation site are worth hosting. A free film-processing backend is not the same investment.

3. Architecture: keep native inference; change the boundary gradually

[D] Localhost HTTP is a reasonable developer architecture. Replacing ThreadingHTTPServer with a framework would not fix the observed defects.

[D] Preserve three boundaries:

    Extension: discover media, obtain consent, render captions.
    Transport: authenticated HTTP now; native messaging later.
    Engine: durable jobs, subprocesses, providers and inference.

[E] The engine has a two-job semaphore, while additional jobs create threads; prefetch/refinement/alignment have separate execution paths. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/engine/server.py))

[D] What breaks first “at scale” is per-machine contention and support variability, not aggregate HTTP traffic. Bound admission, serialise scarce inference resources, limit disk usage and make all expensive operations use the scheduler. More installations do not share one local engine.

[D] Do not move the current workload into MV3’s background worker. Chrome workers can terminate on inactivity and long operations. Browser Whisper implementations exist, but that does not establish equivalent performance or quality for this workload. ([developer.chrome.com](https://developer.chrome.com/docs/extensions/develop/concepts/service-workers/lifecycle))

[D] WASM/WebGPU is a separate experimental backend, not an installation fix you get for free. Tab-audio capture is likewise a separate acquisition strategy: Chrome requires user invocation and introduces capture/audio-routing behavior. It deserves a later experiment if stream fetching proves the dominant compatibility problem. ([developer.chrome.com](https://developer.chrome.com/docs/extensions/reference/api/tabCapture))

4. Pipeline: should speech translation replace ASR → translation?

[D] Not as the next architectural move. Compare complete subtitle systems, not their number of model calls.

[E] You already have an end-to-end cloud path: cloud_asr.py sends audio to a multimodal model and requests translated, timestamped cues. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/engine/cloud_asr.py))

[D] The useful comparison is therefore:

    Existing track, possibly translated.
    Local ASR plus text translation.
    Direct cloud speech translation.
    A candidate direct local speech-translation model.

Quality

[D] Direct translation might avoid propagating a mistaken intermediate transcript, but it can also make omissions harder to inspect. A cascade preserves source text for bilingual display, correction, alignment and retranslation. Neither property proves which output viewers will prefer.

SeamlessM4T provides multilingual direct speech-to-text translation. Its published capabilities are a reason to benchmark it, not evidence that it improves foreign-film subtitles on this Mac. ([ai.meta.com](https://ai.meta.com/research/seamless-communication?utm_source=openai))

Latency

[D] The cascade already overlaps translation with subsequent transcription. Removing translation does not remove the dominant ASR work. Measure first usable dialogue and caption availability at the playback position, not only whole-film completion.

For an English-only experiment, Whisper supports direct speech-to-English translation, but the turbo model is explicitly not trained for that task. Testing it properly requires a different model; adding a translation flag to the current turbo path is not a valid comparison. ([github.com](https://github.com/openai/whisper))

Cost

[D] Direct cloud translation trades local computation for audio-upload inference. Its actual advantage depends on model, chunk size, retries, timestamp repair and quality acceptance. The README’s reported cloud-film cost is not enough to establish that comparison. [E] ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/README.md))

[D] Run a small fixed comparison covering quiet dialogue, music, overlapping speech and multiple languages. Score omissions, meaning errors, terminology consistency, readable segmentation and timestamp error. Keep the cascade unless the alternative wins on the experience you intend to support.

5. Where the owner’s assumptions are wrong

“The four rungs describe what every request does.”

[E] Cloud execution depends on explicit mode selection; availability checks for a key, not usable credit. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/engine/server.py))

[D] Describe a policy-controlled router, not an unconditional cheapest-first ladder. Publish the actual decision rules, including consent and fallbacks.

“Runtime coverage is a sync gate.”

[E] providers.accept() checks cue count and first/last timestamps. It does not establish content identity or local alignment. A synthetic unrelated track passed my runtime-coverage probe. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/engine/providers.py))

[D] Call it a duration-plausibility gate. Separate “candidate found,” “duration plausible” and “sync verified.” Check sync searches only a limited timing neighborhood and applies a constant offset; it is not a general repair for different edits or drift. [E] ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/engine/captions.py))

“The music filter knows this cannot be human speech.”

[E] The speech-rate filter uses raw characters per second with fixed thresholds. Its lang argument does not calibrate those thresholds. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/engine/captions.py))

[D] Sparse text over a long ASR segment can also mean poor segmentation, pauses or sparse dialogue. Treat this as a heuristic with false-negative tests, not a language-independent truth.

“Local means nothing leaves the machine.”

[E] The default local-ASR path can use cloud text translation; the cloud-audio path uploads audio. The current panel and README contain broader privacy wording. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/extension/content.js))

[D] Name the modes by data flow: “local transcription + cloud translation,” “cloud audio,” and “offline inference.” State what leaves before work begins.

6. What to cut

[D] Remove these from the supported release surface:

    Fully local LLM translation: retain experimental code only if wanted.
    The bespoke LAN handoff installer: use one published release path.
    Arbitrary backend URLs: fix loopback pairing rather than supporting remote engines.
    Automatic deep refinement: expose one advanced “Refine translation” action.
    Universal-site and cross-platform implications: publish tested cases instead.

[E] Offline-model installation and discovery currently disagree about checkout paths, and discovery includes an author-specific workspace. The handoff installer also assumes a checkout name different from the README clone path. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/allsubs))

[D] Those are maintenance branches without enough demonstrated user value to justify expanding them now.

[D] Keep retrieval, ordinary local ASR, optional cloud inference, manual timing correction and VTT export. Stop adding providers, model choices and decoder tuning until the supported path is reproducible.

7. The three objections a hostile reviewer should lead with

1) “Your privacy promises are not enforced.”

[E] The offline-routing and synthetic-control probes support this objection; they are not hypothetical concerns about plaintext key storage.

[D] Cheapest honest pre-emption: fix policy enforcement and privileged consent, publish a data-flow table, add no-network regression tests and rotate the previously exposed key. Do not imply that rotation was performed as part of this review.

2) “You have demonstrated a successful film, not a reliable subtitle system.”

[E] The duration gate, timing matcher defects and assertion-free browser script leave that distinction unresolved. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/engine/providers.py))

[D] Cheapest honest pre-emption: publish separate retrieval and generation demonstrations, a small rights-cleared fixture set, measured failures and independent installer reports. Label unsupported cases plainly.

3) “The quickest path still makes me install the expensive fallback first.”

[E] The current setup requirements substantiate this complaint. ([raw.githubusercontent.com](https://raw.githubusercontent.com/mattdani21/all-subs/9a11ee94346633a1e6e3f9ba325510d3d4716378/allsubs))

[D] Cheapest honest pre-emption: retrieval-first setup, deferred model download and a reproducible first-run example. That improves adoption more directly than a new inference architecture.

[D] Bottom line: earn credibility through enforced boundaries, recoverable failures and reproducible results. The next release should demonstrate less breadth and substantially more certainty.
