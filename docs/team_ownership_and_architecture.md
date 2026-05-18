# AI-Based Clinical Record Summarization System

## Team Ownership and Architecture Documentation

**Document Path:** `docs/team_ownership_and_architecture.md`  
**Project Type:** Academic AI Engineering RAG System  
**Primary Goal:** Safe retrieval, summarization, and citation of synthetic clinical records  
**Target Use:** DEPI graduation evaluation, GitHub portfolio presentation, team handoff, and LLM project context  
**Status:** Final Team Ownership and Architecture Reference  
**Architecture Mode:** Local-first academic RAG demo using synthetic records only

---

# 1. Executive Architecture Overview

The **AI-Based Clinical Record Summarization System** is an academic Retrieval-Augmented Generation system designed to retrieve, summarize, and cite **synthetic clinical records** safely.

The system uses:

- FastAPI for backend APIs
- Streamlit for the frontend demo interface
- ChromaDB for local vector storage
- Sentence-transformers for local embeddings
- Groq API for grounded RAG answer generation
- Google Vision OCR with offline cache
- Synthetic JSON medical records
- Docker and Docker Compose for reproducible local execution

The architecture is intentionally modular but not overengineered. It is designed for a small academic engineering team where each member has clear ownership boundaries.

The system follows this final workflow:

```text
Synthetic Structured Data Generation
        ↓
Structured Validation V1–V11
        ↓
Dataset-Level Validation Checks
        ↓
Deterministic SOAP Generation
        ↓
SOAP Safety Audit
        ↓
Final Validation Gate
        ↓
Retrieval Enrichment
        ↓
Retrieval Enrichment Audit
        ↓
Chunking and Metadata Construction
        ↓
Embedding and ChromaDB Ingestion
        ↓
RAG Retrieval
        ↓
Grounded Answer Generation
        ↓
FastAPI Backend
        ↓
Streamlit Frontend
        ↓
Offline Demo Execution
```

The system must only retrieve and summarize documented synthetic records. It must not diagnose, recommend treatment, predict disease, infer undocumented medical conditions, use real patient data, or connect to real hospital systems.

---

# 2. Locked Engineering Rules

The following rules are mandatory and must not be changed during implementation.

| Rule | Requirement |
|---|---|
| Validation | V1–V11 validation rules must be implemented and enforced |
| Dataset checks | Full dataset must pass count, tier distribution, unique patient ID, and CKD count checks |
| Validation gate | Structured validation must pass before SOAP, enrichment, chunking, or ingestion |
| Blood Pressure | BP exists only inside `visit.vitals` |
| BP in labs | BP must never appear in labs |
| BP in metadata | BP must never appear in ChromaDB metadata |
| CKD | CKD is complication-only: chronic tier only, requires both T2DM and HTN, max 2 patients |
| Routes | Medication route enum is locked to `oral` and `inhaled` only |
| Generators | Data generators are deterministic and must not call an LLM |
| SOAP | SOAP notes are deterministic template-based text generated from structured JSON only |
| SOAP LLM usage | No LLM is used during SOAP generation in the current implementation |
| RAG LLM usage | The LLM is used later only for grounded answer generation from retrieved evidence |
| Retrieval enrichment | Enrichment text is deterministic support text, not source truth |
| RAG priority | Retrieval quality is the highest engineering priority |
| OCR demo | OCR demo must use offline cached OCR during presentation |
| Answers | All answers must be grounded and citation-based |
| Deployment | Docker must remain simple and local-first |
| Architecture | No Kubernetes, no microservices, no PostgreSQL primary database |
| AI orchestration | No LangGraph or agent orchestration |
| Medical safety | No diagnosis, treatment recommendation, prediction, or undocumented inference |

---

# 3. Final Repository Structure

```text
AI-Based-Clinical-Record-Summarization-System/
│
├── backend/
├── config/
├── data/
├── deployment/
├── docs/
├── frontend/
├── generators/
├── ingestion/
├── logs/
├── ocr/
├── rag/
├── scripts/
├── soap/
├── tests/
├── validators/
│
├── .dockerignore
├── .env.example
├── .gitignore
├── LICENSE
├── README.md
└── requirements.txt
```

This structure separates the project into clear engineering areas:

| Area | Purpose |
|---|---|
| `backend/` | FastAPI backend and API orchestration |
| `frontend/` | Streamlit user interface |
| `rag/` | Retrieval, prompt construction, grounding, citations, and answer generation |
| `ingestion/` | Retrieval enrichment, chunking, metadata construction, and ChromaDB ingestion |
| `generators/` | Deterministic synthetic structured patient data generation |
| `validators/` | V1–V11 validation rules and validation reporting |
| `soap/` | Deterministic SOAP generation and SOAP safety auditing |
| `ocr/` | Google Vision OCR, OCR cache, and offline OCR loading |
| `data/` | Synthetic patient JSON, schema files, quarantine, and ChromaDB storage |
| `config/` | Constants, paths, prompts, settings, and showcase patient configuration |
| `scripts/` | Pipeline automation scripts |
| `deployment/` | Docker and Docker Compose files |
| `tests/` | Validation, retrieval, API, and integration tests |
| `logs/` | Pipeline and runtime logs |
| `docs/` | Architecture, API, demo, fallback, data, validation, and ownership documentation |

---

# 4. Folder-by-Folder Responsibilities

## 4.1 `backend/`

Recommended internal structure:

```text
backend/
├── README.md
└── app/
    ├── __init__.py
    ├── health.py
    ├── main.py
    ├── routes.py
    ├── schemas.py
    └── services.py
```

Purpose:

- Expose API endpoints
- Receive frontend requests
- Validate request and response models
- Call the RAG pipeline
- Return structured answers, citations, timelines, and summaries

The backend must remain lightweight. It should orchestrate system components but must not contain chunking logic, validation rules, embedding logic, data generation logic, or frontend UI logic.

---

## 4.2 `config/`

Recommended internal structure:

```text
config/
├── constants.py
├── paths.py
├── prompts.py
├── settings.py
└── showcase_patients.json
```

Purpose:

- Store locked enums
- Store medication whitelist
- Store valid route values
- Store valid lab type values
- Store valid source type values
- Store global paths
- Store environment-driven settings
- Store reusable prompt templates for RAG and any shared prompt configuration
- Store showcase patient IDs

Important rule:

`config/constants.py` is the single source of truth for locked values used by generators, validators, SOAP, ingestion, RAG, and tests.

---

## 4.3 `data/`

Recommended internal structure:

```text
data/
├── chromadb/
├── patients/
├── quarantine/
└── schemas/
    └── patient_schema.json
```

Purpose:

- `patients/` stores approved synthetic patient JSON records
- `quarantine/` stores invalid or rejected patient records and issue reports
- `chromadb/` stores local persistent ChromaDB files
- `schemas/` stores patient JSON schema definitions

Important rules:

- Only validated records should be stored in `data/patients/`.
- Invalid records must be moved to `data/quarantine/`.
- Files in `data/quarantine/` must never be ingested into ChromaDB.
- Files in `data/chromadb/` are runtime output and are not source data.

---

## 4.4 `deployment/`

Recommended internal structure:

```text
deployment/
├── docker-compose.yml
├── Dockerfile.backend
└── Dockerfile.frontend
```

Purpose:

- Build backend container
- Build frontend container
- Run backend and frontend together locally
- Support reproducible demo execution from a clean clone

Deployment must remain simple. This project must not include Kubernetes, cloud deployment complexity, Nginx reverse proxy complexity, Redis, Celery, or microservice orchestration.

---

## 4.5 `docs/`

Recommended internal structure:

```text
docs/
├── architecture_summary.md
├── team_ownership_and_architecture.md
├── project_scope_and_safety_rules.md
├── data_schema_contract.md
├── validation_rules.md
├── data_generation_pipeline.md
├── rag_handoff_contract.md
├── retrieval_enrichment_contract.md
├── chunking_and_metadata_contract.md
├── rag_pipeline.md
├── citation_contract.md
├── api_contract.md
├── ocr_workflow.md
├── demo_script.md
├── fallback_plan.md
├── showcase_patients.md
├── llm_project_context.md
└── Report/
    └── Project_Planning_and_Management.docx
```

Purpose:

- Explain system architecture
- Document team ownership boundaries
- Document data/schema handoff rules
- Document validation rules
- Document RAG workflow
- Document retrieval enrichment behavior
- Document chunking and metadata expectations
- Document API behavior
- Document OCR workflow
- Provide demo script
- Provide fallback plan
- Support DEPI evaluation, GitHub presentation, and LLM-assisted team work

---

## 4.6 `frontend/`

Recommended internal structure:

```text
frontend/
├── api_client.py
├── app.py
└── README.md
```

Purpose:

- Provide demo user interface
- Allow patient selection
- Send queries to backend
- Display grounded answers
- Display citations
- Display timeline view
- Display allergy history
- Display OCR demo output

The frontend should communicate with the backend only through API calls. It must not call ChromaDB, Groq, validators, data generators, or ingestion modules directly.

---

## 4.7 `generators/`

Recommended internal structure:

```text
generators/
├── allergy_generator.py
├── lab_generator.py
├── medication_generator.py
├── patient_generator.py
└── visit_generator.py
```

Purpose:

- Generate patient identities, demographics, tiers, and conditions
- Generate visit timelines and prior visit links
- Generate vitals with BP inside `visit.vitals` only
- Generate lab values and lab progression
- Generate medication records from whitelist only
- Generate allergy registry
- Maintain structured medical consistency

Important rule:

The generators must not call the LLM. They produce structured facts only.

---

## 4.8 `ingestion/`

Recommended internal structure:

```text
ingestion/
├── retrieval_enricher.py
├── retrieval_enrichment_auditor.py
├── chunker.py
├── metadata_builder.py
├── ingest.py
└── README.md
```

Purpose:

- Build deterministic retrieval enrichment text from structured records
- Audit retrieval enrichment text before it becomes part of chunks
- Convert patient visits into semantic chunks
- Build safe ChromaDB metadata
- Validate metadata before ingestion
- Embed chunks
- Store chunks in ChromaDB

Important rules:

- Ingestion must only run after validation passes.
- Retrieval enrichment text is not the medical source of truth.
- Source truth remains structured patient JSON and deterministic SOAP text.
- BP values must never be stored in ChromaDB metadata.
- Allergy records should be represented as dedicated `source_type="allergy"` chunks.

---

## 4.9 `logs/`

Recommended internal structure:

```text
logs/
└── pipeline_run.log
```

Purpose:

- Record pipeline execution
- Record validation summaries
- Record ingestion results
- Record demo startup status

A single readable log file is enough for this academic system. A complex logging framework is unnecessary.

---

## 4.10 `ocr/`

Recommended internal structure:

```text
ocr/
├── ocr_cache/
├── sample_scans/
├── ocr_cache_manager.py
├── ocr_cleaner.py
├── ocr_extractor.py
└── offline_loader.py
```

Purpose:

- Store sample scanned synthetic documents
- Extract OCR text using Google Vision during preparation
- Cache extracted OCR text
- Load cached OCR text during demo
- Clean OCR text lightly using simple rules

Important rule:

During demo, OCR must operate in offline mode and must not depend on a live Google Vision API call.

---

## 4.11 `rag/`

Recommended internal structure:

```text
rag/
├── __init__.py
├── answer_generator.py
├── citations.py
├── grounding.py
├── llm_client.py
├── prompt_builder.py
├── query_models.py
├── README.md
└── retriever.py
```

Purpose:

- Retrieve relevant chunks from ChromaDB
- Build grounded prompts
- Call Groq API for answer generation
- Generate answers using retrieved context only
- Format source citations
- Enforce grounding rules
- Return structured RAG responses

Important rule:

The RAG layer must never generate unsupported medical conclusions. If evidence is missing, the system must say the available records do not contain enough documented evidence.

---

## 4.12 `scripts/`

Recommended internal structure:

```text
scripts/
├── generate_all.py
├── generate_soap.py
├── validate_all.py
├── check_retrieval_enricher_output.py
├── ingest_all.py
├── reset_chromadb.py
├── run_local_demo.sh
└── warmup_demo.py
```

Purpose:

- Automate dataset generation
- Run validation
- Run deterministic SOAP generation
- Run retrieval enrichment debug checks
- Run ingestion
- Reset vector database
- Warm up demo queries
- Start local demo

Ownership note:

- Data, validation, SOAP, and retrieval-enrichment debug scripts are primarily owned by Ahmed Hesham Kamel.
- Ingestion and RAG scripts are primarily owned by Gamal Mohamed Gad.
- Demo, deployment, and smoke-test scripts are primarily owned by Mahmoud Mohamed El Faham.

---

## 4.13 `soap/`

Recommended internal structure:

```text
soap/
├── soap_contract.py
├── soap_generator.py
├── soap_renderers.py
├── soap_templates.py
├── soap_selector.py
├── soap_semantics.py
├── soap_safety.py
├── soap_auditor.py
└── README.md
```

Purpose:

- Generate SOAP notes deterministically from structured facts
- Render structured visit data into readable SOAP sections
- Select deterministic templates without randomness
- Improve wording diversity for retrieval quality while staying grounded
- Audit SOAP text for unsupported, unsafe, or inconsistent content

Important rules:

- SOAP generation does not call an LLM in the current implementation.
- SOAP text must never modify structured patient data.
- SOAP text must never invent medications, diagnoses, labs, vitals, allergies, or clinical interpretations.
- SOAP is narrative evidence for retrieval, not a replacement for structured JSON.

---

## 4.14 `tests/`

Recommended internal structure:

```text
tests/
├── test_api.py
├── test_chunking.py
├── test_retrieval.py
├── test_validation.py
├── test_ocr_cache.py
└── test_demo_smoke.py
```

Purpose:

- Test validation logic
- Test chunking behavior
- Test retrieval quality
- Test API endpoints
- Test OCR cache behavior
- Test demo readiness

---

## 4.15 `validators/`

Recommended internal structure:

```text
validators/
├── __init__.py
├── rules.py
├── validate.py
└── validation_report.py
```

Purpose:

- Implement V1–V11 validation rules
- Check patient JSON consistency
- Reject invalid records
- Generate validation reports

Validation is a hard gate before SOAP generation, retrieval enrichment, chunking, and ingestion.

---

# 5. File-by-File Responsibilities

## 5.1 Backend Files

| File | Responsibility |
|---|---|
| `backend/app/main.py` | Creates FastAPI app and registers routes |
| `backend/app/routes.py` | Defines `/query`, `/timeline/{patient_id}`, `/summary/{patient_id}`, and `/health` |
| `backend/app/schemas.py` | Defines Pydantic request and response models |
| `backend/app/services.py` | Calls RAG, timeline, OCR, and summary services |
| `backend/app/health.py` | Provides backend health checks if separated from routes |
| `backend/README.md` | Backend setup and API usage guide |

## 5.2 Config Files

| File | Responsibility |
|---|---|
| `config/constants.py` | Locked enums, medication whitelist, source types, valid routes, lab types, tier prefixes |
| `config/paths.py` | Centralized project paths |
| `config/prompts.py` | Shared prompt templates for RAG and shared configuration only |
| `config/settings.py` | Environment variables and runtime settings |
| `config/showcase_patients.json` | Selected demo patients and showcase IDs |

## 5.3 Data Files

| File/Folder | Responsibility |
|---|---|
| `data/patients/` | Approved patient JSON records |
| `data/quarantine/` | Invalid records blocked by validation |
| `data/chromadb/` | Local ChromaDB persistence |
| `data/schemas/patient_schema.json` | Formal patient JSON schema |

## 5.4 Generator Files

| File | Responsibility |
|---|---|
| `generators/patient_generator.py` | Generates patient identity, demographics, tiers, and conditions |
| `generators/visit_generator.py` | Generates visits, visit dates, vitals, and prior visit links |
| `generators/lab_generator.py` | Generates lab results and lab progression |
| `generators/medication_generator.py` | Generates medication records from whitelist with stable start/stop timeline dates |
| `generators/allergy_generator.py` | Generates allergy registry safely and deterministically |

