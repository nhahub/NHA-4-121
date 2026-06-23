# Validation Rules

## AI-Based Clinical Record Summarization System

---

# 1. Document Metadata

| Field | Value |
|---|---|
| Document Path | `docs/validation_rules.md` |
| Project Name | AI-Based Clinical Record Summarization System |
| Document Type | Official Validation Rules Reference |
| Primary Owner | Ahmed Hesham Kamel — Data Engineering Lead |
| Primary Audience | Gamal Mohamed Gad — AI/RAG Engineer |
| Secondary Audience | Backend Developer, Frontend Developer, DevOps/Testing Member, DEPI Evaluators |
| Status | READY FOR FINAL HANDOFF |
| Version | v1.0 |
| Scope | Patient JSON validation rules, dataset-level checks, validation gates, failure handling, and pipeline commands |
| Source of Truth | `validators/rules.py`, `validators/validate.py`, `validators/validation_report.py`, `scripts/validate_all.py`, `config/constants.py` |
| Related Contracts | `docs/data_schema_contract.md`, `docs/project_scope_and_safety_rules.md`, `docs/data_generation_pipeline.md`, `docs/rag_handoff_contract.md`, `docs/retrieval_enrichment_contract.md`, `docs/chunking_and_metadata_contract.md` |

---

# 2. Purpose of This Document

This document defines the official validation reference for the synthetic patient dataset used by the project.

It explains the validation rules implemented for the patient JSON records and how those rules protect:

- synthetic data quality,
- schema stability,
- SOAP generation safety,
- retrieval enrichment quality,
- chunking correctness,
- ChromaDB ingestion safety,
- grounded RAG answers,
- citation reliability,
- and demo readiness.

The validation layer is the hard gate between Ahmed's data engineering work and Gamal's RAG implementation.

```text
Invalid data must not enter SOAP generation, retrieval enrichment, chunking, embedding, or ChromaDB ingestion.
```

---

# 3. Validation Philosophy

The validation system is intentionally simple and deterministic.

It uses plain Python rules instead of external schema engines or complex frameworks because the project is an academic engineering system with a small, controlled dataset.

The validator is designed to be:

- readable,
- explainable,
- deterministic,
- easy to debug,
- suitable for student-team collaboration,
- strict enough to protect RAG quality,
- and simple enough to defend during DEPI evaluation.

The validator does not perform medical diagnosis, treatment recommendation, risk scoring, prediction, or clinical inference.

It only checks whether synthetic structured records obey the locked project contract.

---

# 4. Validation Architecture

The validation implementation is split across three main files.

| File | Responsibility |
|---|---|
| `validators/rules.py` | Implements the authoritative V1–V13 validation rules. |
| `validators/validate.py` | Loads patient files, runs `validate_patient()`, supports quarantine/report workflow. |
| `validators/validation_report.py` | Formats validation results into readable console/report output. |

The command-line workflow is handled by:

| File | Responsibility |
|---|---|
| `scripts/validate_all.py` | Runs validation across generated patient files and enforces dataset-level checks. |

The most important public function is:

```python
validate_patient(patient: dict[str, Any]) -> list[ValidationIssue]
```

It runs rules V1–V12 and returns structured validation issues instead of raising exceptions. V13 is run separately as a report.

---

# 5. Validation Issue Model

Each validation issue is represented as:

```python
ValidationIssue(
    rule_id: str,
    severity: Literal["FAIL", "WARN"],
    patient_id: str,
    message: str,
    location: str = "",
)
```

## Fields

| Field | Meaning |
|---|---|
| `rule_id` | Validation rule identifier such as `V1`, `V2`, `V12`, or `V13`. |
| `severity` | Either `FAIL` or `WARN`. |
| `patient_id` | The patient record affected by the issue. |
| `location` | Path-like hint showing where the problem was found. |
| `message` | Human-readable explanation of the issue. |

## Severity Meanings

| Severity | Meaning | Pipeline Action |
|---|---|---|
| `FAIL` | The record violates a hard safety/schema/data rule. | Stop. Do not proceed to SOAP, enrichment, or ingestion. |
| `WARN` | The record has a reviewable issue that should be fixed before demo. | Review and fix when possible. Do not ignore before final delivery. |

---

# 6. Validation Gate Policy

Validation is a hard gate in the project pipeline.

