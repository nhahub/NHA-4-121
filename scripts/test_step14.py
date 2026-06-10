"""
scripts/test_step14.py  —  Step 14 complete integration + scenario + negative tests
"""

from generators.patient_generator import generate_patients
from generators.visit_generator import generate_visits_for_patient
from generators.medication_generator import generate_medications_for_patient
from generators.lab_generator import generate_labs_for_patient
from generators.allergy_generator import generate_allergy_registry_for_patient
from soap.soap_generator import generate_soap_for_patient
from soap.soap_auditor import audit_soap_for_patient, soap_audit_passed
from ingestion.chunker import build_all_chunks
from ingestion.metadata_builder import (
    build_metadata_for_all_chunks,
    validate_metadata,
    summarize_metadata_set,
    MetadataBuilderError,
)
from config.patient_blueprints import BLUEPRINT_BY_ID
from config.constants import SOURCE_TYPES

# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------
patients = generate_patients(mode="v17_lite")
for patient in patients:
    blueprint = BLUEPRINT_BY_ID[patient["patient_id"]]
    generate_visits_for_patient(patient, blueprint)
    generate_medications_for_patient(patient, blueprint)
    generate_labs_for_patient(patient, blueprint)
    generate_allergy_registry_for_patient(patient, blueprint)
    generate_soap_for_patient(patient, blueprint)
    assert soap_audit_passed(audit_soap_for_patient(patient, blueprint))

chunks = build_all_chunks(patients, BLUEPRINT_BY_ID)
print(f"Chunks built: {len(chunks)}")

metadata_list = build_metadata_for_all_chunks(chunks, patients)
print(f"Metadata records built: {len(metadata_list)}")
assert len(metadata_list) == len(chunks)

# Validate every metadata record
for i, (chunk, meta) in enumerate(zip(chunks, metadata_list)):
    validate_metadata(meta, source_type=chunk["source_type"])
print("All metadata records validated ✓")

# ---------------------------------------------------------------------------
# BP key check
# ---------------------------------------------------------------------------
BP_KEYS = {"bp","blood_pressure","bp_systolic","bp_diastolic",
           "systolic","diastolic","sbp","dbp"}
for meta in metadata_list:
    for key in meta:
        assert key.lower() not in BP_KEYS, \
            f"BP key '{key}' found in metadata"
print("No BP keys in any metadata ✓")

# ---------------------------------------------------------------------------
# None value check
# ---------------------------------------------------------------------------
for i, meta in enumerate(metadata_list):
    for key, val in meta.items():
        assert val is not None, \
            f"None value for key '{key}' in metadata[{i}]"
print("No None values in any metadata ✓")

# ---------------------------------------------------------------------------
# List/dict check
# ---------------------------------------------------------------------------
for i, meta in enumerate(metadata_list):
    for key, val in meta.items():
        assert not isinstance(val, (list, dict)), \
            f"Non-scalar value for key '{key}' in metadata[{i}]: {type(val)}"
print("No list or dict values in any metadata ✓")

# ---------------------------------------------------------------------------
# Boolean type check
# ---------------------------------------------------------------------------
for i, meta in enumerate(metadata_list):
    for bool_key in ("has_medication_change","has_hospitalization","has_lab_trend"):
        assert isinstance(meta[bool_key], bool), \
            f"'{bool_key}' is not bool in metadata[{i}]: {type(meta[bool_key])}"
print("All boolean fields are typed bool ✓")

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
summary = summarize_metadata_set(metadata_list)
print(f"\nMetadata Summary:")
print(f"  Total:               {summary['total']}")
print(f"  By source_type:      {summary['by_source_type']}")
print(f"  Patients covered:    {summary['patients_covered']}")
print(f"  has_medication_change: {summary['has_medication_change_count']}")
print(f"  has_hospitalization:   {summary['has_hospitalization_count']}")
print(f"  has_lab_trend:         {summary['has_lab_trend_count']}")

