"""
scripts/run_step8_validation.py

Step 8 — Full end-to-end generation + validation for v1.7 Lite dataset.

Covers:
  Part 1 — Run generation pipeline in memory and collect counts.
  Part 2 — Run V1-V12 validation and report FAIL/WARN counts.
  Part 3 — Run 10 negative tests (each must fire the stated rule).
  Part 4 — Verify 5 patient-specific scenarios.
  Part 5 — Print the final status report.

Do NOT modify any generator or validator files.
Do NOT generate SOAP text.  Do NOT ingest into ChromaDB.  Do NOT call any LLM.
"""

from __future__ import annotations

import copy
import sys
import os

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path when executed from scripts/
# ---------------------------------------------------------------------------
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ---------------------------------------------------------------------------
# Imports — generators
# ---------------------------------------------------------------------------
from generators.patient_generator import generate_patients
from generators.visit_generator import generate_visits_for_patient
from generators.medication_generator import generate_medications_for_patient
from generators.lab_generator import generate_labs_for_patient
from generators.allergy_generator import generate_allergy_registry_for_patient
from config.patient_blueprints import BLUEPRINT_BY_ID

# ---------------------------------------------------------------------------
# Imports — validators
# ---------------------------------------------------------------------------
from validators.rules import (
    run_all_rules,
    validate_v12_dataset_diversity,
    FAIL,
    WARN,
)

# ---------------------------------------------------------------------------
# ANSI colour helpers (no third-party deps)
# ---------------------------------------------------------------------------
_GREEN  = "\033[92m"
_RED    = "\033[91m"
_YELLOW = "\033[93m"
_CYAN   = "\033[96m"
_BOLD   = "\033[1m"
_RESET  = "\033[0m"

def _pass(msg: str) -> str: return f"{_GREEN}✔  {msg}{_RESET}"
def _fail(msg: str) -> str: return f"{_RED}✘  {msg}{_RESET}"
def _warn(msg: str) -> str: return f"{_YELLOW}⚠  {msg}{_RESET}"
def _head(msg: str) -> str: return f"\n{_BOLD}{_CYAN}{'='*70}\n{msg}\n{'='*70}{_RESET}"


# ===========================================================================
# PART 1 — Generation pipeline
# ===========================================================================

def run_part1() -> list[dict]:
    print(_head("PART 1 — Generation Pipeline"))

    patients = generate_patients(mode="v17_lite")

    total_visits      = 0
    total_medications = 0
    total_labs        = 0
    total_allergies   = 0

    for patient in patients:
        blueprint = BLUEPRINT_BY_ID[patient["patient_id"]]
        generate_visits_for_patient(patient, blueprint)
        generate_medications_for_patient(patient, blueprint)
        generate_labs_for_patient(patient, blueprint)
        generate_allergy_registry_for_patient(patient, blueprint)

        total_visits      += len(patient.get("visits", []))
        for visit in patient.get("visits", []):
            total_medications += len(visit.get("medications", []))
            total_labs        += len(visit.get("labs", []))
        total_allergies   += len(patient.get("allergy_registry", []))

    print(f"  Total patients generated : {len(patients)}")
    print(f"  Total visits             : {total_visits}")
    print(f"  Total medication records : {total_medications}")
    print(f"  Total lab records        : {total_labs}")
    print(f"  Total allergy records    : {total_allergies}")

    # Store counts globally for Part 5
    global _P1_COUNTS
    _P1_COUNTS = {
        "patients"   : len(patients),
        "visits"     : total_visits,
        "medications": total_medications,
        "labs"       : total_labs,
        "allergies"  : total_allergies,
    }

    return patients


# ===========================================================================
# PART 2 — Run V1–V12 validation on generated dataset
# ===========================================================================

