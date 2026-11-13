"""All Subs local caption engine — HTTP API + job runner."""
from __future__ import annotations

import json
import os
import queue
import re
import sys
import threading
import time
import traceback
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import captions
import providers

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


def _local_available():
    try:
        import local_llm
        return local_llm.available()
    except Exception:
        return False


class Job(object):
    def __init__(self, job_id, url, target="en", mode="fast", limit=None,
                 translator="cloud", duration_hint=None):
        self.id = job_id
        self.url = url
        self.target = target
        self.mode = mode
        self.limit = limit
        self.translator = translator
        self.duration_hint = duration_hint
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
        self.disk_lock = threading.Lock()

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
                "translator": self.translator,
                "duration_hint": self.duration_hint,
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
        with self.disk_lock:
            data = self.snapshot()
            with self.lock:
                data["cues"] = self.cues
            data["glossary"] = self.glossary
            tmp = path + ".tmp"
            with open(tmp, "w") as fh:
                json.dump(data, fh, ensure_ascii=False)
            os.replace(tmp, path)


to_vtt = captions.to_vtt


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
        if code.lower().startswith(job.target.lower()):
            for c in cues:
                c["dst"] = c["src"]
        else:
            # found a usable track, but not in the viewer's language: translate it
            translated = captions.translate_cues(cues, job.target, {"title": job.title})
            for c in cues:
                c["dst"] = translated.get(c["i"], c["src"])
        job.add_cues(cues)
        job.set(status="done", stage="Captions ready (%s)" % code, progress=1.0,
                source="native", lang=code)
        job.to_disk()
        _cache(job)
        return

    # 2. search public subtitle libraries before doing any ASR
    if job.duration_hint and job.duration_hint > 300 and job.translator != "local":
        job.set(status="searching", stage="Searching subtitle libraries", progress=0.08)
        try:
            found = providers.find(job.title, job.duration_hint, job.target)
        except Exception as exc:
            found = None
            log("job %s: provider error: %s" % (job.id, exc))
        if found and found.get("rejected"):
            log("job %s: provider rejected track %s (%s)" % (
                job.id, found.get("imdb"), found.get("note")))
        elif found:
            cues = found["cues"]
            if job.target and (found.get("lang") or "").startswith(job.target):
                for c in cues:
                    c["dst"] = c["src"]
            else:
                translated = captions.translate_cues(
                    cues, job.target, {"title": job.title})
                for c in cues:
                    c["dst"] = translated.get(c["i"], c["src"])
            job.add_cues(cues)
            job.set(status="done", stage="Captions ready (library)", progress=1.0,
                    source="wyzie", lang=found.get("lang"), duration=job.duration_hint)
            job.to_disk()
            _cache(job)
            log("job %s: used library track %s (%s)" % (
                job.id, found.get("imdb"), found.get("note")))
            return

    # 3. no usable track -> transcribe locally
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
    chunks = captions.split_wav(wav, workdir, limit=job.limit, schedule=[60, 120, 300])
    job.set(status="asr", stage="Transcribing 0/%d" % len(chunks), progress=0.1,
            source="asr")
    log("job %s: %d chunks (first %ss), %.0fs audio" % (
        job.id, len(chunks), chunks[0][2] if chunks else 0, total))

    lang = captions.detect_language(wav, total) or "auto"
    job.set(lang=lang)
    log("job %s: language %s" % (job.id, lang))

    timings = {"asr": 0.0, "translate": 0.0, "deep": 0.0}
    pending = queue.Queue(maxsize=3)
    state = {"done": 0}
    last_src = [""]

    def translate_worker():
        """Translate finished chunks while the next chunk is being transcribed."""
        while True:
            cues = pending.get()
            if cues is None:
                pending.task_done()
                return
            t0 = time.time()
            if job.target and lang and lang.startswith(job.target):
                for c in cues:
                    c["dst"] = c["src"]
            elif job.translator == "local":
                for c in cues:
                    c["dst"] = ""
            else:
                translated = captions.translate_cues(
                    cues, job.target,
                    {"title": job.title, "glossary": job.glossary,
                     "previous": last_src[0]})
                for c in cues:
                    c["dst"] = translated.get(c["i"], "")
            if cues:
                last_src[0] = cues[-1]["src"]
            job.add_cues(cues)
            timings["translate"] += time.time() - t0
            job.set(stage="%d/%d transcribed \u00b7 %d cues" % (
                state["done"], len(chunks), len(job.cues)))
            job.to_disk()
            pending.task_done()

    worker = threading.Thread(target=translate_worker, daemon=True)
    worker.start()
    try:
        for idx, (path, offset, length) in enumerate(chunks):
            if job.status == "cancelled":
                return
            t0 = time.time()
            silences = captions.silence_intervals(path)
            cues, _detected = captions.transcribe_chunk(
                path, os.path.join(workdir, "c%03d" % idx), lang)
            cues = captions.filter_segments(cues, silences, lang)
            for c in cues:
                c["start"] = round(c["start"] + offset, 3)
                c["end"] = round(c["end"] + offset, 3)
            cues = captions.split_display(cues)
            timings["asr"] += time.time() - t0
            state["done"] = idx + 1
            if cues:
                pending.put(cues)
            job.set(stage="Transcribing %d/%d" % (idx + 1, len(chunks)),
                    progress=0.1 + 0.8 * (idx + 1) / len(chunks))
    finally:
        pending.put(None)
        pending.join()
        worker.join()

    if not job.cues:
        raise RuntimeError("no speech detected in the audio")
    with job.lock:
        all_src = [c["src"] for c in job.cues]

    if job.translator == "local" and not (lang or "").startswith(job.target):
        _translate_local(job)
        job.set(status="done", stage="Captions ready", progress=1.0)
        job.to_disk()
        _cache(job)
        log("job %s: done (local), %d cues" % (job.id, len(job.cues)))
        return

    # 3. whole-film pass: the LLM reads everything, then re-translates in parallel
    if job.mode == "deep" and not (lang or "").startswith(job.target):
        timings["deep"] = _deep_pass(job)

    job.set(status="done", stage="Captions ready", progress=1.0)
    job.to_disk()
    _cache(job)
    log("job %s: done, %d cues (asr %.0fs, translate %.0fs, deep %.0fs)" % (
        job.id, len(job.cues), timings["asr"], timings["translate"], timings["deep"]))


