# Running the Demo — Complete Implementation Guide

> **This guide covers everything from initial environment setup through ChromaDB ingestion,
> system testing, and live demo launch.**
> Follow each section in order for a clean first-time setup.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Clone and Set Up the Environment](#2-clone-and-set-up-the-environment)
3. [Configure API Keys](#3-configure-api-keys)
4. [Generate the Synthetic Dataset](#4-generate-the-synthetic-dataset)
5. [Validate the Dataset](#5-validate-the-dataset)
6. [Build and Ingest into ChromaDB](#6-build-and-ingest-into-chromadb)
7. [Verify ChromaDB Population](#7-verify-chromadb-population)
8. [Run the Step 14 Metadata Test Suite](#8-run-the-step-14-metadata-test-suite)
9. [Run the Step 15 Ingestion Test Suite](#9-run-the-step-15-ingestion-test-suite)
10. [Launch the System (Two Terminals)](#10-launch-the-system-two-terminals)
11. [Health Check](#11-health-check)
12. [Recommended Demo Sequence](#12-recommended-demo-sequence)
13. [OFFLINE_MODE Reference](#13-offline_mode-reference)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11 or 3.13 |
| pip | 23+ |
| Git | Any recent version |
| Internet | Required for Groq API (or use OFFLINE_MODE) |

No Docker, no database server, no GPU required.
ChromaDB runs locally and persists to disk.

---

## 2. Clone and Set Up the Environment

```bash
# 1. Clone the repository
git clone <repository-url>
cd AI-Based-Clinical-Record-Summarization-System

# 2. Create the virtual environment
python3 -m venv clinical-rag-env

# 3. Activate it
source clinical-rag-env/bin/activate

# 4. Install all dependencies
pip install -r requirements.txt
```

> **Every terminal you open** must activate the environment before running any command:
> ```bash
> source clinical-rag-env/bin/activate
> ```

---

## 3. Configure API Keys

The system uses the **Groq API** for LLM answer generation.
Retrieval from ChromaDB works without a key — only final answer synthesis requires it.

```bash
# Option A: export for the current shell session
export GROQ_API_KEY="gsk_your_key_here"

# Option B: create a .env file (persists across sessions)
cp .env.example .env
# Edit .env and set GROQ_API_KEY=gsk_your_key_here
```

The `.env` file is loaded automatically at backend startup.
If the key is absent, start the system in `OFFLINE_MODE=true` (see §13).

---

## 4. Generate the Synthetic Dataset

This step runs the deterministic 5-stage data generation pipeline and writes
15 patient JSON files to `data/patients/`.

```bash
source clinical-rag-env/bin/activate
PYTHONPATH=. python scripts/generate_all.py --mode v17_lite
```

**Expected output:**

```
  [Stage 1/5] Generating patient shells  [mode='v17_lite']
  [Stage 1/5] ✓ 15 patient shell(s) created.
  [Stage 2/5] Generating visit timelines
  [Stage 2/5] ✓ 65 visit(s) generated across 15 patient(s).
  [Stage 3/5] Generating medications
  [Stage 3/5] ✓ Medication records populated for all patients.
  [Stage 4/5] Generating lab results
  [Stage 4/5] ✓ Lab results populated for all patients.
  [Stage 5/5] Generating allergy registries
  [Stage 5/5] ✓ Allergy registries populated for all patients.
================================================================================
v1.7 Lite dataset generation complete (WRITE)
================================================================================
Patients generated: 15
Patients written:   15
Total visits:       65
...
```

To verify without writing files:
```bash
PYTHONPATH=. python scripts/generate_all.py --mode v17_lite --dry-run
```

---

## 5. Validate the Dataset

Run the V1–V12 validation gate against the generated JSON files.
This step must pass before ChromaDB ingestion.

```bash
source clinical-rag-env/bin/activate
PYTHONPATH=. python scripts/validate_all.py --mode v17_lite
```

All 12 rules must report `PASS`. If any fail, re-run Step 4 after fixing the
issue (generation is deterministic — failures indicate a configuration problem).

---

## 6. Build and Ingest into ChromaDB

This is the main pipeline script. It runs all 14 internal stages:

- Stages 1–5: Patient generation
- Stage 6: SOAP note generation
- Stage 7: SOAP audit
- Stage 8: V1–V12 validation
- Stage 9: Chunk building (148 chunks)
- Stage 10: Metadata building (148 metadata records)
- Stage 11: Pre-ingestion validation gate
- Stage 12: ChromaDB embed + upsert
- Stage 13: Post-ingestion smoke test
- Stage 14: Final report

```bash
source clinical-rag-env/bin/activate
PYTHONPATH=. python scripts/ingest_all.py --clean
```

> `--clean` resets the ChromaDB collection before ingesting.
> Always use `--clean` for a fresh or repeatable run.

**Expected final output:**

```
================================================================================
AI-Based Clinical Record Summarization System
Step 15 — ChromaDB Ingestion Complete
================================================================================
...
Chunk counts by source_type:
  doctor_note                    50
  lab_result                     31
  prescription                   50
  allergy                        15
  discharge_summary              1
  medication_reconciliation      1
  ────────────────────────────────────
  Total:                         148

Post-ingestion verification:
  ChromaDB collection count: 148 (matches expected 148)
  PAT-CHR-005 source_types:  allergy, discharge_summary, doctor_note, lab_result, ...
  Patient-scoped retrieval:  VERIFIED (no cross-patient contamination)
  Allergy retrieval:         VERIFIED (PAT-MOD-003 Aspirin found in top result)

Status: INGESTION COMPLETE
================================================================================
```

---

## 7. Verify ChromaDB Population

After ingestion, confirm ChromaDB contains exactly 148 chunks:

```bash
source clinical-rag-env/bin/activate
PYTHONPATH=. python3 -c "
from rag.retriever import _get_collection
col = _get_collection()
print(f'ChromaDB chunk count: {col.count()}')
assert col.count() == 148, 'Expected 148 chunks!'
print('Verification: PASS')
"
```

Expected output:
```
ChromaDB chunk count: 148
Verification: PASS
```

If ChromaDB is unavailable or empty, re-run §6 with `--clean`.

---

## 8. Run the Step 14 Metadata Test Suite

Validates all 148 metadata records against the ChromaDB contract
(field types, boolean enrichment, BP key prohibition, None value prohibition).

```bash
source clinical-rag-env/bin/activate
PYTHONPATH=. python scripts/test_step14.py
```

Expected output:
```
Chunks built: 148
Metadata records built: 148
All metadata records validated ✓
No BP keys in any metadata ✓
No None values in any metadata ✓
No list or dict values in any metadata ✓
All boolean fields are typed bool ✓

Integration test:            PASS
Scenario tests:              5/5 PASS
Negative tests:              4/4 PASS

Status: APPROVED FOR STEP 15 — CHROMADB INGESTION
```

---

## 9. Run the Step 15 Ingestion Test Suite

Confirms ChromaDB ingestion correctness: chunk count, field presence,
patient-scoped retrieval isolation, and allergy retrieval.

```bash
source clinical-rag-env/bin/activate
PYTHONPATH=. python scripts/test_step15.py
```

All checks must report `PASS` before launching the demo.

---

## 10. Launch the System (Two Terminals)

> **The backend and frontend are two separate processes.**
> They **must run in two separate terminal sessions**.
> Opening both in the same terminal will only run the first command —
> the second is never reached while the first is blocking.

### Terminal 1 — FastAPI Backend

```bash
source clinical-rag-env/bin/activate
PYTHONPATH=. uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

**Expected startup output:**

```
INFO:     Started server process [...]
INFO:     Waiting for application startup.
============================================================
AI-Based Clinical Record Summarization System
OFFLINE_MODE: False
Embedding model loaded ✓
============================================================
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

**Leave this terminal running.** Do not close it.

---

### Terminal 2 — Streamlit Frontend

Open a **new terminal** (new tab, new window, or a new `tmux` pane):

```bash
source clinical-rag-env/bin/activate
PYTHONPATH=. streamlit run frontend/app.py
```

**Expected startup output:**

```
You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://<your-ip>:8501
```

---

## 11. Health Check

Before opening the frontend, confirm the backend is healthy:

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{
  "status": "ok",
  "chromadb": "available",
  "chunk_count": 148,
  "offline_mode": false,
  "dataset_version": "v1.7-lite",
  "timestamp_utc": "..."
}
```

| URL | What you will see |
|---|---|
| `http://localhost:8000/` | JSON service info — name, status, docs link |
| `http://localhost:8000/docs` | Interactive Swagger UI — test all endpoints directly |
| `http://localhost:8000/health` | JSON health snapshot — ChromaDB status and chunk count |
| `http://localhost:8501` | Streamlit demo — patient selector, 5 tabs, citations |

If `"chromadb": "unavailable"`, re-run ingestion before continuing:
```bash
PYTHONPATH=. python scripts/ingest_all.py --clean
```

---

## 12. Recommended Demo Sequence

1. Confirm Terminal 1 shows `Application startup complete.`
2. Run `curl http://localhost:8000/health` — confirm `"status": "ok"` and `"chunk_count": 148`.
3. Open `http://localhost:8501` in your browser.
4. Select **PAT-CHR-001** from the sidebar patient selector.
5. **Tab 1 — Ask a Question:** ask *"What medications is this patient taking?"* — show the answer and expand Citation 1.
6. **Tab 2 — Visit Timeline:** show the 5 chronological visits with roles.
7. **Tab 3 — Allergy History:** show the documented allergy retrieval with safe label.
8. Switch patient to **PAT-MOD-003** — observe the sidebar update instantly.
9. **Tab 4 — Patient Summary:** click *Generate Summary* — show source type breakdown.
10. Switch to **PAT-CHR-005** and ask *"Was this patient ever hospitalized?"* — show the discharge summary citation.
11. Point out: all data comes from the backend; the frontend makes no direct ChromaDB or Groq calls.

---

## 13. OFFLINE_MODE Reference

The startup log line `OFFLINE_MODE: False` means live Groq LLM calls are active.

| Scenario | Action |
|---|---|
| `GROQ_API_KEY` is set and valid | No change needed — live answers work |
| `GROQ_API_KEY` is missing or expired | Set `OFFLINE_MODE=true` before starting |
| Rate-limited by Groq | Set `OFFLINE_MODE=true` temporarily |

To enable offline mode (retrieval still works; only LLM generation is skipped):

```bash
# Terminal 1 — backend in offline mode
OFFLINE_MODE=true PYTHONPATH=. uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — frontend in offline mode (shows yellow warning banner)
OFFLINE_MODE=true PYTHONPATH=. streamlit run frontend/app.py
```

In `OFFLINE_MODE=true`, the system still retrieves chunks from ChromaDB and returns
citations — only the final Groq answer synthesis is skipped.

---

## 14. Troubleshooting

### `ModuleNotFoundError` on any script

You forgot `PYTHONPATH=.`:
```bash
PYTHONPATH=. python scripts/<script>.py
```

### ChromaDB count is 0 or unavailable

Re-run ingestion with `--clean`:
```bash
PYTHONPATH=. python scripts/ingest_all.py --clean
```

### Backend starts but Groq calls fail with 401

Your API key is missing or expired.
```bash
export GROQ_API_KEY="gsk_your_key_here"
# then restart the backend
```
Or run in `OFFLINE_MODE=true`.

### Backend log shows `GET / HTTP/1.1 404` on startup

This is expected and harmless. The browser auto-requests `/` and `/favicon.ico`
when you visit any URL. The backend serves `/` with a JSON info response;
`/favicon.ico` 404 is normal — FastAPI does not serve static assets.

### `test_step14.py` or `test_step15.py` fails after a code change

Re-run ingestion to refresh ChromaDB with the updated logic:
```bash
PYTHONPATH=. python scripts/ingest_all.py --clean
```
Then re-run the test scripts.

### Frontend shows "Cannot connect to backend"

Confirm Terminal 1 is still running and the backend is on port 8000:
```bash
curl http://localhost:8000/health
```
If Terminal 1 was closed, restart it.

---

## Quick Reference — Command Summary

```bash
# Environment setup (once)
python3 -m venv clinical-rag-env
pip install -r requirements.txt

# Every session
source clinical-rag-env/bin/activate

# Full pipeline from scratch
PYTHONPATH=. python scripts/generate_all.py --mode v17_lite
PYTHONPATH=. python scripts/validate_all.py --mode v17_lite
PYTHONPATH=. python scripts/ingest_all.py --clean

# Test suites
PYTHONPATH=. python scripts/test_step14.py
PYTHONPATH=. python scripts/test_step15.py

# Verify ChromaDB
PYTHONPATH=. python3 -c "from rag.retriever import _get_collection; print(_get_collection().count(), 'chunks')"

# Launch (two separate terminals)
PYTHONPATH=. uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
PYTHONPATH=. streamlit run frontend/app.py

# Health check
curl http://localhost:8000/health
```
