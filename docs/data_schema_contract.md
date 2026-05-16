# Data Schema Contract

## AI-Based Clinical Record Summarization System

---

# 1. Document Metadata

| Field              | Value                                                                                                                                                                |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Document Path      | `docs/data_schema_contract.md`                                                                                                                                       |
| Project Name       | AI-Based Clinical Record Summarization System                                                                                                                        |
| Document Type      | Official Data Schema Implementation Contract                                                                                                                         |
| Primary Owner      | Ahmed Hesham Kamel — Data Engineering Lead                                                                                                                           |
| Primary Audience   | Gamal Mohamed Gad — AI/RAG Engineer                                                                                                                                  |
| Secondary Audience | Backend Developer, Frontend/OCR Developer, DevOps/Testing Member, DEPI Evaluators                                                                                    |
| Status             | LOCKED — Official Schema Handoff Contract                                                                                                                            |
| Version            | v1.0                                                                                                                                                                 |
| Scope              | Patient JSON structure, schema meaning, RAG dependencies, ingestion assumptions, forbidden fields, stability rules                                                   |
| Related Contracts  | `docs/team_ownership_and_architecture.md`, `docs/validation_rules.md`, `docs/chunking_and_metadata_contract.md`, `docs/citation_contract.md`, `docs/rag_pipeline.md` |
| Source of Truth    | `data/schemas/patient_schema.json`, `config/constants.py`, validated files in `data/patients/`                                                                       |

---

# 2. Purpose of This Contract

This document defines the official patient data contract between:

```text
Ahmed Hesham Kamel
Data Engineering Lead
```

and

```text
Gamal Mohamed Gad
AI/RAG Engineer
```

The purpose of this contract is to make the patient dataset safe, predictable, and stable for:

* chunking,
* metadata extraction,
* ChromaDB ingestion,
* patient-scoped retrieval,
* grounded answer generation,
* citation formatting,
* timeline reconstruction,
* allergy retrieval,
* lab trend retrieval,
* and backend RAG integration.

This document exists because the RAG pipeline must not guess the schema.

A RAG system depends heavily on consistent document structure. If field names, ID formats, metadata assumptions, or visit structures change unexpectedly, the retrieval pipeline may silently break. This can lead to missing chunks, wrong citations, invalid filters, poor retrieval quality, or unsupported generated answers.

This contract defines what Gamal can safely assume when building the RAG layer.

---

# 3. Relationship to Other Documents

This document is part of a layered documentation system. It does not replace the architecture document, validation document, or future RAG implementation contracts.

| Document                                  | Relationship                                                                                                                                                                |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `docs/team_ownership_and_architecture.md` | Defines the full system architecture, folder ownership, team responsibilities, dependency order, and high-level RAG flow. This schema contract builds on that architecture. |
| `docs/validation_rules.md`                | Defines V1–V11 validation behavior in detail. This document explains what the schema means; the validation document explains how schema correctness is enforced.            |
| `docs/chunking_and_metadata_contract.md`  | Will define exact chunk types, chunk IDs, metadata fields, and ChromaDB-ready chunk structure. This document defines the source patient data that chunking reads from.      |
| `docs/citation_contract.md`               | Will define exact citation object structure and display behavior. This document defines the stable IDs and source fields citations depend on.                               |
| `docs/rag_pipeline.md`                    | Will explain the end-to-end RAG flow. This schema contract explains the dataset assumptions underneath that flow.                                                           |

## Documentation Layering Rule

This document must remain focused on the patient dataset contract.

It must not become:

* a full validation manual,
* a chunking implementation guide,
* a retrieval tuning guide,
* a citation formatting guide,
* or a ChromaDB operations runbook.

Those responsibilities belong to separate focused documents.

---

# 4. High-Level Dataset Structure

Each patient record is stored as one JSON object.

The high-level structure is:

```text
Patient
├── schema_version
├── patient_id
├── demographics
├── conditions
├── allergy_registry[]
├── visits[]
└── metadata
```

## Conceptual Meaning

| Section            | Purpose                                                                                                                                 |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| `schema_version`   | Identifies the patient JSON schema version used by generators, validators, and ingestion.                                               |
| `patient_id`       | Stable unique patient identifier used for file naming, retrieval filtering, citations, and patient-scoped queries.                      |
| `demographics`     | Contains basic non-sensitive synthetic identity fields needed for display and age derivation.                                           |
| `conditions`       | Defines the patient’s documented condition set. Used heavily in generation, validation, chunking, and retrieval filters.                |
| `allergy_registry` | Stores documented allergies for the patient. Used for allergy retrieval and medication safety validation.                               |
| `visits`           | The central clinical timeline. Each visit contains vitals, labs, medications, SOAP notes, linked documents, and prior visit references. |
| `metadata`         | Stores patient-level dataset metadata, especially `tier`. It must remain minimal and stable.                                            |

## RAG Interpretation

The RAG layer should treat the patient JSON as a structured evidence source.

The patient object is not a free-form document. It is a structured record from which different evidence chunks will be created.

