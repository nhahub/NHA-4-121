# AI-Based Clinical Record Summarization System

## Team Ownership and Architecture Documentation

**Document Path:** `docs/team_ownership_and_architecture.md`
**Project Type:** Academic AI Engineering RAG System
**Primary Goal:** Safe retrieval, summarization, and citation of synthetic clinical records
**Target Use:** DEPI graduation evaluation, GitHub portfolio presentation, and academic AI engineering documentation

---

# 1. Executive Architecture Overview

The **AI-Based Clinical Record Summarization System** is an academic Retrieval-Augmented Generation system designed to retrieve, summarize, and cite **synthetic clinical records** safely.

The system uses:

- FastAPI for backend APIs
- Streamlit for the frontend demo interface
- ChromaDB for local vector storage
- Groq API for LLM-based answer generation
- Google Vision OCR with offline cache
- Synthetic JSON medical records
- Docker and Docker Compose for reproducible local execution

The architecture is intentionally modular but not overengineered. It is designed for a small academic engineering team where each member has clear ownership boundaries.

The system follows this core workflow:

```text
Synthetic Data Generation
        ↓
Validation V1–V11
        ↓
SOAP Narrative Generation
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

| Rule             | Requirement                                                                   |
| ---------------- | ----------------------------------------------------------------------------- |
| Validation       | Must implement V1–V11 validation rules                                        |
| Blood Pressure   | BP exists only inside `visit.vitals`                                          |
| BP in labs       | BP must never appear in labs                                                  |
| BP in metadata   | BP must never appear in ChromaDB metadata                                     |
| SOAP             | SOAP generation is the only LLM-based narrative-writing step                  |
| RAG priority     | Retrieval quality is the highest engineering priority                         |
| OCR demo         | OCR demo must use offline cached OCR                                          |
| Answers          | All answers must be grounded and citation-based                               |
| Deployment       | Docker must remain simple and local-first                                     |
| Architecture     | No Kubernetes, no microservices, no PostgreSQL primary database               |
| AI orchestration | No LangGraph or agent orchestration                                           |
| Medical safety   | No diagnosis, treatment recommendation, prediction, or undocumented inference |

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

| Area          | Purpose                                                                     |
| ------------- | --------------------------------------------------------------------------- |
| `backend/`    | FastAPI backend and API orchestration                                       |
| `frontend/`   | Streamlit user interface                                                    |
| `rag/`        | Retrieval, prompt construction, grounding, citations, and answer generation |
| `ingestion/`  | Chunking, metadata construction, and ChromaDB ingestion                     |
| `generators/` | Synthetic structured patient data generation                                |
| `validators/` | V1–V11 validation rules and validation reporting                            |
| `soap/`       | LLM-based SOAP narrative generation and auditing                            |
| `ocr/`        | Google Vision OCR, OCR cache, and offline OCR loading                       |
| `data/`       | Synthetic patient JSON, schema files, quarantine, and ChromaDB storage      |
| `config/`     | Constants, paths, prompts, settings, and showcase patient configuration     |
| `scripts/`    | Pipeline automation scripts                                                 |
| `deployment/` | Docker and Docker Compose files                                             |
| `tests/`      | Validation, retrieval, API, and integration tests                           |
| `logs/`       | Pipeline and runtime logs                                                   |
| `docs/`       | Architecture, API, demo, fallback, and ownership documentation              |

---

# 4. Folder-by-Folder Responsibilities

## 4.1 `backend/`

The `backend/` folder contains the FastAPI backend.

Recommended internal structure:

```text
backend/
├── README.md
└── app/
    ├── __init__.py
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

The backend must remain lightweight. It should orchestrate system components but must not contain chunking logic, validation rules, embedding logic, or frontend UI logic.

---

## 4.2 `config/`

The `config/` folder contains shared project configuration.

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
- Store route values
- Store lab type values
- Store source type values
- Store global paths
- Store environment-driven settings
- Store reusable prompt templates
- Store showcase patient IDs

Important rule:

`config/constants.py` should be treated as the single source of truth for locked values used by generators, validators, ingestion, and tests.

---

## 4.3 `data/`

The `data/` folder stores synthetic data and local vector database files.

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
- `quarantine/` stores invalid or rejected patient records
- `chromadb/` stores local persistent ChromaDB files
- `schemas/` stores patient JSON schema definitions

Important rule:

Only validated records should be stored in `data/patients/`.

Invalid records must be moved to `data/quarantine/` and must not be ingested into ChromaDB.

---

