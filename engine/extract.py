"""Ambient transcript -> problem representation via Claude structured output.

Live call has a hard timeout and a checked-in cache fallback (data/segment_cache.json),
so the demo can never hang on a model call and runs fully offline with CONCORD_FORCED=1
(`make demo-forced`). The model NARRATES; it never authorizes — everything it produces
is advisory until the Sentinel gates pass it.
"""
from __future__ import annotations

import json
import os
from concurrent.futures import ThreadPoolExecutor

MODEL_ID = os.environ.get("CONCORD_MODEL", "claude-haiku-4-5-20251001")
TIMEOUT_S = float(os.environ.get("CONCORD_MODEL_TIMEOUT", "10"))
FORCED = os.environ.get("CONCORD_FORCED", "") == "1"

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
_EXEC = ThreadPoolExecutor(max_workers=2)

_TOOL = {
    "name": "problem_representation",
    "description": "Structured clinical problem representation from an ambient ED conversation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string",
                        "description": "One-sentence clinical problem representation."},
            "flags": {"type": "array", "items": {"type": "string"},
                      "description": "Safety-critical items: meds, comorbidities, limits."},
        },
        "required": ["summary", "flags"],
    },
}


def _cache() -> dict:
    with open(os.path.join(DATA, "segment_cache.json")) as f:
        return json.load(f)


def _live_call(segment: str) -> dict:
    import anthropic
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=MODEL_ID, max_tokens=300,
        system=("Extract a structured problem representation from this ambient ED "
                "conversation segment. Facts only, no advice, no invented numbers."),
        messages=[{"role": "user", "content": segment}],
        tools=[_TOOL], tool_choice={"type": "tool", "name": "problem_representation"},
    )
    block = next(b for b in msg.content if b.type == "tool_use")
    return {"summary": block.input["summary"], "flags": block.input["flags"]}


def mode_label() -> str:
    if FORCED or not os.environ.get("ANTHROPIC_API_KEY"):
        return "cached extraction (deterministic)"
    return f"{MODEL_ID} structured output (live, cache fallback)"


def problem_representation(segment: str) -> dict:
    cached = _cache()["segment1"]
    if FORCED or not os.environ.get("ANTHROPIC_API_KEY"):
        return {**cached, "source": "cache (forced/offline)"}
    try:
        out = _EXEC.submit(_live_call, segment).result(timeout=TIMEOUT_S)
        if out.get("summary") and out.get("flags"):
            return {**out, "source": f"{MODEL_ID} (live structured output)"}
    except Exception:
        pass
    return {**cached, "source": "cache (model unavailable — fallback)"}
