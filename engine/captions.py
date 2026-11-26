"""All Subs caption pipeline: probe -> native subs or ASR -> LLM translation."""
from __future__ import annotations

import array
import bisect
import concurrent.futures as cf
import hashlib
import http.client
import json
import operator
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import wave

VERSION = "0.4.0"

HOME = os.path.expanduser("~")
ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(ENGINE_DIR)
DATA_DIR = os.path.join(HOME, ".allsubs")
JOBS_DIR = os.path.join(DATA_DIR, "jobs")
CACHE_DIR = os.path.join(DATA_DIR, "cache")

WHISPER_BIN = shutil.which("whisper-cli") or "/opt/homebrew/bin/whisper-cli"
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"
YTDLP = shutil.which("yt-dlp") or os.path.expanduser("~/Library/Python/3.9/bin/yt-dlp")
WHISPER_MODEL = os.path.expanduser("~/.whisper-models/ggml-large-v3-turbo.bin")
WHISPER_THREADS = int(os.environ.get("ALLSUBS_WHISPER_THREADS") or min(8, max(4, os.cpu_count() or 4)))

CHUNK_SECONDS = 300
CUE_MAX_LATIN = 84
CUE_MAX_CJK = 26

TARGET_NAMES = {
    "en": "English", "zh": "Chinese (Simplified)", "ko": "Korean", "ja": "Japanese",
    "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese",
    "ru": "Russian", "ar": "Arabic", "hi": "Hindi", "id": "Indonesian",
}

LANG_PREFERENCE = {
    "en": ["en", "en-US", "en-GB", "eng"],
    "zh": ["zh-Hans", "zh-CN", "zh", "zh-Hant", "zh-TW"],
    "ko": ["ko", "kor"],
    "ja": ["ja", "jpn"],
}

for d in (DATA_DIR, JOBS_DIR, CACHE_DIR):
    os.makedirs(d, exist_ok=True)


# ---------------------------------------------------------------- utilities

CONFIG_PATH = os.path.join(DATA_DIR, "config.json")
_ENV_MTIMES = {}
_ENV_LOCK = threading.Lock()


def load_config():
    if not os.path.exists(CONFIG_PATH):
        return {}
    try:
        with open(CONFIG_PATH) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_config(data):
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, indent=1)
    os.replace(tmp, CONFIG_PATH)
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
    with _ENV_LOCK:
        _ENV_MTIMES.clear()


def load_env(force=False):
    """Pull API keys from .env files, then the runtime config written by the UI."""
    paths = (os.path.join(PROJECT_DIR, ".env"), os.path.join(HOME, ".hermes", ".env"), CONFIG_PATH)
    with _ENV_LOCK:
        if not force:
            changed = False
            for p in paths:
                try:
                    mt = os.path.getmtime(p)
                except OSError:
                    mt = None
                if _ENV_MTIMES.get(p) != mt:
                    changed = True
                    break
            if not changed and _ENV_MTIMES:
                return
        for path in paths[:2]:
            try:
                _ENV_MTIMES[path] = os.path.getmtime(path)
            except OSError:
                _ENV_MTIMES[path] = None
                continue
            try:
                with open(path) as fh:
                    for line in fh:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip('"').strip("'")
                        if k and v and k not in os.environ:
                            os.environ[k] = v
            except OSError:
                pass
        try:
            _ENV_MTIMES[CONFIG_PATH] = os.path.getmtime(CONFIG_PATH)
        except OSError:
            _ENV_MTIMES[CONFIG_PATH] = None
        cfg = load_config()
        for env_name, cfg_name in (("DEEPSEEK_API_KEY", "deepseek_api_key"),
                                   ("WYZIE_API_KEY", "wyzie_api_key"),
                                   ("OPENROUTER_API_KEY", "openrouter_api_key")):
            if cfg.get(cfg_name) and not os.environ.get(env_name):
                os.environ[env_name] = cfg[cfg_name]


def run(cmd, timeout=1800, cwd=None):
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, timeout=timeout, cwd=cwd)
    if proc.returncode != 0:
        raise RuntimeError("%s failed (%s): %s" % (
            os.path.basename(cmd[0]), proc.returncode, (proc.stderr or "")[-800:]))
    return proc


def url_key(url, target):
    return hashlib.sha1(("%s|%s" % (url, target)).encode()).hexdigest()[:12]


def cache_path(key):
    return os.path.join(CACHE_DIR, key + ".json")


def load_cache(key):
    p = cache_path(key)
    if os.path.exists(p):
        try:
            with open(p) as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None
    return None


def save_cache(key, data):
    p = cache_path(key)
    tmp = p + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.replace(tmp, p)


# ---------------------------------------------------------------- probe

