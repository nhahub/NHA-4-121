# Patient Schema Explained

**Document Path:** `docs/patient_schema_explained.md`  
**Project:** AI Based Clinical Record Summarization System  
**Audience:** Member 2 — Gamal, AI/RAG Engineer  
**Owner:** Member 1 — Ahmed, Data Engineering Lead  
**Status:** Final schema handoff reference  
**Related Schema:** `data/schemas/patient_schema.json`

---

## Purpose of This Document

This document is the formal technical handoff from the Data Engineering layer to the AI/RAG layer. It explains how the patient JSON schema works, why each structure exists, how the Retrieval-Augmented Generation pipeline depends on it, and what must remain stable for chunking, metadata extraction, ChromaDB ingestion, retrieval filtering, grounded answer generation, citations, allergy retrieval, lab trend retrieval, OCR linkage, and timeline generation.

This is not only a field-by-field explanation. It is an architecture contract. Member 2 should treat this document as the practical guide for building ingestion, chunking, metadata construction, retrieval, grounding, and citation logic on top of the validated synthetic patient records.

---

# 1. System Overview

## 1.1 What the Project Does

The **AI Based Clinical Record Summarization System** is an academic Retrieval-Augmented Generation system that works with synthetic medical records only. The system stores structured patient records as JSON files, converts those records into retrieval-friendly chunks, indexes the chunks in ChromaDB, retrieves relevant evidence for a user question, and generates a grounded answer with citations.

The system can:

| Capability | Meaning |
|---|---|
| Retrieve patient records | Search within a selected patient’s synthetic record |
| Summarize documented history | Summarize facts already stored in records |
| Show patient timelines | Build chronological views from `visits[]` |
| Retrieve allergy history | Surface documented allergies from `allergy_registry` |
| Retrieve lab trends | Compare lab values across visit dates |
| Use OCR-linked documents | Connect scanned/cached text to visit-level documents |
| Generate grounded answers | Answer using retrieved chunks only |
| Display citations | Show which visit/document/chunk supports the answer |

The system must not:

| Forbidden Capability | Reason |
|---|---|
| Diagnose disease | Out of project scope and unsafe |
| Recommend treatment | The system is not a clinical decision system |
| Predict future disease | No predictive modeling is allowed |
| Infer undocumented facts | RAG must stay grounded in retrieved records |
| Use real patient data | Dataset is synthetic only |
| Replace doctors | Academic retrieval and summarization only |

## 1.2 Why Synthetic Patient Records Exist

Synthetic patient records are the stable knowledge base for this academic system. They make the project safe, explainable, and reproducible. They allow the team to demonstrate realistic RAG workflows without using private or real clinical data.

Synthetic records also give the team control over:

| Controlled Area | Why It Matters |
|---|---|
| Patient tier | Enables normal, moderate, and chronic examples |
| Visit chronology | Enables timeline and temporal retrieval |
| Lab progression | Enables trend queries such as HbA1c history |
| Medication history | Enables prescription retrieval and citations |
| Allergy registry | Enables dedicated allergy retrieval |
| SOAP notes | Enables doctor-note chunks for semantic search |
| Linked documents | Enables OCR and citation workflows |

## 1.3 Why Schema Stability Matters

The schema is the foundation of the entire system. Every downstream layer assumes that the same fields exist in the same locations with the same meanings.

```text
Patient JSON Schema
        ↓
Validation Rules
        ↓
Approved Patient Records
        ↓
Chunking and Metadata Extraction
        ↓
ChromaDB Ingestion
        ↓
Patient-Scoped Retrieval
        ↓
Grounded Answer Generation
        ↓
Citation Display
        ↓
Streamlit Demo
```

If the schema changes without coordination, the RAG layer may retrieve the wrong chunks, miss important evidence, generate broken citations, or fail to filter by patient, visit date, source type, condition, or visit type.

## 1.4 How the RAG Pipeline Depends on the Schema

| RAG Function | Schema Dependency |
|---|---|
| Patient-scoped retrieval | `patient_id` |
| Temporal filtering | `visits[].visit_date` |
| Visit-specific citation | `visits[].visit_id` |
| OCR citation | `visits[].linked_documents[]` |
| Condition filtering | `conditions` and `visits[].diagnoses` |
| Lab trend retrieval | `visits[].labs[]` |
| Medication retrieval | `visits[].medications[]` |
| Allergy retrieval | `allergy_registry[]` |
| Doctor-note retrieval | `visits[].soap_note` |
| Timeline generation | `visits[]` and `prior_visit_id` |
| Tier filtering | `metadata.tier` |

---

# 2. Full Patient Structure Overview

## 2.1 Root-Level Patient Object

Every patient JSON file follows this root structure:

```json
{
  "schema_version": "1.0",
  "patient_id": "PAT-MOD-001",
  "demographics": {},
  "conditions": [],
  "allergy_registry": [],
  "visits": [],
  "metadata": {}
}
```

## 2.2 Hierarchy Diagram

```text
Patient
├── schema_version
├── patient_id
├── demographics
│   ├── name
│   ├── date_of_birth
│   └── sex
├── conditions[]
├── allergy_registry[]
│   ├── allergen
│   ├── reaction
│   ├── severity
│   ├── recorded_date
│   └── source_visit_id
├── visits[]
│   ├── visit_id
│   ├── visit_date
│   ├── visit_type
│   ├── attending_physician
│   ├── diagnoses[]
│   ├── vitals
│   │   ├── bp_systolic
│   │   ├── bp_diastolic
│   │   ├── heart_rate
│   │   ├── weight_kg
│   │   └── bmi
│   ├── labs[]
│   │   ├── lab_type
│   │   ├── value
│   │   ├── unit
│   │   ├── reference_range
│   │   └── flag
│   ├── medications[]
│   │   ├── medication_name
│   │   ├── medication_class
│   │   ├── dose
│   │   ├── frequency
│   │   ├── route
│   │   ├── start_date
│   │   └── stop_date
│   ├── soap_note
│   │   ├── subjective
│   │   ├── objective
│   │   ├── assessment
│   │   └── plan
│   ├── linked_documents[]
│   └── prior_visit_id
└── metadata
    └── tier
```