```text
Data generation
    ↓
Structured validation
    ↓
SOAP generation only if zero FAIL
    ↓
SOAP audit
    ↓
Final validation
    ↓
Retrieval enrichment
    ↓
Enrichment audit
    ↓
Chunking and metadata
    ↓
ChromaDB ingestion
```

## Hard Gate Rule

```text
FAIL count must be 0 before data can move forward.
```

This applies before:

- SOAP generation,
- retrieval enrichment,
- chunking,
- ChromaDB ingestion,
- RAG testing,
- backend demo usage.

## Why This Matters

Bad structured data causes bad retrieval.

A single invalid patient file can create:

- missing chunks,
- incorrect citations,
- wrong metadata filters,
- unsafe allergy answers,
- broken timeline ordering,
- incorrect lab trend summaries,
- or unsupported RAG responses.

---

# 7. Authoritative Rule List

There are exactly 13 validation rules.

```text
V1 through V13
```

| Rule | Name | Severity |
|---|---|---|
| V1 | Chronological visit order | FAIL |
| V2 | Allergy-medication conflict prevention | FAIL |
| V3 | Impossible vitals and age bounds | FAIL |
| V4 | Required fields, schema version, types, and forbidden `demographics.age` | FAIL/WARN |
| V5 | Reference integrity for `prior_visit_id` and allergy `source_visit_id` | WARN |
| V6 | Duplicate visit IDs | FAIL |
| V7 | Enums, ID patterns, tier rules, and CKD constraints | FAIL |
| V8 | Date format and valid calendar dates | FAIL |
| V9 | BP forbidden inside labs | FAIL |
| V10 | `timeline_events` forbidden anywhere in patient JSON | FAIL |
| V11 | Medication whitelist, expected frequency, and expected route | FAIL |
| V12 | Dataset diversity fingerprint and retrieval signature validation | FAIL/WARN |
| V13 | Embedding similarity report helper | REPORT |

---

# 8. Rule V1 — Chronological Visit Order

## Purpose

Ensures that visits are ordered chronologically inside each patient record.

## Check

For every patient:

```text
visits[i].visit_date must not be earlier than visits[i-1].visit_date
```

## Severity

```text
FAIL
```

## Example Failure

```text
Visit 1: 2024-06-20
Visit 2: 2024-03-15
```

## Why It Matters

Chronology protects:

- timeline views,
- lab trend summaries,
- medication progression,
- prior visit references,
- longitudinal RAG answers,
- and demo patient storytelling.

## Fix

Reorder visits or correct the wrong `visit_date` value.

---

# 9. Rule V2 — Allergy-Medication Conflict Prevention

## Purpose

Prevents a medication record from directly contradicting the allergy registry.

## Check

For each medication in every visit:

```text
medication.medication_name.lower() must not equal allergy_registry[].allergen.lower()
```

## Severity

```text
FAIL
```

## Example Failure

```json
"allergy_registry": [
  { "allergen": "Penicillin" }
],
"medications": [
  { "medication_name": "Penicillin" }
]
```

## Why It Matters

This protects safety-related retrieval and prevents the RAG system from surfacing contradictory medication/allergy evidence.

## Important Limitation

This is a generic string-match safety rule.

It does not infer drug classes, cross-reactivity, or clinical contraindications.

That is intentional because the project is not a clinical decision support system.

## Fix

Change the synthetic medication record or change the allergy registry so they do not directly conflict.

---

# 10. Rule V3 — Impossible Vitals and Age Bounds

## Purpose

Prevents impossible or unrealistic synthetic vital signs and invalid patient age at visit time.

## Checks

The validator checks numeric ranges for visit vitals, including:

```text
bp_systolic
bp_diastolic
heart_rate
weight_kg
bmi
```

It also calculates age from:

```text
demographics.date_of_birth + visit.visit_date
```

and checks that age is within the allowed adult range.

## Severity

```text
FAIL
```

## Examples of Failure

```text
bp_systolic = 300
heart_rate = 10
bmi = 80
age_at_visit = 12
```

## Why It Matters

Impossible values damage:

- SOAP credibility,
- retrieval trust,
- demo realism,
- and evaluator confidence.

## Fix

Correct the relevant vital value or date field.

---

# 11. Rule V4 — Required Fields and Forbidden Demographic Age

## Purpose

Ensures the patient JSON contains the fields required by generators, SOAP, ingestion, RAG, citations, and frontend display.

## Checks

V4 checks:

