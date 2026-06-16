"""
frontend/app.py  —  Step 20

Streamlit frontend for the AI-Based Clinical Record Summarization System.

Display layer only:
  - All data comes from the FastAPI backend via api_client.py.
  - No direct ChromaDB, Groq, or validator calls.
  - No hardcoded patient IDs — patient list comes from /patients endpoint.
  - Safe clinical terminology throughout.

Start command:
  PYTHONPATH=. streamlit run frontend/app.py

Demo URL:
  http://localhost:8501
"""

from __future__ import annotations

import os

import streamlit as st

from frontend.api_client import (
    get_error_message,
    get_health,
    get_patients,
    get_summary,
    get_timeline,
    is_error,
    post_query,
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BACKEND_URL: str = os.environ.get("BACKEND_URL", "http://localhost:8000")

st.set_page_config(
    page_title="Clinical Record Summarization System",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Session state — pre-filled question from example buttons
# ---------------------------------------------------------------------------

if "prefilled_question" in st.session_state:
    default_question = st.session_state.pop("prefilled_question")
else:
    default_question = ""

# ---------------------------------------------------------------------------
# Cached API calls (stable during a session)
# ---------------------------------------------------------------------------


@st.cache_data(ttl=300)
def cached_get_patients(base_url: str) -> dict:
    return get_patients(base_url)


@st.cache_data(ttl=300)
def cached_get_timeline(patient_id: str, base_url: str) -> dict:
    return get_timeline(patient_id, base_url)


# ---------------------------------------------------------------------------
# App header
# ---------------------------------------------------------------------------

st.title("🏥 AI-Based Clinical Record Summarization System")
st.caption(
    "Academic RAG demonstration — synthetic patient records only. "
    "This system does not diagnose, recommend treatment, or use real patient data."
)

# Offline mode banner
if os.environ.get("OFFLINE_MODE", "false").lower() == "true":
    st.warning(
        "⚠️ OFFLINE MODE — Live answer generation is disabled. "
        "Retrieval and citations are active. LLM answers are cached."
    )

# ---------------------------------------------------------------------------
# Sidebar — health + patient selector
# ---------------------------------------------------------------------------

with st.sidebar:
    st.header("System Status")
    health = get_health(BACKEND_URL)
    if is_error(health):
        st.error(f"🔴 Backend unavailable\n\n{get_error_message(health)}")
    elif health.get("chromadb") == "unavailable":
        st.warning(
            f"🟡 ChromaDB unavailable | "
            f"chunks: {health.get('chunk_count', 0)}"
        )
    else:
        st.success(
            f"🟢 Backend online  \n"
            f"ChromaDB: {health.get('chromadb')}  \n"
            f"Chunks: {health.get('chunk_count')}  \n"
            f"Version: {health.get('dataset_version')}"
        )

    st.markdown("---")
    st.header("Patient Selector")

    patients_data = cached_get_patients(BACKEND_URL)
    if is_error(patients_data):
        st.error(get_error_message(patients_data))
        st.stop()

    patients = patients_data.get("patients", [])
    patient_options = {
        f"{p['patient_id']} — {', '.join(p['conditions'])} ({p['tier']})": p["patient_id"]
        for p in patients
    }

    selected_label = st.selectbox(
        "Select Patient",
        options=list(patient_options.keys()),
        help="Select a synthetic patient to query.",
    )
    selected_patient_id = patient_options[selected_label]

    # Selected patient metadata
    selected_patient = next(
        p for p in patients if p["patient_id"] == selected_patient_id
    )
    st.markdown("---")
    st.markdown(f"**Patient ID:** `{selected_patient_id}`")
    st.markdown(f"**Tier:** {selected_patient['tier']}")
    st.markdown(f"**Conditions:** {', '.join(selected_patient['conditions'])}")
    st.markdown(f"**Semantic Focus:** {selected_patient['semantic_focus']}")
    st.markdown(
        f"**Documented Allergy:** "
        f"{'Yes' if selected_patient['has_allergy'] else 'None recorded'}"
    )

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_query, tab_timeline, tab_allergy, tab_summary = st.tabs([
    "💬 Ask a Question",
    "📅 Visit Timeline",
    "⚠️ Allergy History",
    "📋 Patient Summary",
])


# ── Tab 1: Ask a Question ────────────────────────────────────────────────

with tab_query:
    st.subheader("Ask a Question About This Patient's Records")
    st.caption(
        "Questions are answered using only retrieved evidence from the patient's "
        "documented synthetic records. No medical knowledge beyond the records is used."
    )

    question = st.text_input(
        "Your question",
        value=default_question,
        placeholder="e.g. What medications is this patient currently taking?",
        help="Ask a natural language question about the selected patient's records.",
        key="question_input",
    )

    col1, col2 = st.columns([1, 4])
    with col1:
        top_k = st.slider("Top K results", min_value=1, max_value=10, value=5)

    ask_button = st.button("Ask", type="primary", key="ask_btn")

    if ask_button and question:
        with st.spinner("Retrieving evidence and generating answer..."):
            result = post_query(
                selected_patient_id, question, BACKEND_URL, top_k=top_k
            )

        if is_error(result):
            st.error(get_error_message(result))
        else:
            if result.get("no_evidence"):
                st.warning(result["answer"])
            else:
                st.markdown("### Answer")
                st.markdown(result["answer"])

            if result.get("grounded"):
                st.success(
                    f"✅ Answer grounded in {result['chunks_used']} retrieved record(s)."
                )
            else:
                st.warning(
                    "⚠️ Answer not grounded — insufficient evidence retrieved."
                )

            citations = result.get("citations", [])
            if citations:
                st.markdown("### Source Citations")
                for i, citation in enumerate(citations, 1):
                    with st.expander(
                        f"Citation {i} — {citation['source_type']} | "
                        f"{citation.get('visit_date') or 'patient-level'} | "
                        f"{citation.get('visit_role') or '—'}",
                        expanded=(i == 1),
                    ):
                        st.markdown(f"**Chunk ID:** `{citation['chunk_id']}`")
                        st.markdown(f"**Patient:** `{citation['patient_id']}`")
                        st.markdown(f"**Visit:** `{citation.get('visit_id') or 'N/A'}`")
                        st.markdown(f"**Source type:** `{citation['source_type']}`")
                        st.markdown("**Excerpt:**")
                        st.text(citation["excerpt"])

    elif ask_button and not question:
        st.info("Please enter a question before clicking Ask.")

    # Example questions
    with st.expander("💡 Example questions for this patient"):
        example_questions = [
            "What medications is this patient currently taking?",
            "Does this patient have any documented allergies?",
            "What laboratory results are available for this patient?",
            "Summarize this patient's visit history.",
            "Were there any changes to this patient's medication?",
        ]
        for q in example_questions:
            if st.button(q, key=f"example_{hash(q)}"):
                st.session_state["prefilled_question"] = q
                st.rerun()


# ── Tab 2: Visit Timeline ─────────────────────────────────────────────────

with tab_timeline:
    st.subheader("Documented Visit Timeline")
    st.caption(
        "Chronological visit history reconstructed from structured patient records. "
        "Source: patient visit data — not generated from a summary field."
    )

    timeline_data = cached_get_timeline(selected_patient_id, BACKEND_URL)

    if is_error(timeline_data):
        st.error(get_error_message(timeline_data))
    else:
        st.markdown(
            f"**{timeline_data['total_visits']} documented visits** "
            f"for `{selected_patient_id}`"
        )

        for visit in timeline_data["visits"]:
            with st.expander(
                f"📅 {visit['visit_date']} — {visit['visit_type']} "
                f"({visit['visit_role']})",
                expanded=False,
            ):
                st.markdown(f"**Visit ID:** `{visit['visit_id']}`")
                st.markdown(f"**Visit type:** {visit['visit_type']}")
                st.markdown(f"**Visit role:** `{visit['visit_role']}`")
                if visit["diagnoses"]:
                    st.markdown(f"**Diagnoses:** {', '.join(visit['diagnoses'])}")
                st.markdown(f"**Clinical event:** {visit['clinical_event_label']}")

                col_labs, col_meds = st.columns(2)
                with col_labs:
                    st.markdown(
                        f"**Lab results:** {'✅ Yes' if visit['has_labs'] else '— None'}"
                    )
                with col_meds:
                    st.markdown(
                        f"**Medications:** {'✅ Yes' if visit['has_medications'] else '— None'}"
                    )


# ── Tab 3: Allergy History ────────────────────────────────────────────────

with tab_allergy:
    st.subheader("Documented Allergy History")
    st.caption(
        "Displays documented allergy records from the patient's allergy registry. "
        "This system retrieves documented allergies — it does not detect or predict allergies."
    )

    with st.spinner("Retrieving documented allergy records..."):
        allergy_result = post_query(
            selected_patient_id,
            "Does this patient have any documented allergies? "
            "List all allergens, reactions, and severity.",
            BACKEND_URL,
            top_k=3,
            source_type_hint="allergy",
        )

    if is_error(allergy_result):
        st.error(get_error_message(allergy_result))
    elif allergy_result.get("no_evidence"):
        st.info(
            "ℹ️ No documented allergies found in the available records for this patient."
        )
    else:
        st.markdown("### Retrieved Allergy Evidence")
        st.markdown(allergy_result["answer"])

        allergy_citations = [
            c for c in allergy_result.get("citations", [])
            if c["source_type"] == "allergy"
        ]
        if allergy_citations:
            st.markdown("### Allergy Record Source")
            for citation in allergy_citations:
                st.info(
                    f"**Source:** `{citation['chunk_id']}`  \n"
                    f"**Record type:** {citation['source_type']}  \n"
                    f"**Excerpt:** {citation['excerpt']}"
                )

    st.markdown("---")
    st.caption(
        "⚠️ For academic demonstration only. "
        "This system retrieves documented records and does not provide "
        "clinical allergy assessment."
    )


# ── Tab 4: Patient Summary ────────────────────────────────────────────────

with tab_summary:
    st.subheader("Patient Record Summary")
    st.caption(
        "A grounded summary of this patient's documented medical history, "
        "generated from retrieved synthetic records only."
    )

    generate_summary = st.button(
        "Generate Summary",
        key="generate_summary_btn",
        type="primary",
    )

    if generate_summary:
        with st.spinner("Generating grounded summary from retrieved records..."):
            summary_result = get_summary(selected_patient_id, BACKEND_URL)

        if is_error(summary_result):
            st.error(get_error_message(summary_result))
        else:
            st.markdown("### Summary")
            st.markdown(summary_result["answer"])
            st.markdown(
                f"*Summary generated from {summary_result['chunks_used']} "
                f"retrieved record chunk(s).*"
            )

            citations = summary_result.get("citations", [])
            if citations:
                st.markdown("### Evidence Sources")
                source_type_counts: dict[str, int] = {}
                for c in citations:
                    source_type_counts[c["source_type"]] = (
                        source_type_counts.get(c["source_type"], 0) + 1
                    )
                for source_type, count in sorted(source_type_counts.items()):
                    st.markdown(f"- **{source_type}**: {count} chunk(s)")


