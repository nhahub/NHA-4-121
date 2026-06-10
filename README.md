# AI-Based Clinical Record Summarization System

> Academic Retrieval-Augmented Generation (RAG) system for safe retrieval, summarization, and citation of **synthetic clinical records**.

---

## 1. Project Overview

**AI-Based Clinical Record Summarization System** is a DEPI graduation project that demonstrates how Retrieval-Augmented Generation can retrieve and summarize synthetic clinical records while keeping answers grounded in documented evidence.

The system allows a user to select a synthetic patient, ask a question, retrieve relevant record chunks, generate a grounded answer, and display citations that point back to the supporting patient record evidence.

This project is built for:

- DEPI graduation evaluation
- Academic AI engineering demonstration
- RAG system architecture practice
- GitHub portfolio presentation
- Safe AI response design using synthetic data

This system **does not** diagnose, recommend treatment, prescribe medication, predict disease, infer undocumented conditions, use real patient data, or connect to real hospital infrastructure. It only retrieves and summarizes documented synthetic records.

---

## 2. Core Safety Rules

The following rules are locked for this project:

| Area | Rule |
|---|---|
| Medical safety | No diagnosis, treatment recommendation, prediction, or undocumented inference |
| Data source | Synthetic patient records only |
| Grounding | No retrieved evidence = no generated medical answer |
| Citations | Every generated answer must include supporting citations |
| Validation | Patient JSON files must pass validation before ingestion |
| Blood pressure | BP exists only inside `visit.vitals` |
| BP in labs | BP must never appear in `visit.labs` |
| BP in metadata | BP must never appear in ChromaDB metadata |
| Generators | Deterministic Python only; no LLM calls |
| SOAP | Deterministic template-based SOAP generation from structured facts only |
| RAG | LLM is used only for grounded answer generation from retrieved chunks |
| Architecture | No Kubernetes, microservices, PostgreSQL, Redis, Celery, LangGraph, or agent orchestration |

---

## 3. Key Features

- **Patient-scoped RAG retrieval** using ChromaDB and semantic search.
- **Grounded answer generation** using retrieved chunks only.
- **Source citations** for answer transparency.
- **Timeline retrieval** from chronological visit records.
- **Allergy history retrieval** from documented allergy records.
- **Lab trend retrieval** from structured lab result chunks.
- **Prescription retrieval** from visit medication records.
- **Deterministic SOAP notes** generated from structured JSON facts.
- **Retrieval enrichment layer** to improve semantic retrieval quality.
- **Retrieval enrichment auditor** to prevent unsupported enrichment text.
- **FastAPI backend** for query, timeline, summary, and health endpoints.
- **Streamlit frontend** for interactive academic demo.
- **Docker Compose local demo** for reproducible execution.

---

## 4. Tech Stack

| Area | Technology |
|---|---|
| Language | Python |
| Backend | FastAPI |
| Frontend | Streamlit |
| Vector Store | ChromaDB |
| Embeddings | Sentence Transformers |
| Answer LLM | Groq API |
| Data Storage | Local JSON files |
| Validation | Plain Python validation rules |
| Containerization | Docker, Docker Compose |

---

## 5. System Architecture

```text
Synthetic Patient Generation
        ↓
Validation V1–V11
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
Citations
        ↓
FastAPI Backend
        ↓
Streamlit Frontend
```

The architecture is intentionally modular and academic-demo friendly. It is designed for a small team with clear ownership boundaries and simple local reproducibility.

---

## 6. Repository Structure

```text
AI-Based-Clinical-Record-Summarization-System/
├── backend/        # FastAPI backend and API orchestration
├── config/         # Constants, paths, settings, prompts, showcase config
├── data/           # Patient JSON, schema, quarantine, ChromaDB
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
├── validators/     # V1–V11 validation rules and reports
├── requirements.txt
└── README.md
```

---

## 7. Data Pipeline

The data pipeline is deterministic and validation-gated.

```text
patient shells
→ visits
→ medications
→ labs
→ allergies
→ structured validation
→ SOAP generation
→ SOAP audit
→ final validation
→ approved export to data/patients
→ invalid export to data/quarantine
```

Important rules:

- `data/patients/` contains approved patient JSON files only.
- `data/quarantine/` contains invalid or blocked patient files and issue reports.
- `data/chromadb/` is runtime output produced by ingestion.
- Validation is the hard gate before ingestion.

---

## 8. Validation System

Validation rules are implemented as V1–V11.

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

Dataset-level checks are also run by `scripts/validate_all.py`:

- Expected patient count for `pilot` or `full` mode
- Expected tier distribution
- Duplicate `patient_id` detection
- CKD patient count limit

---

## 9. Locked Dataset Rules

