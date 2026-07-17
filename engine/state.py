"""THE decision state + the beat machine. One state, two audiences render from it.

The golden path is a scripted consultation (seeded demo data, disclosed in the README);
Claude narrates the problem representation live from each ambient segment (extract.py,
cache-backed). The Sentinel gates (gates.py) are deterministic and re-run on every mutation:
model output is advisory until it passes them.
"""
from __future__ import annotations

import json
import os
import time

from . import evidence_source, extract, gates

DATA = os.path.join(os.path.dirname(__file__), "..", "data")
EVIDENCE, EVIDENCE_OK, EVIDENCE_SOURCE, EVIDENCE_SHA = evidence_source.load(
    os.path.join(DATA, "evidence.yaml"))


def load_segments() -> list[str]:
    with open(os.path.join(DATA, "golden_case.md")) as f:
        raw = f.read()
    parts = raw.split("---SEGMENT")[1:]
    return [p.split("---", 1)[1].strip() for p in parts]


SEGMENTS = load_segments()

OPTIONS = [
    {"id": 1, "title": "Stay — endoscopy now, as recommended",
     "clinician": ["EGD tonight under procedural sedation",
                   "Anticoagulation: individualized periprocedural plan [E-ANTICOAG]",
                   "Severe AS: sedation is the dominant procedural risk [E-SED-AS]"],
     "patient": ["The camera procedure tonight, asleep, to take the food out.",
                 "Your heart valve makes the sleep medicine the riskiest part."],
     "claims": ["c-time", "c-sed"]},
    {"id": 2, "title": "Negotiated plan — observed tonight, supported endoscopy in the morning",
     "clinician": ["Monitored observation overnight; NPO; secretion watch [E-SECR]",
                   "AM endoscopy with anesthesia-supported, cardiology-aware sedation [E-SED-AS]",
                   "Daughter at bedside; explicit documented limits",
                   "LIMITS (documented): if perforation occurs → comfort-focused care, no surgery"],
     "patient": ["Stay tonight. We watch you the whole time. Margaret stays.",
                 "In the morning, a dedicated anesthesia doctor — careful with your heart — "
                 "while the camera clears the food.",
                 "Written down: if something tears, we keep you comfortable. Nobody operates."],
     "claims": ["c-time", "c-secr", "c-sed"]},
    {"id": 3, "title": "Leave — with a real safety net",
     "clinician": ["Natural-history risks reviewed honestly [E-TIME][E-ANTICOAG][E-AMA-OUT]",
                   "Explicit return precautions; care remains open [E-SDM]",
                   "Insurance myth addressed [E-INS]",
                   "AMA/SDM note documents capacity + understanding"],
     "patient": ["You can choose to go home. Here is exactly what to watch for, and when to "
                 "come straight back.",
                 "Leaving does NOT cancel your insurance — that's a myth.",
                 "You stay our patient either way. The door stays open, day or night."],
     "claims": ["c-time", "c-anticoag", "c-ama", "c-ins", "c-sdm", "c-hp"]},
]

# The claim set for the case. c-hp is the STAGED HONEYPOT: the clinician's reassuring
# line from segment 3 — it exists verbatim in the transcript, is extracted into state,
# and has NO evidence binding. The grounding gate must block it every single run.
CLAIMS = [
    {"id": "c-time", "text": "", "evidence": "E-TIME", "status": "pending"},
    {"id": "c-secr", "text": "", "evidence": "E-SECR", "status": "pending"},
    {"id": "c-anticoag", "text": "", "evidence": "E-ANTICOAG", "status": "pending"},
    {"id": "c-sed", "text": "", "evidence": "E-SED-AS", "status": "pending"},
    {"id": "c-ama", "text": "", "evidence": "E-AMA-OUT", "status": "pending"},
    {"id": "c-ins", "text": "", "evidence": "E-INS", "status": "pending"},
    {"id": "c-sdm", "text": "", "evidence": "E-SDM", "status": "pending"},
    {"id": "c-hp", "text": "“Honestly, waiting until tomorrow is perfectly safe.”",
     "evidence": None, "status": "pending", "honeypot": True},
]