## 2.3 Architecture Diagram

```text
                      ┌────────────────────────────┐
                      │ data/patients/PAT-*.json   │
                      └──────────────┬─────────────┘
                                     │
                                     ▼
                      ┌────────────────────────────┐
                      │ validators/rules.py        │
                      │ V1–V11 validation          │
                      └──────────────┬─────────────┘
                                     │ zero FAIL
                                     ▼
                      ┌────────────────────────────┐
                      │ ingestion/chunker.py       │
                      │ visit-level chunking       │
                      └──────────────┬─────────────┘
                                     │ chunks + metadata
                                     ▼
                      ┌────────────────────────────┐
                      │ ChromaDB                   │
                      │ vector index + filters     │
                      └──────────────┬─────────────┘
                                     │ retrieval
                                     ▼
                      ┌────────────────────────────┐
                      │ RAG answer generation      │
                      │ grounding + citations      │
                      └────────────────────────────┘
```

## 2.4 Root-Level Object Breakdown

| Field | Type | Required | Main Consumer | Purpose |
|---|---:|---:|---|---|
| `schema_version` | string | Yes | Validators | Ensures all files use the locked schema version |
| `patient_id` | string | Yes | Retrieval, metadata, citations | Stable patient identity and filter key |
| `demographics` | object | Yes | SOAP, display, age calculation | Basic synthetic patient profile |
| `conditions` | array | Yes | Metadata, retrieval filters | Patient-level canonical conditions |
| `allergy_registry` | array | Yes | Allergy chunks, V2 validation | Documented allergy history |
| `visits` | array | Yes | Chunking, timeline, citations | Chronological clinical record history |
| `metadata` | object | Yes | Filtering, tier logic | Patient tier and ingestion-safe metadata |

---

# 3. Core Database Philosophy

## 3.1 Local JSON as the Source Database

For this academic project, local JSON files are the primary database. This is intentional. JSON keeps the data readable, editable, portable, and easy to validate.

```text
Local JSON Files
├── Easy to inspect
├── Easy to version with Git
├── Easy to validate with Python
├── Easy to transform into chunks
└── Easy to explain during evaluation
```

The JSON dataset is not a temporary mock. It is the authoritative structured data source for ingestion.

## 3.2 Why Strict Validation Exists

Strict validation protects the entire RAG pipeline. The RAG layer cannot safely retrieve and cite records if the records are inconsistent.

| Validation Protects | Example |
|---|---|
| Retrieval accuracy | Ensures source fields exist and are stable |
| Citation correctness | Ensures `visit_id` and `linked_documents` are valid |
| Timeline correctness | Ensures visit dates and prior references are usable |
| Metadata safety | Ensures filter fields are stable and not overloaded |
| Medical safety framing | Prevents unsupported or contradictory synthetic records |
| Demo reliability | Blocks invalid records before ingestion |

## 3.3 Why `additionalProperties: false` Matters

The schema rejects random or unsupported fields. This is critical because extra fields create ambiguity for generators, validators, and chunkers.

Bad example:

```json
{
  "metadata": {
    "tier": "moderate",
    "bp_systolic": 145
  }
}
```

This is invalid because BP must not appear in metadata.

Why this matters:

| Risk | Result |
|---|---|
| Extra fields in metadata | ChromaDB filters become unsafe |
| Extra BP fields | Conflicts with BP vitals-only rule |
| Extra timeline fields | Breaks timeline generation contract |
| Extra diagnosis fields | May create unsupported RAG claims |

## 3.4 Why Deterministic Structures Matter

The data layer uses deterministic structures because the RAG layer must know exactly where to find facts.

```text
Same field name
+ Same nested location
+ Same enum values
+ Same ID format
= Reliable chunking and retrieval
```

If one patient stores medications under `medications` and another stores them under `prescriptions`, the RAG engineer must write fragile special-case logic. The locked schema prevents this.

## 3.5 Why Locked Enums Matter

Locked enums make metadata filters reliable. For example, if `visit_type` is always one of:

```text
initial | follow_up | emergency | hospitalization
```

then the RAG layer can safely filter or prioritize emergency visits without handling spelling variants such as `ER`, `urgent`, `Emergency Visit`, or `emerg`.

## 3.6 Why Stable IDs Matter

Stable IDs are the backbone of traceability.

| ID | Used For |
|---|---|
| `patient_id` | Patient filtering and record ownership |
| `visit_id` | Visit-level citation and timeline anchors |
| `document_id` | OCR linkage and document citation |
| `chunk_id` | ChromaDB storage and retrieval references |

---

# 4. Patient ID and Visit ID System

## 4.1 Patient ID Format

Format:

```text
PAT-(NRM|MOD|CHR)-NNN
```

Examples:

```text
PAT-NRM-001
PAT-MOD-001
PAT-CHR-001
```

Meaning:

| Segment | Meaning |
|---|---|
| `PAT` | Patient record prefix |
| `NRM`, `MOD`, `CHR` | Tier code |
| `NNN` | Three-digit patient number |

## 4.2 Visit ID Format

Format:

```text
VST-(NRM|MOD|CHR)-NNN-VVV
```

Examples:

```text
VST-MOD-001-001
VST-MOD-001-002
VST-CHR-001-006
```

Meaning:

| Segment | Meaning |
|---|---|
| `VST` | Visit prefix |
| `MOD` | Tier code inherited from patient |
| `001` | Patient number |
| `002` | Visit sequence number |

## 4.3 Document ID Format

Format:

```text
DOC-(NRM|MOD|CHR)-NNN-VVV
```