## 4.4 `deployment/`

The `deployment/` folder contains Docker-related files.

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

The `docs/` folder contains academic and engineering documentation.

Recommended internal structure:

```text
docs/
├── api_contract.md
├── architecture_summary.md
├── demo_script.md
├── fallback_plan.md
├── showcase_patients.md
├── team_ownership_and_architecture.md
├── validation_rules.md
├── rag_pipeline.md
├── ocr_workflow.md
└── Project_Planning_and_Management.docx
```

Purpose:

- Explain system architecture
- Document API behavior
- Document ownership boundaries
- Document validation rules
- Document RAG workflow
- Document OCR workflow
- Provide demo script
- Provide fallback plan
- Support DEPI evaluation and GitHub presentation

---

## 4.6 `frontend/`

The `frontend/` folder contains the Streamlit application.

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

The frontend should communicate with the backend only through API calls. It must not call ChromaDB, Groq, validators, or data generators directly.

---

## 4.7 `generators/`

The `generators/` folder contains deterministic synthetic data generation logic.

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

- Generate patient demographics
- Generate visit timelines
- Generate vitals
- Generate lab values
- Generate medications from whitelist
- Generate allergy registry
- Maintain structured medical consistency

Important rule:

The generators must not call the LLM. They produce structured facts only.

---

## 4.8 `ingestion/`

The `ingestion/` folder converts validated patient records into ChromaDB-ready chunks.

Recommended internal structure:

```text
ingestion/
├── chunker.py
├── ingest.py
├── metadata_builder.py
└── README.md
```

Purpose:

- Convert patient visits into semantic chunks
- Build metadata for each chunk
- Validate metadata before ingestion
- Embed chunks
- Store chunks in ChromaDB

Important rule:

Ingestion must only run after validation passes.

---

## 4.9 `logs/`

The `logs/` folder stores runtime and pipeline logs.

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

The `ocr/` folder handles Google Vision OCR and offline cache behavior.

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

The `rag/` folder contains the core Retrieval-Augmented Generation logic.

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
- Call Groq API
- Generate answers using retrieved context only
- Format source citations
- Enforce grounding rules
- Return structured RAG responses

Important rule:

The RAG layer must never generate unsupported medical conclusions.

---

## 4.12 `scripts/`

The `scripts/` folder contains command-line workflow scripts.

Recommended internal structure:

```text
scripts/
├── generate_all.py
├── generate_soap.py
├── ingest_all.py
├── reset_chromadb.py
├── run_local_demo.sh
├── validate_all.py
└── warmup_demo.py
```

Purpose:

- Automate dataset generation
- Run validation
- Run SOAP generation
- Run ingestion
- Reset vector database
- Warm up demo queries
- Start local demo

Scripts make the system easier for the full team to run consistently.

---

## 4.13 `soap/`

The `soap/` folder contains LLM-based SOAP narrative generation.

Recommended internal structure:

```text
soap/
├── soap_auditor.py
└── soap_generator.py
```

Purpose:

- Generate SOAP notes from structured facts
- Audit SOAP text for basic consistency
- Prevent fabricated medications or unsupported narrative claims

Important rule:

SOAP generation is the only LLM-based narrative-writing step. The LLM must not control structured medical data.

---

## 4.14 `tests/`

The `tests/` folder contains project tests.

Recommended internal structure:

```text
tests/
├── test_api.py
├── test_chunking.py
├── test_retrieval.py
└── test_validation.py
```

Purpose:

- Test validation logic
- Test chunking behavior
- Test retrieval quality
- Test API endpoints

Recommended additions:

```text
tests/test_ocr_cache.py
tests/test_demo_smoke.py
```

These additions would improve demo stability.

---

## 4.15 `validators/`

The `validators/` folder contains validation rules and validation reporting.

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

Validation is a hard gate before ingestion.

---

# 5. File-by-File Responsibilities

## Backend Files

| File                      | Responsibility                                                                     |
| ------------------------- | ---------------------------------------------------------------------------------- |
| `backend/app/main.py`     | Creates FastAPI app and registers routes                                           |
| `backend/app/routes.py`   | Defines `/query`, `/timeline/{patient_id}`, `/summary/{patient_id}`, and `/health` |
| `backend/app/schemas.py`  | Defines Pydantic request and response models                                       |
| `backend/app/services.py` | Calls RAG, timeline, OCR, and summary services                                     |
| `backend/README.md`       | Backend setup and API usage guide                                                  |

## Config Files