The most important RAG unit is the visit.

```text
Patient JSON
    ↓
Visit-level evidence
    ↓
Semantic chunks
    ↓
ChromaDB metadata
    ↓
Patient-scoped retrieval
    ↓
Grounded cited answer
```

---

# 5. Patient Root Object Contract

Every patient JSON file must contain the following root-level fields:

```text
schema_version
patient_id
demographics
conditions
allergy_registry
visits
metadata
```

No extra root-level fields should be introduced without team approval.

## Root Field Contract

| Field              | Type             | Meaning                                                        | RAG Importance                                                            | Ingestion Importance                                            | Validation Importance                                        |
| ------------------ | ---------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------ |
| `schema_version`   | string           | Schema version for the patient record. Current value: `"1.0"`. | Allows future compatibility checks if schema changes.                     | Ingestion can reject unsupported schema versions.               | Ensures records follow the expected structure.               |
| `patient_id`       | string           | Stable patient identifier.                                     | Primary filter for patient-scoped retrieval.                              | Required in every chunk metadata object.                        | Must match locked ID format.                                 |
| `demographics`     | object           | Synthetic patient identity fields.                             | Used for display and query context, not for clinical inference.           | May be used in chunk text but should not become large metadata. | Required fields must exist; forbidden fields must not exist. |
| `conditions`       | array of strings | Documented patient conditions.                                 | Important for filtering, retrieval context, and query interpretation.     | Used to enrich chunk text and metadata.                         | Must use locked condition enums and CKD rule.                |
| `allergy_registry` | array of objects | Documented allergy history.                                    | Required for allergy retrieval and demo queries.                          | Usually becomes dedicated allergy evidence.                     | Used for medication-allergy conflict validation.             |
| `visits`           | array of objects | Chronological clinical record timeline.                        | Primary source for doctor-note, lab, prescription, and timeline evidence. | Main input to chunking and metadata extraction.                 | Must be chronological, unique, and structurally valid.       |
| `metadata`         | object           | Minimal patient-level metadata.                                | Supports tier awareness and dataset grouping.                             | May be used for filtering if needed.                            | Must contain valid tier value.                               |

---

# 6. ID Format Contracts

Stable IDs are critical for retrieval, filtering, citations, debugging, and timeline reconstruction.

## 6.1 `patient_id`

Expected format:

```text
PAT-(NRM|MOD|CHR)-NNN
```

Examples:

```text
PAT-NRM-001
PAT-MOD-007
PAT-CHR-003
```

Where:

| Segment | Meaning                                      |
| ------- | -------------------------------------------- |
| `PAT`   | Patient record prefix                        |
| `NRM`   | Normal patient tier                          |
| `MOD`   | Moderate patient tier                        |
| `CHR`   | Chronic patient tier                         |
| `NNN`   | Three-digit patient sequence within the tier |

## 6.2 `visit_id`

Expected format:

```text
VST-(NRM|MOD|CHR)-NNN-VVV
```

Examples:

```text
VST-NRM-001-001
VST-MOD-007-003
VST-CHR-003-009
```

Where:

| Segment       | Meaning               |
| ------------- | --------------------- |
| `VST`         | Visit record prefix   |
| `NRM/MOD/CHR` | Patient tier prefix   |
| `NNN`         | Patient sequence      |
| `VVV`         | Visit sequence number |

## 6.3 `document_id`

Expected format:

```text
DOC-(NRM|MOD|CHR)-NNN-DDD
```

Examples:

```text
DOC-MOD-007-001
DOC-CHR-003-002
```

Where:

| Segment       | Meaning                  |
| ------------- | ------------------------ |
| `DOC`         | Linked document prefix   |
| `NRM/MOD/CHR` | Patient tier prefix      |
| `NNN`         | Patient sequence         |
| `DDD`         | Document sequence number |

## 6.4 ID Stability Requirements

IDs must be:

* deterministic,
* unique within their scope,
* stable across generation runs,
* human-readable,
* suitable for citations,
* suitable for ChromaDB metadata,
* and suitable for debugging.

## 6.5 Why IDs Matter for RAG

Stable IDs allow the system to answer questions with traceable evidence.

Example:

```text
Answer:
The patient was prescribed Metformin during the follow-up visit.

Citation:
PAT-MOD-007 | VST-MOD-007-003 | prescription | 2024-04-12
```

If IDs change unpredictably, citations become unstable and retrieval debugging becomes difficult.

---

# 7. Demographics Contract

The `demographics` object contains basic synthetic demographic information.

Expected structure:

```text
demographics
├── name
├── date_of_birth
└── sex
```

## Allowed Fields

| Field           | Type   | Meaning                                                  |
| --------------- | ------ | -------------------------------------------------------- |
| `name`          | string | Synthetic patient name for display and demo readability. |
| `date_of_birth` | string | Patient date of birth in `YYYY-MM-DD` format.            |
| `sex`           | string | Allowed values: `male`, `female`.                        |

## Forbidden Field

