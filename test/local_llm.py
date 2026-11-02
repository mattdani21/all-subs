"""Measure a local GGUF model as a subtitle translator: quality sample + tok/s."""
import json
import subprocess
import sys
import time
import urllib.request

MODELS = [
    ("Qwen3-4B", "/Users/matt/orchestrator-work/ModelSwapper/models/Qwen3-4B-Q4_K_M.gguf"),
    ("Qwen3-8B", "/Users/matt/orchestrator-work/ModelSwapper/models/Qwen3-8B-Q4_K_M.gguf"),
]
LINES = [
    "你比都督还像都督", "以前我是你的都督", "以后我还是你的都督", "如此而已",
    "杨家刀房", "你等需以女人的身形入配伞", "主公为何一定要让都督弹琴啊",
    "叔父生性暴力", "这是你在这里的最后一晚", "刺客逆贼，已被本都督当场击杀",
]

SYSTEM = ("/no_think You are a world-class subtitle translator for feature films. "
          "Translate each numbered line into English. Keep lines under 90 characters. "
          'Reply with JSON only: {"t": {"<index>": "<translation>"}}.')


def wait_ready(port, timeout=120):
    end = time.time() + timeout
    while time.time() < end:
        try:
            urllib.request.urlopen("http://127.0.0.1:%d/health" % port, timeout=2)
            return True
        except Exception:
            time.sleep(0.5)
    return False


def run(name, path, port=8091):
    proc = subprocess.Popen(
        ["llama-server", "-m", path, "--port", str(port), "-c", "4096",
         "--no-webui", "-t", "6"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        if not wait_ready(port):
            print(name, "did not start")
            return
        payload = {
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": json.dumps(
                             [{"i": i, "text": t} for i, t in enumerate(LINES)],
                             ensure_ascii=False)}],
            "temperature": 0.2, "max_tokens": 700,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            "http://127.0.0.1:%d/v1/chat/completions" % port,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=600) as r:
            d = json.load(r)
        dt = time.time() - t0
        usage = d.get("usage", {})
        content = d["choices"][0]["message"]["content"]
        tps = usage.get("completion_tokens", 0) / dt if dt else 0
        print("== %s  %.1fs  out_tokens=%s  %.1f tok/s" % (
            name, dt, usage.get("completion_tokens"), tps))
        try:
            table = json.loads(content).get("t", {})
            for k in sorted(table, key=int)[:10]:
                print("   ", LINES[int(k)], "->", table[k])
        except Exception:
            print("   RAW:", content[:500])
    finally:
        proc.terminate()
        proc.wait(timeout=20)
        time.sleep(1)


def total_ram_gb():
    return int(subprocess.check_output(["sysctl", "-n", "hw.memsize"])) / 1073741824.0


if __name__ == "__main__":
    only = sys.argv[1] if len(sys.argv) > 1 else None
    if total_ram_gb() < 16 and not only:
        print("RAM %.0f GB: refusing to sweep 8B models, they thrash this machine" % total_ram_gb())
        MODELS = MODELS[:1]
    for name, path in MODELS:
        if only and only not in name:
            continue
        run(name, path)
