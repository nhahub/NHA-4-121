"""
scripts/run_step12_enrichment.py

Step 12 — Retrieval Enrichment Builder and Auditor integration test.

Run from project root:
    python scripts/run_step12_enrichment.py
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from generators.patient_generator import generate_patients
from generators.visit_generator import generate_visits_for_patient
from generators.medication_generator import generate_medications_for_patient
from generators.lab_generator import generate_labs_for_patient
from generators.allergy_generator import generate_allergy_registry_for_patient
from soap.soap_generator import generate_soap_for_patient
from soap.soap_auditor import audit_soap_for_patient, soap_audit_passed
from ingestion.retrieval_enricher import build_retrieval_text, build_all_retrieval_texts
from ingestion.retrieval_enrichment_auditor import (
    audit_retrieval_text, enrichment_audit_passed
)
from config.patient_blueprints import BLUEPRINT_BY_ID
from config.constants import CORE_SOURCE_TYPES

# ---------------------------------------------------------------------------
# Generate all 15 patients
# ---------------------------------------------------------------------------
print("Generating patients...")
patients = generate_patients(mode="v17_lite")
for patient in patients:
    blueprint = BLUEPRINT_BY_ID[patient["patient_id"]]
    generate_visits_for_patient(patient, blueprint)
    generate_medications_for_patient(patient, blueprint)
    generate_labs_for_patient(patient, blueprint)
    generate_allergy_registry_for_patient(patient, blueprint)
    generate_soap_for_patient(patient, blueprint)
    assert soap_audit_passed(audit_soap_for_patient(patient, blueprint)), \
        f"SOAP audit failed for {patient['patient_id']}"

print(f"All {len(patients)} patients generated and SOAP-audited.\n")

# ---------------------------------------------------------------------------
# Integration test — all 15 patients, all visits, all source types
# ---------------------------------------------------------------------------
all_audit_results = []
total_visits = 0
counts = {st: 0 for st in CORE_SOURCE_TYPES}

for patient in patients:
    blueprint = BLUEPRINT_BY_ID[patient["patient_id"]]

    # Visit-level source types
    for visit in patient["visits"]:
        total_visits += 1
        for source_type in ("doctor_note", "lab_result", "prescription"):
            text = build_retrieval_text(patient, visit, source_type)
            result = audit_retrieval_text(text, patient, visit, source_type)
            all_audit_results.append(result)
            counts[source_type] += 1

    # Patient-level allergy
    text = build_retrieval_text(patient, None, "allergy")
    result = audit_retrieval_text(text, patient, None, "allergy")
    all_audit_results.append(result)
    counts["allergy"] += 1

fail_results = [r for r in all_audit_results if not r.passed]
assert len(fail_results) == 0, (
    f"Enrichment audit failures:\n"
    + "\n".join(
        f"  {r.patient_id} {r.visit_id} [{r.source_type}]: {r.issues}"
        for r in fail_results
    )
)
print(f"Integration test PASS — {len(all_audit_results)} enrichment texts, 0 failures.\n")

# ---------------------------------------------------------------------------
# Scenario tests
# ---------------------------------------------------------------------------

# Test 1 — PAT-CHR-001 visit 3 (partial_adherence) doctor_note enrichment
p_chr1 = next(p for p in patients if p["patient_id"] == "PAT-CHR-001")
v = p_chr1["visits"][2]
text = build_retrieval_text(p_chr1, v, "doctor_note")
assert "partial adherence" in text.lower() or "missed doses" in text.lower(), \
    f"PAT-CHR-001 v3 doctor_note enrichment missing adherence vocabulary: {text}"
print("Test 1: PAT-CHR-001 v3 adherence vocabulary in enrichment ✓")

# Test 2 — PAT-CHR-001 visit 4 (second_medication_added) prescription enrichment
v = p_chr1["visits"][3]
text = build_retrieval_text(p_chr1, v, "prescription")
assert "glibenclamide" in text.lower(), \
    f"PAT-CHR-001 v4 prescription enrichment missing Glibenclamide: {text}"
assert "newly added" in text.lower() or "added" in text.lower(), \
    f"PAT-CHR-001 v4 prescription enrichment missing addition vocabulary: {text}"
print("Test 2: PAT-CHR-001 v4 Glibenclamide addition in enrichment ✓")

# Test 3 — PAT-CHR-002 lab_result enrichment contains CKD-related label
p2 = next(p for p in patients if p["patient_id"] == "PAT-CHR-002")
for v in p2["visits"]:
    if v["labs"]:
        text = build_retrieval_text(p2, v, "lab_result")
        assert "creatinine" in text.lower(), f"Test 3 missing creatinine: {text}"
        assert "trend" in text.lower(), f"Test 3 missing trend: {text}"
        assert "ckd" in text.lower() or "kidney" in text.lower(), \
            f"Test 3 missing CKD/kidney: {text}"
        break
print("Test 3: PAT-CHR-002 lab_result enrichment contains CKD and trend vocabulary ✓")

# Test 4 — PAT-MOD-003 allergy enrichment contains Aspirin
p3 = next(p for p in patients if p["patient_id"] == "PAT-MOD-003")
text = build_retrieval_text(p3, None, "allergy")
assert "aspirin" in text.lower(), f"Test 4 missing aspirin: {text}"
assert "bronchospasm" in text.lower(), f"Test 4 missing bronchospasm: {text}"
assert "detected" not in text.lower(), f"Test 4 has 'detected': {text}"
assert "predicted" not in text.lower(), f"Test 4 has 'predicted': {text}"
print("Test 4: PAT-MOD-003 allergy enrichment is correctly framed ✓")

# Test 5 — No-allergy patient returns correct empty message
p5 = next(p for p in patients if p["patient_id"] == "PAT-NRM-001")
text = build_retrieval_text(p5, None, "allergy")
assert "no documented" in text.lower() or "no allergy" in text.lower(), \
    f"Test 5 empty allergy incorrect: {text}"
print("Test 5: PAT-NRM-001 empty allergy enrichment correctly stated ✓")

# Test 6 — PAT-CHR-005 visit 5 (medication_reconciliation) prescription enrichment
p_chr5 = next(p for p in patients if p["patient_id"] == "PAT-CHR-005")
v5 = p_chr5["visits"][4]
text = build_retrieval_text(p_chr5, v5, "prescription")
assert "reconciliation" in text.lower() or "post-discharge" in text.lower(), \
    f"Test 6 missing reconciliation vocabulary: {text}"
assert "metformin" in text.lower(), f"Test 6 missing Metformin: {text}"
print("Test 6: PAT-CHR-005 v5 reconciliation vocabulary in enrichment ✓")

# ---------------------------------------------------------------------------
# Negative tests
# ---------------------------------------------------------------------------

p_neg = patients[0]
v_neg = p_neg["visits"][0]

# Negative Test 1 — Empty enrichment text caught
result = audit_retrieval_text("", p_neg, v_neg, "doctor_note")
assert not result.passed, "Negative Test 1: empty text should FAIL"
assert any("empty" in issue.lower() for issue in result.issues), \
    f"Negative Test 1: expected 'empty' in issues: {result.issues}"
print("Negative Test 1: Empty enrichment text caught ✓")

# Negative Test 2 — Placeholder leakage caught
bad_text = "Doctor note for {patient_id} visit {visit_id}: T2DM follow-up."
result = audit_retrieval_text(bad_text, p_neg, v_neg, "doctor_note")
assert not result.passed, "Negative Test 2: placeholder text should FAIL"
assert any("placeholder" in issue.lower() for issue in result.issues), \
    f"Negative Test 2: expected 'placeholder' in issues: {result.issues}"
print("Negative Test 2: Placeholder leakage caught ✓")

# Negative Test 3 — Unsafe recommendation phrase caught
bad_text = "Prescription context for PAT-MOD-001: Patient should take Metformin twice daily."
result = audit_retrieval_text(bad_text, p_neg, v_neg, "prescription")
assert not result.passed, "Negative Test 3: unsafe phrase should FAIL"
assert any(
    "recommendation" in issue.lower() or "unsafe" in issue.lower()
    for issue in result.issues
), f"Negative Test 3: expected recommendation/unsafe in issues: {result.issues}"
print("Negative Test 3: Unsafe recommendation phrase caught ✓")

# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------
warn_results = [r for r in all_audit_results if not r.passed or any("[WARN]" in i for i in r.issues)]
warn_count   = sum(
    sum(1 for i in r.issues if i.startswith("[WARN]"))
    for r in all_audit_results
)

print()
print("=== Step 12 — Retrieval Enrichment Report ===")
print(f"Patients processed:          {len(patients)}")
print(f"Visits processed:            {total_visits}")
print(f"Enrichment texts generated:  {len(all_audit_results)}  (doctor_note + lab_result + prescription + allergy)")
print(f"Audit results:               {len(all_audit_results)} total  |  0 FAIL  |  {warn_count} WARN")
print(f"Integration test:            PASS")
print(f"Scenario tests:              6/6 PASS")
print(f"Negative tests:              3/3 PASS")
print()
print("Source-type breakdown:")
print(f"  doctor_note:    {counts['doctor_note']} enrichment texts")
print(f"  lab_result:     {counts['lab_result']} enrichment texts (all visits, including those without labs)")
print(f"  prescription:   {counts['prescription']} enrichment texts")
print(f"  allergy:        {counts['allergy']} enrichment texts (15 patients, including empty-allergy)")
print()
print("Inter-patient similarity impact:")
print("  PAT-CHR-001 v3 adherence vocabulary reinforced in enrichment: YES")
print("  PAT-CHR-001 v4 Glibenclamide addition vocabulary reinforced: YES")
print("  PAT-CHR-002 CKD + trend vocabulary in lab enrichment: YES")
print("  PAT-CHR-005 post-discharge reconciliation vocabulary reinforced: YES")
print()
print("Status: APPROVED FOR STEP 13 — CHUNKING AND INGESTION")
print("=============================================")
