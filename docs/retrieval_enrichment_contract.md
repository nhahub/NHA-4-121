# Retrieval Enrichment Contract

## AI-Based Clinical Record Summarization System

---

# 1. Document Metadata

| Field | Value |
|---|---|
| Document Path | `docs/retrieval_enrichment_contract.md` |
| Project Name | AI-Based Clinical Record Summarization System |
| Document Type | Retrieval Enrichment Implementation Contract |
| Primary Data Owner | Ahmed Hesham Kamel — Data Engineering Lead |
| Primary Consumer | Gamal Mohamed Gad — Retrieval-Augmented Generation Engineer |
| Secondary Audience | Backend Developer, DevOps/Testing Member, DEPI Evaluators, GitHub Reviewers |
| Status | READY FOR FINAL HANDOFF |
| Version | v1.0 |
| Scope | Deterministic retrieval enrichment text, enrichment safety audit, source type behavior, handoff rules before chunking and ingestion |
| Related Contracts | `docs/data_schema_contract.md`, `docs/validation_rules.md`, `docs/data_generation_pipeline.md`, `docs/rag_handoff_contract.md`, `docs/chunking_and_metadata_contract.md`, `docs/project_scope_and_safety_rules.md` |

---

# 2. Purpose of This Contract

This document defines the official contract for the retrieval enrichment layer used before chunking, embedding, and ChromaDB ingestion.

The goal of retrieval enrichment is to improve semantic retrieval quality without changing the clinical facts stored in the patient JSON files.

This contract explains:

- what retrieval enrichment is,
- why it exists,
- which files implement it,
- what each `source_type` means,
- what enrichment text may and may not contain,
- how the enrichment auditor protects the pipeline,
- and what Gamal can safely depend on when building chunking, metadata, ChromaDB ingestion, retrieval, grounding, and citations.

The enrichment layer is especially important because raw structured JSON is not always semantically rich enough for vector retrieval. A lab value such as `HbA1c = 8.2` is clinically meaningful, but retrieval works better when the chunk text also includes structured context such as patient ID, visit date, lab type, condition context, and source type.

---

# 3. Core Principle

Retrieval enrichment text is **support text**, not source truth.

The source truth remains:

```text
validated patient JSON
+ deterministic SOAP notes
```

Retrieval enrichment text must only restate, organize, or label documented facts already present in the structured record.

It must never:

- invent medical facts,
- infer diagnoses,
- recommend treatment,
- predict disease,
- change structured patient data,
- create new medication records,
- create new lab values,
- create new allergies,
- create new vitals,
- or add unsupported clinical interpretation.

---

# 4. Files Covered by This Contract

The retrieval enrichment layer currently consists of two implementation files.

```text
ingestion/retrieval_enricher.py
ingestion/retrieval_enrichment_auditor.py
```

## 4.1 `ingestion/retrieval_enricher.py`

Responsibility:

```text
Build deterministic retrieval-oriented text from validated patient JSON and visit data.
```

It should:

- read structured patient facts,
- read visit-level facts when required,
- generate semantic support text for retrieval,
- preserve documented facts exactly,
- keep output deterministic,
- avoid LLM calls,
- avoid mutation of patient records,
- avoid metadata construction,
- avoid ChromaDB writes,
- and avoid chunk ID construction unless explicitly required by a downstream contract.

It should not:

- call Groq or any LLM,
- create embeddings,
- write to ChromaDB,
- decide chunk metadata,
- perform clinical reasoning,
- replace SOAP notes,
- validate the full patient schema,
- or ingest anything.

## 4.2 `ingestion/retrieval_enrichment_auditor.py`

Responsibility:

```text
Audit retrieval enrichment text before it is used for chunking or ingestion.
```

It should detect:

- empty enrichment text,
- invalid `source_type`,
- missing visit context when a visit is required,
- unsupported placeholders,
- unsafe recommendation phrases,
- unsupported condition references,
- unsupported lab references,
- medication mentions not supported by the source context,
- BP metadata-like wording,
- and unusually long retrieval text.

It should not:

- rewrite enrichment text,
- mutate patient records,
- call an LLM,
- create chunks,
- create metadata,
- or write to ChromaDB.

---

# 5. Pipeline Position

Retrieval enrichment sits after validated data and SOAP generation, but before final chunking and ChromaDB ingestion.

The final pipeline order is:

```text
1. Generate structured patient records
2. Run validation V1–V13
3. Run dataset-level validation checks
4. Generate deterministic SOAP notes
5. Run SOAP audit
6. Run final validation
7. Build retrieval enrichment text
8. Audit retrieval enrichment text
9. Build chunks
10. Build safe metadata
11. Embed chunks
12. Store chunks in ChromaDB
13. Test retrieval quality
14. Serve grounded RAG answers with citations
```

Important rule:

```text
No invalid patient file may reach retrieval enrichment.
```

Retrieval enrichment assumes records have already passed validation and SOAP audit.

---

# 6. Supported Source Types

Retrieval enrichment is source-type aware.

Current supported values are:

```text
doctor_note
lab_result
prescription
allergy
discharge_summary
medication_reconciliation
```

These values must remain aligned with `config/constants.py` and the future chunking/metadata contract.

## Source Type Summary

| Source Type | Requires Visit? | Primary Evidence | Typical RAG Queries |
|---|---:|---|---|
| `doctor_note` | Yes | visit SOAP note + visit context | visit summaries, BP questions, timeline-style questions, emergency visit questions |
| `lab_result` | Yes | visit labs + lab context | HbA1c trends, FBG, creatinine, hemoglobin, ferritin, lab monitoring queries |
| `prescription` | Yes | visit medications + medication timeline context | current medications, medication changes, dose/frequency/start/stop questions |
| `allergy` | No | patient allergy registry | documented allergies, reactions, recorded allergy history |
| `discharge_summary` | Yes | visit SOAP note + visit context | hospitalization summaries, discharge timelines |
| `medication_reconciliation` | Yes | visit SOAP note + visit context | post-hospitalization medication reviews, continuity checks |

---

# 7. Public Interface Contract

The main expected entry point is:

```python
build_retrieval_text(patient: dict, visit: dict | None, source_type: str) -> str
```

Expected behavior:

- `source_type = "doctor_note"` requires `visit`.
- `source_type = "lab_result"` requires `visit`.
- `source_type = "prescription"` requires `visit`.
- `source_type = "allergy"` does not require `visit`.
- `source_type = "discharge_summary"` requires `visit`.
- `source_type = "medication_reconciliation"` requires `visit`.
- Unsupported `source_type` should fail clearly.
- Missing `visit` for visit-level source types should fail clearly.

Auditor entry points:

```python
audit_retrieval_text(
    retrieval_text: str,
    patient: dict,
    visit: dict | None,
    source_type: str,
) -> RetrievalAuditResult
```

Optional batch helper:

```python
audit_retrieval_texts(items: Iterable[RetrievalAuditInput]) -> list[RetrievalAuditResult]
```

Expected audit result fields:

```text
patient_id
visit_id
source_type
passed
issues
```

---

# 8. Source Type Contracts

## 8.1 `doctor_note` Enrichment

Purpose:

```text
Improve retrieval for visit-level narrative questions.
```

The doctor-note enrichment text may include:

- patient ID,
- visit ID,
- visit date,
- visit type,
- documented patient tier,
- documented patient conditions,
- visit diagnoses,
- presence of vital-sign documentation,
- presence of lab documentation,
- presence of medication documentation,
- prior visit reference,
- and SOAP-derived context where applicable.

It must not:

- invent symptoms,
- create a new diagnosis,
- summarize across visits unless the source is explicitly visit-linked,
- add unsupported clinical status words such as `well controlled`, `poorly controlled`, or `deteriorating`,
- or turn BP into metadata-like text.

BP behavior:

```text
BP values may appear in SOAP objective text or doctor-note text.
BP values must not become ChromaDB metadata fields.
```

## 8.2 `lab_result` Enrichment

Purpose:

```text
Improve retrieval for lab trend and monitoring questions.
```

The lab-result enrichment text may include:

- patient ID,
- visit ID,
- visit date,
- visit type,
- documented conditions,
- documented lab types in the visit,
- lab values and flags,
- condition-to-lab context labels,
- and source type context.

Allowed lab types:

```text
HbA1c
FBG
Creatinine
Hemoglobin
Ferritin
LDL
```

Condition-to-lab semantic support:

| Condition Context | Lab Types | Suggested Retrieval Label |
|---|---|---|
| `T2DM` | `HbA1c`, `FBG` | `diabetes-related` |
| `HTN` | `Creatinine` when present in T2DM+HTN context | `hypertension-related` |
| `CKD` | `Creatinine` | `CKD-related` |
| `IDA` | `Hemoglobin`, `Ferritin` | `anemia-related` |
| `Dyslipidemia` | `LDL` | `dyslipidemia-related` |

