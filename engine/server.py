"""All Subs local caption engine — HTTP API + job runner."""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import captions

PORT = int(os.environ.get("ALLSUBS_PORT", "8765"))
MAX_WORKERS = 2
VERSION = "0.1.0"

JOBS = {}
JOBS_LOCK = threading.Lock()
SEM = threading.Semaphore(MAX_WORKERS)
LOG_PATH = os.path.join(captions.DATA_DIR, "engine.log")


def log(msg):
    line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
    if sys.stdout.isatty():
        print(line, flush=True)
    try:
        with open(LOG_PATH, "a") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def now():
    return time.time()


class Job(object):
    def __init__(self, job_id, url, target="en", mode="fast", limit=None):
        self.id = job_id
        self.url = url
        self.target = target
        self.mode = mode
        self.limit = limit
        self.title = ""
        self.duration = 0.0
        self.status = "queued"
        self.stage = "Queued"
        self.progress = 0.0
        self.source = None          # "native" | "asr"
        self.lang = None
        self.cues = []
        self.version = 0
        self.pass2 = False
        self.synopsis = ""
        self.glossary = {}
        self.error = None
        self.created = now()
        self.updated = now()
        self.lock = threading.Lock()

    def set(self, **kw):
        with self.lock:
            for k, v in kw.items():
                setattr(self, k, v)
            self.updated = now()

    def add_cues(self, cues):
        with self.lock:
            base = len(self.cues)
            for n, c in enumerate(cues):
                c["i"] = base + n
                self.cues.append(c)
            self.version += 1
            self.updated = now()

    def snapshot(self):
        with self.lock:
            return {
                "id": self.id, "url": self.url, "title": self.title,
                "duration": self.duration, "status": self.status, "stage": self.stage,
                "progress": round(self.progress, 3), "source": self.source,
                "lang": self.lang, "count": len(self.cues), "version": self.version,
                "pass2": self.pass2, "error": self.error,
                "synopsis": self.synopsis, "mode": self.mode,
            }

    def cue_payload(self, start=0, limit=400):
        with self.lock:
            total = len(self.cues)
            chunk = self.cues[start:start + limit]
            out = [{"i": c["i"], "s": c["start"], "e": c["end"],
                    "x": c.get("src", ""), "t": c.get("dst", "")} for c in chunk]
            return {"version": self.version, "total": total,
                    "next": start + len(chunk), "cues": out,
                    "done": self.status == "done"}

    def to_disk(self):
        path = os.path.join(captions.JOBS_DIR, self.id + ".json")
        data = self.snapshot()
        with self.lock:
            data["cues"] = self.cues
            data["glossary"] = self.glossary
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(tmp, path)