def run_part2(patients: list[dict]) -> tuple[int, int, bool, list[dict]]:
    print(_head("PART 2 — V1–V12 Validation"))

    summary = run_all_rules(patients, strict_diversity=True)

    fail_count = summary.fail_count
    warn_count = summary.warn_count
    passed     = summary.passed

    fail_issues = [i.as_dict() for i in summary.issues if i.severity == FAIL]

    print(f"  FAIL issues : {fail_count}")
    print(f"  WARN issues : {warn_count}")
    print(f"  Dataset passes (zero FAIL) : {passed}")

    if fail_issues:
        print(f"\n  {_RED}FAIL details:{_RESET}")
        for issue in fail_issues:
            print(f"    [{issue['rule_id']}] {issue['patient_id']} | {issue['path']} | {issue['message']}")
    else:
        print(f"  {_GREEN}No FAIL issues — dataset is clean.{_RESET}")

    return fail_count, warn_count, passed, fail_issues


# ===========================================================================
# PART 3 — Negative tests
# ===========================================================================

# Shared: build a valid deep-copy base patient to inject violations into.
def _base_patient(patients: list[dict]) -> dict:
    """Return a deep copy of the first generated patient for mutation tests."""
    return copy.deepcopy(patients[0])


def _check_fired(issues: list, expected_rule: str) -> tuple[bool, str]:
    """Return (caught, detail_msg)."""
    matching = [i for i in issues if i.get("rule_id") == expected_rule and i.get("severity") == FAIL]
    if matching:
        return True, f"Rule {expected_rule} fired — {matching[0]['message']}"
    all_rules = list({i.get("rule_id") for i in issues if i.get("severity") == FAIL})
    return False, f"Expected {expected_rule} FAIL; got FAILs from: {all_rules}"


