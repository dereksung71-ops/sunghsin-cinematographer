#!/usr/bin/env python3
"""Rebuild the site, then preview it at http://localhost:8000

The browser is told never to cache anything, so every refresh shows the
latest build. Stop with Ctrl+C.

Usage:
    python3 serve.py
"""

import functools
import http.server
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"
PORT = 8000


class NoCacheHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-store, max-age=0")
        super().end_headers()


def main():
    subprocess.run([sys.executable, str(ROOT / "build.py")], check=True)
    handler = functools.partial(NoCacheHandler, directory=str(DIST))
    with http.server.ThreadingHTTPServer(("", PORT), handler) as server:
        print("\nPreview: http://localhost:{}  (Ctrl+C to stop)".format(PORT))
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped.")


if __name__ == "__main__":
    main()
