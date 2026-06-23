# Data Generation Pipeline

## AI-Based Clinical Record Summarization System

---

# 1. Document Metadata

| Field | Value |
|---|---|
| Document Path | `docs/data_generation_pipeline.md` |
| Project Name | AI-Based Clinical Record Summarization System |
| Document Type | Official Data Generation Pipeline Reference |
| Primary Owner | Ahmed Hesham Kamel — Data Engineering Lead |
| Primary Audience | Gamal Mohamed Gad — AI/RAG Engineer |
| Secondary Audience | Backend Developer, Frontend Developer, DevOps/Testing Member, DEPI Evaluators |
| Status | READY FOR FINAL HANDOFF |
| Version | v1.0 |
| Scope | Deterministic synthetic patient generation, validation gates, SOAP generation, audit, export, and handoff to ingestion/RAG |
| Related Contracts | `docs/data_schema_contract.md`, `docs/validation_rules.md`, `docs/retrieval_enrichment_contract.md`, `docs/rag_handoff_contract.md`, `docs/project_scope_and_safety_rules.md`, `docs/team_ownership_and_architecture.md` |

---

# 2. Purpose of This Document

This document explains the complete data generation workflow used to produce the synthetic clinical records for the project.

It is intended to answer the following questions:

- How are patient JSON files generated?
- Which files participate in the generation pipeline?
- What is the correct execution order?
- Where does validation happen?
- When is SOAP generated?
- What is exported to `data/patients/`?
- What is blocked into `data/quarantine/`?
- What does Gamal receive as stable input for ingestion and RAG?

This document is not a general architecture overview. It focuses only on Ahmed's data pipeline and the handoff boundary into Gamal's ingestion/RAG work.

---

# 3. Pipeline Summary

The final data generation pipeline is:

```text
patient shells
→ visits
→ medications
→ labs
→ allergies
→ structured validation hard gate
→ deterministic SOAP generation
→ SOAP audit
→ final validation
→ export to data/patients/ or data/quarantine/
```

The most important rule is:

```text
Validation is the hard gate before SOAP generation and ingestion.
```

A patient that fails structured validation must not receive regenerated SOAP notes and must not be ingested into ChromaDB.

---

# 4. Pipeline Safety Principles

## 4.1 Deterministic Structured Generation

All structured data generation is deterministic.

The following files must not call an LLM:

```text
generators/patient_generator.py
generators/visit_generator.py
generators/lab_generator.py
generators/medication_generator.py
generators/allergy_generator.py
```

These files produce structured facts only.

They do not generate diagnoses dynamically, prescribe medications, infer conditions, or modify data using AI.

## 4.2 Validation Before SOAP

SOAP generation runs only after structured validation passes.

This avoids generating narrative text from invalid structured records.

## 4.3 SOAP Is Deterministic

In the current implementation, SOAP notes are generated deterministically from structured JSON using approved templates.

SOAP generation does not call an LLM.

The LLM is used later only in the RAG answer generation layer, after retrieval.

## 4.4 Data Before RAG

The RAG pipeline must consume only validated patient records from:

```text
data/patients/
```

It must not read from:

```text
data/quarantine/
```

---

# 5. Files Involved in the Pipeline

## 5.1 Configuration Files

| File | Responsibility |
|---|---|
| `config/constants.py` | Single source of truth for locked enums, medication whitelist, lab types, visit types, source types, dataset distribution, route values, and generation constants. |
| `config/paths.py` | Centralized project paths such as `PATIENTS_DIR`, `QUARANTINE_DIR`, and helper path functions. |
| `config/showcase_patients.json` | Stores selected showcase patient IDs for demo usage. |

## 5.2 Generator Files

