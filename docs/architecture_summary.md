# Architecture Summary

**Project:** AI-Based Clinical Record Summarization System  
**Project Type:** Academic Retrieval-Augmented Generation (RAG) system  
**Target Use:** DEPI graduation evaluation, GitHub portfolio presentation, and team handoff  
**Architecture Status:** Local-first, modular, validation-gated, demo-oriented  
**Data Scope:** Synthetic clinical records only  
**Primary Goal:** Retrieve, summarize, and cite documented synthetic patient records safely

---

## 1. Executive Summary

The **AI-Based Clinical Record Summarization System** is an academic AI engineering project that demonstrates a safe Retrieval-Augmented Generation workflow for synthetic clinical records.

The system allows a user to select a synthetic patient, ask a natural-language question, retrieve relevant evidence from that patient's records, generate a grounded answer, and display citations pointing back to the supporting record chunks.

The architecture is intentionally **simple, modular, local-first, and validation-gated**. It is designed for a small student team where every layer has a clear owner and every file has a bounded responsibility.

This system does **not** diagnose, prescribe, recommend treatment, predict disease, infer undocumented conditions, use real patient data, or connect to real hospital infrastructure. It only retrieves and summarizes information already documented in synthetic records.

---

## 2. System Goals

The system is designed to demonstrate the following capabilities:

1. Generate deterministic synthetic patient records.
2. Validate all patient data using explicit rules before ingestion.
3. Generate deterministic SOAP notes from structured JSON facts.
4. Enrich retrieval text without changing the source of truth.
5. Convert validated patient records into RAG-ready chunks.
6. Store embedded chunks in a local ChromaDB vector database.
7. Retrieve evidence using patient-scoped semantic search.
8. Generate grounded answers using retrieved chunks only.
9. Display citations for transparency.
10. Provide a simple FastAPI backend and Streamlit frontend.
11. Remain reproducible for local academic demo execution.


---

## 3. Non-Goals

The project must not expand into a clinical decision-support system.

The system must not:

- diagnose patients,
- recommend medications,
- prescribe treatment,
- predict clinical outcomes,
- infer undocumented conditions,
- use real patient data,
- connect to real hospital systems,
- provide emergency or clinical advice,
- replace medical judgment,
- introduce Kubernetes, microservices, Redis, Celery, PostgreSQL, LangGraph, or agent orchestration.

This is an academic RAG demonstration using synthetic records only.

---

## 4. High-Level Architecture

```text
Synthetic Patient Generation
        ↓
Validation V1–V13
        ↓
Deterministic SOAP Generation
        ↓
SOAP Audit
        ↓
Final Validation
        ↓
Retrieval Enrichment
        ↓
Chunking and Metadata Construction
        ↓
Embedding
        ↓
ChromaDB Ingestion
        ↓
Patient-Scoped Retrieval
        ↓
Grounded Prompt Construction
        ↓
Groq LLM Answer Generation
        ↓
Citation Formatting
        ↓
FastAPI Backend
        ↓
Streamlit Frontend
        ↓
Offline Demo Execution
```

The architecture separates **data truth**, **retrieval support**, **RAG reasoning**, and **user interface** into independent layers.

---

## 5. Core Architectural Principle

The project follows one central rule:

```text
Structured patient JSON and validated SOAP notes are the source of truth.
Everything else supports retrieval, presentation, or answer generation.
```

This means:

- Generators create structured facts.
- Validators decide whether records are allowed to proceed.
- SOAP notes describe structured facts only.
- Retrieval enrichment improves semantic matching but does not create new facts.
- Chunks store retrievable evidence.
- RAG answers must be grounded in retrieved evidence.
- Citations must point back to the supporting record chunks.

---

## 6. Technology Stack

| Layer | Technology | Purpose |
|---|---|---|
| Language | Python | Main implementation language |
| Structured data | Local JSON files | Portable synthetic patient records |
| Validation | Plain Python | Explicit V1–V13 rule checks |
| SOAP generation | Deterministic templates | Safe note generation from structured facts |
| Retrieval enrichment | Python text builders | Improve semantic retrieval quality |
| Embeddings | Sentence Transformers | Local vector embedding generation |
| Vector database | ChromaDB | Local persistent semantic search |
| Backend | FastAPI | API endpoints and orchestration |
| Frontend | Streamlit | Interactive academic demo UI |
| Answer LLM | Groq API | Grounded answer generation from retrieved chunks |
| Deployment | Docker / Docker Compose | Reproducible local demo execution |

