"""
frontend/dev_rag_chat.py

Developer-only Streamlit page for testing the clinical RAG pipeline.

Run from project root:

    streamlit run frontend/dev_rag_chat.py

Purpose:
    This page is a lightweight RAG testing console, not the final demo UI.
    It helps Ahmed, Gamal, and the backend/frontend team inspect retrieval,
    prompt construction, answer generation, citations, and chunk evidence while
    the RAG layer is still being implemented.

What this page does:
    - Selects one patient from data/patients/.
    - Accepts a patient-scoped question.
    - Runs retrieval + prompt preview without LLM by default.
    - Optionally calls the LLM through rag.answer_generator if rag/llm_client.py
      is implemented.
    - Displays answer, citation seeds, retrieved chunks, metadata, and prompt
      debug information.

What this page must not do:
    - It must not write to ChromaDB.
    - It must not ingest files.
    - It must not mutate patient JSON files.
    - It must not read data/quarantine/.
    - It must not bypass patient-scoped retrieval.
    - It must not be treated as the final Streamlit frontend.

Expected dependencies:
    - data/patients/*.json already generated and validated.
    - ChromaDB already populated by `python -m ingestion.ingest --reset`.
    - rag/retriever.py and rag/answer_generator.py available.
    - rag/llm_client.py optional. Preview mode works without it.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import streamlit as st

# Allow running with: streamlit run frontend/dev_rag_chat.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.constants import SOURCE_TYPES  # noqa: E402
from config.paths import PATIENTS_DIR  # noqa: E402
from rag.answer_generator import (  # noqa: E402
    AnswerGenerationError,
    AnswerGeneratorConfig,
    build_answer_preview_without_llm,
    generate_answer,
)
from rag.retriever import DEFAULT_TOP_K, RetrievalError  # noqa: E402


PAGE_TITLE = "Dev RAG Testing Chat"
PAGE_ICON = "🧪"
DEFAULT_QUERY = "What happened during the latest documented visit?"
DEFAULT_PREVIEW_ONLY = True
MAX_PATIENT_LABEL_CHARS = 90


@dataclass(frozen=True)
class PatientOption:
    """Small display object for patient selection."""

    patient_id: str
    name: str
    tier: str
    conditions: tuple[str, ...]
    path: Path

    @property
    def label(self) -> str:
        conditions_text = ", ".join(self.conditions) if self.conditions else "no chronic conditions"
        raw = f"{self.patient_id} — {self.name} — {self.tier} — {conditions_text}"
        return _truncate(raw, MAX_PATIENT_LABEL_CHARS)


# ---------------------------------------------------------------------
# Streamlit page
# ---------------------------------------------------------------------


def main() -> None:
    """Render the dev RAG chat page."""
    st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout="wide")

    st.title(f"{PAGE_ICON} {PAGE_TITLE}")
    st.caption(
        "Developer-only page for testing patient-scoped retrieval, prompts, "
        "citations, and grounded RAG answers. This is not the final demo UI."
    )

    _render_safety_notice()

    patient_options = load_patient_options(PATIENTS_DIR)
    if not patient_options:
        st.error(
            "No approved patient files found in data/patients/. "
            "Run `python scripts/generate_all.py --mode pilot --clean` first."
        )
        return

    settings = _render_sidebar(patient_options)
    selected_patient = settings["patient"]

    st.subheader("Patient scope")
    _render_patient_scope(selected_patient)

    if "rag_chat_history" not in st.session_state:
        st.session_state.rag_chat_history = []

    _render_history_controls()
    _render_chat_history()

    query_text = st.chat_input("Ask a patient-scoped RAG question...")

    with st.form("manual_query_form"):
        manual_query = st.text_area(
            "Or type a query here",
            value=DEFAULT_QUERY,
            height=90,
            help="Use this form if chat_input is not convenient in your browser.",
        )
        submitted = st.form_submit_button("Run query")

    final_query = query_text or (manual_query if submitted else "")

    if final_query:
        _run_and_render_query(
            query_text=final_query,
            patient=selected_patient,
            source_types=settings["source_types"],
            top_k=settings["top_k"],
            preview_only=settings["preview_only"],
            route_source_types=settings["route_source_types"],
            return_debug=settings["return_debug"],
        )


# ---------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------


def _render_safety_notice() -> None:
    with st.expander("Safety and scope reminder", expanded=False):
        st.markdown(
            """
This page is for **development testing only**.