| Domain | Locked Values / Rules |
|---|---|
| Dataset size | Pilot: 5 patients; Full: 30 patients |
| Full distribution | 10 normal, 13 moderate, 7 chronic |
| Conditions | `T2DM`, `HTN`, `Asthma`, `IDA`, `GERD`, `CKD` |
| CKD | Chronic-tier only; must co-occur with `T2DM` and `HTN`; max 2 patients |
| Visit types | `initial`, `follow_up`, `emergency`, `hospitalization` |
| Lab types | `HbA1c`, `FBG`, `Creatinine`, `Hemoglobin`, `Ferritin` |
| Medication routes | `oral`, `inhaled` |
| Source types | `doctor_note`, `lab_result`, `prescription`, `allergy` |
| BP location | `visit.vitals.bp_systolic` and `visit.vitals.bp_diastolic` only |
| Forbidden BP locations | labs, lab type enum, ChromaDB metadata, duplicate shadow fields |

---

## 10. SOAP Generation

SOAP notes are generated deterministically from structured JSON facts.

```text
Structured patient JSON
        ↓
SOAP fact context
        ↓
Deterministic template selection
        ↓
Template rendering
        ↓
SOAP note dictionary
        ↓
SOAP audit
```

SOAP rules:

- No LLM calls in the current SOAP implementation.
- No randomization.
- No Python built-in `hash()` for selection.
- No medical fact generation.
- No diagnosis inference.
- No medication selection.
- No lab selection.
- No structured data mutation.
- SOAP text must preserve structured patient facts exactly.

---

## 11. Retrieval Enrichment Layer

Retrieval enrichment improves semantic retrieval quality without changing the source of truth.

Relevant files:

```text
ingestion/retrieval_enricher.py
ingestion/retrieval_enrichment_auditor.py
```

Supported source types:

```text
doctor_note
lab_result
prescription
allergy
```

Rules:

- Enrichment text is **retrieval support only**.
- Structured patient JSON and SOAP notes remain the source of truth.
- Enrichment must be deterministic.
- Enrichment must not call an LLM.
- Enrichment must not build metadata, embeddings, chunks, or ChromaDB records.
- Enrichment must be audited before it is appended to chunks or ingested.
- BP must not be added to ChromaDB metadata.

---

## 12. RAG Pipeline

```text
User query
        ↓
FastAPI /query
        ↓
Patient-scoped retrieval
        ↓
ChromaDB top-k chunks
        ↓
Grounding check
        ↓
Prompt construction
        ↓
Groq LLM answer
        ↓
Citation formatting
        ↓
Streamlit display
```

RAG rules:

- Retrieval must be patient-scoped.
- Allergy queries should prioritize `allergy` chunks.
- Medication queries should prioritize `prescription` chunks.
- Lab trend queries should prioritize `lab_result` chunks.
- BP queries should retrieve `doctor_note` chunks because BP is present in SOAP objective text, not metadata.
- If retrieved chunks do not support the question, the answer should clearly say that the available records do not contain enough evidence.

---

## 13. Quick Start

### 13.1 Clone Repository

```bash
git clone https://github.com/nhahub/NHA-4-121.git
cd AI-Based-Clinical-Record-Summarization-System
```

### 13.2 Create Virtual Environment

```bash
python -m venv .venv
```

Windows:

```bash
.venv\Scripts\activate
```

macOS / Linux:

```bash
source .venv/bin/activate
```

### 13.3 Install Dependencies

```bash
pip install -r requirements.txt
```

### 13.4 Configure Environment

```bash
cp .env.example .env
```

Set required values such as:

```text
GROQ_API_KEY=
```

---

## 14. Full Local Pipeline

Run the full dataset pipeline from the project root.

### 14.1 Generate Full Dataset

```bash
python scripts/generate_all.py --mode full --clean
```

### 14.2 Validate Dataset

```bash
python scripts/validate_all.py --mode full
```

### 14.3 Dry-Run SOAP Regeneration

```bash
python scripts/generate_soap.py --dry-run
```

### 14.4 Generate SOAP Notes

```bash
python scripts/generate_soap.py
```

### 14.5 Final Validation

```bash
python scripts/validate_all.py --mode full
```

### 14.6 Build Vector Store

```bash
python scripts/reset_chromadb.py
python scripts/ingest_all.py
```

### 14.7 Test Retrieval

```bash
python tests/test_retrieval.py
```

---

## 15. Pilot Pipeline

For a small 5-patient development dataset:

```bash
python scripts/generate_all.py --mode pilot --clean
python scripts/validate_all.py --mode pilot
python scripts/generate_soap.py --dry-run
python scripts/generate_soap.py
python scripts/validate_all.py --mode pilot
```

---

## 16. Run Backend and Frontend

### Backend

```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend API docs:

```text
http://localhost:8000/docs
```

### Frontend

Open another terminal:

```bash
streamlit run frontend/app.py
```

Frontend URL:

```text
http://localhost:8501
```

---

## 17. Docker Quick Start

Docker is used for reproducible local demo execution.

```bash
cd deployment
docker compose up --build
```

Expected services:

| Service | URL |
|---|---|
| FastAPI Backend | `http://localhost:8000` |
| Streamlit Frontend | `http://localhost:8501` |
| API Docs | `http://localhost:8000/docs` |