| File                            | Responsibility                                                 |
| ------------------------------- | -------------------------------------------------------------- |
| `config/constants.py`           | Locked enums, whitelist, source types, valid routes, lab types |
| `config/paths.py`               | Centralized project paths                                      |
| `config/prompts.py`             | Prompt templates for SOAP and RAG                              |
| `config/settings.py`            | Environment variables and runtime settings                     |
| `config/showcase_patients.json` | Selected demo patients and showcase IDs                        |

## Data Files

| File/Folder                        | Responsibility                        |
| ---------------------------------- | ------------------------------------- |
| `data/patients/`                   | Approved patient JSON records         |
| `data/quarantine/`                 | Invalid records blocked by validation |
| `data/chromadb/`                   | Local ChromaDB persistence            |
| `data/schemas/patient_schema.json` | Formal JSON schema                    |

## Generator Files

| File                                 | Responsibility                                                  |
| ------------------------------------ | --------------------------------------------------------------- |
| `generators/patient_generator.py`    | Generates patient identity, demographics, tiers, and conditions |
| `generators/visit_generator.py`      | Generates visits, visit dates, vitals, and prior visit links    |
| `generators/lab_generator.py`        | Generates lab results and lab progression                       |
| `generators/medication_generator.py` | Generates medication records from whitelist                     |
| `generators/allergy_generator.py`    | Generates allergy registry                                      |

## Ingestion Files

| File                            | Responsibility                                |
| ------------------------------- | --------------------------------------------- |
| `ingestion/chunker.py`          | Converts patient records into semantic chunks |
| `ingestion/metadata_builder.py` | Builds safe ChromaDB metadata                 |
| `ingestion/ingest.py`           | Embeds chunks and stores them in ChromaDB     |
| `ingestion/README.md`           | Documents chunking and ingestion usage        |

## RAG Files

| File                      | Responsibility                                              |
| ------------------------- | ----------------------------------------------------------- |
| `rag/retriever.py`        | Performs patient-scoped ChromaDB retrieval                  |
| `rag/prompt_builder.py`   | Builds strict context-grounded prompts                      |
| `rag/llm_client.py`       | Wraps Groq API calls                                        |
| `rag/answer_generator.py` | Coordinates retrieval, prompting, generation, and citations |
| `rag/citations.py`        | Formats citations for API and frontend                      |
| `rag/grounding.py`        | Enforces no-evidence/no-answer behavior                     |
| `rag/query_models.py`     | Defines internal RAG data models                            |
| `rag/README.md`           | Documents RAG behavior and retrieval rules                  |

## OCR Files

| File                       | Responsibility                                          |
| -------------------------- | ------------------------------------------------------- |
| `ocr/ocr_extractor.py`     | Calls Google Vision OCR when live extraction is allowed |
| `ocr/ocr_cache_manager.py` | Reads and writes cached OCR text                        |
| `ocr/ocr_cleaner.py`       | Performs light OCR text cleaning                        |
| `ocr/offline_loader.py`    | Loads OCR cache during offline demo mode                |
| `ocr/sample_scans/`        | Stores synthetic scanned documents                      |
| `ocr/ocr_cache/`           | Stores pre-extracted OCR text files                     |

## SOAP Files

| File                     | Responsibility                                            |
| ------------------------ | --------------------------------------------------------- |
| `soap/soap_generator.py` | Generates SOAP narrative from structured facts            |
| `soap/soap_auditor.py`   | Checks SOAP text for hallucinated or inconsistent content |

## Validator Files

| File                              | Responsibility                       |
| --------------------------------- | ------------------------------------ |
| `validators/rules.py`             | Contains V1–V11 validation functions |
| `validators/validate.py`          | Runs all validation checks           |
| `validators/validation_report.py` | Produces readable validation reports |
| `validators/__init__.py`          | Marks validators as a package        |

## Script Files

| File                        | Responsibility                                  |
| --------------------------- | ----------------------------------------------- |
| `scripts/generate_all.py`   | Runs all structured data generators             |
| `scripts/validate_all.py`   | Runs V1–V11 validation across all patient files |
| `scripts/generate_soap.py`  | Runs SOAP generation and SOAP auditing          |
| `scripts/ingest_all.py`     | Runs chunking and ChromaDB ingestion            |
| `scripts/reset_chromadb.py` | Clears local ChromaDB state                     |
| `scripts/warmup_demo.py`    | Runs warmup queries before demo                 |
| `scripts/run_local_demo.sh` | Starts local demo workflow                      |

## Test Files