| File | Responsibility |
|---|---|
| `generators/patient_generator.py` | Builds deterministic patient shells, patient IDs, demographics, tier assignment, condition assignment, and patient blueprints. |
| `generators/visit_generator.py` | Adds visit timelines, visit dates, visit types, vitals, linked documents, and `prior_visit_id`. |
| `generators/medication_generator.py` | Adds visit-level medications from the whitelist only, with stable `start_date` and `stop_date` timeline behavior. |
| `generators/lab_generator.py` | Adds visit-level labs using locked lab types only. BP is never generated as a lab. |
| `generators/allergy_generator.py` | Adds allergy registry records using safe non-medication allergens and source visit references. |

## 5.3 Validation Files

| File | Responsibility |
|---|---|
| `validators/rules.py` | Implements V1–V13 per-patient validation rules. |
| `validators/validate.py` | Loads patient files and runs validation across patient JSON records. |
| `validators/validation_report.py` | Formats validation results into readable reports. |
| `scripts/validate_all.py` | Runs project-level validation and dataset-level checks. |

## 5.4 SOAP Files

| File | Responsibility |
|---|---|
| `soap/soap_contract.py` | Shared SOAP structure, section names, template contracts, required facts, and allowed placeholders. |
| `soap/soap_templates.py` | Deterministic SOAP wording templates. |
| `soap/soap_selector.py` | Deterministic template selection. |
| `soap/soap_renderers.py` | Extracts and formats structured facts for SOAP. |
| `soap/soap_semantics.py` | Adds grounded semantic wording diversity for retrieval quality. |
| `soap/soap_safety.py` | Shared safety constants used by SOAP validation and auditing. |
| `soap/soap_auditor.py` | Audits SOAP notes for unsupported wording, missing facts, unsafe phrases, and formatting problems. |
| `soap/soap_generator.py` | Adds deterministic SOAP notes to validated patient records. |

## 5.5 Script Files

| File | Responsibility |
|---|---|
| `scripts/generate_all.py` | Master data generation script. Runs structured generation, validation gate, SOAP generation, SOAP audit, final validation, and export. |
| `scripts/generate_soap.py` | Regenerates SOAP for existing patient JSON files, with pre-validation gate and SOAP audit. |
| `scripts/validate_all.py` | Runs validation and dataset-level checks against `data/patients/`. |
| `scripts/check_retrieval_enricher_output.py` | Debug tool for inspecting retrieval enrichment output for one patient/visit/source type. |

---

# 6. Dataset Modes

The pipeline supports two dataset modes.

| Mode | Expected Count | Distribution | Purpose |
|---|---:|---|---|
| `pilot` | 5 | 2 normal, 2 moderate, 1 chronic | Fast testing and early validation. |
| `full` | 15 | 1 normal, 9 moderate, 5 chronic | Final dataset for ingestion, RAG, and demo. |

Use `full` for final handoff to Gamal.

---

# 7. Detailed Pipeline Stages

## 7.1 Stage 1 — Patient Shell Generation

Implemented by:

```text
generators/patient_generator.py
```

Creates the base patient object:

```text
schema_version
patient_id
demographics
conditions
allergy_registry = []
visits = []
metadata.tier
```

This stage owns:

- patient IDs,
- patient tiers,
- demographics,
- condition assignment,
- deterministic blueprints,
- dataset count,
- tier distribution,
- CKD count guard.

It does not generate visits, vitals, labs, medications, allergies, or SOAP.

## 7.2 Stage 2 — Visit Generation

Implemented by:

```text
generators/visit_generator.py
```

Adds chronological visits to each patient.

This stage owns:

- `visit_id`,
- `visit_date`,
- `visit_type`,
- `attending_physician`,
- `diagnoses`,
- `vitals`,
- `linked_documents`,
- `prior_visit_id`,
- empty placeholder SOAP structure before final SOAP generation.

Important BP rule:

```text
BP exists only in visit.vitals.bp_systolic and visit.vitals.bp_diastolic.
```

BP must never be stored in labs or metadata.

## 7.3 Stage 3 — Medication Generation

Implemented by:

```text
generators/medication_generator.py
```

Adds visit-level medication records from the locked whitelist only.

This stage owns:

- `medication_name`,
- `medication_class`,
- `dose`,
- `frequency`,
- `route`,
- `start_date`,
- `stop_date`.

