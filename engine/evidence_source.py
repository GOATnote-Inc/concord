"""Evidence delivery layer. live mode: the curated evidence corpus is DELIVERED
through Nexla (governed, credentialed, versioned) and the grounding gate only
trusts what the governed pipeline hands it. Any failure -> local file, labeled.

    CONCORD_NEXLA=live + NEXLA_API_URL + NEXLA_SESSION_TOKEN + CONCORD_NEXSET_ID
"""
from __future__ import annotations

import json
import os
import urllib.request

from . import gates

NEXLA_URL = os.environ.get("NEXLA_API_URL", "https://dataops.nexla.io/nexla-api")
TOKEN = os.environ.get("NEXLA_SESSION_TOKEN", "")
NEXSET_ID = os.environ.get("CONCORD_NEXSET_ID", "")
LIVE = os.environ.get("CONCORD_NEXLA", "local") == "live" and TOKEN and NEXSET_ID

# Verified against this instance (nexla-prod-gcp): legacy dataset-samples endpoint;
# records come back wrapped as {"nexlaMetaData": ..., "rawMessage": {<record>}}.
RECORDS_PATH = "/data_sets/{id}/samples?output_only=1&count=50"


def _fetch_records() -> list[dict]:
    url = f"{NEXLA_URL}{RECORDS_PATH.format(id=NEXSET_ID)}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {TOKEN}",
        "Accept": "application/vnd.nexla.api.v1+json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        body = json.loads(r.read())
    if isinstance(body, dict):
        body = body.get("records") or body.get("data") or body.get("output") or []
    records = []
    for item in body:
        rec = None
        if isinstance(item, dict):
            rec = item.get("rawMessage") or item.get("record") or item.get("output") or item
        if isinstance(rec, dict) and rec.get("id") and rec.get("claim"):
            records.append(rec)
    # De-dup by id (multiple pushes accumulate samples; last write wins).
    return list({r["id"]: r for r in records}.values())


def load(yaml_path: str) -> tuple[dict, bool, str]:
    """Returns (evidence_by_id, parse_ok, source_label)."""
    if LIVE:
        try:
            records = _fetch_records()
            if records:
                ev = {r["id"]: r for r in records}
                for e in ev.values():
                    assert e["claim"] and e["source"]
                return ev, True, f"Nexla NexSet #{NEXSET_ID} (live, governed)"
        except Exception:
            pass  # fail closed into the local file, honestly labeled
    ev, ok = gates.load_evidence(yaml_path)
    return ev, ok, "local evidence.yaml (fallback)"