def probe(url, cookies=False):
    """Metadata + subtitle inventory without downloading media."""
    cmd = [YTDLP, "-J", "--no-warnings", "--no-playlist"]
    if cookies:
        cmd += ["--cookies-from-browser", "chrome"]
    proc = run(cmd + [url], timeout=300)
    info = json.loads(proc.stdout)
    return {
        "title": info.get("title") or "Untitled",
        "duration": info.get("duration") or 0,
        "webpage_url": info.get("webpage_url") or url,
        "uploader": info.get("uploader") or "",
        "subtitles": info.get("subtitles") or {},
        "automatic_captions": info.get("automatic_captions") or {},
    }


def pick_native_subs(meta, target):
    """Return (lang_code, {label, kind}) for a usable existing track, or None."""
    prefs = LANG_PREFERENCE.get(target, [target]) + ["en"]
    tracks = meta.get("subtitles") or {}
    for code in prefs:
        for have in tracks:
            if have.lower() == code.lower():
                return have, "native"
    return None


def download_native_subs(url, lang, dest_base):
    run([YTDLP, "--no-warnings", "--skip-download", "--write-subs",
         "--sub-langs", lang, "--sub-format", "vtt/srt/best",
         "--convert-subs", "vtt", "-o", dest_base, url], timeout=300)
    for ext in ("vtt", "srt"):
        p = dest_base + "." + lang + "." + ext
        if os.path.exists(p):
            with open(p, encoding="utf-8", errors="replace") as fh:
                return fh.read()
    raise RuntimeError("subtitle download produced no file for %s" % lang)


# ---------------------------------------------------------------- media

def _yt_clients(url):
    """YouTube needs a working player client; the web client now 403s on media."""
    if "youtube.com" in url or "youtu.be" in url:
        return [["--extractor-args", "youtube:player_client=%s" % c]
                for c in ("mweb", "ios", "web")]
    return [[]]


def download_audio_range(url, workdir, seconds=120, timeout=300, cookies=False):
    """Fetch only the opening seconds (yt-dlp sections), for first-caption latency."""
    out = os.path.join(workdir, "prefix.%(ext)s")
    base = [YTDLP, "--no-warnings", "--no-playlist", "-f", "bestaudio/best"]
    if cookies:
        base += ["--cookies-from-browser", "chrome"]
    last = None
    for extra in _yt_clients(url):
        for name in os.listdir(workdir):
            if name.startswith("prefix."):
                try:
                    os.remove(os.path.join(workdir, name))
                except OSError:
                    pass
        try:
            run(base + extra + ["--download-sections", "*0-%d" % int(seconds),
                                "-o", out, url], timeout=timeout)
        except Exception as exc:
            last = exc
            continue
        for name in os.listdir(workdir):
            if name.startswith("prefix."):
                return os.path.join(workdir, name)
        last = RuntimeError("section download produced no file")
    raise last or RuntimeError("section download failed")