## 5.5 Ingestion Files

| File | Responsibility |
|---|---|
| `ingestion/retrieval_enricher.py` | Builds deterministic retrieval support text from structured facts |
| `ingestion/retrieval_enrichment_auditor.py` | Audits retrieval enrichment text before chunking/ingestion |
| `ingestion/chunker.py` | Converts patient records into semantic chunks |
| `ingestion/metadata_builder.py` | Builds safe ChromaDB metadata |
| `ingestion/ingest.py` | Embeds chunks and stores them in ChromaDB |
| `ingestion/README.md` | Documents chunking and ingestion usage |

## 5.6 RAG Files

| File | Responsibility |
|---|---|
| `rag/retriever.py` | Performs patient-scoped ChromaDB retrieval |
| `rag/prompt_builder.py` | Builds strict context-grounded prompts |
| `rag/llm_client.py` | Wraps Groq API calls |
| `rag/answer_generator.py` | Coordinates retrieval, prompting, generation, and citations |
| `rag/citations.py` | Formats citations for API and frontend |
| `rag/grounding.py` | Enforces no-evidence/no-answer behavior |
| `rag/query_models.py` | Defines internal RAG data models |
| `rag/README.md` | Documents RAG behavior and retrieval rules |

## 5.7 OCR Files

| File | Responsibility |
|---|---|
| `ocr/ocr_extractor.py` | Calls Google Vision OCR when live extraction is allowed |
| `ocr/ocr_cache_manager.py` | Reads and writes cached OCR text |
| `ocr/ocr_cleaner.py` | Performs light OCR text cleaning |
| `ocr/offline_loader.py` | Loads OCR cache during offline demo mode |
| `ocr/sample_scans/` | Stores synthetic scanned documents |
| `ocr/ocr_cache/` | Stores pre-extracted OCR text files |

## 5.8 SOAP Files

| File | Responsibility |
|---|---|
| `soap/soap_contract.py` | Defines shared SOAP sections, template contract, required facts, and placeholders |
| `soap/soap_generator.py` | Generates deterministic SOAP notes from structured facts |
| `soap/soap_renderers.py` | Converts structured visit data into renderable SOAP fact context |
| `soap/soap_templates.py` | Stores deterministic SOAP wording templates |
| `soap/soap_selector.py` | Selects deterministic template variants |
| `soap/soap_semantics.py` | Adds grounded semantic wording diversity for retrieval quality |
| `soap/soap_safety.py` | Stores SOAP safety constants and forbidden wording policy |
| `soap/soap_auditor.py` | Audits SOAP text for unsupported or inconsistent content |

## 5.9 Validator Files

| File | Responsibility |
|---|---|
| `validators/rules.py` | Contains V1–V11 validation functions |
| `validators/validate.py` | Runs validation checks across patient files |
| `validators/validation_report.py` | Produces readable validation reports |
| `validators/__init__.py` | Marks validators as a package |

## 5.10 Script Files

| File | Responsibility | Primary Owner |
|---|---|---|
| `scripts/generate_all.py` | Runs full data generation pipeline with validation hard gate | Ahmed Hesham Kamel |
| `scripts/generate_soap.py` | Regenerates deterministic SOAP after validation | Ahmed Hesham Kamel |
| `scripts/validate_all.py` | Runs V1–V11 and dataset-level checks | Ahmed Hesham Kamel |
| `scripts/check_retrieval_enricher_output.py` | Debugs retrieval enrichment output | Ahmed Hesham Kamel / Gamal Mohamed Gad |
| `scripts/ingest_all.py` | Runs chunking and ChromaDB ingestion | Gamal Mohamed Gad |
| `scripts/reset_chromadb.py` | Clears local ChromaDB state | Gamal Mohamed Gad / Mahmoud Mohamed El Faham |
| `scripts/warmup_demo.py` | Runs warmup queries before demo | Mahmoud Mohamed El Faham |
| `scripts/run_local_demo.sh` | Starts local demo workflow | Mahmoud Mohamed El Faham |

## 5.11 Test Files

| File | Responsibility |
|---|---|
| `tests/test_validation.py` | Tests validation rules |
| `tests/test_chunking.py` | Tests chunk structure and metadata |
| `tests/test_retrieval.py` | Tests retrieval quality and expected source types |
| `tests/test_api.py` | Tests FastAPI endpoints |
| `tests/test_ocr_cache.py` | Tests OCR cache loading behavior |
| `tests/test_demo_smoke.py` | Tests demo startup and key workflows |

---

# 6. Full RAG Pipeline Flow

The RAG pipeline is the highest-priority engineering component.

```text
User Query
    ↓
FastAPI /query endpoint
    ↓
Request validation
    ↓
Patient-scoped retrieval
    ↓
ChromaDB top-k search
    ↓
Retrieved chunks
    ↓
Grounding check
    ↓
Prompt construction
    ↓
Groq LLM call
    ↓
Grounded answer
    ↓
Citation formatting
    ↓
Structured API response
    ↓
Streamlit display
```

## RAG Responsibilities