```text
demographics.age
```

`age` must not be stored directly in the patient JSON.

## Why `demographics.age` Is Forbidden

Age changes over time. A static `age` field creates dual-state risk:

```text
date_of_birth says one thing
age says another thing
```

Instead, age should be derived dynamically from:

```text
date_of_birth + visit_date
```

This is safer for:

* validation,
* visit chronology,
* SOAP generation,
* timeline reconstruction,
* and future display logic.

## RAG Usage

Demographics may be used in chunk text for readability, but should not become a large metadata object.

Recommended usage:

```text
Patient PAT-MOD-007 is a synthetic male patient with documented T2DM.
```

Avoid storing full demographic objects in ChromaDB metadata unless explicitly required by a future contract.

---

# 8. Conditions Contract

The `conditions` array stores documented conditions assigned to the patient.

Allowed values:

```text
T2DM
HTN
Asthma
IDA
GERD
CKD
```

## Condition Meanings

| Condition | Meaning                             | Typical Tier      |
| --------- | ----------------------------------- | ----------------- |
| `T2DM`    | Type 2 Diabetes Mellitus            | moderate, chronic |
| `HTN`     | Hypertension                        | moderate, chronic |
| `Asthma`  | Asthma                              | moderate, chronic |
| `IDA`     | Iron-Deficiency Anemia              | moderate          |
| `GERD`    | Gastroesophageal Reflux Disease     | moderate          |
| `CKD`     | Chronic Kidney Disease complication | chronic only      |

## Tier Expectations

| Tier       | Expected Condition Pattern                                                    |
| ---------- | ----------------------------------------------------------------------------- |
| `normal`   | No chronic diseases. Acute/simple cases only.                                 |
| `moderate` | One to two managed conditions.                                                |
| `chronic`  | Multiple visits and long-term conditions, usually T2DM + HTN, optionally CKD. |

## CKD Dependency Rule

CKD is not standalone.

If a patient has:

```text
CKD
```

then the same patient must also have:

```text
T2DM
HTN
metadata.tier = chronic
```

Valid example:

```text
conditions = ["T2DM", "HTN", "CKD"]
metadata.tier = "chronic"
```

Invalid examples:

```text
conditions = ["CKD"]
metadata.tier = "chronic"
```

```text
conditions = ["T2DM", "CKD"]
metadata.tier = "chronic"
```

```text
conditions = ["T2DM", "HTN", "CKD"]
metadata.tier = "moderate"
```

## RAG Importance

Conditions are important because they support:

* patient filtering,
* condition-specific retrieval,
* lab trend queries,
* medication queries,
* chronic patient summaries,
* and showcase patient selection.

Conditions may be included in chunk metadata, but the exact metadata format belongs to `docs/chunking_and_metadata_contract.md`.

---

# 9. Visits Contract

The `visits` array is the most important section of the patient JSON.

Visits are the atomic timeline units of the clinical record.

Each visit contains:

```text
visit
├── visit_id
├── visit_date
├── visit_type
├── attending_physician
├── diagnoses
├── vitals
├── labs
├── medications
├── soap_note
├── linked_documents
└── prior_visit_id
```

## 9.1 Visit-Level Meaning

Each visit represents one documented clinical encounter.

A visit may contain:

* structured vitals,
* structured lab results,
* structured medication records,
* narrative SOAP text,
* linked OCR/scanned document references,
* and connection to a prior visit.

## 9.2 Visit Chronology

Visits must be ordered chronologically by `visit_date`.

Correct:

```text
Visit 1: 2023-01-10
Visit 2: 2023-03-15
Visit 3: 2023-06-20
```

Incorrect:

```text
Visit 1: 2023-06-20
Visit 2: 2023-03-15
```

Chronology matters because visits are used for:

* timeline reconstruction,
* longitudinal summaries,
* lab trend retrieval,
* medication progression,
* and grounded patient history answers.

## 9.3 `prior_visit_id`

`prior_visit_id` links a visit to the previous visit.

Expected behavior:

| Visit Position | `prior_visit_id`            |
| -------------- | --------------------------- |
| First visit    | `null`                      |
| Later visits   | Previous visit’s `visit_id` |

Example:

```text
VST-MOD-007-001 → prior_visit_id = null
VST-MOD-007-002 → prior_visit_id = VST-MOD-007-001
VST-MOD-007-003 → prior_visit_id = VST-MOD-007-002
```

This supports:

* timeline logic,
* visit sequence checks,
* longitudinal summaries,
* and debugging.

## 9.4 `visit_type`

Allowed values:

```text
initial
follow_up
emergency
hospitalization
```

`visit_type` helps the RAG layer understand the nature of the visit.

Examples:

| Query                                       | Useful Visit Type |
| ------------------------------------------- | ----------------- |
| “What happened during the emergency visit?” | `emergency`       |
| “Summarize the first visit.”                | `initial`         |
| “How did the condition progress?”           | `follow_up`       |
| “Was the patient hospitalized?”             | `hospitalization` |