def youtube_id(url):
    m = re.search(r"(?:[?&]v=|youtu\.be/|/embed/|/shorts/|/live/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else None


def youtube_cues(url, target="en"):
    """Native/auto captions for a YouTube video, without touching yt-dlp."""
    vid = youtube_id(url)
    if not vid:
        return None
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return None
    langs = [target] if target == "en" else [target, "en"]
    tr = None
    try:
        api = YouTubeTranscriptApi()
        tr = api.fetch(vid, languages=langs)
        snips = list(tr)
    except Exception:
        try:
            snips = YouTubeTranscriptApi.get_transcript(vid, languages=langs)
        except Exception:
            return None
    cues = []
    for item in snips:
        if hasattr(item, "text"):
            text, start, dur = item.text, item.start, item.duration
        else:
            text, start, dur = item.get("text", ""), item.get("start", 0), item.get("duration", 2)
        text = re.sub(r"\s+", " ", text or "").strip()
        if not text:
            continue
        cues.append({"start": round(start, 3), "end": round(start + (dur or 2.0), 3), "src": text})
    if len(cues) < 5:
        return None
    lang = getattr(tr, "language_code", target) or target
    return {"cues": cues, "lang": lang}


def download_audio(url, workdir, key=None, cookies=False):
    media_cache = os.path.join(CACHE_DIR, "media")
    os.makedirs(media_cache, exist_ok=True)
    if key:
        for ext in ("m4a", "mp4", "webm", "opus", "mkv", "mp3"):
            cached = os.path.join(media_cache, key + "." + ext)
            if os.path.exists(cached) and os.path.getsize(cached) > 100000:
                return cached
    out = os.path.join(workdir, "audio.%(ext)s")
    base = [YTDLP, "--no-warnings", "--no-playlist", "-f", "bestaudio/best"]
    if cookies:
        base += ["--cookies-from-browser", "chrome"]
    last = None
    for extra in _yt_clients(url):
        for name in list(os.listdir(workdir)):
            if name.startswith("audio."):
                try:
                    os.remove(os.path.join(workdir, name))
                except OSError:
                    pass
        try:
            run(base + extra + ["-o", out, url], timeout=3600)
        except Exception as exc:
            last = exc
            continue
        for name in os.listdir(workdir):
            if name.startswith("audio."):
                path = os.path.join(workdir, name)
                if key:
                    shutil.copyfile(path, os.path.join(media_cache,
                                                       key + os.path.splitext(name)[1]))
                return path
        last = RuntimeError("audio download produced no file")
    raise last or RuntimeError("audio download failed")


def duration_of(path):
    proc = run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", path], timeout=120)
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def to_wav(src, dst):
    run([FFMPEG, "-y", "-v", "error", "-vn", "-i", src, "-ar", "16000", "-ac", "1",
         "-c:a", "pcm_s16le", dst], timeout=1800)
    return dst


def plan_chunks(total, chunk_seconds=CHUNK_SECONDS, limit=None, schedule=None,
                start_at=0.0, first_index=0):
    """Return [(idx, start, length), ...] without slicing audio yet."""
    if limit:
        total = min(total, float(limit))
    if total <= 0:
        raise RuntimeError("could not read audio duration")
    plan = []
    start = float(start_at)
    idx = first_index
    while start < total - 0.01:
        sched_i = idx - first_index
        want = schedule[sched_i] if schedule and 0 <= sched_i < len(schedule) else chunk_seconds
        length = min(want, total - start)
        plan.append((idx, start, length))
        start += length
        idx += 1
    return plan


def cut_chunk(src, workdir, idx, start, length):
    """Extract one 16 kHz mono PCM chunk via fast input seeking."""
    path = os.path.join(workdir, "chunk_%03d.wav" % idx)
    run([FFMPEG, "-y", "-v", "error", "-ss", str(start), "-t", str(length),
         "-i", src, "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", path],
        timeout=600)
    return path


def split_wav(wav, workdir, chunk_seconds=CHUNK_SECONDS, limit=None, schedule=None,
              start_at=0.0, first_index=0):
    """Split audio into chunks; `schedule` overrides the first sizes."""
    total = duration_of(wav)
    plan = plan_chunks(total, chunk_seconds=chunk_seconds, limit=limit,
                       schedule=schedule, start_at=start_at, first_index=first_index)
    return [(cut_chunk(wav, workdir, idx, start, length), start, length)
            for idx, start, length in plan]


# ---------------------------------------------------------------- ASR

TIME_RE = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def _secs(s):
    h, m, sec, ms = TIME_RE.match(s).groups()
    return int(h) * 3600 + int(m) * 60 + int(sec) + int(ms.ljust(3, "0")[:3]) / 1000.0


def parse_srt(text):
    cues = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [l for l in block.splitlines() if l.strip()]
        if len(lines) < 2:
            continue
        idx = 0
        if re.match(r"^\d+$", lines[0].strip()):
            idx = 1
        if idx >= len(lines) or "-->" not in lines[idx]:
            continue
        a, b = lines[idx].split("-->")
        try:
            start, end = _secs(a.strip()), _secs(b.strip())
        except AttributeError:
            continue
        body = " ".join(l.strip() for l in lines[idx + 1:]).strip()
        body = re.sub(r"<[^>]+>", "", body)
        if body:
            cues.append({"start": round(start, 3), "end": round(max(end, start + 0.4), 3),
                         "src": body})
    return cues


def parse_vtt(text):
    text = re.sub(r"^WEBVTT.*?$", "", text, count=1, flags=re.M)
    return parse_srt(text)


def vtt_timestamp(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d.%03d" % (h, m, s, ms)


def to_vtt(cues):
    lines = ["WEBVTT", ""]
    for c in cues:
        text = (c.get("dst") or "").strip() or (c.get("src") or "").strip()
        if not text:
            continue
        lines.append("%s --> %s" % (vtt_timestamp(c["start"]), vtt_timestamp(c["end"])))
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


def silence_intervals(wav, noise_db=-45, min_dur=4.0):
    """Intervals of near-silence; used to reject ASR hallucinations over quiet audio."""
    proc = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", wav, "-af",
         "silencedetect=noise=%ddB:d=%s" % (noise_db, min_dur), "-f", "null", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=900)
    spans = []
    start = None
    for line in proc.stderr.splitlines():
        m = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        if m:
            start = max(0.0, float(m.group(1)))
        m = re.search(r"silence_end:\s*([\d.]+)", line)
        if m and start is not None:
            spans.append((start, float(m.group(1))))
            start = None
    if start is not None:
        spans.append((start, 1e9))
    return spans


def is_mostly_silent(silences, length, threshold=0.96):
    """True when almost the entire chunk is silence (skip whisper completely)."""
    if not silences or length <= 0:
        return False
    covered = sum(overlap(0.0, length, b, e) for b, e in silences)
    return (covered / length) >= threshold


ARTIFACTS = (
    "thank you", "thanks for watching", "thank you for watching", "please subscribe",
    "subtitles by", "字幕 by", "中文字幕", "字幕志愿者", "请不吝点赞", "订阅", "打赏",
    "谢谢观看", "谢谢收看", "关注", "点赞", "明镜", "点点栏目", "ご視聴ありがとうございました",
    "amara.org", "subtitle", "www.", ".com",
)


def overlap(a0, a1, b0, b1):
    return max(0.0, min(a1, b1) - max(a0, b0))


def _norm(text):
    return re.sub(r"[\s\W_]+", "", text.lower())


def filter_segments(segs, silences, lang=None):
    """Drop ASR hallucinations: silence-backed, artifact, repeated and looping output."""
    if not segs:
        return []
    counts = {}
    for seg in segs:
        counts[_norm(seg["src"])] = counts.get(_norm(seg["src"]), 0) + 1

    out = []
    last = ""
    for seg in segs:
        text = (seg.get("src") or "").strip()
        if not text:
            continue
        key = _norm(text)
        dur = max(seg["end"] - seg["start"], 0.1)
        conf = seg.get("conf", 1.0)
        silent = sum(overlap(seg["start"], seg["end"], b, e) for b, e in silences)
        mid = (seg["start"] + seg["end"]) / 2.0
        mid_silent = any(b <= mid <= e for b, e in silences)

        if conf < 0.40:
            continue
        # Speech rate sanity: a long segment with almost no words is whisper
        # captioning music ("see you in the next video"). 0.4 chars/s over 30 s
        # is not human speech in any language.
        cps = len(text) / dur
        if dur >= 10 and cps < 1.2:
            continue
        if dur >= 6 and cps < 0.8:
            continue
        if silent / dur > 0.6 or (mid_silent and dur > 20):
            continue
        repeats = counts.get(key, 0)
        # Repetition is only evidence of a whisper loop when the audio does not back
        # the words up: a chorus repeating a line is real speech, a hallucination
        # repeating one is usually low-confidence or sitting over silence.
        weak = conf < 0.60 or (silent / dur) > 0.35
        if repeats >= 6:
            continue
        if weak and repeats >= 2 and dur >= 8:
            continue
        if weak and repeats >= (4 if len(key) <= 3 else 3):
            continue
        if any(a in key for a in (_norm(x) for x in ARTIFACTS)):
            if counts.get(key, 0) >= 2 or (lang and not lang.startswith("en")):
                continue
        if key == last and (len(key) <= 3 or silent / dur > 0.5):
            continue
        last = key
        out.append({"start": seg["start"], "end": seg["end"], "src": text})
    return out


def detect_language(wav, total, window_span=None):
    """Language vote on up to three windows; early-exits on unanimous high confidence."""
    span = float(window_span or total or 0)
    votes = {}
    conf = []
    tmp = os.path.join(os.path.dirname(wav), "langprobe.wav")
    try:
        for idx, frac in enumerate((0.25, 0.55, 0.8)):
            start = max(0.0, span * frac - 15.0)
            subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", str(start), "-t", "20",
                            "-i", wav, "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", tmp],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
            proc = subprocess.run([WHISPER_BIN, "-m", WHISPER_MODEL, "-f", tmp, "-dl", "-l", "auto"],
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                  timeout=300)
            blob = (proc.stdout or "") + (proc.stderr or "")
            m = re.search(r"auto-detected language:\s*([a-zA-Z-]+)(?:\s*\(p = ([\d.]+)\))?", blob)
            if m:
                code = m.group(1).lower()
                votes[code] = votes.get(code, 0) + 1
                if m.group(2):
                    conf.append(float(m.group(2)))
            # Early exit: if the first two windows unanimously agree with high confidence,
            # a third whisper-cli launch cannot change the majority vote.
            if idx == 1 and len(votes) == 1 and sum(votes.values()) == 2:
                if conf and (sum(conf) / len(conf)) >= 0.85:
                    break
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
    if not votes:
        return None, 0.0
    code = max(votes.items(), key=lambda kv: kv[1])[0]
    return code, (sum(conf) / len(conf) if conf else 0.0)


