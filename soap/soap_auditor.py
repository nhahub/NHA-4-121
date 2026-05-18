"""
soap/soap_auditor.py

Deterministic SOAP audit utilities.

Purpose:
    Audit generated SOAP notes against structured patient JSON facts.

Design goal:
    Keep this auditor focused, maintainable, deterministic, and easy to explain.
    The auditor should verify that generated SOAP text preserves structured
    facts and does not introduce unsafe medical language.

Architecture role:
    soap_renderers.py  -> owns fact extraction and exact formatting
    soap_safety.py     -> owns forbidden clinical phrases and debug markers
    soap_selector.py   -> owns deterministic template selection
    soap_generator.py  -> owns SOAP rendering
    soap_auditor.py    -> owns SOAP safety checks only

Important safety rules:
    - No LLM calls.
    - No randomization.
    - No auto-correction.
    - No schema changes.
    - No medical inference.
    - No duplicated lab or medication formatting logic.
    - Uses build_fact_context() as the source of formatted facts.

The auditor does not decide medical truth. It only checks that SOAP text remains
consistent with the structured JSON record.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from soap.soap_contract import REQUIRED_FACTS_BY_SECTION, SOAP_SECTIONS, SoapSection
from soap.soap_renderers import build_fact_context
from soap.soap_safety import (
    ALLERGEN_CONTEXT_TERMS,
    DEBUG_TEMPLATE_MARKERS,
    FORBIDDEN_CLINICAL_PHRASE_TERMS,
    FORBIDDEN_CLINICAL_SINGLE_WORDS,
)


SOAP_SECTION_KEYS: tuple[SoapSection, ...] = SOAP_SECTIONS


class SoapAuditSeverity(str, Enum):
    """SOAP audit severity values."""

    FAIL = "FAIL"
    WARN = "WARN"


@dataclass(frozen=True)
class SoapAuditIssue:
    """
    One SOAP audit issue.

    Attributes:
        severity: FAIL or WARN.
        rule_id: Stable audit rule ID.
        patient_id: Patient identifier.
        visit_id: Visit identifier.
        section: SOAP section name, or None for whole-note issues.
        message: Human-readable audit message.
    """

    severity: SoapAuditSeverity
    rule_id: str
    patient_id: str
    visit_id: str
    section: str | None
    message: str


@dataclass(frozen=True)
class SoapAuditResult:
    """
    Audit result for one visit.

    Attributes:
        patient_id: Patient identifier.
        visit_id: Visit identifier.
        issues: Tuple of SOAP audit issues.
    """

    patient_id: str
    visit_id: str
    issues: tuple[SoapAuditIssue, ...]

    @property
    def passed(self) -> bool:
        """Return True if there are no FAIL issues."""
        return not any(issue.severity == SoapAuditSeverity.FAIL for issue in self.issues)

    @property
    def failed(self) -> bool:
        """Return True if there is at least one FAIL issue."""
        return not self.passed

    @property
    def failures(self) -> tuple[SoapAuditIssue, ...]:
        """Return FAIL issues."""
        return tuple(
            issue
            for issue in self.issues
            if issue.severity == SoapAuditSeverity.FAIL
        )

    @property
    def warnings(self) -> tuple[SoapAuditIssue, ...]:
        """Return WARN issues."""
        return tuple(
            issue
            for issue in self.issues
            if issue.severity == SoapAuditSeverity.WARN
        )


def audit_patient_soap(
    patient: dict[str, Any],
    *,
    soap_field: str = "soap_note",
) -> list[SoapAuditResult]:
    """
    Audit SOAP notes for all visits in one patient record.

    Args:
        patient: Patient JSON dictionary.
        soap_field: Visit field containing the SOAP note.

    Returns:
        List of SoapAuditResult objects.
    """
    return [
        audit_visit_soap(
            patient=patient,
            visit=visit,
            soap_field=soap_field,
        )
        for visit in patient.get("visits", [])
    ]


def audit_visit_soap(
    *,
    patient: dict[str, Any],
    visit: dict[str, Any],
    soap_field: str = "soap_note",
) -> SoapAuditResult:
    """
    Audit a visit SOAP note against structured patient and visit facts.

    Args:
        patient: Patient JSON dictionary.
        visit: Visit dictionary.
        soap_field: Visit field containing SOAP note dictionary.

    Returns:
        SoapAuditResult for the visit.
    """
    patient_id = str(patient.get("patient_id", "UNKNOWN_PATIENT"))
    visit_id = str(visit.get("visit_id", "UNKNOWN_VISIT"))

    issues: list[SoapAuditIssue] = []

    soap_note = visit.get(soap_field)

    if not isinstance(soap_note, Mapping):
        issues.append(
            _issue(
                severity=SoapAuditSeverity.FAIL,
                rule_id="SOAP-STRUCT-001",
                patient_id=patient_id,
                visit_id=visit_id,
                section=None,
                message=f"Missing or invalid SOAP note field: {soap_field!r}.",
            )
        )
        return SoapAuditResult(
            patient_id=patient_id,
            visit_id=visit_id,
            issues=tuple(issues),
        )

    structure_issues = _check_soap_structure(
        soap_note=soap_note,
        patient_id=patient_id,
        visit_id=visit_id,
    )
    issues.extend(structure_issues)

    if _has_failures(structure_issues):
        return SoapAuditResult(
            patient_id=patient_id,
            visit_id=visit_id,
            issues=tuple(issues),
        )

    fact_context = build_fact_context(patient=patient, visit=visit)
    soap_text = _join_soap_text(soap_note)

    issues.extend(
        _check_required_fact_text(
            soap_note=soap_note,
            fact_context=fact_context,
            patient_id=patient_id,
            visit_id=visit_id,
        )
    )

    issues.extend(
        _check_bp_in_objective(
            soap_note=soap_note,
            fact_context=fact_context,
            patient_id=patient_id,
            visit_id=visit_id,
        )
    )
    issues.extend(
        _check_current_medications_are_rendered(
            soap_text=soap_text,
            visit=visit,
            patient_id=patient_id,
            visit_id=visit_id,
        )
    )
    issues.extend(
        _check_allergen_prescription_risk(
            soap_text=soap_text,
            patient=patient,
            patient_id=patient_id,
            visit_id=visit_id,
        )
    )
    issues.extend(
        _check_unsafe_phrases(
            soap_text=soap_text,
            patient_id=patient_id,
            visit_id=visit_id,
        )
    )
    issues.extend(
        _check_unrendered_placeholders(
            soap_note=soap_note,
            patient_id=patient_id,
            visit_id=visit_id,
        )
    )
    issues.extend(
        _check_no_internal_debug_markers(
            soap_text=soap_text,
            patient_id=patient_id,
            visit_id=visit_id,
        )
    )

    return SoapAuditResult(
        patient_id=patient_id,
        visit_id=visit_id,
        issues=tuple(issues),
    )


def audit_soap_note_text(
    *,
    soap_note: Mapping[str, Any],
    patient: dict[str, Any],
    visit: dict[str, Any],
) -> SoapAuditResult:
    """
    Audit a SOAP note mapping before storing it inside the visit.

    Useful for tests or candidate SOAP notes.

    Args:
        soap_note: SOAP note dictionary.
        patient: Patient JSON dictionary.
        visit: Visit dictionary.

    Returns:
        SoapAuditResult.
    """
    visit_copy = dict(visit)
    visit_copy["soap_note"] = dict(soap_note)

    return audit_visit_soap(
        patient=patient,
        visit=visit_copy,
        soap_field="soap_note",
    )


def flatten_issues(results: Iterable[SoapAuditResult]) -> list[SoapAuditIssue]:
    """
    Flatten issues from multiple audit results.

    Args:
        results: Iterable of SoapAuditResult.

    Returns:
        List of SoapAuditIssue objects.
    """
    issues: list[SoapAuditIssue] = []

    for result in results:
        issues.extend(result.issues)

    return issues


def has_failures(results: Iterable[SoapAuditResult]) -> bool:
    """
    Return True if any result contains a FAIL issue.

    Args:
        results: Iterable of SoapAuditResult.

    Returns:
        Boolean failure status.
    """
    return any(result.failed for result in results)


def format_audit_report(results: Iterable[SoapAuditResult]) -> str:
    """
    Format SOAP audit results as readable plain text.

    Args:
        results: Iterable of SoapAuditResult.

    Returns:
        Plain-text audit report.
    """
    result_list = list(results)
    issues = flatten_issues(result_list)

    fail_count = sum(
        1
        for issue in issues
        if issue.severity == SoapAuditSeverity.FAIL
    )
    warn_count = sum(
        1
        for issue in issues
        if issue.severity == SoapAuditSeverity.WARN
    )

    lines = [
        "=== SOAP AUDIT REPORT ===",
        f"Visits checked: {len(result_list)}",
        f"FAIL issues:   {fail_count}",
        f"WARN issues:   {warn_count}",
    ]

    if not issues:
        lines.append("Status: PASS — no SOAP audit issues detected.")
        return "\n".join(lines)

    lines.append("")
    lines.append("--- ISSUES ---")

    for issue in issues:
        section = issue.section if issue.section else "whole_note"
        lines.append(
            f"[{issue.severity.value}] "
            f"[{issue.rule_id}] "
            f"{issue.patient_id} / {issue.visit_id} / {section}: "
            f"{issue.message}"
        )

    return "\n".join(lines)


def _check_soap_structure(
    *,
    soap_note: Mapping[str, Any],
    patient_id: str,
    visit_id: str,
) -> list[SoapAuditIssue]:
    """Check that SOAP note has the expected four-section structure."""
    issues: list[SoapAuditIssue] = []

    for section in SOAP_SECTION_KEYS:
        if section not in soap_note:
            issues.append(
                _issue(
                    severity=SoapAuditSeverity.FAIL,
                    rule_id="SOAP-STRUCT-002",
                    patient_id=patient_id,
                    visit_id=visit_id,
                    section=section,
                    message=f"Missing SOAP section: {section!r}.",
                )
            )
            continue

        value = soap_note[section]

        if not isinstance(value, str):
            issues.append(
                _issue(
                    severity=SoapAuditSeverity.FAIL,
                    rule_id="SOAP-STRUCT-003",
                    patient_id=patient_id,
                    visit_id=visit_id,
                    section=section,
                    message=f"SOAP section {section!r} must be a string.",
                )
            )
            continue

        if not value.strip():
            issues.append(
                _issue(
                    severity=SoapAuditSeverity.FAIL,
                    rule_id="SOAP-STRUCT-004",
                    patient_id=patient_id,
                    visit_id=visit_id,
                    section=section,
                    message=f"SOAP section {section!r} is empty.",
                )
            )

    extra_sections = [
        key
        for key in soap_note.keys()
        if key not in SOAP_SECTION_KEYS
    ]

    if extra_sections:
        issues.append(
            _issue(
                severity=SoapAuditSeverity.WARN,
                rule_id="SOAP-STRUCT-005",
                patient_id=patient_id,
                visit_id=visit_id,
                section=None,
                message=f"Unexpected SOAP keys found: {extra_sections}.",
            )
        )

    return issues


def _check_required_fact_text(
    *,
    soap_note: Mapping[str, Any],
    fact_context: Mapping[str, Any],
    patient_id: str,
    visit_id: str,
) -> list[SoapAuditIssue]:
    """
    Check that required rendered facts from build_fact_context() appear in the
    correct SOAP section.

    This is stricter than checking the whole SOAP text because the same value
    may appear in multiple sections. For example, condition_text and
    diagnosis_text may both be "T2DM, HTN", but they must still appear in their
    intended SOAP sections.
    """
    issues: list[SoapAuditIssue] = []

    for section in SOAP_SECTION_KEYS:
        section_text = str(soap_note.get(section, ""))

        for fact_key in REQUIRED_FACTS_BY_SECTION[section]:
            expected_text = str(fact_context[fact_key])

            if expected_text not in section_text:
                issues.append(
                    _issue(
                        severity=SoapAuditSeverity.FAIL,
                        rule_id="SOAP-FACT-001",
                        patient_id=patient_id,
                        visit_id=visit_id,
                        section=section,
                        message=(
                            f"Required fact text missing or changed in {section}: "
                            f"{fact_key}={expected_text!r}."
                        ),
                    )
                )

    return issues


def _check_bp_in_objective(
    *,
    soap_note: Mapping[str, Any],
    fact_context: Mapping[str, Any],
    patient_id: str,
    visit_id: str,
) -> list[SoapAuditIssue]:
    """
    Check that BP appears in the Objective section.

    BP is a vital sign and should be rendered in SOAP objective text.
    """
    bp_text = str(fact_context["bp_text"])
    objective_text = str(soap_note.get("objective", ""))

    if bp_text in objective_text:
        return []

    return [
        _issue(
            severity=SoapAuditSeverity.FAIL,
            rule_id="SOAP-BP-001",
            patient_id=patient_id,
            visit_id=visit_id,
            section="objective",
            message=f"BP value missing from objective section: {bp_text!r}.",
        )
    ]


def _check_current_medications_are_rendered(
    *,
    soap_text: str,
    visit: Mapping[str, Any],
    patient_id: str,
    visit_id: str,
) -> list[SoapAuditIssue]:
    """
    Check that every medication listed in the structured visit record appears
    in the rendered SOAP note.

    This check does not decide whether a medication is clinically appropriate.
    It only confirms that documented structured medication facts were preserved
    in the SOAP text. Exact medication formatting is additionally covered by
    REQUIRED_FACTS_BY_SECTION through fact_context["medication_text"].
    """
    issues: list[SoapAuditIssue] = []
    current_medications = visit.get("medications", [])

    for medication in current_medications:
        medication_name = str(medication.get("medication_name", "")).strip()

        if not medication_name:
            continue

        if medication_name not in soap_text:
            issues.append(
                _issue(
                    severity=SoapAuditSeverity.FAIL,
                    rule_id="SOAP-MED-001",
                    patient_id=patient_id,
                    visit_id=visit_id,
                    section="plan",
                    message=f"Medication name missing from SOAP: {medication_name!r}.",
                )
            )

    return issues


def _check_allergen_prescription_risk(
    *,
    soap_text: str,
    patient: Mapping[str, Any],
    patient_id: str,
    visit_id: str,
) -> list[SoapAuditIssue]:
    """
    Check whether an allergen appears near medication or treatment context.

    This is conservative and does not ban allergen mentions globally because a
    SOAP note may safely mention documented allergy history. It only flags
    allergen mentions near medication/prescription wording.
    """
    issues: list[SoapAuditIssue] = []
    allergy_registry = patient.get("allergy_registry", [])

    for allergy in allergy_registry:
        allergen = str(allergy.get("allergen", "")).strip()

        if not allergen:
            continue

        windows = _windows_around_phrase(
            text=soap_text,
            phrase=allergen,
            window_size=80,
        )

        for window in windows:
            normalized_window = _normalize_text(window)

            if any(term in normalized_window for term in ALLERGEN_CONTEXT_TERMS):
                issues.append(
                    _issue(
                        severity=SoapAuditSeverity.FAIL,
                        rule_id="SOAP-ALLERGY-001",
                        patient_id=patient_id,
                        visit_id=visit_id,
                        section=None,
                        message=(
                            f"Allergen {allergen!r} appears near medication "
                            "or treatment context."
                        ),
                    )
                )
                break

    return issues


def _check_unsafe_phrases(
    *,
    soap_text: str,
    patient_id: str,
    visit_id: str,
) -> list[SoapAuditIssue]:
    """
    Check unsafe interpretive or recommendation wording.

    Single-word terms are matched with word boundaries to avoid false positives
    such as matching "likely" inside "unlikely". Multi-word phrases are
    matched after whitespace normalization with phrase-edge boundaries.
    """
    issues: list[SoapAuditIssue] = []
    normalized_text = _normalize_text(soap_text)

    for word in FORBIDDEN_CLINICAL_SINGLE_WORDS:
        normalized_word = _normalize_text(word)

        if _contains_word_boundary_match(normalized_text, normalized_word):
            issues.append(
                _issue(
                    severity=SoapAuditSeverity.FAIL,
                    rule_id="SOAP-SAFE-001",
                    patient_id=patient_id,
                    visit_id=visit_id,
                    section=None,
                    message=f"Unsafe single-word term found in SOAP text: {word!r}.",
                )
            )

    for phrase in FORBIDDEN_CLINICAL_PHRASE_TERMS:
        normalized_phrase = _normalize_text(phrase)

        if _contains_phrase_boundary_match(normalized_text, normalized_phrase):
            issues.append(
                _issue(
                    severity=SoapAuditSeverity.FAIL,
                    rule_id="SOAP-SAFE-001",
                    patient_id=patient_id,
                    visit_id=visit_id,
                    section=None,
                    message=f"Unsafe phrase found in SOAP text: {phrase!r}.",
                )
            )

    return issues


def _check_unrendered_placeholders(
    *,
    soap_note: Mapping[str, Any],
    patient_id: str,
    visit_id: str,
) -> list[SoapAuditIssue]:
    """Check for leftover template placeholders such as {bp_text}."""
    issues: list[SoapAuditIssue] = []

    for section in SOAP_SECTION_KEYS:
        section_text = str(soap_note.get(section, ""))

        if "{" in section_text or "}" in section_text:
            issues.append(
                _issue(
                    severity=SoapAuditSeverity.FAIL,
                    rule_id="SOAP-TEMPLATE-001",
                    patient_id=patient_id,
                    visit_id=visit_id,
                    section=section,
                    message="Unrendered template placeholder found.",
                )
            )

    return issues


def _check_no_internal_debug_markers(
    *,
    soap_text: str,
    patient_id: str,
    visit_id: str,
) -> list[SoapAuditIssue]:
    """Check that template IDs or selector metadata do not leak into SOAP text."""
    issues: list[SoapAuditIssue] = []

    for marker in DEBUG_TEMPLATE_MARKERS:
        if marker in soap_text:
            issues.append(
                _issue(
                    severity=SoapAuditSeverity.FAIL,
                    rule_id="SOAP-DEBUG-001",
                    patient_id=patient_id,
                    visit_id=visit_id,
                    section=None,
                    message=f"Internal template/debug marker leaked into SOAP: {marker!r}.",
                )
            )

    return issues


def _join_soap_text(soap_note: Mapping[str, Any]) -> str:
    """Join SOAP sections in canonical order into one searchable text string."""
    return " ".join(str(soap_note.get(section, "")) for section in SOAP_SECTION_KEYS)


def _normalize_text(text: str) -> str:
    """Normalize text for case-insensitive phrase matching."""
    return " ".join(text.lower().split())


def _contains_word_boundary_match(text: str, word: str) -> bool:
    """Return True when a normalized single word appears as a whole word."""
    if not word:
        return False

    pattern = re.compile(rf"(?<!\w){re.escape(word)}(?!\w)")
    return bool(pattern.search(text))


def _contains_phrase_boundary_match(text: str, phrase: str) -> bool:
    """Return True when a normalized phrase appears with safe edge boundaries."""
    if not phrase:
        return False

    pattern = re.compile(rf"(?<!\w){re.escape(phrase)}(?!\w)")
    return bool(pattern.search(text))


def _windows_around_phrase(
    *,
    text: str,
    phrase: str,
    window_size: int,
) -> list[str]:
    """
    Return text windows around each occurrence of phrase.

    Args:
        text: Source text.
        phrase: Phrase to find.
        window_size: Characters before and after the match.

    Returns:
        List of local text windows.
    """
    if not phrase:
        return []

    windows: list[str] = []
    pattern = re.compile(re.escape(phrase), re.IGNORECASE)

    for match in pattern.finditer(text):
        start = max(match.start() - window_size, 0)
        end = min(match.end() + window_size, len(text))
        windows.append(text[start:end])

    return windows


def _has_failures(issues: Iterable[SoapAuditIssue]) -> bool:
    """Return True if any issue is FAIL severity."""
    return any(issue.severity == SoapAuditSeverity.FAIL for issue in issues)


def _issue(
    *,
    severity: SoapAuditSeverity,
    rule_id: str,
    patient_id: str,
    visit_id: str,
    section: str | None,
    message: str,
) -> SoapAuditIssue:
    """Create a SoapAuditIssue object."""
    return SoapAuditIssue(
        severity=severity,
        rule_id=rule_id,
        patient_id=patient_id,
        visit_id=visit_id,
        section=section,
        message=message,
    )


__all__ = [
    "SOAP_SECTION_KEYS",
    "SoapAuditIssue",
    "SoapAuditResult",
    "SoapAuditSeverity",
    "audit_patient_soap",
    "audit_soap_note_text",
    "audit_visit_soap",
    "flatten_issues",
    "format_audit_report",
    "has_failures",
]