Creatinine rule:

```text
Creatinine appears for CKD patients or combined T2DM + HTN context.
T2DM-only or HTN-only patients are not required to have Creatinine labs.
```

BP rule:

```text
BP is not a lab type.
BP must not appear in lab_result enrichment as a lab.
```

## 8.3 `prescription` Enrichment

Purpose:

```text
Improve retrieval for medication and medication-timeline questions.
```

The prescription enrichment text may include:

- patient ID,
- visit ID,
- visit date,
- documented conditions,
- medication names,
- medication class,
- dose,
- frequency,
- route,
- start date,
- stop date when documented,
- and medication source context.

Medication timeline rule:

```text
start_date represents the first documented start date of that medication, not necessarily the current visit date.
stop_date remains null unless the medication is documented as stopped.
```

This supports questions such as:

```text
When was Metformin started?
When was Amlodipine added?
Was Ferrous sulfate stopped?
What medication changed over time?
```

The prescription enrichment text must not:

- recommend medication,
- describe what the patient should start,
- infer medication response,
- invent dose changes,
- introduce non-whitelisted medication names,
- or mention medication that is not documented in the visit source context.

## 8.4 `allergy` Enrichment

Purpose:

```text
Improve retrieval for documented allergy history questions.
```

The allergy enrichment text may include:

- patient ID,
- documented allergens,
- reactions,
- severity,
- recorded date,
- source visit ID,
- and clear allergy-history framing.

Correct framing:

```text
Documented allergy history
Recorded allergy information
Allergy registry entry
```

Forbidden framing:

```text
Detected allergy
Predicted allergy
Inferred allergy
Clinical allergy detection
```

Allergy enrichment may be patient-level rather than visit-level because `allergy_registry` belongs to the patient record.

## 8.5 `discharge_summary` Enrichment

Purpose:

```text
Improve retrieval for hospitalization and discharge summaries.
```

The discharge-summary enrichment text may include the same fields as doctor_note, but explicitly flags the event as a major timeline transition (hospitalization).

## 8.6 `medication_reconciliation` Enrichment

Purpose:

```text
Improve retrieval for post-hospitalization medication checks.
```

The medication-reconciliation enrichment text ensures medication changes made during hospitalization are semantically highlighted for continuity queries.

---

# 9. Enrichment Text Safety Rules

Retrieval enrichment text must follow these rules.

## 9.1 Must Be Deterministic

The same patient JSON and source type must produce the same enrichment text every time.

No randomness is allowed.

## 9.2 Must Be Grounded

Every value in enrichment text must come from:

```text
patient JSON
visit object
SOAP note
allergy_registry
```

## 9.3 Must Not Use LLMs

The enrichment layer must not call:

- Groq,
- OpenAI,
- Gemini,
- Claude,
- LangChain agents,
- LangGraph,
- or any external model.

## 9.4 Must Not Mutate Records

The enrichment layer should return text only.

It must not modify:

```text
patient
visit
labs
medications
soap_note
metadata
allergy_registry
```

## 9.5 Must Not Replace Validation

Retrieval enrichment is not a validator for patient JSON.

Validation remains owned by:

```text
validators/rules.py
validators/validate.py
scripts/validate_all.py
```

The enrichment auditor only checks enrichment text safety and source support.

---

# 10. Retrieval Enrichment Auditor Contract

The auditor protects the pipeline from unsafe or unsupported enrichment text.

## 10.1 Audit Severity

Expected severities:

```text
FAIL
WARN
```

Meaning:

| Severity | Meaning | Action |
|---|---|---|
| `FAIL` | Unsafe or unsupported enrichment text | Do not ingest this enrichment text |
| `WARN` | Reviewable issue, usually quality-related | Review before demo or ingestion freeze |

## 10.2 Audit Areas

The auditor should check:

| Area | Purpose |
|---|---|
| Empty text | Prevent blank chunks |
| Source type validity | Ensure only locked source types are used |
| Visit requirement | Ensure visit-level source types have visit context |
| Placeholder leakage | Prevent `{patient_id}` or template markers from entering chunks |
| Unsafe recommendation wording | Prevent treatment recommendation language |
| Unsupported condition mentions | Prevent unsupported condition context |
| Unsupported lab mentions | Prevent lab references not documented in the source context |
| Unsupported medication mentions | Prevent medication names not present in the source context |
| BP metadata-like wording | Prevent BP becoming filter-style metadata |
| Excessive length | Prevent bloated retrieval text |