def transcribe_chunk(path, base, language="auto"):
    """Run whisper.cpp on one chunk; returns (segments, detected language)."""
    proc = subprocess.run(
        [WHISPER_BIN, "-m", WHISPER_MODEL, "-f", path, "-t", str(WHISPER_THREADS),
         "-l", language, "-mc", "0", "-ojf", "-of", base],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1800)
    if proc.returncode != 0:
        raise RuntimeError("whisper failed: %s" % (proc.stderr or "")[-500:])
    json_path = base + ".json"
    if not os.path.exists(json_path):
        return [], None
    with open(json_path, encoding="utf-8", errors="replace") as fh:
        data = json.load(fh)
    lang = (data.get("result") or {}).get("language")
    segs = []
    for item in data.get("transcription") or []:
        text = (item.get("text") or "").strip()
        if not text:
            continue
        tokens = [t for t in item.get("tokens") or [] if not t.get("text", "").startswith("[")]
        probs = [t.get("p", 1.0) for t in tokens]
        conf = sum(probs) / len(probs) if probs else 1.0
        off = item.get("offsets") or {}
        segs.append({"start": off.get("from", 0) / 1000.0,
                     "end": off.get("to", 0) / 1000.0,
                     "src": text, "conf": conf})
    return segs, lang


def _shingles(text):
    text = re.sub(r"[\s\W_]+", "", text or "").lower()
    if not text:
        return set()
    if any("\u4e00" <= ch <= "\u9fff" for ch in text):
        return {text[i:i + 2] for i in range(len(text) - 1)}
    return set(re.findall(r"[a-z0-9']+", text.lower()))


