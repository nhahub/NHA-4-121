"""
ingestion/retrieval_enrichment_auditor.py

Deterministic Retrieval Enrichment Auditor — Step 12.

Audits retrieval-oriented enrichment text before it is appended to chunks,
embedded, or stored in ChromaDB.  Compares generated text against documented
structured facts from the patient record and the current source context.

This module is intentionally deterministic.  It does NOT:
  - call any LLM or external API
  - mutate patient or visit dictionaries
  - perform chunking, build metadata, create embeddings, or write to ChromaDB

Seven checks are implemented (Checks 1-6 are FAIL; Check 7 is WARN).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from config.constants import CORE_SOURCE_TYPES, MEDICATION_NAMES


# ---------------------------------------------------------------------------
# Unsafe recommendation phrases (Check 5)
# ---------------------------------------------------------------------------

_UNSAFE_PHRASES: tuple[str, ...] = (
    "should take",
    "recommended to",
    "advised to",
    "treatment should",
    "patient must",
    "prescribe",
    "increase dose",
    "decrease dose",
)

# Word-count limit before a WARN is issued (Check 7)
_MAX_WORDS: int = 120

# Source types that require a visit dict
_VISIT_LEVEL_TYPES: frozenset[str] = frozenset(
    {"doctor_note", "lab_result", "prescription"}
)


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class RetrievalAuditResult:
    """Audit result for one enrichment text and one source context."""

    patient_id:  str
    visit_id:    str | None
    source_type: str
    passed:      bool
    issues:      list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def audit_retrieval_text(
    retrieval_text: str,
    patient: dict,
    visit: dict | None,
    source_type: str,
) -> RetrievalAuditResult:
    """
    Audit one enrichment text string against documented patient/visit facts.

    Args:
        retrieval_text: Enrichment string produced by build_retrieval_text().
        patient:        Full patient JSON dictionary.
        visit:          Visit dictionary, or None for allergy source_type.
        source_type:    One of CORE_SOURCE_TYPES.

    Returns:
        RetrievalAuditResult with passed=True only when zero FAIL issues exist.
    """
    patient_id = _patient_id(patient)
    visit_id   = _visit_id(visit)
    text       = str(retrieval_text).strip() if retrieval_text is not None else ""
    issues: list[str] = []
    has_fail   = False

    def fail(msg: str) -> None:
        nonlocal has_fail
        has_fail = True
        issues.append(msg)

    def warn(msg: str) -> None:
        issues.append(f"[WARN] {msg}")

    # ------------------------------------------------------------------
    # Check 1 — Non-empty (FAIL)
    # ------------------------------------------------------------------
    if not text:
        fail("Enrichment text is empty or whitespace-only.")

    # ------------------------------------------------------------------
    # Check 2 — Valid source_type (FAIL)
    # ------------------------------------------------------------------
    if source_type not in CORE_SOURCE_TYPES:
        fail(
            f"Invalid source_type {source_type!r}; "
            f"expected one of: {', '.join(CORE_SOURCE_TYPES)}."
        )

    # ------------------------------------------------------------------
    # Check 3 — Visit required for visit-level source types (FAIL)
    # ------------------------------------------------------------------
    if source_type in _VISIT_LEVEL_TYPES and visit is None:
        fail(
            f"source_type={source_type!r} requires a non-None visit dictionary."
        )
    if source_type == "allergy" and patient is None:
        fail("source_type='allergy' requires a non-None patient dictionary.")

    # ------------------------------------------------------------------
    # Check 4 — No unrendered placeholder leakage (FAIL)
    # ------------------------------------------------------------------
    if _has_placeholder(text):
        fail(
            "Enrichment text contains an unrendered placeholder pattern such as {…}."
        )

    # ------------------------------------------------------------------
    # Check 5 — No unsafe recommendation phrases (FAIL)
    # ------------------------------------------------------------------
    for phrase in _UNSAFE_PHRASES:
        if _phrase_present(text, phrase):
            fail(
                f"Unsafe recommendation phrase found in enrichment text: {phrase!r}."
            )

    # ------------------------------------------------------------------
    # Check 6 — No unsupported medication mentions (FAIL)
    # ------------------------------------------------------------------
    if source_type in ("doctor_note", "prescription"):
        visit_meds = _visit_medication_names(visit)
        for med_name in MEDICATION_NAMES:
            if _phrase_present(text, med_name) and med_name not in visit_meds:
                fail(
                    f"Medication {med_name!r} appears in enrichment text "
                    "but is not documented in visit medications for this source context."
                )

    # ------------------------------------------------------------------
    # Check 7 — Reasonable length (WARN)
    # ------------------------------------------------------------------
    word_count = len(text.split())
    if word_count > _MAX_WORDS:
        warn(
            f"Enrichment text exceeds {_MAX_WORDS} words ({word_count} words). "
            "Long enrichment may dilute embedding quality."
        )

    return RetrievalAuditResult(
        patient_id=patient_id,
        visit_id=visit_id,
        source_type=source_type,
        passed=not has_fail,
        issues=issues,
    )


def audit_retrieval_texts(
    items: list[dict],
) -> list[RetrievalAuditResult]:
    """
    Audit multiple enrichment texts in a deterministic batch.

    Each item dict must have keys: retrieval_text, patient, visit, source_type.

    Returns:
        List of RetrievalAuditResult in input order; never short-circuits.
    """
    results: list[RetrievalAuditResult] = []
    for item in items:
        results.append(
            audit_retrieval_text(
                item["retrieval_text"],
                item["patient"],
                item.get("visit"),
                item["source_type"],
            )
        )
    return results


def enrichment_audit_passed(results: list[RetrievalAuditResult]) -> bool:
    """Return True only when every result in the list has passed=True."""
    return all(r.passed for r in results)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _has_placeholder(text: str) -> bool:
    """Return True when text contains unrendered {…} placeholders."""
    return bool(re.search(r"\{[^{}]*\}", text))


def _phrase_present(text: str, phrase: str) -> bool:
    """Case-insensitive word-boundary match for phrase inside text."""
    if not phrase:
        return False
    pattern = r"(?<![A-Za-z0-9])" + re.escape(phrase) + r"(?![A-Za-z0-9])"
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def _visit_medication_names(visit: dict | None) -> frozenset[str]:
    """Return medication_name values documented in the visit."""
    if visit is None:
        return frozenset()
    medications = visit.get("medications") or []
    names: set[str] = set()
    for med in medications:
        if isinstance(med, Mapping):
            name = str(med.get("medication_name", "") or "").strip()
            if name:
                names.add(name)
    return frozenset(names)


def _patient_id(patient: Any) -> str:
    if not isinstance(patient, Mapping):
        return "UNKNOWN_PATIENT"
    return str(patient.get("patient_id") or "UNKNOWN_PATIENT").strip()


def _visit_id(visit: Any) -> str | None:
    if not isinstance(visit, Mapping):
        return None
    value = str(visit.get("visit_id") or "").strip()
    return value if value else None


__all__ = [
    "RetrievalAuditResult",
    "audit_retrieval_text",
    "audit_retrieval_texts",
    "enrichment_audit_passed",
]
