"""Send the All Subs review brief + code pack to a frontier model via OpenRouter."""
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.expanduser("~/AllSubs")
model, out_path = sys.argv[1], sys.argv[2]


def key():
    env = {}
    for line in open(os.path.expanduser("~/.hermes/.env")):
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k] = v.strip().strip('"')
    return env[os.environ.get("PROBE_KEY", "OPENROUTER_API_KEY")]


prompt_file = os.environ.get("PROBE_PROMPT")
if prompt_file:
    brief, pack = open(os.path.join(ROOT, prompt_file)).read(), ""
else:
    brief = open(os.path.join(ROOT, "docs/REVIEW-BRIEF.md")).read()
    pack = open(os.path.join(ROOT, "docs/review-pack.md")).read()

body = {
    "model": model,
    "messages": [
        {"role": "system", "content": "You are a principal engineer and product strategist "
                                      "reviewing an open-source project. Be concrete, critical "
                                      "and brief. Follow the evidence rules in the brief."},
        {"role": "user", "content": brief + "\n\n---\n\n" + pack},
    ],
    "max_tokens": int(os.environ.get("PROBE_MAX", "6000")),

}

base = os.environ.get("PROBE_BASE", "https://openrouter.ai/api/v1")
req = urllib.request.Request(
    base + "/chat/completions",
    data=json.dumps(body).encode(),
    headers={"Authorization": "Bearer " + key(), "Content-Type": "application/json",
             "HTTP-Referer": "https://github.com/mattdani21/all-subs",
             "X-Title": "All Subs review"})

t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=1800) as resp:
        data = json.load(resp)
except Exception as exc:
    body = getattr(exc, "read", lambda: b"")().decode()[:800]
    open(out_path, "w").write("ERROR: %s\n%s\n" % (exc, body))
    print("failed", exc)
    sys.exit(1)

text = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
usage = data.get("usage") or {}
with open(out_path, "w") as fh:
    fh.write("# Review by %s\n\n" % model)
    fh.write(text)
    fh.write("\n\n---\n_usage: %s · %.0fs_\n" % (json.dumps(usage), time.time() - t0))
print("ok", model, len(text), "chars", usage, "%.0fs" % (time.time() - t0))