---

## 7. Repository-Level Architecture

```text
AI-Based-Clinical-Record-Summarization-System/
├── backend/        # FastAPI backend and API orchestration
├── config/         # Constants, paths, settings, prompts, showcase config
├── data/           # Patient JSON, schema, quarantine, ChromaDB runtime output
├── deployment/     # Docker and Docker Compose files
├── docs/           # Engineering documentation and handoff contracts
├── frontend/       # Streamlit demo interface
├── generators/     # Deterministic synthetic patient generation
├── ingestion/      # Retrieval enrichment, chunking, metadata, ingestion
├── logs/           # Validation and runtime logs
├── rag/            # Retrieval, prompts, grounding, citations, answer generation
├── scripts/        # Pipeline workflow scripts
├── soap/           # Deterministic SOAP templates, rendering, audit
├── tests/          # Validation, retrieval, chunking, API, smoke tests
├── validators/     # V1–V13 validation rules and reports
├── requirements.txt
└── README.md
```

Each folder owns one bounded responsibility. Cross-folder imports should follow the architecture flow rather than bypassing earlier gates.

---

## 8. Source of Truth Hierarchy

The project uses the following truth hierarchy:

| Priority | Source | Role |
|---|---|---|
| 1 | `config/constants.py` | Locked enums, whitelist, IDs, project constants |
| 2 | `data/schemas/patient_schema.json` | Formal patient JSON structure |
| 3 | `data/patients/*.json` | Approved validated patient records |
| 4 | `visit.soap_note` | Deterministic narrative generated from structured facts |
| 5 | Retrieval enrichment text | Search support text only |
| 6 | ChromaDB chunks | Searchable evidence units |
| 7 | LLM answer | Generated summary from retrieved evidence |

The LLM answer is never treated as a source of truth.

---

## 9. Data Engineering Layer

### 9.1 Purpose

The data engineering layer generates and validates the synthetic clinical dataset before RAG ingestion.

### 9.2 Main Folders

```text
config/
generators/
validators/
soap/
data/
scripts/
```

### 9.3 Responsibilities

The data engineering layer owns:

- locked constants,
- patient schema,
- deterministic patient generation,
- deterministic visit generation,
- deterministic lab generation,
- deterministic medication generation,
- deterministic allergy registry generation,
- validation rules V1–V13,
- deterministic SOAP generation,
- SOAP auditing,
- approved patient files,
- quarantine handling,
- data pipeline scripts.

### 9.4 Data Pipeline

```text
patient shells
→ visits
→ medications
→ labs
→ allergies
→ structured validation
→ deterministic SOAP generation
→ SOAP audit
→ final validation
→ approved export to data/patients
→ invalid export to data/quarantine
```

Important rule:

```text
Validation is the hard gate before SOAP generation and ingestion.
```

---

## 10. Dataset Design

### 10.1 Dataset Modes

| Mode | Count | Purpose |
|---|---:|---|
| `pilot` | 5 patients | Fast development and smoke testing |
| `full` | 15 patients | Final dataset for RAG and demo |

### 10.2 Full Dataset Distribution

| Tier | Count | Meaning |
|---|---:|---|
| `normal` | 1 | Simple or acute records with no chronic condition profile |
| `moderate` | 9 | Managed condition profiles |
| `chronic` | 5 | Multi-visit chronic profiles with longer timelines |

### 10.3 Locked Conditions

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

### 10.4 CKD Rule

CKD is not a standalone archetype.

```text
CKD is allowed only in chronic-tier patients.
CKD must co-occur with both T2DM and HTN.
CKD is limited to at most 2 patients in the locked full dataset.
```

### 10.5 Lab Types

```text
HbA1c
FBG
Creatinine
Hemoglobin
Ferritin
LDL
```

Creatinine is generated for:

```text
CKD patients
or
patients with combined T2DM + HTN context
```

T2DM-only or HTN-only patients are not required to have Creatinine labs.

---

## 11. Blood Pressure Rule

Blood pressure has one authoritative location:

```json
"vitals": {
  "bp_systolic": 120,
  "bp_diastolic": 80
}
```

BP must never appear in:

```text
visit.labs[]
lab_type enum
ChromaDB metadata
standalone metadata fields
duplicate shadow fields
```

BP-related questions should retrieve `doctor_note` chunks because BP appears in SOAP objective text, not in ChromaDB metadata.

---

## 12. Validation Layer

### 12.1 Purpose

The validation layer protects data quality and prevents invalid records from entering SOAP generation, retrieval enrichment, chunking, or ingestion.

### 12.2 Validation Rules

| Rule | Purpose | Severity |
|---|---|---|
| V1 | Chronological visit order | FAIL |
| V2 | Medication/allergy conflict prevention | FAIL |
| V3 | Impossible vitals and age bounds | FAIL |
| V4 | Required fields and forbidden `demographics.age` | WARN/FAIL |
| V5 | `prior_visit_id` and allergy `source_visit_id` integrity | WARN |
| V6 | Duplicate `visit_id` prevention | FAIL |
| V7 | Enum validation, ID pattern validation, CKD constraints | FAIL |
| V8 | Date format validation | FAIL |
| V9 | BP forbidden inside labs | FAIL |
| V10 | `timeline_events` forbidden | FAIL |
| V11 | Medication whitelist, frequency, and route validation | FAIL |
| V12 | Dataset diversity fingerprint and retrieval signature validation | FAIL/WARN |
| V13 | Embedding similarity report helper | REPORT |

### 12.3 Dataset-Level Checks

`scripts/validate_all.py` also checks:

- expected patient count for selected mode,
- expected tier distribution,
- duplicate `patient_id` values across files,
- CKD patient count limit.

These checks do not replace V1–V13. They protect dataset-level integrity.

---

## 13. SOAP Layer

### 13.1 Purpose

The SOAP layer converts structured patient facts into readable visit notes.

### 13.2 Current Implementation

The current SOAP implementation is:

```text
deterministic
template-based
offline
non-random
grounded in structured JSON
```

It does not call an LLM in the current implementation.

### 13.3 SOAP Flow

```text
Validated patient JSON
        ↓
SOAP fact context
        ↓
Deterministic template selection
        ↓
Template rendering
        ↓
SOAP note sections
        ↓
SOAP safety checks
        ↓
SOAP audit
```

### 13.4 SOAP Rules

SOAP generation must not:

- mutate structured patient facts,
- infer diagnoses,
- select medications,
- select lab values,
- modify vitals,
- add unsupported claims,
- make treatment recommendations,
- generate unsupported clinical interpretation.

SOAP notes exist to create readable narrative evidence for `doctor_note` chunks.

---

## 14. Retrieval Enrichment Layer

### 14.1 Purpose

The retrieval enrichment layer improves semantic retrieval quality by producing deterministic support text derived from structured patient facts.

Relevant files:

```text
ingestion/retrieval_enricher.py
ingestion/retrieval_enrichment_auditor.py
```

### 14.2 Supported Source Types

```text
doctor_note
lab_result
prescription
allergy
discharge_summary
medication_reconciliation
```

### 14.3 Rules

Retrieval enrichment text:

- is not the source of truth,
- must be deterministic,
- must not call an LLM,
- must not invent medical facts,
- must not change patient JSON,
- must not build embeddings,
- must not write ChromaDB records,
- must be audited before ingestion use.

### 14.4 Why It Exists

SOAP templates are safe and deterministic, but deterministic wording can reduce semantic variety. Retrieval enrichment adds grounded context phrases to help semantic search match user queries more reliably.

Examples:

- diabetes-related lab context,
- hypertension-related Creatinine context,
- medication timeline start dates,
- allergy registry summary,
- prior visit reference context.

---

## 15. Ingestion Layer

### 15.1 Purpose

The ingestion layer converts validated patient records into ChromaDB-ready chunks.

### 15.2 Expected Components

```text
ingestion/retrieval_enricher.py
ingestion/retrieval_enrichment_auditor.py
ingestion/chunker.py
ingestion/metadata_builder.py
ingestion/ingest.py
```

### 15.3 Ingestion Flow

