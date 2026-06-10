"""
scripts/test_step10_auditor.py

Step 10 integration test for soap/soap_auditor.py.

Run from project root:
    python scripts/test_step10_auditor.py
"""

from __future__ import annotations

import copy
import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from generators.patient_generator import generate_patients
from generators.visit_generator import generate_visits_for_patient
from generators.medication_generator import generate_medications_for_patient
from generators.lab_generator import generate_labs_for_patient
from generators.allergy_generator import generate_allergy_registry_for_patient
from soap.soap_generator import generate_soap_for_patient
from soap.soap_auditor import audit_soap_for_patient, soap_audit_passed
from config.patient_blueprints import BLUEPRINT_BY_ID


def main() -> int:
    # ------------------------------------------------------------------
    # Build full 15-patient dataset
    # ------------------------------------------------------------------
    print("Generating 15-patient v1.7 Lite dataset...")
    patients = generate_patients(mode="v17_lite")
    for patient in patients:
        blueprint = BLUEPRINT_BY_ID[patient["patient_id"]]
        generate_visits_for_patient(patient, blueprint)
        generate_medications_for_patient(patient, blueprint)
        generate_labs_for_patient(patient, blueprint)
        generate_allergy_registry_for_patient(patient, blueprint)
        generate_soap_for_patient(patient, blueprint)

    total_visits = sum(len(p["visits"]) for p in patients)
    print(f"  Generated {len(patients)} patients, {total_visits} visits.\n")

    # ------------------------------------------------------------------
    # Positive test: all 15 patients must have zero FAIL
    # ------------------------------------------------------------------
    print("Running positive audit across all 15 patients...")
    all_issues = []
    for patient in patients:
        blueprint = BLUEPRINT_BY_ID[patient["patient_id"]]
        issues = audit_soap_for_patient(patient, blueprint)
        fails = [i for i in issues if i.severity == "FAIL"]
        all_issues.extend(issues)
        if fails:
            print(f"  FAIL in {patient['patient_id']}:")
            for f in fails:
                print(f"    [{f.rule_id}] visit={f.visit_id}: {f.message}")
        assert len(fails) == 0, (
            f"{patient['patient_id']}: {[(i.rule_id, i.message) for i in fails]}"
        )
    print("  All 15 patients: zero FAIL audit issues ✓\n")

    # ------------------------------------------------------------------
    # Negative test helpers
    # ------------------------------------------------------------------
    # Use the first patient that has a partial_adherence visit for SA1/SA2/SA3/SA4/SA7
    pa_patient = None
    for p in patients:
        for v in p["visits"]:
            if v.get("visit_role") == "partial_adherence":
                pa_patient = p
                break
        if pa_patient:
            break

    test_patient = pa_patient if pa_patient else patients[0]
    test_pid = test_patient["patient_id"]

    # ------------------------------------------------------------------
    # Test 1 — SA1: Remove primary visit_role phrase
    # ------------------------------------------------------------------
    print("Negative test 1 — SA1 (visit_role phrase removed)...")
    p = copy.deepcopy(test_patient)
    patched = False
    for v in p["visits"]:
        vr = v.get("visit_role", "")
        if vr == "partial_adherence":
            v["soap_note"]["assessment"] = v["soap_note"]["assessment"].replace(
                "reported partial adherence", "some adherence issues noted"
            )
            v["soap_note"]["plan"] = (
                v["soap_note"]["plan"]
                .replace("reported partial adherence", "")
                .replace("missed doses noted", "")
            )
            v["soap_note"]["subjective"] = (
                v["soap_note"]["subjective"]
                .replace("reported partial adherence", "")
                .replace("missed doses noted", "")
                .replace("adherence counselling provided", "")
            )
            patched = True
            break
    if not patched:
        # Patch first visit's primary phrase regardless of role
        v = p["visits"][0]
        vr = v.get("visit_role", "")
        from soap.soap_generator import VISIT_ROLE_PHRASES
        if vr in VISIT_ROLE_PHRASES and VISIT_ROLE_PHRASES[vr]:
            phrase = VISIT_ROLE_PHRASES[vr][0]
            for section in ["subjective", "objective", "assessment", "plan"]:
                v["soap_note"][section] = v["soap_note"][section].replace(phrase, "REMOVED")

    issues = audit_soap_for_patient(p, BLUEPRINT_BY_ID[p["patient_id"]])
    assert any(i.rule_id == "SA1" and i.severity == "FAIL" for i in issues), (
        f"SA1 did not fire. Issues: {[(i.rule_id, i.severity, i.message) for i in issues]}"
    )
    print("  SA1 fires on removed visit_role phrase ✓\n")

    # ------------------------------------------------------------------
    # Test 2 — SA2: Remove event_summary from assessment
    # ------------------------------------------------------------------
    print("Negative test 2 — SA2 (event_summary removed from assessment)...")
    p = copy.deepcopy(test_patient)
    v = p["visits"][0]
    summary = v["clinical_event"]["event_summary"]
    original = v["soap_note"]["assessment"]
    v["soap_note"]["assessment"] = original.replace(summary, "Follow-up noted.")
    issues = audit_soap_for_patient(p, BLUEPRINT_BY_ID[p["patient_id"]])
    assert any(i.rule_id == "SA2" and i.severity == "FAIL" for i in issues), (
        f"SA2 did not fire. Issues: {[(i.rule_id, i.severity) for i in issues]}"
    )
    print("  SA2 fires on removed event_summary ✓\n")

    # ------------------------------------------------------------------
    # Test 3 — SA3: Empty SOAP section
    # ------------------------------------------------------------------
    print("Negative test 3 — SA3 (empty plan section)...")
    p = copy.deepcopy(test_patient)
    p["visits"][0]["soap_note"]["plan"] = ""
    issues = audit_soap_for_patient(p, BLUEPRINT_BY_ID[p["patient_id"]])
    assert any(i.rule_id == "SA3" and i.severity == "FAIL" for i in issues), (
        f"SA3 did not fire. Issues: {[(i.rule_id, i.severity) for i in issues]}"
    )
    print("  SA3 fires on empty plan section ✓\n")

    # ------------------------------------------------------------------
    # Test 4 — SA4: Invented medication
    # ------------------------------------------------------------------
    print("Negative test 4 — SA4 (invented medication)...")
    p = copy.deepcopy(test_patient)
    # Find a medication NOT in visit[0] meds
    v0 = p["visits"][0]
    visit_meds_lower = {
        m.get("medication_name", "").lower()
        for m in v0.get("medications", [])
    }
    from config.constants import MEDICATION_NAMES as MED_NAMES
    invented = next(
        (n for n in MED_NAMES if n.lower() not in visit_meds_lower),
        "Glibenclamide",
    )
    v0["soap_note"]["plan"] += f" {invented} 5 mg once daily was prescribed."
    issues = audit_soap_for_patient(p, BLUEPRINT_BY_ID[p["patient_id"]])
    assert any(i.rule_id == "SA4" and i.severity == "FAIL" for i in issues), (
        f"SA4 did not fire (invented='{invented}'). "
        f"Issues: {[(i.rule_id, i.severity, i.message) for i in issues]}"
    )
    print(f"  SA4 fires on invented medication '{invented}' ✓\n")

    # ------------------------------------------------------------------
    # Test 5 — SA7: Forbidden inference phrase
    # ------------------------------------------------------------------
    print("Negative test 5 — SA7 (forbidden inference phrase)...")
    p = copy.deepcopy(test_patient)
    p["visits"][0]["soap_note"]["assessment"] += " The patient is well controlled."
    issues = audit_soap_for_patient(p, BLUEPRINT_BY_ID[p["patient_id"]])
    assert any(i.rule_id == "SA7" and i.severity == "WARN" for i in issues), (
        f"SA7 did not fire. Issues: {[(i.rule_id, i.severity) for i in issues]}"
    )
    print("  SA7 fires on forbidden inference phrase ✓\n")

    # ------------------------------------------------------------------
    # Final report
    # ------------------------------------------------------------------
    warn_count = sum(1 for i in all_issues if i.severity == "WARN")
    print("SOAP Audit Step 10 — Final Report")
    print("==================================")
    print(f"Patients audited:         {len(patients)}")
    print(f"Visits audited:           {total_visits}")
    print(f"Positive test:            PASS (0 FAIL across all {len(patients)} patients)")
    print(f"SA1 negative test:        PASS (visit_role phrase removal caught)")
    print(f"SA2 negative test:        PASS (event_summary removal caught)")
    print(f"SA3 negative test:        PASS (empty section caught)")
    print(f"SA4 negative test:        PASS (invented medication caught)")
    print(f"SA7 negative test:        PASS (inference phrase caught)")
    print(f"Warnings (positive run):  {warn_count}")
    print("==================================")
    print("Status: READY FOR STEP 11 — RETRIEVAL ENRICHMENT")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
