"""One-shot handoff server: serves exactly one installer and one source archive
under a random token, then dies. No shell, no directory listing, no reuse.
"""
from __future__ import annotations

import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = sys.argv[1]
TOKEN = sys.argv[2]
PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 8790
TTL = int(sys.argv[4]) if len(sys.argv) > 4 else 900
ARCHIVE = os.path.join(ROOT, "dist", "AllSubs-src.tgz")

INSTALL = """#!/bin/bash
# All Subs one-shot installer — fetches the archive, runs setup, exits.
set -u
BASE="http://{host}:{port}/{token}"
cd "$HOME" || exit 1
echo "downloading All Subs..."
curl -fsSL "$BASE/AllSubs-src.tgz" -o AllSubs-src.tgz || exit 1
tar xzf AllSubs-src.tgz || exit 1
cd AllSubs || exit 1
chmod +x allsubs
./allsubs setup
echo
echo "Setup finished. Now:"
echo "  printf 'DEEPSEEK_API_KEY=%%s\\\\n' 'sk-...' > ~/AllSubs/.env"
echo "  cd ~/AllSubs && ./allsubs start"
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        sys.stderr.write("handoff %s\n" % (format % args))

    def _send(self, body, ctype):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/%s/install.sh" % TOKEN:
            host = self.headers.get("Host") or ("127.0.0.1:%d" % PORT)
            return self._send(
                INSTALL.format(host=host.split(":")[0], port=PORT, token=TOKEN),
                "text/x-shellscript")
        if self.path == "/%s/AllSubs-src.tgz" % TOKEN:
            if not os.path.exists(ARCHIVE):
                self.send_error(404)
                return
            with open(ARCHIVE, "rb") as fh:
                return self._send(fh.read(), "application/gzip")
        self.send_error(404)


def expire(server):
    time.sleep(TTL)
    server.shutdown()


def main():
    if not os.path.exists(ARCHIVE):
        print("missing archive: %s" % ARCHIVE)
        sys.exit(1)
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    threading.Thread(target=expire, args=(server,), daemon=True).start()
    print("handoff live on port %d for %d min (token %s)" % (PORT, TTL // 60, TOKEN))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