| File                       | Responsibility                                    |
| -------------------------- | ------------------------------------------------- |
| `tests/test_validation.py` | Tests validation rules                            |
| `tests/test_chunking.py`   | Tests chunk structure and metadata                |
| `tests/test_retrieval.py`  | Tests retrieval quality and expected source types |
| `tests/test_api.py`        | Tests FastAPI endpoints                           |

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

| Step                 | Owner             | Implementation            |
| -------------------- | ----------------- | ------------------------- |
| Query input          | Backend Developer | `backend/app/routes.py`   |
| Retrieval            | AI/RAG Engineer   | `rag/retriever.py`        |
| Prompt building      | AI/RAG Engineer   | `rag/prompt_builder.py`   |
| LLM call             | AI/RAG Engineer   | `rag/llm_client.py`       |
| Answer generation    | AI/RAG Engineer   | `rag/answer_generator.py` |
| Citation formatting  | AI/RAG Engineer   | `rag/citations.py`        |
| Grounding validation | AI/RAG Engineer   | `rag/grounding.py`        |
| API response         | Backend Developer | `backend/app/schemas.py`  |
| UI display           | Frontend Engineer | `frontend/app.py`         |

## Retrieval Rules

- Retrieval must be patient-scoped.
- Chunks must include meaningful text for semantic search.
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
Generate synthetic records
        ↓
Run V1–V11 validation
        ↓
Move invalid records to quarantine
        ↓
Fix validation errors
        ↓
Run validation again
        ↓
