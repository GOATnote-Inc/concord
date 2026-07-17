"""The two artifacts. Generated ONLY after the teach-back gate passes and the clinician
has attested every capacity element. Every risk statement is pulled from bound claims —
the artifacts cannot contain a claim the grounding gate hasn't passed.
"""
from __future__ import annotations

import time


def _bound_claims(state: dict) -> list[dict]:
    return [c for c in state["claims"] if c["status"] == "bound"]


def _chosen(state: dict) -> dict:
    return next(o for o in state["options"] if o["id"] == state["chosen_option"])


def patient_plan(state: dict, evidence: dict) -> dict:
    """Large-print, plain-language plan. Rendered by the UI at >=20px."""
    opt = _chosen(state)
    return {
        "title": f"Your plan — {state['case']['name']}",
        "date": time.strftime("%B %d, %Y"),
        "what_we_agreed": opt["patient"],
        "why_it_fits_you": [
            "You told us your biggest fear is dying in a procedure room, and your goal is "
            "to be home, in your own bed.",
            "This plan was built around that: extra heart monitoring, Margaret with you, "
            "and your limits in writing.",
        ],
        "the_risks_in_plain_words": [c.get("patient_text", c["text"])
                                     for c in _bound_claims(state)
                                     if c["id"] in ("c-time", "c-anticoag", "c-secr", "c-sed")],
        "your_rights": [c.get("patient_text", c["text"]) for c in _bound_claims(state)
                        if c["id"] in ("c-ins", "c-sdm")],
        "come_back_immediately_if": [
            "You cannot swallow your spit, or you start drooling",
            "Chest pain, trouble breathing, or coughing when you swallow",
            "Vomiting blood, or black stools",
            "Fever or chills",
            "You simply change your mind — the door is open, day or night",
        ],
        "who_to_call": "Emergency Department, any hour: (555) 010-0911 — SYNTHETIC DEMO",
        "print_note": "large-print (min 20px); reading level target ~6th grade",
    }


def ama_sdm_note(state: dict, evidence: dict) -> dict:
    """Structured, capacity-documented SDM/AMA note. FHIR-shaped JSON (DocumentReference-
    style sections); rendered text view in the UI."""
    opt = _chosen(state)
    tb = state["teachback"]
    return {
        "resourceType": "DocumentReference",
        "status": "current",
        "type": {"text": "Shared decision-making / informed refusal note (AMA-capable)"},
        "date": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "subject": {"display": f"{state['case']['name']}, {state['case']['age']} "
                               "(SYNTHETIC PATIENT — DEMO)"},
        "content": {
            "situation": state["problem"]["summary"],
            "safety_flags": state["problem"]["flags"],
            "options_discussed": [
                {"option": o["title"],
                 "evidence_bindings": sorted({c["evidence"] for c in state["claims"]
                                              if c["id"] in o.get("claims", [])
                                              and c["status"] == "bound"
                                              and c["evidence"]})}
                for o in state["options"]],
            "patient_values_elicited": state["values"],
            "agreed_plan": {
                "option": opt["title"],
                "details": opt["clinician"],
                "documented_limits": [l for l in opt["clinician"]
                                      if l.startswith("LIMITS")],
            },
            "capacity_assessment": {
                "method": "Clinician attestation of each element (the tool structures "
                          "documentation; the CLINICIAN determines capacity)",
                "elements_attested": state["capacity"]["attested"],
                "attested_by": "Attending physician (demo placeholder)",
            },
            "comprehension_verification": {
                "method": "teach-back, deterministic critical-risk coverage",
                "attempts": tb["attempts"],
                "concepts_covered": tb["covered"],
                "result": "VERIFIED" if tb["passed"] else "NOT VERIFIED",
            },
            "risk_disclosure_evidence_table": [
                {"id": c["evidence"], "claim": c["text"], "source": c.get("citation", "")}
                for c in _bound_claims(state)],
            "return_precautions_given": True,
            "care_relationship": "continues; AMA does not terminate duty of care [E-SDM]",
        },
        "provenance": {
            "generated_by": "CONCORD (Sentinel gates)",
            "gate_log": state["gate_log"],
            "disclaimer": "Demo artifact from a synthetic case. Not for clinical use "
                          "without local review.",
        },
    }
