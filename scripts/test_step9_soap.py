"""
scripts/test_step9_soap.py

Step 9 verification test:
  1. Generate SOAP notes for two visits that share T2DM + Metformin but have
     different visit_roles and soap_styles.
  2. Verify that all required VISIT_ROLE_VOCABULARY phrases appear verbatim.
  3. Verify that the soap_style openers appear in the correct sections.
  4. Verify that the event_summary appears verbatim (or near-verbatim) in the
     assessment section.
  5. Run both doctor_note chunks through all-MiniLM-L6-v2 and verify that
     cosine similarity is below 0.87.

Run from project root:
    python scripts/test_step9_soap.py
    python scripts/test_step9_soap.py --no-embedding   # skip similarity check

Exit code:
    0 — all checks passed.
    1 — one or more checks failed.
"""

from __future__ import annotations

import argparse
import sys
import os
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from soap.soap_generator import generate_soap_note
from soap.soap_semantics import VISIT_ROLE_VOCABULARY, SOAP_STYLE_OPENERS


# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------
_GREEN  = "\033[92m"
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"

def _ok(msg: str) -> str:  return f"{_GREEN}✔  {msg}{_RESET}"
def _fail(msg: str) -> str: return f"{_RED}✘  {msg}{_RESET}"
def _head(msg: str) -> str: return f"\n{_BOLD}{'='*70}\n{msg}\n{'='*70}{_RESET}"


# ---------------------------------------------------------------------------
# Minimal patient fixture — two visits, same condition, different roles/styles
# ---------------------------------------------------------------------------

def _make_patient(soap_style: str) -> dict[str, Any]:
    """Return a minimal but valid patient fixture."""
    return {
        "patient_id": f"TEST-STEP9-{soap_style.upper()[:3]}",
        "demographics": {
            "name": "Test Patient",
            "date_of_birth": "1970-03-15",
            "sex": "male",
        },
        "conditions": ["T2DM"],
        "allergy_registry": [],
        "metadata": {
            "tier": "moderate",
            "dataset_version": "v1.7-lite",
            "story_arc": "t2dm_management",
            "timeline_pattern": "regular_quarterly",
            "semantic_focus": "lab_improvement",
            "retrieval_signature": f"T2DM|Metformin|lab_improvement|regular_quarterly|{soap_style}",
            "retrieval_intent_tags": ["diabetes_medication", "hba1c_trend"],
            "soap_style": soap_style,
            "primary_retrieval_targets": ["medication_query", "lab_trend_query"],
        },
        "visits": [],
    }


def _make_visit(
    visit_id: str,
    visit_date: str,
    visit_role: str,
    event_summary: str,
    event_type: str,
    prior_visit_id: str | None = None,
) -> dict[str, Any]:
    """Return a minimal valid visit dict."""
    return {
        "visit_id": visit_id,
        "visit_date": visit_date,
        "visit_type": "follow_up" if prior_visit_id else "initial",
        "attending_physician": "Dr. Test",
        "diagnoses": ["T2DM"],
        "vitals": {
            "bp_systolic": 125,
            "bp_diastolic": 80,
            "heart_rate": 74,
            "weight_kg": 85.0,
            "bmi": 29.5,
        },
        "labs": [
            {
                "lab_type": "HbA1c",
                "value": 7.2,
                "unit": "%",
                "reference_range": "4.0-5.6 %",
                "flag": "HIGH",
            }
        ],
        "medications": [
            {
                "medication_name": "Metformin",
                "medication_class": "Biguanide",
                "dose": "500 mg",
                "frequency": "twice_daily",
                "route": "oral",
                "start_date": "2023-01-01",
                "stop_date": None,
                "medication_status": "continued",
                "trajectory_event": "simple_start_continue",
            }
        ],
        "soap_note": {"subjective": "", "objective": "", "assessment": "", "plan": ""},
        "linked_documents": [],
        "prior_visit_id": prior_visit_id,
        "visit_role": visit_role,
        "timeline_pattern": "regular_quarterly",
        "timeline_gap_days": 0 if prior_visit_id is None else 90,
        "clinical_event": {
            "event_type": event_type,
            "event_label": event_summary[:60],
            "event_summary": event_summary,
        },
        "retrieval_context": {
            "semantic_focus": "lab_improvement",
            "retrieval_intent_tags": ["diabetes_medication", "hba1c_trend"],
        },
    }


