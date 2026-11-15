Verdict

[D] Worth polishing into a reproducible, Mac-first subtitle-recovery tool—not into a universal captioning platform. The strongest demonstration would be a stranger installing it, recovering useful captions, understanding which route ran, and correcting a bad result. [E] The supplied measurements establish feasibility on one film and one machine; they do not establish general reliability. [D] For reputation, a narrow claim supported by reproducible evidence is worth more than additional inference modes.

[E] This review has the README and selected implementation excerpts, not the complete request handler, setup script, extension manifest, provider gates, or job lifecycle. [D] Where those details matter, the findings below are verification requirements rather than claims that safeguards are absent.

1. Top five changes, ranked by expected quality gained per hour

[A] Effort estimates below assume the current implementation is reasonably factored. They are estimates, not measured implementation times. [D] The security item is a public-release prerequisite regardless of its ranking.

1) Make route selection and success conditions truthful

[A] Effort: roughly one day.

[E] Both shown subtitle branches parse or obtain cues, publish them, and mark the job done without a visible post-parse usability check. [D] An empty or unusable native track could therefore prevent the fallback that is the project’s central promise.

[E] The shown cloud path runs only when job.asr == "cloud" and cloud_asr.available(); it is not visibly an automatic cloud-before-local ladder. [E] The README describes automatic fallthrough through four rungs. [D] Either implement that policy explicitly or describe the actual selectable modes.

Build:

- [D] A shared candidate validator: nonempty text, finite timestamps, positive durations, valid ordering, and a recorded language/provenance result. Keep runtime coverage separate from synchronization confidence.
- [D] Explicit route outcomes: accepted, rejected, unavailable, failed. Preserve the reason when moving to another route.
- [D] Treat “no usable cues” as a failed candidate, not a completed job.
- [D] Make cloud use an explicit, consented policy choice; do not interpret a missing subtitle track as permission to spend API credit.
- [D] Return a small route trace to the panel: “native empty → library rejected → local ASR running.”

[D] Unlocks: failures become explainable, and the README’s central routing claim becomes testable. Acceptance: an empty native track reaches the next permitted route; no usable final cues never produces “Captions ready.”

2) Remove the model download from the default installation

[A] Effort: one to two days for a retrieval-first setup path and an extension-guided connection check—not a packaged application.

[E] The quick start installs the speech stack and a large speech model before the user has demonstrated any need for ASR. [D] This makes the most expensive fallback a prerequisite for the cheapest successful route.

Build:

- [D] A minimal engine installation for retrieval and native-track handling; install ASR dependencies and the model only when that route is requested.
- [D] A capability endpoint that reports engine version, available routes, missing dependencies, and actionable errors without returning secrets.
- [D] An extension welcome screen that checks the engine, explains the permitted routes, and opens the relevant setup instructions.
- [D] A model-install operation with visible progress, integrity verification, cancellation, and a safe retry.
- [D] A rights-cleared local sample page for the first success, independent of a streaming site or paid provider.

[D] Unlocks: a stranger can test the extension–engine connection and overlay without first committing to a large model download. [A] This is likely a better initial return than building a notarised application around an unproven first-run flow.

3) Turn the local-player harness into a release gate

[A] Effort: one to two days for a bounded initial suite; broader real-film validation remains ongoing.

[E] A Playwright local-player harness already exists, but there is no automated end-to-end suite. [D] Extend that asset rather than starting with a large compatibility campaign.

Build a small, rights-cleared fixture set covering:

- [D] A valid track, an empty track, and a malformed track.
- [D] A wrong-release track with plausible total duration.
- [D] Speech, music, silence, and sparse dialogue.
- [D] Engine unavailable, provider failure, and interrupted processing.
- [D] Seeking, reloading, switching videos, and duplicate requests.

[D] Stub provider responses for deterministic routing tests, but label those tests as integration tests with stubs—not proof of live transcription quality. Add a separate real-engine smoke test and a small human-reviewed quality set.

[D] Publish a compatibility table with exact tested machine, browser, source type, language pair, route, and result. Leave untested cells unclaimed.

[D] Unlocks: changes stop silently breaking the working demonstration, and reviewers can distinguish tested behavior from aspiration. Acceptance: one command runs the deterministic suite and produces an actual pass/fail result.

4) Establish the local engine’s trust boundary

[A] Effort: roughly one to two days if the safeguards are not already present; their current state is unclear from the excerpts.

[E] The engine accepts work through localhost HTTP, and content scripts can request API calls through the extension background proxy. [D] Binding to 127.0.0.1 limits network exposure; it does not by itself establish that a request is authorised.

