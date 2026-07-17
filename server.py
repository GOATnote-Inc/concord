"""CONCORD server — stdlib only. Serves the split-screen UI and the decision state;
beats advance by keyboard (space) from the UI. No chat surface exists anywhere.

    python3 server.py            # live extraction if ANTHROPIC_API_KEY is set
    CONCORD_FORCED=1 python3 server.py   # fully deterministic (make demo-forced)
"""
from __future__ import annotations

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from engine import gates, state as st  # noqa: E402

PORT = int(os.environ.get("CONCORD_PORT", "8901"))
UI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "index.html")

STATE = st.initial_state()
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            with open(UI, "rb") as f:
                self._send(200, f.read(), "text/html")
        elif self.path == "/state.json":
            with LOCK:
                self._send(200, st.to_json(STATE).encode())
        elif self.path == "/healthz":
            self._send(200, b'{"ok": true}')
        else:
            self._send(404, b'{"error": "not found"}')

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        global STATE
        with LOCK:
            if self.path == "/advance":
                st.advance(STATE)
                out = {"beat": STATE["beat"], "name": STATE["beat_name"]}
            elif self.path == "/bind":
                ok = gates.bind_claim(STATE, st.EVIDENCE,
                                      body.get("claim_id", "c-hp"),
                                      body.get("evidence_id", "E-TIME"))
                gates.grounding_check(STATE, st.EVIDENCE, st.EVIDENCE_OK)
                out = {"bound": ok}
            elif self.path == "/teachback":
                out = gates.teachback_check(STATE, body.get("words", ""))
            elif self.path == "/attest":
                el = body.get("element", "")
                if el in STATE["capacity"]["elements"] and \
                        el not in STATE["capacity"]["attested"]:
                    STATE["capacity"]["attested"].append(el)
                    gates.gate_log(STATE, "capacity", "ATTESTED", el)
                out = {"attested": STATE["capacity"]["attested"]}
            elif self.path == "/reset":
                STATE = st.initial_state()
                out = {"reset": True}
            else:
                self._send(404, b'{"error": "not found"}')
                return
        self._send(200, json.dumps(out).encode())


def main() -> None:
    mode = "FORCED/deterministic" if os.environ.get("CONCORD_FORCED") == "1" else "live-capable"
    print(f"CONCORD on http://localhost:{PORT}  ({mode}; extraction: "
          f"{STATE['extraction_mode']}; evidence table "
          f"{'OK' if STATE['evidence_ok'] else 'UNPARSEABLE -> quantified claims blocked'})")
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
