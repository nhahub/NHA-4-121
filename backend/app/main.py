"""
backend/app/main.py  —  Step 19

FastAPI app factory and startup configuration.

Environment variables are loaded from a .env file in the project root
automatically on startup. Shell exports always take precedence.

Start command:
    PYTHONPATH=. uvicorn backend.app.main:app --host 0.0.0.0 --port 8000

API docs:
    http://localhost:8000/docs
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Load .env from project root — must happen before any module reads env vars.
# override=False means shell exports always win over .env values.
# ---------------------------------------------------------------------------
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(dotenv_path=_env_path, override=False)
except ImportError:
    pass  # python-dotenv not installed — fall back to manual export

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes import router


def create_app() -> FastAPI:
    app = FastAPI(
        title="AI-Based Clinical Record Summarization System",
        description=(
            "Academic RAG system for safe retrieval, summarization, "
            "and citation of synthetic clinical records. "
            "This system does not diagnose, recommend treatment, or use real patient data."
        ),
        version="1.0.0",
    )

    # CORS — allow Streamlit frontend on localhost
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router, prefix="")
    return app


app = create_app()


@app.get("/", include_in_schema=False)
async def root() -> dict:
    """Static info route — eliminates 404 noise when a browser hits the base URL."""
    return {
        "service": "AI-Based Clinical Record Summarization System",
        "status": "running",
        "docs": "/docs",
        "health": "/health",
    }


@app.on_event("startup")
async def startup_event() -> None:
    """Log startup status and warm up the embedding model."""
    offline = os.environ.get("OFFLINE_MODE", "false").lower() == "true"
    groq_key_set  = bool(os.environ.get("GROQ_API_KEY"))
    gemini_key_set = bool(os.environ.get("GEMINI_API_KEY"))
    print("=" * 60)
    print("AI-Based Clinical Record Summarization System")
    print(f"OFFLINE_MODE:    {offline}")
    print(f"GROQ_API_KEY:    {'set ✓' if groq_key_set else 'NOT SET ✗  — queries will fail'}")
    print(f"GEMINI_API_KEY:  {'set ✓' if gemini_key_set else 'not set (fallback disabled)'}")
    print(f"LLM_PROVIDER:    {os.environ.get('LLM_PROVIDER', 'groq (default)')}")
    try:
        from rag.retriever import _get_model
        _get_model()
        print("Embedding model: loaded ✓")
    except Exception as exc:
        print(f"WARNING: Could not pre-load embedding model: {exc}")
    print("=" * 60)