Build or verify:

- [D] Pair the extension with the engine using a generated credential stored in extension-owned configuration, not page-accessible state.
- [D] Restrict proxy routes, HTTP methods, request sizes, and accepted URL schemes. Authenticate every sensitive endpoint; CORS alone is not authorisation.
- [D] Validate redirects and destination addresses for downloader requests. Document any deliberate exception for local media.
- [D] Bound queued jobs, active inference work, subprocess duration, and disk retention.
- [D] Exclude keys, cookies, signed media URLs, and transcript contents from default diagnostics.
- [D] Rotate the disclosed development key if it has not already been rotated; tightening file permissions does not revoke an exposed credential.

[D] Unlocks: a defensible answer to “What can an untrusted webpage make this local process do?” Acceptance: unauthorised requests cannot start work, spend credit, read configuration, or modify settings.

5) Add recovery controls before more automation

[A] Effort: one to two days for the initial controls.

[E] Library tracks can come from other releases, and “Check sync” is limited to matching recognisable same-language text. [D] Users need an escape hatch when the automated decision is wrong.

Build:

- [D] “Wrong film/release,” “Try another source,” and “Generate instead.”
- [D] Import a local SRT/VTT file.
- [D] A reversible manual subtitle offset with reset.
- [D] Cancel and retry from an explicit route, without allowing a rejected cached result to win again.
- [D] Show source, track language, translation mode, and the actual rejection/error reason.

[D] Unlocks: a recoverable bad match stops looking like a broken product. Cross-tab polish is less valuable than recovering the captions in the tab already open.

2. Distribution: choose a sequence, not one permanent package

[D] Recommended sequence: bounded developer preview now; retrieval-first installation next; signed/notarised Mac companion plus a separately distributed extension after clean-machine validation. Consider Chrome Web Store distribution for the extension once its permissions and behavior are stable. Do not build a hosted service for this goal.

Unpacked extension + local engine

[E] This is the current distribution. [D] Keep it as the contributor/debugging path and label it honestly as a developer preview.

[A] Effort is lowest; adoption friction remains highest. [D] Its credibility comes from accurate instructions and reproducible results, not from pretending it is consumer-ready.

Signed/notarised Mac companion

[D] This is the best fit for a deliberately Mac-first, local-processing product: engine lifecycle, dependency management, model installation, logs, and updates can have one owner.

[A] Expect several days to multiple weeks for a dependable package, depending on dependency bundling and release experience. [D] Ongoing risks include updater maintenance, binary provenance, model redistribution terms, and supporting the packaged dependencies.

[D] It does not distribute the Chrome extension by itself. Avoid turning the entire product into a mandatory large download; keep models optional.

Chrome Web Store + native-messaging host

[D] These solve different problems: the store distributes the extension; native messaging changes how it talks to a companion. The native host still needs installation.

[A] Effort is several days to weeks beyond a stable companion, with ongoing browser-integration and release work. [D] Native messaging can narrow the exposed browser-to-engine interface, but it does not replace URL validation, queue limits, or safe subprocess handling.

[D] Do not make this architectural migration a prerequisite for proving that strangers can use the product.

Hosted service

[D] This adds account/abuse controls, operating costs, media-upload privacy, retention decisions, and service availability to a project whose stated goal is reputation rather than revenue. [A] It is the highest ongoing burden of these options.

[D] It also changes the trust proposition substantially. Reject it unless evidence later shows that local installation—not caption quality or source access—is the dominant obstacle.

3. Architecture: keep Python and localhost, constrain the boundary

[D] The current shape is appropriate for this stage. A local engine can own downloader and inference subprocesses independently of the overlay. Moving inference into the extension would be a new implementation effort, not simply a packaging improvement.

[D] WASM/WebGPU should be a separate experiment with an explicit acceptance test on the target hardware. Nothing supplied establishes comparable model support, speed, memory use, or caption quality in that environment.

[D] A native-messaging adapter can be added later without rewriting the inference pipeline. Separate the job API from its HTTP transport now.

What breaks first:

- [E] The server is threaded and processing launches additional download work. [D] If admission control is absent, concurrent tabs can compete for memory, compute, network, and disk. The excerpts do not establish current limits.
- [E] Jobs are described as cached by URL and language. [D] If that is the complete identity, changed media at the same URL or changed generation settings can reuse the wrong result. Verify the implementation; include stable media identity and result-affecting settings where appropriate.
- [D] Across more users, source extraction differences, credentials, and release mismatches are more immediate risks than scaling a shared server: each user runs their own engine.