def initial_state() -> dict:
    st = {
        "t0": time.time(),
        "beat": 0,
        "beat_name": "title",
        "case": {"name": "Eleanor Hale", "age": 90,
                 "chief": "esophageal food bolus impaction, ~14h"},
        "problem": {"summary": "", "flags": [], "source": "pending extraction"},
        "transcript_shown": [],
        "options": [],
        "options_order": [1, 2, 3],
        "recomposed": False,
        "values": {"fears": [], "goals": [], "conditions": [], "elicited": False},
        "claims": [dict(c) for c in CLAIMS],
        "chosen_option": None,
        "teachback": {"required": list(gates.COVERAGE), "covered": [], "passed": False,
                      "attempts": 0, "needs_clinician": False, "prompt": ""},
        "capacity": {"elements": ["Understands her condition",
                                  "Understands risks + alternatives",
                                  "Reasoning is consistent with her stated values",
                                  "Communicates a clear choice"],
                     "attested": []},
        "artifacts": {"locked": True, "reason": "teach-back + capacity attestation pending",
                      "patient_plan": None, "clinical_note": None},
        "gate_log": [],
        "evidence_ok": EVIDENCE_OK,
        "evidence_source": EVIDENCE_SOURCE,
        "evidence_sha": EVIDENCE_SHA,
        "extraction_mode": extract.mode_label(),
    }
    # Populate bound-claim text from the evidence table itself (single source of truth).
    for c in st["claims"]:
        if c["evidence"]:
            e = EVIDENCE.get(c["evidence"])
            if e:
                c["text"] = e["claim"]
                c["patient_text"] = e.get("patient_claim", e["claim"])
    return st


# ---------------------------------------------------------------- beats ----

def _regate(st: dict) -> None:
    gates.grounding_check(st, EVIDENCE, EVIDENCE_OK)


def beat_1_ambient_history(st: dict) -> None:
    st["beat_name"] = "ambient: history populates"
    st["transcript_shown"].append(SEGMENTS[0])
    rep = extract.problem_representation(SEGMENTS[0])
    st["problem"] = {"summary": rep["summary"], "flags": rep["flags"],
                     "source": rep["source"]}


def beat_2_options_board(st: dict) -> None:
    st["beat_name"] = "options board (both panes)"
    st["transcript_shown"].append(SEGMENTS[1])
    st["options"] = [dict(o) for o in OPTIONS]
    _regate(st)


def beat_3_honeypot(st: dict) -> None:
    st["beat_name"] = "walking option 3 — grounding gate fires"
    st["transcript_shown"].append(SEGMENTS[2])
    for c in st["claims"]:
        c["active"] = c["id"] in ("c-time", "c-anticoag", "c-ama", "c-ins", "c-sdm", "c-hp")
    _regate(st)  # c-hp has no binding -> BLOCKED, redline left, nothing right


def beat_4_values(st: dict) -> None:
    st["beat_name"] = "values elicitation -> option 2 recomposes"
    st["transcript_shown"].append(SEGMENTS[3])
    st["values"] = {
        "fears": ["dying in a procedure room (as her husband did)"],
        "goals": ["die at home, in her own bed, when it's time"],
        "conditions": ["limits in writing", "daughter Margaret present"],
        "elicited": True,
    }
    st["options_order"] = [2, 1, 3]
    st["recomposed"] = True
    st["chosen_option"] = 2
    st["teachback"]["prompt"] = ("Eleanor, tell me back in your own words: what are we "
                                 "agreeing to, and what are the risks we talked about?")


def beat_5_teachback_stage(st: dict) -> None:
    st["beat_name"] = "teach-back gate (patient's own words)"
    st["transcript_shown"].append(SEGMENTS[4])
    # Her actual paraphrase is now on screen; the gate evaluates it only when
    # submitted via POST /teachback — verification is an explicit act, not ambient.


def beat_6_artifacts(st: dict) -> None:
    st["beat_name"] = "artifacts (only if gates allow)"
    ok, reason = gates.artifacts_unlocked(st)
    if ok:
        from artifacts.generate import ama_sdm_note, patient_plan
        st["artifacts"] = {"locked": False, "reason": "unlocked",
                           "patient_plan": patient_plan(st, EVIDENCE),
                           "clinical_note": ama_sdm_note(st, EVIDENCE)}
        gates.gate_log(st, "artifacts", "GENERATED",
                       "patient plan + AMA/SDM note (gates passed)")
    else:
        st["artifacts"]["reason"] = f"LOCKED: {reason}"
        gates.gate_log(st, "artifacts", "LOCKED", reason)


def beat_7_close(st: dict) -> None:
    st["beat_name"] = "close: one conversation, two truths, zero unverified numbers"


BEATS = [beat_1_ambient_history, beat_2_options_board, beat_3_honeypot,
         beat_4_values, beat_5_teachback_stage, beat_6_artifacts, beat_7_close]


def advance(st: dict) -> dict:
    if st["beat"] < len(BEATS):
        BEATS[st["beat"]](st)
        st["beat"] += 1
    return st


def to_json(st: dict) -> str:
    view = {k: v for k, v in st.items() if k != "t0"}
    view["elapsed_s"] = round(time.time() - st["t0"], 1)
    return json.dumps(view, indent=1)
