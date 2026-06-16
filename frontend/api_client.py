"""
frontend/api_client.py  —  Step 20

Typed API client for the clinical RAG backend.

All HTTP calls go through this module. The Streamlit app never calls
`requests` directly. This makes the API contract explicit, testable
independently of the UI, and gives a single place to update timeouts
or base URLs.

Error contract:
  Every function returns a dict.
  On success: parsed JSON response dict.
  On any error: {"error": "<human-readable message>"}
  The Streamlit app checks `is_error(response)` before rendering.
"""

from __future__ import annotations

import requests

_TIMEOUT = 30  # seconds — never block indefinitely during demo


# ---------------------------------------------------------------------------
# Internal HTTP helpers
# ---------------------------------------------------------------------------

def _get(url: str) -> dict:
    try:
        r = requests.get(url, timeout=_TIMEOUT)
        if r.status_code >= 400:
            return {"error": f"Backend returned {r.status_code}: {r.text[:200]}"}
        return r.json()
    except requests.exceptions.ConnectionError:
        return {"error": "Backend unavailable. Is the FastAPI server running?"}
    except requests.exceptions.Timeout:
        return {"error": "Request timed out after 30 seconds."}
    except Exception as exc:
        return {"error": f"Unexpected error: {exc}"}


def _post(url: str, payload: dict) -> dict:
    try:
        r = requests.post(url, json=payload, timeout=_TIMEOUT)
        if r.status_code >= 400:
            return {"error": f"Backend returned {r.status_code}: {r.text[:200]}"}
        return r.json()
    except requests.exceptions.ConnectionError:
        return {"error": "Backend unavailable. Is the FastAPI server running?"}
    except requests.exceptions.Timeout:
        return {"error": "Request timed out after 30 seconds."}
    except Exception as exc:
        return {"error": f"Unexpected error: {exc}"}


# ---------------------------------------------------------------------------
# Public API client functions
# ---------------------------------------------------------------------------

def get_health(base_url: str) -> dict:
    """GET /health — system health and ChromaDB status."""
    return _get(f"{base_url.rstrip('/')}/health")


def get_patients(base_url: str) -> dict:
    """GET /patients — all 15 synthetic patients with summary metadata."""
    return _get(f"{base_url.rstrip('/')}/patients")


def get_timeline(patient_id: str, base_url: str) -> dict:
    """GET /timeline/{patient_id} — chronological visit history."""
    return _get(f"{base_url.rstrip('/')}/timeline/{patient_id}")


def get_summary(patient_id: str, base_url: str) -> dict:
    """GET /summary/{patient_id} — grounded patient summary from backend."""
    return _get(f"{base_url.rstrip('/')}/summary/{patient_id}")


def post_query(
    patient_id: str,
    question: str,
    base_url: str,
    top_k: int = 5,
    source_type_hint: str | None = None,
) -> dict:
    """POST /query — grounded RAG answer with citations."""
    payload: dict = {
        "patient_id": patient_id,
        "question": question,
        "top_k": top_k,
    }
    if source_type_hint is not None:
        payload["source_type_hint"] = source_type_hint
    return _post(f"{base_url.rstrip('/')}/query", payload)


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def is_error(response: dict) -> bool:
    """Return True if the response dict contains an error key."""
    return "error" in response


def get_error_message(response: dict) -> str:
    """Return the error message from an error response dict."""
    return response.get("error", "Unknown error")


__all__ = [
    "get_health",
    "get_patients",
    "get_timeline",
    "get_summary",
    "post_query",
    "is_error",
    "get_error_message",
]
