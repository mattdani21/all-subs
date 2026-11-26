"""Unit & integration tests for All Subs engine, optimizations, and publish artefacts."""
import array
import gzip
import http.client
import json
import os
import struct
import sys
import tempfile
import threading
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "engine"))

import captions  # noqa: E402
import providers  # noqa: E402
import server  # noqa: E402


def test_pick_native_subs():
    meta = {"subtitles": {"zh-Hans": [], "en": []}}
    assert captions.pick_native_subs(meta, "en")[0] == "en"
    assert captions.pick_native_subs(meta, "zh")[0] == "zh-Hans"
    assert captions.pick_native_subs({"subtitles": {}}, "en") is None
    assert captions.pick_native_subs({"subtitles": {"fr": []}}, "en") is None


def test_parse_srt():
    srt = """1
00:00:01,000 --> 00:00:02,500
Hello <i>there</i>

2
00:00:03,000 --> 00:00:04,000
World
"""
    cues = captions.parse_srt(srt)
    assert len(cues) == 2
    assert cues[0]["src"] == "Hello there"
    assert cues[0]["start"] == 1.0 and cues[0]["end"] == 2.5


def test_split_display_cjk():
    cues = captions.split_display([
        {"start": 0.0, "end": 6.0, "src": "这是一句很长很长的台词，需要被切分成两条字幕显示。另一句也在这里。"}
    ])
    assert len(cues) >= 2
    assert cues[0]["start"] == 0.0
    assert cues[-1]["end"] == 6.0
    assert all(c["end"] > c["start"] for c in cues)


def test_split_display_short_untouched():
    cues = captions.split_display([{"start": 0, "end": 2, "src": "Short line"}])
    assert len(cues) == 1


def test_filter_drops_repeats_and_artifacts():
    segs = [
        {"start": 0, "end": 30, "src": "中文字幕志愿者", "conf": 0.99},
        {"start": 30, "end": 60, "src": "中文字幕志愿者", "conf": 0.99},
        {"start": 60, "end": 90, "src": "中文字幕志愿者", "conf": 0.99},
        {"start": 100, "end": 103, "src": "小爱等你呢", "conf": 0.95},
    ]
    out = captions.filter_segments(segs, [], "zh")
    assert [c["src"] for c in out] == ["小爱等你呢"]


def test_filter_drops_low_confidence():
    segs = [{"start": 0, "end": 2, "src": "maybe", "conf": 0.2}]
    assert captions.filter_segments(segs, [], "en") == []


def test_filter_drops_silence_backed():
    segs = [{"start": 0, "end": 20, "src": "Thank you.", "conf": 0.95}]
    assert captions.filter_segments(segs, [(0.0, 19.0)], "en") == []


def test_to_vtt():
    cues = [{"start": 1.5, "end": 3.0, "src": "源", "dst": "target"}]
    vtt = captions.to_vtt(cues)
    assert "00:00:01.500 --> 00:00:03.000" in vtt
    assert "target" in vtt


def test_is_mostly_silent():
    assert captions.is_mostly_silent([(0.0, 295.0)], 300.0) is True
    assert captions.is_mostly_silent([(0.0, 100.0)], 300.0) is False
    assert captions.is_mostly_silent([], 300.0) is False


def test_plan_chunks_schedule_with_first_index():
    plan = captions.plan_chunks(500.0, chunk_seconds=300, start_at=120.0,
                                first_index=100, schedule=[180, 300])
    assert plan == [(100, 120.0, 180.0), (101, 300.0, 200.0)]


def test_match_offset_one_to_one_and_wide_window():
    # Track is 14 seconds late; repeated phrase must NOT match the same cue twice
    cues = [
        {"start": 100.0, "end": 102.0, "src": "Wait for the signal"},
        {"start": 110.0, "end": 112.0, "src": "Open the north gate now"},
        {"start": 120.0, "end": 122.0, "src": "Bring the commander here"},
    ]
    observations = [
        (114.0, "Wait for the signal"),
        (115.0, "Wait for the signal"),  # duplicate observation must not reuse cue 0
        (124.2, "Open the north gate now"),
        (134.1, "Bring the commander here"),
    ]
    diffs, count = captions._match_offset(observations, cues, window=30.0)
    assert count == 3, "expected strict one-to-one count=3, got %d" % count
    diffs.sort()
    assert abs(diffs[1] - 14.1) < 0.2


def test_snap_to_onsets_fast_and_accurate():
    # Generate a 2.0s 16 kHz mono WAV: 0.0-0.60s quiet, 0.60-1.50s loud tone
    rate = 16000
    samples = array.array("h", [0] * (rate * 2))
    for i in range(int(0.60 * rate), int(1.50 * rate)):
        samples[i] = 12000 if (i % 16) < 8 else -12000
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        with wave.open(path, "wb") as fh:
            fh.setnchannels(1)
            fh.setsampwidth(2)
            fh.setframerate(rate)
            fh.writeframes(samples.tobytes())
        cues = [{"start": 0.25, "end": 1.40, "src": "Hello"}]
        out = captions.snap_to_onsets(cues, path)
        assert 0.56 <= out[0]["start"] <= 0.64, "expected snap near 0.60s, got %s" % out[0]["start"]
    finally:
        os.remove(path)


