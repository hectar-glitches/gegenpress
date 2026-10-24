#!/usr/bin/env python3
"""Serve docs/ with caching switched off.

    python3 scripts/serve.py            # http://localhost:8000
    python3 scripts/serve.py 8010       # another port

`python -m http.server` lets the browser cache index.html and the 2 MB
feed, so a rebuilt console can keep showing yesterday's render and the
only clue is that nothing you changed appears. Every response here says
no-store, so a reload is always the current build.
"""

from __future__ import annotations

import pathlib
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"


class NoCache(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def log_message(self, fmt: str, *args) -> None:
        if "304" not in (args[1] if len(args) > 1 else ""):
            super().log_message(fmt, *args)


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    handler = partial(NoCache, directory=str(DOCS))
    print(f"gegenpress console -> http://localhost:{port}   (no-store; ctrl-c to stop)")
    try:
        ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
