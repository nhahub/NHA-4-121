# RAG Handoff Contract

## AI-Based Clinical Record Summarization System

---

# 1. Document Metadata

| Field | Value |
|---|---|
| Document Path | `docs/rag_handoff_contract.md` |
| Project Name | AI-Based Clinical Record Summarization System |
| Document Type | Official Data-to-RAG Engineering Handoff Contract |
| Data Owner | Ahmed Hesham Kamel — Team Leader & Data Engineering Lead |
| RAG Owner | Gamal Mohamed Gad — Retrieval-Augmented Generation Engineer |
| Secondary Audience | Backend Developer, Frontend/OCR Developer, DevOps/Testing Member, DEPI Evaluators |
| Status | READY FOR FINAL HANDOFF |
| Version | v1.0 |
| Scope | Defines the exact handoff boundary between validated synthetic patient data and the RAG implementation layer |
| Source of Truth | `data/patients/`, `config/constants.py`, `validators/`, `soap/`, `ingestion/retrieval_enricher.py`, `ingestion/retrieval_enrichment_auditor.py` |
| Related Documents | `docs/data_schema_contract.md`, `docs/validation_rules.md`, `docs/data_generation_pipeline.md`, `docs/retrieval_enrichment_contract.md`, `docs/project_scope_and_safety_rules.md`, `docs/architecture_summary.md`, `docs/team_ownership_and_architecture.md` |

---

# 2. Purpose of This Contract

This document defines the official engineering handoff from Ahmed Hesham Kamel to Gamal Mohamed Gad.

Ahmed owns the data engineering layer:

```text
config/
data/patients/
data/schemas/
generators/
validators/
soap/
data quality documentation
schema documentation
```

Gamal owns the RAG engineering layer:

```text
ingestion/
rag/
data/chromadb/
retrieval tests
chunking
metadata construction
embeddings
retrieval
grounding
citations
RAG answer generation
```

The purpose of this contract is to make clear:

- what Gamal receives from Ahmed,
- what Gamal may safely assume,
- what Gamal must not change,
- what must be validated before ingestion,
- how retrieval enrichment should be used,
- how chunks and metadata should preserve evidence boundaries,
- and how RAG answers must remain grounded and citation-based.

This document is not a general architecture summary. It is a practical handoff contract for starting ingestion, retrieval, and RAG implementation safely.

---

# 3. Handoff Boundary

The handoff boundary is simple:

```text
Ahmed delivers validated patient evidence.
Gamal converts that evidence into retrievable, grounded RAG chunks.
```

## 3.1 Ahmed Delivers

Ahmed delivers:

```text
config/constants.py
config/paths.py
config/showcase_patients.json
data/patients/*.json
data/schemas/patient_schema.json
validators/rules.py
validators/validate.py
validators/validation_report.py
soap/*.py
ingestion/retrieval_enricher.py
ingestion/retrieval_enrichment_auditor.py
docs/data_schema_contract.md
docs/validation_rules.md
docs/data_generation_pipeline.md
docs/retrieval_enrichment_contract.md
```

## 3.2 Gamal Builds

Gamal builds or owns:

```text
ingestion/chunker.py
ingestion/metadata_builder.py
ingestion/ingest.py
rag/retriever.py
rag/prompt_builder.py
rag/llm_client.py
rag/answer_generator.py
rag/citations.py
rag/grounding.py
rag/query_models.py
tests/test_retrieval.py
data/chromadb/
```

## 3.3 Boundary Rule

Gamal should not modify Ahmed-owned schema, generator, validation, or SOAP files unless Ahmed explicitly approves the change.

If RAG implementation needs a new field, metadata item, source type, or schema assumption, the change must be discussed first and reflected in the relevant contract document.

---

# 4. Handoff Inputs

Gamal should treat the following as the official input layer for RAG.

## 4.1 Approved Patient Records

Path:

```text
data/patients/*.json
```

Meaning:

- contains only approved synthetic patient JSON records,
- each file must pass validation,
- each file may contain multiple chronological visits,
- each visit may contain vitals, labs, medications, SOAP note, linked documents, and prior visit reference.

Gamal may ingest from this folder only.

## 4.2 Quarantine Records

Path:

```text
data/quarantine/
```

Meaning:

- contains invalid, rejected, or blocked patient records,
- contains issue reports,
- must never be ingested into ChromaDB,
- can be used only for debugging data problems.

## 4.3 Constants

Path:

```text
config/constants.py
```

Meaning:

This is the single source of truth for:

- condition enums,
- source types,
- visit types,
- lab types,
- medication whitelist,
- frequency values,
- route values,
- severity values,
- tier names,
- ID prefixes,
- dataset mode values,
- dataset distribution values.

Gamal must import locked values from this file instead of duplicating strings manually.

## 4.4 Validation System

Paths:

```text
validators/rules.py
validators/validate.py
validators/validation_report.py
scripts/validate_all.py
```

Meaning:

Validation is the hard gate before ingestion.

The RAG layer must not ingest records unless:

```text
FAIL violations = 0
```

## 4.5 SOAP Notes

Paths:

```text
soap/soap_generator.py
soap/soap_renderers.py
soap/soap_templates.py
soap/soap_selector.py
soap/soap_semantics.py
soap/soap_safety.py
soap/soap_auditor.py
```

Meaning:

SOAP notes are deterministic template-based narrative text generated from structured JSON only.

Important current implementation rule:

```text
No LLM is used during SOAP generation.
```

The LLM is used later only in the RAG answer generation layer.

SOAP is used mainly as evidence text for `doctor_note` chunks.

## 4.6 Retrieval Enrichment Layer

Paths:

```text
ingestion/retrieval_enricher.py
ingestion/retrieval_enrichment_auditor.py
```

Meaning:

This layer creates deterministic support text to improve semantic retrieval.

It does not replace the patient JSON or SOAP note.

Retrieval enrichment text is:

```text
deterministic
structured-fact-derived
safe support text
not source truth
not a medical conclusion
not generated by an LLM
```

---

# 5. Required Pipeline Before RAG Work

Before Gamal starts chunking or ingestion, the following commands should pass.

## 5.1 Generate Full Dataset

```bash
python scripts/generate_all.py --mode full --clean
```

Expected result:

```text
30 valid patients
0 quarantined patients
```

## 5.2 Validate Full Dataset

```bash
python scripts/validate_all.py --mode full
```

Expected result:

```text
Validation PASS
Dataset-level checks PASS
```

## 5.3 Optional SOAP Dry Run

```bash
python scripts/generate_soap.py --dry-run
```

Expected result:

```text
Validation failures: 0
SOAP failures: 0
```

## 5.4 Retrieval Enrichment Debug Check

```bash
python scripts/check_retrieval_enricher_output.py --patient-id PAT-MOD-001 --visit-index 0
```

Expected result:

- prints deterministic retrieval support text,
- no runtime error,
- source types are readable,
- BP does not appear as metadata,
- enrichment remains grounded.

---

# 6. What Gamal May Safely Assume

Gamal may safely assume that approved patient files in `data/patients/` satisfy the following conditions.

## 6.1 Patient-Level Assumptions

```text
patient_id exists and is stable
schema_version exists
conditions is a list of locked condition enums
metadata.tier exists and is valid
allergy_registry exists
visits exists and is chronological
```

## 6.2 Visit-Level Assumptions

```text
visit_id exists and is unique within the patient
visit_date exists and uses YYYY-MM-DD
visit_type is one of the locked visit types
attending_physician exists
diagnoses exists
vitals exists
labs exists
medications exists
soap_note exists
linked_documents exists
prior_visit_id is either null or points to a valid previous visit
```

## 6.3 Vitals Assumptions

```text
BP exists only in visit.vitals
BP is not in labs
BP is not in metadata
BP should be retrieved from doctor_note text or visit text, not metadata filters
```

## 6.4 Lab Assumptions

Allowed lab types are:

```text
HbA1c
FBG
Creatinine
Hemoglobin
Ferritin
```

Creatinine generation follows the current locked rule:

```text
Creatinine appears for CKD patients or patients with combined T2DM + HTN context.
T2DM-only or HTN-only patients are not required to have Creatinine labs.
```

## 6.5 Medication Assumptions

Medication names are always from the whitelist in `config/constants.py`.

Routes are locked to:

```text
oral
inhaled
```

Forbidden:

```text
subcutaneous
```

Medication timeline semantics:

```text
start_date = first documented start date of that medication
stop_date = null unless the medication is documented as stopped
```

Gamal should preserve `start_date` and `stop_date` in prescription chunks because they are important for medication timeline queries.

## 6.6 CKD Assumptions

CKD is complication-only.

If `CKD` appears, the patient must also have:

```text
T2DM
HTN
metadata.tier = chronic
```

Dataset-level rule:

```text
CKD patient count <= 2
```

---

# 7. What Gamal Must Not Assume

Gamal must not assume:

- that `data/quarantine/` contains ingestible records,
- that all fields are safe to put into metadata,
- that BP can be filtered as metadata,
- that generated summaries are source truth,
- that unsupported medical inference is allowed,
- that source types may be renamed freely,
- that chunking may combine multiple visits into one evidence chunk,
- that patient-level summaries may replace visit-level evidence,
- that OCR outputs are live API outputs during demo,
- that RAG answers may include facts not present in retrieved chunks.

---

# 8. Source Types

The locked source types for ingestion are:

```text
doctor_note
lab_result
prescription
allergy
```

These source types must stay stable because they are used by:

- retrieval filters,
- citation formatting,
- evaluation queries,
- UI display logic,
- test expectations,
- demo scripts.

## 8.1 `doctor_note`

Source object:

```text
visit.soap_note
```

Expected use:

- visit summaries,
- patient history questions,
- BP retrieval from objective text,
- emergency visit questions,
- timeline-style explanations.

Important:

BP-related queries should usually retrieve `doctor_note` chunks because BP is not metadata and not a lab.

## 8.2 `lab_result`

Source object:

```text
visit.labs[]
```

Expected use:

- HbA1c trend queries,
- FBG queries,
- Creatinine queries,
- Hemoglobin and Ferritin queries,
- lab progression summaries.

Important:

BP must never appear as a `lab_result` chunk.

## 8.3 `prescription`

Source object:

```text
visit.medications[]
```

Expected use:

- current medication questions,
- medication change questions,
- dose/frequency/route questions,
- start/stop date questions,
- condition-treatment history questions.

Important:

Prescription chunks should include:

```text
medication_name
medication_class
dose
frequency
route
start_date
stop_date
visit_date
visit_id
```

## 8.4 `allergy`

Source object:

```text
patient.allergy_registry[]
```

Expected use:

- allergy history retrieval,
- documented allergen questions,
- reaction/severity questions,
- allergy highlight panel support.

Important:

The system retrieves documented allergies. It does not detect, predict, or infer allergies.

---

# 9. Retrieval Enrichment Usage Contract

Retrieval enrichment may be used to improve semantic retrieval quality.

It should be appended to, prepended to, or included inside chunk text when useful.

It must not become a replacement for the original evidence.

## 9.1 Correct Use

Correct:

```text
chunk_text = original evidence text + deterministic retrieval enrichment support text
```

Correct:

```text
Use enrichment text to improve semantic matching for queries.
```

Correct:

```text
Audit enrichment text before ingestion.
```

## 9.2 Incorrect Use

Incorrect:

```text
Treat enrichment text as a clinical conclusion.
```

Incorrect:

```text
Cite enrichment text as if it were the original record.
```

Incorrect:

```text
Use enrichment text to add new facts not present in JSON or SOAP.
```

Incorrect:

```text
Skip audit because the text is deterministic.
```

## 9.3 Enrichment Audit Rule

Any enriched retrieval text should pass:

```python
audit_retrieval_text(...)
```

or batch audit:

```python
audit_retrieval_texts(...)
```

before ingestion.

If retrieval enrichment audit returns FAIL, the chunk should not be ingested until the issue is fixed.

---

# 10. Chunking Contract Summary

This document does not fully define chunk structure. That belongs to:

```text
docs/chunking_and_metadata_contract.md
```

However, Gamal should follow these minimum rules immediately.

## 10.1 Chunk Scope

Each chunk should be anchored to one evidence source.

Recommended minimum chunk units:

```text
one visit doctor_note chunk
one visit lab_result chunk when labs exist
one visit prescription chunk when medications exist
one patient allergy chunk when allergy_registry exists
```

## 10.2 No Cross-Visit Chunks

Do not combine multiple visits into one chunk.

Why:

- visit_date metadata becomes ambiguous,
- citations become unclear,
- temporal queries become unreliable,
- trend summaries may retrieve mixed evidence.

Exception:

```text
allergy chunk may summarize patient-level allergy_registry
```

## 10.3 Chunk Text Should Be Retrieval-Friendly

Chunk text should include:

```text
patient_id
visit_id
visit_date
source_type
condition names when relevant
lab type names when relevant
medication names when relevant
clear evidence wording
```

Do not optimize only for human readability. Optimize for semantic search.

---

# 11. Metadata Contract Summary

This document does not fully define metadata. That belongs to:

```text
docs/chunking_and_metadata_contract.md
```

However, the following metadata rules are mandatory.

## 11.1 Required Metadata Candidates

Each chunk should be able to carry:

```text
chunk_id
patient_id
visit_id
visit_date
source_type
visit_type
conditions
tier
```

For allergy chunks, `visit_id` may be null or may reference the source visit depending on the final citation contract.

## 11.2 Forbidden Metadata