Example:

```text
DOC-CHR-001-004
```

Document IDs link structured visits to OCR text files or scanned documents.

## 4.4 Why IDs Matter

| System Area | Dependency on IDs |
|---|---|
| Citations | Cite answer evidence by patient, visit, and document |
| Retrieval | Filter chunks by `patient_id` |
| Chunk references | Build stable `chunk_id` from visit/source type |
| Timeline generation | Sort and display events by visit ID/date |
| ChromaDB filtering | Store `patient_id`, `visit_id`, and `source_type` metadata |
| OCR linkage | Connect `linked_documents[]` to cached OCR output |

## 4.5 Recommended Chunk ID Pattern for Gamal

The schema does not store `chunk_id`, but the ingestion layer should create it deterministically.

Recommended patterns:

```text
{visit_id}-doctor_note-01
{visit_id}-lab_result-01
{visit_id}-prescription-01
{patient_id}-allergy-01
```

Example:

```text
VST-MOD-001-003-lab_result-01
PAT-MOD-001-allergy-01
```

---

# 5. Demographics Section

## 5.1 Structure

```json
"demographics": {
  "name": "Karim Hassan",
  "date_of_birth": "1982-11-19",
  "sex": "male"
}
```

## 5.2 Field Responsibilities

| Field | Purpose | Downstream Use |
|---|---|---|
| `name` | Human-readable synthetic patient name | UI display and demo queries |
| `date_of_birth` | Stable age source | Age calculation at visit time |
| `sex` | Basic demographic field | SOAP prompt context and display |

## 5.3 Why `demographics.age` Is Forbidden

Age changes over time. Storing age directly creates duplicate state and can become inconsistent with `date_of_birth` and `visit_date`.

Forbidden:

```json
"demographics": {
  "name": "Karim Hassan",
  "date_of_birth": "1982-11-19",
  "age": 42
}
```

Correct approach:

```python
age_at_visit = visit_date.year - date_of_birth.year
```

## 5.4 RAG Impact

The RAG layer should not use age as metadata. If a generated answer needs age context, it should derive age dynamically from `date_of_birth` and the relevant `visit_date`, or rely on SOAP text that was generated from structured facts.

---

# 6. Conditions System

## 6.1 Supported Conditions

| Condition | Meaning | Typical Tier |
|---|---|---|
| `T2DM` | Type 2 Diabetes Mellitus | Moderate or chronic |
| `HTN` | Hypertension | Moderate or chronic |
| `Asthma` | Asthma | Moderate or chronic |
| `IDA` | Iron-Deficiency Anemia | Moderate |
| `GERD` | Gastroesophageal Reflux Disease | Moderate |
| `CKD` | Chronic Kidney Disease complication | Chronic only with T2DM + HTN |

## 6.2 Why Condition Enums Are Locked

Conditions are used by:

| Layer | Use |
|---|---|
| Generators | Decide labs, medications, and visit progression |
| Validators | Enforce legal condition values |
| Chunking | Add condition terms into chunk text |
| Metadata extraction | Store condition filters in ChromaDB metadata |
| Retrieval | Filter or rerank by condition |
| Grounding | Explain only documented conditions |

Changing `T2DM` to `Diabetes` or `Type 2 Diabetes` would break filters and create inconsistent retrieval behavior.

## 6.3 CKD Co-Occurrence Rule

CKD is not a standalone condition in this project.

Valid:

```json
"conditions": ["T2DM", "HTN", "CKD"],
"metadata": {
  "tier": "chronic"
}
```

Invalid:

```json
"conditions": ["CKD"],
"metadata": {
  "tier": "moderate"
}
```

CKD requires:

```text
CKD → requires T2DM + HTN + chronic tier
```

## 6.4 Validation Dependencies

| Rule | Protection |
|---|---|
| V7 | Ensures all conditions are valid enums |
| V7-CKD | Ensures CKD co-occurs with T2DM + HTN + chronic tier |
| V8 | Ensures dates supporting progression are valid |
| V3 | Ensures age and vitals are realistic |

## 6.5 Retrieval Impact

CKD can remain in chunk metadata as a condition filter only because V7 guarantees that CKD patients also carry `T2DM`, `HTN`, and `chronic` tier. Without this rule, CKD retrieval could return inconsistent patients.

---

# 7. Visits Architecture

## 7.1 Why Visits Are the Atomic Unit

A visit is the most important object in the patient schema. It represents one dated clinical event. Every retrieval chunk except the patient-level allergy chunk should be scoped to exactly one visit.

```text
One visit
├── one visit date
├── one visit type
├── one set of vitals
├── one set of labs
├── one medication state
├── one SOAP note
├── one linked document set
└── one citation anchor
```

## 7.2 Visit Structure

```json
{
  "visit_id": "VST-MOD-001-002",
  "visit_date": "2023-12-09",
  "visit_type": "follow_up",
  "attending_physician": "Dr. Salma Nabil",
  "diagnoses": ["T2DM"],
  "vitals": {},
  "labs": [],
  "medications": [],
  "soap_note": {},
  "linked_documents": ["DOC-MOD-001-002"],
  "prior_visit_id": "VST-MOD-001-001"
}
```

## 7.3 How Visits Affect Chunking

Recommended chunks per visit:

| Chunk Type | Source Type | Input Fields |
|---|---|---|
| Doctor note | `doctor_note` | `soap_note`, `vitals`, `diagnoses`, `visit_date` |
| Lab result | `lab_result` | `labs[]`, `visit_date`, `diagnoses` |
| Prescription | `prescription` | `medications[]`, `visit_date`, `diagnoses` |
| OCR-linked note | optional source | `linked_documents[]` and OCR cache |

The allergy chunk is usually patient-level, not visit-level, because it summarizes `allergy_registry[]` once per patient.

## 7.4 How Visits Affect Retrieval