- required top-level fields,
- `schema_version`,
- demographics structure,
- required demographic fields,
- forbidden `demographics.age`,
- metadata structure and required `metadata.tier`,
- visits as an array,
- required visit fields,
- vitals as an object,
- required vital fields,
- labs as an array,
- required lab fields,
- medications as an array,
- required medication fields,
- `soap_note` as an object,
- required SOAP sections,
- allergy registry as an array,
- required allergy fields.

## Severity

V4 can produce both `FAIL` and `WARN`.

| Case | Severity |
|---|---|
| Missing top-level field | FAIL |
| Wrong `schema_version` | FAIL |
| Invalid object/array type | FAIL |
| Missing demographics field | FAIL |
| `demographics.age` present | FAIL |
| Missing `metadata.tier` | FAIL |
| Missing vital field | FAIL |
| Missing lab field | FAIL |
| Missing medication field | FAIL |
| Missing SOAP section | FAIL |
| Missing allergy field | FAIL |
| Missing some visit descriptive fields | WARN |

## Forbidden Field

```text
demographics.age
```

Age must be derived from:

```text
date_of_birth + visit_date
```

## Why It Matters

RAG and citation logic depend on predictable fields.

If fields are missing or stored in inconsistent places, ingestion may skip evidence or create broken chunks.

## Fix

Add missing required fields, remove forbidden fields, and restore expected object/list shapes.

---

# 12. Rule V5 — Reference Integrity

## Purpose

Checks whether references inside the patient record point to real visit IDs.

## Checks

V5 verifies:

```text
visit.prior_visit_id
allergy_registry[].source_visit_id
```

If a reference is not null, it must match a visit ID inside the same patient record.

## Severity

```text
WARN
```

## Example Failure

```text
prior_visit_id = VST-MOD-001-999
```

but no such visit exists.

## Why It Matters

Broken references weaken:

- timeline reconstruction,
- allergy source tracing,
- citation reliability,
- and longitudinal RAG answers.

## Fix

Set the reference to the correct visit ID, or set it to `null` when no prior/source visit is available.

---

# 13. Rule V6 — Duplicate Visit IDs

## Purpose

Ensures every visit in a patient record has a unique `visit_id`.

## Check

For each patient:

```text
No two visits may share the same visit_id.
```

## Severity

```text
FAIL
```

## Example Failure

```text
VST-MOD-001-002 appears twice in the same patient file.
```

## Why It Matters

`visit_id` is a citation anchor.

Duplicate visit IDs can cause:

- incorrect citations,
- chunk ID collisions,
- timeline ambiguity,
- and retrieval debugging confusion.

## Fix

Regenerate or correct the duplicated visit ID.

---

# 14. Rule V7 — Enums, ID Patterns, Tier Rules, and CKD Constraints

## Purpose

Ensures that all locked values and IDs follow the project contract.

## Checks

V7 validates:

- `patient_id` format,
- `visit_id` format,
- linked `document_id` format,
- `metadata.tier`,
- `demographics.sex`,
- `conditions`,
- allergy `severity`,
- `visit_type`,
- `lab_type`,
- lab `flag`,
- medication `frequency`,
- medication `route`,
- CKD co-occurrence and tier constraints.

## Severity

```text
FAIL
```

## Locked Enums

### Conditions

```text
Acute_URTI
T2DM
HTN
Asthma
IDA
GERD
Dyslipidemia
Allergic_Rhinitis
UTI
CKD
```

### Visit Types

```text
initial
follow_up
emergency
hospitalization
```

### Lab Types

```text
HbA1c
FBG
Creatinine
Hemoglobin
Ferritin
LDL
```

### Lab Flags

```text
NORMAL
HIGH
LOW
```

### Allergy Severity

```text
mild
moderate
severe
```

### Medication Frequency

```text
once_daily
twice_daily
as_needed
```

### Medication Route

```text
oral
inhaled
```

The following route is forbidden:

```text
subcutaneous
```

## CKD Rule

CKD is complication-only.

If a patient has:

```text
CKD
```

then the patient must also have:

```text
T2DM
HTN
metadata.tier = chronic
```

## Examples of Failure

```text
condition = Diabetes
route = subcutaneous
lab_type = BP
metadata.tier = severe
CKD without HTN
CKD in moderate tier
```

## Why It Matters

Enums and ID patterns protect:

- ChromaDB filters,
- source-type routing,
- retrieval consistency,
- citations,
- dataset reproducibility,
- and handoff stability.

## Fix

Use only locked constants from `config/constants.py`.