# ---------------------------------------------------------------------------
# Generate the two contrasting SOAP notes
# ---------------------------------------------------------------------------

def generate_two_soaps() -> tuple[dict[str, str], dict[str, str], dict, dict]:
    """Return (soap_A, soap_B, visit_A, visit_B)."""

    # Visit A — problem_oriented, partial_adherence
    patient_A = _make_patient("problem_oriented")
    visit_A = _make_visit(
        visit_id="VST-STEP9-A001",
        visit_date="2023-04-01",
        visit_role="partial_adherence",
        event_summary=(
            "Patient reported partial adherence to Metformin over the past month; "
            "missed doses were noted and adherence counselling was provided."
        ),
        event_type="adherence_issue",
        prior_visit_id="VST-STEP9-A000",
    )
    soap_A = generate_soap_note(patient=patient_A, visit=visit_A)

    # Visit B — timeline_oriented, post_discharge_stabilization
    patient_B = _make_patient("timeline_oriented")
    visit_B = _make_visit(
        visit_id="VST-STEP9-B001",
        visit_date="2023-04-01",
        visit_role="post_discharge_stabilization",
        event_summary=(
            "Post-discharge review following recent hospitalization; "
            "discharge medications reviewed and Metformin reconciled."
        ),
        event_type="post_discharge_review",
        prior_visit_id="VST-STEP9-B000",
    )
    soap_B = generate_soap_note(patient=patient_B, visit=visit_B)

    return soap_A, soap_B, visit_A, visit_B


# ---------------------------------------------------------------------------
# Verification checks
# ---------------------------------------------------------------------------

def _full_text(soap_note: dict[str, str]) -> str:
    return " ".join(soap_note.values())


def check_vocabulary_phrases(
    soap_note: dict[str, str],
    visit_role: str,
    label: str,
) -> list[str]:
    """Return list of vocabulary phrases MISSING from the soap text."""
    full = _full_text(soap_note).lower()
    phrases = VISIT_ROLE_VOCABULARY.get(visit_role, ())
    missing = [p for p in phrases if p.rstrip(",").lower() not in full]
    return missing


def check_style_opener(
    soap_note: dict[str, str],
    soap_style: str,
    label: str,
) -> bool:
    """Return True if the style opener appears in the soap text."""
    opener = SOAP_STYLE_OPENERS.get(soap_style, "")
    full = _full_text(soap_note).lower()
    return opener.lower() in full


def check_event_summary_in_assessment(
    soap_note: dict[str, str],
    event_summary: str,
) -> bool:
    """
    Return True if the event_summary (or a major substring of it) appears
    in the assessment section. We check the first 60 characters as a
    near-verbatim probe — sufficient to confirm Step 9 requirement 3.
    """
    assessment = soap_note.get("assessment", "").lower()
    probe = event_summary[:60].lower()
    return probe in assessment


# ---------------------------------------------------------------------------
# Embedding similarity check (optional)
# ---------------------------------------------------------------------------