Medication timeline rule:

```text
start_date represents the first documented start date of the medication, not necessarily the current visit date.
stop_date remains null unless the medication is documented as stopped.
```

Add-on medications use the date of the escalation visit as their `start_date`.

## 7.4 Stage 4 — Lab Generation

Implemented by:

```text
generators/lab_generator.py
```

Adds visit-level lab records using locked lab types only.

Allowed lab types:

```text
HbA1c
FBG
Creatinine
Hemoglobin
Ferritin
```

BP is not a lab.

Final Creatinine rule:

```text
Creatinine is generated for CKD patients or patients with combined T2DM + HTN context.
T2DM-only or HTN-only patients are not required to have Creatinine labs.
```

## 7.5 Stage 5 — Allergy Registry Generation

Implemented by:

```text
generators/allergy_generator.py
```

Adds patient-level allergy registry entries.

This stage owns:

- `allergen`,
- `reaction`,
- `severity`,
- `recorded_date`,
- `source_visit_id`.

Allergy safety rule:

```text
No medication.medication_name may match any allergy_registry[].allergen.
```

This is enforced by validation rule V2.

## 7.6 Stage 6 — Structured Validation Hard Gate

Implemented by:

```text
validators/rules.py
scripts/generate_all.py
scripts/validate_all.py
```

After structured generation and before SOAP generation, the patient must pass validation.

If a patient has any `FAIL` validation issue:

```text
Do not generate SOAP for that patient.
Do not export it as approved data.
Do not ingest it into ChromaDB.
```

## 7.7 Stage 7 — Deterministic SOAP Generation

Implemented by:

```text
soap/soap_generator.py
```

SOAP is generated only for patients that passed structured validation.

SOAP notes are generated from structured facts only.

SOAP must not:

- create medications,
- create lab values,
- create diagnoses,
- create allergies,
- modify vitals,
- modify dates,
- infer unsupported clinical meaning,
- recommend treatment,
- predict conditions.

## 7.8 Stage 8 — SOAP Audit

Implemented by:

```text
soap/soap_auditor.py
```

SOAP audit checks for:

- missing required facts,
- unrendered placeholders,
- unsafe phrases,
- debug/template leakage,
- unsupported medication rendering,
- allergy-context risk,
- section structure problems.

A patient with SOAP audit `FAIL` must not be exported as approved data.

## 7.9 Stage 9 — Final Validation

After SOAP generation and SOAP audit, validation runs again.

This ensures the patient JSON remains structurally valid after SOAP notes are added.

## 7.10 Stage 10 — Export

Export behavior:

| Result | Destination |
|---|---|
| Valid patient | `data/patients/PAT-XXX-000.json` |
| Invalid patient | `data/quarantine/PAT-XXX-000.json` |
| Issue report | `data/quarantine/PAT-XXX-000.validation_issues.json` or related issue report |

Only files in `data/patients/` are approved for ingestion.

---

# 8. Master Script Behavior

The main script is:

```text
scripts/generate_all.py
```

It performs:

```text
1. ensure project directories
2. optionally clean previous generated files
3. generate structured patients
4. run structured validation hard gate
5. generate deterministic SOAP for valid records only
6. audit SOAP
7. run final validation
8. export valid records to data/patients/
9. export invalid records and reports to data/quarantine/
10. print summary
```

Expected success summary for full mode:

```text
Mode:               full
Expected patients:  15
Generated patients: 15
Valid exported:     15
Quarantined:        0
```

Expected success summary for pilot mode:

```text
Mode:               pilot
Expected patients:  5
Generated patients: 5
Valid exported:     5
Quarantined:        0
```

---

# 9. Validation Rules Used by the Pipeline

The pipeline uses V1–V13 validation rules.