def run_part3(patients: list[dict]) -> tuple[int, list[tuple[str, bool, str]]]:
    print(_head("PART 3 — Negative Tests (10 violations)"))

    results: list[tuple[str, bool, str]] = []  # (description, caught, detail)

    # -----------------------------------------------------------------------
    # Test 1: medication_status = "invalid_status" → V11 FAIL
    # -----------------------------------------------------------------------
    test_name = 'T1: medication_status="invalid_status" → V11'
    p = _base_patient(patients)
    # Inject into first available medication
    for visit in p.get("visits", []):
        if visit.get("medications"):
            visit["medications"][0]["medication_status"] = "invalid_status"
            break
    issues = [i.as_dict() for i in run_all_rules([p]).issues]
    caught, detail = _check_fired(issues, "V11")
    # V7 also fires for invalid enum — accept either or both, but V11 must fire
    v11_fired = any(i["rule_id"] == "V11" and i["severity"] == FAIL for i in issues)
    results.append((test_name, v11_fired, detail))
    print(f"  {_pass(test_name)}" if v11_fired else f"  {_fail(test_name)} — {detail}")

    # -----------------------------------------------------------------------
    # Test 2: timeline_events field added to a visit → V10 FAIL
    # -----------------------------------------------------------------------
    test_name = 'T2: timeline_events in visit → V10'
    p = _base_patient(patients)
    if p.get("visits"):
        p["visits"][0]["timeline_events"] = ["event_a", "event_b"]
    issues = [i.as_dict() for i in run_all_rules([p]).issues]
    v10_fired = any(i["rule_id"] == "V10" and i["severity"] == FAIL for i in issues)
    results.append((test_name, v10_fired, "V10 fired" if v10_fired else "V10 NOT fired"))
    print(f"  {_pass(test_name)}" if v10_fired else f"  {_fail(test_name)}")

    # -----------------------------------------------------------------------
    # Test 3: Duplicate retrieval_signature across two patients → V12 FAIL
    # -----------------------------------------------------------------------
    test_name = 'T3: duplicate retrieval_signature → V12'
    p1 = copy.deepcopy(patients[0])
    p2 = copy.deepcopy(patients[1])
    # Force p2 to carry p1's signature
    p2["metadata"]["retrieval_signature"] = p1["metadata"]["retrieval_signature"]
    issues = [i.as_dict() for i in run_all_rules([p1, p2]).issues]
    v12_fired = any(i["rule_id"] == "V12" and i["severity"] == FAIL for i in issues)
    results.append((test_name, v12_fired, "V12 fired" if v12_fired else "V12 NOT fired"))
    print(f"  {_pass(test_name)}" if v12_fired else f"  {_fail(test_name)}")

    # -----------------------------------------------------------------------
    # Test 4: CKD added to a moderate-tier patient → V7 FAIL
    # -----------------------------------------------------------------------
    test_name = 'T4: CKD in moderate-tier patient → V7'
    # Find a moderate patient
    mod_patient = next(
        p for p in patients if p.get("metadata", {}).get("tier") == "moderate"
    )
    p = copy.deepcopy(mod_patient)
    p["conditions"] = list(p["conditions"]) + ["CKD", "T2DM", "HTN"]
    # Ensure unique conditions
    p["conditions"] = list(dict.fromkeys(p["conditions"]))
    issues = [i.as_dict() for i in run_all_rules([p]).issues]
    v7_fired = any(
        i["rule_id"] == "V7" and i["severity"] == FAIL and "CKD" in i.get("message", "")
        for i in issues
    )
    results.append((test_name, v7_fired, "V7 CKD rule fired" if v7_fired else "V7 CKD rule NOT fired"))
    print(f"  {_pass(test_name)}" if v7_fired else f"  {_fail(test_name)}")

    # -----------------------------------------------------------------------
    # Test 5: lab_type = "BP" in a visit lab → V9 FAIL
    # -----------------------------------------------------------------------
    test_name = 'T5: lab_type="BP" in visit → V9'
    p = _base_patient(patients)
    # Find or create a lab entry
    injected = False
    for visit in p.get("visits", []):
        if visit.get("labs"):
            visit["labs"][0]["lab_type"] = "BP"
            injected = True
            break
    if not injected:
        # inject a synthetic lab
        for visit in p.get("visits", []):
            visit.setdefault("labs", []).append({
                "lab_type": "BP",
                "value": 130,
                "unit": "mmHg",
                "reference_range": "<120",
                "flag": "HIGH",
            })
            break
    issues = [i.as_dict() for i in run_all_rules([p]).issues]
    v9_fired = any(i["rule_id"] == "V9" and i["severity"] == FAIL for i in issues)
    results.append((test_name, v9_fired, "V9 fired" if v9_fired else "V9 NOT fired"))
    print(f"  {_pass(test_name)}" if v9_fired else f"  {_fail(test_name)}")

    # -----------------------------------------------------------------------
    # Test 6: trajectory_event="adherence_interruption" on Amlodipine (non-target) → V11 FAIL
    # -----------------------------------------------------------------------
    test_name = 'T6: adherence_interruption on Amlodipine (non-target) → V11'
    # PAT-CHR-001 has T2DM+HTN; Metformin is adherence target; Amlodipine is NOT.
    chr001 = next(
        p for p in patients if p.get("patient_id") == "PAT-CHR-001"
    )
    p = copy.deepcopy(chr001)
    # Inject adherence_interruption on Amlodipine
    for visit in p.get("visits", []):
        for med in visit.get("medications", []):
            if med.get("medication_name") == "Amlodipine":
                med["trajectory_event"] = "adherence_interruption"
    issues = [i.as_dict() for i in run_all_rules([p]).issues]
    v11_t6 = any(
        i["rule_id"] == "V11" and i["severity"] == FAIL
        and "adherence_interruption" in i.get("message", "")
        for i in issues
    )
    results.append((test_name, v11_t6, "V11 adherence_interruption rule fired" if v11_t6 else "V11 NOT fired"))
    print(f"  {_pass(test_name)}" if v11_t6 else f"  {_fail(test_name)}")

    # -----------------------------------------------------------------------
    # Test 7: Visit dates out of chronological order → V1 FAIL
    # -----------------------------------------------------------------------
    test_name = 'T7: visit dates out of order → V1'
    # Pick any patient with ≥2 visits
    multi_visit = next(p for p in patients if len(p.get("visits", [])) >= 2)
    p = copy.deepcopy(multi_visit)
    # Swap first two visit dates to create out-of-order
    dates = [v["visit_date"] for v in p["visits"]]
    p["visits"][0]["visit_date"], p["visits"][1]["visit_date"] = dates[1], dates[0]
    issues = [i.as_dict() for i in run_all_rules([p]).issues]
    v1_fired = any(i["rule_id"] == "V1" and i["severity"] == FAIL for i in issues)
    results.append((test_name, v1_fired, "V1 fired" if v1_fired else "V1 NOT fired"))
    print(f"  {_pass(test_name)}" if v1_fired else f"  {_fail(test_name)}")

    # -----------------------------------------------------------------------
    # Test 8: Medication name not in MEDICATION_NAMES → V11 FAIL
    # -----------------------------------------------------------------------
    test_name = 'T8: unknown medication name → V11'
    p = _base_patient(patients)
    for visit in p.get("visits", []):
        if visit.get("medications"):
            visit["medications"][0]["medication_name"] = "SnakeOilElixir"
            break
    issues = [i.as_dict() for i in run_all_rules([p]).issues]
    v11_t8 = any(i["rule_id"] == "V11" and i["severity"] == FAIL for i in issues)
    results.append((test_name, v11_t8, "V11 fired" if v11_t8 else "V11 NOT fired"))
    print(f"  {_pass(test_name)}" if v11_t8 else f"  {_fail(test_name)}")

    # -----------------------------------------------------------------------
    # Test 9: demographics.age field present → V4 FAIL
    # -----------------------------------------------------------------------
    test_name = 'T9: demographics.age present → V4'
    p = _base_patient(patients)
    p["demographics"]["age"] = 45
    issues = [i.as_dict() for i in run_all_rules([p]).issues]
    v4_fired = any(i["rule_id"] == "V4" and i["severity"] == FAIL for i in issues)
    results.append((test_name, v4_fired, "V4 fired" if v4_fired else "V4 NOT fired"))
    print(f"  {_pass(test_name)}" if v4_fired else f"  {_fail(test_name)}")

    # -----------------------------------------------------------------------
    # Test 10: retrieval_signature deleted from patient metadata → V12 FAIL
    # -----------------------------------------------------------------------
    test_name = 'T10: retrieval_signature missing → V12'
    p = _base_patient(patients)
    del p["metadata"]["retrieval_signature"]
    # Run only v12 (dataset-level) using single patient list
    issues = [i.as_dict() for i in run_all_rules([p]).issues]
    v12_t10 = any(i["rule_id"] == "V12" and i["severity"] == FAIL for i in issues)
    results.append((test_name, v12_t10, "V12 fired" if v12_t10 else "V12 NOT fired"))
    print(f"  {_pass(test_name)}" if v12_t10 else f"  {_fail(test_name)}")

    caught_count = sum(1 for _, caught, _ in results if caught)
    print(f"\n  Negative tests caught: {caught_count}/10")

    return caught_count, results