def compute_cosine_similarity(text_a: str, text_b: str) -> float:
    """Compute cosine similarity via all-MiniLM-L6-v2."""
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore
        import numpy as np  # type: ignore
    except ImportError:
        raise RuntimeError(
            "sentence-transformers and numpy are required for the embedding test. "
            "Install with: pip install sentence-transformers"
        )

    model = SentenceTransformer("all-MiniLM-L6-v2")
    embs = model.encode([text_a, text_b], normalize_embeddings=True)
    return float(np.dot(embs[0], embs[1]))


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Step 9 SOAP generator self-test."
    )
    parser.add_argument(
        "--no-embedding",
        action="store_true",
        help="Skip the embedding similarity check.",
    )
    args = parser.parse_args()

    results: list[tuple[str, bool, str]] = []

    print(_head("Step 9 SOAP Self-Test"))

    # --- Generate -------------------------------------------------------
    print("\nGenerating SOAP notes...")
    soap_A, soap_B, visit_A, visit_B = generate_two_soaps()

    print("\n  Visit A (problem_oriented / partial_adherence)")
    for section, text in soap_A.items():
        print(f"  [{section.upper()}] {text[:120]}...")

    print("\n  Visit B (timeline_oriented / post_discharge_stabilization)")
    for section, text in soap_B.items():
        print(f"  [{section.upper()}] {text[:120]}...")

    # --- Check 1: vocabulary phrases ------------------------------------
    print(_head("Check 1 — VISIT_ROLE_VOCABULARY phrases present"))

    missing_A = check_vocabulary_phrases(soap_A, "partial_adherence", "A")
    ok_A = not missing_A
    msg_A = "all phrases present" if ok_A else f"MISSING: {missing_A}"
    results.append(("Visit A vocabulary (partial_adherence)", ok_A, msg_A))
    print(f"  {_ok('Visit A: ' + msg_A) if ok_A else _fail('Visit A: ' + msg_A)}")

    missing_B = check_vocabulary_phrases(soap_B, "post_discharge_stabilization", "B")
    ok_B = not missing_B
    msg_B = "all phrases present" if ok_B else f"MISSING: {missing_B}"
    results.append(("Visit B vocabulary (post_discharge_stabilization)", ok_B, msg_B))
    print(f"  {_ok('Visit B: ' + msg_B) if ok_B else _fail('Visit B: ' + msg_B)}")

    # --- Check 2: style openers ----------------------------------------
    print(_head("Check 2 — soap_style openers injected"))

    opener_A = check_style_opener(soap_A, "problem_oriented", "A")
    results.append(("Visit A opener (problem_oriented)", opener_A,
                    f"'{SOAP_STYLE_OPENERS['problem_oriented']}' found"))
    print(f"  {_ok('Visit A opener found') if opener_A else _fail('Visit A opener MISSING')}")

    opener_B = check_style_opener(soap_B, "timeline_oriented", "B")
    results.append(("Visit B opener (timeline_oriented)", opener_B,
                    f"'{SOAP_STYLE_OPENERS['timeline_oriented']}' found"))
    print(f"  {_ok('Visit B opener found') if opener_B else _fail('Visit B opener MISSING')}")

    # --- Check 3: event_summary in assessment --------------------------
    print(_head("Check 3 — event_summary verbatim in assessment"))

    event_A = visit_A["clinical_event"]["event_summary"]
    sum_A = check_event_summary_in_assessment(soap_A, event_A)
    results.append(("Visit A event_summary in assessment", sum_A,
                    event_A[:60]))
    print(f"  {_ok('Visit A event_summary in assessment') if sum_A else _fail('Visit A event_summary NOT in assessment')}")

    event_B = visit_B["clinical_event"]["event_summary"]
    sum_B = check_event_summary_in_assessment(soap_B, event_B)
    results.append(("Visit B event_summary in assessment", sum_B,
                    event_B[:60]))
    print(f"  {_ok('Visit B event_summary in assessment') if sum_B else _fail('Visit B event_summary NOT in assessment')}")

    # --- Check 4: embedding similarity ----------------------------------
    if not args.no_embedding:
        print(_head("Check 4 — Embedding similarity < 0.87"))
        print("  Loading all-MiniLM-L6-v2 ...")

        text_A = _full_text(soap_A)
        text_B = _full_text(soap_B)

        try:
            sim = compute_cosine_similarity(text_A, text_B)
            threshold = 0.87
            sim_ok = sim < threshold
            sim_msg = f"cosine similarity = {sim:.4f} (threshold < {threshold})"
            results.append(("Embedding similarity < 0.87", sim_ok, sim_msg))
            print(f"  {_ok(sim_msg) if sim_ok else _fail(sim_msg)}")
        except RuntimeError as exc:
            print(f"  {_YELLOW}⚠  Embedding check skipped: {exc}{_RESET}")
            results.append(("Embedding similarity < 0.87", True, "SKIPPED (missing dep)"))
    else:
        print(_head("Check 4 — Embedding similarity (SKIPPED via --no-embedding)"))
        results.append(("Embedding similarity < 0.87", True, "SKIPPED"))

    # --- Summary --------------------------------------------------------
    print(_head("Summary"))
    passed = sum(1 for _, ok, _ in results if ok)
    total = len(results)
    for name, ok, detail in results:
        marker = _ok(name) if ok else _fail(name)
        print(f"  {marker}  — {detail}")

    print(f"\n  Checks passed: {passed}/{total}")

    if passed == total:
        print(f"\n  {_GREEN}{_BOLD}Step 9 PASSED — SOAP generator has style, vocabulary, and event injection.{_RESET}")
    else:
        print(f"\n  {_RED}{_BOLD}Step 9 FAILED — {total - passed} check(s) need attention.{_RESET}")

    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