| Rule | Purpose | Severity |
|---|---|---|
| V1 | Chronological visit order | FAIL |
| V2 | Allergy contradiction check | FAIL |
| V3 | Impossible vitals and age bounds | FAIL |
| V4 | Required fields and forbidden demographic age field | WARN/FAIL |
| V5 | Prior visit reference integrity | WARN |
| V6 | Duplicate visit IDs | FAIL |
| V7 | Invalid enums and CKD co-occurrence rule | FAIL |
| V8 | Date format validation | FAIL |
| V9 | BP forbidden in labs | FAIL |
| V10 | `timeline_events` forbidden in patient JSON | FAIL |
| V11 | Medication whitelist, frequency, and route validation | FAIL |
| V12 | Dataset diversity fingerprint and retrieval signature validation | FAIL/WARN |
| V13 | Embedding similarity report helper | REPORT |

Detailed rule behavior belongs to:

```text
docs/validation_rules.md
```

---

# 10. Dataset-Level Checks

In addition to per-patient validation, `scripts/validate_all.py` performs dataset-level checks.

These checks are not new V-rules. They protect the dataset as a whole.

| Check | Purpose |
|---|---|
| Expected patient count | Confirms `pilot` has 5 and `full` has 15. |
| Tier distribution | Confirms correct `normal`, `moderate`, `chronic` distribution. |
| Unique patient IDs | Prevents duplicate patient IDs across files. |
| CKD patient count | Ensures CKD appears in no more than 2 patients. |

Expected full distribution:

```text
normal:   10
moderate: 13
chronic:  7
```

Expected pilot distribution:

```text
normal:   2
moderate: 2
chronic:  1
```

---

# 11. Approved Output Contract

A patient file in `data/patients/` means:

```text
The file passed structured validation.
SOAP was generated only after validation passed.
SOAP audit passed with zero FAIL issues.
Final validation passed.
The file is approved for ingestion.
```

A patient file in `data/quarantine/` means:

```text
The file failed validation or SOAP audit.
The file must not be ingested.
The issue report must be reviewed before correction.
```

---

# 12. Handoff to Gamal

Gamal should receive data only after Ahmed runs the final pipeline successfully.

## 12.1 Approved Handoff Inputs

Gamal may safely consume:

```text
data/patients/*.json
config/constants.py
config/paths.py
docs/data_schema_contract.md
docs/validation_rules.md
docs/data_generation_pipeline.md
docs/retrieval_enrichment_contract.md
docs/rag_handoff_contract.md
```

## 12.2 Do Not Consume

Gamal must not ingest:

```text
data/quarantine/
data/chromadb/ from old runs
logs/ as source evidence
any manually edited unvalidated JSON
```

## 12.3 Handoff Readiness Criteria

Before handoff, the following must be true:

```text
python scripts/generate_all.py --mode full --clean
python scripts/validate_all.py --mode full
```

Both commands must complete successfully.

Expected result:

```text
15 approved patient files
0 quarantined files
0 validation FAIL issues
0 SOAP audit FAIL issues
dataset-level checks PASS
```

---

# 13. Retrieval Enrichment Relationship

The data generation pipeline produces structured patient JSON and SOAP notes.

After that, Gamal may use retrieval enrichment during ingestion.

Relevant files:

```text
ingestion/retrieval_enricher.py
ingestion/retrieval_enrichment_auditor.py
```

Retrieval enrichment text is:

```text
deterministic support text
not source truth
derived from structured JSON and SOAP
used to improve semantic retrieval
subject to audit before ingestion
```

The source truth remains:

```text
patient JSON structured fields
visit-level SOAP notes
validated patient records
```

Retrieval enrichment must not introduce unsupported clinical claims.

---

# 14. Commands

## 14.1 Generate Pilot Dataset

```bash
python scripts/generate_all.py --mode pilot --clean
python scripts/validate_all.py --mode pilot
```

Use this for quick smoke testing.

## 14.2 Generate Full Dataset

```bash
python scripts/generate_all.py --mode full --clean
python scripts/validate_all.py --mode full
```

Use this before handoff to Gamal.

## 14.3 SOAP Dry Run for Existing Patients

```bash
python scripts/generate_soap.py --dry-run
```