def text_sim(a, b):
    """Dice similarity on character bigrams (CJK) or word sets (latin)."""
    A, B = _shingles(a), _shingles(b)
    if not A or not B:
        return 0.0
    return 2.0 * len(A & B) / (len(A) + len(B))


def _match_offset(observations, cues, window=30.0, min_sim=0.5):
    """One-to-one greedy matching between recognised speech observations and cues.

    Each observation is `(abs_start_sec, text)`. Each cue is matched at most once
    (highest similarity first) so repeated phrases or loose windows cannot inflate
    the match count. Returns `(diffs, matched_pairs)`.
    """
    if not observations or not cues:
        return [], 0
    ordered = sorted(enumerate(cues), key=lambda pair: pair[1]["start"])
    starts = [c["start"] for _, c in ordered]
    cue_shingles = [_shingles(c.get("src", "") or c.get("dst", "")) for _, c in ordered]

    candidates = []
    for obs_idx, (t, text) in enumerate(observations):
        obs_sh = _shingles(text)
        if not obs_sh:
            continue
        lo = bisect.bisect_left(starts, t - window)
        hi = bisect.bisect_right(starts, t + window)
        for pos in range(lo, hi):
            c_sh = cue_shingles[pos]
            if not c_sh:
                continue
            sc = 2.0 * len(obs_sh & c_sh) / (len(obs_sh) + len(c_sh))
            if sc >= min_sim:
                orig_idx, c = ordered[pos]
                candidates.append((sc, -abs(t - c["start"]), obs_idx, orig_idx, t - c["start"]))

    # Greedy one-to-one assignment: strongest text match first, closest timestamp breaks ties
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    used_obs = set()
    used_cues = set()
    diffs = []
    for _sc, _neg_dt, obs_idx, cue_idx, diff in candidates:
        if obs_idx in used_obs or cue_idx in used_cues:
            continue
        used_obs.add(obs_idx)
        used_cues.add(cue_idx)
        diffs.append(diff)
    return diffs, len(diffs)