# ---------------------------------------------------------------------------
# Test 1 — PAT-CHR-001 visit 4 has_medication_change is True
# ---------------------------------------------------------------------------
chr1_meta = [
    m for m, c in zip(metadata_list, chunks)
    if c["patient_id"] == "PAT-CHR-001"
    and c["source_type"] == "prescription"
    and m["visit_role"] == "second_medication_added"
]
assert len(chr1_meta) == 1, f"Expected 1 PAT-CHR-001 prescription/second_medication_added chunk, got {len(chr1_meta)}"
assert chr1_meta[0]["has_medication_change"] is True
print("Test 1: PAT-CHR-001 v4 has_medication_change=True ✓")

# ---------------------------------------------------------------------------
# Test 2 — PAT-CHR-005 visit 3 has_hospitalization is True
# ---------------------------------------------------------------------------
chr5_hosp_meta = [
    m for m, c in zip(metadata_list, chunks)
    if c["patient_id"] == "PAT-CHR-005"
    and m["visit_role"] == "hospitalization"
    and c["source_type"] == "doctor_note"
]
assert len(chr5_hosp_meta) >= 1, f"Expected >=1 PAT-CHR-005 hospitalization doctor_note chunk, got {len(chr5_hosp_meta)}"
assert chr5_hosp_meta[0]["has_hospitalization"] is True
print("Test 2: PAT-CHR-005 hospitalization has_hospitalization=True ✓")

# ---------------------------------------------------------------------------
# Test 3 — PAT-CHR-002 lab visits have has_lab_trend True
# ---------------------------------------------------------------------------
chr2_lab_meta = [
    m for m, c in zip(metadata_list, chunks)
    if c["patient_id"] == "PAT-CHR-002"
    and c["source_type"] == "lab_result"
]
assert all(m["has_lab_trend"] is True for m in chr2_lab_meta)
print("Test 3: PAT-CHR-002 lab_result chunks all have has_lab_trend=True ✓")

# ---------------------------------------------------------------------------
# Test 4 — Allergy chunk metadata uses empty strings not None
# ---------------------------------------------------------------------------
allergy_meta = [
    m for m, c in zip(metadata_list, chunks)
    if c["source_type"] == "allergy"
]
assert len(allergy_meta) == 15, f"Expected 15 allergy chunks, got {len(allergy_meta)}"
for m in allergy_meta:
    assert m["visit_id"] == "", f"visit_id not empty string: {m['visit_id']!r}"
    assert m["visit_date"] == "", f"visit_date not empty string: {m['visit_date']!r}"
    assert m["visit_type"] == "", f"visit_type not empty string: {m['visit_type']!r}"
    assert m["visit_role"] == "", f"visit_role not empty string: {m['visit_role']!r}"
    assert m["has_medication_change"] is False
    assert m["has_hospitalization"] is False
    assert m["has_lab_trend"] is False
print("Test 4: All 15 allergy chunk metadata use empty strings, not None ✓")

# ---------------------------------------------------------------------------
# Test 5 — Conditions are pipe-separated strings not lists
# ---------------------------------------------------------------------------
for m in metadata_list:
    conds = m["conditions"]
    assert isinstance(conds, str), f"conditions is {type(conds)}"
    assert "," not in conds, f"conditions contains comma: {conds}"
    pid = m["patient_id"]
    if pid in ("PAT-CHR-001", "PAT-CHR-002", "PAT-CHR-005"):
        assert "|" in conds, f"{pid} conditions missing pipe separator: {conds}"
print("Test 5: All conditions are pipe-separated strings ✓")

# ---------------------------------------------------------------------------
# Negative Test 1 — BP key rejected
# ---------------------------------------------------------------------------
bad_meta = {
    "patient_id": "PAT-MOD-001",
    "visit_id": "VST-MOD-001-001",
    "visit_date": "2023-01-10",
    "source_type": "doctor_note",
    "conditions": "T2DM",
    "visit_type": "initial",
    "visit_role": "initial_diagnosis",
    "semantic_focus": "lab_improvement",
    "timeline_pattern": "regular_quarterly",
    "has_medication_change": False,
    "has_hospitalization": False,
    "has_lab_trend": False,
    "bp_systolic": 130,
}
try:
    validate_metadata(bad_meta, source_type="doctor_note")
    assert False, "Should have raised MetadataBuilderError"
except MetadataBuilderError as e:
    assert "bp_systolic" in str(e).lower() or "forbidden" in str(e).lower(), str(e)
print("Negative Test 1: BP key rejected ✓")

