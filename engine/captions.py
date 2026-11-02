"""All Subs caption pipeline: probe -> native subs or ASR -> LLM translation."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request

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

def load_env():
    """Pull API keys from the project .env, then the Hermes env file."""
    for path in (os.path.join(PROJECT_DIR, ".env"), os.path.join(HOME, ".hermes", ".env")):
        if not os.path.exists(path):
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

def probe(url):
    """Metadata + subtitle inventory without downloading media."""
    proc = run([YTDLP, "-J", "--no-warnings", "--no-playlist", url], timeout=300)
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

def download_audio(url, workdir, key=None):
    media_cache = os.path.join(CACHE_DIR, "media")
    os.makedirs(media_cache, exist_ok=True)
    if key:
        for ext in ("m4a", "mp4", "webm", "opus", "mkv", "mp3"):
            cached = os.path.join(media_cache, key + "." + ext)
            if os.path.exists(cached) and os.path.getsize(cached) > 100000:
                return cached
    out = os.path.join(workdir, "audio.%(ext)s")
    run([YTDLP, "--no-warnings", "--no-playlist", "-f", "bestaudio/best",
         "-o", out, url], timeout=3600)
    for name in os.listdir(workdir):
        if name.startswith("audio."):
            path = os.path.join(workdir, name)
            if key:
                shutil.copyfile(path, os.path.join(media_cache, key + os.path.splitext(name)[1]))
            return path
    raise RuntimeError("audio download produced no file")


def duration_of(path):
    proc = run([FFPROBE, "-v", "error", "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1", path], timeout=120)
    try:
        return float(proc.stdout.strip())
    except ValueError:
        return 0.0


def to_wav(src, dst):
    run([FFMPEG, "-y", "-v", "error", "-i", src, "-ar", "16000", "-ac", "1",
         "-c:a", "pcm_s16le", dst], timeout=1800)
    return dst


def split_wav(wav, workdir, chunk_seconds=CHUNK_SECONDS, limit=None):
    """Split the wav into chunks; `limit` caps how many seconds to cut."""
    total = duration_of(wav)
    if limit:
        total = min(total, float(limit))
    if total <= 0:
        raise RuntimeError("could not read audio duration")
    out = []
    start = 0.0
    idx = 0
    while start < total - 0.01:
        length = min(chunk_seconds, total - start)
        path = os.path.join(workdir, "chunk_%03d.wav" % idx)
        run([FFMPEG, "-y", "-v", "error", "-ss", str(start), "-t", str(length),
             "-i", wav, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", path],
            timeout=600)
        out.append((path, start, length))
        start += length
        idx += 1
    return out


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
        if silent / dur > 0.6 or (mid_silent and dur > 20):
            continue
        repeats = counts.get(key, 0)
        if repeats >= 2 and dur >= 8:
            continue
        if repeats >= (4 if len(key) <= 3 else 3):
            continue
        if any(a in key for a in (_norm(x) for x in ARTIFACTS)):
            if counts.get(key, 0) >= 2 or (lang and not lang.startswith("en")):
                continue
        if key == last:
            continue
        last = key
        out.append({"start": seg["start"], "end": seg["end"], "src": text})
    return out


def detect_language(wav, total):
    """Majority language vote on three loud windows across the film."""
    votes = {}
    for frac in (0.25, 0.55, 0.8):
        start = max(0.0, total * frac - 15.0)
        tmp = os.path.join(os.path.dirname(wav), "langprobe.wav")
        subprocess.run([FFMPEG, "-y", "-v", "error", "-ss", str(start), "-t", "20",
                        "-i", wav, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", tmp],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
        proc = subprocess.run([WHISPER_BIN, "-m", WHISPER_MODEL, "-f", tmp, "-dl", "-l", "auto"],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              timeout=300)
        m = re.search(r"auto-detected language:\s*([a-zA-Z-]+)", (proc.stdout or "") + (proc.stderr or ""))
        if m:
            code = m.group(1).lower()
            votes[code] = votes.get(code, 0) + 1
    if not votes:
        return None
    return max(votes.items(), key=lambda kv: kv[1])[0]


def transcribe_chunk(path, base, language="auto"):
    """Run whisper.cpp on one chunk; returns (segments, detected language)."""
    proc = subprocess.run(
        [WHISPER_BIN, "-m", WHISPER_MODEL, "-f", path, "-t", "8", "-l", language,
         "-mc", "0", "-ojf", "-of", base],
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


def is_cjk(text):
    return len(re.findall(r"[\u3400-\u9fff\u3040-\u30ff\uac00-\ud7af]", text)) > len(text) * 0.3


def split_display(cues, limit_seconds=None):
    """Break whisper segments into subtitle-sized cues with proportional timing."""
    out = []
    for cue in cues:
        text = cue["src"].strip()
        budget = CUE_MAX_CJK if is_cjk(text) else CUE_MAX_LATIN
        if len(text) <= budget or cue["end"] - cue["start"] < 1.2:
            out.append(dict(cue))
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

def llm_json(system, user, max_tokens=2600, temperature=0.2, retries=3):
    """JSON-mode chat call. deepseek-flash with thinking off; deepseek-chat fallback."""
    load_env()
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")
    models = [(os.environ.get("ALLSUBS_MODEL", "deepseek-flash"), True)]
    if models[0][0] != "deepseek-chat":
        models.append(("deepseek-chat", False))
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
        data = json.dumps(body).encode()
        for attempt in range(retries):
            req = urllib.request.Request(
                "https://api.deepseek.com/chat/completions", data=data,
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer " + key})
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    payload = json.loads(resp.read().decode())
                content = payload["choices"][0]["message"]["content"]
                return json.loads(content)
            except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as exc:
                last = exc
                time.sleep(1.5 + attempt * 2)
    raise RuntimeError("LLM call failed: %s" % last)


TRANSLATE_SYSTEM = (
    "You are a world-class subtitle translator for feature films. "
    "Translate every numbered line into {target}. Rules: translate meaning and intent, "
    "not words; dialogue must sound like spoken language, never prose; keep the register "
    "and tone of the scene; use the glossary spelling for names; keep each line under "
    "90 characters; never merge, split, drop, reorder or renumber lines; if a line is a "
    "song lyric, translate it as a lyric; if a line is untranslatable noise, leave it "
    "empty. Reply with JSON only: {{\"t\": {{\"<index>\": \"<translation>\"}}}}."
)


def translate_cues(cues, target, context=None, batch=36, llm=None):
    """Translate display cues; returns dict index -> translated text."""
    call = llm or llm_json
    target_name = TARGET_NAMES.get(target, target)
    system = TRANSLATE_SYSTEM.format(target=target_name)
    out = {}
    ctx = context or {}
    for start in range(0, len(cues), batch):
        chunk = cues[start:start + batch]
        lines = [{"i": c["i"], "text": c["src"]} for c in chunk]
        user_parts = []
        if ctx.get("title"):
            user_parts.append("FILM: " + ctx["title"])
        if ctx.get("synopsis"):
            user_parts.append("SYNOPSIS: " + ctx["synopsis"])
        if ctx.get("glossary"):
            gl = "; ".join("%s = %s" % (k, v) for k, v in list(ctx["glossary"].items())[:60])
            user_parts.append("GLOSSARY: " + gl)
        if ctx.get("previous"):
            user_parts.append("PREVIOUS LINES (context, do not translate): " + ctx["previous"])
        user_parts.append("LINES:\n" + json.dumps(lines, ensure_ascii=False))
        res = call(system, "\n\n".join(user_parts), max_tokens=3000)
        table = res.get("t") or {}
        for c in chunk:
            val = table.get(str(c["i"]))
            if val is None:
                val = table.get(c["i"]) if isinstance(table, dict) else None
            if isinstance(val, str) and val.strip():
                out[c["i"]] = val.strip()
        ctx["previous"] = " / ".join(c["src"] for c in chunk[-2:])
    return out


def analyze_film(cues, target, llm=None):
    """Whole-film pass: synopsis + glossary so the final translation is grounded."""
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
    res = (llm or llm_json)(system, user, max_tokens=2000, temperature=0.1)
    return {
        "synopsis": (res.get("synopsis") or "").strip(),
        "glossary": res.get("glossary") or {},
        "register": (res.get("register") or "").strip(),
    }
