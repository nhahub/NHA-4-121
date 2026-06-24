# API Contract

This document outlines the exact API boundaries established by the FastAPI backend for the AI-Based Clinical Record Summarization System. 

It is generated directly from the current backend implementation and serves as the official integration contract between the backend layer and the frontend Streamlit application.

---

## 1. Current Implemented APIs

The following APIs are currently implemented and available in the `backend/app` module.

### `GET /`

* **Method**: `GET`
* **Path**: `/`
* **Purpose**: Static info route to provide basic service details and eliminate 404 noise when navigating to the base URL.
* **Path Parameters**: None
* **Query Parameters**: None
* **Request Body Schema**: None
* **Response Schema**:
  ```json
  {
      "service": "AI-Based Clinical Record Summarization System",
      "status": "running",
      "docs": "/docs",
      "health": "/health"
  }
  ```

---

### `POST /query`

* **Method**: `POST`
* **Path**: `/query`
* **Purpose**: Ask a grounded RAG question about a specific patient. The backend validates `patient_id` and enforces patient-level scoping.
* **Path Parameters**: None
* **Query Parameters**: None
* **Request Body Schema** (`QueryRequest`):
  ```json
  {
      "patient_id": "string (Matches regex: ^PAT-(NRM|MOD|CHR)-\\d{3}$)",
      "question": "string (min_length=5)",
      "top_k": "integer (1-20, default=5)",
      "source_type_hint": "string | null (Must be a valid source type if provided)"
  }
  ```
* **Response Schema** (`QueryResponse`):
  ```json
  {
      "patient_id": "string",
      "question": "string",
      "answer": "string",
      "citations": [
          {
              "chunk_id": "string",
              "patient_id": "string",
              "visit_id": "string | null",
              "visit_date": "string | null",
              "source_type": "string",
              "visit_role": "string | null",
              "excerpt": "string"
          }
      ],
      "grounded": "boolean",
      "chunks_used": "integer",
      "no_evidence": "boolean",
      "model_name": "string",
      "timestamp_utc": "string"
  }
  ```

---

### `GET /patients`

* **Method**: `GET`
* **Path**: `/patients`
* **Purpose**: Return summary metadata for all 15 synthetic patients currently available in the system.
* **Path Parameters**: None
* **Query Parameters**: None
* **Request Body Schema**: None
* **Response Schema** (`PatientsResponse`):
  ```json
  {
      "total": "integer",
      "patients": [
          {
              "patient_id": "string",
              "conditions": ["string"],
              "tier": "string",
              "total_visits": "integer",
              "has_allergy": "boolean",
              "semantic_focus": "string",
              "timeline_pattern": "string"
          }
      ]
  }
  ```

---

### `GET /timeline/{patient_id}`

* **Method**: `GET`
* **Path**: `/timeline/{patient_id}`
* **Purpose**: Return chronological visit history reconstructed from the structured patient JSON timeline.
* **Path Parameters**: 
  * `patient_id` (string): The ID of the patient to retrieve the timeline for.
* **Query Parameters**: None
* **Request Body Schema**: None
* **Response Schema** (`TimelineResponse`):
  ```json
  {
      "patient_id": "string",
      "total_visits": "integer",
      "visits": [
          {
              "visit_id": "string",
              "visit_date": "string",
              "visit_type": "string",
              "visit_role": "string",
              "diagnoses": ["string"],
              "has_labs": "boolean",
              "has_medications": "boolean",
              "clinical_event_label": "string"
          }
      ]
  }
  ```
* **Error Responses**:
  * `404 Not Found`: Returned if the requested `patient_id` is not found.

---

### `GET /summary/{patient_id}`

* **Method**: `GET`
* **Path**: `/summary/{patient_id}`
* **Purpose**: Generate a grounded patient summary by running a fixed overarching RAG query across all `source_types` for the patient.
* **Path Parameters**: 
  * `patient_id` (string): The ID of the patient to summarize.
* **Query Parameters**: None
* **Request Body Schema**: None
* **Response Schema** (`QueryResponse`): 
  * Returns the same structure as `POST /query`.
* **Error Responses**:
  * `404 Not Found`: Returned if the requested `patient_id` is not found.

---

### `GET /health`

* **Method**: `GET`
* **Path**: `/health`
* **Purpose**: System health check. Verifies the status of ChromaDB and data availability.
* **Path Parameters**: None
* **Query Parameters**: None
* **Request Body Schema**: None
* **Response Schema** (`HealthResponse`):
  ```json
  {
      "status": "string ('ok' or 'degraded')",
      "chromadb": "string ('available' or 'unavailable')",
      "chunk_count": "integer",
      "offline_mode": "boolean",
      "dataset_version": "string",
      "timestamp_utc": "string"
  }
  ```

---

## 2. Future Expansion (Not Yet Implemented)

The following endpoints are PLANNED ONLY — NOT IMPLEMENTED. They represent potential avenues for future enhancements to the system if clinical use-cases expand.

* `POST /login`: User authentication for clinicians (PLANNED ONLY — NOT IMPLEMENTED)
* `POST /register`: New user registration (PLANNED ONLY — NOT IMPLEMENTED)
* `POST /feedback`: Clinician feedback submission on LLM answers (PLANNED ONLY — NOT IMPLEMENTED)
* `GET /history`: Retrieval of past RAG queries (PLANNED ONLY — NOT IMPLEMENTED)