Rules:
- Every query must be scoped to one selected `patient_id`.
- No retrieved evidence means no generated medical answer.
- The answer must be based only on retrieved chunks.
- The system must not diagnose, prescribe, predict, or infer undocumented facts.
- BP may appear in retrieved doctor-note text, but must not be used as metadata.
- Do not use this page as the final Streamlit frontend.
"""
        )


def _render_sidebar(patient_options: list[PatientOption]) -> dict[str, Any]:
    st.sidebar.header("RAG settings")

    patient_by_label = {patient.label: patient for patient in patient_options}
    selected_label = st.sidebar.selectbox(
        "Patient",
        options=list(patient_by_label),
        index=0,
        help="Retrieval must always be scoped to one approved patient.",
    )

    selected_source_types = st.sidebar.multiselect(
        "source_type filter",
        options=list(SOURCE_TYPES),
        default=[],
        help="Leave empty to retrieve from all source types. Use this for focused debugging.",
    )

    top_k = st.sidebar.slider(
        "Top K",
        min_value=1,
        max_value=12,
        value=DEFAULT_TOP_K,
        step=1,
        help="Number of chunks requested from ChromaDB.",
    )

    route_source_types = st.sidebar.checkbox(
        "Auto-route source types",
        value=False,
        help="Uses lightweight keyword routing if no source_type filter is selected.",
    )

    preview_only = st.sidebar.checkbox(
        "Preview only — do not call LLM",
        value=DEFAULT_PREVIEW_ONLY,
        help="Recommended until rag/llm_client.py is implemented and tested.",
    )

    return_debug = st.sidebar.checkbox(
        "Show prompt/debug payload",
        value=True,
        help="Shows prompt context, metadata, and retrieved chunk debug information.",
    )

    st.sidebar.divider()
    st.sidebar.caption("Required setup")
    st.sidebar.code(
        "python scripts/generate_all.py --mode pilot --clean\n"
        "python scripts/validate_all.py --mode pilot\n"
        "python -m ingestion.ingest --reset\n"
        "streamlit run frontend/dev_rag_chat.py",
        language="bash",
    )

    return {
        "patient": patient_by_label[selected_label],
        "source_types": tuple(selected_source_types) or None,
        "top_k": top_k,
        "route_source_types": route_source_types,
        "preview_only": preview_only,
        "return_debug": return_debug,
    }


def _render_patient_scope(patient: PatientOption) -> None:
    columns = st.columns(4)
    columns[0].metric("patient_id", patient.patient_id)
    columns[1].metric("tier", patient.tier or "unknown")
    columns[2].metric("conditions", len(patient.conditions))
    columns[3].metric("file", patient.path.name)

    if patient.conditions:
        st.write("Conditions:", ", ".join(patient.conditions))
    else:
        st.write("Conditions: no chronic conditions")


def _render_history_controls() -> None:
    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("Clear history"):
            st.session_state.rag_chat_history = []
            st.rerun()
    with col2:
        st.caption("Chat history is stored only in Streamlit session state.")


def _render_chat_history() -> None:
    for item in st.session_state.rag_chat_history:
        with st.chat_message("user"):
            st.write(item["query"])
        with st.chat_message("assistant"):
            st.write(item["answer"])
            if item.get("citation_count") is not None:
                st.caption(f"Citations: {item['citation_count']} | Used LLM: {item.get('used_llm')}")


def _run_and_render_query(
    *,
    query_text: str,
    patient: PatientOption,
    source_types: tuple[str, ...] | None,
    top_k: int,
    preview_only: bool,
    route_source_types: bool,
    return_debug: bool,
) -> None:
    query_text = query_text.strip()
    if not query_text:
        st.warning("Query is empty.")
        return

    with st.chat_message("user"):
        st.write(query_text)

    with st.spinner("Running patient-scoped RAG..."):
        try:
            config = AnswerGeneratorConfig(
                top_k=top_k,
                route_source_types=route_source_types,
            )

            if preview_only:
                result = build_answer_preview_without_llm(
                    query_text=query_text,
                    patient_id=patient.patient_id,
                    source_types=source_types,
                    top_k=top_k,
                    config=config,
                    return_debug=return_debug,
                )
            else:
                result = generate_answer(
                    query_text=query_text,
                    patient_id=patient.patient_id,
                    source_types=source_types,
                    top_k=top_k,
                    config=config,
                    return_debug=return_debug,
                )
        except (RetrievalError, AnswerGenerationError) as exc:
            _render_error(query_text=query_text, patient_id=patient.patient_id, exc=exc)
            return
        except Exception as exc:  # Keep dev page alive while integrations evolve.
            _render_error(query_text=query_text, patient_id=patient.patient_id, exc=exc)
            return

    payload = result.to_dict()

    with st.chat_message("assistant"):
        _render_answer_payload(payload)

    st.session_state.rag_chat_history.append(
        {
            "query": query_text,
            "answer": payload.get("answer", ""),
            "citation_count": payload.get("citation_count"),
            "used_llm": payload.get("used_llm"),
        }
    )


def _render_answer_payload(payload: dict[str, Any]) -> None:
    st.subheader("Answer")

    if payload.get("error"):
        st.error(payload["error"])

    if not payload.get("has_evidence"):
        st.warning("No retrieved evidence was available for this query.")

    if not payload.get("used_llm"):
        st.info("LLM was not called. This is retrieval/prompt preview mode.")

    st.write(payload.get("answer", ""))

    metrics = st.columns(4)
    metrics[0].metric("has_evidence", str(payload.get("has_evidence")))
    metrics[1].metric("used_llm", str(payload.get("used_llm")))
    metrics[2].metric("citations", payload.get("citation_count", 0))
    metrics[3].metric("retrieved_chunks", len(payload.get("retrieved_chunks", [])))

    _render_citations(payload.get("citations", []))
    _render_retrieved_chunks(payload.get("retrieved_chunks", []))
    _render_prompt_debug(payload.get("prompt"))
    _render_raw_payload(payload)


def _render_citations(citations: list[dict[str, Any]]) -> None:
    st.subheader("Citation seeds")
    if not citations:
        st.caption("No citation seeds available.")
        return

    display_rows = []
    for citation in citations:
        display_rows.append(
            {
                "context_id": citation.get("context_id"),
                "chunk_id": citation.get("chunk_id"),
                "source_type": citation.get("source_type"),
                "visit_id": citation.get("visit_id"),
                "visit_date": citation.get("visit_date"),
                "rank": citation.get("rank"),
                "score": citation.get("score"),
            }
        )

    st.dataframe(display_rows, use_container_width=True, hide_index=True)

    with st.expander("Citation evidence excerpts", expanded=False):
        for citation in citations:
            st.markdown(f"**{citation.get('context_id', '')} — {citation.get('chunk_id', '')}**")
            st.write(citation.get("evidence_excerpt", ""))


def _render_retrieved_chunks(chunks: list[dict[str, Any]]) -> None:
    st.subheader("Retrieved chunks")
    if not chunks:
        st.caption("No chunks retrieved.")
        return

    for chunk in chunks:
        title = (
            f"#{chunk.get('rank')} | {chunk.get('source_type')} | "
            f"{chunk.get('chunk_id')} | score={_format_score(chunk.get('score'))}"
        )
        with st.expander(title, expanded=False):
            st.markdown("**Evidence text**")
            st.write(chunk.get("text", ""))

            metadata = chunk.get("metadata", {})
            st.markdown("**Metadata**")
            st.json(metadata)


def _render_prompt_debug(prompt: dict[str, Any] | None) -> None:
    st.subheader("Prompt debug")
    if not prompt:
        st.caption("Prompt debug was not requested or no prompt was built.")
        return

    with st.expander("Prompt summary", expanded=False):
        st.json(
            {
                "query_text": prompt.get("query_text"),
                "patient_id": prompt.get("patient_id"),
                "has_evidence": prompt.get("has_evidence"),
                "no_evidence": prompt.get("no_evidence"),
                "context_count": len(prompt.get("context_chunks", [])),
            }
        )

    with st.expander("System prompt", expanded=False):
        st.code(prompt.get("system_prompt", ""), language="text")

    with st.expander("User prompt", expanded=False):
        st.code(prompt.get("user_prompt", ""), language="text")


def _render_raw_payload(payload: dict[str, Any]) -> None:
    with st.expander("Raw result payload", expanded=False):
        st.json(payload)


def _render_error(*, query_text: str, patient_id: str, exc: Exception) -> None:
    with st.chat_message("assistant"):
        st.error(str(exc))
        st.caption(
            "Common causes: ChromaDB has not been ingested yet, rag/llm_client.py "
            "is not implemented, dependencies are missing, or no collection exists."
        )
        st.code(
            "python scripts/generate_all.py --mode pilot --clean\n"
            "python scripts/validate_all.py --mode pilot\n"
            "python -m ingestion.ingest --reset\n"
            "streamlit run frontend/dev_rag_chat.py",
            language="bash",
        )

    st.session_state.rag_chat_history.append(
        {
            "query": query_text,
            "answer": f"ERROR for {patient_id}: {exc}",
            "citation_count": 0,
            "used_llm": False,
        }
    )


# ---------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------


def load_patient_options(directory: Path) -> list[PatientOption]:
    """Load approved patients from data/patients only."""
    if not directory.exists():
        return []

    options: list[PatientOption] = []

    for path in sorted(directory.glob("PAT-*.json")):
        try:
            patient = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue

        if not isinstance(patient, dict):
            continue

        patient_id = _safe_text(patient.get("patient_id")) or path.stem
        demographics = patient.get("demographics", {})
        metadata = patient.get("metadata", {})

        name = "Unknown synthetic patient"
        if isinstance(demographics, dict):
            name = _safe_text(demographics.get("name")) or name

        tier = "unknown"
        if isinstance(metadata, dict):
            tier = _safe_text(metadata.get("tier")) or tier

        conditions = patient.get("conditions", [])
        if not isinstance(conditions, list):
            conditions_tuple: tuple[str, ...] = ()
        else:
            conditions_tuple = tuple(_safe_text(condition) for condition in conditions if _safe_text(condition))

        options.append(
            PatientOption(
                patient_id=patient_id,
                name=name,
                tier=tier,
                conditions=conditions_tuple,
                path=path,
            )
        )

    return options


# ---------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------


def _safe_text(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _truncate(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def _format_score(score: Any) -> str:
    if isinstance(score, int | float):
        return f"{float(score):.4f}"
    return "n/a"


if __name__ == "__main__":
    main()