## 10.3 Duplicate Issue Prevention

The auditor should avoid duplicate issues caused by overlapping phrases.

Example:

```text
diabetes-related
```

should not produce separate unsupported issues for both:

```text
diabetes
diabetes-related
```

The auditor should prefer the longer, more specific phrase.

## 10.4 Batch Audit Support

Batch audit support is useful for chunking and ingestion.

Expected pattern:

```python
items = [
    RetrievalAuditInput(
        retrieval_text=text,
        patient=patient,
        visit=visit,
        source_type=source_type,
    )
]

results = audit_retrieval_texts(items)
```

Batch auditing must not short-circuit. Every item should be audited and returned in original order.

---

# 11. Relationship to Chunking

Retrieval enrichment does not replace chunking.

It supplies additional deterministic text that the chunker may include when building chunk bodies.

The chunker remains responsible for:

- chunk boundaries,
- chunk IDs,
- final chunk text assembly,
- source type assignment,
- metadata construction,
- and handoff to embedding/ingestion.

Recommended chunk construction pattern:

```text
primary evidence text
+ deterministic retrieval enrichment text
= final chunk text
```

Example:

```text
SOAP objective text
+ doctor_note enrichment context
= doctor_note chunk text
```

---

# 12. Relationship to Metadata

Retrieval enrichment text is not metadata.

Metadata should be built separately from stable schema fields.

Allowed metadata examples:

```text
patient_id
visit_id
visit_date
visit_type
source_type
conditions
tier
```

Forbidden metadata examples:

```text
bp_systolic
bp_diastolic
full_labs
full_medications
full_soap
retrieval_enrichment_text
ai_answer
risk_score
diagnosis_confidence
```

BP rule:

```text
BP may be present in chunk text through SOAP objective or doctor-note text.
BP must never be stored in ChromaDB metadata.
```

---

# 13. Relationship to RAG Retrieval

Retrieval enrichment improves semantic matching.

It helps the retriever find correct chunks for queries such as:

```text
What medications does this patient take?
When was Amlodipine added?
How has HbA1c changed over time?
Does the patient have a documented allergy?
What happened during the emergency visit?
What was the patient's blood pressure at the last visit?
```

Expected retrieval behavior:

| Query Type | Preferred Source Type |
|---|---|
| Medication history | `prescription` |
| Lab trend | `lab_result` |
| Allergy history | `allergy` |
| Visit narrative | `doctor_note` |
| BP question | `doctor_note` |
| Emergency/hospitalization question | `doctor_note` |

---

# 14. Relationship to Grounded Answer Generation

The answer generator may receive chunks that include enrichment text.

However, the LLM should still answer only from retrieved evidence.

The prompt builder should treat enrichment text as retrieval-supporting context, not as a separate clinical authority.

Recommended prompt framing:

```text
Use the retrieved patient record evidence below. Do not add diagnoses, treatment recommendations, or unsupported conclusions. If the retrieved records do not contain the answer, say that the available records do not contain enough documented evidence.
```

---

# 15. Handoff Responsibilities

## 15.1 Ahmed Hesham Kamel Provides

Ahmed provides:

- validated patient JSON records,
- deterministic SOAP notes,
- validation reports,
- data schema contract,
- retrieval enrichment implementation,
- retrieval enrichment auditor,
- source type definitions,
- and examples from `scripts/check_retrieval_enricher_output.py`.

## 15.2 Gamal Mohamed Gad Uses

Gamal uses this layer to:

- build stronger chunk text,
- improve retrieval quality,
- audit enrichment before ingestion,
- design chunking and metadata behavior,
- test expected source type retrieval,
- and preserve grounding/citation correctness.

## 15.3 Gamal Must Not

Gamal must not:

- alter patient schema without Ahmed approval,
- ingest quarantined records,
- treat enrichment text as source truth,
- put BP values in metadata,
- add unapproved source types,
- bypass enrichment audit if enrichment text is used,
- or allow unsupported medical claims into final RAG answers.

---

# 16. Implementation Examples

## 16.1 Example `lab_result` Enrichment