Docker must remain local-first and simple. This project does not use Kubernetes, cloud orchestration, Redis, Celery, or microservices.

---

## 18. API Endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| `GET` | `/health` | Check backend and runtime status |
| `GET` | `/patients` | List available synthetic patients |
| `POST` | `/query` | Ask a grounded RAG question |
| `GET` | `/timeline/{patient_id}` | Retrieve chronological patient visit history |
| `GET` | `/summary/{patient_id}` | Generate grounded patient summary |
Example query request:

```json
{
  "patient_id": "PAT-MOD-001",
  "question": "What medications are documented for this patient?"
}
```

Expected response shape:

```json
{
  "answer": "Grounded answer based on retrieved records.",
  "citations": [
    {
      "patient_id": "PAT-MOD-001",
      "visit_id": "VST-MOD-001-001",
      "visit_date": "2023-01-10",
      "source_type": "prescription",
      "chunk_id": "VST-MOD-001-001-prescription-01"
    }
  ]
}
```

---

## 19. Demo Workflow

Recommended demo sequence:

1. Start backend.
2. Start frontend.
3. Select a showcase patient.
4. Ask a RAG question.
5. Show grounded answer.
6. Show citations.
7. Open timeline view.
8. Show chronological visit history.
9. Ask an allergy-history question.
10. Show documented allergy retrieval.
11. Open patient summary view.
12. Show grounded patient summary.
13. Demonstrate citation transparency.

Demo rules:

- Use showcase patients only.
- Use rehearsed queries.
- Keep fallback screenshots ready.
- Do not claim diagnosis, treatment recommendation, prediction, or clinical decision support.
- Use wording such as “retrieves documented records” and “summarizes available synthetic records.”

---

## 20. Important Documentation

| Document | Purpose |
|---|---|
| `docs/architecture_summary.md` | High-level system architecture |
| `docs/team_ownership_and_architecture.md` | Team ownership and folder responsibilities |
| `docs/project_scope_and_safety_rules.md` | Medical safety and scope boundaries |
| `docs/data_schema_contract.md` | Patient JSON schema handoff contract |
| `docs/validation_rules.md` | V1–V11 validation rule explanation |
| `docs/data_generation_pipeline.md` | Data generation and validation workflow |
| `docs/rag_handoff_contract.md` | Data-to-RAG handoff for AI/RAG engineer |
| `docs/retrieval_enrichment_contract.md` | Retrieval enrichment layer contract |
| `docs/chunking_and_metadata_contract.md` | Chunk and metadata rules |
| `docs/rag_pipeline.md` | End-to-end RAG behavior |
| `docs/citation_contract.md` | Citation object and display format |
| `docs/api_contract.md` | API request/response contract |
| `docs/demo_script.md` | Final demo script |
| `docs/fallback_plan.md` | Demo fallback and recovery plan |
| `docs/llm_project_context.md` | Compact context file for LLM tools used by the team |

---
## 21. Team Ownership Summary

| Area | Primary Owner |
|---|---|
| `config/` | Ahmed Hesham |
| `data/` | Ahmed Hesham |
| `generators/` | Ahmed Hesham |
| `validators/` | Ahmed Hesham |
| `soap/` | Ahmed Hesham |
| `docs/` | Ahmed Hesham with team input |
| `ingestion/` | Gamal Mohamed Gad |
| `rag/` | Gamal Mohamed Gad |
| `backend/` | Youssef Yassin Ibrahim |
| `frontend/` | Youssef Yassin Ibrahim |
| `deployment/` | Mahmoud Mohamed El Faham |
| `tests/` | Mahmoud Mohamed El Faham with all members |

---

## 22. Development Order

```text
1. Lock constants and schema
2. Implement validation rules V1–V11
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

## 23. Testing Commands

```bash
python -m py_compile config/*.py
python -m py_compile generators/*.py
python -m py_compile validators/*.py
python -m py_compile soap/*.py
python -m py_compile ingestion/*.py
python -m py_compile scripts/*.py
```

Dataset validation:

```bash
python scripts/validate_all.py --mode full
```

Retrieval enrichment debug:

```bash
python scripts/check_retrieval_enricher_output.py --patient-id PAT-MOD-001 --visit-index 0
```

Backend smoke test:

```bash
curl http://localhost:8000/health
```

---

## 24. Project Status

Current implementation direction:

```text
Status: Academic DEPI RAG demo
Architecture: Local-first, modular, validation-gated
Dataset: Synthetic patient JSON records
Validation: V1–V11 + dataset-level checks
SOAP: Deterministic template-based generation
RAG: Patient-scoped, citation-based, grounded answers
Demo: Streamlit + FastAPI + ChromaDB
```

---

## 25. License

This project is intended for academic learning, DEPI evaluation, and portfolio demonstration. It must not be used for real clinical care, diagnosis, treatment, or medical decision-making.
