# 1. Project Title

# AI-Based Clinical Record Summarization System

> A Retrieval-Augmented Generation (RAG) academic AI engineering project for retrieving, summarizing, and citing synthetic clinical records safely.

---

# 2. Project Overview

**AI-Based Clinical Record Summarization System** is an academic AI engineering project designed to demonstrate how Retrieval-Augmented Generation can support safe retrieval and summarization of **synthetic medical records**.

The system allows users to ask questions about a selected synthetic patient record, retrieve relevant information from local clinical data, generate grounded summaries, and display source citations for transparency.

This project is built for:

- DEPI graduation evaluation
- AI engineering portfolio presentation
- RAG system demonstration
- Academic software architecture practice
- Safe AI response design using synthetic data

The system does **not** diagnose, recommend treatment, predict disease, or perform medical inference. It only retrieves and summarizes documented information from available synthetic records.

---

# 3. Key Features

- 🔎 **RAG-Based Record Retrieval**
  Retrieves relevant synthetic patient record chunks using semantic search.

- 🧠 **Grounded Summarization**
  Generates answers only from retrieved patient records.

- 📌 **Source Citations**
  Displays supporting record sources for AI-generated answers.

- 🗓️ **Timeline Retrieval**
  Provides patient visit history and documented medical progression.

- ⚠️ **Allergy History Retrieval**
  Surfaces documented allergy information from synthetic records.

- 📄 **OCR-Supported Retrieval**
  Supports scanned document extraction using Google Vision OCR and local cache.

- 🖥️ **Streamlit Demo Interface**
  Provides an interactive frontend for project demonstration.

- 🚀 **FastAPI Backend**
  Exposes clean API endpoints for query, timeline, and summary workflows.

- 🐳 **Docker Reproducibility**
  Supports reproducible local execution using Docker Compose.

---

# 4. System Architecture Overview

```text
User
 │
 ▼
Streamlit Frontend
 │
 │ HTTP Request
 ▼
FastAPI Backend
 │
 │ Calls RAG Services
 ▼
RAG Engine
 │
 ├── Retrieval
 ├── Prompt Building
 ├── Answer Generation
 └── Citation Formatting
 │
 ▼
ChromaDB Vector Store
 │
 ▼
Synthetic Patient Records + OCR Cache
```

The system follows a modular academic prototype architecture:

- **Frontend:** Streamlit user interface
- **Backend:** FastAPI API layer
- **RAG Layer:** Retrieval, prompting, answer generation, citations
- **Vector Store:** Local ChromaDB database
- **Data Layer:** Synthetic JSON patient records
- **OCR Layer:** Google Vision OCR with offline cache support

Detailed architecture documentation is available in [`docs/architecture/`](docs/architecture/).

---

# 5. Tech Stack

| Area             | Technology             |
| ---------------- | ---------------------- |
| Language         | Python                 |
| Backend          | FastAPI                |
| Frontend         | Streamlit              |
| Vector Database  | ChromaDB               |
| Embeddings       | Sentence Transformers  |
| LLM Provider     | Groq API               |
| OCR              | Google Vision OCR      |
| Data Storage     | Local JSON files       |
| Containerization | Docker, Docker Compose |
| Testing          | Python test scripts    |

---

# 6. Simplified Repository Structure

```text
AI-Based-Clinical-Record-Summarization-System/
├── backend/        # FastAPI backend
├── frontend/       # Streamlit frontend
├── rag/            # Retrieval, prompts, answers, citations
├── ingestion/      # Chunking and ChromaDB ingestion
├── generators/     # Synthetic data generation
├── validators/     # Data validation scripts
├── ocr/            # OCR extraction and cache
├── data/           # Synthetic records and local ChromaDB
├── config/         # Shared constants, settings, prompts
├── scripts/        # Utility scripts
├── deployment/     # Docker files
├── docs/           # Detailed engineering documentation
├── tests/          # Validation, retrieval, and API tests
├── logs/           # Runtime logs
├── requirements.txt
└── README.md
```

Each major folder has a focused responsibility to support clean teamwork, maintainability, and demo stability.

---

# 7. RAG Pipeline Summary