| Query Type | Visit Dependency |
|---|---|
| “What happened at the last visit?” | Sort by `visit_date`, retrieve latest doctor note |
| “How did HbA1c change?” | Retrieve lab chunks across visits |
| “What medications changed?” | Compare prescription chunks by visit date |
| “Was there a hospitalization?” | Filter or search `visit_type=hospitalization` |
| “What document supports this?” | Use `linked_documents[]` |

## 7.5 How Visits Affect Citations

Every retrieved chunk should carry the visit ID and visit date in metadata or citation payload.

Recommended citation payload:

```json
{
  "patient_id": "PAT-MOD-001",
  "visit_id": "VST-MOD-001-003",
  "visit_date": "2024-03-08",
  "source_type": "lab_result",
  "document_ids": ["DOC-MOD-001-003"]
}
```

## 7.6 How Visits Affect Timelines

Timelines must be generated from `visits[]`. The schema forbids a stored `timeline_events` field.

Correct timeline source:

```text
visits[].visit_date
visits[].visit_type
visits[].diagnoses
visits[].labs
visits[].medications
visits[].prior_visit_id
```

Forbidden timeline source:

```json
"timeline_events": []
```

---

# 8. Vitals and BP Rules

## 8.1 Vitals Structure

```json
"vitals": {
  "bp_systolic": 120,
  "bp_diastolic": 80,
  "heart_rate": 76,
  "weight_kg": 74.5,
  "bmi": 24.1
}
```

## 8.2 BP Architecture

Blood pressure is a vital sign. It must live only in the visit vitals object.

```text
Correct:
visits[].vitals.bp_systolic
visits[].vitals.bp_diastolic

Incorrect:
visits[].labs[].lab_type = "BP"
metadata.bp_systolic
chunk metadata bp_systolic
```

## 8.3 Why BP Is Forbidden in Labs

BP is not a blood test. Storing it as a lab would break lab trend retrieval, corrupt lab-type filters, and confuse the AI/RAG layer.

Bad example:

```json
"labs": [
  {
    "lab_type": "BP",
    "value": "145/92",
    "unit": "mmHg",
    "reference_range": "",
    "flag": "HIGH"
  }
]
```

Correct example:

```json
"vitals": {
  "bp_systolic": 145,
  "bp_diastolic": 92,
  "heart_rate": 84,
  "weight_kg": 88.0,
  "bmi": 29.1
}
```

## 8.4 Why BP Is Forbidden in Metadata

ChromaDB metadata should remain safe, stable, and filter-oriented. BP is a numeric clinical value that belongs in text evidence, not metadata filters.

Allowed metadata:

```json
{
  "patient_id": "PAT-CHR-001",
  "visit_id": "VST-CHR-001-004",
  "visit_date": "2022-10-12",
  "source_type": "doctor_note",
  "conditions": ["T2DM", "HTN", "CKD"],
  "visit_type": "hospitalization"
}
```

Forbidden metadata:

```json
{
  "bp_systolic": 158,
  "bp_diastolic": 96
}
```

## 8.5 How BP Retrieval Works

BP queries should retrieve doctor-note chunks, not lab chunks.

Example user query:

```text
What was the patient's blood pressure at the last visit?
```

Expected retrieval strategy:

```text
1. Filter by patient_id
2. Retrieve doctor_note chunks
3. Prefer latest visit_date
4. Read BP from SOAP objective text or structured visit vitals included in doctor-note chunk text
5. Cite visit_id and visit_date
```

---

# 9. Lab System

## 9.1 Supported Lab Types

| Lab Type | Unit | Retrieval Use |
|---|---|---|
| `HbA1c` | `%` | Diabetes trend retrieval |
| `FBG` | `mg/dL` | Diabetes monitoring retrieval |
| `Creatinine` | `mg/dL` | CKD/T2DM/HTN kidney marker retrieval |
| `Hemoglobin` | `g/dL` | IDA trend retrieval |
| `Ferritin` | `ng/mL` | Iron store trend retrieval |

BP is not a lab type.

## 9.2 Lab Object Structure

```json
{
  "lab_type": "HbA1c",
  "value": 7.2,
  "unit": "%",
  "reference_range": "4.0-5.6 %",
  "flag": "HIGH"
}
```

## 9.3 Lab Flags

| Flag | Meaning |
|---|---|
| `NORMAL` | Value is within expected reference range |
| `HIGH` | Value is above expected reference range |
| `LOW` | Value is below expected reference range |

## 9.4 Why Strict Lab Validation Exists

Lab data drives trend queries. If lab types or units drift, retrieval becomes unreliable.

| Problem | Result |
|---|---|
| `HbA1C` instead of `HbA1c` | Query may miss the lab chunk |
| `blood glucose` instead of `FBG` | Filter/rerank logic becomes inconsistent |
| Missing visit date | Trend order breaks |
| BP stored as lab | Lab search polluted with vital signs |

## 9.5 How Lab Trend Retrieval Works

Example query:

```text
How has Karim Hassan's HbA1c changed over time?
```

Recommended retrieval behavior:

```text
1. Filter by patient_id = PAT-MOD-001
2. Search/retrieve source_type = lab_result
3. Match lab_type text = HbA1c
4. Sort evidence by visit_date
5. Summarize values chronologically
6. Cite each visit or cite the retrieved lab chunks
```

## 9.6 Recommended Lab Chunk Text Format

```text
Patient PAT-MOD-001 had lab results at visit VST-MOD-001-003 on 2024-03-08.
Condition context: T2DM.
HbA1c: 7.2 % (HIGH), reference range 4.0-5.6 %.
FBG: 132 mg/dL (HIGH), reference range 70-99 mg/dL.
```

This text is retrieval-friendly because it includes patient ID, visit ID, date, condition, lab names, values, units, and flags.

---

# 10. Medication System

## 10.1 Medication Whitelist