# ---------------------------------------------------------------------------
# Negative Test 2 — List value rejected
# ---------------------------------------------------------------------------
bad_meta_list = {
    "patient_id": "PAT-MOD-001",
    "visit_id": "VST-MOD-001-001",
    "visit_date": "2023-01-10",
    "source_type": "doctor_note",
    "conditions": ["T2DM"],
    "visit_type": "initial",
    "visit_role": "initial_diagnosis",
    "semantic_focus": "lab_improvement",
    "timeline_pattern": "regular_quarterly",
    "has_medication_change": False,
    "has_hospitalization": False,
    "has_lab_trend": False,
}
try:
    validate_metadata(bad_meta_list, source_type="doctor_note")
    assert False, "Should have raised MetadataBuilderError"
except MetadataBuilderError as e:
    assert "list" in str(e).lower() or "scalar" in str(e).lower() or "str" in str(e).lower(), str(e)
print("Negative Test 2: List value in conditions rejected ✓")

# ---------------------------------------------------------------------------
# Negative Test 3 — None value rejected
# ---------------------------------------------------------------------------
bad_meta_none = {
    "patient_id": "PAT-MOD-001",
    "visit_id": None,
    "visit_date": "2023-01-10",
    "source_type": "doctor_note",
    "conditions": "T2DM",
    "visit_type": "initial",
    "visit_role": "initial_diagnosis",
    "semantic_focus": "lab_improvement",
    "timeline_pattern": "regular_quarterly",
    "has_medication_change": False,
    "has_hospitalization": False,
    "has_lab_trend": False,
}
try:
    validate_metadata(bad_meta_none, source_type="doctor_note")
    assert False, "Should have raised MetadataBuilderError"
except MetadataBuilderError as e:
    assert "none" in str(e).lower() or "null" in str(e).lower() or "visit_id" in str(e).lower(), str(e)
print("Negative Test 3: None value rejected ✓")

# ---------------------------------------------------------------------------
# Negative Test 4 — Boolean field as string rejected
# ---------------------------------------------------------------------------
bad_meta_bool = {
    "patient_id": "PAT-MOD-001",
    "visit_id": "VST-MOD-001-001",
    "visit_date": "2023-01-10",
    "source_type": "doctor_note",
    "conditions": "T2DM",
    "visit_type": "initial",
    "visit_role": "initial_diagnosis",
    "semantic_focus": "lab_improvement",
    "timeline_pattern": "regular_quarterly",
    "has_medication_change": "False",
    "has_hospitalization": False,
    "has_lab_trend": False,
}
try:
    validate_metadata(bad_meta_bool, source_type="doctor_note")
    assert False, "Should have raised MetadataBuilderError"
except MetadataBuilderError as e:
    assert "bool" in str(e).lower() or "has_medication_change" in str(e).lower(), str(e)
print("Negative Test 4: Boolean as string rejected ✓")

# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------
total = summary["total"]
by_st = summary["by_source_type"]
med_count  = summary["has_medication_change_count"]
hosp_count = summary["has_hospitalization_count"]
lab_count  = summary["has_lab_trend_count"]

print(f"""
=== Step 14 — Metadata Builder Report ===
Total metadata records:      {total}
By source_type:
  doctor_note:               {by_st.get('doctor_note', 0)}
  lab_result:                {by_st.get('lab_result', 0)}
  prescription:              {by_st.get('prescription', 0)}
  allergy:                   {by_st.get('allergy', 0)}
  discharge_summary:         {by_st.get('discharge_summary', 0)}
  medication_reconciliation: {by_st.get('medication_reconciliation', 0)}

Field validation:            PASS — all 12 fields present and typed correctly
BP forbidden check:          PASS — zero BP keys in any metadata record
None value check:            PASS — zero None values
List/dict value check:       PASS — all values are scalar types
Boolean type check:          PASS — all booleans are typed bool

Boolean field counts:
  has_medication_change:     {med_count} True out of {total} total
  has_hospitalization:       {hosp_count} True out of {total} total
  has_lab_trend:             {lab_count} True out of {total} total

Integration test:            PASS
Scenario tests:              5/5 PASS
Negative tests:              4/4 PASS

Status: APPROVED FOR STEP 15 — CHROMADB INGESTION
==========================================
""")
