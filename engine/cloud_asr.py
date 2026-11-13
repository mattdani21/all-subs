"""Cloud audio rung: one multimodal call turns an audio chunk into translated cues.

No local ASR, no local model. The audio leaves the machine, so this rung is opt-in and
sits above the local one. Timestamps are coarser than whisper's token timing, so cue
density is checked before the result is trusted.
"""
from __future__ import annotations

import base64
import json
import re
import os
import subprocess
import tempfile
import time
import urllib.request

import captions

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.environ.get("ALLSUBS_CLOUD_MODEL", "google/gemini-2.5-flash")

SYSTEM = (
    "You transcribe and translate film audio into {lang} subtitles. "
    "Return JSON only: {{\"cues\":[{{\"s\":0.0,\"e\":2.4,\"text\":\"...\"}}]}}. "
    "Times are seconds from the start of this clip. Split at natural sentence or subtitle "
    "boundaries, keep each line under 90 characters, do not merge separate speakers, and "
    "do not invent dialogue for music or silence."
)


def _key():
    captions.load_env()
    return os.environ.get("OPENROUTER_API_KEY")


def available():
    return bool(_key())


def _to_mp3(path):
    out = os.path.join(tempfile.gettempdir(), "allsubs_cloud_%d.mp3" % int(time.time() * 1000))
    subprocess.run([captions.FFMPEG, "-y", "-v", "error", "-i", path,
                    "-ar", "16000", "-ac", "1", "-b:a", "64k", out],
                   check=True, timeout=300)
    return out


def _cues_from(content):
    """Parse the model's JSON, salvaging complete cue objects from a truncated reply."""
    parsed = None
    try:
        parsed = json.loads(content)
    except ValueError:
        start, end = content.find("{"), content.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(content[start:end + 1])
            except ValueError:
                parsed = None
    items = (parsed or {}).get("cues") if isinstance(parsed, dict) else None
    if items:
        return items
    salvage = []
    pattern = re.compile(
        r'\{\s*"s"\s*:\s*([\d.]+)\s*,\s*"e"\s*:\s*([\d.]+)\s*,\s*"text"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}')
    for m in pattern.finditer(content):
        try:
            text = json.loads('"' + m.group(3) + '"')
        except ValueError:
            text = m.group(3)
        salvage.append({"s": m.group(1), "e": m.group(2), "text": text})
    return salvage


def transcribe_chunk(path, language="en", target="en", timeout=300):
    """Return cues [{start,end,text}] relative to the chunk, already translated."""
    key = _key()
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY not set")
    mp3 = _to_mp3(path)
    try:
        b64 = base64.b64encode(open(mp3, "rb").read()).decode()
    finally:
        try:
            os.remove(mp3)
        except OSError:
            pass
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM.format(
                lang=captions.TARGET_NAMES.get(target, target))},
            {"role": "user", "content": [
                {"type": "text", "text": "Caption this clip."},
                {"type": "input_audio", "input_audio": {"data": b64, "format": "mp3"}},
            ]},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 4000,
    }
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.load(resp)
    content = data["choices"][0]["message"]["content"]
    items = _cues_from(content)
    cues = []
    for item in items:
        try:
            s, e = float(item["s"]), float(item["e"])
        except (KeyError, TypeError, ValueError):
            continue
        text = (item.get("text") or "").strip()
        if not text or e <= s or e - s > 30:
            continue
        cues.append({"start": round(s, 3), "end": round(e, 3), "src": "", "dst": text})
    cues.sort(key=lambda c: c["start"])
    return cues, data.get("usage", {})
