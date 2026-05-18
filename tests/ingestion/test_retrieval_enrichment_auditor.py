"""
tests/ingestion/test_retrieval_enrichment_auditor.py

Tests for the Deterministic Retrieval Enrichment Auditor.

These tests protect the safety gate that audits retrieval_text before future
chunk construction, embedding, and ChromaDB ingestion.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from config.constants import LAB_TYPES, MEDICATION_NAMES, SOURCE_TYPES
from ingestion.retrieval_enricher import build_retrieval_text
from ingestion.retrieval_enrichment_auditor import (
    RetrievalAuditResult,
    RetrievalAuditSeverity,
    audit_retrieval_text,
    format_retrieval_audit_report,
    has_failures,
)


@pytest.fixture()
def sample_patient() -> dict[str, Any]:
    """Return a representative patient with documented structured facts."""
    return {
        "schema_version": "1.0",
        "patient_id": "PAT-MOD-003",
        "demographics": {
            "name": "Karim Hassan",
            "date_of_birth": "1978-03-20",
            "sex": "male",
        },
        "conditions": ["T2DM", "HTN"],
        "allergy_registry": [
            {
                "allergen": "Penicillin",
                "reaction": "skin rash",
                "severity": "moderate",
                "recorded_date": "2022-03-10",
                "source_visit_id": "VST-MOD-003-002",
            }
        ],
        "visits": [],
        "metadata": {"tier": "moderate"},
    }


@pytest.fixture()
def sample_visit() -> dict[str, Any]:
    """Return a representative visit with diagnoses, labs, and medications."""
    return {
        "visit_id": "VST-MOD-003-004",
        "visit_date": "2024-06-15",
        "visit_type": "follow_up",
        "attending_physician": "Dr. Salma Nabil",
        "diagnoses": ["T2DM", "HTN"],
        "vitals": {
            "bp_systolic": 148,
            "bp_diastolic": 92,
            "heart_rate": 84,
            "weight_kg": 91.0,
            "bmi": 30.1,
        },
        "labs": [
            {
                "lab_type": "HbA1c",
                "value": 8.1,
                "unit": "%",
                "reference_range": "4.0-5.6 %",
                "flag": "HIGH",
            },
            {
                "lab_type": "FBG",
                "value": 165,
                "unit": "mg/dL",
                "reference_range": "70-99 mg/dL",
                "flag": "HIGH",
            },
        ],
        "medications": [
            {
                "medication_name": "Metformin",
                "medication_class": "Biguanide",
                "dose": "500 mg",
                "frequency": "twice_daily",
                "route": "oral",
                "start_date": "2024-06-15",
                "stop_date": None,
            },
            {
                "medication_name": "Lisinopril",
                "medication_class": "ACE Inhibitor",
                "dose": "10 mg",
                "frequency": "once_daily",
                "route": "oral",
                "start_date": "2024-06-15",
                "stop_date": None,
            },
        ],
        "soap_note": {
            "subjective": "",
            "objective": "",
            "assessment": "",
            "plan": "",
        },
        "linked_documents": [],
        "prior_visit_id": "VST-MOD-003-003",
    }


def _rule_ids(result: RetrievalAuditResult) -> set[str]:
    """Return rule IDs emitted by one audit result."""
    return {issue.rule_id for issue in result.issues}


def _severities(result: RetrievalAuditResult) -> set[RetrievalAuditSeverity]:
    """Return severities emitted by one audit result."""
    return {issue.severity for issue in result.issues}


def test_auditor_passes_safe_retrieval_text(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Grounded retrieval text should pass."""
    retrieval_text = build_retrieval_text(
        patient=sample_patient,
        visit=sample_visit,
        source_type="doctor_note",
    )

    result = audit_retrieval_text(
        retrieval_text=retrieval_text,
        patient=sample_patient,
        visit=sample_visit,
        source_type="doctor_note",
    )

    assert result.passed is True
    assert has_failures(result) is False
    assert result.issues == ()
    assert result.patient_id == "PAT-MOD-003"
    assert result.visit_id == "VST-MOD-003-004"
    assert result.source_type == "doctor_note"


