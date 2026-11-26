# Chrome Web Store Listing — All Subs

> Last Updated: 2026-11-25

## Store Listing

**Extension Name**
All Subs

**Short Description**
AI captions for web video: checks existing subtitle tracks first, then transcribes and translates when none exist.

**Detailed Description**
All Subs adds synchronized, bilingual subtitles to web videos that lack captions in your language.

Instead of blindly running speech recognition on every video, All Subs checks for existing subtitles first (YouTube tracks, site-native tracks, and public subtitle libraries checked for runtime fit) and only falls back to AI transcription and translation when no usable track exists.

Key features:
- Existing subtitles first: recovers YouTube, native, or library subtitle tracks in seconds whenever a valid track exists
- Local-first AI fallback: connects to your local All Subs engine on macOS so audio stays on your computer while only caption text is translated
- Opt-in cloud mode: faster audio-to-subtitle translation when you choose Cloud mode
- Bilingual display: view original-language captions above the translation with automatic sizing that never clashes with site styling
- Timing tools: nudge subtitles in 0.1 s steps (remembered per site), reset with one click, or run Check sync to align tracks automatically
- Transparent provenance: always shows whether captions came from YouTube, the site, a subtitle library, or AI, with a one-click "Use AI instead" override
- Export: download any generated track as WebVTT (.vtt)

How to use:
1. Install and start the free, open-source All Subs local engine on your Mac (see the project homepage for two-command setup).
2. Open Settings in the extension to add your own translation or subtitle-library API keys.
3. Open a web video and press Alt+Shift+A (or click the AS button on the player) to load captions.

Privacy note:
All Subs has no hosted servers, no accounts, and no analytics. Your preferences sync through your browser profile, and caption requests go strictly to your local engine at 127.0.0.1:8765. Any third-party API calls are made directly by your local engine using your own API keys, and audio only leaves your device if you explicitly select Cloud mode.

Support & source code (MIT license):
https://github.com/mattdani21/all-subs/issues

**Category**
Accessibility

**Single Purpose**
Displays synchronized bilingual subtitles over web video players by communicating with a user-run local caption engine.

**Primary Language**
English

## Graphics & Assets

| Asset | Dimensions | Status | Filename |
|-------|-----------|--------|----------|
| Store Icon | 128×128 PNG | ✅ Ready | `extension/icons/icon-128.png` |
| Toolbar Icons | 16/32/48 PNG | ✅ Ready | `extension/icons/icon-{16,32,48}.png` |
| Screenshot 1 | 1280×800 | 🟡 Resize `docs/panel.png` (1360×860) to 1280×800 | `docs/panel.png` |
| Screenshot 2 | 1280×800 | 🟡 Capture 1280×800 bilingual overlay screenshot | `docs/hero.png` |
| Small Promo Tile | 440×280 | ⬜ Not created | |

### Screenshot Notes
- Screenshot 1: Show the video player with bilingual subtitles rendered cleanly and the compact All Subs control panel open showing route provenance.
- Screenshot 2: Show the Settings page with local engine health indicators and privacy-first key storage.

## Permissions Justification

| Permission | Type | Justification |
|------------|------|---------------|
| `storage` | permissions | Stores user subtitle preferences (target language, bilingual toggle, mode choice, and per-site timing offsets) so settings persist across browsing sessions. |
| `activeTab` | permissions | Allows the toolbar popup and keyboard shortcut (`Alt+Shift+A`) to open the caption panel on the currently active video tab when triggered by the user. |
| `http://127.0.0.1:8765/*` | host_permissions | Communicates with the user's locally running All Subs caption engine on loopback port 8765 to request subtitle jobs, poll progress, and fetch WebVTT cues from HTTPS video pages. |
| `http://localhost:8765/*` | host_permissions | Same local loopback engine communication when the user configures `localhost` instead of `127.0.0.1`. |
| `<all_urls>` (content script) | content_scripts | Detects HTML5 `<video>` players across diverse video hosts and embedded players so the user can display synchronized subtitles on any non-DRM video page they visit. |

## Privacy & Data Use

### Data Collection

**Does the extension collect user data?** Yes (settings synced via browser profile; current video page URL/title sent to the user's own local engine on `127.0.0.1:8765` only when the user opens the panel or clicks "Caption this video").

| Data Type | Collected? | Transmitted Off-Device? | Purpose | Shared with Third Parties? |
|-----------|-----------|------------------------|---------|---------------------------|
| Personally identifiable info | No | No | — | No |
| Health info | No | No | — | No |
| Financial info | No | No | — | No |
| Authentication info | No | No | — | No |
| Personal communications | No | No | — | No |
| Location | No | No | — | No |
| Web history | No | No | — | No |
| User activity | Yes (preferences only) | Yes (via browser profile sync) | Persist caption language, bilingual display, and mode preferences | No |
| Website content | Yes (active video page URL, title, and stream URL when user initiates captioning) | No (sent only to user's local `127.0.0.1` engine) | Fetch or generate synchronized subtitles for the active video | No |

### Data Use Certification
- [x] Data is NOT sold to third parties
- [x] Data is NOT used for purposes unrelated to the extension's core functionality
- [x] Data is NOT used for creditworthiness or lending purposes

## Privacy Policy

**Privacy Policy URL**
https://mattdani21.github.io/all-subs/#privacy (or `https://github.com/mattdani21/all-subs#what-leaves-your-machine`)

## Distribution

**Visibility**: Public
**Regions**: All regions

## Developer Info

**Publisher Name**: Matt (`mattdani21`)
**Contact Email**: *(fill in developer dashboard contact email before submission)*
**Support URL**: https://github.com/mattdani21/all-subs/issues
**Homepage URL**: https://github.com/mattdani21/all-subs

## Version History

| Version | Date | Changes | Status |
|---------|------|---------|--------|
| 0.4.0 | 2026-11-25 | Added crisp PNG extension icons (16/32/48/128), zero-idle-CPU overlay rendering, event-driven video discovery, per-site offset reset, OpenRouter key configuration in Settings, and standalone CWS ZIP build (`./allsubs package`). | Draft |
| 0.3.1 | 2026-11-16 | Added subtitle provenance display and "Use AI instead" override. | Unpacked only |
| 0.3.0 | 2026-11-15 | Added Check sync, per-site offsets, Cloud mode toggle, and YouTube native captions. | Unpacked only |