```text
Validated patient JSON
        ↓
Visit-level evidence extraction
        ↓
Retrieval enrichment text generation
        ↓
Enrichment audit
        ↓
Chunk construction
        ↓
Metadata construction
        ↓
Embedding generation
        ↓
ChromaDB upsert
```

### 15.4 Ingestion Rules

- Ingestion must read only from `data/patients/`.
- Ingestion must never read from `data/quarantine/`.
- Ingestion must only run after validation passes.
- Metadata must be safe and filterable.
- BP must not be stored in metadata.
- Chunk text may contain BP through SOAP objective text.
- Chunks must preserve patient and visit traceability.

---

## 16. Chunking Architecture

### 16.1 Chunk Types

| Source Type | Meaning | Expected Evidence |
|---|---|---|
| `doctor_note` | Visit narrative | SOAP note text and visit context |
| `lab_result` | Visit lab evidence | Lab names, values, flags, units, dates |
| `prescription` | Visit medication evidence | Medication names, doses, routes, frequencies, start/stop dates |
| `allergy` | Patient allergy evidence | Allergy registry records and source visit references |
| `discharge_summary` | Hospitalization narrative | Hospitalization summaries, discharge timelines |
| `medication_reconciliation` | Transition of care medications | Post-hospitalization medication reviews, continuity checks |

### 16.2 Chunking Rules

- Chunks should be patient-scoped.
- Chunks should retain `patient_id`.
- Visit chunks should retain `visit_id` and `visit_date`.
- Allergy chunks may be patient-level.
- Chunks should not merge unrelated patients.
- Cross-visit aggregation should be avoided unless explicitly designed.
- Chunk IDs should be deterministic.

### 16.3 Minimum Metadata

Recommended metadata fields:

```text
patient_id
visit_id
visit_date
source_type
visit_type
conditions
document_id or linked_documents
```

Forbidden metadata fields:

```text
bp_systolic
bp_diastolic
blood_pressure
raw BP values
unsupported clinical interpretations
```

---

## 17. RAG Layer

### 17.1 Purpose

The RAG layer retrieves relevant chunks, builds a grounded prompt, calls the answer LLM, and returns a cited response.

### 17.2 Expected Components

```text
rag/retriever.py
rag/prompt_builder.py
rag/llm_client.py
rag/answer_generator.py
rag/citations.py
rag/grounding.py
rag/query_models.py
```

### 17.3 RAG Flow

```text
User question
        ↓
Patient selection / patient_id filter
        ↓
ChromaDB semantic retrieval
        ↓
Top-k chunk selection
        ↓
Grounding check
        ↓
Prompt construction
        ↓
Groq answer generation
        ↓
Citation formatting
        ↓
Structured API response
```

### 17.4 Grounding Rule

```text
No retrieved evidence = no generated medical answer.
```

If retrieved chunks do not support the question, the system should say that the available records do not contain enough documented evidence.

### 17.5 Query Routing Expectations

| Query Type | Preferred Source Type |
|---|---|
| Medication questions | `prescription` |
| Lab trend questions | `lab_result` |
| Allergy questions | `allergy` |
| Visit summary questions | `doctor_note` |
| BP questions | `doctor_note` |
| Timeline questions | `doctor_note` + visit metadata |

---

## 18. Backend Layer

### 18.1 Purpose

The backend exposes the RAG system through stable API endpoints.

### 18.2 Expected Endpoints

```text
GET  /health
GET  /patients
POST /query
GET  /timeline/{patient_id}
GET  /summary/{patient_id}
```

### 18.3 Backend Rules

The backend should:

- validate requests,
- call RAG services,
- return structured responses,
- include citations,
- expose timeline and summary endpoints,
- avoid duplicating RAG logic,
- avoid direct frontend-specific formatting.

The backend should not:

- generate patient data,
- run validation rules as business logic,
- directly modify patient JSON during query handling,
- bypass the RAG layer,
- perform frontend rendering.

---

## 19. Frontend Layer

### 19.1 Purpose

The frontend provides a simple demo interface for DEPI evaluation.

### 19.2 Expected UI Areas

```text
Patient selector
Query tab
Timeline tab
Allergy history tab
Citation display
```

### 19.3 Frontend Rules

The frontend should:

- call backend APIs only,
- display grounded answers,
- display citations clearly,
- show patient timeline information,
- show documented allergy records,

The frontend should not:

- call ChromaDB directly,
- call Groq directly,
- run validators,
- generate data,
- bypass backend contracts.

---

## 20. Script Workflow

### 20.1 Full Dataset Pipeline

```bash
python scripts/generate_all.py --mode full --clean
python scripts/validate_all.py --mode full
python scripts/generate_soap.py --dry-run
python scripts/generate_soap.py
python scripts/validate_all.py --mode full
python scripts/reset_chromadb.py
python scripts/ingest_all.py
python tests/test_retrieval.py
```

### 20.2 Pilot Pipeline

```bash
python scripts/generate_all.py --mode pilot --clean
python scripts/validate_all.py --mode pilot
python scripts/generate_soap.py --dry-run
python scripts/generate_soap.py
python scripts/validate_all.py --mode pilot
```

### 20.3 Retrieval Enrichment Debug

```bash
python scripts/check_retrieval_enricher_output.py --patient-id PAT-MOD-001 --visit-index 0
```

---

## 21. Development Order

The project should be developed in dependency order:

```text
1. Lock constants and schema
2. Implement validation rules V1–V13
3. Generate pilot dataset
4. Validate pilot dataset
5. Generate full dataset
6. Validate full dataset
7. Generate deterministic SOAP notes
8. Audit SOAP notes
9. Validate again
10. Build retrieval enrichment, chunking, and metadata
11. Ingest into ChromaDB
12. Test retrieval quality
13. Build FastAPI backend
14. Test API endpoints
15. Build Streamlit frontend
16. Integrate frontend with backend
17. Build Docker workflow
18. Run smoke tests
19. Prepare demo script
20. Rehearse final demo
```

Important rule:

```text
Do not build or polish the frontend before retrieval works.
```

---

## 22. Team Ownership Map

| Area | Primary Owner | Notes |
|---|---|---|
| `config/` | Ahmed Hesham Kamel | Constants, paths, settings, showcase config |
| `data/` | Ahmed Hesham Kamel | Patient JSON, schema, quarantine; not ChromaDB runtime ownership |
| `generators/` | Ahmed Hesham Kamel | Deterministic synthetic data generation |
| `validators/` | Ahmed Hesham Kamel | V1–V13 validation rules and reports |
| `soap/` | Ahmed Hesham Kamel | Deterministic SOAP generation and audit |
| `docs/` | Ahmed Hesham Kamel + team input | Architecture, contracts, handoff docs |
| `ingestion/` | Gamal Mohamed Gad | Chunking, metadata, enrichment integration, ChromaDB ingestion |
| `rag/` | Gamal Mohamed Gad | Retrieval, grounding, prompts, citations, answer generation |
| `backend/` | Youssef Yassin Ibrahim | API routing and orchestration |
| `frontend/` | Youssef Yassin Ibrahim | Streamlit demo UI |
| `deployment/` | Mahmoud Mohamed El Faham | Docker and local demo reproducibility |
| `tests/` | Mahmoud Mohamed El Faham + all members | Validation, retrieval, API, smoke tests |

---

## 23. Cross-Team Dependency Map

```text
Ahmed Hesham Kamel
        ↓
Gamal Mohamed Gad
        ↓
Youssef Yassin Ibrahim
        ↓
Mahmoud Mohamed El Faham
        ↓
Final Demo
```

### Ahmed Hesham Kamel → Gamal Mohamed Gad

Ahmed provides:

* stable schema,
* valid patient JSON records,
* constants and locked enums,
* deterministic SOAP notes,
* validation reports,
* retrieval enrichment contract,
* showcase patient configuration.

Gamal must not ingest invalid or quarantined records.

### Gamal Mohamed Gad → Youssef Yassin Ibrahim

Gamal provides:

* working ChromaDB collection,
* retriever interface,
* prompt builder,
* answer generator,
* citation formatter,
* retrieval test results.

Youssef should integrate backend APIs with the RAG layer rather than duplicating retrieval logic.

### Youssef Yassin Ibrahim → Mahmoud Mohamed El Faham

Youssef provides:

* stable API endpoints,
* request and response schemas,
* answer and citation response shapes,
* timeline and summary responses,
* runnable Streamlit frontend,
* frontend-backend integration.

### Mahmoud Mohamed El Faham → Final Demo