def _translate_local(job):
    """Offline translation pass: whisper is finished, so the small model owns RAM."""
    from local_llm import LocalTranslator
    step = 20
    with LocalTranslator() as lt:
        total = len(job.cues)
        job.set(status="translate", stage="Translating on this Mac", progress=0.82)
        for start in range(0, total, step):
            if job.status == "cancelled":
                return
            with job.lock:
                batch = list(job.cues[start:start + step])
            if not batch:
                break
            res = captions.translate_cues(
                batch, job.target, {"title": job.title, "glossary": job.glossary},
                batch=step, llm=lt.chat_json)
            with job.lock:
                for c in batch:
                    c["dst"] = res.get(c["i"]) or c.get("dst") or c["src"]
                job.version += 1
            done = min(start + step, total)
            job.set(stage="Translating %d/%d (local)" % (done, total),
                    progress=0.82 + 0.16 * done / max(total, 1))
            job.to_disk()
        if job.mode == "deep":
            try:
                job.set(status="deep", stage="Reading the whole film (local)",
                        progress=0.96)
                info = captions.analyze_film(job.cues, job.target, llm=lt.chat_json)
                job.set(synopsis=info["synopsis"], glossary=info["glossary"])
                with job.lock:
                    snapshot = list(job.cues)
                for start in range(0, len(snapshot), step):
                    batch = snapshot[start:start + step]
                    res = captions.translate_cues(
                        batch, job.target,
                        {"title": job.title, "synopsis": job.synopsis,
                         "glossary": job.glossary}, batch=step, llm=lt.chat_json)
                    with job.lock:
                        for c in batch:
                            if res.get(c["i"]):
                                c["dst"] = res[c["i"]]
                        job.version += 1
                    job.set(stage="Refining %d/%d (local)" % (
                        min(start + step, len(snapshot)), len(snapshot)))
                job.pass2 = True
                job.to_disk()
            except Exception as exc:
                log("job %s: local deep pass failed: %s" % (job.id, exc))