## 14.4 Regenerate SOAP for Existing Patients

```bash
python scripts/generate_soap.py
python scripts/validate_all.py --mode full
```

## 14.5 Check One Patient's Retrieval Enrichment Output

```bash
python scripts/check_retrieval_enricher_output.py --patient-id PAT-MOD-001 --visit-index 0
```

---

# 15. Common Failure Cases

## 15.1 Validation FAIL

Cause examples:

- BP appears in labs.
- Medication is not in whitelist.
- CKD appears without T2DM + HTN + chronic tier.
- Visit dates are out of order.
- Duplicate visit IDs exist.

Action:

```text
Fix the generator or patient JSON source.
Regenerate the dataset.
Run validation again.
```

## 15.2 SOAP Audit FAIL

Cause examples:

- SOAP contains unsafe wording.
- SOAP misses required structured facts.
- SOAP contains unrendered placeholders.
- SOAP leaks internal template IDs.

Action:

```text
Fix SOAP template/rendering/audit logic.
Regenerate SOAP.
Run validation again.
```

## 15.3 Dataset-Level Check FAIL

Cause examples:

- Wrong patient count.
- Wrong tier distribution.
- Duplicate patient IDs.
- More than 2 CKD patients.

Action:

```text
Fix patient_generator.py or constants.
Regenerate full dataset with --clean.
Run validate_all.py again.
```

## 15.4 Existing Output Files Found

`scripts/generate_all.py` prevents mixing old and new records.

Action:

```bash
python scripts/generate_all.py --mode full --clean
```

---

# 16. What Must Not Be Added to This Pipeline

The data generation pipeline must not add:

```text
Kubernetes
microservices
PostgreSQL
Redis
Celery
LangGraph
agent orchestration
clinical decision support
disease prediction
treatment recommendation
real patient data
live hospital integration
```

This is an academic synthetic-data RAG demo.

The goal is stable, explainable, validated data that supports grounded retrieval.

---

# 17. Data Quality Checklist

Before final handoff, Ahmed should confirm:

```text
[ ] config/constants.py is the single source of truth.
[ ] Full mode generates 15 patients.
[ ] Pilot mode generates 5 patients.
[ ] Full tier distribution is 1 normal, 9 moderate, 5 chronic.
[ ] CKD appears in no more than 2 chronic patients.
[ ] CKD always co-occurs with T2DM and HTN.
[ ] BP appears only in visit.vitals.
[ ] BP never appears in labs.
[ ] BP never appears in metadata.
[ ] All medications come from the whitelist.
[ ] route is only oral or inhaled.
[ ] subcutaneous does not appear.
[ ] start_date reflects first documented medication start.
[ ] stop_date is null unless medication is stopped.
[ ] Creatinine appears only for CKD or T2DM + HTN context.
[ ] Allergy registry does not contradict medications.
[ ] Visits are chronological.
[ ] prior_visit_id references are valid.
[ ] SOAP notes are deterministic and grounded.
[ ] SOAP audit returns zero FAIL issues.
[ ] scripts/validate_all.py returns dataset-level PASS.
[ ] data/quarantine/ is empty after final full generation.
```

---

# 18. Final Handoff Statement

When the pipeline completes successfully, Ahmed can hand the data layer to Gamal with the following statement:

```text
The full synthetic dataset has been generated deterministically, validated with V1–V13, checked with dataset-level validation, enriched with deterministic SOAP notes, audited successfully, and exported to data/patients/. The files in data/patients/ are the only approved records for ingestion and RAG. Files in data/quarantine/ must not be ingested.
```

---

# 19. Final Classification

```text
Official Data Generation Pipeline Reference
Ready for Team Handoff
Ready for RAG Ingestion Dependency
Ready for DEPI Review
```

This document should be read together with:

```text
docs/data_schema_contract.md
docs/validation_rules.md
docs/retrieval_enrichment_contract.md
docs/rag_handoff_contract.md
docs/project_scope_and_safety_rules.md
```
