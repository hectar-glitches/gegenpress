#!/usr/bin/env python3
"""Serve docs/ with caching switched off.

    python3 scripts/serve.py            # http://localhost:8000
    python3 scripts/serve.py 8010       # another port

`python -m http.server` lets the browser cache index.html and the 2 MB
feed, so a rebuilt console can keep showing yesterday's render and the
only clue is that nothing you changed appears. Every response here says
no-store, so a reload is always the current build.

It also voices audio description. With AZURE_SPEECH_KEY and
AZURE_SPEECH_REGION in the environment, POST /api/tts speaks a line with
an Azure neural voice; the key stays here and never reaches the page.
Without them, GET /api/speech says so and the page uses the browser's
voice instead. See src/gegenpress/speech.py.
"""

from __future__ import annotations

import json
import pathlib
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
sys.path.insert(0, str(ROOT / "src"))
from gegenpress import speech  # noqa: E402


class NoCache(SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def _json(self, code: int, obj: dict) -> None:
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path.split("?")[0] == "/api/speech":
            return self._json(200, {"azure": speech.configured(),
                                    "voices": {k: v[1] for k, v in speech.VOICES.items()}})
        return super().do_GET()

    def do_POST(self) -> None:
        if self.path.split("?")[0] != "/api/tts":
            return self._json(404, {"error": "not found"})
        try:
            n = min(int(self.headers.get("Content-Length") or 0), 4096)
            req = json.loads(self.rfile.read(n) or b"{}")
            audio = speech.synthesize(str(req.get("text", "")), str(req.get("lang", "en")),
                                      float(req.get("rate", 1.0)), bool(req.get("excited")))
        except speech.SpeechUnavailable as e:
            return self._json(503, {"error": str(e)})
        except (ValueError, TypeError):
            return self._json(400, {"error": "bad request"})
        self.send_response(200)
        self.send_header("Content-Type", "audio/mpeg")
        self.send_header("Content-Length", str(len(audio)))
        self.end_headers()
        self.wfile.write(audio)

    def log_message(self, fmt: str, *args) -> None:
        if "304" not in (args[1] if len(args) > 1 else ""):
            super().log_message(fmt, *args)


def main() -> int:
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    handler = partial(NoCache, directory=str(DOCS))
    print(f"gegenpress console -> http://localhost:{port}   (no-store; ctrl-c to stop)")
    print("audio description: " + ("Azure neural voices" if speech.configured()
          else "browser voice (set AZURE_SPEECH_KEY and AZURE_SPEECH_REGION for Azure)"))
    try:
        ThreadingHTTPServer(("127.0.0.1", port), handler).serve_forever()
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