def align_by_content(path, cues, total, windows=(0.2, 0.5, 0.8), duration=30):
    """Measure subtitle offset by one-to-one matching recognised speech to cue text.

    Only meaningful when the subtitle language matches the audio; cross-language
    tracks produce almost no matches, and the caller should report that instead
    of shifting anything.
    """
    observations = []
    langs = set()
    tmpdir = os.path.dirname(path)
    for i, frac in enumerate(windows):
        start = max(0.0, total * frac - duration / 2.0)
        if start + duration > total:
            start = max(0.0, total - duration)
        clip = os.path.join(tmpdir, "align_%d.wav" % i)
        base = os.path.join(tmpdir, "align_%d" % i)
        try:
            run([FFMPEG, "-y", "-v", "error", "-ss", str(start), "-t", str(duration),
                 "-i", path, "-vn", "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", clip],
                timeout=300)
            segs, lang = transcribe_chunk(clip, base)
        except Exception:
            continue
        finally:
            for p in (clip, base + ".json"):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except OSError:
                    pass
        if lang:
            langs.add(lang)
        for seg in segs:
            observations.append((seg["start"] + start, seg.get("src", "")))
    diffs, count = _match_offset(observations, cues, window=30.0, min_sim=0.5)
    if count < 6:
        return None, count, None, sorted(langs)
    diffs.sort()
    med = diffs[count // 2]
    mad = sorted(abs(d - med) for d in diffs)[count // 2]
    return round(med, 2), count, round(mad, 2), sorted(langs)


def _block_rms(samples):
    if not samples:
        return 0.0
    # sum(map(mul, ...)) runs the inner multiply-accumulate loop in C instead of Python bytecode.
    return (sum(map(operator.mul, samples, samples)) / len(samples)) ** 0.5


def _wav_frames(path, frame_ms=20):
    with wave.open(path, "rb") as fh:
        rate = fh.getframerate()
        width = fh.getsampwidth()
        raw = fh.readframes(fh.getnframes())
    if width != 2:
        return [], frame_ms / 1000.0
    samples = array.array("h")
    samples.frombytes(raw)
    step = max(1, int(rate * frame_ms / 1000))
    frames = [_block_rms(samples[i:i + step]) for i in range(0, len(samples), step)]
    return frames, frame_ms / 1000.0


def snap_to_onsets(cues, wav_path, max_shift=0.7, frame_ms=20):
    """Move each cue start to the first speech frame near it, killing lead-in slop.

    Reads only sampled frames for the noise floor plus the small window around each cue,
    avoiding full-file Python loops over millions of PCM samples.
    """
    if not cues:
        return cues
    try:
        with wave.open(wav_path, "rb") as fh:
            rate = fh.getframerate()
            width = fh.getsampwidth()
            nframes = fh.getnframes()
            if width != 2 or nframes <= 0 or rate <= 0:
                return cues
            step = max(1, int(rate * frame_ms / 1000))
            step_sec = step / float(rate)

            # Estimate noise floor from ~120 evenly spaced frames across the chunk.
            total_blocks = max(1, nframes // step)
            stride = max(1, total_blocks // 120)
            floor_samples = []
            for b in range(0, total_blocks, stride):
                fh.setpos(b * step)
                raw = fh.readframes(step)
                if len(raw) < 2:
                    break
                buf = array.array("h")
                buf.frombytes(raw)
                floor_samples.append(_block_rms(buf))
            if not floor_samples:
                return cues
            floor_samples.sort()
            floor = floor_samples[int(len(floor_samples) * 0.2)] or 1.0

            for c in cues:
                lo_frame = max(0, int((c["start"] - 0.45) * rate))
                hi_frame = min(nframes, int((c["start"] + max_shift) * rate) + step)
                if hi_frame <= lo_frame:
                    continue
                fh.setpos(lo_frame)
                raw = fh.readframes(hi_frame - lo_frame)
                if len(raw) < 2:
                    continue
                buf = array.array("h")
                buf.frombytes(raw)
                seg = [_block_rms(buf[i:i + step]) for i in range(0, len(buf), step)]
                if not seg:
                    continue
                peak = max(seg)
                thresh = max(floor * 3.0, peak * 0.18)
                base_sec = lo_frame / float(rate)
                for i, v in enumerate(seg):
                    if v >= thresh:
                        t = base_sec + i * step_sec
                        if t > c["start"] + 0.02:
                            c["start"] = round(t, 3)
                        break
                if c["end"] <= c["start"]:
                    c["end"] = round(c["start"] + 0.8, 3)
    except Exception:
        return cues
    return cues


def is_cjk(text):
    return len(re.findall(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", text)) > len(text) * 0.3


def split_display(cues, limit_seconds=None):
    """Break whisper segments into subtitle-sized cues with proportional timing."""
    out = []
    for cue in cues:
        text = cue["src"].strip()
        budget = CUE_MAX_CJK if is_cjk(text) else CUE_MAX_LATIN
        if len(text) <= budget or cue["end"] - cue["start"] < 1.2:
            single = dict(cue)
            if single["end"] - single["start"] > 8.0:
                single["end"] = round(single["start"] + 8.0, 3)
            out.append(single)
            continue
        parts = []
        buf = ""
        for token in re.split(r"(?<=[。！？；，、.!?;,])\s*", text):
            if not token:
                continue
            if len(buf) + len(token) > budget and buf:
                parts.append(buf.strip())
                buf = token
            else:
                buf += token
        if buf.strip():
            parts.append(buf.strip())
        if len(parts) <= 1:
            out.append(dict(cue))
            continue
        span = cue["end"] - cue["start"]
        total_chars = sum(max(len(p), 1) for p in parts)
        t = cue["start"]
        for p in parts:
            share = span * (max(len(p), 1) / total_chars)
            out.append({"start": round(t, 3), "end": round(t + share, 3), "src": p})
            t += share
    # renumber and drop zero-length artefacts
    cleaned = []
    for i, c in enumerate(out):
        if c["end"] - c["start"] < 0.25:
            c["end"] = c["start"] + 0.6
        c["i"] = i
        cleaned.append(c)
    return cleaned


# ---------------------------------------------------------------- LLM

_HTTPS_LOCAL = threading.local()
_MODEL_LOCK = threading.Lock()
_ACTIVE_MODEL = None  # (model_name, disable_thinking) cached once verified for the process
_USAGE_LOCK = threading.Lock()

# Approximate DeepSeek chat/flash list rates ($/1M tokens) for rough job telemetry.
_COST_INPUT_MISS = 0.27 / 1e6
_COST_INPUT_HIT = 0.07 / 1e6
_COST_OUTPUT = 1.10 / 1e6


class AuthError(RuntimeError):
    """Non-retryable API key / permission error."""


def new_usage():
    return {"calls": 0, "prompt_tokens": 0, "cache_hit_tokens": 0,
            "completion_tokens": 0, "estimated_usd": 0.0}


def _record_usage(sink, payload_usage):
    if sink is None or not isinstance(payload_usage, dict):
        return
    prompt = int(payload_usage.get("prompt_tokens") or 0)
    completion = int(payload_usage.get("completion_tokens") or 0)
    hit = int(payload_usage.get("prompt_cache_hit_tokens")
              or (payload_usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
    miss = max(0, prompt - hit)
    cost = miss * _COST_INPUT_MISS + hit * _COST_INPUT_HIT + completion * _COST_OUTPUT
    with _USAGE_LOCK:
        sink["calls"] = sink.get("calls", 0) + 1
        sink["prompt_tokens"] = sink.get("prompt_tokens", 0) + prompt
        sink["cache_hit_tokens"] = sink.get("cache_hit_tokens", 0) + hit
        sink["completion_tokens"] = sink.get("completion_tokens", 0) + completion
        sink["estimated_usd"] = round(sink.get("estimated_usd", 0.0) + cost, 5)


def _post_keepalive(host, path, body_bytes, headers, timeout=180):
    """POST JSON over a thread-local keep-alive HTTPS connection (100% stdlib)."""
    conns = getattr(_HTTPS_LOCAL, "conns", None)
    if conns is None:
        conns = {}
        _HTTPS_LOCAL.conns = conns
    for fresh in (False, True):
        conn = conns.get(host)
        if conn is None or fresh:
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            conn = http.client.HTTPSConnection(host, timeout=timeout)
            conns[host] = conn
        try:
            conn.timeout = timeout
            conn.request("POST", path, body=body_bytes, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            return resp.status, dict(resp.getheaders()), raw
        except (http.client.HTTPException, OSError):
            conns.pop(host, None)
            try:
                conn.close()
            except Exception:
                pass
            if fresh:
                raise


def _parse_json_object(content):
    """Parse JSON object from LLM text, tolerating stray fences/prose."""
    text = (content or "").strip()
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except ValueError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        obj = json.loads(text[start:end + 1])
        if isinstance(obj, dict):
            return obj
    raise ValueError("LLM response was not a JSON object")


def llm_json(system, user, max_tokens=4096, temperature=0.2, retries=3, usage=None):
    """JSON-mode chat call with keep-alive, fail-fast 4xx fallback, and usage tracking."""
    load_env()
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")
    preferred = os.environ.get("ALLSUBS_MODEL", "deepseek-flash")
    with _MODEL_LOCK:
        active = _ACTIVE_MODEL
    if active and (active[0] == preferred or preferred == "deepseek-flash"):
        models = [active]
    else:
        models = [(preferred, True)]
        if preferred != "deepseek-chat":
            models.append(("deepseek-chat", False))

    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + key,
        "Connection": "keep-alive",
    }
    last = None
    for model, no_think in models:
        body = {
            "model": model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "response_format": {"type": "json_object"},
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if no_think:
            body["thinking"] = {"type": "disabled"}
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        for attempt in range(retries):
            try:
                status, resp_headers, raw = _post_keepalive(
                    "api.deepseek.com", "/chat/completions", data, headers, timeout=180)
                if status == 200:
                    payload = json.loads(raw.decode("utf-8", "replace"))
                    _record_usage(usage, payload.get("usage"))
                    content = payload["choices"][0]["message"]["content"]
                    parsed = _parse_json_object(content)
                    with _MODEL_LOCK:
                        globals()["_ACTIVE_MODEL"] = (model, no_think)
                    return parsed
                snippet = raw.decode("utf-8", "replace")[:240]
                if status in (401, 403):
                    raise AuthError("DeepSeek authentication failed (HTTP %d): %s" % (status, snippet))
                if status in (400, 404, 422):
                    # Permanent model/parameter rejection: immediately try fallback model.
                    last = RuntimeError("HTTP %d (%s): %s" % (status, model, snippet))
                    break
                # Transient rate limit or server error: respect Retry-After and back off.
                last = RuntimeError("HTTP %d (%s): %s" % (status, model, snippet))
                retry_after = None
                for hk, hv in resp_headers.items():
                    if hk.lower() == "retry-after":
                        try:
                            retry_after = float(hv)
                        except ValueError:
                            pass
                time.sleep(retry_after if retry_after is not None else (1.2 * (2 ** attempt)))
            except AuthError:
                raise
            except (http.client.HTTPException, OSError, KeyError, ValueError, TimeoutError) as exc:
                last = exc
                time.sleep(1.0 + attempt * 1.5)
    raise RuntimeError("LLM call failed: %s" % last)


TRANSLATE_SYSTEM = (
    "Subtitle translator for films. Translate each keyed line into {target}. "
    "Translate meaning into natural spoken dialogue (not prose); match scene tone; "
    "use glossary names; max 90 chars/line; keep every key, never merge/split/drop; "
    "translate lyrics as lyrics; leave pure noise empty. "
    "JSON only: {{\"t\":{{\"<key>\":\"<translation>\"}}}}."
)

_VERBAL_RE = re.compile(r"[\w\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]")


def _is_nonverbal(text):
    """True for pure punctuation/music symbols/whitespace that need no translation."""
    s = (text or "").strip()
    return not s or not _VERBAL_RE.search(s)


def _build_translate_system(target, ctx):
    """Place static film context in the system message to maximize prompt-prefix caching."""
    target_name = TARGET_NAMES.get(target, target)
    parts = [TRANSLATE_SYSTEM.format(target=target_name)]
    if ctx.get("title"):
        parts.append("FILM: " + str(ctx["title"]))
    if ctx.get("synopsis"):
        parts.append("SYNOPSIS: " + str(ctx["synopsis"]))
    if ctx.get("register"):
        parts.append("REGISTER: " + str(ctx["register"]))
    if ctx.get("glossary"):
        items = sorted(ctx["glossary"].items())[:60]
        parts.append("GLOSSARY: " + "; ".join("%s=%s" % (k, v) for k, v in items))
    return "\n".join(parts)


def translate_cues(cues, target, context=None, batch=60, llm=None, workers=1, usage=None):
    """Translate display cues; returns dict index -> translated text.

    Uses a deterministic system prefix (film/synopsis/glossary) for prompt caching,
    compact key->text JSON input (~40% fewer tokens), skips non-verbal lines,
    auto-halves on truncated JSON, and supports parallel workers for full-track jobs.
    """
    ctx = dict(context or {})
    system = _build_translate_system(target, ctx)
    out = {}
    verbal = []
    for c in cues:
        src = (c.get("src") or "").strip()
        if _is_nonverbal(src):
            if src:
                out[c["i"]] = src
        else:
            verbal.append(c)
    if not verbal:
        return out

    def call_model(sys_prompt, usr_prompt, max_tokens):
        if llm is not None:
            return llm(sys_prompt, usr_prompt, max_tokens=max_tokens)
        return llm_json(sys_prompt, usr_prompt, max_tokens=max_tokens, usage=usage)

    def translate_group(group, prev_text):
        lines = {str(c["i"]): c["src"] for c in group}
        user_parts = []
        if prev_text:
            user_parts.append("PREV (context only): " + prev_text)
        user_parts.append("LINES:\n" + json.dumps(lines, ensure_ascii=False, separators=(",", ":")))
        try:
            res = call_model(system, "\n".join(user_parts), max_tokens=4096)
        except AuthError:
            raise
        except (ValueError, RuntimeError):
            if len(group) > 10:
                half = len(group) // 2
                left = translate_group(group[:half], prev_text)
                mid_prev = " / ".join(c["src"] for c in group[max(0, half - 2):half])
                right = translate_group(group[half:], mid_prev)
                left.update(right)
                return left
            raise
        table = res.get("t") if isinstance(res, dict) else None
        if not isinstance(table, dict):
            if len(group) > 10:
                half = len(group) // 2
                left = translate_group(group[:half], prev_text)
                mid_prev = " / ".join(c["src"] for c in group[max(0, half - 2):half])
                right = translate_group(group[half:], mid_prev)
                left.update(right)
                return left
            table = {}
        got = {}
        for c in group:
            val = table.get(str(c["i"]))
            if val is None:
                val = table.get(c["i"])
            if isinstance(val, str) and val.strip():
                got[c["i"]] = val.strip()
        return got

    # Precompute 2-line rolling context per batch so batches can safely run in parallel.
    tasks = []
    initial_prev = ctx.get("previous") or ""
    for start in range(0, len(verbal), batch):
        chunk = verbal[start:start + batch]
        prev = initial_prev if start == 0 else " / ".join(
            c["src"] for c in verbal[max(0, start - 2):start])
        tasks.append((chunk, prev))

    if workers > 1 and len(tasks) > 1:
        with cf.ThreadPoolExecutor(max_workers=min(workers, len(tasks))) as pool:
            futs = [pool.submit(translate_group, chunk, prev) for chunk, prev in tasks]
            for fut in futs:
                out.update(fut.result())
    else:
        for chunk, prev in tasks:
            out.update(translate_group(chunk, prev))

    if context is not None:
        context["previous"] = " / ".join(c["src"] for c in verbal[-2:])
    return out


def analyze_film(cues, target, llm=None, usage=None):
    """Whole-film pass: synopsis + glossary so the final translation is grounded."""
    if cues and isinstance(cues[0], str):
        transcript = "\n".join(cues)
    else:
        transcript = "\n".join(c["src"] for c in cues)
    if len(transcript) <= 30000:
        body = transcript
    else:
        # sample the whole arc so the glossary sees every act, not just the opening
        third = 10000
        body = (transcript[:third] + "\n...\n"
                + transcript[len(transcript) // 2 - third // 2:
                             len(transcript) // 2 + third // 2] + "\n...\n"
                + transcript[-third:])
    system = ("You analyse full film transcripts to prepare a subtitle translation. "
              "Reply with JSON only: {\"synopsis\": \"<=80 words, spoilers allowed\", "
              "\"glossary\": {\"source name or term\": \"%s rendering\"}, "
              "\"register\": \"one line on tone\"}." % TARGET_NAMES.get(target, target))
    user = "FILM TRANSCRIPT:\n" + body
    if llm is not None:
        res = llm(system, user, max_tokens=2000, temperature=0.1)
    else:
        res = llm_json(system, user, max_tokens=2000, temperature=0.1, usage=usage)
    return {
        "synopsis": (res.get("synopsis") or "").strip(),
        "glossary": res.get("glossary") or {},
        "register": (res.get("register") or "").strip(),
    }