# ===========================================================================
# PART 4 — Patient-specific scenarios
# ===========================================================================

def run_part4(patients: list[dict]) -> tuple[int, list[tuple[str, bool, str]]]:
    print(_head("PART 4 — Patient-Specific Scenarios"))

    results: list[tuple[str, bool, str]] = []

    def get_patient(pid: str) -> dict | None:
        return next((p for p in patients if p.get("patient_id") == pid), None)

    def get_visit(patient: dict, visit_index: int) -> dict | None:
        visits = patient.get("visits", [])
        if visit_index < len(visits):
            return visits[visit_index]
        return None

    def find_med(visit: dict, name: str) -> dict | None:
        for med in visit.get("medications", []):
            if med.get("medication_name") == name:
                return med
        return None

    # -----------------------------------------------------------------------
    # Scenario 1: PAT-CHR-001 visit 3 (index 2):
    #   Metformin → trajectory_event="adherence_interruption"
    #   Amlodipine → trajectory_event="simple_start_continue"
    # -----------------------------------------------------------------------
    scen_name = "S1: PAT-CHR-001 v3: Metformin=adherence_interruption, Amlodipine=simple_start_continue"
    p = get_patient("PAT-CHR-001")
    visit = get_visit(p, 2) if p else None  # 0-indexed → visit 3
    ok = False
    detail = ""
    if visit:
        metformin = find_med(visit, "Metformin")
        amlodipine = find_med(visit, "Amlodipine")
        m_ok = metformin and metformin.get("trajectory_event") == "adherence_interruption"
        a_ok = amlodipine and amlodipine.get("trajectory_event") == "simple_start_continue"
        ok = bool(m_ok and a_ok)
        if not m_ok:
            detail = f"Metformin trajectory={metformin.get('trajectory_event') if metformin else 'NOT FOUND'}"
        elif not a_ok:
            detail = f"Amlodipine trajectory={amlodipine.get('trajectory_event') if amlodipine else 'NOT FOUND'}"
        else:
            detail = "Both correct"
    else:
        detail = "Patient or visit not found"
    results.append((scen_name, ok, detail))
    print(f"  {_pass(scen_name)}" if ok else f"  {_fail(scen_name)} — {detail}")

    # -----------------------------------------------------------------------
    # Scenario 2: PAT-CHR-001 visit 4 (index 3):
    #   Glibenclamide → medication_status="added", trajectory_event="second_medication_added"
    # -----------------------------------------------------------------------
    scen_name = "S2: PAT-CHR-001 v4: Glibenclamide=added+second_medication_added"
    visit = get_visit(p, 3) if p else None
    ok = False
    detail = ""
    if visit:
        glib = find_med(visit, "Glibenclamide")
        ok = bool(
            glib
            and glib.get("medication_status") == "added"
            and glib.get("trajectory_event") == "second_medication_added"
        )
        if glib:
            detail = f"status={glib.get('medication_status')}, trajectory={glib.get('trajectory_event')}"
        else:
            detail = "Glibenclamide NOT FOUND in visit 4"
    else:
        detail = "Patient or visit not found"
    results.append((scen_name, ok, detail))
    print(f"  {_pass(scen_name)}" if ok else f"  {_fail(scen_name)} — {detail}")

    # -----------------------------------------------------------------------
    # Scenario 3: PAT-MOD-008 visit 2 (index 1):
    #   Nitrofurantoin → medication_status="completed", trajectory_event="course_completed"
    # -----------------------------------------------------------------------
    scen_name = "S3: PAT-MOD-008 v2: Nitrofurantoin=completed+course_completed"
    p_mod8 = get_patient("PAT-MOD-008")
    visit = get_visit(p_mod8, 1) if p_mod8 else None
    ok = False
    detail = ""
    if visit:
        nitro = find_med(visit, "Nitrofurantoin")
        ok = bool(
            nitro
            and nitro.get("medication_status") == "completed"
            and nitro.get("trajectory_event") == "course_completed"
        )
        if nitro:
            detail = f"status={nitro.get('medication_status')}, trajectory={nitro.get('trajectory_event')}"
        else:
            detail = "Nitrofurantoin NOT FOUND in visit 2"
    else:
        detail = "Patient or visit not found"
    results.append((scen_name, ok, detail))
    print(f"  {_pass(scen_name)}" if ok else f"  {_fail(scen_name)} — {detail}")

    # -----------------------------------------------------------------------
    # Scenario 4: PAT-CHR-005 visit 5 (index 4):
    #   Metformin, Losartan, Glibenclamide all have trajectory_event="post_discharge_reconciliation"
    # -----------------------------------------------------------------------
    scen_name = "S4: PAT-CHR-005 v5: Metformin+Losartan+Glibenclamide=post_discharge_reconciliation"
    p_chr5 = get_patient("PAT-CHR-005")
    visit = get_visit(p_chr5, 4) if p_chr5 else None
    ok = False
    detail = ""
    if visit:
        targets = ["Metformin", "Losartan", "Glibenclamide"]
        results_per_med = {}
        for name in targets:
            med = find_med(visit, name)
            results_per_med[name] = med.get("trajectory_event") if med else "NOT_FOUND"
        all_ok = all(v == "post_discharge_reconciliation" for v in results_per_med.values())
        ok = all_ok
        detail = str(results_per_med)
    else:
        detail = "Patient or visit not found"
    results.append((scen_name, ok, detail))
    print(f"  {_pass(scen_name)}" if ok else f"  {_fail(scen_name)} — {detail}")

    # -----------------------------------------------------------------------
    # Scenario 5: PAT-MOD-004 visit 2 (index 1):
    #   Ferrous sulfate → trajectory_event="adherence_interruption"
    # -----------------------------------------------------------------------
    scen_name = "S5: PAT-MOD-004 v2: Ferrous sulfate=adherence_interruption"
    p_mod4 = get_patient("PAT-MOD-004")
    visit = get_visit(p_mod4, 1) if p_mod4 else None
    ok = False
    detail = ""
    if visit:
        ferrous = find_med(visit, "Ferrous sulfate")
        ok = bool(ferrous and ferrous.get("trajectory_event") == "adherence_interruption")
        if ferrous:
            detail = f"trajectory={ferrous.get('trajectory_event')}"
        else:
            detail = "Ferrous sulfate NOT FOUND in visit 2"
    else:
        detail = "Patient or visit not found"
    results.append((scen_name, ok, detail))
    print(f"  {_pass(scen_name)}" if ok else f"  {_fail(scen_name)} — {detail}")

    # Run validation to confirm zero FAIL on the real dataset for these scenarios
    real_summary = run_all_rules(patients, strict_diversity=True)
    real_ok = real_summary.fail_count == 0
    if not real_ok:
        print(f"\n  {_warn('Dataset has FAIL issues — scenarios may be contaminated:')}")
        for issue in real_summary.issues:
            if issue.severity == FAIL:
                print(f"    [{issue.rule_id}] {issue.patient_id}: {issue.message}")

    passed_count = sum(1 for _, ok, _ in results if ok)
    print(f"\n  Patient scenarios passed: {passed_count}/5")

    return passed_count, results