---

# 15. Rule V8 — Date Format and Calendar Validity

## Purpose

Ensures all date fields use the locked format and represent valid calendar dates.

## Date Format

```text
YYYY-MM-DD
```

## Checked Date Fields

The validator checks date-like fields including:

```text
demographics.date_of_birth
visits[].visit_date
allergy_registry[].recorded_date
medications[].start_date
medications[].stop_date
```

## Severity

```text
FAIL
```

## Example Failures

```text
2024/01/10
10-01-2024
2024-13-40
```

## Why It Matters

Date validity protects:

- visit chronology,
- medication timelines,
- allergy record dates,
- lab trend summaries,
- timeline endpoint behavior,
- and temporal retrieval queries.

## Fix

Convert dates to valid `YYYY-MM-DD` strings.

---

# 16. Rule V9 — BP Forbidden Inside Labs

## Purpose

Enforces the authoritative BP rule.

```text
Blood pressure is a vital sign, not a lab value.
```

## Correct BP Location

```text
visit.vitals.bp_systolic
visit.vitals.bp_diastolic
```

## Forbidden Locations

BP must not appear in:

```text
visit.labs[]
lab_type
lab object keys
patient metadata
chunk metadata
```

## Forbidden BP-Like Lab Terms

The validator checks BP-like values such as:

```text
bp
blood pressure
blood_pressure
systolic
diastolic
bp_systolic
bp_diastolic
sbp
dbp
```

## Severity

```text
FAIL
```

## Why It Matters

BP queries should retrieve doctor-note text or vitals-derived text, not lab chunks or metadata filters.

Putting BP in labs damages:

- lab trend retrieval,
- source-type routing,
- metadata safety,
- and RAG evidence boundaries.

## Fix

Remove BP from labs and keep it only inside `visit.vitals`.

---

# 17. Rule V10 — `timeline_events` Forbidden

## Purpose

Prevents duplicate timeline truth inside patient JSON.

## Check

The key:

```text
timeline_events
```

is forbidden anywhere in the patient JSON.

## Severity

```text
FAIL
```

## Why It Matters

Timeline must be reconstructed from visits.

A stored `timeline_events` field creates:

- duplicated truth,
- stale summaries,
- conflicts with visits,
- and unreliable timeline endpoints.

## Fix

Delete `timeline_events` and derive timeline views from `visits[]`.

---

# 18. Rule V11 — Medication Whitelist, Frequency, and Route

## Purpose

Ensures all medication records use the locked medication whitelist and expected medication configuration.

## Checks

For each medication record:

- `medication_name` must exist in `MEDICATION_WHITELIST`,
- `frequency` must be valid,
- `route` must be valid,
- `frequency` must match the whitelist specification for that medication,
- `route` must match the whitelist specification for that medication.

## Severity

```text
FAIL
```

## Medication Whitelist

```text
Metformin
Glibenclamide
Lisinopril
Amlodipine
Losartan
Salbutamol inhaler
Budesonide inhaler
Ferrous sulfate
Omeprazole
```

## Allowed Routes

```text
oral
inhaled
```

## Forbidden Route

```text
subcutaneous
```

## Why It Matters

Medication consistency protects:

- prescription chunks,
- allergy conflict validation,
- medication timeline questions,
- treatment-history retrieval,
- and grounded RAG answers.

## Fix

Use medication names, frequency, and route exactly as defined in `config/constants.py`.

---

# 19. Rule V12 — Dataset Diversity and Retrieval Signature

## Purpose

Enforces dataset diversity and retrieval metadata correctness across the dataset to ensure a wide semantic and temporal space.

## Checks

For every patient:
- `metadata.retrieval_signature` must be present and unique across the dataset.
- `metadata.retrieval_intent_tags` must contain between 2 and 4 valid tags.
- Every visit must have a `visit_role`, `clinical_event`, and `retrieval_context`.
- The diversity fingerprint (composed of tier, conditions, semantic focus, timeline pattern, visit roles, main medications, lab focus, and allergens) must be unique across the dataset.
- Patients with overlapping primary conditions must not share both `semantic_focus` and `timeline_pattern`.

## Severity

```text
FAIL (when strict=True) or WARN (when strict=False)
```

## Why It Matters

Ensures the generated dataset covers diverse clinical scenarios and prevents synthetic patient clustering, which would degrade retrieval testing fidelity.

## Fix

Regenerate the dataset to resolve fingerprint or signature collisions.