Only these medications are valid:

| Medication | Class | Frequency | Route |
|---|---|---|---|
| Metformin | Biguanide | twice_daily | oral |
| Glibenclamide | Sulfonylurea | once_daily | oral |
| Lisinopril | ACE Inhibitor | once_daily | oral |
| Amlodipine | Calcium Channel Blocker | once_daily | oral |
| Losartan | ARB | once_daily | oral |
| Salbutamol inhaler | SABA | as_needed | inhaled |
| Budesonide inhaler | ICS | twice_daily | inhaled |
| Ferrous sulfate | Iron supplement | twice_daily | oral |
| Omeprazole | PPI | once_daily | oral |

## 10.2 Medication Object Structure

```json
{
  "medication_name": "Metformin",
  "medication_class": "Biguanide",
  "dose": "500 mg",
  "frequency": "twice_daily",
  "route": "oral",
  "start_date": "2023-09-10",
  "stop_date": null
}
```

## 10.3 Frequency Enums

```text
once_daily
twice_daily
as_needed
```

## 10.4 Route Enums

```text
oral
inhaled
```

`subcutaneous` is forbidden because no whitelisted medication uses it in the locked project scope.

## 10.5 How Medication Chunks Are Generated

Prescription chunks should summarize all medications for one visit.

Recommended prescription chunk:

```text
Patient PAT-MOD-001 medication record for visit VST-MOD-001-002 on 2023-12-09.
Condition context: T2DM.
Medication: Metformin, class Biguanide, dose 500 mg, frequency twice_daily, route oral, start date 2023-12-09, stop date active.
```

## 10.6 Medication Retrieval Dependencies

| Query | Expected Source Type |
|---|---|
| “What medications does this patient currently take?” | `prescription` |
| “What diabetes medication was prescribed?” | `prescription` |
| “Was Metformin changed?” | `prescription` + visit dates |
| “What medication is linked to hypertension?” | `prescription` with condition context |

## 10.7 Allergy Conflict Protection

Medication records are validated against `allergy_registry`. If a medication name exactly matches an allergen, the patient should fail validation and must not be ingested.

---

# 11. Allergy System

## 11.1 Allergy Registry Structure

```json
"allergy_registry": [
  {
    "allergen": "Penicillin",
    "reaction": "skin rash",
    "severity": "mild",
    "recorded_date": "2024-02-03",
    "source_visit_id": "VST-NRM-002-001"
  }
]
```

## 11.2 Why Allergy Registry Exists

The allergy registry creates a stable, patient-level source for allergy retrieval. It allows the system to answer questions such as:

```text
Does this patient have any recorded allergies?
What reaction was documented?
When was the allergy recorded?
Which visit recorded the allergy?
```

## 11.3 Allergy Retrieval

Recommended allergy chunk:

```text
Patient PAT-NRM-002 documented allergy record.
Allergen: Penicillin.
Reaction: skin rash.
Severity: mild.
Recorded date: 2024-02-03.
Source visit: VST-NRM-002-001.
```

Recommended metadata:

```json
{
  "patient_id": "PAT-NRM-002",
  "source_type": "allergy",
  "visit_id": "VST-NRM-002-001",
  "visit_date": "2024-02-03",
  "conditions": [],
  "visit_type": "initial"
}
```

## 11.4 Contradiction Prevention

Validation rule V2 ensures a medication does not conflict with an allergen in `allergy_registry`.

Invalid example:

```json
"allergy_registry": [
  { "allergen": "Metformin", "reaction": "rash", "severity": "mild" }
],
"medications": [
  { "medication_name": "Metformin" }
]
```

## 11.5 Important Framing

The system retrieves documented allergies. It does not detect, infer, or predict allergies.

Correct wording:

```text
The system retrieves documented allergy records.
```

Forbidden wording:

```text
The system detects allergies.
```

---

# 12. SOAP Note System

## 12.1 SOAP Structure

```json
"soap_note": {
  "subjective": "...",
  "objective": "...",
  "assessment": "...",
  "plan": "..."
}
```

## 12.2 Section Meanings

| Section | Purpose |
|---|---|
| `subjective` | Patient-reported or contextual narrative based on structured facts |
| `objective` | Vitals, labs, and measurable visit data |
| `assessment` | Documented diagnoses only |
| `plan` | Documented medication and follow-up information only |

## 12.3 SOAP Is Narrative-Only

SOAP text must never create new structured facts. It can describe facts that already exist in the visit record, but it must not invent medications, labs, diagnoses, allergies, or dates.

Correct flow:

```text
Structured JSON facts
        ↓
SOAP narrative generation
        ↓
SOAP audit
        ↓
doctor_note chunk
```

Incorrect flow:

```text
LLM invents medication
        ↓
SOAP text says medication exists
        ↓
RAG retrieves unsupported claim
        ↓
Answer becomes unsafe
```

## 12.4 Doctor-Note Chunks

Doctor-note chunks should be built from SOAP sections and may include important structured context such as visit date and BP values.

Recommended doctor-note chunk:

```text
Patient PAT-CHR-001 doctor note for visit VST-CHR-001-004 on 2022-10-12.
Visit type: hospitalization.
Diagnoses documented: T2DM, HTN, CKD.
Vitals: BP 158/96 mmHg, heart rate 79 bpm, BMI 29.6.
SOAP Subjective: ...
SOAP Objective: ...
SOAP Assessment: ...
SOAP Plan: ...
```

## 12.5 Grounding Dependency

The RAG answer generator should only answer from retrieved chunks. SOAP chunks are useful because they provide natural language context, but they must remain traceable to structured JSON.

## 12.6 Hallucination Prevention

SOAP audit should check:

| Risk | Audit Strategy |
|---|---|
| Fabricated medication | Search for whitelisted medication names not in visit medication list |
| Missing BP in objective text | Compare SOAP text against structured vitals |
| Allergen prescribed in text | Search allergen mentions near prescription verbs |
| Empty SOAP sections | Require all four sections |