def test_auditor_passes_generated_text_for_all_supported_source_types(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Auditor should pass safe output from the enricher for each source type."""
    assert SOURCE_TYPES == ("doctor_note", "lab_result", "prescription", "allergy")

    for source_type in SOURCE_TYPES:
        visit = None if source_type == "allergy" else sample_visit
        retrieval_text = build_retrieval_text(
            patient=sample_patient,
            visit=visit,
            source_type=source_type,
        )

        result = audit_retrieval_text(
            retrieval_text=retrieval_text,
            patient=sample_patient,
            visit=visit,
            source_type=source_type,
        )

        assert result.passed is True, format_retrieval_audit_report(result)
        assert has_failures(result) is False


def test_auditor_fails_empty_retrieval_text(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Empty retrieval text should fail with RET-001."""
    result = audit_retrieval_text(
        retrieval_text="   ",
        patient=sample_patient,
        visit=sample_visit,
        source_type="doctor_note",
    )

    assert result.passed is False
    assert has_failures(result) is True
    assert "RET-001" in _rule_ids(result)


def test_auditor_fails_unrendered_placeholders(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Unrendered placeholders should fail with RET-002."""
    result = audit_retrieval_text(
        retrieval_text="Doctor-note retrieval context for patient {patient_id}.",
        patient=sample_patient,
        visit=sample_visit,
        source_type="doctor_note",
    )

    assert result.passed is False
    assert "RET-002" in _rule_ids(result)


def test_auditor_fails_invalid_source_type(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Invalid source_type should fail with RET-011."""
    result = audit_retrieval_text(
        retrieval_text="Timeline retrieval context for patient PAT-MOD-003.",
        patient=sample_patient,
        visit=sample_visit,
        source_type="timeline",
    )

    assert result.passed is False
    assert has_failures(result) is True
    assert "RET-011" in _rule_ids(result)


def test_auditor_fails_non_allergy_without_visit(
    sample_patient: dict[str, Any],
) -> None:
    """doctor_note, lab_result, and prescription should fail if visit is None."""
    for source_type in ("doctor_note", "lab_result", "prescription"):
        result = audit_retrieval_text(
            retrieval_text="Retrieval context exists but visit is missing.",
            patient=sample_patient,
            visit=None,
            source_type=source_type,
        )

        assert result.passed is False
        assert "RET-012" in _rule_ids(result)


def test_auditor_allows_allergy_with_visit_none(
    sample_patient: dict[str, Any],
) -> None:
    """allergy source_type should support patient-level audit with visit=None."""
    retrieval_text = build_retrieval_text(
        patient=sample_patient,
        visit=None,
        source_type="allergy",
    )

    result = audit_retrieval_text(
        retrieval_text=retrieval_text,
        patient=sample_patient,
        visit=None,
        source_type="allergy",
    )

    assert result.passed is True
    assert has_failures(result) is False
    assert result.visit_id is None


def test_auditor_fails_hallucinated_medication(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Mentioning undocumented medication should fail."""
    assert "Amlodipine" in MEDICATION_NAMES
    assert all(
        medication["medication_name"] != "Amlodipine"
        for medication in sample_visit["medications"]
    )

    retrieval_text = (
        build_retrieval_text(sample_patient, sample_visit, "doctor_note")
        + " Amlodipine is also mentioned in this retrieval text."
    )

    result = audit_retrieval_text(
        retrieval_text=retrieval_text,
        patient=sample_patient,
        visit=sample_visit,
        source_type="doctor_note",
    )

    assert result.passed is False
    assert "RET-005" in _rule_ids(result)


def test_auditor_fails_hallucinated_condition(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Mentioning undocumented condition should fail."""
    retrieval_text = (
        build_retrieval_text(sample_patient, sample_visit, "doctor_note")
        + " Asthma is also mentioned without structured support."
    )

    result = audit_retrieval_text(
        retrieval_text=retrieval_text,
        patient=sample_patient,
        visit=sample_visit,
        source_type="doctor_note",
    )

    assert result.passed is False
    assert "RET-006" in _rule_ids(result)


def test_auditor_fails_condition_related_wording_without_support(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Condition-related wording should require documented condition support."""
    patient = deepcopy(sample_patient)
    patient["conditions"] = []
    visit = deepcopy(sample_visit)
    visit["diagnoses"] = []

    result = audit_retrieval_text(
        retrieval_text="Laboratory retrieval context includes diabetes-related laboratory wording.",
        patient=patient,
        visit=visit,
        source_type="lab_result",
    )

    assert result.passed is False
    assert "RET-006" in _rule_ids(result)


def test_auditor_fails_hallucinated_lab_type(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Mentioning undocumented lab type should fail."""
    assert "Creatinine" in LAB_TYPES
    assert all(lab["lab_type"] != "Creatinine" for lab in sample_visit["labs"])

    retrieval_text = (
        build_retrieval_text(sample_patient, sample_visit, "lab_result")
        + " Creatinine is also mentioned without a documented visit lab entry."
    )

    result = audit_retrieval_text(
        retrieval_text=retrieval_text,
        patient=sample_patient,
        visit=sample_visit,
        source_type="lab_result",
    )

    assert result.passed is False
    assert "RET-007" in _rule_ids(result)


def test_auditor_fails_treatment_recommendation_phrases(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Treatment recommendation language should fail."""
    result = audit_retrieval_text(
        retrieval_text="Prescription retrieval context says the patient should start a new medication.",
        patient=sample_patient,
        visit=sample_visit,
        source_type="prescription",
    )

    assert result.passed is False
    assert "RET-003" in _rule_ids(result)


def test_auditor_fails_unsafe_interpretation_phrases(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Unsupported interpretation should fail."""
    result = audit_retrieval_text(
        retrieval_text="Laboratory retrieval context says diabetes is poorly controlled.",
        patient=sample_patient,
        visit=sample_visit,
        source_type="lab_result",
    )

    assert result.passed is False
    assert "RET-004" in _rule_ids(result)


def test_auditor_warns_on_symptom_phrase_without_structured_support(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Unsupported symptom phrasing should warn without creating a failure."""
    result = audit_retrieval_text(
        retrieval_text="Doctor-note retrieval context mentions chest pain without structured support.",
        patient=sample_patient,
        visit=sample_visit,
        source_type="doctor_note",
    )

    assert result.passed is True
    assert has_failures(result) is False
    assert "RET-008" in _rule_ids(result)
    assert _severities(result) == {RetrievalAuditSeverity.WARN}


def test_auditor_warns_on_bp_metadata_like_text(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """BP metadata-like output should produce WARN."""
    result = audit_retrieval_text(
        retrieval_text="Doctor-note retrieval context includes bp_systolic: 148 as a metadata-like field.",
        patient=sample_patient,
        visit=sample_visit,
        source_type="doctor_note",
    )

    assert result.passed is True
    assert has_failures(result) is False
    assert "RET-009" in _rule_ids(result)
    assert _severities(result) == {RetrievalAuditSeverity.WARN}


def test_auditor_warns_on_text_that_is_too_long(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Very long retrieval enrichment text should warn with RET-010."""
    long_text = "Retrieval context. " + ("documented entry " * 180)

    result = audit_retrieval_text(
        retrieval_text=long_text,
        patient=sample_patient,
        visit=sample_visit,
        source_type="doctor_note",
    )

    assert result.passed is True
    assert has_failures(result) is False
    assert "RET-010" in _rule_ids(result)
    assert RetrievalAuditSeverity.WARN in _severities(result)


def test_audit_result_is_deterministic(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Repeated auditing of the same input should return equal results."""
    retrieval_text = build_retrieval_text(sample_patient, sample_visit, "lab_result")

    first = audit_retrieval_text(
        retrieval_text=retrieval_text,
        patient=sample_patient,
        visit=sample_visit,
        source_type="lab_result",
    )
    second = audit_retrieval_text(
        retrieval_text=retrieval_text,
        patient=sample_patient,
        visit=sample_visit,
        source_type="lab_result",
    )

    assert first == second


def test_phrase_matching_avoids_naive_substring_false_positive(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Auditor matching should use phrase boundaries, not raw substrings."""
    result = audit_retrieval_text(
        retrieval_text="Doctor-note retrieval context contains Metforminx as an unrelated token.",
        patient=sample_patient,
        visit=sample_visit,
        source_type="doctor_note",
    )

    assert result.passed is True
    assert "RET-005" not in _rule_ids(result)


def test_format_retrieval_audit_report_includes_key_context(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Formatted reports should be readable for pipeline logs."""
    result = audit_retrieval_text(
        retrieval_text="Prescription retrieval context says the patient should stop medication.",
        patient=sample_patient,
        visit=sample_visit,
        source_type="prescription",
    )

    report = format_retrieval_audit_report(result)

    assert "Retrieval enrichment audit report" in report
    assert "Status: FAILED" in report
    assert "Patient ID: PAT-MOD-003" in report
    assert "Visit ID: VST-MOD-003-004" in report
    assert "Source type: prescription" in report
    assert "RET-003" in report


def test_auditor_does_not_mutate_patient_or_visit(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Auditing must not mutate input dictionaries."""
    patient_before = deepcopy(sample_patient)
    visit_before = deepcopy(sample_visit)
    retrieval_text = build_retrieval_text(sample_patient, sample_visit, "doctor_note")

    audit_retrieval_text(
        retrieval_text=retrieval_text,
        patient=sample_patient,
        visit=sample_visit,
        source_type="doctor_note",
    )

    assert sample_patient == patient_before
    assert sample_visit == visit_before
