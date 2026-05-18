"""
ingestion/retrieval_enrichment_auditor.py

Deterministic Retrieval Enrichment Auditor.

This module audits retrieval-oriented text before it is appended to chunks,
embedded, or stored in ChromaDB. It compares the generated retrieval text
against documented structured facts from the patient record and the current
source context.

The auditor is intentionally deterministic. It does not call an LLM, mutate
patient or visit dictionaries, perform chunking, build metadata, create
embeddings, or write to ChromaDB.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
import re
from typing import Any

from config.constants import (
    BP_FORBIDDEN_LAB_TERMS,
    CONDITIONS,
    LAB_TYPES,
    MEDICATION_NAMES,
    SOURCE_TYPES,
)


class RetrievalAuditSeverity(str, Enum):
    """Severity levels emitted by the retrieval enrichment auditor."""

    FAIL = "FAIL"
    WARN = "WARN"


@dataclass(frozen=True)
class RetrievalAuditIssue:
    """One deterministic audit issue for a retrieval_text string."""

    rule_id: str
    severity: RetrievalAuditSeverity
    message: str
    patient_id: str | None = None
    visit_id: str | None = None
    source_type: str | None = None


@dataclass(frozen=True)
class RetrievalAuditResult:
    """Audit result for one retrieval_text string and one source context."""

    patient_id: str
    visit_id: str | None
    source_type: str
    passed: bool
    issues: tuple[RetrievalAuditIssue, ...]


@dataclass(frozen=True)
class RetrievalAuditInput:
    """Input record for batch retrieval enrichment auditing."""

    retrieval_text: str
    patient: dict[str, Any]
    visit: dict[str, Any] | None
    source_type: str


TREATMENT_RECOMMENDATION_PHRASES: tuple[str, ...] = (
    "requires treatment",
    "requires medication",
    "requires medication adjustment",
    "should start",
    "should stop",
    "should increase",
    "should decrease",
    "recommended",
    "recommend",
    "needs treatment",
    "must receive",
)

UNSAFE_INTERPRETATION_PHRASES: tuple[str, ...] = (
    "poor control",
    "poorly controlled",
    "well controlled",
    "uncontrolled",
    "controlled",
    "worsening",
    "improving",
    "improved",
    "deteriorating",
    "above target",
    "below target",
    "target range",
    "at risk of",
    "likely has",
    "suggests diagnosis",
)

SYMPTOM_PHRASES_REQUIRING_STRUCTURED_SUPPORT: tuple[str, ...] = (
    "chest pain",
    "shortness of breath",
    "fever",
    "cough",
    "wheezing",
    "abdominal pain",
    "dizziness",
    "fatigue",
    "headache",
    "nausea",
    "vomiting",
)

# These phrases are not enum values, but they imply one. They are audited
# because enrichment text can otherwise smuggle condition context without
# explicitly naming the canonical condition token.
CONDITION_CONTEXT_PHRASE_REQUIREMENTS: dict[str, str] = {
    "diabetes": "T2DM",
    "diabetes-related": "T2DM",
    "kidney-related": "CKD",
    "CKD-related": "CKD",
    "anemia": "IDA",
    "anemia-related": "IDA",
    "hypertension": "HTN",
    "hypertension-related": "HTN",
    "asthma-related": "Asthma",
    "GERD-related": "GERD",
}

RETRIEVAL_TEXT_MAX_CHARS: int = 2_000


@dataclass(frozen=True)
class _DocumentedFacts:
    """Allowed structured facts for the requested audit source context."""

    conditions: tuple[str, ...]
    lab_types: tuple[str, ...]
    medication_names: tuple[str, ...]
    allergy_terms: tuple[str, ...]


def audit_retrieval_text(
    *,
    retrieval_text: str,
    patient: dict[str, Any],
    visit: dict[str, Any] | None,
    source_type: str,
) -> RetrievalAuditResult:
    """
    Audit one retrieval_text string against structured patient and visit facts.

    The function never raises for source-type or visit-context problems. Those
    problems are reported as FAIL issues so the ingestion pipeline can format
    and log them consistently.
    """
    patient_id = _patient_id(patient)
    visit_id = _visit_id(visit)
    text = _safe_text(retrieval_text)
    issues: list[RetrievalAuditIssue] = []

    add_issue = _issue_appender(
        issues=issues,
        patient_id=patient_id,
        visit_id=visit_id,
        source_type=source_type,
    )

    if not text:
        add_issue(
            "RET-001",
            RetrievalAuditSeverity.FAIL,
            "retrieval_text is empty or whitespace only.",
        )

    if _contains_unrendered_placeholder(text):
        add_issue(
            "RET-002",
            RetrievalAuditSeverity.FAIL,
            "retrieval_text contains an unrendered placeholder such as {...}.",
        )

    if source_type not in SOURCE_TYPES:
        add_issue(
            "RET-011",
            RetrievalAuditSeverity.FAIL,
            f"Invalid source_type {source_type!r}; expected one of: {', '.join(SOURCE_TYPES)}.",
        )

    if source_type in SOURCE_TYPES and source_type != "allergy" and visit is None:
        add_issue(
            "RET-012",
            RetrievalAuditSeverity.FAIL,
            f"source_type={source_type!r} requires a visit dictionary.",
        )

    facts = _collect_documented_facts(
        patient=patient,
        visit=visit,
        source_type=source_type,
    )

    for phrase in _present_phrases(text, TREATMENT_RECOMMENDATION_PHRASES):
        add_issue(
            "RET-003",
            RetrievalAuditSeverity.FAIL,
            f"Unsafe treatment recommendation phrase found: {phrase!r}.",
        )

    for phrase in _present_phrases(text, UNSAFE_INTERPRETATION_PHRASES):
        add_issue(
            "RET-004",
            RetrievalAuditSeverity.FAIL,
            f"Unsafe clinical interpretation phrase found: {phrase!r}.",
        )

    for medication_name in _present_phrases(text, MEDICATION_NAMES):
        if medication_name not in facts.medication_names:
            add_issue(
                "RET-005",
                RetrievalAuditSeverity.FAIL,
                f"Medication {medication_name!r} appears but is not documented for this source context.",
            )

    condition_context_spans = _condition_context_phrase_spans(text)

    for condition in _present_phrases_outside_spans(
        text,
        CONDITIONS,
        excluded_spans=condition_context_spans,
    ):
        if condition not in facts.conditions:
            add_issue(
                "RET-006",
                RetrievalAuditSeverity.FAIL,
                f"Condition or diagnosis {condition!r} appears but is not documented for this source context.",
            )

    for phrase, required_condition in _unsupported_condition_context_phrases(
        text=text,
        documented_conditions=facts.conditions,
    ):
        add_issue(
            "RET-006",
            RetrievalAuditSeverity.FAIL,
            f"Condition-related wording {phrase!r} appears without documented {required_condition!r} support.",
        )

    for lab_type in _present_phrases(text, LAB_TYPES):
        if lab_type not in facts.lab_types:
            add_issue(
                "RET-007",
                RetrievalAuditSeverity.FAIL,
                f"Lab type {lab_type!r} appears but is not documented for this source context.",
            )

    for symptom_phrase in _present_phrases(text, SYMPTOM_PHRASES_REQUIRING_STRUCTURED_SUPPORT):
        if symptom_phrase not in facts.allergy_terms:
            add_issue(
                "RET-008",
                RetrievalAuditSeverity.WARN,
                f"Symptom phrase {symptom_phrase!r} appears without explicit structured support.",
            )

    bp_terms = _bp_metadata_like_terms(text)
    if bp_terms:
        add_issue(
            "RET-009",
            RetrievalAuditSeverity.WARN,
            "BP metadata-like wording appears in retrieval_text: "
            f"{_join_phrases(bp_terms)}.",
        )

    if len(text) > RETRIEVAL_TEXT_MAX_CHARS:
        add_issue(
            "RET-010",
            RetrievalAuditSeverity.WARN,
            "retrieval_text is longer than the recommended retrieval enrichment limit "
            f"of {RETRIEVAL_TEXT_MAX_CHARS} characters.",
        )

    final_issues = tuple(issues)
    return RetrievalAuditResult(
        patient_id=patient_id,
        visit_id=visit_id,
        source_type=source_type,
        passed=not any(issue.severity == RetrievalAuditSeverity.FAIL for issue in final_issues),
        issues=final_issues,
    )


def audit_retrieval_texts(
    items: Iterable[RetrievalAuditInput],
) -> list[RetrievalAuditResult]:
    """
    Audit multiple retrieval_text strings in a deterministic batch.

    This helper keeps chunker/ingestion code simple while preserving the same
    single-item audit contract used by audit_retrieval_text(). It does not
    short-circuit on failures; every input item is audited and returned in the
    original order.
    """
    return [
        audit_retrieval_text(
            retrieval_text=item.retrieval_text,
            patient=item.patient,
            visit=item.visit,
            source_type=item.source_type,
        )
        for item in items
    ]


def has_failures(result: RetrievalAuditResult) -> bool:
    """Return True if an audit result contains FAIL issues."""
    return any(issue.severity == RetrievalAuditSeverity.FAIL for issue in result.issues)


def format_retrieval_audit_report(result: RetrievalAuditResult) -> str:
    """Return a readable audit report for debugging and pipeline logs."""
    status = "PASSED" if result.passed else "FAILED"
    visit_label = result.visit_id if result.visit_id is not None else "patient-level"
    lines = [
        "Retrieval enrichment audit report",
        f"Status: {status}",
        f"Patient ID: {result.patient_id}",
        f"Visit ID: {visit_label}",
        f"Source type: {result.source_type}",
        f"Issue count: {len(result.issues)}",
    ]

    if not result.issues:
        lines.append("No audit issues found.")
        return "\n".join(lines)

    lines.append("Issues:")
    for issue in result.issues:
        lines.append(
            f"- [{issue.severity.value}] {issue.rule_id}: {issue.message}"
        )

    return "\n".join(lines)


def _collect_documented_facts(
    *,
    patient: Mapping[str, Any],
    visit: Mapping[str, Any] | None,
    source_type: str,
) -> _DocumentedFacts:
    """Collect source-context facts used by the audit checks."""
    patient_conditions = _documented_patient_conditions(patient)
    visit_diagnoses = _documented_visit_diagnoses(visit)
    combined_conditions = _ordered_unique((*patient_conditions, *visit_diagnoses))

    visit_lab_types = _documented_visit_lab_types(visit)
    visit_medications = _documented_visit_medication_names(visit)
    allergy_terms = _documented_allergy_terms(patient)

    if source_type == "doctor_note":
        return _DocumentedFacts(
            conditions=combined_conditions,
            lab_types=visit_lab_types,
            medication_names=visit_medications,
            allergy_terms=allergy_terms,
        )

    if source_type == "lab_result":
        return _DocumentedFacts(
            conditions=combined_conditions,
            lab_types=visit_lab_types,
            medication_names=visit_medications,
            allergy_terms=allergy_terms,
        )

    if source_type == "prescription":
        return _DocumentedFacts(
            conditions=combined_conditions,
            lab_types=(),
            medication_names=visit_medications,
            allergy_terms=allergy_terms,
        )

    if source_type == "allergy":
        return _DocumentedFacts(
            conditions=patient_conditions,
            lab_types=(),
            medication_names=(),
            allergy_terms=allergy_terms,
        )

    return _DocumentedFacts(
        conditions=combined_conditions,
        lab_types=visit_lab_types,
        medication_names=visit_medications,
        allergy_terms=allergy_terms,
    )


def _documented_patient_conditions(patient: Mapping[str, Any]) -> tuple[str, ...]:
    """Return valid patient-level conditions from patient['conditions']."""
    return _ordered_allowed_values(_sequence(patient.get("conditions")), CONDITIONS)


def _documented_visit_diagnoses(
    visit: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    """Return valid visit-level diagnoses from visit['diagnoses']."""
    if visit is None:
        return ()
    return _ordered_allowed_values(_sequence(visit.get("diagnoses")), CONDITIONS)


def _documented_visit_lab_types(
    visit: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    """Return valid lab_type values documented in the visit."""
    if visit is None:
        return ()

    labs = _dict_list(visit.get("labs"))
    values = (_safe_text(lab.get("lab_type")) for lab in labs)
    return _ordered_allowed_values(values, LAB_TYPES)


def _documented_visit_medication_names(
    visit: Mapping[str, Any] | None,
) -> tuple[str, ...]:
    """Return medication_name values documented in the visit."""
    if visit is None:
        return ()

    medications = _dict_list(visit.get("medications"))
    names = (_safe_text(medication.get("medication_name")) for medication in medications)
    return _ordered_unique(name for name in names if name)


def _documented_allergy_terms(patient: Mapping[str, Any]) -> tuple[str, ...]:
    """Return patient-level allergy terms documented in allergy_registry."""
    terms: list[str] = []

    for allergy in _dict_list(patient.get("allergy_registry")):
        for field_name in (
            "allergen",
            "reaction",
            "severity",
            "recorded_date",
            "source_visit_id",
        ):
            value = _safe_text(allergy.get(field_name))
            if value:
                terms.append(value)

    return _ordered_unique(terms)


def _contains_unrendered_placeholder(text: str) -> bool:
    """Return True when text still contains placeholder-like braces."""
    return re.search(r"\{[^{}]*\}|\{\{|\}\}", text) is not None


def _contains_phrase(text: str, phrase: str) -> bool:
    """
    Return True if phrase appears using safe case-insensitive boundaries.

    This intentionally avoids naive substring matching, so a short phrase such
    as IDA does not match inside an unrelated longer token.
    """
    clean_phrase = _safe_text(phrase)
    if not clean_phrase:
        return False

    pattern = r"(?<![A-Za-z0-9])" + re.escape(clean_phrase) + r"(?![A-Za-z0-9])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _present_phrases(text: str, phrases: Iterable[str]) -> tuple[str, ...]:
    """Return deterministic phrases from phrases that are present in text."""
    return tuple(phrase for phrase in phrases if _contains_phrase(text, phrase))


def _present_phrases_outside_spans(
    text: str,
    phrases: Iterable[str],
    *,
    excluded_spans: Iterable[tuple[int, int]],
) -> tuple[str, ...]:
    """Return phrases present in text outside excluded character spans."""
    excluded = tuple(excluded_spans)
    present: list[str] = []

    for phrase in phrases:
        spans = _phrase_spans(text, phrase)
        if any(not _span_overlaps_any(span, excluded) for span in spans):
            present.append(phrase)

    return tuple(present)


def _condition_context_phrase_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Return spans for any condition-context phrase found in text."""
    spans: list[tuple[int, int]] = []

    for phrase in CONDITION_CONTEXT_PHRASE_REQUIREMENTS:
        spans.extend(_phrase_spans(text, phrase))

    return tuple(spans)