## 9.5 Visits as Chunk Sources

Each visit may later produce multiple semantic evidence chunks, such as:

```text
doctor_note
lab_result
prescription
```

All visit-derived chunks must remain anchored to the visit.

The exact chunking rules belong to:

```text
docs/chunking_and_metadata_contract.md
```

But this schema contract establishes that visits are the primary source objects for chunking.

## 9.6 Visits as Citation Anchors

Every visit has:

```text
visit_id
visit_date
```

These are essential for citations.

A cited answer should be able to point back to the visit that supplied the evidence.

Example citation anchor:

```text
PAT-CHR-003 | VST-CHR-003-005 | 2024-08-14
```

## 9.7 Visits as Timeline Sources

Timeline generation must be derived from `visits`.

The system must not depend on a separate stored `timeline_events` field.

---

# 10. Vitals Contract

The `vitals` object stores visit-level vital signs.

Expected fields:

```text
vitals
├── bp_systolic
├── bp_diastolic
├── heart_rate
├── weight_kg
└── bmi
```

## Vitals Field Meaning

| Field          | Type           | Meaning                           |
| -------------- | -------------- | --------------------------------- |
| `bp_systolic`  | number/integer | Systolic blood pressure in mmHg.  |
| `bp_diastolic` | number/integer | Diastolic blood pressure in mmHg. |
| `heart_rate`   | number/integer | Heart rate in beats per minute.   |
| `weight_kg`    | number         | Weight in kilograms.              |
| `bmi`          | number         | Body Mass Index.                  |

## BP Vitals-Only Rule

Blood pressure is a vital sign.

It must exist only inside:

```text
visit.vitals.bp_systolic
visit.vitals.bp_diastolic
```

BP must never appear in:

```text
visit.labs[]
lab_type
patient.metadata
chunk metadata
timeline_events
any duplicate shadow field
```

## Why BP Must Not Be Metadata

BP values are numeric clinical values that change per visit. Storing them as ChromaDB metadata creates several risks:

* metadata explosion,
* inconsistent filtering,
* cross-visit confusion,
* duplicated truth,
* and retrieval drift.

BP should be present in structured vitals and may appear in SOAP text, especially in the objective section.

BP-related retrieval should rely on visit text or doctor-note chunks, not metadata filters.

---

# 11. Labs Contract

The `labs` array stores structured laboratory test results for a visit.

Expected lab object:

```text
lab
├── lab_type
├── value
├── unit
├── reference_range
└── flag
```

## Allowed Lab Types

```text
HbA1c
FBG
Creatinine
Hemoglobin
Ferritin
```

## Lab Field Meaning

| Field             | Type   | Meaning                                  |
| ----------------- | ------ | ---------------------------------------- |
| `lab_type`        | string | Locked lab type enum.                    |
| `value`           | number | Numeric lab result value.                |
| `unit`            | string | Measurement unit.                        |
| `reference_range` | string | Human-readable expected range.           |
| `flag`            | string | Allowed values: `NORMAL`, `HIGH`, `LOW`. |

## BP Is Not a Lab

The following are forbidden as lab types:

```text
BP
blood pressure
blood_pressure
systolic
diastolic
bp_systolic
bp_diastolic
SBP
DBP
```

BP must remain in `visit.vitals`.

## RAG Importance

Labs are critical for:

* lab trend retrieval,
* chronic patient summaries,
* diabetes progression questions,
* anemia progression questions,
* CKD-related creatinine tracking,
* and medication-response summaries.

A lab result can later become part of a `lab_result` chunk.

## Lab Trend Retrieval

Lab trend retrieval depends on:

```text
patient_id
visit_id
visit_date
lab_type
value
flag
conditions
```

The schema must keep lab values structured and visit-scoped so the RAG layer can retrieve and summarize trends safely.

Example query:

```text
How has this patient's HbA1c changed over time?
```

This query depends on consistent `HbA1c` lab records across multiple visits.

---

# 12. Medications Contract

The `medications` array stores structured medication records for a visit.

Expected medication object:

```text
medication
├── medication_name
├── medication_class
├── dose
├── frequency
├── route
├── start_date
└── stop_date
```

## Medication Field Meaning

| Field              | Type           | Meaning                                     |
| ------------------ | -------------- | ------------------------------------------- |
| `medication_name`  | string         | Must be from the medication whitelist.      |
| `medication_class` | string         | Human-readable medication class.            |
| `dose`             | string         | Dose text such as `500 mg`.                 |
| `frequency`        | string         | Locked frequency enum.                      |
| `route`            | string         | Locked route enum.                          |
| `start_date`       | string         | Date medication started.                    |
| `stop_date`        | string or null | Date medication stopped, or null if active. |

## Allowed Frequencies

```text
once_daily
twice_daily
as_needed
```

## Allowed Routes

```text
oral
inhaled
```

The route must satisfy:

```text
route ∈ {oral, inhaled}
```

The following route is forbidden:

```text
subcutaneous
```

## Medication Whitelist

