"""
scripts/run_step13_chunker.py

Step 13 — Chunker integration test and report.
Run from project root:
    python scripts/run_step13_chunker.py
"""

import copy
import random
import sys
from collections import Counter

# ---------------------------------------------------------------------------
# Pipeline setup
# ---------------------------------------------------------------------------
from generators.patient_generator import generate_patients
from generators.visit_generator import generate_visits_for_patient
from generators.medication_generator import generate_medications_for_patient
from generators.lab_generator import generate_labs_for_patient
from generators.allergy_generator import generate_allergy_registry_for_patient
from soap.soap_generator import generate_soap_for_patient
from soap.soap_auditor import audit_soap_for_patient, soap_audit_passed
from ingestion.chunker import build_all_chunks, validate_chunk, ChunkerError
from config.patient_blueprints import BLUEPRINT_BY_ID

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

print("Pipeline: all 15 patients generated and SOAP-audited ✓")

chunks = build_all_chunks(patients, BLUEPRINT_BY_ID)

print(f"\nTotal chunks: {len(chunks)}")

# Counts by source_type
by_type = Counter(c["source_type"] for c in chunks)
print(f"By source_type: {dict(by_type)}")

# ---------------------------------------------------------------------------
# Integration assertions
# ---------------------------------------------------------------------------

# Every chunk begins with patient_id
for chunk in chunks:
    pid = chunk["patient_id"]
    first_sentence = chunk["text"].split(".")[0]
    assert pid in first_sentence, \
        f"Chunk {chunk['chunk_id']} first sentence missing patient_id: {first_sentence!r}"
print("All chunks begin with patient_id ✓")

# No BP in metadata
BP_KEYS = {"bp", "blood_pressure", "bp_systolic", "bp_diastolic",
           "systolic", "diastolic", "sbp", "dbp"}
for chunk in chunks:
    for key in chunk["metadata"]:
        assert key.lower() not in BP_KEYS, \
            f"BP key '{key}' found in metadata of chunk {chunk['chunk_id']}"
print("No BP keys in metadata ✓")

# conditions is a pipe-separated string
for chunk in chunks:
    conds = chunk["metadata"].get("conditions", "")
    assert isinstance(conds, str), \
        f"conditions must be str: {chunk['chunk_id']}"
    assert "," not in conds or "|" in conds, \
        f"conditions must be pipe-separated: {chunk['chunk_id']} — got {conds!r}"
print("Conditions format: pipe-separated ✓")

# PAT-CHR-005 special chunks
chr5_chunks = [c for c in chunks if c["patient_id"] == "PAT-CHR-005"]
chr5_types  = {c["source_type"] for c in chr5_chunks}
assert "discharge_summary" in chr5_types, "PAT-CHR-005 missing discharge_summary chunk"
assert "medication_reconciliation" in chr5_types, \
    "PAT-CHR-005 missing medication_reconciliation chunk"
print("PAT-CHR-005 discharge_summary and medication_reconciliation present ✓")

# doctor_note == 50, allergy == 15
assert by_type.get("doctor_note") == 50, \
    f"Expected 50 doctor_note chunks, got {by_type.get('doctor_note')}"
assert by_type.get("allergy") == 15, \
    f"Expected 15 allergy chunks, got {by_type.get('allergy')}"
print(f"doctor_note == {by_type['doctor_note']} ✓   allergy == {by_type['allergy']} ✓")

# ---------------------------------------------------------------------------
# Scenario tests
# ---------------------------------------------------------------------------

# Test 1 — PAT-CHR-001 partial_adherence doctor_note anchor
chr1_chunks = [c for c in chunks
               if c["patient_id"] == "PAT-CHR-001"
               and c["source_type"] == "doctor_note"]
v3_chunk = next(c for c in chr1_chunks
                if c["metadata"]["visit_role"] == "partial_adherence")
assert "PAT-CHR-001" in v3_chunk["text"].split(".")[0]
assert "partial" in v3_chunk["text"].lower() or "adherence" in v3_chunk["text"].lower()
print("Test 1: PAT-CHR-001 v3 doctor_note anchor correct ✓")

# Test 2 — PAT-CHR-001 v4 prescription chunk contains Glibenclamide
chr1_rx = [c for c in chunks
           if c["patient_id"] == "PAT-CHR-001"
           and c["source_type"] == "prescription"]
v4_rx = next(c for c in chr1_rx
             if c["metadata"]["visit_role"] == "second_medication_added")
assert "Glibenclamide" in v4_rx["text"]
assert "PAT-CHR-001" in v4_rx["text"].split(".")[0]
print("Test 2: PAT-CHR-001 v4 prescription chunk correct ✓")

