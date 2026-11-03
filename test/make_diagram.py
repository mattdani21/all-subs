"""Generate the All Subs pipeline diagram as an Excalidraw file."""
import json
import os

OUT = os.path.expanduser("~/AllSubs/docs/allsubs-pipeline.excalidraw")
os.makedirs(os.path.dirname(OUT), exist_ok=True)

elements = []
_ids = set()

BLUE = "#a5d8ff"
PURPLE = "#d0bfff"
YELLOW = "#fff3bf"
GREEN = "#b2f2bb"
ORANGE = "#ffd8a8"
GRAY = "#e9ecef"
TEAL = "#c3fae8"


def _id(prefix):
    n = 1
    while "%s_%d" % (prefix, n) in _ids:
        n += 1
    _ids.add("%s_%d" % (prefix, n))
    return "%s_%d" % (prefix, n)


def text_block(label, x, y, w, h, size=16, color="#1e1e1e", align="center"):
    lines = label.split("\n")
    height = len(lines) * (size * 1.3)
    tid = _id("t")
    return {
        "type": "text", "id": tid, "x": x + 10, "y": y + (h - height) / 2,
        "width": w - 20, "height": height,
        "text": label, "originalText": label,
        "fontSize": size, "fontFamily": 1, "strokeColor": color,
        "textAlign": align, "verticalAlign": "middle",
        "autoResize": True, "lineHeight": 1.3,
        "containerId": None,
    }


def box(label, x, y, w, h, fill, size=16, dashed=False):
    rid = _id("r")
    label_el = text_block(label, x, y, w, h, size)
    tid = label_el["id"]
    shape = {
        "type": "rectangle", "id": rid, "x": x, "y": y, "width": w, "height": h,
        "roundness": {"type": 3}, "backgroundColor": fill, "fillStyle": "solid",
        "strokeColor": "#1e1e1e", "strokeWidth": 2, "opacity": 100,
        "boundElements": [{"id": tid, "type": "text"}],
    }
    if dashed:
        shape["strokeStyle"] = "dashed"
    label_el["containerId"] = rid
    elements.append(shape)
    elements.append(label_el)
    return rid


def arrow(x1, y1, x2, y2, start=None, end=None, dashed=False, label=None):
    aid = _id("a")
    dx, dy = x2 - x1, y2 - y1
    el = {
        "type": "arrow", "id": aid, "x": x1, "y": y1,
        "width": abs(dx), "height": abs(dy),
        "points": [[0, 0], [dx, dy]],
        "strokeColor": "#1e1e1e", "strokeWidth": 2,
        "endArrowhead": "arrow", "startArrowhead": None,
        "roundness": {"type": 2},
    }
    if dashed:
        el["strokeStyle"] = "dashed"
    if start:
        el["startBinding"] = {"elementId": start, "fixedPoint": [0.5, 1]}
    if end:
        el["endBinding"] = {"elementId": end, "fixedPoint": [0.5, 0]}
    if label:
        tid = _id("t")
        el["boundElements"] = [{"id": tid, "type": "text"}]
        elements.append(el)
        txt = {
            "type": "text", "id": tid,
            "x": x1 + dx / 2 - 60, "y": y1 + dy / 2 - 10,
            "width": 120, "height": 20, "text": label, "originalText": label,
            "fontSize": 14, "fontFamily": 1, "strokeColor": "#495057",
            "textAlign": "center", "verticalAlign": "middle",
            "autoResize": True, "containerId": aid,
        }
        elements.append(txt)
    else:
        elements.append(el)
    return aid


def title(label, x, y, size=28, color="#1e1e1e"):
    tid = _id("t")
    elements.append({
        "type": "text", "id": tid, "x": x, "y": y,
        "width": len(label) * size * 0.52, "height": size * 1.3,
        "text": label, "originalText": label, "fontSize": size,
        "fontFamily": 1, "strokeColor": color, "textAlign": "left",
        "verticalAlign": "top", "autoResize": True, "containerId": None,
    })


title("All Subs — how a video becomes captions", 60, 40)
title("measured on a 116-minute bilibili film: 1,052 cues, ~11 min end to end",
      60, 82, size=16, color="#757575")