def vtt_timestamp(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d.%03d" % (h, m, s, ms)


def to_vtt(cues):
    lines = ["WEBVTT", ""]
    for c in cues:
        text = (c.get("dst") or "").strip()
        if not text:
            text = c.get("src", "")
        if not text:
            continue
        lines.append("%s --> %s" % (vtt_timestamp(c["start"]), vtt_timestamp(c["end"])))
        lines.append(text)
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------- pipeline

def run_job(job):
    with SEM:
        try:
            _run_job(job)
        except Exception as exc:  # keep the daemon alive, surface the error
            log("job %s failed: %s\n%s" % (job.id, exc, traceback.format_exc()))
            job.set(status="error", stage="Failed", error=str(exc)[:500])
            job.to_disk()


def _run_job(job):
    job.set(status="probing", stage="Reading page")
    log("job %s: probing %s" % (job.id, job.url))

    meta = captions.probe(job.url)
    job.set(title=meta["title"], duration=meta["duration"] or 0)
    log("job %s: %s (%ss) native subs=%s" % (
        job.id, meta["title"], meta["duration"], list(meta["subtitles"].keys())))

    target_name = captions.TARGET_NAMES.get(job.target, job.target)

    # 1. existing, safe captions win
    native = captions.pick_native_subs(meta, job.target)
    if native:
        code, _kind = native
        job.set(status="fetching", stage="Found %s subtitles" % code, progress=0.3)
        workdir = os.path.join(captions.JOBS_DIR, job.id + "_work")
        os.makedirs(workdir, exist_ok=True)
        text = captions.download_native_subs(job.url, code, os.path.join(workdir, "sub"))
        cues = captions.parse_vtt(text) if text.lstrip().startswith("WEBVTT") else captions.parse_srt(text)
        cues = captions.split_display([dict(c) for c in cues])
        for c in cues:
            c["dst"] = c["src"]
        job.add_cues(cues)
        job.set(status="done", stage="Captions ready (%s)" % code, progress=1.0,
                source="native", lang=code)
        job.to_disk()
        _cache(job)
        return

    # 2. no usable track -> transcribe locally
    job.set(status="audio", stage="Downloading audio", progress=0.05)
    workdir = os.path.join(captions.JOBS_DIR, job.id + "_work")
    os.makedirs(workdir, exist_ok=True)
    audio = captions.download_audio(job.url, workdir, job.id)
    wav = captions.to_wav(audio, os.path.join(workdir, "audio.wav"))
    total = captions.duration_of(wav)
    if job.limit:
        total = min(total, float(job.limit))
        job.set(duration=total)

    job.set(duration=total)
    chunks = captions.split_wav(wav, workdir, limit=job.limit)
    job.set(status="asr", stage="Transcribing 0/%d" % len(chunks), progress=0.1,
            source="asr")
    log("job %s: %d chunks, %.0fs audio" % (job.id, len(chunks), total))

    lang = captions.detect_language(wav, total) or "auto"
    job.set(lang=lang)
    log("job %s: language %s" % (job.id, lang))
    all_src = []
    for idx, (path, offset, length) in enumerate(chunks):
        if job.status == "cancelled":
            return
        silences = captions.silence_intervals(path)
        cues, _detected = captions.transcribe_chunk(
            path, os.path.join(workdir, "c%03d" % idx), lang)
        cues = captions.filter_segments(cues, silences, lang)
        for c in cues:
            c["start"] = round(c["start"] + offset, 3)
            c["end"] = round(c["end"] + offset, 3)
        cues = captions.split_display(cues)
        if not cues:
            continue
        all_src.extend(cues)
        if job.target and lang and lang.startswith(job.target):
            for c in cues:
                c["dst"] = c["src"]
        else:
            translated = captions.translate_cues(
                cues, job.target,
                {"title": job.title, "glossary": job.glossary,
                 "previous": job.cues[-1]["src"] if job.cues else ""})
            for c in cues:
                c["dst"] = translated.get(c["i"], "")
        job.add_cues(cues)
        job.set(stage="Transcribing %d/%d" % (idx + 1, len(chunks)),
                progress=0.1 + 0.8 * (idx + 1) / len(chunks))
        job.to_disk()

    if not all_src:
        raise RuntimeError("no speech detected in the audio")

    # 3. whole-film pass: the LLM reads everything, then re-translates grounded
    if job.mode == "deep" and not (lang or "").startswith(job.target):
        try:
            job.set(status="deep", stage="Reading the whole film", progress=0.92)
            info = captions.analyze_film(all_src, job.target)
            job.set(synopsis=info["synopsis"], glossary=info["glossary"])
            with job.lock:
                snapshot = list(job.cues)
            result = {}
            for start in range(0, len(snapshot), 36):
                batch = snapshot[start:start + 36]
                result.update(captions.translate_cues(
                    batch, job.target,
                    {"title": job.title, "synopsis": job.synopsis,
                     "glossary": job.glossary, "previous": ""}))
                job.set(stage="Refining translation %d/%d" % (
                    min(start + 36, len(snapshot)), len(snapshot)),
                    progress=0.92 + 0.07 * (start + 36) / max(len(snapshot), 1))
            with job.lock:
                for c in job.cues:
                    if result.get(c["i"]):
                        c["dst"] = result[c["i"]]
                job.version += 1
                job.pass2 = True
        except Exception as exc:  # fast captions already exist; keep them
            log("job %s: deep pass failed: %s" % (job.id, exc))

    job.set(status="done", stage="Captions ready", progress=1.0)
    job.to_disk()
    _cache(job)
    log("job %s: done, %d cues" % (job.id, len(job.cues)))


def _cache(job):
    snap = job.snapshot()
    with job.lock:
        snap["cues"] = job.cues
        snap["glossary"] = job.glossary
    captions.save_cache(job.id, snap)


def get_or_create(url, target, mode, limit):
    key = captions.url_key(url, target)
    with JOBS_LOCK:
        job = JOBS.get(key)
        if job and job.status not in ("error", "cancelled"):
            return job, False
        cached = captions.load_cache(key)
        if cached and cached.get("cues") and cached.get("status") == "done":
            job = Job(key, url, target, mode, limit)
            job.title = cached.get("title") or ""
            job.duration = cached.get("duration") or 0
            job.source = cached.get("source")
            job.lang = cached.get("lang")
            job.cues = cached["cues"]
            job.glossary = cached.get("glossary") or {}
            job.synopsis = cached.get("synopsis") or ""
            job.pass2 = bool(cached.get("pass2"))
            job.status = "done"
            job.stage = "Captions ready (cached)"
            job.progress = 1.0
            JOBS[key] = job
            log("job %s: served from cache" % key)
            return job, False
        job = Job(key, url, target, mode, limit)
        JOBS[key] = job
    threading.Thread(target=run_job, args=(job,), daemon=True).start()
    return job, True


def load_existing_jobs():
    if not os.path.isdir(captions.JOBS_DIR):
        return
    for name in os.listdir(captions.JOBS_DIR):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(captions.JOBS_DIR, name)) as fh:
                data = json.load(fh)
            job = Job(data["id"], data.get("url", ""), data.get("target", "en"),
                      data.get("mode", "fast"))
            for k in ("title", "duration", "status", "stage", "progress", "source",
                      "lang", "version", "pass2", "synopsis", "glossary"):
                if k in data:
                    setattr(job, k, data[k])
            job.cues = data.get("cues") or []
            if job.status != "done":
                job.status = "error"
                job.stage = "Interrupted (engine restarted)"
                job.error = "Engine restarted mid-job. Start it again."
            JOBS[job.id] = job
        except (OSError, ValueError, KeyError):
            continue