[E] In the shown cloud branch, prefix fetching is skipped and the code waits for the full download before preparing chunks. [D] Improving that path’s time to first useful caption may matter more than substituting a faster model. The snippet does not establish that later cloud processing streams around this bottleneck.

4. Speech translation: benchmark a replacement, do not assume one

[E] The cloud mode already represents the proposed end-to-end shape at the application level: audio goes in and translated cues come back. [D] The question is therefore which implementation produces better usable subtitles—not whether two stages are intrinsically worse.

Quality

[D] A direct speech-translation model could avoid propagating some transcription errors, but it can also make source errors harder to inspect and repair. Separate ASR and translation preserve a source transcript for debugging, retranslating, and same-language alignment.

[E] No comparative subtitle-quality evaluation is supplied. [D] There is no basis here to claim a material quality advantage for either approach.

Latency

[E] The measured local path spends 94–97% of wall time in ASR. [D] Removing the relatively small translation stage cannot remove the dominant delay. A replacement must make speech processing faster or produce useful cues earlier while retaining acceptable timing and meaning.

Cost

[E] The cloud estimate is about $0.30 per film on the supplied test. [D] That is not a general cost guarantee, and the supplied text does not establish a complete cost comparison against the separate pipeline.

[D] Compare candidates on the same clips: meaning preservation, omissions/hallucinations, cue timing, time to first useful caption, total completion time, and actual billed cost. Keep the two-stage path until a replacement wins on the outcomes that matter.

5. What to cut or demote

- [D] Demote fully local translation to an experimental/offline option. [E] The supplied measurements show slower translation and visible quality loss, with memory constraints. [D] It should not complicate the default onboarding.
- [D] Remove the deep pass from the primary interface until it demonstrates a quality improvement on a fixed evaluation set. [E] Its execution time is measured; its benefit is not quantified here.
- [D] Cut “any video” as the headline claim. [E] DRM is excluded and some no-caption YouTube downloads fail. [D] Describe supported source types and known exceptions instead.
- [D] Do not prioritise Windows/Linux packaging, hosted accounts, or cross-tab polish before the Mac acceptance path works.
- [D] Do not market “Check sync” as general release matching. [E] Its matcher only considers cues within eight seconds of recognised segment starts, and can reuse a cue for multiple matches. [D] Match count alone therefore does not establish independent evidence or correction of large offsets, drift, or edits.

6. Where the owner’s assumptions are wrong

“Coverage is a sync gate.”

[D] Runtime coverage can reject obviously incomplete or overlong tracks; it cannot establish that dialogue aligns throughout the film. Keep coverage, identity, and synchronization as separate confidence checks.

“The speech-rate filter identifies music hallucinations.”

[E] The filter rejects low character-rate segments using fixed duration thresholds. [D] This can also reject a genuine short utterance inside an overlong ASR segment. It is a heuristic trading false positives against false negatives, not a language-independent proof that speech is absent.

“Only cue text leaves the machine.”

[E] The README says this, while cloud mode sends audio and library lookup uses title-based external services. [D] Replace it with route-specific disclosure, including what warming the panel sends or downloads before the caption button is pressed.

“Fully local means offline.”

[E] The shown local-translator condition skips library lookup, but native probing and downloads still precede ASR. [D] Distinguish “local inference” from “no network access”; the latter is not established.

“Packaging makes it production-ready.”

[D] Packaging removes installation work. It does not make a wrong track correct, an empty result successful, or an unauthorised local request safe.

7. The three objections a hostile reviewer would lead with

1) “Your privacy story contradicts your implementation.”

[E] The blanket text-only disclosure conflicts with the described audio-upload route. [D] Cheapest honest pre-emption: fix the wording immediately, show route-specific data disclosure, and require explicit cloud consent. Audit the localhost authorisation boundary before recommending broad installation.

2) “This is a one-film demo marketed as universal.”

[E] End-to-end validation is concentrated on one film. [D] Cheapest honest pre-emption: publish a bounded compatibility matrix, a rights-cleared reproducible demo, and deterministic fallback tests. Say “tested on” rather than “works on.”

3) “You call a track safe because it has roughly the right runtime.”

[E] Release mismatch is known, the speech filter is heuristic, and the alignment routine has a bounded matching neighborhood. [D] Cheapest honest pre-emption: expose provenance and uncertainty, provide manual offset/reject/regenerate controls, and publish failed examples alongside successful ones.

[D] The next release should prove a bounded path from clean installation to useful, recoverable captions. Another model or another mode would be a weaker reputation investment.