Medication names must come from the project whitelist.

Allowed medications:

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

## RAG Importance

Medication records are important for:

* prescription retrieval,
* active medication summaries,
* chronic disease management questions,
* medication change questions,
* allergy contradiction checks,
* and citation-supported answers.

Example queries:

```text
What medications does this patient currently take?
```

```text
Has the diabetes medication changed over time?
```

Medication evidence should remain visit-scoped and citation-ready.

---

# 13. Allergy Registry Contract

The `allergy_registry` array stores documented allergies for the patient.

Expected allergy object:

```text
allergy
├── allergen
├── reaction
├── severity
├── recorded_date
└── source_visit_id
```

## Allergy Field Meaning

| Field             | Type   | Meaning                                       |
| ----------------- | ------ | --------------------------------------------- |
| `allergen`        | string | Documented allergen or substance.             |
| `reaction`        | string | Documented reaction.                          |
| `severity`        | string | Allowed values: `mild`, `moderate`, `severe`. |
| `recorded_date`   | string | Date allergy was recorded.                    |
| `source_visit_id` | string | Visit where the allergy was documented.       |

## Allergy Registry Purpose

The allergy registry supports:

* allergy retrieval,
* demo allergy queries,
* medication safety validation,
* structured highlight display,
* and source-cited allergy summaries.

## Demo Importance

Allergy retrieval is demo-critical because it shows that the system can retrieve documented safety-relevant information without claiming to detect or infer allergies.

Correct framing:

```text
The system retrieves documented allergy records.
```

Incorrect framing:

```text
The system detects allergies.
```

## RAG Importance

Allergy evidence should be easy to retrieve.

Example query:

```text
Does this patient have any recorded allergies?
```

This should retrieve documented allergy evidence from the patient record and return a grounded answer with citations.

---

# 14. SOAP Contract

The `soap_note` object stores narrative text for each visit.

Expected SOAP structure:

```text
soap_note
├── subjective
├── objective
├── assessment
└── plan
```

## SOAP Section Meaning

| Section      | Meaning                                                                                              |
| ------------ | ---------------------------------------------------------------------------------------------------- |
| `subjective` | Patient-reported symptoms, complaints, or history as documented in the visit.                        |
| `objective`  | Objective observations such as vitals and lab summaries.                                             |
| `assessment` | Documented assessment based only on provided structured facts.                                       |
| `plan`       | Documented plan based only on generated structured medications, labs, diagnoses, or follow-up facts. |

## Narrative-Only Rule

SOAP is narrative-only.

SOAP generation must not:

* create new medications,
* create new lab values,
* create new diagnoses,
* create new allergies,
* modify vitals,
* modify visit dates,
* modify structured fields,
* or introduce unsupported clinical conclusions.

SOAP text is allowed to describe the structured facts that already exist.

## RAG Importance

SOAP is important because it provides natural-language evidence for:

* doctor-note retrieval,
* patient summary questions,
* visit explanation queries,
* BP retrieval from text,
* emergency visit questions,
* and timeline-style summaries.

SOAP content will usually be the basis for `doctor_note` chunks.

## Grounding Importance

Because SOAP is narrative, it must remain grounded in structured data.

If SOAP text contradicts structured fields, the RAG answer may become unsafe or misleading.

SOAP auditing helps reduce this risk, but the schema contract requires that SOAP remain descriptive and evidence-preserving.

---

# 15. Metadata Contract

The patient JSON contains a `metadata` object.

Expected patient-level metadata:

```text
metadata
└── tier
```

Allowed values:

```text
normal
moderate
chronic
```

## Patient Metadata Meaning

| Field           | Type   | Meaning                                      |
| --------------- | ------ | -------------------------------------------- |
| `metadata.tier` | string | Dataset tier classification for the patient. |

## Metadata Scope Clarification

There are two different metadata concepts:

```text
1. Patient JSON metadata
2. ChromaDB chunk metadata
```

This document defines the patient JSON metadata.

The exact ChromaDB chunk metadata contract belongs to:

```text
docs/chunking_and_metadata_contract.md
```

## Required Metadata

At the patient JSON level:

```text
metadata.tier
```

is required.

## Optional Metadata

At this schema level, no additional patient-level metadata should be added unless approved.

## Forbidden or Dangerous Metadata

The following should not be added to patient metadata:

```text
bp_systolic
bp_diastolic
full_vitals
full_labs
full_medications
large_nested_objects
timeline_events
free_text_summaries
generated_ai_answers
```

## Why Metadata Must Stay Minimal

Metadata should remain stable and filter-friendly.

Large or unstable metadata causes:

* ChromaDB filtering problems,
* duplicated truth,
* large metadata payloads,
* inconsistent retrieval behavior,
* and future schema drift.

---

# 16. Forbidden Fields and Anti-Patterns

The following fields and patterns are forbidden.

## 16.1 `timeline_events`

Forbidden:

```text
timeline_events
```

Reason:

Timeline should be reconstructed from `visits`, not stored as a duplicate timeline object.

