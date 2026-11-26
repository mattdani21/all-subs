"""Creator pipeline: video -> translated captions -> second-model review -> YouTube SRT.

The reviewer is a different model from the translator on purpose: a translator
grading its own output is not a quality gate.
"""
import json
import os
import re
import shutil
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import captions  # noqa: E402

REVIEWER_MODEL = os.environ.get("ALLSUBS_REVIEWER", "deepseek-v4-pro")
MAX_CHARS = 42
MAX_LINES = 2
MIN_DUR = 1.0
MAX_DUR = 7.0


def _api(payload, timeout=180, retries=3):
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")
    raw_body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    headers = {
        "Authorization": "Bearer " + key,
        "Content-Type": "application/json",
        "Connection": "keep-alive",
    }
    last = None
    for attempt in range(retries):
        try:
            status, _hdrs, raw = captions._post_keepalive(
                "api.deepseek.com", "/chat/completions", raw_body, headers, timeout=timeout)
            if status == 200:
                return json.loads(raw.decode("utf-8", "replace"))
            snippet = raw.decode("utf-8", "replace")[:200]
            if status in (400, 401, 403, 404):
                raise RuntimeError("DeepSeek HTTP %d: %s" % (status, snippet))
            last = RuntimeError("DeepSeek HTTP %d: %s" % (status, snippet))
            time.sleep(1.5 * (2 ** attempt))
        except RuntimeError:
            raise
        except Exception as exc:
            last = exc
            time.sleep(1.5 * (2 ** attempt))
    raise RuntimeError("reviewer API failed: %s" % last)


def transcribe(media, lang="auto", limit=None):
    workdir = os.path.join(captions.JOBS_DIR, "creator_" + str(os.getpid()))
    os.makedirs(workdir, exist_ok=True)
    try:
        total = captions.duration_of(media)
        if limit:
            total = min(total, float(limit))
        plan = captions.plan_chunks(total, limit=limit, schedule=[300])
        segs = []
        detected = lang
        for i, offset, length in plan:
            path = captions.cut_chunk(media, workdir, i, offset, length)
            silences = captions.silence_intervals(path)
            if captions.is_mostly_silent(silences, length):
                try:
                    os.remove(path)
                except OSError:
                    pass
                continue
            base = os.path.join(workdir, "c%03d" % i)
            part, lg = captions.transcribe_chunk(path, base, lang)
            detected = lg or detected
            part = captions.filter_segments(part, silences, detected)
            part = captions.snap_to_onsets(part, path)
            for c in part:
                c["start"] = round(c["start"] + offset, 3)
                c["end"] = round(c["end"] + offset, 3)
            segs.extend(part)
            for p in (path, base + ".json"):
                try:
                    if os.path.exists(p):
                        os.remove(p)
                except OSError:
                    pass
        return captions.split_display(segs), detected, total
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


def translate(cues, target="en", title=""):
    out = captions.translate_cues(cues, target, {"title": title}, workers=4)
    for c in cues:
        c["dst"] = out.get(c["i"], "")
    return cues