---

# 20. Rule V13 — Embedding Similarity Report

## Purpose

Generates a report-only audit of chunk similarity using embeddings to detect near-duplicate chunks.

## Methodology

Computes cosine similarity of `sentence-transformers` embeddings across chunks (from different visits). Identifies pairs of chunks with high similarity.

## Checks

This is a report-only rule. It does not block ingestion.
It flags chunk pairs with similarities exceeding thresholds:
- `critical_threshold` (e.g., >= 0.95)
- `warn_threshold` (e.g., >= 0.88)
- informational (e.g., >= 0.82)

## Severity

```text
REPORT
```

## Why It Matters

Helps track chunk quality and diversity after SOAP generation and enrichment, ensuring the retrieval system operates on distinct chunks.

## Fix

If critical similarities are flagged, review chunking strategy, SOAP templates, or retrieval enrichment text to increase distinctiveness.

---

# 21. Dataset-Level Validation Checks

V1–V11 validate individual patient records, V12 validates dataset diversity and signatures, and V13 provides chunk similarity reports.

The project also requires dataset-level checks before final handoff or ingestion.

These checks belong to the command-line workflow in `scripts/validate_all.py`, not to the per-patient rule list.

## Dataset-Level Checks

| Check | Expected Behavior |
|---|---|
| Patient count | `pilot` mode must contain 5 patients; `full` mode must contain 15 patients. |
| Tier distribution | Full mode must match 1 normal, 9 moderate, 5 chronic. |
| Unique patient IDs | No two patient files may contain the same `patient_id`. |
| CKD count limit | CKD must appear in at most 2 chronic patients. |

## Why These Are Separate From V1–V13

The V-rules operate on one patient at a time.

Dataset-level checks require visibility across all files.

Example:

```text
Two files may each be valid individually but still share the same patient_id.
```

That issue can only be detected at dataset level.

---

# 22. Validation Commands

## Generate Full Dataset and Validate

```bash
python scripts/generate_all.py --mode full --clean
python scripts/validate_all.py --mode full
```

## Generate Pilot Dataset and Validate

```bash
python scripts/generate_all.py --mode pilot --clean
python scripts/validate_all.py --mode pilot
```

## Validate With Quarantine Output

```bash
python scripts/validate_all.py --mode full --quarantine
```

## SOAP Safety Workflow

```bash
python scripts/generate_all.py --mode full --clean
python scripts/validate_all.py --mode full
python scripts/generate_soap.py --dry-run
python scripts/generate_soap.py
python scripts/validate_all.py --mode full
```

## Recommended Final Data Check Before Ingestion

```bash
python scripts/validate_all.py --mode full
```

Ingestion should not run unless this command passes with:

```text
FAIL violations = 0
Dataset-level checks = PASS
```

---

# 23. Quarantine Policy

Invalid patient records must not be ingested.

## Approved Records

Approved records belong in:

```text
data/patients/
```

## Invalid Records

Invalid or rejected records belong in:

```text
data/quarantine/
```

## Quarantine Contents

The quarantine folder may contain:

- invalid patient JSON files,
- validation issue reports,
- SOAP generation issue reports,
- debug outputs for failed records.

## Ingestion Rule

```text
The ingestion pipeline must read only from data/patients/.
```

It must never read from:

```text
data/quarantine/
```

---

# 24. Relationship Between Validation and SOAP

SOAP notes are generated after structured data passes validation.

## Current SOAP Implementation

In the current implementation:

```text
SOAP notes are generated deterministically from structured JSON using approved templates.
No LLM is used during SOAP generation.
```

## Validation Before SOAP

Before SOAP generation:

```text
structured patient record must have zero FAIL issues
```

## Validation After SOAP

After SOAP generation:

```text
validation must run again
```

This confirms that SOAP generation did not produce malformed records or missing sections.

## SOAP Audit

SOAP audit is separate from V1–V13.

It checks that SOAP text remains grounded and does not contain unsafe or unsupported phrases.

---

# 25. Relationship Between Validation and Retrieval Enrichment

Retrieval enrichment is downstream from validation.

The enrichment layer includes:

```text
ingestion/retrieval_enricher.py
ingestion/retrieval_enrichment_auditor.py
```

## Rule

```text
Retrieval enrichment must only run on validated patient records.
```

## Why

Enrichment text is derived from structured patient facts.

If the structured facts are invalid, enrichment will amplify bad evidence into chunk text and harm retrieval quality.