Risk if allowed:

* duplicated timeline truth,
* mismatch between visits and timeline events,
* stale generated summaries,
* corrupted timeline endpoint behavior.

## 16.2 `demographics.age`

Forbidden:

```text
demographics.age
```

Reason:

Age should be derived from `date_of_birth` and `visit_date`.

Risk if allowed:

* inconsistent age,
* outdated records,
* validation ambiguity,
* incorrect SOAP context.

## 16.3 `cross_visit_summary_objects`

Forbidden pattern:

```text
cross_visit_summary
longitudinal_summary
patient_ai_summary
```

Reason:

Summaries should be generated from retrieved evidence, not stored as authoritative source data.

Risk if allowed:

* model may retrieve a generated summary instead of primary evidence,
* citations become weaker,
* hallucinated or outdated summaries may be treated as truth.

## 16.4 `bp_inside_labs`

Forbidden:

```text
labs[].lab_type = "BP"
labs[].lab_type = "blood pressure"
```

Reason:

BP is a vital sign, not a lab.

Risk if allowed:

* invalid lab trend retrieval,
* metadata confusion,
* wrong source type retrieval,
* validation failure.

## 16.5 `bp_inside_metadata`

Forbidden:

```text
metadata.bp_systolic
metadata.bp_diastolic
chunk_metadata.bp_systolic
chunk_metadata.bp_diastolic
```

Reason:

BP varies per visit and should remain in vitals/text.

Risk if allowed:

* filtering confusion,
* metadata bloat,
* stale duplicate values,
* incorrect retrieval assumptions.

## 16.6 Large Nested Metadata

Forbidden pattern:

```text
metadata.full_visit
metadata.full_labs
metadata.full_medications
metadata.full_soap
```

Reason:

Metadata should support filtering, not duplicate content.

Risk if allowed:

* ChromaDB payload bloat,
* unclear evidence boundaries,
* duplicate source truth,
* slower debugging.

## 16.7 Hallucinated Fields

Forbidden pattern:

```text
risk_score
diagnosis_confidence
predicted_condition
recommended_treatment
ai_generated_diagnosis
```

Reason:

The project is not a diagnostic or prediction system.

Risk if allowed:

* medical safety violation,
* scope violation,
* DEPI evaluation risk,
* unsupported AI behavior.

---

# 17. RAG Dependencies

The RAG layer depends on this schema in several ways.

## 17.1 Chunking Dependency

Chunking depends on predictable patient and visit structure.

The chunker must be able to read:

```text
patient_id
conditions
metadata.tier
visits[].visit_id
visits[].visit_date
visits[].visit_type
visits[].labs
visits[].medications
visits[].soap_note
allergy_registry
```

If these fields are unstable, chunking becomes unreliable.

## 17.2 Metadata Extraction Dependency

Metadata extraction depends on stable fields such as:

```text
patient_id
visit_id
visit_date
visit_type
conditions
source_type
metadata.tier
```

Exact ChromaDB metadata rules belong in the future chunking and metadata contract, but the source fields come from this schema.

## 17.3 Citation Dependency

Citation generation depends on stable identifiers:

```text
patient_id
visit_id
visit_date
document_id
source_type
```

If IDs are missing or inconsistent, citations become unreliable.

## 17.4 Retrieval Dependency

Retrieval depends on both:

```text
semantic text
+
stable metadata filters
```

The schema provides semantic text through SOAP and structured fields through visits, labs, medications, and allergies.

## 17.5 Grounding Dependency

Grounded answers depend on retrieved evidence.

If the schema contains hallucinated summaries, duplicate fields, or inconsistent source data, the answer generator may ground itself on poor evidence.

## 17.6 Timeline Generation Dependency

Timeline generation depends on:

```text
visits[].visit_date
visits[].visit_type
visits[].diagnoses
visits[].medications
visits[].labs
visits[].soap_note
prior_visit_id
```

The timeline must be reconstructed from visits, not stored as a separate `timeline_events` object.

## 17.7 Allergy Retrieval Dependency

Allergy retrieval depends on:

```text
allergy_registry[].allergen
allergy_registry[].reaction
allergy_registry[].severity
allergy_registry[].recorded_date
allergy_registry[].source_visit_id
```

## 17.8 Lab Trend Retrieval Dependency

Lab trend retrieval depends on:

```text
visits[].visit_date
visits[].labs[].lab_type
visits[].labs[].value
visits[].labs[].unit
visits[].labs[].flag
```

## 17.9 Backend Integration Dependency

Backend endpoints depend on RAG outputs that can trace back to this schema.

For example:

```text
/query
```

depends on retrieved chunks and citations.

```text
/timeline/{patient_id}
```

depends on visits.

```text
/summary/{patient_id}
```

depends on retrieved evidence and patient-level context.

---

# 18. Validation Dependencies

Validation protects this schema from corrupting downstream RAG behavior.

The V1–V11 validation rules protect:

| Rule Area                   | Schema Protection                                | RAG Protection                                    |
| --------------------------- | ------------------------------------------------ | ------------------------------------------------- |
| Chronology                  | Ensures visits are ordered.                      | Protects timeline and trend queries.              |
| Allergy conflicts           | Ensures medications do not contradict allergies. | Protects safety-related answers.                  |
| Impossible vitals           | Prevents unrealistic structured facts.           | Protects SOAP and summary credibility.            |
| Required fields             | Ensures schema completeness.                     | Protects chunking and metadata extraction.        |
| Prior visit references      | Ensures visit links are valid.                   | Protects timeline reasoning.                      |
| Duplicate visit IDs         | Ensures unique citation anchors.                 | Protects citation accuracy.                       |
| Enum validation             | Ensures stable values.                           | Protects filters and retrieval logic.             |
| Date format validation      | Ensures temporal fields are parseable.           | Protects date filtering and timeline generation.  |
| BP forbidden in labs        | Protects lab/vitals separation.                  | Protects lab retrieval and BP retrieval behavior. |
| `timeline_events` forbidden | Prevents duplicate timeline truth.               | Protects timeline reconstruction.                 |
| Medication whitelist        | Ensures prescriptions are controlled.            | Protects medication retrieval consistency.        |

Validation must run before ingestion.

---

# 19. Ingestion Dependencies

The ingestion pipeline assumes the dataset has already passed validation.

## Ingestion Must Read Only From

```text
data/patients/
```

This folder contains approved patient records only.

## Ingestion Must Not Read From

```text
data/quarantine/
```

Quarantined records are invalid or rejected and must not enter ChromaDB.

## Ingestion Assumptions

The ingestion pipeline may assume:

```text
- patient_id is valid and unique
- visits are chronological
- visit_id values are unique
- required fields exist
- conditions use locked enums
- lab_type values use locked enums
- medications use the whitelist
- BP is not in labs
- metadata.tier is valid
- timeline_events is absent
```

## Stable Schema Assumption

Ingestion code should not contain fragile fallback logic for multiple schema shapes.

If the schema changes, the contract must change first, validation must change second, and ingestion must be updated third.

## Metadata Consistency

Metadata should be derived from stable schema fields. The RAG engineer should not invent metadata fields that are not supported by this contract or the future chunking metadata contract.

---

# 20. Schema Stability Policy

This schema is treated as frozen for the current project phase.

## Frozen Fields

The following are frozen:

```text
schema_version
patient_id
demographics
conditions
allergy_registry
visits
metadata
```

The visit structure is also frozen:

```text
visit_id
visit_date
visit_type
attending_physician
diagnoses
vitals
labs
medications
soap_note
linked_documents
prior_visit_id
```

The following are also frozen:

```text
ID formats
date format
condition enum
lab_type enum
visit_type enum
frequency enum
route enum
flag enum
severity enum
medication whitelist
BP vitals-only rule
CKD dependency rule
timeline_events forbidden rule
demographics.age forbidden rule
```

## Changes Requiring Team Approval

Any change to the following requires approval from Ahmed and Gamal:

```text
root patient fields
visit structure
ID formats
date formats
conditions enum
metadata fields
source evidence fields
allergy structure
lab structure
medication structure
SOAP structure
```

## Why Schema Drift Is Dangerous

Schema drift can cause:

* missed chunks,
* inconsistent metadata,
* invalid ChromaDB filters,
* broken citations,
* duplicated evidence,
* timeline errors,
* retrieval failure,
* and unsupported generated answers.

A RAG system is only as stable as the evidence structure beneath it.

---

# 21. Example Patient Structure

This is a simplified structural example. It is not the full JSON schema.

```text
Patient
├── schema_version: "1.0"
├── patient_id: "PAT-MOD-007"
├── demographics
│   ├── name: "Synthetic Patient Name"
│   ├── date_of_birth: "1982-04-15"
│   └── sex: "male"
├── conditions
│   ├── "T2DM"
│   └── "HTN"
├── allergy_registry
│   └── allergy
│       ├── allergen: "Example allergen"
│       ├── reaction: "Example reaction"
│       ├── severity: "moderate"
│       ├── recorded_date: "2023-03-12"
│       └── source_visit_id: "VST-MOD-007-002"
├── visits
│   ├── visit
│   │   ├── visit_id: "VST-MOD-007-001"
│   │   ├── visit_date: "2023-01-10"
│   │   ├── visit_type: "initial"
│   │   ├── attending_physician: "Dr. Example"
│   │   ├── diagnoses
│   │   │   └── "T2DM"
│   │   ├── vitals
│   │   │   ├── bp_systolic: 132
│   │   │   ├── bp_diastolic: 84
│   │   │   ├── heart_rate: 78
│   │   │   ├── weight_kg: 84.5
│   │   │   └── bmi: 28.1
│   │   ├── labs
│   │   │   └── lab
│   │   │       ├── lab_type: "HbA1c"
│   │   │       ├── value: 7.8
│   │   │       ├── unit: "%"
│   │   │       ├── reference_range: "4.0-5.6 %"
│   │   │       └── flag: "HIGH"
│   │   ├── medications
│   │   │   └── medication
│   │   │       ├── medication_name: "Metformin"
│   │   │       ├── medication_class: "Biguanide"
│   │   │       ├── dose: "500 mg"
│   │   │       ├── frequency: "twice_daily"
│   │   │       ├── route: "oral"
│   │   │       ├── start_date: "2023-01-10"
│   │   │       └── stop_date: null
│   │   ├── soap_note
│   │   │   ├── subjective: "Narrative text..."
│   │   │   ├── objective: "Narrative text..."
│   │   │   ├── assessment: "Narrative text..."
│   │   │   └── plan: "Narrative text..."
│   │   ├── linked_documents
│   │   │   └── "DOC-MOD-007-001"
│   │   └── prior_visit_id: null
└── metadata
    └── tier: "moderate"
```