def _unsupported_condition_context_phrases(
    *,
    text: str,
    documented_conditions: tuple[str, ...],
) -> tuple[tuple[str, str], ...]:
    """
    Return unsupported condition-context phrases without duplicate overlaps.

    Longer phrases are evaluated first so text such as "diabetes-related"
    produces one issue for "diabetes-related" instead of separate issues for
    both "diabetes-related" and "diabetes".
    """
    occupied_spans: list[tuple[int, int]] = []
    unsupported: list[tuple[str, str]] = []
    seen_pairs: set[tuple[str, str]] = set()

    requirements = sorted(
        CONDITION_CONTEXT_PHRASE_REQUIREMENTS.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    for phrase, required_condition in requirements:
        if required_condition in documented_conditions:
            continue

        for span in _phrase_spans(text, phrase):
            if _span_overlaps_any(span, occupied_spans):
                continue

            pair = (phrase, required_condition)
            if pair not in seen_pairs:
                unsupported.append(pair)
                seen_pairs.add(pair)

            occupied_spans.append(span)

    return tuple(unsupported)


def _phrase_spans(text: str, phrase: str) -> tuple[tuple[int, int], ...]:
    """Return case-insensitive safe-boundary spans for phrase in text."""
    clean_phrase = _safe_text(phrase)
    if not clean_phrase:
        return ()

    pattern = r"(?<![A-Za-z0-9])" + re.escape(clean_phrase) + r"(?![A-Za-z0-9])"
    return tuple(
        (match.start(), match.end())
        for match in re.finditer(pattern, text, flags=re.IGNORECASE)
    )


def _span_overlaps_any(
    span: tuple[int, int],
    spans: Iterable[tuple[int, int]],
) -> bool:
    """Return True if span overlaps any span in spans."""
    start, end = span
    return any(start < other_end and end > other_start for other_start, other_end in spans)


def _bp_metadata_like_terms(text: str) -> tuple[str, ...]:
    """Return BP terms that appear in metadata-like form."""
    matches: list[str] = []

    for term in BP_FORBIDDEN_LAB_TERMS:
        clean_term = _safe_text(term)
        if not clean_term:
            continue

        escaped = re.escape(clean_term)
        boundary_term = r"(?<![A-Za-z0-9])" + escaped + r"(?![A-Za-z0-9])"
        patterns = (
            boundary_term + r"\s*[:=]",
            boundary_term + r".{0,30}\b(metadata|field|column|key)\b",
            r"\b(metadata|field|column|key)\b.{0,30}" + boundary_term,
        )

        always_metadata_like = clean_term in {
            "bp_systolic",
            "bp_diastolic",
            "blood_pressure",
        }

        if always_metadata_like and _contains_phrase(text, clean_term):
            matches.append(clean_term)
            continue

        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns):
            matches.append(clean_term)

    return _ordered_unique(matches)


