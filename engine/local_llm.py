"""On-device translation via llama.cpp — opt-in offline mode.

Runs one llama-server for the duration of a job and speaks the OpenAI-compatible
chat API, so the same prompt code as the cloud path is reused.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.request

HOME = os.path.expanduser("~")
LLAMA_SERVER = shutil.which("llama-server") or "/opt/homebrew/bin/llama-server"
PORT = int(os.environ.get("ALLSUBS_LOCAL_PORT", "8091"))

CANDIDATES = [
    os.path.join(HOME, "AllSubs", "models", "Qwen3-4B-Instruct-2507-Q4_K_M.gguf"),
    os.path.join(HOME, "AllSubs", "models", "qwen3-4b-instruct-q4_k_m.gguf"),
    os.path.join(HOME, "AllSubs", "models", "Qwen3-4B-Q4_K_M.gguf"),
    os.path.join(HOME, "orchestrator-work", "ModelSwapper", "models", "Qwen3-4B-Q4_K_M.gguf"),
]


def model_path():
    env = os.environ.get("ALLSUBS_LOCAL_MODEL")
    if env and os.path.exists(env):
        return env
    for path in CANDIDATES:
        if os.path.exists(path):
            return path
    return None


def available():
    return bool(model_path()) and os.path.exists(LLAMA_SERVER)


class LocalTranslator(object):
    def __init__(self, path=None, port=PORT, threads=6):
        self.path = path or model_path()
        self.port = port
        self.threads = threads
        self.proc = None
        if not self.path:
            raise RuntimeError(
                "no local model found; set ALLSUBS_LOCAL_MODEL or put a GGUF in "
                "~/AllSubs/models/")

    def __enter__(self):
        model = str(self.path)
        self.proc = subprocess.Popen(
            [LLAMA_SERVER, "-m", model, "--port", str(self.port), "-c", "4096",
             "--no-webui", "-t", str(self.threads)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        deadline = time.time() + 180
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("llama-server exited while loading (out of memory?)")
            try:
                urllib.request.urlopen(
                    "http://127.0.0.1:%d/health" % self.port, timeout=2)
                return self
            except Exception:
                time.sleep(0.5)
        self.__exit__(None, None, None)
        raise RuntimeError("llama-server did not become ready")

    def __exit__(self, *exc):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=20)
            except subprocess.TimeoutExpired:
                self.proc.kill()
        self.proc = None
        return False

    def chat_json(self, system, user, max_tokens=1200, temperature=0.2):
        payload = {
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
        }
        req = urllib.request.Request(
            "http://127.0.0.1:%d/v1/chat/completions" % self.port,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=900) as resp:
            data = json.load(resp)
        content = data["choices"][0]["message"]["content"]
        try:
            return json.loads(content)
        except ValueError:
            # small models sometimes wrap JSON in prose or fences
            start, end = content.find("{"), content.rfind("}")
            if start >= 0 and end > start:
                return json.loads(content[start:end + 1])
            raise
