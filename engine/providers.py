"""Existing-subtitle providers.

Chain: title + year -> Wikidata -> IMDb id -> Wyzie download -> sync gate.
No API key for resolution (Wikidata is open), one free key for Wyzie.
A track is accepted only when its timing plausibly covers the film; otherwise the
caller falls back to ASR.
"""
from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request

import captions

WYZIE_DOWNLOAD = "https://sub.wyzie.io/download"
WIKIDATA = "https://query.wikidata.org/sparql"
UA = "AllSubs/0.1 (local subtitle resolver)"

AD_PATTERNS = ("wyzie", "free plan", "sub.wyzie.io")


def clean_title(raw):
    """'Shadow.2018 - (CHINESE MOVE'S CINEMA HD' -> ('Shadow', 2018)."""
    text = raw or ""
    year = None
    m = re.search(r"(19|20)\d{2}", text)
    if m:
        year = int(m.group(0))
        text = text[:m.start()]
    text = re.split(r"\s+-\s+|\s*\|\s*|\s*\(", text)[0]
    text = text.replace(".", " ").replace("_", " ")
    text = re.sub(r"\s+", " ", text).strip(" -:,")
    return text, year


def wikidata_imdb(title, year, timeout=20):
    if not title:
        return None
    label = json.dumps(title)
    year_filter = ""
    if year:
        year_filter = "FILTER(YEAR(?date) = %d)" % year
    query = (
        "SELECT ?film ?imdb ?date WHERE { "
        "?film wdt:P31/wdt:P279* wd:Q11424; rdfs:label %s@en; "
        "wdt:P577 ?date; wdt:P345 ?imdb. %s "
        "} ORDER BY DESC(?date) LIMIT 5" % (label, year_filter))
    url = WIKIDATA + "?format=json&query=" + urllib.parse.quote(query)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except Exception:
        return None
    rows = data.get("results", {}).get("bindings") or []
    return rows[0]["imdb"]["value"] if rows else None


def _key():
    captions.load_env()
    return os.environ.get("WYZIE_API_KEY")


def wyzie_download(imdb_id, language="en", timeout=30):
    key = _key()
    if not key or not imdb_id:
        return None
    params = urllib.parse.urlencode({
        "id": imdb_id, "language": language, "to": "vtt", "key": key})
    req = urllib.request.Request(WYZIE_DOWNLOAD + "?" + params,
                                 headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except Exception:
        return None


def strip_ads(cues):
    out = []
    for c in cues:
        text = (c.get("src") or "").lower()
        if any(p in text for p in AD_PATTERNS):
            continue
        out.append(c)
    return out


def accept(cues, duration):
    """Sync gate: a track must plausibly span the film, or we do not trust it."""
    if not cues or not duration:
        return False, "no duration to check against"
    if len(cues) < 50:
        return False, "only %d cues" % len(cues)
    first = min(c["start"] for c in cues)
    last = max(c["end"] for c in cues)
    if last < duration * 0.70:
        return False, "ends at %d min for a %d min film" % (last / 60, duration / 60)
    if last > duration * 1.05:
        return False, "runs %d min past the film" % ((last - duration) / 60)
    if first > duration * 0.35:
        return False, "starts %d min in" % (first / 60)
    return True, "covers %.0f-%.0f of %.0f min" % (first / 60, last / 60, duration / 60)


def find(title, duration, target="en"):
    """Return (cues, provider, language, note) or None."""
    name, year = clean_title(title)
    if not name:
        return None
    imdb_id = wikidata_imdb(name, year)
    if not imdb_id:
        return None
    text = wyzie_download(imdb_id, target)
    if not text or not text.lstrip().startswith("WEBVTT"):
        return None
    cues = captions.parse_vtt(text)
    cues = strip_ads(cues)
    ok, note = accept(cues, duration)
    if not ok:
        return {"rejected": True, "note": note, "imdb": imdb_id}
    for i, c in enumerate(cues):
        c["i"] = i
    return {"cues": cues, "imdb": imdb_id, "lang": target, "note": note}