# ---------------------------------------------------------------- HTTP

CORS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Private-Network": "true",
    "Access-Control-Max-Age": "600",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "AllSubs/" + VERSION

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, payload, ctype="application/json"):
        if isinstance(payload, (dict, list)):
            body = json.dumps(payload, ensure_ascii=False).encode()
        else:
            body = payload.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text") or ctype.endswith("json") else ""))
        self.send_header("Content-Length", str(len(body)))
        for k, v in CORS.items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(204, b"", "text/plain")

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        qs = urllib.parse.parse_qs(parsed.query)

        if path == "/health":
            return self._send(200, {
                "ok": True, "version": VERSION,
                "whisper": os.path.exists(captions.WHISPER_BIN),
                "model": os.path.exists(captions.WHISPER_MODEL),
                "jobs": len(JOBS),
            })

        if path == "/" or path == "/jobs":
            rows = "".join(
                "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
                    j.id, (j.title or j.url)[:60], j.status, len(j.cues), j.stage)
                for j in sorted(JOBS.values(), key=lambda x: -x.created))
            html = ("<html><body style='font:14px -apple-system;background:#0b0d10;color:#ddd'>"
                    "<h2 style='color:#fff'>All Subs engine %s</h2><table cellpadding=6>"
                    "<tr style='color:#888'><th>id</th><th>title</th><th>status</th>"
                    "<th>cues</th><th>stage</th></tr>%s</table></body></html>" % (VERSION, rows))
            return self._send(200, html, "text/html")

        m = re.match(r"^/api/jobs/([a-zA-Z0-9]+)$", path)
        if m:
            job = JOBS.get(m.group(1))
            if not job:
                return self._send(404, {"error": "no such job"})
            return self._send(200, job.snapshot())

        m = re.match(r"^/api/jobs/([a-zA-Z0-9]+)/cues$", path)
        if m:
            job = JOBS.get(m.group(1))
            if not job:
                return self._send(404, {"error": "no such job"})
            start = int(qs.get("from", ["0"])[0])
            payload = job.cue_payload(max(0, start))
            payload["title"] = job.title
            payload["target"] = job.target
            payload["lang"] = job.lang
            payload["source"] = job.source
            payload["status"] = job.status
            payload["stage"] = job.stage
            return self._send(200, payload)

        m = re.match(r"^/api/jobs/([a-zA-Z0-9]+)\.vtt$", path)
        if m:
            job = JOBS.get(m.group(1))
            if not job:
                return self._send(404, "no such job", "text/plain")
            with job.lock:
                data = to_vtt(job.cues)
            self.send_response(200)
            self.send_header("Content-Type", "text/vtt; charset=utf-8")
            self.send_header("Content-Length", str(len(data.encode())))
            for k, v in CORS.items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data.encode())
            return

        return self._send(404, {"error": "not found"})

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw.decode() or "{}")
        except ValueError:
            return self._send(400, {"error": "bad json"})

        if parsed.path == "/api/jobs":
            url = (body.get("url") or "").strip()
            if not url:
                return self._send(400, {"error": "url required"})
            target = body.get("target") or "en"
            mode = body.get("mode") or "fast"
            limit = body.get("limit")
            job, created = get_or_create(url, target, mode, limit)
            log("%s job %s for %s (%s)" % ("created" if created else "reused",
                                           job.id, url[:80], target))
            return self._send(200, dict(job.snapshot(), created=created))

        m = re.match(r"^/api/jobs/([a-zA-Z0-9]+)/cancel$", parsed.path)
        if m:
            job = JOBS.get(m.group(1))
            if job:
                job.set(status="cancelled", stage="Cancelled")
            return self._send(200, {"ok": True})

        return self._send(404, {"error": "not found"})


def main():
    load_existing_jobs()
    load_env_done = captions.load_env()  # noqa: F841
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    log("All Subs engine %s on http://127.0.0.1:%d — %d cached jobs" % (
        VERSION, PORT, len(JOBS)))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