def _issue_appender(
    *,
    issues: list[RetrievalAuditIssue],
    patient_id: str,
    visit_id: str | None,
    source_type: str,
):
    """Return a small closure for adding normalized audit issues."""

    def add_issue(
        rule_id: str,
        severity: RetrievalAuditSeverity,
        message: str,
    ) -> None:
        issues.append(
            RetrievalAuditIssue(
                rule_id=rule_id,
                severity=severity,
                message=message,
                patient_id=patient_id,
                visit_id=visit_id,
                source_type=source_type,
            )
        )

    return add_issue


def _patient_id(patient: Mapping[str, Any]) -> str:
    """Return the patient_id or a deterministic fallback string."""
    return _safe_text(patient.get("patient_id")) or "UNKNOWN_PATIENT"


def _visit_id(visit: Mapping[str, Any] | None) -> str | None:
    """Return the visit_id if a visit is available."""
    if visit is None:
        return None
    return _safe_text(visit.get("visit_id")) or None


def _sequence(value: Any) -> tuple[Any, ...]:
    """Return a tuple for list or tuple values; otherwise return empty tuple."""
    if isinstance(value, (list, tuple)):
        return tuple(value)
    return ()


def _dict_list(value: Any) -> tuple[Mapping[str, Any], ...]:
    """Return mapping items from a list/tuple; ignore non-dict entries."""
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _ordered_allowed_values(
    values: Iterable[Any],
    allowed_values: Iterable[str],
) -> tuple[str, ...]:
    """Return ordered unique values that exactly match allowed constants."""
    allowed = set(allowed_values)
    return _ordered_unique(
        text for text in (_safe_text(value) for value in values) if text in allowed
    )


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    """Return string values without duplicates while preserving first-seen order."""
    seen: set[str] = set()
    output: list[str] = []

    for value in values:
        text = _safe_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)

    return tuple(output)


def _join_phrases(values: Iterable[str]) -> str:
    """Join values deterministically for readable audit messages."""
    items = _ordered_unique(values)

    if not items:
        return "none"
    if len(items) == 1:
        return items[0]
    if len(items) == 2:
        return f"{items[0]} and {items[1]}"
    return f"{', '.join(items[:-1])}, and {items[-1]}"


def _safe_text(value: Any) -> str:
    """Convert a structured value to stripped text without inventing data."""
    if value is None:
        return ""
    return str(value).strip()


__all__ = [
    "RetrievalAuditSeverity",
    "RetrievalAuditIssue",
    "RetrievalAuditResult",
    "RetrievalAuditInput",
    "audit_retrieval_text",
    "audit_retrieval_texts",
    "has_failures",
    "format_retrieval_audit_report",
]