---

# 13. Metadata Architecture

## 13.1 Patient Metadata

The patient JSON only stores minimal patient-level metadata:

```json
"metadata": {
  "tier": "moderate"
}
```

Allowed values:

```text
normal
moderate
chronic
```

## 13.2 Chunk Metadata

ChromaDB metadata is generated during ingestion. It should not be stored inside patient JSON.

Minimum recommended chunk metadata:

```json
{
  "patient_id": "PAT-MOD-001",
  "visit_id": "VST-MOD-001-003",
  "visit_date": "2024-03-08",
  "source_type": "lab_result",
  "conditions": ["T2DM"],
  "visit_type": "follow_up"
}
```

## 13.3 Why Metadata Is Intentionally Minimal

Metadata should help retrieval filters, not duplicate the clinical record.

Good metadata:

| Field | Reason |
|---|---|
| `patient_id` | Patient-scoped retrieval |
| `visit_id` | Citation anchor |
| `visit_date` | Temporal filtering |
| `source_type` | Query routing |
| `conditions` | Condition filter/rerank |
| `visit_type` | Visit-type filter/rerank |

Bad metadata:

| Field | Why Forbidden |
|---|---|
| `bp_systolic` | BP must stay in vitals/text evidence |
| `HbA1c_value` | Numeric clinical data belongs in chunk text |
| `diagnosis_prediction` | Inference is forbidden |
| `risk_score` | Predictive analytics is out of scope |

## 13.4 Metadata Safety Rules

```text
Metadata should identify evidence.
Metadata should not become the evidence itself.
```

This keeps retrieval explainable and prevents the vector database from becoming a hidden clinical database.

---

# 14. Validation Architecture

## 14.1 Validation Purpose

Validation is the gate between data generation and RAG ingestion.

```text
Generate patient JSON
        ↓
Validate V1–V11
        ↓
Zero FAIL required
        ↓
Ingest into ChromaDB
```

## 14.2 Validation Rules V1–V11

| Rule | Purpose | Severity |
|---|---|---|
| V1 | Chronological visit order | FAIL |
| V2 | Medication must not match allergy allergen | FAIL |
| V3 | Impossible vitals and age bounds | FAIL |
| V4 | Required fields and forbidden demographics.age | WARN/FAIL |
| V5 | `prior_visit_id` integrity | WARN |
| V6 | Duplicate `visit_id` prevention | FAIL |
| V7 | Enum validation and CKD co-occurrence | FAIL |
| V8 | Date format validation | FAIL |
| V9 | BP forbidden in labs | FAIL |
| V10 | `timeline_events` forbidden | FAIL |
| V11 | Medication whitelist, frequency, and route validation | FAIL |

## 14.3 Structure Validation

Structure validation ensures that required fields exist and unsupported fields do not exist.

Examples:

| Check | Why It Matters |
|---|---|
| `visits[].soap_note` exists | Required for doctor-note chunks |
| `visits[].labs[]` is an array | Required for lab chunks |
| `visits[].linked_documents[]` exists | Required for OCR linkage |
| `metadata.tier` exists | Required for tier logic |

## 14.4 Medical Consistency Validation

This project does not do clinical reasoning, but it does enforce consistency rules for synthetic data.

Examples:

| Rule | Purpose |
|---|---|
| CKD requires T2DM + HTN + chronic tier | Prevents invalid condition combinations |
| Medication must not match allergen | Prevents direct contradiction |
| BP range bounds | Prevents impossible synthetic vitals |
| Lab type enum | Prevents unsupported lab categories |

## 14.5 Timeline Validation

Timeline correctness depends on:

```text
visit_date order
prior_visit_id references
unique visit_id values
no stored timeline_events
```

## 14.6 Ingestion Protection

The ingestion layer should refuse to run unless validation passes with zero FAIL issues.

Recommended ingestion guard:

```python
report = validate_patient_files()
if not report.passed:
    raise RuntimeError("Cannot ingest invalid patient records.")
```

## 14.7 RAG Safety

Validation protects RAG safety because the model can only be as reliable as the retrieved evidence. Invalid data produces unreliable chunks, unreliable chunks produce unreliable answers, and unreliable answers break the grounded AI constraint.

---

# 15. Chunking and RAG Dependencies

## 15.1 Chunking Goal

The chunking layer converts validated patient JSON into semantic text units that can be embedded and retrieved.

The goal is not to create beautiful prose. The goal is to create retrieval-friendly evidence.

## 15.2 Recommended Chunk Boundaries

| Chunk Type | Source Type | Boundary | Main Query Type |
|---|---|---|---|
| SOAP doctor note | `doctor_note` | One visit | Visit summary, BP, assessment, timeline context |
| Lab result | `lab_result` | One visit | Lab trend and value retrieval |
| Prescription | `prescription` | One visit | Medication history retrieval |
| Allergy record | `allergy` | One patient | Allergy retrieval |

## 15.3 Do Not Use Cross-Visit Chunks

Cross-visit chunks create incorrect metadata. If one chunk contains two visit dates, ChromaDB can only store one `visit_date`, which makes temporal retrieval unreliable.

Bad:

```text
Chunk contains visits from January and April but metadata says visit_date = January.
```

Good:

```text
One chunk = one visit = one visit_date = one citation anchor.
```

Exception:

```text
The allergy chunk may summarize allergy_registry[] once per patient.
```

## 15.4 Doctor-Note Chunk Strategy

Use:

```text
source_type = doctor_note
```

Include:

| Include | Reason |
|---|---|
| `patient_id` | Patient identity |
| `visit_id` | Citation anchor |
| `visit_date` | Timeline and temporal retrieval |
| `visit_type` | Emergency/hospitalization filtering |
| `diagnoses` | Condition context |
| `vitals` including BP | BP retrieval from text |
| SOAP sections | Main narrative evidence |

