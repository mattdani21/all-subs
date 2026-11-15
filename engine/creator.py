"""Creator pipeline: video -> translated captions -> second-model review -> YouTube SRT.

The reviewer is a different model from the translator on purpose: a translator
grading its own output is not a quality gate.
"""
import json
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import captions  # noqa: E402

REVIEWER_MODEL = os.environ.get("ALLSUBS_REVIEWER", "deepseek-v4-pro")
MAX_CHARS = 42
MAX_LINES = 2
MIN_DUR = 1.0
MAX_DUR = 7.0


def _api(payload, timeout=180):
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")
    req = urllib.request.Request(
        "https://api.deepseek.com/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)


def transcribe(media, lang="auto", limit=None):
    workdir = os.path.join(captions.JOBS_DIR, "creator_" + str(os.getpid()))
    os.makedirs(workdir, exist_ok=True)
    total = captions.duration_of(media)
    if limit:
        total = min(total, float(limit))
    chunks = captions.split_wav(media, workdir, limit=limit, schedule=[300])
    segs = []
    detected = lang
    for i, (path, offset, length) in enumerate(chunks):
        part, lg = captions.transcribe_chunk(path, os.path.join(workdir, "c%03d" % i), lang)
        detected = lg or detected
        silences = captions.silence_intervals(path)
        part = captions.filter_segments(part, silences, detected)
        for c in part:
            c["start"] = round(c["start"] + offset, 3)
            c["end"] = round(c["end"] + offset, 3)
        segs.extend(part)
    return captions.split_display(segs), detected, total


def translate(cues, target="en", title=""):
    out = captions.translate_cues(cues, target, {"title": title})
    for c in cues:
        c["dst"] = out.get(c["i"], "")
    return cues


def review(cues, source_lang, target="en", batch=30):
    """Second model checks meaning, omissions and fluency; returns issues + fixes."""
    issues, fixes, scores = [], {}, []
    for start in range(0, len(cues), batch):
        group = cues[start:start + batch]
        payload = [{"id": c["i"], "source": c.get("src", ""), "translation": c.get("dst", "")}
                   for c in group]
        system = (
            "You are a bilingual subtitle editor. For each pair, judge whether the %s "
            "translation is accurate, complete and natural English suitable for a YouTube "
            "caption track. Flag: wrong meaning, omitted content, added content, mistranslated "
            "names, unnatural phrasing, or lines that read as literal machine output. "
            "Reply with JSON only: {\"lines\":[{\"id\":N,\"verdict\":\"ok|fix\","
            "\"problem\":\"short reason\",\"fixed\":\"corrected English or empty\"}],"
            "\"score\":0-100}. Score is overall caption quality for this batch."
            % target)
        user = "Source language: %s\n%s" % (source_lang, json.dumps(payload, ensure_ascii=False))
        data = _api({"model": REVIEWER_MODEL, "messages": [
            {"role": "system", "content": system}, {"role": "user", "content": user}],
            "response_format": {"type": "json_object"}, "temperature": 0.1, "max_tokens": 8000})
        text = (data["choices"][0]["message"]["content"] or "").strip()
        try:
            parsed = json.loads(text)
        except ValueError:
            print("review: batch at %d returned unparseable JSON (%s); splitting"
                  % (start, data["choices"][0].get("finish_reason")), file=sys.stderr)
            if len(group) > 4:
                half = len(group) // 2
                for sub in (group[:half], group[half:]):
                    sub_issues, sub_score = review(sub, source_lang, target, batch=half)
                    issues.extend(sub_issues)
                    if sub_score is not None:
                        scores.append(sub_score)
            continue
        if isinstance(parsed.get("score"), (int, float)):
            scores.append(float(parsed["score"]))
        for line in parsed.get("lines", []):
            if line.get("verdict") == "fix" and line.get("fixed"):
                fixes[line["id"]] = line["fixed"].strip()
                issues.append(line)
    for c in cues:
        if c["i"] in fixes:
            c["dst_reviewed"] = fixes[c["i"]]
        else:
            c["dst_reviewed"] = c.get("dst", "")
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
