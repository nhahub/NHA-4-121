# Running the Demo — Two-Terminal Runbook

> **Important:** The backend and frontend are two separate processes.  
> They **must run in two separate terminal sessions** (or two `tmux` panes).  
> Typing both commands sequentially into the same terminal will only run
> the first command — the second is never reached while the first is blocking.

---

## Prerequisites

```bash
# Activate the virtual environment in EVERY terminal you open
source clinical-rag-env/bin/activate

# Verify ChromaDB is populated (should print 148)
PYTHONPATH=. python3 -c "from rag.retriever import _get_collection; print(_get_collection().count(), 'chunks')"
```

---

## Terminal 1 — Start the FastAPI Backend

```bash
# Open a dedicated terminal, activate the environment, then run:
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

## Terminal 2 — Start the Streamlit Frontend

Open a **second** terminal (new tab, new window, or a new `tmux` pane):

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

## Quick Health Check

Before opening the frontend, verify the backend is healthy:

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

If `chromadb` is `"unavailable"`, re-run the ingestion script before continuing:

```bash
PYTHONPATH=. python3 scripts/ingest_all.py --clean
```

---

## URLs to Open

| URL | What you will see |
|---|---|
| `http://localhost:8000/` | `{"service": "...", "status": "running", "docs": "/docs", "health": "/health"}` |
| `http://localhost:8000/docs` | Interactive Swagger UI — test all 5 endpoints directly |
| `http://localhost:8000/health` | JSON health snapshot — ChromaDB status and chunk count |
| `http://localhost:8501` | Streamlit demo — patient selector, 5 tabs, citations |

---

## About the 404 Lines (Expected — Not an Error)

You may see these two lines in the backend log when a browser first opens `http://localhost:8000`:

```
INFO: ... "GET / HTTP/1.1" 404 Not Found
INFO: ... "GET /favicon.ico HTTP/1.1" 404 Not Found
```

These are **not errors**. They appear because:

- The browser automatically requests `/` and `/favicon.ico` when you open any URL.
- The backend previously had no route registered for `/`.

**This is now fixed.** The updated `backend/app/main.py` adds a static root route at `GET /` that returns a friendly JSON info message. The `/favicon.ico` 404 is still expected and harmless — FastAPI does not serve static assets, and it does not affect functionality.

---

## OFFLINE_MODE

The startup log line `OFFLINE_MODE: False` means **live Groq calls are active**.

| Scenario | Action |
|---|---|
| `GROQ_API_KEY` is set and valid | No change needed — live answers work |
| `GROQ_API_KEY` is missing or rate-limited | Set `OFFLINE_MODE=true` before starting the backend |

To enable offline mode:

```bash
# Terminal 1 — backend in offline mode
OFFLINE_MODE=true PYTHONPATH=. uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

# Terminal 2 — frontend in offline mode (shows banner in UI)
OFFLINE_MODE=true PYTHONPATH=. streamlit run frontend/app.py
```

In `OFFLINE_MODE=true`, the system still retrieves chunks from ChromaDB and returns citations — only the Groq LLM answer generation is skipped. The frontend shows a yellow warning banner.

To set your Groq API key:

```bash
export GROQ_API_KEY="your-key-here"
```

Or create a `.env` file and load it before starting:

```bash
echo "GROQ_API_KEY=your-key-here" > .env
export $(cat .env)
```

---

## Recommended Demo Sequence

1. Confirm Terminal 1 shows `Application startup complete.`
2. Run `curl http://localhost:8000/health` — confirm `"status": "ok"`.
3. Open `http://localhost:8501` in your browser.
4. Select **PAT-CHR-001** from the sidebar patient selector.
5. **Tab 1 — Ask a Question:** ask *"What medications is this patient taking?"* — show the answer and expand Citation 1.
6. **Tab 2 — Visit Timeline:** show the 5 chronological visits with roles.
7. **Tab 3 — Allergy History:** show documented allergy retrieval with safe label.
8. Switch patient to **PAT-MOD-003** — observe the sidebar update.
9. **Tab 4 — Patient Summary:** click *Generate Summary* — show source type breakdown.
10. Point out: all data comes from the backend; no direct ChromaDB or Groq calls from the frontend.
