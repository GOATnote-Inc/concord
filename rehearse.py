"""Golden-path rehearsal for CONCORD. Boots the server, drives every beat over HTTP,
asserts the gates behave, times the run.  PASS required before any demo.

    .venv/bin/python rehearse.py            # live-capable
    .venv/bin/python rehearse.py --forced   # fully deterministic path
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.request

PORT = 8902
BASE = f"http://127.0.0.1:{PORT}"

ELEANOR_TEACHBACK = (
    "I stay tonight, you watch me. In the morning your sleep medicine doctor puts me under, "
    "careful with my heart, and they take the food out with the camera. The blood thinner "
    "means I bleed easier, and if the tissue tears - if there's a hole - you will keep me "
    "comfortable and nobody will operate on me.")
BAD_TEACHBACK = "You'll fix it in the morning and everything will be fine."


def req(path: str, body: dict | None = None) -> dict:
    if body is None:
        with urllib.request.urlopen(f"{BASE}{path}", timeout=30) as r:
            return json.loads(r.read())
    data = json.dumps(body).encode()
    r = urllib.request.Request(f"{BASE}{path}", data=data,
                               headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(r, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> int:
    forced = "--forced" in sys.argv
    env = dict(os.environ, CONCORD_PORT=str(PORT))
    if forced:
        env["CONCORD_FORCED"] = "1"
    srv = subprocess.Popen([sys.executable, "server.py"], env=env,
                           cwd=os.path.dirname(os.path.abspath(__file__)) or ".",
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    checks: dict[str, bool] = {}
    try:
        for _ in range(40):
            try:
                req("/healthz")
                break
            except Exception:
                time.sleep(0.5)
        req("/reset", {})

        req("/advance", {})                      # b1 history
        s = req("/state.json")
        checks["extraction populated problem + apixaban flag"] = (
            bool(s["problem"]["summary"]) and any("apixaban" in f for f in s["problem"]["flags"]))
        print(f"  extraction source: {s['problem']['source']}")

        req("/advance", {})                      # b2 options
        s = req("/state.json")
        checks["three options render"] = len(s["options"]) == 3

        req("/advance", {})                      # b3 honeypot
        s = req("/state.json")
        hp = next(c for c in s["claims"] if c["id"] == "c-hp")
        checks["HONEYPOT BLOCKED by grounding gate"] = hp["status"] == "BLOCKED"
        checks["blocked claim absent from patient pane (bound-only rule)"] = hp["status"] != "bound"
        checks["gate_log records the block"] = any(
            g["action"] == "BLOCKED" for g in s["gate_log"])

        req("/bind", {"claim_id": "c-hp", "evidence_id": "E-TIME"})   # live bind
        s = req("/state.json")
        hp = next(c for c in s["claims"] if c["id"] == "c-hp")
        checks["bind replaces claim with evidence-grounded text + citation"] = (
            hp["status"] == "bound" and "24 hours" in hp["text"] and bool(hp.get("citation")))

        req("/advance", {})                      # b4 values -> recompose
        s = req("/state.json")
        checks["option 2 recomposes to top after values"] = s["options_order"][0] == 2

        req("/advance", {})                      # b5 teach-back stage
        r1 = req("/teachback", {"words": BAD_TEACHBACK})
        checks["insufficient teach-back does NOT pass"] = not r1["passed"]
        r2 = req("/teachback", {"words": ELEANOR_TEACHBACK})
        checks["her real words pass the teach-back gate"] = r2["passed"]

        req("/advance", {})                      # b6 artifacts — but capacity not attested
        s = req("/state.json")
        checks["artifacts LOCKED until capacity attested"] = s["artifacts"]["locked"]
        for el in s["capacity"]["elements"]:
            req("/attest", {"element": el})
        # regenerate now that attestation is complete: step back is not allowed, so beat 6
        # re-runs via advance? No: artifacts beat re-fires on next advance in demo we attest
        # BEFORE b6. For the harness, re-run beat 6 by resetting beat pointer via reset is
        # heavy — instead the demo order is: attest during b5, then advance. Verify that:
        req("/reset", {})
        for _ in range(5):
            req("/advance", {})                  # b1..b5
        req("/bind", {"claim_id": "c-hp", "evidence_id": "E-TIME"})
        req("/teachback", {"words": ELEANOR_TEACHBACK})
        s = req("/state.json")
        for el in s["capacity"]["elements"]:
            req("/attest", {"element": el})
        req("/advance", {})                      # b6 artifacts (gates satisfied)
        s = req("/state.json")
        art = s["artifacts"]
        checks["artifacts generate once BOTH gates pass"] = (
            not art["locked"] and bool(art["patient_plan"]) and bool(art["clinical_note"]))
        if art["clinical_note"]:
            note = art["clinical_note"]["content"]
            checks["note documents capacity attestation + teach-back VERIFIED"] = (
                len(note["capacity_assessment"]["elements_attested"]) == 4
                and note["comprehension_verification"]["result"] == "VERIFIED")
            checks["note carries evidence-bound risk table"] = (
                len(note["risk_disclosure_evidence_table"]) >= 5)
        req("/advance", {})                      # b7 close
    finally:
        srv.kill()
        srv.wait(timeout=10)

    total = time.time() - t0
    print(f"\n--- CONCORD rehearsal ({'FORCED' if forced else 'live-capable'}) ---")
    ok = True
    for k, v in checks.items():
        ok &= v
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print(f"  run time: {total:.1f}s (driver-paced)")
    print(f"=== {'PASS' if ok else 'FAIL'} ===")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