steps = [
    ("video page\n<video> element, 1:56:00", BLUE, "the player is the only thing the extension touches"),
    ("probe — yt-dlp -J\ntitle · duration · subtitle list", BLUE, "no video downloaded at this point"),
    ("existing subtitles in your language?\nuse them — this is the ~2 s path", GREEN, "the fastest caption is one someone already made"),
    ("download audio\nyt-dlp -f bestaudio → 56 MB AAC", BLUE, "audio-only rendition the player would stream"),
    ("ffmpeg → 16 kHz mono WAV\n(~220 MB working file)", PURPLE, "decode + resample once; every later step reads this"),
    ("split into 5-minute chunks", PURPLE, "one whisper run per chunk; cues stream as they land"),
    ("whisper-cli large-v3-turbo\n-mc 0 · -ojf · Metal", PURPLE, "13x realtime on an M3; 30 s windows, token timestamps"),
    ("filter + split into cues\nconf · silence · repeats", YELLOW, "drops hallucinated lines over music and room tone"),
    ("translate each cue\nDeepSeek flash (or local 4B)", ORANGE, "only text leaves the machine; ~$0.03-0.07 per film"),
    ("overlay renders\nsynced to video.currentTime", GREEN, "shadow DOM, bilingual, survives fullscreen"),
]

X, W, H = 120, 460, 92
Y0, GAP = 170, 38
ys = [Y0 + i * (H + GAP) for i in range(len(steps))]
boxes = []
for i, (label, fill, note) in enumerate(steps):
    rid = box(label, X, ys[i], W, H, fill)
    boxes.append(rid)
    # side note
    box(note, 660, ys[i] + 16, 420, 60, GRAY, size=14)
    aid = _id("a")
    elements.append({
        "type": "arrow", "id": aid, "x": 580, "y": ys[i] + H / 2,
        "width": 80, "height": 0, "points": [[0, 0], [80, 0]],
        "strokeColor": "#868e96", "strokeWidth": 1.5, "strokeStyle": "dashed",
        "endArrowhead": "dot", "startArrowhead": None,
    })

for i in range(len(steps) - 1):
    elements.append({
        "type": "arrow", "id": _id("a"),
        "x": X + W / 2, "y": ys[i] + H,
        "width": 0, "height": GAP,
        "points": [[0, 0], [0, GAP]],
        "strokeColor": "#1e1e1e", "strokeWidth": 2,
        "endArrowhead": "arrow", "startArrowhead": None,
        "startBinding": {"elementId": boxes[i], "fixedPoint": [0.5, 1]},
        "endBinding": {"elementId": boxes[i + 1], "fixedPoint": [0.5, 0]},
    })

# branch: native subtitle path skips everything between step 3 and the overlay
elements.append({
    "type": "arrow", "id": _id("a"), "x": X + W, "y": ys[2] + H / 2,
    "width": 120, "height": 0, "points": [[0, 0], [120, 0]],
    "strokeColor": "#2f9e44", "strokeWidth": 2, "strokeStyle": "dashed",
    "endArrowhead": "arrow", "startArrowhead": None,
})
elements.append({
    "type": "text", "id": _id("t"), "x": X + W + 8, "y": ys[2] + H / 2 - 34,
    "width": 180, "height": 20, "text": "skip to overlay",
    "originalText": "skip to overlay", "fontSize": 14, "fontFamily": 1,
    "strokeColor": "#2f9e44", "textAlign": "left", "verticalAlign": "top",
    "autoResize": True, "containerId": None,
})

# footnote
elements.append({
    "type": "text", "id": _id("t"), "x": 120, "y": ys[-1] + H + 50,
    "width": 900, "height": 24,
    "text": "whisper sees only the WAV; ffmpeg sees only the container; the browser sees only cue JSON.",
    "originalText": "whisper sees only the WAV; ffmpeg sees only the container; the browser sees only cue JSON.",
    "fontSize": 15, "fontFamily": 1, "strokeColor": "#757575",
    "textAlign": "left", "verticalAlign": "top", "autoResize": True,
    "containerId": None,
})

# validation
ids = [e["id"] for e in elements]
assert len(ids) == len(set(ids)), "duplicate ids"
by_id = {e["id"]: e for e in elements}
for e in elements:
    for b in e.get("boundElements") or []:
        assert b["id"] in by_id, "missing bound element %s" % b["id"]
    if e.get("containerId"):
        assert e["containerId"] in by_id, "missing container"
        assert e["type"] == "text"

doc = {
    "type": "excalidraw",
    "version": 2,
    "source": "hermes-agent",
    "elements": elements,
    "appState": {"viewBackgroundColor": "#ffffff", "gridSize": None},
    "files": {},
}
with open(OUT, "w") as fh:
    json.dump(doc, fh, indent=1)
print("wrote", OUT, "elements:", len(elements), "size:", os.path.getsize(OUT))