```text
Synthetic Patient JSON
        │
        ▼
Validation
        │
        ▼
Chunking
        │
        ▼
Embedding
        │
        ▼
ChromaDB Storage
        │
        ▼
Semantic Retrieval
        │
        ▼
Prompt Construction
        │
        ▼
Groq LLM Answer
        │
        ▼
Citations Displayed
```

The project follows a **retrieval-first philosophy**:

> The system should retrieve the correct evidence before generating any answer.

All AI responses must be grounded in retrieved records and must include citations. Detailed RAG design is available in [`docs/rag/`](docs/rag/).

---

# 8. Quick Start

## Clone the Repository

```bash
git clone https://github.com/nhahub/NHA-4-121.git
cd AI-Based-Clinical-Record-Summarization-System
```

## Create a Virtual Environment

```bash
python -m venv .venv
```

## Activate the Environment

### Windows

```bash
.venv\Scripts\activate
```

### macOS / Linux

```bash
source .venv/bin/activate
```

## Install Dependencies

```bash
pip install -r requirements.txt
```

## Configure Environment Variables

```bash
cp .env.example .env
```

Update `.env` with your local settings and API keys.

## Validate Data

```bash
python scripts/validate_all.py
```

## Build the Vector Store

```bash
python scripts/reset_chromadb.py
python scripts/ingest_all.py
```

## Run Backend

```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

## Run Frontend

Open another terminal:

```bash
streamlit run frontend/app.py
```

Frontend:

```text
http://localhost:8501
```

Backend API docs:

```text
http://localhost:8000/docs
```

---

# 9. Docker Quick Start

Docker is used for reproducible local execution.

```bash
cd deployment
docker compose up --build
```

Expected services:

| Service            | URL                          |
| ------------------ | ---------------------------- |
| FastAPI Backend    | `http://localhost:8000`      |
| Streamlit Frontend | `http://localhost:8501`      |
| API Docs           | `http://localhost:8000/docs` |

Docker setup details are available in [`docs/docker/`](docs/docker/).

---

# 10. Example API Endpoints

| Method | Endpoint                 | Purpose                           |
| ------ | ------------------------ | --------------------------------- |
| `GET`  | `/health`                | Check backend status              |
| `GET`  | `/patients`              | List available synthetic patients |
| `POST` | `/query`                 | Ask a grounded RAG question       |
| `GET`  | `/timeline/{patient_id}` | Retrieve patient timeline         |
| `GET`  | `/summary/{patient_id}`  | Generate patient summary          |
| `GET`  | `/ocr/{doc_id}`          | Retrieve cached OCR text          |

## Example Query Request

```http
POST /query
```

```json
{
  "patient_id": "PAT-MOD-001",
  "query": "Does this patient have any recorded allergies?",
  "top_k": 5
}
```

## Example Response

```json
{
  "answer": "The retrieved records show a documented allergy in the patient's allergy registry.",
  "citations": [
    {
      "source_type": "allergy",
      "visit_id": "VST-MOD-001-002",
      "visit_date": "2024-02-15"
    }
  ],
  "safety_notice": "This answer is based only on retrieved synthetic patient records."
}
```

Full API documentation is available in [`docs/api/`](docs/api/).

---

# 11. Example Queries

```text
Summarize this patient's medical history.
```

```text
What medications has this patient been prescribed?
```

```text
Does this patient have any recorded allergies?
```

```text
Summarize this patient's HbA1c history.
```

```text
What happened during the latest visit?
```

```text
Show this patient's timeline.
```

```text
Summarize the scanned clinical note.
```

---

# 12. Documentation Structure

Detailed engineering documentation is stored inside the `docs/` directory.

```text
docs/
├── architecture/   # System architecture and module boundaries
├── rag/            # RAG pipeline, retrieval, prompts, citations
├── validation/     # Data schema and validation strategy
├── api/            # API contract and examples
├── ocr/            # OCR workflow and offline cache strategy
├── docker/         # Docker setup and local deployment
├── testing/        # Testing and evaluation strategy
├── workflow/       # Git workflow and team collaboration
├── demo/           # Demo script, showcase patients, fallback plan
└── reports/        # Final technical reports
```

Recommended documents:

| Area              | Document                                          |
| ----------------- | ------------------------------------------------- |
| Architecture      | `docs/architecture/System_Architecture.docx`      |
| Data & Validation | `docs/validation/Data_Generation_Validation.docx` |
| RAG               | `docs/rag/RAG_Pipeline_Design.docx`               |
| API               | `docs/api/API_Contract.docx`                      |
| OCR               | `docs/ocr/OCR_Architecture.docx`                  |
| Docker            | `docs/docker/Docker_Deployment_Guide.docx`        |
| Testing           | `docs/testing/Testing_Evaluation.docx`            |
| Workflow          | `docs/workflow/Team_Workflow_Git_Strategy.docx`   |
| Demo              | `docs/demo/Demo_Script.docx`                      |
| Safety            | `docs/architecture/Safety_and_Scope.docx`         |
| Final Report      | `docs/reports/Final_Technical_Report.docx`        |

---

# 13. Demo Highlights

The final demo focuses on a small number of stable, high-value scenarios:

1. **Grounded RAG Query**
   - Ask a clinical-record question and show an answer with citations.

2. **Allergy History Retrieval**
   - Retrieve documented allergy information from synthetic patient records.

3. **Timeline View**
   - Display patient visit history and progression.

4. **OCR Demo**
   - Show cached OCR text from a scanned document and retrieve answers from it.

5. **Lab Trend Summary**
   - Summarize documented lab values across visits.

Before the demo, run:

```bash
python scripts/validate_all.py
python scripts/ingest_all.py
python tests/test_retrieval.py
python scripts/warmup_demo.py
```

---

# 14. Safety & Scope Notice

This project uses **synthetic medical records only**.

The system is designed for academic demonstration and AI engineering evaluation.

## The System Does

- Retrieve documented synthetic patient information
- Summarize retrieved records
- Display source citations
- Support timeline and allergy history retrieval
- Support OCR-based document retrieval

## The System Does Not

- Diagnose diseases
- Recommend treatment
- Predict disease progression
- Infer undocumented conditions
- Replace clinical judgment
- Use real patient data
- Connect to real hospital infrastructure

All AI-generated answers must be grounded in retrieved records. If the required information is not found in the retrieved context, the system should state that the available records do not contain enough information.

---

# 15. Contributors

| Name          | Role                                | Main Responsibility                                                                                                                                          |
| ------------- | ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Ahmed Hesham  | Team Leader & Data Engineering Lead | Project coordination, synthetic patient data generation, schema design, validation pipeline (V1–V11), documentation organization, and overall demo readiness |
| [Member Name] | AI/RAG Engineer                     | RAG pipeline design, chunking strategy, embeddings, ChromaDB ingestion, retrieval workflow, prompt construction, grounded answer generation, and citations   |
| [Member Name] | Backend Developer                   | FastAPI backend development, API endpoints, service integration, request/response handling, and backend orchestration                                        |
| [Member Name] | Frontend & OCR Engineer             | Streamlit frontend development, OCR workflow integration, OCR cache handling, scanned document demo support, and frontend API integration                    |
| [Member Name] | DevOps & Testing Engineer           | Docker setup, Docker Compose orchestration, local deployment workflow, environment management, retrieval/API testing, and demo stability verification        |

Detailed workflow and ownership rules are available in [`docs/workflow/`](docs/workflow/).

---

# 16. Future Improvements

Potential post-demo improvements include:

- More synthetic patient records
- Better retrieval evaluation metrics
- Improved timeline visualization
- Enhanced OCR text cleaning
- Stronger automated testing
- More detailed citation inspection
- Optional reranking after baseline retrieval is stable
- Exportable summary reports

These improvements are intentionally outside the current MVP scope and should not compromise demo stability.

---

# 17. Contributors

This project was developed as part of a DEPI academic graduation project.

## Contributors

-Team Leader & Data Engineering Lead

- AI/RAG Engineer
- Backend Developer
- Frontend & OCR Engineer
- DevOps & Testing Engineer

---

# 18. License

This project is intended for academic and educational use.

Recommended license:

```text
MIT License
```

## Academic Disclaimer

This project is not a medical product, not a diagnostic system, and not a clinical decision support tool. It uses synthetic records only and is designed for academic AI engineering demonstration.

```

```