```text
Laboratory retrieval context for patient PAT-MOD-001 and visit VST-MOD-001-003 on 2023-05-10 during a follow_up visit. Documented lab types in this visit include HbA1c, FBG, and Creatinine. Documented T2DM context allows HbA1c and FBG to be described as diabetes-related laboratory entries. Documented HTN context allows Creatinine to be described as hypertension-related monitoring when present.
```

## 16.2 Example `prescription` Enrichment

```text
Prescription retrieval context for patient PAT-CHR-002 and visit VST-CHR-002-004 on 2022-04-15. Documented medications in this visit include Metformin dose 500 mg frequency twice_daily route oral start date 2021-01-15; Amlodipine dose 5 mg frequency once_daily route oral start date 2021-10-12.
```

## 16.3 Example `allergy` Enrichment

```text
Allergy retrieval context for patient PAT-MOD-004. The allergy registry documents Penicillin with reaction rash, severity moderate, recorded date 2023-03-12, source visit VST-MOD-004-002.
```

## 16.4 Example `doctor_note` Enrichment

```text
Doctor-note retrieval context for patient PAT-CHR-003 and visit VST-CHR-003-006 on 2022-09-15. Documented patient tier is chronic. Documented patient conditions include T2DM, HTN, and CKD. Visit diagnoses include T2DM and HTN. The visit contains vital-sign documentation, laboratory entries, medication entries, and a prior visit reference.
```

---

# 17. Required Test Commands

After updating enrichment logic:

```bash
python -m py_compile ingestion/retrieval_enricher.py
python -m py_compile ingestion/retrieval_enrichment_auditor.py
```

To inspect one patient and visit:

```bash
python scripts/check_retrieval_enricher_output.py --patient-id PAT-MOD-001 --visit-index 0
```

To inspect selected source types:

```bash
python scripts/check_retrieval_enricher_output.py \
  --patient-id PAT-MOD-001 \
  --visit-index 0 \
  --source-type doctor_note \
  --source-type lab_result \
  --source-type prescription
```

Expected result:

```text
No unsupported medical claims.
No unsupported medication mentions.
No BP metadata-like wording.
No invalid source_type.
No placeholders.
```

---

# 18. Acceptance Criteria

The retrieval enrichment layer is acceptable when:

- all enrichment functions are deterministic,
- no LLM calls exist,
- no patient JSON mutation occurs,
- all source types are locked and supported,
- visit-level source types fail clearly without visit context,
- allergy source type works at patient level,
- lab enrichment includes relevant lab and condition context,
- prescription enrichment includes medication timeline fields,
- HTN + Creatinine context is handled safely,
- enrichment audit returns zero FAIL issues on generated approved patient records,
- BP is never treated as lab or metadata,
- and chunking can consume enrichment text without guessing schema.

---

# 19. Final Handoff Checklist

Before Gamal uses retrieval enrichment in chunking or ingestion:

```text
[ ] data/patients/ contains only validated patient files
[ ] data/quarantine/ is not used by ingestion
[ ] python scripts/validate_all.py --mode full passes
[ ] deterministic SOAP notes exist for all visits
[ ] SOAP audit has no FAIL issues
[ ] retrieval_enricher.py compiles
[ ] retrieval_enrichment_auditor.py compiles
[ ] check_retrieval_enricher_output.py works on showcase patients
[ ] enrichment audit returns no FAIL issues on approved data
[ ] source_type values match config/constants.py
[ ] BP is absent from metadata design
[ ] chunking contract is aligned with this document
```

---

# 20. Final Contract Summary

Retrieval enrichment is a deterministic bridge between structured patient records and high-quality semantic retrieval.

It exists because vector retrieval works better when structured facts are expressed as clear, source-aware text.

The layer must remain:

```text
deterministic
safe
audited
schema-aware
source-type-aware
non-mutating
non-diagnostic
non-prescriptive
```

Ahmed owns the validity and meaning of the enriched source text.

Gamal may use that text to improve chunking and retrieval, but must preserve grounding, citations, patient scoping, metadata safety, and the rule that no generated answer may exceed retrieved documented evidence.

The contract boundary is simple:

```text
Validated data + deterministic SOAP
        ↓
Retrieval enrichment + enrichment audit
        ↓
Chunking + safe metadata
        ↓
ChromaDB ingestion
        ↓
Patient-scoped grounded RAG
```

This document is the official handoff reference for the retrieval enrichment layer.
