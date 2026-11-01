"""Unit tests for the caption pipeline's pure functions."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine"))

import captions  # noqa: E402


def test_pick_native_subs():
    meta = {"subtitles": {"zh-Hans": [], "en": []}}
    assert captions.pick_native_subs(meta, "en")[0] == "en"
    assert captions.pick_native_subs(meta, "zh")[0] == "zh-Hans"
    assert captions.pick_native_subs({"subtitles": {}}, "en") is None
    # a track in a language we do not speak is not "good enough": generate instead
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
    sys.exit(1 if failures else 0)