Mahmoud provides:

* Docker workflow,
* local reproducibility,
* smoke testing,
* environment setup validation,
* demo readiness verification.

```

---

## 24. Safety Rules

The system must always follow these safety rules:

1. Use synthetic data only.
2. Never diagnose.
3. Never recommend treatment.
4. Never prescribe medication.
5. Never predict disease.
6. Never infer undocumented conditions.
7. Never use real patient data.
8. Never answer without retrieved evidence.
9. Always show citations for generated answers.
10. Keep BP out of labs and metadata.
11. Keep validation as the hard gate before ingestion.
12. Keep RAG answers grounded in retrieved chunks.

---

## 25. Demo Architecture

### 25.1 Demo Flow

```text
Start backend
Start frontend
Select showcase patient
Ask grounded RAG question
Show answer and citations
Open timeline tab
Show chronological visit history
Ask allergy question
Show documented allergy retrieval
Open patient summary tab
Show grounded patient summary
Demonstrate citation transparency
```

### 25.2 Demo Stability Rules

* Use showcase patients only.
* Use rehearsed queries.
* Warm up ChromaDB with test queries.
* Keep fallback screenshots ready.
* Do not introduce untested features during demo.


---

## 26. Architecture Change Policy

Architecture changes must be avoided unless they fix a clear bug or blocked integration.

Allowed changes:

- small bug fixes,
- clearer error handling,
- documentation updates,
- validation-safe improvements,
- retrieval quality improvements within current architecture.

Forbidden changes:

- new database architecture,
- microservices,
- cloud deployment redesign,
- Kubernetes,
- Redis/Celery workflows,
- LangGraph or agent orchestration,
- medical inference features,
- schema changes without Ahmed approval.

---

## 27. Final Architecture Summary

The final system is a **local-first academic RAG architecture** built around deterministic synthetic data generation, strict validation, grounded retrieval, and cited answer generation.

The most important architectural decisions are:

```text
Structured JSON is the source of truth.
Validation is the hard gate.
SOAP is deterministic and grounded.
Retrieval enrichment improves search but does not create facts.
ChromaDB stores chunks and safe metadata.
RAG answers must cite retrieved evidence.
The frontend is a demo layer, not a logic layer.
```

This architecture is intentionally scoped for a DEPI graduation project: strong enough to demonstrate real AI engineering discipline, simple enough for a small team to build, test, explain, and defend.

---

## 28. Related Documentation

| Document | Purpose |
|---|---|
| `README.md` | Project overview and quick start |
| `docs/team_ownership_and_architecture.md` | Team ownership and folder responsibilities |
| `docs/project_scope_and_safety_rules.md` | Medical safety and scope boundaries |
| `docs/data_schema_contract.md` | Patient JSON schema handoff contract |
| `docs/validation_rules.md` | Validation rules V1–V13 and dataset checks |
| `docs/data_generation_pipeline.md` | Data generation and validation workflow |
| `docs/rag_handoff_contract.md` | Data-to-RAG handoff for AI/RAG engineer |
| `docs/retrieval_enrichment_contract.md` | Retrieval enrichment layer contract |
| `docs/chunking_and_metadata_contract.md` | Chunk and metadata rules |
| `docs/rag_pipeline.md` | End-to-end RAG pipeline |
| `docs/api_contract.md` | API request/response contract |
| `docs/demo_script.md` | Final demo script |
| `docs/fallback_plan.md` | Demo fallback and recovery plan |
| `docs/llm_project_context.md` | Compact context file for team LLM tools |

---

## 29. Quick Reference Commands

```bash
# Generate full dataset
python scripts/generate_all.py --mode full --clean

# Validate full dataset
python scripts/validate_all.py --mode full

# Dry-run SOAP generation
python scripts/generate_soap.py --dry-run

# Generate SOAP notes
python scripts/generate_soap.py

# Validate again
python scripts/validate_all.py --mode full

# Debug retrieval enrichment
python scripts/check_retrieval_enricher_output.py --patient-id PAT-MOD-001 --visit-index 0

# Reset and ingest vector store
python scripts/reset_chromadb.py
python scripts/ingest_all.py

# Run retrieval tests
python tests/test_retrieval.py

# Start backend
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000

# Start frontend
streamlit run frontend/app.py
```