---

# 22. Engineering Risks if This Contract Is Ignored

Ignoring this contract can create downstream failures that are hard to debug.

## Broken Retrieval

If fields are renamed or moved, the chunker may skip evidence.

Example:

```text
soap_note renamed to doctor_notes
```

Result:

```text
doctor_note chunks are empty or missing
```

## Incorrect Citations

If `visit_id` or `patient_id` is missing, citations cannot point to stable evidence.

Result:

```text
answers appear unsupported even when retrieval worked
```

## Metadata Inconsistency

If metadata fields are invented inconsistently, ChromaDB filters become unreliable.

Example:

```text
source_type = "labs"
source_type = "lab"
source_type = "lab_result"
```

Result:

```text
lab trend queries fail unpredictably
```

## Timeline Corruption

If visits are not chronological or if timeline data is duplicated in `timeline_events`, timeline views may conflict with source visits.

Result:

```text
frontend timeline shows a different story than retrieved evidence
```

## Ingestion Failure

If patient files contain unexpected structures, ingestion code may crash or silently drop records.

Result:

```text
ChromaDB contains incomplete patient evidence
```

## Chunk Instability

If visits contain cross-visit summary objects or unstable generated text, chunks may no longer map cleanly to one evidence source.

Result:

```text
citations become vague and retrieval loses precision
```

## Hallucinated Responses

If generated summaries or unsupported medical fields are treated as evidence, the LLM may answer from non-authoritative content.

Result:

```text
the system violates the no unsupported medical conclusion rule
```

---

# 23. Final Contract Summary

This schema contract defines the stable evidence layer of the project.

Ahmed owns the trusted structured evidence:

```text
patient schema
patient JSON records
conditions
visits
vitals
labs
medications
allergy registry
SOAP notes
validation reports
```

Gamal builds trusted retrieval on top of that evidence:

```text
chunking
metadata extraction
ChromaDB ingestion
retrieval
grounding
citations
RAG answers
```

The engineering relationship is simple:

```text
Stable schema = stable ingestion
Stable ingestion = stable retrieval
Stable retrieval = grounded answers
Grounded answers = safe citation-based RAG
```

The RAG layer must not guess the schema, invent metadata, ingest quarantined records, duplicate BP values, or treat generated summaries as source truth.

This contract is the boundary between data engineering and retrieval engineering.

---

# 24. Self-Review

## Completeness

| Area                    | Evaluation |
| ----------------------- | ---------- |
| Root patient object     | Complete   |
| IDs                     | Complete   |
| Demographics            | Complete   |
| Conditions              | Complete   |
| Visits                  | Complete   |
| Vitals                  | Complete   |
| Labs                    | Complete   |
| Medications             | Complete   |
| Allergy registry        | Complete   |
| SOAP                    | Complete   |
| Metadata                | Complete   |
| Forbidden fields        | Complete   |
| RAG dependencies        | Complete   |
| Validation dependencies | Complete   |
| Ingestion dependencies  | Complete   |
| Stability policy        | Complete   |

## RAG-Awareness

This document is strongly RAG-aware. It explains how schema stability affects:

* chunking,
* metadata extraction,
* citation anchors,
* retrieval filters,
* grounding,
* timeline reconstruction,
* allergy retrieval,
* lab trend retrieval,
* and backend integration.

## Schema Clarity

The document clearly defines every major schema section and explains which fields are required, which are forbidden, and why each section matters.

## Ingestion Readiness

The document provides enough schema-level context for the ingestion engineer to understand what input structure is safe to consume. Exact chunk and ChromaDB metadata rules should still be defined separately in `docs/chunking_and_metadata_contract.md`.

## Handoff Readiness

This document is ready to be used as the official schema handoff contract between Ahmed and Gamal.

## Documentation Professionalism

The document is professional, structured, implementation-oriented, and suitable for both GitHub review and DEPI academic evaluation.

## Final Classification

```text
Strong Engineering Contract
```

This document is stronger than an internal reference and suitable for official project handoff. It is not classified as a full production-grade schema contract only because detailed chunking, metadata, citation, and validation rules intentionally belong to separate contract documents.