| Step | Owner | Implementation |
|---|---|---|
| Query input | Mahmoud Tarek Mahmoud | `backend/app/routes.py` |
| Retrieval | Gamal Mohamed Gad | `rag/retriever.py` |
| Prompt building | Gamal Mohamed Gad | `rag/prompt_builder.py` |
| LLM call | Gamal Mohamed Gad | `rag/llm_client.py` |
| Answer generation | Gamal Mohamed Gad | `rag/answer_generator.py` |
| Citation formatting | Gamal Mohamed Gad | `rag/citations.py` |
| Grounding validation | Gamal Mohamed Gad | `rag/grounding.py` |
| API response | Mahmoud Tarek Mahmoud | `backend/app/schemas.py` |
| UI display | Youssef Yassin Ibrahim | `frontend/app.py` |

## Retrieval Rules

- Retrieval must be patient-scoped.
- Chunks must include meaningful text for semantic search.
- Retrieval enrichment may be used to strengthen chunk text, but it is not source truth.
- Metadata must support filtering by patient, visit date, visit type, source type, and conditions.
- BP must not appear in ChromaDB metadata.
- BP queries should retrieve doctor note chunks, not lab metadata.
- Allergy queries should prioritize allergy chunks.
- Medication queries should prioritize prescription chunks.
- Lab trend queries should prioritize lab result chunks.

## Grounding Rule

The system must follow this rule:

```text
No retrieved evidence = no generated medical answer.
```

If retrieved chunks do not support the question, the system should respond that the available records do not contain enough documented evidence.

---

# 7. Validation Workflow

Validation is the main safety and quality gate.

## Validation Pipeline

```text
Generate structured synthetic records
        ↓
Run V1–V11 validation
        ↓
Run dataset-level checks
        ↓
Move invalid records to quarantine
        ↓
Fix validation errors
        ↓
Run validation again
        ↓
Only valid records proceed to SOAP, enrichment, chunking, and ingestion
```

## Validation Rules

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

## Dataset-Level Checks

In addition to V1–V11, the full dataset must pass:

| Check | Requirement |
|---|---|
| Patient count | `pilot = 5`, `full = 30` |
| Tier distribution | `full = 10 normal / 13 moderate / 7 chronic` |
| Unique patient IDs | No duplicate `patient_id` values across files |
| CKD count | CKD appears in max 2 chronic patients |

## BP Validation Rule

BP must only appear here:

```json
"vitals": {
  "bp_systolic": 120,
  "bp_diastolic": 80
}
```

BP must not appear in:

```text
labs
lab_type enum
ChromaDB metadata
timeline_events
any duplicate shadow field
```

## Validation Gate

The pipeline must not proceed unless:

```text
FAIL violations = 0
```

Warnings should be reviewed before demo day.

---

# 8. Deterministic SOAP Workflow

SOAP notes provide readable narrative content for doctor-note chunks.

## SOAP Pipeline

```text
Validated structured patient JSON
        ↓
Build SOAP fact context
        ↓
Select deterministic template variants
        ↓
Render SOAP sections
        ↓
Run SOAP safety audit
        ↓
Save SOAP note back into patient JSON
```

## SOAP Rules

- SOAP generation is deterministic.
- SOAP generation does not call an LLM in the current implementation.
- SOAP must use structured patient facts only.
- SOAP must not invent medical facts.
- SOAP must not modify structured JSON.
- SOAP must pass safety audit before ingestion.

## SOAP Sections

Each visit SOAP note contains:

```text
subjective
objective
assessment
plan
```

The SOAP objective section is where BP values can appear as text for retrieval. BP still must not appear in labs or metadata.

---

# 9. Retrieval Enrichment Workflow

Retrieval enrichment improves semantic retrieval quality before chunking.

## Enrichment Pipeline

```text
Validated patient JSON + SOAP
        ↓
Build retrieval enrichment text
        ↓
Audit retrieval enrichment text
        ↓
Attach to chunk text or use during chunk construction
        ↓
Build metadata
        ↓
Ingest into ChromaDB
```

## Source Types

| Source Type | Purpose |
|---|---|
| `doctor_note` | SOAP narrative and visit-level clinical context |
| `lab_result` | Lab values, lab types, and condition-related lab context |
| `prescription` | Medication names, dose, frequency, route, start date, and stop date |
| `allergy` | Allergy registry and documented reactions |

## Enrichment Rules

- Enrichment text is deterministic.
- Enrichment text is derived from documented facts only.
- Enrichment text is not source truth.
- The auditor must detect unsupported condition, medication, lab, or unsafe wording.
- Enrichment audit should pass before ChromaDB ingestion.

---

# 10. OCR Workflow

OCR supports the demo by showing that scanned synthetic documents can be extracted and retrieved.

## OCR Development Mode

```text
Synthetic scanned document
        ↓
Google Vision OCR
        ↓
Raw extracted text
        ↓
Light OCR cleaning
        ↓
Save to ocr_cache/
        ↓
Use cached text for ingestion/demo
```

## OCR Demo Mode

```text
OFFLINE_MODE=true
        ↓
Load text from ocr/ocr_cache/
        ↓
Display cached OCR text in Streamlit
        ↓
Use cached text for retrieval demo
        ↓
No live Google Vision call
```

## OCR Rules

- Use Google Vision only during preparation.
- Cache every OCR result.
- During demo, use cached OCR only.
- Do not rely on internet during presentation.
- Do not use LLM-based OCR correction.
- Use light regex-based cleaning only.

---

# 11. API Workflow

The backend exposes a simple API layer.

## Required Endpoints

```text
POST /query
GET /timeline/{patient_id}
GET /summary/{patient_id}
GET /health
```

## `POST /query`

Purpose:

```text
Answer a user question using grounded RAG.
```

Flow:

```text
Frontend query
        ↓
FastAPI validates request
        ↓
Backend calls RAG answer generator
        ↓
RAG retrieves chunks
        ↓
RAG generates grounded answer
        ↓
Citations are attached
        ↓
Backend returns structured response
```

## `GET /timeline/{patient_id}`

Purpose:

```text
Return chronological patient visit history from patient JSON.
```

The timeline should be generated from visit records. It should not depend on a stored `timeline_events` field.

## `GET /summary/{patient_id}`

Purpose:

```text
Return a grounded summary of documented patient history.
```

The summary should still be based on retrieved records and should include citations where appropriate.

## `GET /health`

Purpose:

```text
Verify backend availability and demo readiness.
```

Recommended response:

```json
{
  "status": "ok",
  "chromadb": "available",
  "offline_mode": true
}
```

---

# 12. Docker Workflow

Docker is used for reproducible local execution.

## Docker Structure

```text
deployment/
├── docker-compose.yml
├── Dockerfile.backend
└── Dockerfile.frontend
```

## Expected Workflow

```text
Copy .env.example to .env
        ↓
Build backend and frontend containers
        ↓
Start docker-compose
        ↓
Backend runs FastAPI
        ↓
Frontend runs Streamlit
        ↓
Frontend communicates with backend
        ↓
Demo runs locally
```

## Docker Rules

- Docker must remain simple.
- No Kubernetes.
- No cloud deployment complexity.
- No microservices.
- No database container unless strictly needed.
- ChromaDB remains local persistent storage.
- Environment variables must be documented in `.env.example`.

---

# 13. Team Ownership Table

| Member | Role | Main Ownership | Main Deliverables |
|---|---|---|---|
| Ahmed Hesham Kamel | Team Leader & Data Engineering Lead | `generators/`, `validators/`, `data/`, `config/`, `soap/`, `docs/` | Valid dataset, schema, validation rules, deterministic SOAP, showcase patients, documentation |
| Gamal Mohamed Gad | Retrieval-Augmented Generation Engineer | `ingestion/`, `rag/`, `data/chromadb/`, retrieval tests | Retrieval enrichment integration, chunking, embeddings, ChromaDB ingestion, retrieval, grounding, citations |
| Mahmoud Tarek Mahmoud | FastAPI Backend Engineer | `backend/`, API services, API testing | API routes, schemas, backend orchestration |
| Youssef Yassin Ibrahim | Streamlit and OCR Engineer | `frontend/`, `ocr/` | Demo UI, API client, OCR cache flow, OCR display |
| Mahmoud Mohamed El Faham | Deployment and Testing Engineer | `deployment/`, demo scripts, smoke tests, logs | Docker setup, reproducible local demo, tests, smoke checks |

---

# 14. Folder Ownership Table

| Folder | Primary Owner | Secondary Support |
|---|---|---|
| `backend/` | Mahmoud Tarek Mahmoud | Gamal Mohamed Gad |
| `config/` | Ahmed Hesham Kamel | Mahmoud Mohamed El Faham |
| `data/` | Ahmed Hesham Kamel | Gamal Mohamed Gad |
| `deployment/` | Mahmoud Mohamed El Faham | Mahmoud Tarek Mahmoud and Youssef Yassin Ibrahim |
| `docs/` | Ahmed Hesham Kamel | All team members |
| `frontend/` | Youssef Yassin Ibrahim | Mahmoud Tarek Mahmoud |
| `generators/` | Ahmed Hesham Kamel | None |
| `ingestion/` | Gamal Mohamed Gad | Ahmed Hesham Kamel |
| `logs/` | Mahmoud Mohamed El Faham | Ahmed Hesham Kamel |
| `ocr/` | Youssef Yassin Ibrahim | Mahmoud Mohamed El Faham |
| `rag/` | Gamal Mohamed Gad | Mahmoud Tarek Mahmoud |
| `scripts/` | Shared by script type | Ahmed Hesham Kamel, Gamal Mohamed Gad, Mahmoud Mohamed El Faham |
| `soap/` | Ahmed Hesham Kamel | Gamal Mohamed Gad |
| `tests/` | Mahmoud Mohamed El Faham | All team members |
| `validators/` | Ahmed Hesham Kamel | Mahmoud Mohamed El Faham |

---

# 15. Dependency Relationships Between Members

## Ahmed Hesham Kamel → Gamal Mohamed Gad

Gamal depends on Ahmed for:

- Stable patient schema
- Valid patient JSON records
- Correct constants and enums
- Deterministic SOAP notes
- Retrieval enrichment contract
- Validation reports
- Showcase patient list

If validation fails, ingestion must not proceed.

---

## Gamal Mohamed Gad → Mahmoud Tarek Mahmoud

Mahmoud Tarek depends on Gamal for:

- Working retriever
- Working ChromaDB collection
- Answer generation interface
- Citation format
- Retrieval test results

The backend should call RAG modules instead of duplicating RAG logic.

---

## Mahmoud Tarek Mahmoud → Youssef Yassin Ibrahim

Youssef depends on Mahmoud Tarek for:

- Stable API endpoints
- Clear request/response schemas
- Citation response format
- Timeline response format
- Summary response format

The frontend should not bypass the backend.

---

## Youssef Yassin Ibrahim → Mahmoud Mohamed El Faham

Mahmoud El Faham depends on the frontend and backend being runnable locally before Docker hardening.

The OCR workflow must also be stable before demo smoke testing.

---