The following must not be stored in ChromaDB metadata:

```text
bp_systolic
bp_diastolic
full_vitals
full_labs
full_medications
full_soap
large nested objects
AI-generated summaries
risk scores
diagnosis predictions
treatment recommendations
```

## 11.3 BP Metadata Rule

BP is never metadata.

Correct location:

```text
visit.vitals.bp_systolic
visit.vitals.bp_diastolic
SOAP objective text
doctor_note chunk text
```

Incorrect locations:

```text
lab_result chunk metadata
ChromaDB numeric metadata
patient metadata
```

---

# 12. Citation Requirements for RAG

Every generated RAG answer must be traceable to retrieved evidence.

Minimum citation anchors should include:

```text
patient_id
visit_id
visit_date
source_type
chunk_id
```

For OCR-linked documents, citation may also include:

```text
document_id
```

A citation should allow the team to answer:

```text
Which patient record supported this answer?
Which visit supported this answer?
Which source type supported this answer?
Which chunk was retrieved?
```

The final citation object should be defined in:

```text
docs/citation_contract.md
```

---

# 13. Grounding Requirements

The RAG layer must follow this rule:

```text
No retrieved evidence = no generated medical answer.
```

If retrieved chunks do not support the user question, the answer should say that the available records do not contain enough documented evidence.

The RAG layer must not:

- diagnose,
- recommend treatment,
- predict disease,
- infer undocumented conditions,
- invent medication changes,
- invent lab trends,
- infer allergy severity,
- summarize beyond retrieved evidence,
- answer from general medical knowledge instead of patient records.

---

# 14. Query Types Gamal Should Support

Gamal should optimize retrieval for these query types.

## 14.1 Medication Queries

Examples:

```text
What medications does this patient currently take?
When was Amlodipine added?
Has the diabetes medication changed over time?
What is the current dose of Metformin?
```

Expected source type:

```text
prescription
```

## 14.2 Lab Trend Queries

Examples:

```text
How has this patient's HbA1c changed over time?
What were the most recent Creatinine results?
Summarize the Hemoglobin trend.
```

Expected source type:

```text
lab_result
```

## 14.3 BP Queries

Examples:

```text
What was the patient's blood pressure at the last visit?
How did BP appear across recent visits?
```

Expected source type:

```text
doctor_note
```

Important:

BP should not be retrieved from lab metadata or BP metadata.

## 14.4 Allergy Queries

Examples:

```text
Does this patient have any recorded allergies?
What reaction was documented for this allergen?
When was the allergy recorded?
```

Expected source type:

```text
allergy
```

Correct wording:

```text
recorded allergies
documented allergy history
retrieved allergy records
```

Forbidden wording:

```text
detected allergy
predicted allergy
inferred allergy
```

## 14.5 Visit Summary Queries

Examples:

```text
What happened during the last visit?
Summarize the emergency visit.
What was documented in the initial visit?
```

Expected source type:

```text
doctor_note
```

## 14.6 Timeline Queries

Examples:

```text
Show the patient's visit timeline.
What changed between visits?
When did the medication change happen?
```

Expected source types:

```text
doctor_note
lab_result
prescription
```

Timeline reconstruction should come from visits, not from a stored `timeline_events` field.

---

# 15. Retrieval Testing Expectations

Gamal should build retrieval tests before polishing the backend or frontend.

Recommended test file:

```text
tests/test_retrieval.py
```

Minimum test coverage:

- allergy retrieval,
- medication retrieval,
- lab trend retrieval,
- BP retrieval from doctor-note chunks,
- visit summary retrieval,
- patient-scoped filtering,
- no-evidence behavior,
- citation presence,
- source type correctness.

Recommended pass threshold for showcase patients:

```text
All critical queries must pass.
Most high-priority queries should retrieve expected source_type in top-k.
```

Suggested top-k experiments:

```text
top_k = 3
top_k = 5
```

---

# 16. Handoff Acceptance Criteria

The RAG handoff is accepted when the following are true.

## 16.1 Data Acceptance

```text
python scripts/generate_all.py --mode full --clean
python scripts/validate_all.py --mode full
```

Expected:

```text
30 patients
0 validation FAIL
0 dataset-level FAIL
```

## 16.2 SOAP Acceptance

```text
python scripts/generate_soap.py --dry-run
```

Expected:

```text
0 validation FAIL
0 SOAP FAIL
```

## 16.3 Enrichment Acceptance

```text
python scripts/check_retrieval_enricher_output.py --patient-id PAT-MOD-001 --visit-index 0
```

Expected:

```text
retrieval text prints successfully
no unsupported source_type
no unsafe fabricated facts
```

## 16.4 RAG Acceptance

Gamal should later confirm:

```text
chunks created
metadata valid
ChromaDB populated
patient-scoped retrieval works
citations attached
retrieval tests pass for showcase patients
```

---

# 17. Ownership Escalation Rules

## 17.1 Ask Ahmed Before Changing

Gamal must ask Ahmed before changing:

```text
patient JSON schema
conditions enum
lab_type enum
source_type enum
visit_type enum
medication whitelist
route enum
frequency enum
validation rules V1–V11
SOAP structure
BP rule
CKD rule
data generation logic
```

## 17.2 Gamal May Decide Independently

Gamal may decide independently:

```text
chunk text formatting
chunk ID implementation details
embedding batching
ChromaDB collection setup
retrieval top-k experiments
query preprocessing
prompt assembly for RAG answers
citation formatting implementation
retrieval tests
RAG internal models
```

As long as these decisions do not violate the schema, validation, source type, metadata, BP, CKD, or safety contracts.

---

# 18. Common Mistakes to Avoid

## 18.1 Ingesting Before Validation

Incorrect:

```text
Generate data → ingest into ChromaDB
```

Correct:

```text
Generate data → validate → SOAP → audit → final validation → ingest
```

## 18.2 Treating BP as Lab Data

Incorrect:

```text
source_type = lab_result
metadata.bp_systolic = 150
```

Correct:

```text
source_type = doctor_note
chunk text includes objective BP wording
```

## 18.3 Creating Cross-Visit Chunks

Incorrect:

```text
one chunk contains Visit 1 + Visit 2 + Visit 3
```

Correct:

```text
one chunk is anchored to one visit and one source_type
```

## 18.4 Treating Enrichment as Source Truth

Incorrect:

```text
citation points to enrichment text only
```

Correct:

```text
citation points to patient_id, visit_id, source_type, and original evidence chunk
```

## 18.5 Using General Medical Knowledge

Incorrect:

```text
The answer explains what should happen medically based on general knowledge.
```

Correct:

```text
The answer summarizes what is documented in retrieved patient records.
```

---

# 19. Final Handoff Checklist for Ahmed

Ahmed should provide Gamal with:

```text
[ ] Updated README.md
[ ] docs/architecture_summary.md
[ ] docs/team_ownership_and_architecture.md
[ ] docs/project_scope_and_safety_rules.md
[ ] docs/data_schema_contract.md
[ ] docs/validation_rules.md
[ ] docs/data_generation_pipeline.md
[ ] docs/retrieval_enrichment_contract.md
[ ] docs/rag_handoff_contract.md
[ ] config/constants.py
[ ] config/paths.py
[ ] config/showcase_patients.json
[ ] generators/*.py
[ ] validators/*.py
[ ] soap/*.py
[ ] ingestion/retrieval_enricher.py
[ ] ingestion/retrieval_enrichment_auditor.py
[ ] scripts/generate_all.py
[ ] scripts/validate_all.py
[ ] scripts/generate_soap.py
[ ] scripts/check_retrieval_enricher_output.py
[ ] data/patients/*.json
[ ] data/schemas/patient_schema.json
```

---

# 20. Final Handoff Checklist for Gamal

Before implementing RAG, Gamal should confirm:

```text
[ ] I understand the patient schema.
[ ] I understand the validation hard gate.
[ ] I understand that SOAP is deterministic and not LLM-generated in the current implementation.
[ ] I understand that retrieval enrichment is support text, not source truth.
[ ] I understand the four source types.
[ ] I understand BP must not enter labs or metadata.
[ ] I understand CKD is complication-only.
[ ] I understand ingestion must read only from data/patients/.
[ ] I understand quarantine records must not be ingested.
[ ] I understand citations must point to retrieved evidence.
[ ] I understand no-evidence means no generated medical answer.
```

---

# 21. Final Contract Summary

Ahmed is responsible for trusted patient evidence.

Gamal is responsible for making that evidence retrievable, grounded, and citation-ready.

The contract between them is:

```text
Validated data only
Deterministic SOAP only
Audited enrichment only
Safe chunking only
Minimal metadata only
Patient-scoped retrieval only
Grounded answers only
Citations always
No unsupported medical conclusions
```

This file is the official RAG handoff boundary for the current project phase.

Once this contract is accepted, Gamal can safely begin:

```text
chunking
metadata construction
ChromaDB ingestion
retrieval testing
RAG prompt building
grounding
citation formatting
answer generation
```

without guessing Ahmed's data schema or data quality assumptions.