def _deep_pass(job):
    """Whole-film context + parallel retranslation. Returns elapsed seconds."""
    all_src = [c["src"] for c in job.cues]
    t0 = time.time()
    try:
        job.set(status="deep", stage="Reading the whole film", progress=0.92)
        info = captions.analyze_film(all_src, job.target)
        job.set(synopsis=info["synopsis"], glossary=info["glossary"])
        with job.lock:
            snapshot = list(job.cues)
        batches = [snapshot[i:i + 36] for i in range(0, len(snapshot), 36)]
        result = {}
        done = [0]
        lock = threading.Lock()

        def refine(batch):
            res = captions.translate_cues(
                batch, job.target,
                {"title": job.title, "synopsis": job.synopsis,
                 "glossary": job.glossary, "previous": ""})
            with lock:
                result.update(res)
                done[0] += len(batch)
                job.set(stage="Refining translation %d/%d" % (
                    done[0], len(snapshot)),
                    progress=0.92 + 0.07 * done[0] / max(len(snapshot), 1))
            return True

        with ThreadPoolExecutor(max_workers=6) as pool:
            list(pool.map(refine, batches))
        with job.lock:
            for c in job.cues:
                if result.get(c["i"]):
                    c["dst"] = result[c["i"]]
            job.version += 1
            job.pass2 = True
        job.to_disk()
    except Exception as exc:
        log("job %s: deep pass failed: %s" % (job.id, exc))
    elapsed = time.time() - t0
    log("job %s: deep pass %.0fs" % (job.id, elapsed))
    return elapsed


def _cache(job):
    snap = job.snapshot()
    with job.lock:
        snap["cues"] = job.cues
        snap["glossary"] = job.glossary
    captions.save_cache(job.id, snap)


def get_or_create(url, target, mode, limit, translator="cloud", duration_hint=None):
    key = captions.url_key(url, target if translator == "cloud" else target + "|" + translator)
    with JOBS_LOCK:
        job = JOBS.get(key)
        if job and job.status not in ("error", "cancelled"):
            return job, False
        cached = captions.load_cache(key)
        if cached and cached.get("cues") and cached.get("status") == "done":
            job = Job(key, url, target, mode, limit, translator, duration_hint)
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
        job = Job(key, url, target, mode, limit, translator, duration_hint)
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
                      data.get("mode", "fast"), None, data.get("translator", "cloud"))
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
                "jobs": len(JOBS), "local": _local_available(),
                "ram_gb": round(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1e9, 1),
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
            translator = body.get("translator") or "cloud"
            duration_hint = body.get("duration") or None
            job, created = get_or_create(url, target, mode, limit, translator,
                                         float(duration_hint) if duration_hint else None)
            log("%s job %s for %s (%s)" % ("created" if created else "reused",
                                           job.id, url[:80], target))
            return self._send(200, dict(job.snapshot(), created=created))

        m = re.match(r"^/api/jobs/([a-zA-Z0-9]+)/refine$", parsed.path)
        if m:
            job = JOBS.get(m.group(1))
            if not job or not job.cues:
                return self._send(404, {"error": "no such job"})
            job.set(status="deep", stage="Reading the whole film", progress=0.9)

            def run():
                _deep_pass(job)
                job.set(status="done", stage="Captions ready", progress=1.0)
                _cache(job)

            threading.Thread(target=run, daemon=True).start()
            return self._send(200, job.snapshot())

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