# ===========================================================================
# PART 5 — Final status report
# ===========================================================================

def run_part5(
    p1_counts: dict,
    fail_count: int,
    warn_count: int,
    v12_passed: bool,
    v11_passed: bool,
    v7_passed: bool,
    negative_caught: int,
    scenarios_passed: int,
) -> None:
    print(_head("PART 5 — Final Status Report"))

    dataset_ok = (
        fail_count == 0
        and v12_passed
        and v11_passed
        and v7_passed
        and negative_caught == 10
        and scenarios_passed == 5
    )
    status_str = (
        f"{_GREEN}APPROVED FOR SOAP GENERATION{_RESET}"
        if dataset_ok
        else f"{_RED}NOT APPROVED — resolve FAIL issues above{_RESET}"
    )

    print(f"""
  Patients:            {p1_counts['patients']}
  Visits:              {p1_counts['visits']}
  Medication records:  {p1_counts['medications']}
  Lab records:         {p1_counts['labs']}
  Allergy records:     {p1_counts['allergies']}
  FAIL issues:         {fail_count}
  WARN issues:         {warn_count}
  V12 passed:          {v12_passed}
  V11 passed:          {v11_passed}
  V7 passed:           {v7_passed}
  Negative tests:      {negative_caught}/10 caught
  Patient scenarios:   {scenarios_passed}/5 passed
  Dataset status:      {status_str}
""")