# Test 3 — PAT-MOD-003 allergy chunk
mod3_allergy = next(c for c in chunks
                    if c["patient_id"] == "PAT-MOD-003"
                    and c["source_type"] == "allergy")
assert "PAT-MOD-003" in mod3_allergy["text"].split(".")[0]
assert "Aspirin" in mod3_allergy["text"]
assert mod3_allergy["metadata"]["visit_id"] is None
print("Test 3: PAT-MOD-003 allergy chunk correct ✓")

# Test 4 — PAT-CHR-005 discharge_summary chunk
chr5_discharge = next(c for c in chunks
                      if c["patient_id"] == "PAT-CHR-005"
                      and c["source_type"] == "discharge_summary")
assert "PAT-CHR-005" in chr5_discharge["text"].split(".")[0]
assert ("hospitalisation" in chr5_discharge["text"].lower() or
        "hospitalization" in chr5_discharge["text"].lower())
print("Test 4: PAT-CHR-005 discharge_summary chunk correct ✓")

# Test 5 — 20 random chunks begin with patient_id
random.seed(42)
sample = random.sample(chunks, min(20, len(chunks)))
for chunk in sample:
    pid   = chunk["patient_id"]
    first = chunk["text"].split(".")[0]
    assert pid in first, \
        f"Chunk {chunk['chunk_id']}: first sentence missing patient_id"
print("Test 5: 20 sampled chunks all begin with patient_id ✓")

# ---------------------------------------------------------------------------
# Negative tests
# ---------------------------------------------------------------------------

# Negative Test 1 — chunk without patient_id in first sentence is rejected
bad_chunk = {
    "chunk_id":   "VST-MOD-001-001-doctor_note-01",
    "patient_id": "PAT-MOD-001",
    "visit_id":   "VST-MOD-001-001",
    "source_type": "doctor_note",
    "text": "The patient was seen for a follow-up visit today.",
    "metadata": {
        "patient_id":       "PAT-MOD-001",
        "visit_id":         "VST-MOD-001-001",
        "visit_date":       "2023-01-10",
        "source_type":      "doctor_note",
        "conditions":       "T2DM",
        "visit_type":       "initial",
        "visit_role":       "initial_diagnosis",
        "semantic_focus":   "lab_improvement",
        "timeline_pattern": "regular_quarterly",
        "has_medication_change": False,
        "has_hospitalization":   False,
        "has_lab_trend":         False,
    },
}
try:
    validate_chunk(bad_chunk, patient_id="PAT-MOD-001")
    print("ERROR: Should have raised ChunkerError")
    sys.exit(1)
except ChunkerError as e:
    assert "patient_id" in str(e).lower() or "anchor" in str(e).lower(), \
        f"Wrong error message: {e}"
print("Negative Test 1: Missing patient_id in anchor caught ✓")

# Negative Test 2 — BP key in metadata is rejected
bad_meta_chunk = copy.deepcopy(bad_chunk)
bad_meta_chunk["text"] = "Doctor note for PAT-MOD-001 initial visit on 2023-01-10: T2DM."
bad_meta_chunk["metadata"]["bp_systolic"] = 130
try:
    validate_chunk(bad_meta_chunk, patient_id="PAT-MOD-001")
    print("ERROR: Should have raised ChunkerError for BP key")
    sys.exit(1)
except ChunkerError as e:
    assert "bp" in str(e).lower() or "forbidden" in str(e).lower(), \
        f"Wrong error message: {e}"
print("Negative Test 2: BP key in metadata caught ✓")

# ---------------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------------
print("""
=== Step 13 — Chunker Report ===
Total chunks generated:   {total}
By source_type:
  doctor_note:             {dn}
  lab_result:              {lr}
  prescription:            {rx}
  allergy:                 {al}
  discharge_summary:       {ds}
  medication_reconciliation: {mr}

Anchor enforcement:        PASS — all chunks begin with patient_id
BP metadata check:         PASS — no BP keys in any metadata
Conditions format:         PASS — all pipe-separated strings
Integration test:          PASS
Scenario tests:            5/5 PASS
Negative tests:            2/2 PASS

PAT-CHR-005 special chunks:
  discharge_summary:       PRESENT ✓
  medication_reconciliation: PRESENT ✓

Status: APPROVED FOR STEP 14 — METADATA BUILDER AND CHROMADB INGESTION
==================================
""".format(
    total=len(chunks),
    dn=by_type.get("doctor_note", 0),
    lr=by_type.get("lab_result", 0),
    rx=by_type.get("prescription", 0),
    al=by_type.get("allergy", 0),
    ds=by_type.get("discharge_summary", 0),
    mr=by_type.get("medication_reconciliation", 0),
))
