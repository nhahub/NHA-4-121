"""
scripts/run_step11_v13.py

Step 11 — V13 Embedding Similarity Report smoke tests.

Runs three smoke tests:
    Test 1: Full pipeline (15 patients) — chunks_checked == 50
    Test 2: T2DM condition-group cross-patient critical pairs
    Test 3: Threshold correctness — identical cross-patient SOAP triggers critical

Then prints the final summary table.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from generators.patient_generator import generate_patients
from generators.visit_generator import generate_visits_for_patient
from generators.medication_generator import generate_medications_for_patient
from generators.lab_generator import generate_labs_for_patient
from generators.allergy_generator import generate_allergy_registry_for_patient
from soap.soap_generator import generate_soap_for_patient
from soap.soap_auditor import audit_soap_for_patient, soap_audit_passed
from validators.v13_similarity_report import run_v13_similarity_report
from config.patient_blueprints import BLUEPRINT_BY_ID


# ---------------------------------------------------------------------------
# Build full 15-patient dataset
# ---------------------------------------------------------------------------

print("=== Step 11 — V13 Embedding Similarity Report ===")
print("Building full 15-patient dataset (all 5 pipeline stages + SOAP)...")
print()

patients = generate_patients(mode="v17_lite")

for patient in patients:
    blueprint = BLUEPRINT_BY_ID[patient["patient_id"]]
    generate_visits_for_patient(patient, blueprint)
    generate_medications_for_patient(patient, blueprint)
    generate_labs_for_patient(patient, blueprint)
    generate_allergy_registry_for_patient(patient, blueprint)
    generate_soap_for_patient(patient, blueprint)

    issues = audit_soap_for_patient(patient, blueprint)
    assert soap_audit_passed(issues), (
        f"{patient['patient_id']} SOAP audit FAILED with "
        f"{sum(1 for i in issues if i.severity == 'FAIL')} FAIL issue(s):\n"
        + "\n".join(f"  [{i.rule_id}] {i.message}" for i in issues if i.severity == "FAIL")
    )

print(f"All {len(patients)} patients generated and SOAP-audited successfully.")
total_visits = sum(len(p["visits"]) for p in patients)
print(f"Total visits across all patients: {total_visits}")
print()


# ---------------------------------------------------------------------------
# TEST 1 — Full pipeline smoke test
# ---------------------------------------------------------------------------

print("=" * 60)
print("TEST 1 — Full pipeline smoke test (15 patients)")
print("=" * 60)

report = run_v13_similarity_report(patients, print_report=True)

assert report.chunks_checked == 50, (
    f"Expected chunks_checked == 50, got {report.chunks_checked}. "
    f"Total visits = {total_visits}"
)
print(f"Chunks checked: {report.chunks_checked} ✓")

cross_patient_critical = sum(1 for p in report.critical_pairs if not p.same_patient)
print(f"Critical cross-patient pairs: {cross_patient_critical}")
print(f"V13 passed: {report.passed}")
print()


# ---------------------------------------------------------------------------
# TEST 2 — T2DM condition group
# ---------------------------------------------------------------------------

print("=" * 60)
print("TEST 2 — T2DM condition-group cross-patient pairs")
print("=" * 60)

t2dm_patients = [p for p in patients if "T2DM" in p["conditions"]]
print(f"T2DM patients: {[p['patient_id'] for p in t2dm_patients]}")
print()

sub_report = run_v13_similarity_report(t2dm_patients, print_report=False)

cross_patient_critical_t2dm = [
    r for r in sub_report.critical_pairs
    if not r.same_patient
]
print(f"Cross-patient critical pairs among T2DM patients: {len(cross_patient_critical_t2dm)}")

if cross_patient_critical_t2dm:
    for pair in cross_patient_critical_t2dm:
        print(f"  CRITICAL: {pair.chunk_a_id} vs {pair.chunk_b_id}  sim={pair.similarity:.4f}")
        print(f"  Action: adjust soap_style or story_arc for these two patients.")

t2dm_status = "CLEAR" if not cross_patient_critical_t2dm else "NEEDS REVIEW"
print(f"T2DM group status: {t2dm_status}")
print()


# ---------------------------------------------------------------------------
# TEST 3 — Threshold correctness (identical cross-patient SOAP)
# ---------------------------------------------------------------------------

print("=" * 60)
print("TEST 3 — Threshold correctness (identical SOAP → critical)")
print("=" * 60)

dup_patients = [copy.deepcopy(patients[0]), copy.deepcopy(patients[1])]

# Make patient 1's first SOAP identical to patient 0's first SOAP
dup_patients[1]["visits"][0]["soap_note"] = copy.deepcopy(
    dup_patients[0]["visits"][0]["soap_note"]
)

# Force different patient IDs so same_patient=False
dup_patients[1]["patient_id"] = "PAT-TEST-999"
for v in dup_patients[1]["visits"]:
    v["visit_id"] = v["visit_id"].replace(
        dup_patients[0]["patient_id"].split("-")[1],
        "TST",
    )

dup_report = run_v13_similarity_report(dup_patients, print_report=False)

assert not dup_report.passed, (
    "Expected dup_report.passed == False for identical cross-patient SOAP, "
    f"but got passed={dup_report.passed}. "
    f"critical_pairs={len(dup_report.critical_pairs)}"
)
assert len(dup_report.critical_pairs) > 0, (
    "Expected at least one critical pair for identical cross-patient SOAP, "
    f"got {len(dup_report.critical_pairs)}"
)

print("Test 3: Identical cross-patient SOAP detected as critical ✓")
print(f"  Critical pairs found: {len(dup_report.critical_pairs)}")
print(f"  Highest similarity:   {dup_report.critical_pairs[0].similarity:.6f}")
print()


# ---------------------------------------------------------------------------
# Final summary
# ---------------------------------------------------------------------------

overall_passed = report.passed
next_step = (
    "Step 12 — Chunking and ingestion"
    if overall_passed
    else "Fix blueprints first"
)

print("=== V13 Step 11 — Final Status ===")
print(f"Model:                  {report.model_name}")
print(f"Full dataset (15 pts):")
print(f"  Chunks checked:       {report.chunks_checked}")
print(f"  Critical pairs:       {report.critical_count}")
print(f"  Warn pairs:           {report.warn_count}")
print(f"  Passed:               {report.passed}")
print(f"T2DM condition group:")
print(f"  Cross-patient critical pairs: {len(cross_patient_critical_t2dm)}")
print(f"  Status: {t2dm_status}")
print(f"Threshold test:         PASS (identical SOAP detected correctly)")
print("==================================")
print(f"Overall V13 status:     {'PASSED' if overall_passed else 'NEEDS BLUEPRINT REVIEW'}")
print(f"Next step:              {next_step}")
print("==================================")