Do not store BP as metadata. Put BP in chunk text.

## 15.5 Lab Chunk Strategy

Use:

```text
source_type = lab_result
```

Include:

| Include | Reason |
|---|---|
| Lab names | Semantic matching |
| Values | Answer evidence |
| Units | Prevent ambiguity |
| Flags | Normal/high/low explanation |
| Reference ranges | Contextual explanation |
| Visit date | Trend ordering |

## 15.6 Prescription Chunk Strategy

Use:

```text
source_type = prescription
```

Include:

| Include | Reason |
|---|---|
| Medication name | Direct medication retrieval |
| Class | Medication class queries |
| Dose | Specific prescription answers |
| Frequency | Schedule answers |
| Route | Route-specific queries |
| Start/stop dates | History and current medication reasoning |

## 15.7 Allergy Chunk Strategy

Use:

```text
source_type = allergy
```

Recommended as one patient-level chunk:

```text
Patient PAT-CHR-001 allergy registry.
Documented allergen: Penicillin.
Reaction: generalized rash.
Severity: moderate.
Recorded date: 2022-01-15.
Source visit: VST-CHR-001-001.
```

## 15.8 Metadata Extraction Strategy

Recommended metadata builder:

```python
def build_metadata(patient, visit, source_type):
    return {
        "patient_id": patient["patient_id"],
        "visit_id": visit["visit_id"],
        "visit_date": visit["visit_date"],
        "source_type": source_type,
        "conditions": visit["diagnoses"],
        "visit_type": visit["visit_type"],
    }
```

For allergy chunk:

```python
def build_allergy_metadata(patient):
    first_source_visit_id = patient["allergy_registry"][0]["source_visit_id"]
    return {
        "patient_id": patient["patient_id"],
        "visit_id": first_source_visit_id,
        "source_type": "allergy",
        "conditions": patient["conditions"],
        "visit_type": "initial"
    }
```

## 15.9 Patient-Scoped Retrieval

Every query should be patient-scoped unless the feature explicitly supports cross-patient search.

Recommended retrieval filter:

```python
where={"patient_id": selected_patient_id}
```

## 15.10 Query Routing Recommendations

| Query Intent | Prefer Source Type |
|---|---|
| Allergy question | `allergy` |
| Medication question | `prescription` |
| Lab trend question | `lab_result` |
| BP question | `doctor_note` |
| Visit summary | `doctor_note` |
| Hospitalization question | `doctor_note` with `visit_type=hospitalization` |

## 15.11 Grounding Requirements

The answer generator must follow this rule:

```text
No retrieved evidence = no generated medical answer.
```

Recommended no-evidence response:

```text
The available retrieved records do not contain enough documented evidence to answer this question.
```

## 15.12 Citation Anchors

Each answer should cite retrieved evidence using:

| Citation Field | Source |
|---|---|
| `patient_id` | Root patient object |
| `visit_id` | Visit object or allergy source visit |
| `visit_date` | Visit object |
| `source_type` | Chunk type |
| `document_ids` | `linked_documents[]` |
| `chunk_id` | Generated during ingestion |

---

# 16. Forbidden Rules

## 16.1 Forbidden Fields and Values

| Forbidden Item | Reason |
|---|---|
| `timeline_events` | Timeline must be generated from visits |
| `demographics.age` | Age must be derived dynamically |
| BP in `labs[]` | BP is a vital sign, not a lab |
| BP in metadata | BP is evidence text, not filter metadata |
| `subcutaneous` route | Removed from final route enum |
| Unsupported medication names | Violates whitelist |
| Unsupported condition names | Breaks metadata filters |
| Random fields | Breaks strict schema and chunk assumptions |

## 16.2 Forbidden JSON Examples

### `timeline_events`

```json
{
  "timeline_events": []
}
```

### `demographics.age`

```json
{
  "demographics": {
    "age": 42
  }
}
```

### BP in Labs

```json
{
  "labs": [
    {
      "lab_type": "blood_pressure",
      "value": "145/92"
    }
  ]
}
```

### Unsupported Route

```json
{
  "route": "subcutaneous"
}
```

---

# 17. Critical Stability Rules

## 17.1 Locked Root Fields

These fields must not be renamed or removed:

```text
schema_version
patient_id
demographics
conditions
allergy_registry
visits
metadata
```

## 17.2 Locked Visit Fields

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

## 17.3 Locked Enums

| Enum | Values |
|---|---|
| Conditions | `T2DM`, `HTN`, `Asthma`, `IDA`, `GERD`, `CKD` |
| Lab types | `HbA1c`, `FBG`, `Creatinine`, `Hemoglobin`, `Ferritin` |
| Visit types | `initial`, `follow_up`, `emergency`, `hospitalization` |
| Frequency | `once_daily`, `twice_daily`, `as_needed` |
| Route | `oral`, `inhaled` |
| Flag | `NORMAL`, `HIGH`, `LOW` |
| Severity | `mild`, `moderate`, `severe` |
| Tier | `normal`, `moderate`, `chronic` |
| Sex | `male`, `female` |

## 17.4 What Breaks If Modified

| Change | Breakage |
|---|---|
| Rename `patient_id` | Patient-scoped retrieval breaks |
| Rename `visit_id` | Citations and timelines break |
| Rename `labs` | Lab chunks fail |
| Add BP to metadata | Violates BP architecture and pollutes filters |
| Change condition enum strings | Condition filters fail |
| Add random medication route | V11 and retrieval consistency break |
| Store timeline events | Timeline source of truth becomes duplicated |

---

# 18. Engineering Recommendations for Member 2 — Gamal

## 18.1 General RAG Rule

Build the RAG layer around the schema. Do not force the schema to fit retrieval code. The schema is the source contract.

## 18.2 Metadata Extraction Recommendations