Only valid records proceed to SOAP generation and ingestion
```

## Validation Rules

| Rule | Purpose                                               | Severity  |
| ---- | ----------------------------------------------------- | --------- |
| V1   | Chronological visit order                             | FAIL      |
| V2   | Allergy contradiction check                           | FAIL      |
| V3   | Impossible vitals and age bounds                      | FAIL      |
| V4   | Required fields and forbidden demographic age field   | WARN/FAIL |
| V5   | Prior visit reference integrity                       | WARN      |
| V6   | Duplicate visit IDs                                   | FAIL      |
| V7   | Invalid enums and CKD co-occurrence rule              | FAIL      |
| V8   | Date format validation                                | FAIL      |
| V9   | BP forbidden in labs                                  | FAIL      |
| V10  | `timeline_events` forbidden in patient JSON           | FAIL      |
| V11  | Medication whitelist, frequency, and route validation | FAIL      |

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

The ingestion pipeline must not run unless:

```text
FAIL violations = 0
```

Warnings should be reviewed before demo day.

---

# 8. OCR Workflow

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

# 9. API Workflow

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
Answer a doctor-style question using grounded RAG.
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

# 10. Docker Workflow

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

# 11. Team Ownership Table

| Member                   | Role                                    | Main Ownership                                            | Main Deliverables                                                         |
| ------------------------ | --------------------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------- |
| Ahmed Hesham Kamel       | Team Leader & Data Engineering Lead     | `generators/`, `validators/`, `data/`, `config/`, `docs/` | Valid dataset, schema, validation rules, showcase patients, documentation |
| Gamal Mohamed Gad        | Retrieval-Augmented Generation Engineer | `ingestion/`, `rag/`, `data/chromadb/`, retrieval tests   | Chunking, embeddings, ChromaDB ingestion, retrieval, grounding, citations |
| Mahmoud Tarek Mahmoud    | FastAPI Backend Engineer                | `backend/`, API services, API testing                     | API routes, schemas, backend orchestration                                |
| Youssef Yassin Ibrahim   | Streamlit and OCR Engineer              | `frontend/`, `ocr/`                                       | Demo UI, API client, OCR cache flow, OCR display                          |
| Mahmoud Mohamed El Faham | Deployment and Testing Engineer         | `deployment/`, `scripts/`, `tests/`, `logs/`              | Docker setup, reproducible local demo, tests, smoke checks                |

---

# 12. Folder Ownership Table

| Folder        | Primary Owner            | Secondary Support                                |
| ------------- | ------------------------ | ------------------------------------------------ |
| `backend/`    | Mahmoud Tarek Mahmoud    | Gamal Mohamed Gad                                |
| `config/`     | Ahmed Hesham Kamel       | Mahmoud Mohamed ElFahham                         |
| `data/`       | Ahmed Hesham Kamel       | Gamal Mohamed Gad                                |
| `deployment/` | Mahmoud Mohamed ElFahham | Mahmoud Tarek Mahmoud and Youssef Yassin Ibrahim |
| `docs/`       | Ahmed Hesham Kamel       | All team members                                 |
| `frontend/`   | Youssef Yassin Ibrahim   | Mahmoud Tarek Mahmoud                            |
| `generators/` | Ahmed Hesham Kamel       | None                                             |
| `ingestion/`  | Gamal Mohamed Gad        | Ahmed Hesham Kamel                               |
| `logs/`       | Mahmoud Mohamed ElFahham | Ahmed Hesham Kamel                               |
| `ocr/`        | Youssef Yassin Ibrahim   | Mahmoud Mohamed ElFahham                         |
| `rag/`        | Gamal Mohamed Gad        | Mahmoud Tarek Mahmoud                            |
| `scripts/`    | Mahmoud Mohamed ElFahham | Ahmed Hesham Kamel and Gamal Mohamed Gad         |
| `soap/`       | Ahmed Hesham Kamel       | Gamal Mohamed Gad                                |
| `tests/`      | Mahmoud Mohamed ElFahham | All team members                                 |
| `validators/` | Ahmed Hesham Kamel       | Mahmoud Mohamed ElFahham                         |

---

# 13. Dependency Relationships Between Members

## Ahmed Hesham Kamel → Gamal Mohamed Gad

The AI/RAG Engineer depends on Ahmed for:

- Stable patient schema
- Valid patient JSON records
- Correct constants and enums
- SOAP narratives
- Validation reports
- Showcase patient list

If validation fails, ingestion must not proceed.

---

## Gamal Mohamed Gad → Mahmoud Tarek Mahmoud

The Backend Developer depends on the AI/RAG Engineer for:

- Working retriever
- Working ChromaDB collection
- Answer generation interface
- Citation format
- Retrieval test results

The backend should call RAG modules instead of duplicating RAG logic.

---

## Mahmoud Tarek Mahmoud → Youssef Yassin Ibrahim

The Frontend & OCR Engineer depends on the Backend Developer for:

- Stable API endpoints
- Clear request/response schemas
- Citation response format
- Timeline response format
- Summary response format

The frontend should not bypass the backend.

---

## Youssef Yassin Ibrahim → Mahmoud Mohamed ElFahham

The DevOps Engineer depends on the frontend and backend being runnable locally before Docker hardening.

The OCR workflow must also be stable before demo smoke testing.

---

## Mahmoud Mohamed ElFahham → Entire Team

The entire team depends on DevOps for:

- Clean local setup
- Docker Compose workflow
- Environment variable documentation
- Test execution
- Demo warmup
- Smoke testing
- Runtime stability

---

# 14. Development Order

The project must be developed in dependency order.

```text
1. Define constants and schema
2. Build validation rules V1–V11
3. Generate pilot patient records
4. Validate pilot records
5. Generate full synthetic dataset
6. Validate full dataset
7. Generate SOAP narratives
8. Audit SOAP narratives
9. Validate again
10. Build chunking and metadata
11. Ingest into ChromaDB
12. Test retrieval quality
13. Build FastAPI backend
14. Test API endpoints
15. Build Streamlit frontend
16. Integrate OCR cache workflow
17. Build Docker workflow
18. Run smoke tests
19. Prepare demo script
20. Rehearse final demo
```

Important development rule:

```text
Do not build the frontend before retrieval works.
```

A polished UI cannot compensate for weak retrieval quality.

---

# 15. Collaboration Workflow

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

- Ahmed Hesham Kamel controls schema changes.
- Gamal Mohamed Gad controls chunking and retrieval behavior.
- Mahmoud Tarek Mahmoud controls API contract.
- Youssef Yassin Ibrahim controls Streamlit display and OCR user flow.
- Mahmoud Mohamed El Faham controls Docker, scripts, test execution, and local reproducibility.

## Pull Request Rules

Each pull request should include:

- Clear description
- Folder changed
- Owner approval
- Test command used
- Screenshot or log if UI/demo behavior changed

## Integration Checkpoints

| Checkpoint           | Required Before Proceeding                                    |
| -------------------- | ------------------------------------------------------------- |
| Data checkpoint      | Validation passes with zero FAIL violations                   |
| SOAP checkpoint      | SOAP audit passes or issues are manually reviewed             |
| Ingestion checkpoint | ChromaDB has expected chunk count                             |
| Retrieval checkpoint | Retrieval tests pass for showcase patients                    |
| API checkpoint       | `/query`, `/timeline`, `/summary`, `/health` work             |
| Frontend checkpoint  | Streamlit displays answers, citations, timeline, allergy, OCR |
| Demo checkpoint      | Offline mode works and warmup script passes                   |

---

# 16. Demo Workflow

The demo should show a stable and explainable system.

## Demo Preparation

```text
1. Validate all patient records
2. Confirm ChromaDB is populated
3. Confirm OCR cache exists
4. Set OFFLINE_MODE=true
5. Run warmup_demo.py
6. Start backend
7. Start frontend
8. Test showcase queries
9. Prepare fallback screenshots
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

