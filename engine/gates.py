"""Sentinel gates — CONCORD's fail-closed verification layer. Deterministic, outside the model.

Named for its sibling build SENTINEL (github.com/bGOATnote/sentinel, built earlier today):
same doctrine — the model proposes, deterministic gates dispose, nothing fails silently.

- Grounding gate: a claim renders ONLY if bound to an evidence-table id. Unbound -> BLOCKED
  (visible redline on the clinician pane, NOTHING on the patient pane). Unparseable evidence
  table -> ALL quantified claims blocked.
- Quantity gate: numbers/icon-arrays render ONLY from evidence entries whose quantified form
  is marked verified. Unverified -> the number is withheld, visibly.
- Teach-back gate: artifacts stay LOCKED until the patient's own words cover the critical-risk
  set for the chosen option (deterministic keyword-set coverage). Cap exhausted -> NEEDS
  CLINICIAN, logged, never silent.
- Scope lock: nothing in the engine may modify the evidence table or this file at runtime.
"""
from __future__ import annotations

import time

try:
    import yaml
except Exception:  # pyyaml missing -> fail closed
    yaml = None


def load_evidence(path: str) -> tuple[dict, bool]:
    """Returns (evidence_by_id, parse_ok). parse_ok=False -> block all quantified claims."""
    if yaml is None:
        return {}, False
    try:
        with open(path) as f:
            doc = yaml.safe_load(f)
        ev = {e["id"]: e for e in doc["evidence"]}
        for e in ev.values():
            assert e["claim"] and e["source"]
        return ev, True
    except Exception:
        return {}, False


def gate_log(state: dict, gate: str, action: str, detail: str) -> None:
    state["gate_log"].append({"ts": round(time.time() - state["t0"], 1),
                              "gate": gate, "action": action, "detail": detail})


def grounding_check(state: dict, evidence: dict, parse_ok: bool) -> None:
    """Re-derives every claim's render status from its binding. Fail-closed."""
    for c in state["claims"]:
        eid = c.get("evidence")
        if not parse_ok and c.get("quantified"):
            c["status"] = "BLOCKED"
            c["block_reason"] = "evidence table unparseable — all quantified claims blocked"
        elif eid and eid in evidence:
            c["status"] = "bound"
            c["citation"] = evidence[eid]["source"]
            q = evidence[eid].get("quantified") or {}
            c["show_quantity"] = bool(q.get("verified"))
            c["quantity"] = q if q.get("verified") else None
            if q and not q.get("verified"):
                c["quantity_note"] = "quantified form not yet verified — number withheld"
        else:
            if c["status"] != "BLOCKED":
                gate_log(state, "grounding", "BLOCKED",
                         f"{c['id']}: “{c['text'][:60]}…” — no source — will not display")
            c["status"] = "BLOCKED"
            c["block_reason"] = "no source — will not display"


def bind_claim(state: dict, evidence: dict, claim_id: str, evidence_id: str) -> bool:
    """Clinician binds a blocked claim to evidence: the claim is REPLACED by the
    evidence-grounded statement (we do not launder the unsupported phrasing)."""
    c = next((x for x in state["claims"] if x["id"] == claim_id), None)
    e = evidence.get(evidence_id)
    if not c or not e:
        return False
    c["original_text"] = c["text"]
    c["text"] = e["claim"]
    c["patient_text"] = e.get("patient_claim", e["claim"])
    c["evidence"] = evidence_id
    gate_log(state, "grounding", "BOUND",
             f"{claim_id} corrected + bound to [{evidence_id}] {e['source']}")
    return True


# --- teach-back -------------------------------------------------------------

TEACHBACK_CAP = 3

# Critical-risk coverage sets for the chosen option (option 2, negotiated plan).
# Deterministic: each concept passes if ANY of its keywords appears in her words.
COVERAGE = {
    "bleeding": ["bleed", "blood"],
    "perforation": ["tear", "hole", "perforat", "rip"],
    "the plan (morning scope)": ["morning", "tomorrow", "scope", "camera", "sleep medicine",
                                 "anesthesia", "put me under"],
    "agreed limits": ["comfort", "no surgery", "won't operate", "wont operate", "no operation"],
}


def teachback_check(state: dict, patient_words: str) -> dict:
    words = patient_words.lower()
    covered = [k for k, kws in COVERAGE.items() if any(w in words for w in kws)]
    missing = [k for k in COVERAGE if k not in covered]
    tb = state["teachback"]
    tb["attempts"] += 1
    tb["covered"] = sorted(set(tb["covered"]) | set(covered))
    still = [k for k in COVERAGE if k not in tb["covered"]]
    if not still:
        tb["passed"] = True
        gate_log(state, "teach-back", "PASSED",
                 f"all critical concepts covered in patient's own words "
                 f"(attempt {tb['attempts']})")
    elif tb["attempts"] >= TEACHBACK_CAP:
        tb["needs_clinician"] = True
        gate_log(state, "teach-back", "NEEDS CLINICIAN",
                 f"comprehension not verified after {TEACHBACK_CAP} attempts; "
                 f"uncovered: {', '.join(still)}")
    else:
        gate_log(state, "teach-back", "INCOMPLETE",
                 f"not yet covered: {', '.join(still)} — re-prompting")
    return {"covered_now": covered, "missing": missing, "passed": tb["passed"]}


def artifacts_unlocked(state: dict) -> tuple[bool, str]:
    if not state["teachback"]["passed"]:
        return False, "teach-back gate not passed"
    if len(state["capacity"]["attested"]) < len(state["capacity"]["elements"]):
        return False, "capacity attestation incomplete (clinician attests each element)"
    return True, "unlocked"