Use metadata for filtering and citation identity only.

Recommended metadata:

```json
{
  "patient_id": "PAT-MOD-001",
  "visit_id": "VST-MOD-001-003",
  "visit_date": "2024-03-08",
  "source_type": "lab_result",
  "conditions": ["T2DM"],
  "visit_type": "follow_up"
}
```

Avoid:

```json
{
  "bp_systolic": 140,
  "HbA1c": 7.2,
  "medication_count": 2
}
```

## 18.3 Chunking Recommendations

| Recommendation | Reason |
|---|---|
| One visit per chunk group | Preserves correct visit metadata |
| Include semantic labels in text | Improves embedding retrieval |
| Include dates in chunk text | Helps temporal questions |
| Include values and units | Supports grounded answers |
| Keep chunk IDs deterministic | Makes debugging easier |

## 18.4 Retrieval Recommendations

Start simple:

```text
patient_id filter + source_type preference + top-k retrieval
```

Suggested top-k:

| Query Type | Initial Top-k |
|---|---:|
| Allergy | 3 |
| Medication | 3–5 |
| Lab trend | 5–8 |
| Timeline/summary | 5–8 |
| BP query | 3–5 doctor_note chunks |

## 18.5 Citation Recommendations

Every answer should return citation objects, not just text.

Recommended citation object:

```json
{
  "chunk_id": "VST-MOD-001-003-lab_result-01",
  "patient_id": "PAT-MOD-001",
  "visit_id": "VST-MOD-001-003",
  "visit_date": "2024-03-08",
  "source_type": "lab_result",
  "document_ids": ["DOC-MOD-001-003"]
}
```

## 18.6 Grounding Recommendations

Before calling the LLM, check whether retrieved chunks are relevant. If no relevant chunks exist, return a no-evidence answer.

Recommended grounding gate:

```python
if not retrieved_chunks:
    return "The available records do not contain enough documented evidence."
```

## 18.7 Ingestion Safety Recommendations

Before ingestion:

```text
1. Run validation.
2. Require zero FAIL violations.
3. Reject invalid patient files.
4. Build chunks from validated files only.
5. Assert metadata fields immediately inside chunker.py.
6. Do not ingest quarantine files.
```

## 18.8 Retrieval Filter Recommendations

| Feature | Filter Strategy |
|---|---|
| Patient query | `patient_id` required |
| Allergy query | `source_type=allergy` preferred |
| Medication query | `source_type=prescription` preferred |
| Lab query | `source_type=lab_result` preferred |
| Timeline query | Sort visits from JSON or retrieve doctor notes by date |
| BP query | Search doctor-note chunks; do not search lab metadata |

## 18.9 Debugging Recommendations

When retrieval fails, inspect in this order:

```text
1. Is the patient JSON valid?
2. Did the chunk text include the target term?
3. Did metadata include correct patient_id?
4. Did source_type match the query intent?
5. Did visit_date exist and match the visit?
6. Did ChromaDB receive the expected chunk count?
7. Did top-k return semantically relevant chunks?
```

---

# 19. Failure Scenarios

## 19.1 If IDs Change

| Broken Element | Impact |
|---|---|
| `patient_id` | Patient-scoped queries fail |
| `visit_id` | Citations no longer point to stable evidence |
| `document_id` | OCR references break |
| Chunk IDs | Debugging and citation traceability break |

## 19.2 If Enums Change

| Changed Enum | Impact |
|---|---|
| Conditions | Filters and condition retrieval fail |
| Visit types | Timeline and emergency/hospitalization queries fail |
| Lab types | Lab trend retrieval fails |
| Source types | Query routing fails |
| Routes | Medication validation fails |

## 19.3 If Metadata Changes

If metadata becomes too large or inconsistent, ChromaDB filtering becomes unreliable.

Example failure:

```text
Some chunks use source_type = "lab"
Other chunks use source_type = "lab_result"
```

Result:

```text
Lab queries miss half the evidence.
```

## 19.4 If Visit Structure Changes

If `visits[]` changes, the following break:

| System | Breakage |
|---|---|
| Chunker | Cannot find visit fields |
| Timeline | Cannot sort events |
| Citations | Cannot anchor evidence |
| SOAP generation | Missing prompt facts |
| Retrieval | Missing date/source context |

## 19.5 If Validation Is Bypassed

Bypassing validation can lead to:

```text
Invalid patient records
→ bad chunks
→ bad metadata
→ wrong retrieval
→ unsupported generated answers
→ failed demo
```

Validation is therefore not optional. It is a hard engineering gate.

---

# 20. Final Architecture Summary

The patient schema is the foundation of the AI Based Clinical Record Summarization System. It defines how synthetic patient data is generated, validated, chunked, embedded, retrieved, grounded, cited, and displayed.

The design works because it is strict:

```text
Strict schema
→ deterministic records
→ reliable validation
→ stable chunking
→ safe metadata
→ accurate retrieval
→ grounded answers
→ clear citations
→ stable demo
```

The schema supports the full RAG pipeline through stable IDs, chronological visits, validated conditions, structured labs, whitelisted medications, documented allergies, narrative SOAP notes, linked documents, and minimal metadata.

For Member 2, the most important implementation principle is:

```text
Do not treat patient JSON as loose text.
Treat it as a structured evidence database.
```

The RAG layer should preserve the schema’s boundaries:

| Boundary | RAG Meaning |
|---|---|
| Patient boundary | Prevent cross-patient contamination |
| Visit boundary | Preserve date and citation accuracy |
| Source-type boundary | Route queries to the right evidence type |
| Metadata boundary | Keep filters stable and safe |
| SOAP boundary | Use narrative only as grounded text evidence |
| Validation boundary | Never ingest invalid records |

If these rules are followed, the project will have a strong data-to-RAG foundation that is safe, explainable, academically appropriate, and ready for DEPI evaluation.