def test_translate_cues_compact_prefix_cache_and_nonverbal():
    seen = []

    def fake_llm(system, user, max_tokens=4096):
        seen.append((system, user))
        # Parse compact JSON object after "LINES:\n"
        raw = user.split("LINES:\n", 1)[1]
        mapping = json.loads(raw)
        assert isinstance(mapping, dict), "expected compact key->text JSON object"
        return {"t": {k: "EN:" + v for k, v in mapping.items()}}

    cues = [
        {"i": 0, "src": "♪"},
        {"i": 1, "src": "你好"},
        {"i": 2, "src": "世界"},
        {"i": 3, "src": "再见"},
        {"i": 4, "src": "谢谢"},
    ]
    ctx = {"title": "Shadow", "synopsis": "A decoy replaces a general.",
           "register": "formal period drama", "glossary": {"子虞": "Ziyu", "境州": "Jingzhou"}}
    out = captions.translate_cues(cues, "en", ctx, batch=2, llm=fake_llm, workers=2)
    assert out[0] == "♪"  # non-verbal skipped LLM and preserved
    assert out[1] == "EN:你好" and out[4] == "EN:谢谢"
    assert len(seen) == 2
    # Deterministic identical system prompt across batches for prompt-prefix caching
    assert seen[0][0] == seen[1][0]
    assert "FILM: Shadow" in seen[0][0]
    assert "REGISTER: formal period drama" in seen[0][0]
    assert "GLOSSARY:" in seen[0][0]
    # Second batch receives rolling context from first batch
    assert "PREV (context only):" in seen[1][1]


def test_translate_cues_auto_halves_on_truncation():
    calls = []

    def flaky_llm(system, user, max_tokens=4096):
        mapping = json.loads(user.split("LINES:\n", 1)[1])
        calls.append(len(mapping))
        if len(mapping) > 10:
            raise ValueError("truncated json")
        return {"t": {k: "OK:" + v for k, v in mapping.items()}}

    cues = [{"i": i, "src": "Line %d" % i} for i in range(16)]
    out = captions.translate_cues(cues, "en", {}, batch=16, llm=flaky_llm)
    assert len(out) == 16
    assert calls[0] == 16 and 8 in calls


def test_providers_clean_title_and_accept_gate():
    assert providers.clean_title("Shadow.2018 - (CHINESE MOVIE HD)") == ("Shadow", 2018)
    ok, _ = providers.accept(
        [{"start": float(i * 100), "end": float(i * 100 + 2)} for i in range(1, 60)], 6200)
    assert ok is True
    bad, note = providers.accept(
        [{"start": float(i * 100), "end": float(i * 100 + 2)} for i in range(1, 80)], 6000)
    assert bad is False and "past the film" in note


def test_server_http_options_xss_gzip_and_413():
    httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    port = httpd.server_address[1]
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    job_id = "testjob999"
    j = server.Job(job_id, "https://example.com/v", "en")
    j.title = "<script>alert(1)</script>"
    j.status = "done"
    j.stage = "Captions ready"
    j.add_cues([{"start": float(i), "end": float(i + 1), "src": "line %d" % i, "dst": "hello %d" % i}
                for i in range(100)])
    server.JOBS[job_id] = j
    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        # 1. OPTIONS preflight must succeed (204, no AttributeError on bytes)
        conn.request("OPTIONS", "/api/jobs")
        r = conn.getresponse()
        r.read()
        assert r.status == 204, "expected 204 on OPTIONS, got %d" % r.status

        # 2. HTML dashboard must escape title (no XSS)
        conn.request("GET", "/jobs")
        r = conn.getresponse()
        body = r.read().decode()
        assert r.status == 200
        assert "<script>alert(1)</script>" not in body
        assert "&lt;script&gt;alert(1)&lt;/script&gt;" in body

        # 3. Gzip compression on large /cues payload
        conn.request("GET", "/api/jobs/%s/cues?from=0" % job_id,
                     headers={"Accept-Encoding": "gzip"})
        r = conn.getresponse()
        raw = r.read()
        assert r.status == 200
        assert r.getheader("Content-Encoding") == "gzip"
        decoded = json.loads(gzip.decompress(raw).decode())
        assert decoded["total"] == 100 and len(decoded["cues"]) == 100

        # 4. Invalid pagination parameter returns 400 (not 500)
        conn.request("GET", "/api/jobs/%s/cues?from=nope" % job_id)
        r = conn.getresponse()
        r.read()
        assert r.status == 400

        # 5. Oversized POST returns 413
        conn.request("POST", "/api/jobs", body=b"{}",
                     headers={"Content-Type": "application/json",
                              "Content-Length": str(server.MAX_POST_BYTES + 10)})
        r = conn.getresponse()
        r.read()
        assert r.status == 413
        conn.close()
    finally:
        server.JOBS.pop(job_id, None)
        httpd.shutdown()
        httpd.server_close()


def test_extension_manifest_and_icons():
    manifest_path = os.path.join(ROOT, "extension", "manifest.json")
    with open(manifest_path) as fh:
        m = json.load(fh)
    assert m["manifest_version"] == 3
    assert m["version"] == captions.VERSION == server.VERSION
    assert len(m["description"]) <= 132
    icons = m.get("icons") or {}
    assert set(icons.keys()) >= {"16", "48", "128"}
    for sz_str, rel in icons.items():
        p = os.path.join(ROOT, "extension", rel)
        assert os.path.isfile(p), "missing icon " + p
        with open(p, "rb") as f:
            head = f.read(24)
        assert head[:8] == b"\x89PNG\r\n\x1a\n"
        w, h = struct.unpack(">II", head[16:24])
        assert (w, h) == (int(sz_str), int(sz_str))


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok   ", name)
            except AssertionError as exc:
                failures += 1
                print("FAIL ", name, exc)
            except Exception as exc:
                failures += 1
                print("ERR  ", name, repr(exc))
    sys.exit(1 if failures else 0)