def review(cues, source_lang, target="en", batch=20, workers=6):
    """Second model checks meaning, omissions and fluency; returns issues + score.

    Only lines that need a fix are returned by the model; asking for a verdict on every
    line made the JSON hit max_tokens and silently produced "0 issues".
    """
    import concurrent.futures as cf

    groups = [cues[i:i + batch] for i in range(0, len(cues), batch)]

    def run_group(group):
        payload = [{"id": c["i"], "source": c.get("src", ""), "translation": c.get("dst", "")}
                   for c in group]
        system = (
            "You are a bilingual subtitle editor. Judge each %s translation for accuracy, "
            "completeness and natural English suitable for a YouTube caption track. "
            "Return JSON only, and include ONLY the lines that need changing: "
            "{\"lines\":[{\"id\":N,\"problem\":\"short reason\",\"fixed\":\"corrected English\"}],"
            "\"score\":0-100}. Omit every line that is already correct. Never return a line "
            "with an empty or unchanged fix." % target)
        user = "Source language: %s\n%s" % (source_lang, json.dumps(payload, ensure_ascii=False))
        try:
            data = _api({"model": REVIEWER_MODEL, "messages": [
                {"role": "system", "content": system}, {"role": "user", "content": user}],
                "response_format": {"type": "json_object"}, "temperature": 0.1,
                "max_tokens": 4000,
                # The reviewer was spending ~2,800 hidden reasoning tokens per batch for a
                # 280-character answer: 20 s per batch instead of 3 s, with no better fixes.
                "thinking": {"type": "disabled"}})
        except Exception as exc:
            return [], None, str(exc)[:120]
        text = (data["choices"][0]["message"]["content"] or "").strip()
        try:
            parsed = json.loads(text)
        except ValueError:
            if len(group) > 5:
                half = len(group) // 2
                a = run_group(group[:half])
                b = run_group(group[half:])
                return (a[0] + b[0]), (a[1] if a[1] is not None else b[1]), None
            return [], None, "unparseable JSON"
        score = parsed.get("score")
        fixes = []
        for line in parsed.get("lines", []):
            fixed = (line.get("fixed") or "").strip()
            src = next((c.get("dst", "") for c in group if c["i"] == line.get("id")), "")
            if fixed and fixed.strip() != src.strip():
                fixes.append({"id": line.get("id"), "verdict": "fix",
                              "problem": (line.get("problem") or "")[:160], "fixed": fixed})
        return fixes, (float(score) if isinstance(score, (int, float)) else None), None

    issues, scores, errors = [], [], []
    with cf.ThreadPoolExecutor(max_workers=workers) as pool:
        for fixes, score, err in pool.map(run_group, groups):
            issues.extend(fixes)
            if score is not None:
                scores.append(score)
            if err:
                errors.append(err)
    fixes = {i["id"]: i["fixed"] for i in issues}
    for c in cues:
        c["dst_reviewed"] = fixes.get(c["i"], c.get("dst", ""))
    if errors:
        print("review: %d batch(es) failed: %s" % (len(errors), errors[0]), file=sys.stderr)
    return issues, (round(sum(scores) / len(scores), 1) if scores else None)


def wrap(text, width=MAX_CHARS, lines=MAX_LINES):
    words, out, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > width and cur:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        out.append(cur)
    if len(out) > lines:
        out = out[:lines]
        out[-1] = out[-1].rstrip(" ,;:") + "…"
    return "\n".join(out)


def to_srt(cues, use_reviewed=True):
    lines, seq = [], 0
    prev_end = 0.0
    for c in sorted(cues, key=lambda x: x["start"]):
        start = max(c["start"], prev_end)
        end = min(max(c["end"], start + MIN_DUR), start + MAX_DUR)
        if end <= start:
            continue
        prev_end = end
        text = (c.get("dst_reviewed") if use_reviewed else c.get("dst")) or c.get("src", "")
        if not text.strip():
            continue
        seq += 1
        lines.append("%d\n%s --> %s\n%s\n" % (
            seq, _ts(start), _ts(end), wrap(text)))
    return "\n".join(lines)


def _ts(t):
    h, rem = divmod(max(t, 0), 3600)
    m, s = divmod(rem, 60)
    ms = int(round((s - int(s)) * 1000))
    return "%02d:%02d:%02d,%03d" % (int(h), int(m), int(s), ms)


def run(media, target="en", limit=None, title="", out_srt=None, out_json=None):
    captions.load_env()
    cues, lang, total = transcribe(media, limit=limit)
    print("transcribed %d cues, language %s, %.0fs" % (len(cues), lang, total))
    cues = translate(cues, target, title)
    print("translated")
    issues, score = review(cues, lang, target)
    print("review: %d lines flagged for correction, quality score %s" % (len(issues), score))
    srt = to_srt(cues)
    out_srt = out_srt or os.path.splitext(media)[0] + ".%s.srt" % target
    with open(out_srt, "w") as fh:
        fh.write(srt)
    if out_json:
        with open(out_json, "w") as fh:
            json.dump({"language": lang, "cues": cues, "issues": issues}, fh, ensure_ascii=False, indent=1)
    print("wrote", out_srt, len(srt.splitlines()), "lines")
    return cues, issues, out_srt


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("media")
    ap.add_argument("--target", default="en")
    ap.add_argument("--limit", type=float, default=None)
    ap.add_argument("--title", default="")
    ap.add_argument("--out", default=None)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    run(a.media, a.target, a.limit, a.title, a.out, a.json)