## Mahmoud Mohamed El Faham → Entire Team

The entire team depends on Mahmoud El Faham for:

- Clean local setup
- Docker Compose workflow
- Environment variable documentation
- Test execution
- Demo warmup
- Smoke testing
- Runtime stability

---

# 16. Development Order

The project must be developed in dependency order.

```text
1. Define constants and schema
2. Build validation rules V1–V11
3. Generate pilot patient records
4. Validate pilot records
5. Generate full synthetic dataset
6. Run dataset-level validation checks
7. Generate deterministic SOAP notes
8. Audit SOAP notes
9. Validate again
10. Build retrieval enrichment
11. Audit retrieval enrichment output
12. Build chunking and metadata
13. Ingest into ChromaDB
14. Test retrieval quality
15. Build FastAPI backend
16. Test API endpoints
17. Build Streamlit frontend
18. Integrate OCR cache workflow
19. Build Docker workflow
20. Run smoke tests
21. Prepare demo script
22. Rehearse final demo
```

Important development rule:

```text
Do not build the frontend before retrieval works.
```

A polished UI cannot compensate for weak retrieval quality.

---

# 17. Collaboration Workflow

## Daily Collaboration Pattern

Each member should report:

```text
What I completed
What file or folder I changed
What is blocked
What I need from another member
What should be tested next
```

## Integration Rules

- Ahmed Hesham Kamel controls schema changes, validation rules, dataset generation, deterministic SOAP, and data documentation.
- Gamal Mohamed Gad controls retrieval enrichment integration, chunking, metadata, retrieval behavior, grounding, and citations.
- Mahmoud Tarek Mahmoud controls API contract and backend orchestration.
- Youssef Yassin Ibrahim controls Streamlit display and OCR user flow.
- Mahmoud Mohamed El Faham controls Docker, demo scripts, test execution, logs, and local reproducibility.

## Pull Request Rules

Each pull request should include:

- Clear description
- Folder changed
- Owner approval
- Test command used
- Screenshot or log if UI/demo behavior changed

## Integration Checkpoints

| Checkpoint | Required Before Proceeding |
|---|---|
| Data checkpoint | Validation passes with zero FAIL violations |
| Dataset checkpoint | Count, tier distribution, unique IDs, and CKD limit pass |
| SOAP checkpoint | Deterministic SOAP audit passes |
| Enrichment checkpoint | Retrieval enrichment audit passes |
| Ingestion checkpoint | ChromaDB has expected chunk count |
| Retrieval checkpoint | Retrieval tests pass for showcase patients |
| API checkpoint | `/query`, `/timeline`, `/summary`, `/health` work |
| Frontend checkpoint | Streamlit displays answers, citations, timeline, allergy, OCR |
| Demo checkpoint | Offline mode works and warmup script passes |

---

# 18. Demo Workflow

The demo should show a stable and explainable system.

## Demo Preparation

```text
1. Generate or confirm approved patient records
2. Run validation with zero FAIL issues
3. Confirm deterministic SOAP exists and passes audit
4. Confirm retrieval enrichment output is audited
5. Confirm ChromaDB is populated
6. Confirm OCR cache exists
7. Set OFFLINE_MODE=true
8. Run warmup_demo.py
9. Start backend
10. Start frontend
11. Test showcase queries
12. Prepare fallback screenshots
```

## Demo Sequence

```text
1. Open Streamlit frontend
2. Select showcase patient
3. Ask a RAG question
4. Show grounded answer
5. Show citations
6. Open timeline tab
7. Show chronological patient history
8. Open allergy history tab
9. Show documented allergy retrieval
10. Open OCR demo tab
11. Show cached OCR text
12. Ask question based on OCR content
13. Show cited answer
```

## Demo Rules

- Use showcase patients only.
- Use rehearsed queries.
- Do not introduce new features during demo.
- Do not claim diagnosis or treatment recommendation.
- Use the phrase “retrieves documented records,” not “detects disease.”
- Keep fallback screenshots ready.

---

# 19. Required Commands

## Full data pipeline

```bash
python scripts/generate_all.py --mode full --clean
python scripts/validate_all.py --mode full
python scripts/generate_soap.py --dry-run
python scripts/generate_soap.py
python scripts/validate_all.py --mode full
```

## Retrieval enrichment debug

```bash
python scripts/check_retrieval_enricher_output.py --patient-id PAT-MOD-001 --visit-index 0
```

## Ingestion and retrieval

```bash
python scripts/ingest_all.py
python tests/test_retrieval.py
```

## Backend and frontend

```bash
uvicorn backend.app.main:app --reload
streamlit run frontend/app.py
```

## Demo readiness

```bash
python scripts/warmup_demo.py
```

---

# 20. Engineering Strengths

## Clear Separation of Concerns

Each folder has a clear engineering responsibility. Data generation, validation, SOAP, retrieval enrichment, RAG, backend, frontend, OCR, and deployment are separated cleanly.

## Strong Safety Boundaries

The architecture prevents unsupported medical claims by requiring retrieved evidence and source citations.

## Good Team Ownership

The five-member structure maps naturally to the repository structure.

## Demo Stability

The system includes OCR cache, warmup scripts, validation gates, Docker Compose, and fallback planning.

## Academic Suitability

The repository demonstrates realistic AI engineering practices without unnecessary enterprise infrastructure.

## Portfolio Value

The system shows practical experience with FastAPI, Streamlit, ChromaDB, RAG, OCR, Docker, validation, and modular Python design.

