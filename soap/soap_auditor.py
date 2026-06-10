"""
soap/soap_auditor.py

Deterministic SOAP audit quality gate — Step 10.

Purpose:
    Audit generated SOAP notes against structured patient JSON facts.
    This is a hard gate between SOAP generation and ChromaDB ingestion.
    No patient may proceed to chunking or ingestion unless audit returns
    zero FAIL issues.

Rule IDs:
    SA1 — visit_role primary phrase present           (FAIL)
    SA2 — clinical_event.event_summary in assessment  (FAIL)
    SA3 — No empty SOAP section                       (FAIL)
    SA4 — No invented medications                     (FAIL)
    SA5 — No invented lab values                      (FAIL)
    SA6 — BP value matches vitals                     (FAIL)
    SA7 — No forbidden inference language             (WARN)
    SA8 — No SOAP section exceeds 200 words           (WARN)

Architecture role:
    soap_generator.py  -> SOAP rendering
    soap_auditor.py    -> SOAP safety checks only

Design rules:
    - No LLM calls.
    - No randomization.
    - No auto-correction.
    - No schema changes.
    - No medical inference.
    - All checks are deterministic string matching only.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable, Mapping

from config.constants import MEDICATION_NAMES
from soap.soap_generator import VISIT_ROLE_PHRASES as _VISIT_ROLE_PHRASES

# ---------------------------------------------------------------------------
# Forbidden inference phrases for SA7
# ---------------------------------------------------------------------------

_FORBIDDEN_INFERENCE_PHRASES: tuple[str, ...] = (
    "well controlled",
    "well-controlled",
    "poorly controlled",
    "poorly-controlled",
    "disease is improving",
    "condition is improving",
    "no further follow-up required",
    "clinically stable",
    "treatment is working",
    "patient is responding",
)

_SOAP_SECTIONS: tuple[str, ...] = (
    "subjective",
    "objective",
    "assessment",
    "plan",
)

_MAX_SECTION_WORDS: int = 200

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SoapAuditIssue:
    """One SOAP audit issue."""

    severity: str      # "FAIL" or "WARN"
    patient_id: str
    visit_id: str
    visit_role: str
    section: str       # "subjective" | "objective" | "assessment" | "plan" | "any"
    rule_id: str       # "SA1" .. "SA8"
    message: str


# ---------------------------------------------------------------------------
# Public API — primary entry points
# ---------------------------------------------------------------------------


def audit_soap_for_patient(
    patient: dict,
    blueprint: Any | None = None,
) -> list[SoapAuditIssue]:
    """
    Run all eight SA rules across all visits for one patient.

    Args:
        patient: Patient JSON dictionary (with visits and soap_notes populated).
        blueprint: PatientBlueprint or None. Accepted for API compatibility.

    Returns:
        Flat list of all SoapAuditIssue found across every visit.
    """
    issues: list[SoapAuditIssue] = []
    for index, visit in enumerate(patient.get("visits", [])):
        issues.extend(
            audit_soap_for_visit(
                patient=patient,
                blueprint=blueprint,
                visit=visit,
                visit_index=index,
            )
        )
    return issues


def audit_soap_for_visit(
    patient: dict,
    blueprint: Any | None,
    visit: dict,
    visit_index: int,
) -> list[SoapAuditIssue]:
    """
    Run all eight SA rules for one visit.

    Args:
        patient: Patient JSON dictionary.
        blueprint: PatientBlueprint or None.
        visit: Single visit dict from patient["visits"].
        visit_index: 0-based index of the visit (for context only).

    Returns:
        List of SoapAuditIssue for this visit.
    """
    patient_id = str(patient.get("patient_id", "UNKNOWN"))
    visit_id = str(visit.get("visit_id", f"UNKNOWN-{visit_index}"))
    visit_role = str(visit.get("visit_role", ""))
    soap = visit.get("soap_note", {}) or {}

    issues: list[SoapAuditIssue] = []

    # ------------------------------------------------------------------
    # SA3 first — guard against empty sections before further checks
    # ------------------------------------------------------------------
    issues.extend(_check_sa3_no_empty_section(soap, patient_id, visit_id, visit_role))

    # Build combined text for whole-note checks (after SA3 validates presence)
    full_soap = " ".join([
        str(soap.get("subjective", "")),
        str(soap.get("objective", "")),
        str(soap.get("assessment", "")),
        str(soap.get("plan", "")),
    ])

    issues.extend(_check_sa1_visit_role_phrase(soap, full_soap, patient_id, visit_id, visit_role))
    issues.extend(_check_sa2_event_summary(soap, visit, patient_id, visit_id, visit_role))
    issues.extend(_check_sa4_no_invented_medications(full_soap, visit, patient_id, visit_id, visit_role))
    issues.extend(_check_sa5_no_invented_lab_values(soap, visit, patient_id, visit_id, visit_role))
    issues.extend(_check_sa6_bp_matches_vitals(soap, visit, patient_id, visit_id, visit_role))
    issues.extend(_check_sa7_no_forbidden_inference(soap, full_soap, visit, patient_id, visit_id, visit_role))
    issues.extend(_check_sa8_section_word_limit(soap, patient_id, visit_id, visit_role))

    return issues


def soap_audit_passed(issues: list[SoapAuditIssue]) -> bool:
    """Return True if there are no FAIL-severity issues."""
    return not any(i.severity == "FAIL" for i in issues)


# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------


def audit_soap(patient: dict, blueprint: Any | None = None) -> list[SoapAuditIssue]:
    """Backward-compatible alias for audit_soap_for_patient()."""
    return audit_soap_for_patient(patient, blueprint)


def run_soap_audit(patient: dict, blueprint: Any | None = None) -> list[SoapAuditIssue]:
    """Backward-compatible alias for audit_soap_for_patient()."""
    return audit_soap_for_patient(patient, blueprint)


# ---------------------------------------------------------------------------
# SA1 — visit_role primary phrase present (FAIL)
# ---------------------------------------------------------------------------


def _check_sa1_visit_role_phrase(
    soap: Mapping[str, Any],
    full_soap: str,
    patient_id: str,
    visit_id: str,
    visit_role: str,
) -> list[SoapAuditIssue]:
    """SA1: primary phrase from _VISIT_ROLE_PHRASES[visit_role] must appear in full SOAP."""
    if not visit_role or visit_role not in _VISIT_ROLE_PHRASES:
        return []

    phrases = _VISIT_ROLE_PHRASES[visit_role]
    if not phrases:
        return []

    primary_phrase = phrases[0].lower()
    if primary_phrase not in full_soap.lower():
        return [SoapAuditIssue(
            severity="FAIL",
            patient_id=patient_id,
            visit_id=visit_id,
            visit_role=visit_role,
            section="any",
            rule_id="SA1",
            message=(
                f"Visit role phrase missing: expected '{primary_phrase}' to appear "
                f"in SOAP text for visit_role='{visit_role}'."
            ),
        )]
    return []


# ---------------------------------------------------------------------------
# SA2 — clinical_event.event_summary present in assessment (FAIL)
# ---------------------------------------------------------------------------


def _check_sa2_event_summary(
    soap: Mapping[str, Any],
    visit: dict,
    patient_id: str,
    visit_id: str,
    visit_role: str,
) -> list[SoapAuditIssue]:
    """SA2: event_summary must appear verbatim (case-insensitive) in assessment."""
    clinical_event = visit.get("clinical_event") or {}
    event_summary = str(clinical_event.get("event_summary", "")).strip()
    if not event_summary:
        return []

    assessment = str(soap.get("assessment", ""))
    if event_summary.lower() not in assessment.lower():
        return [SoapAuditIssue(
            severity="FAIL",
            patient_id=patient_id,
            visit_id=visit_id,
            visit_role=visit_role,
            section="assessment",
            rule_id="SA2",
            message=(
                "clinical_event.event_summary not found in assessment section.\n"
                f"Expected: '{event_summary[:80]}...'"
            ),
        )]
    return []


# ---------------------------------------------------------------------------
# SA3 — No empty SOAP section (FAIL)
# ---------------------------------------------------------------------------


def _check_sa3_no_empty_section(
    soap: Mapping[str, Any],
    patient_id: str,
    visit_id: str,
    visit_role: str,
) -> list[SoapAuditIssue]:
    """SA3: each of the four SOAP sections must be a non-empty string."""
    issues: list[SoapAuditIssue] = []
    for section in _SOAP_SECTIONS:
        value = soap.get(section, "")
        if not isinstance(value, str) or not value.strip():
            issues.append(SoapAuditIssue(
                severity="FAIL",
                patient_id=patient_id,
                visit_id=visit_id,
                visit_role=visit_role,
                section=section,
                rule_id="SA3",
                message=f"SOAP section '{section}' is empty after generation.",
            ))
    return issues


# ---------------------------------------------------------------------------
# SA4 — No invented medications (FAIL)
# ---------------------------------------------------------------------------


def _check_sa4_no_invented_medications(
    full_soap: str,
    visit: dict,
    patient_id: str,
    visit_id: str,
    visit_role: str,
) -> list[SoapAuditIssue]:
    """SA4: no medication from MEDICATION_NAMES absent from visit meds appears in SOAP.

    Uses word-boundary matching to avoid false positives from retrieval intent
    tags like 'glibenclamide_added' which contain medication names as prefixes.
    """
    visit_med_names: set[str] = {
        str(m.get("medication_name", "")).strip().lower()
        for m in (visit.get("medications") or [])
        if m.get("medication_name")
    }

    full_soap_lower = full_soap.lower()
    issues: list[SoapAuditIssue] = []

    for name in MEDICATION_NAMES:
        if name.lower() in visit_med_names:
            continue  # legitimately prescribed this visit
        # Word-boundary match: 'glibenclamide' must not be part of 'glibenclamide_added'
        pattern = re.compile(
            r"\b" + re.escape(name) + r"\b",
            re.IGNORECASE,
        )
        if pattern.search(full_soap_lower):
            issues.append(SoapAuditIssue(
                severity="FAIL",
                patient_id=patient_id,
                visit_id=visit_id,
                visit_role=visit_role,
                section="any",
                rule_id="SA4",
                message=(
                    f"SOAP contains medication '{name}' which is not present "
                    f"in visit[\"medications\"]."
                ),
            ))
    return issues


# ---------------------------------------------------------------------------
# SA5 — No invented lab values (FAIL)
# ---------------------------------------------------------------------------


def _check_sa5_no_invented_lab_values(
    soap: Mapping[str, Any],
    visit: dict,
    patient_id: str,
    visit_id: str,
    visit_role: str,
) -> list[SoapAuditIssue]:
    """SA5: numeric values next to a known lab_type name must match visit[\"labs\"].

    Uses a tight separator pattern (colon/whitespace only, max 3 chars) and
    word boundaries on both sides of the number to avoid false positives from
    digits embedded in words like 'hba1c' appearing in retrieval prose.
    """
    objective = str(soap.get("objective", ""))
    visit_labs: dict[str, str] = {
        str(lab.get("lab_type", "")).strip(): str(lab.get("value", "")).strip()
        for lab in (visit.get("labs") or [])
        if lab.get("lab_type")
    }

    issues: list[SoapAuditIssue] = []

    for lab_type, recorded_value in visit_labs.items():
        # Require:
        #   - lab_type as a whole word
        #   - followed by 0-3 chars of only colons/spaces (tight separator)
        #   - a standalone number with word boundaries on both sides
        pattern = re.compile(
            r"\b" + re.escape(lab_type) + r"\b[:\s]{0,3}(\d+(?:\.\d+)?)",
            re.IGNORECASE,
        )
        for match in pattern.finditer(objective):
            found_value = match.group(1)
            # Skip if the digit is immediately followed by a letter
            # (means it is embedded inside a word, e.g. 'hba1c')
            end_pos = match.end()
            if end_pos < len(objective) and objective[end_pos].isalpha():
                continue
            if found_value != str(recorded_value):
                issues.append(SoapAuditIssue(
                    severity="FAIL",
                    patient_id=patient_id,
                    visit_id=visit_id,
                    visit_role=visit_role,
                    section="objective",
                    rule_id="SA5",
                    message=(
                        f"SOAP objective contains lab value for '{lab_type}' "
                        f"not present in visit[\"labs\"]. "
                        f"Found: '{found_value}', expected: '{recorded_value}'."
                    ),
                ))
                break  # one issue per lab type is enough

    return issues


# ---------------------------------------------------------------------------
# SA6 — BP value matches vitals (FAIL)
# ---------------------------------------------------------------------------

_BP_PATTERN = re.compile(r"(\d{2,3})/(\d{2,3})\s*mmHg", re.IGNORECASE)


def _check_sa6_bp_matches_vitals(
    soap: Mapping[str, Any],
    visit: dict,
    patient_id: str,
    visit_id: str,
    visit_role: str,
) -> list[SoapAuditIssue]:
    """SA6: any BP pattern in objective must match visit vitals."""
    objective = str(soap.get("objective", ""))
    vitals = visit.get("vitals") or {}
    systolic = vitals.get("bp_systolic")
    diastolic = vitals.get("bp_diastolic")

    if systolic is None or diastolic is None:
        return []

    issues: list[SoapAuditIssue] = []
    for match in _BP_PATTERN.finditer(objective):
        found_sys = int(match.group(1))
        found_dia = int(match.group(2))
        found_str = match.group(0).strip()
        if found_sys != int(systolic) or found_dia != int(diastolic):
            issues.append(SoapAuditIssue(
                severity="FAIL",
                patient_id=patient_id,
                visit_id=visit_id,
                visit_role=visit_role,
                section="objective",
                rule_id="SA6",
                message=(
                    f"SOAP BP value '{found_str}' does not match vitals "
                    f"bp_systolic={systolic} bp_diastolic={diastolic}."
                ),
            ))
    return issues


# ---------------------------------------------------------------------------
# SA7 — No forbidden inference language (WARN)
# ---------------------------------------------------------------------------


def _check_sa7_no_forbidden_inference(
    soap: Mapping[str, Any],
    full_soap: str,
    visit: dict,
    patient_id: str,
    visit_id: str,
    visit_role: str,
) -> list[SoapAuditIssue]:
    """SA7: forbidden inference phrases not sourced from clinical_event or visit_role raise WARN."""
    clinical_event = visit.get("clinical_event") or {}
    event_summary_lower = str(clinical_event.get("event_summary", "")).lower()

    # Collect all visit_role phrases as allowed sources
    role_phrases_lower: set[str] = set()
    if visit_role and visit_role in _VISIT_ROLE_PHRASES:
        for p in _VISIT_ROLE_PHRASES[visit_role]:
            role_phrases_lower.add(p.lower())

    full_soap_lower = full_soap.lower()
    issues: list[SoapAuditIssue] = []

    for phrase in _FORBIDDEN_INFERENCE_PHRASES:
        phrase_lower = phrase.lower()
        if phrase_lower not in full_soap_lower:
            continue
        # Check if it comes from event_summary or visit_role phrases
        if phrase_lower in event_summary_lower:
            continue
        if any(phrase_lower in rp for rp in role_phrases_lower):
            continue
        issues.append(SoapAuditIssue(
            severity="WARN",
            patient_id=patient_id,
            visit_id=visit_id,
            visit_role=visit_role,
            section="any",
            rule_id="SA7",
            message=(
                f"SOAP contains unsupported inference phrase: '{phrase}' — "
                f"not sourced from clinical_event or visit_role."
            ),
        ))
    return issues


# ---------------------------------------------------------------------------
# SA8 — No SOAP section exceeds 200 words (WARN)
# ---------------------------------------------------------------------------


def _check_sa8_section_word_limit(
    soap: Mapping[str, Any],
    patient_id: str,
    visit_id: str,
    visit_role: str,
) -> list[SoapAuditIssue]:
    """SA8: each SOAP section must be ≤200 words."""
    issues: list[SoapAuditIssue] = []
    for section in _SOAP_SECTIONS:
        text = str(soap.get(section, ""))
        word_count = len(text.split())
        if word_count > _MAX_SECTION_WORDS:
            issues.append(SoapAuditIssue(
                severity="WARN",
                patient_id=patient_id,
                visit_id=visit_id,
                visit_role=visit_role,
                section=section,
                rule_id="SA8",
                message=(
                    f"SOAP section '{section}' exceeds 200 words ({word_count} words). "
                    f"Long sections dilute embedding quality."
                ),
            ))
    return issues


# ---------------------------------------------------------------------------
# Legacy API shim — preserves imports from the old auditor implementation
# ---------------------------------------------------------------------------

class SoapAuditSeverity(str, Enum):
    """SOAP audit severity values (legacy compatibility)."""
    FAIL = "FAIL"
    WARN = "WARN"


@dataclass(frozen=True)
class SoapAuditResult:
    """Audit result for one visit (legacy compatibility)."""
    patient_id: str
    visit_id: str
    issues: tuple[SoapAuditIssue, ...]

    @property
    def passed(self) -> bool:
        return not any(i.severity == "FAIL" for i in self.issues)

    @property
    def failed(self) -> bool:
        return not self.passed

    @property
    def failures(self) -> tuple[SoapAuditIssue, ...]:
        return tuple(i for i in self.issues if i.severity == "FAIL")

    @property
    def warnings(self) -> tuple[SoapAuditIssue, ...]:
        return tuple(i for i in self.issues if i.severity == "WARN")


def audit_patient_soap(
    patient: dict[str, Any],
    *,
    soap_field: str = "soap_note",
) -> list[SoapAuditResult]:
    """Legacy shim: run SA1–SA8 for all visits, return list of SoapAuditResult."""
    results = []
    for index, visit in enumerate(patient.get("visits", [])):
        issues = audit_soap_for_visit(
            patient=patient,
            blueprint=None,
            visit=visit,
            visit_index=index,
        )
        results.append(SoapAuditResult(
            patient_id=str(patient.get("patient_id", "UNKNOWN")),
            visit_id=str(visit.get("visit_id", f"UNKNOWN-{index}")),
            issues=tuple(issues),
        ))
    return results


def audit_visit_soap(
    *,
    patient: dict[str, Any],
    visit: dict[str, Any],
    soap_field: str = "soap_note",
) -> SoapAuditResult:
    """Legacy shim: run SA1–SA8 for one visit, return SoapAuditResult."""
    patient_id = str(patient.get("patient_id", "UNKNOWN"))
    visit_id = str(visit.get("visit_id", "UNKNOWN"))
    issues = audit_soap_for_visit(
        patient=patient,
        blueprint=None,
        visit=visit,
        visit_index=0,
    )
    return SoapAuditResult(
        patient_id=patient_id,
        visit_id=visit_id,
        issues=tuple(issues),
    )


def flatten_issues(results: Iterable[SoapAuditResult]) -> list[SoapAuditIssue]:
    """Flatten issues from multiple audit results (legacy)."""
    issues: list[SoapAuditIssue] = []
    for result in results:
        issues.extend(result.issues)
    return issues


def has_failures(results: Iterable[SoapAuditResult]) -> bool:
    """Return True if any result contains a FAIL issue (legacy)."""
    return any(result.failed for result in results)


def format_audit_report(results: Iterable[SoapAuditResult]) -> str:
    """Format audit results as plain text (legacy)."""
    result_list = list(results)
    issues = flatten_issues(result_list)
    fail_count = sum(1 for i in issues if i.severity == "FAIL")
    warn_count = sum(1 for i in issues if i.severity == "WARN")
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
        section = issue.section or "whole_note"
        lines.append(
            f"[{issue.severity}] [{issue.rule_id}] "
            f"{issue.patient_id} / {issue.visit_id} / {section}: "
            f"{issue.message}"
        )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# audit_soap_note_text — legacy compatibility shim
# ---------------------------------------------------------------------------

def audit_soap_note_text(
    *,
    soap_note: Mapping[str, Any],
    patient: dict[str, Any],
    visit: dict[str, Any],
) -> SoapAuditResult:
    """Legacy shim: audit a SOAP note mapping."""
    visit_copy = dict(visit)
    visit_copy["soap_note"] = dict(soap_note)
    return audit_visit_soap(patient=patient, visit=visit_copy)


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    # Primary SA1–SA8 API
    "SoapAuditIssue",
    "audit_soap_for_patient",
    "audit_soap_for_visit",
    "soap_audit_passed",
    "audit_soap",
    "run_soap_audit",
    # Legacy API
    "SoapAuditSeverity",
    "SoapAuditResult",
    "audit_patient_soap",
    "audit_visit_soap",
    "audit_soap_note_text",
    "flatten_issues",
    "has_failures",
    "format_audit_report",
]