# ===========================================================================
# Main runner
# ===========================================================================

def main() -> None:
    global _P1_COUNTS
    _P1_COUNTS = {}

    # --- Part 1 ---
    patients = run_part1()

    # --- Part 2 ---
    fail_count, warn_count, passed, fail_issues = run_part2(patients)

    # Determine rule-specific pass flags using full dataset validation summary
    summary = run_all_rules(patients, strict_diversity=True)
    v12_passed = not any(i.rule_id == "V12" and i.severity == FAIL for i in summary.issues)
    v11_passed = not any(i.rule_id == "V11" and i.severity == FAIL for i in summary.issues)
    v7_passed  = not any(i.rule_id == "V7"  and i.severity == FAIL for i in summary.issues)

    # --- Part 3 ---
    negative_caught, neg_results = run_part3(patients)

    # --- Part 4 ---
    scenarios_passed, scen_results = run_part4(patients)

    # --- Part 5 ---
    run_part5(
        p1_counts=_P1_COUNTS,
        fail_count=fail_count,
        warn_count=warn_count,
        v12_passed=v12_passed,
        v11_passed=v11_passed,
        v7_passed=v7_passed,
        negative_caught=negative_caught,
        scenarios_passed=scenarios_passed,
    )

    # Exit code reflects final pass/fail
    overall = (
        fail_count == 0
        and negative_caught == 10
        and scenarios_passed == 5
    )
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