# 17. Engineering Strengths

## Clear Separation of Concerns

Each folder has a clear engineering responsibility. Data generation, validation, RAG, backend, frontend, OCR, and deployment are separated cleanly.

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

# 18. Engineering Weaknesses

The structure is strong, but the following weaknesses should be addressed:

| Weakness                                    | Recommended Fix                        |
| ------------------------------------------- | -------------------------------------- |
| OCR tests are not listed in final structure | Add `tests/test_ocr_cache.py`          |
| Demo smoke tests are missing                | Add `tests/test_demo_smoke.py`         |
| RAG documentation may be too light          | Add `docs/rag_pipeline.md`             |
| Validation documentation may be too light   | Add `docs/validation_rules.md`         |
| SOAP folder lacks documentation             | Add `soap/README.md`                   |
| Frontend may become too large               | Add `frontend/components.py` if needed |
| API health logic may grow                   | Add `backend/app/health.py` if needed  |

---

# 19. Future Improvements

The following improvements are safe and do not violate the project scope:

```text
Add tests/test_ocr_cache.py
Add tests/test_demo_smoke.py
Add docs/rag_pipeline.md
Add docs/validation_rules.md
Add docs/ocr_workflow.md
Add soap/README.md
Add ingestion/chunk_schema.py
Add frontend/components.py
Add backend/app/health.py
Add Makefile for common commands
```

The following improvements should not be added before the demo:

```text
Kubernetes
Microservices
PostgreSQL primary database
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

# 20. Why This Architecture Avoids Overengineering

This architecture avoids overengineering by using simple, direct components:

| Need          | Practical Solution              |
| ------------- | ------------------------------- |
| Data storage  | Local JSON files                |
| Vector search | Local ChromaDB                  |
| Backend       | Single FastAPI app              |
| Frontend      | Single Streamlit app            |
| OCR           | Google Vision with local cache  |
| Validation    | Plain Python validation scripts |
| Deployment    | Docker Compose only             |
| Testing       | Focused project-level tests     |

The system does not introduce distributed infrastructure, unnecessary databases, message queues, autonomous agents, or production hospital features.

This is appropriate because the project is an academic AI engineering demo, not a hospital SaaS platform.

---

# 21. Suitability for DEPI Evaluation

This architecture is suitable for DEPI because it demonstrates:

- Clear project scope
- Safe AI usage
- Grounded RAG workflow
- Citation-based answers
- Synthetic data handling
- Validation rules
- OCR integration
- Timeline retrieval
- Allergy history retrieval
- Docker-based reproducibility
- Clear team ownership
- Demo readiness

The architecture is easy to explain to evaluators and shows that the team understands both AI and software engineering.

---

# 22. Suitability for GitHub Portfolio

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

A reviewer can understand the project by reading the README, architecture documentation, API contract, and demo script.

---

# 23. Suitability for Academic AI Engineering

This architecture is suitable for academic AI engineering because it includes:

- Data generation
- Schema design
- Validation
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

# 24. Final Architecture Evaluation

## Score: 9.4 / 10

The architecture is strong, modular, practical, and suitable for the project goals.

## Strengths Behind the Score

- Clear folder responsibilities
- Strong team ownership boundaries
- Correct separation between structured data and LLM narrative generation
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
- SOAP README
- Optional frontend component separation

These are improvements, not major architectural problems.

---

# 25. Final Conclusion

The **AI-Based Clinical Record Summarization System** has a professional, practical, and academically appropriate architecture.

It is designed around the correct priorities:

```text
Data quality
→ validation correctness
→ retrieval quality
→ grounded generation
→ citation transparency
→ demo stability
```

The project is suitable for a five-member academic AI engineering team because each member owns a clear technical area and each folder maps naturally to real implementation responsibilities.

The architecture avoids unnecessary complexity while still demonstrating strong software engineering practice. It is suitable for DEPI evaluation, GitHub portfolio presentation, and academic AI engineering documentation.

The team should now proceed with implementation in the defined development order and must avoid scope creep during the final stages.
