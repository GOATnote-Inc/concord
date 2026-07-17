"""Stand up the governed evidence pipeline in Nexla and verify round-trip.

  create api_push source -> activate -> push evidence records via source webhook
  -> wait for the auto-detected NexSet -> read samples back with the session token.

Prints CONCORD_NEXSET_ID=<id> on success. Uses only stdlib + the session token env:
  NEXLA_API_URL, NEXLA_SESSION_TOKEN   (set -a; source ../loop/.../starter-kit/.env)
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

API = os.environ.get("NEXLA_API_URL", "https://dataops.nexla.io/nexla-api")
TOK = os.environ["NEXLA_SESSION_TOKEN"]
HDRS = {"Authorization": f"Bearer {TOK}",
        "Accept": "application/vnd.nexla.api.v1+json",
        "Content-Type": "application/json"}
SOURCE_NAME = "concord-evidence-gov"
SOURCE_TYPE = "nexla_rest"   # the UI "Webhook" connector (decoded from the venue CLI)


def req(method: str, path: str, body: dict | list | None = None,
        base: str | None = None, headers: dict | None = None):
    url = (base or API) + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method, headers=headers or HDRS)
    with urllib.request.urlopen(r, timeout=20) as resp:
        raw = resp.read()
        return json.loads(raw) if raw else {}


def evidence_records() -> list[dict]:
    import yaml
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "..", "data", "evidence.yaml")) as f:
        return yaml.safe_load(f)["evidence"]


def main() -> int:
    # 1. Reuse or create the api_push source.
    sources = req("GET", "/data_sources")
    src = next((s for s in sources if s.get("name") == SOURCE_NAME), None)
    if src is None:
        src = req("POST", "/data_sources",
                  {"name": SOURCE_NAME, "source_type": SOURCE_TYPE,
                   "source_config": {}})
        print(f"created source id={src['id']}")
    else:
        print(f"reusing source id={src['id']}")
    sid = src["id"]
    try:
        req("PUT", f"/data_sources/{sid}/activate")
        print("source activated")
    except urllib.error.HTTPError as e:
        print(f"activate: HTTP {e.code} (may already be active)")

    # 2. Get (or mint) the per-source ingest api key: POST /data_sources/{id}/api_keys.
    keys = req("GET", f"/data_sources/{sid}/api_keys")
    keyobj = keys[0] if keys else req("POST", f"/data_sources/{sid}/api_keys",
                                      {"name": "concord"})
    api_key = keyobj["api_key"]
    key_url = keyobj.get("url")
    print(f"api key id={keyobj['id']} url={key_url or 'null'}")

    # 3. Push the evidence records to the key's own ingest URL.
    if not key_url:
        print("FAIL: key carries no ingest url"); return 1
    records = evidence_records()
    out = req("POST", "", body=records, base=key_url,
              headers={"Content-Type": "application/json"})
    print(f"pushed {len(records)} records -> {out}")

    # 4. Wait for the auto-detected NexSet.
    nexset_id = None
    for _ in range(30):
        full = req("GET", f"/data_sources/{sid}?expand=1")
        ds = full.get("data_sets") or []
        if ds:
            nexset_id = ds[0]["id"] if isinstance(ds[0], dict) else ds[0]
            break
        time.sleep(3)
    if not nexset_id:
        print("FAIL: nexset never appeared"); return 1
    print(f"nexset id={nexset_id}")

    # 5. Read samples back (the exact call CONCORD makes at boot).
    for _ in range(30):
        try:
            samples = req("GET", f"/nexsets/{nexset_id}/samples?output_only=true")
            if samples:
                ids = sorted({(s.get("id") or "?") for s in samples if isinstance(s, dict)})
                print(f"round-trip OK: {len(samples)} records, ids={ids}")
                print(f"\nCONCORD_NEXSET_ID={nexset_id}")
                return 0
        except Exception as e:  # noqa: BLE001
            print(f"samples not ready: {e}")
        time.sleep(3)
    print("FAIL: samples never came back"); return 1


if __name__ == "__main__":
    raise SystemExit(main())