---

# 21. Engineering Weaknesses and Required Follow-Up

The structure is strong, but the following areas should be strengthened before final demo:

| Weakness | Recommended Fix |
|---|---|
| RAG documentation needs detailed implementation rules | Add `docs/rag_pipeline.md` |
| Validation documentation needs official handoff clarity | Add `docs/validation_rules.md` |
| Retrieval enrichment needs formal handoff documentation | Add `docs/retrieval_enrichment_contract.md` |
| Chunking and metadata need a strict contract | Add `docs/chunking_and_metadata_contract.md` |
| Citation output needs stable format | Add `docs/citation_contract.md` |
| OCR tests may be missing | Add `tests/test_ocr_cache.py` |
| Demo smoke tests may be missing | Add `tests/test_demo_smoke.py` |

---

# 22. Future Improvements

The following improvements are safe and do not violate the project scope:

```text
Add docs/rag_pipeline.md
Add docs/validation_rules.md
Add docs/retrieval_enrichment_contract.md
Add docs/chunking_and_metadata_contract.md
Add docs/citation_contract.md
Add docs/ocr_workflow.md
Add tests/test_ocr_cache.py
Add tests/test_demo_smoke.py
Add frontend/components.py if Streamlit grows too large
Add backend/app/health.py if health logic grows
Add Makefile for common commands
```

The following improvements should not be added before the demo:

```text
Kubernetes
Microservices
PostgreSQL primary database
Redis
Celery
LangGraph
Agent orchestration
Clinical NLP pipelines
Medical ontologies
Real hospital integration
FHIR/HL7
Advanced dashboards
Disease prediction
Treatment recommendation
Diagnosis support
```

---

# 23. Why This Architecture Avoids Overengineering

This architecture avoids overengineering by using simple, direct components:

| Need | Practical Solution |
|---|---|
| Data storage | Local JSON files |
| Vector search | Local ChromaDB |
| Backend | Single FastAPI app |
| Frontend | Single Streamlit app |
| OCR | Google Vision with local cache |
| Validation | Plain Python validation scripts |
| SOAP | Deterministic template-based generation |
| Deployment | Docker Compose only |
| Testing | Focused project-level tests |

The system does not introduce distributed infrastructure, unnecessary databases, message queues, autonomous agents, or production hospital features.

This is appropriate because the project is an academic AI engineering demo, not a hospital SaaS platform.

---

# 24. Suitability for DEPI Evaluation

This architecture is suitable for DEPI because it demonstrates:

- Clear project scope
- Safe AI usage
- Grounded RAG workflow
- Citation-based answers
- Synthetic data handling
- Validation rules
- Retrieval enrichment for stronger semantic retrieval
- OCR integration
- Timeline retrieval
- Allergy history retrieval
- Docker-based reproducibility
- Clear team ownership
- Demo readiness

The architecture is easy to explain to evaluators and shows that the team understands both AI and software engineering.

---

# 25. Suitability for GitHub Portfolio

This architecture is suitable for GitHub because it demonstrates:

- Clean repository organization
- Modular Python engineering
- FastAPI backend development
- Streamlit frontend development
- RAG pipeline implementation
- ChromaDB integration
- OCR cache workflow
- Docker Compose setup
- Testing and validation
- Professional documentation

A reviewer can understand the project by reading the README, architecture documentation, API contract, RAG handoff contract, and demo script.

---

# 26. Suitability for Academic AI Engineering

This architecture is suitable for academic AI engineering because it includes:

- Data generation
- Schema design
- Validation
- Deterministic SOAP generation
- Retrieval enrichment
- Retrieval engineering
- Chunking
- Metadata design
- Embeddings
- Vector storage
- Prompt construction
- Grounding
- Citation formatting
- OCR preprocessing
- API design
- Frontend integration
- Deployment reproducibility
- Demo planning

It demonstrates AI engineering practice rather than only model usage.

---

# 27. Final Architecture Evaluation

## Score: 9.6 / 10

The architecture is strong, modular, practical, and suitable for the project goals.

## Strengths Behind the Score

- Clear folder responsibilities
- Strong team ownership boundaries
- Correct separation between structured data, deterministic SOAP, retrieval enrichment, and RAG answer generation
- Strong validation-first workflow
- RAG pipeline is isolated and testable
- OCR is cache-first and demo-safe
- Docker is simple and local-first
- Architecture avoids medical inference
- Suitable for DEPI and GitHub

## Why It Is Not 10 / 10

The structure can be improved by adding:

- OCR cache tests
- Demo smoke tests
- More detailed RAG documentation
- More detailed validation documentation
- Chunking and citation contracts
- Optional frontend component separation

These are improvements, not major architectural problems.

---

# 28. Final Conclusion

The **AI-Based Clinical Record Summarization System** has a professional, practical, and academically appropriate architecture.

It is designed around the correct priorities:

```text
Data quality
→ validation correctness
→ deterministic SOAP safety
→ retrieval enrichment
→ retrieval quality
→ grounded generation
→ citation transparency
→ demo stability
```

The project is suitable for a five-member academic AI engineering team because each member owns a clear technical area and each folder maps naturally to real implementation responsibilities.

The architecture avoids unnecessary complexity while still demonstrating strong software engineering practice. It is suitable for DEPI evaluation, GitHub portfolio presentation, team handoff, and academic AI engineering documentation.

The team should proceed with implementation in the defined development order and must avoid scope creep during the final stages.