## Enrichment Audit

Enrichment text should be audited before it is used in chunks or ingestion.

The enrichment auditor protects against:

- unsupported condition wording,
- unsupported medication mentions,
- unsupported lab mentions,
- unsafe treatment recommendation wording,
- BP metadata-like wording,
- invalid source type usage,
- and unrendered placeholders.

---

# 26. Relationship Between Validation and Ingestion

Validation protects the RAG pipeline.

The ingestion pipeline may assume that validated patient records have:

- valid patient IDs,
- valid visit IDs,
- chronological visits,
- stable visit dates,
- valid source evidence fields,
- valid labs,
- valid medications,
- no BP inside labs,
- no forbidden `timeline_events`,
- no forbidden `demographics.age`,
- and valid medication whitelist usage.

## Ingestion Must Not Repair Data

The ingestion layer should not silently fix invalid patient records.

If ingestion sees invalid data, the correct action is:

```text
Stop → validate → fix data → regenerate → validate again
```

---

# 27. Common Failure Examples

## BP Stored as Lab

```json
{
  "lab_type": "BP",
  "value": "140/90"
}
```

Fails:

```text
V9
```

Fix:

```json
"vitals": {
  "bp_systolic": 140,
  "bp_diastolic": 90
}
```

## CKD Without HTN

```json
"conditions": ["T2DM", "CKD"]
```

Fails:

```text
V7
```

Fix:

```json
"conditions": ["T2DM", "HTN", "CKD"]
```

and:

```json
"metadata": { "tier": "chronic" }
```

## Forbidden Route

```json
"route": "subcutaneous"
```

Fails:

```text
V7, V11, or V12
```

Fix:

Use only:

```text
oral
inhaled
```

## Stored Age

```json
"demographics": {
  "age": 45
}
```

Fails:

```text
V4
```

Fix:

Remove `age` and use `date_of_birth`.

## Timeline Events Field

```json
"timeline_events": []
```

Fails:

```text
V10
```

Fix:

Delete the field and derive timelines from `visits[]`.

---

# 28. What Validation Does Not Do

The validator does not:

- diagnose diseases,
- recommend treatments,
- infer clinical status,
- predict outcomes,
- score patient risk,
- judge whether medication choices are clinically optimal,
- perform advanced medical reasoning,
- call an LLM,
- call external APIs,
- write to ChromaDB,
- generate SOAP text,
- or build RAG answers.

It only enforces the project’s locked synthetic data contract.

---

# 29. Responsibilities

## Ahmed Hesham Kamel

Ahmed owns:

- validation rule implementation,
- validation documentation,
- generator compatibility,
- constants alignment,
- schema safety,
- and data quality before handoff.

## Gamal Mohamed Gad

Gamal depends on validation to guarantee safe input for:

- chunking,
- metadata extraction,
- retrieval enrichment,
- ChromaDB ingestion,
- retrieval tests,
- grounding,
- and citations.

## DevOps/Testing Member

The DevOps/Testing member supports:

- running validation commands,
- smoke checks,
- demo readiness checks,
- and ensuring invalid files do not enter the ingestion workflow.

---

# 30. Final Validation Checklist

Before handing data to the RAG engineer, confirm:

```text
[ ] python scripts/generate_all.py --mode full --clean succeeds
[ ] python scripts/validate_all.py --mode full succeeds
[ ] Patient count is 15
[ ] Tier distribution is 1 normal, 9 moderate, 5 chronic
[ ] CKD patients are at most 2
[ ] No validation FAIL issues exist
[ ] WARN issues are reviewed
[ ] SOAP generation dry-run succeeds
[ ] SOAP generation succeeds
[ ] Final validation after SOAP succeeds
[ ] data/quarantine/ does not contain active records intended for ingestion
[ ] ingestion reads only from data/patients/
```

---

# 31. Final Summary

The validation system is the project’s data quality firewall.

It protects the system in this order:

```text
Schema correctness
→ data consistency
→ SOAP safety
→ retrieval enrichment quality
→ chunking stability
→ metadata reliability
→ citation accuracy
→ grounded RAG answers
```

The validation rules V1–V12 are authoritative for dataset validation, and V13 serves as an ingestion-readiness check.

Dataset-level checks are required before final handoff and ingestion.

No patient data should be ingested into ChromaDB unless validation passes with zero FAIL issues.

This document is the official validation reference for the project and should be used by the team and any LLM tools working on the repository.
