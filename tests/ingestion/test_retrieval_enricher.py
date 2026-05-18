"""
tests/ingestion/test_retrieval_enricher.py

Tests for the Deterministic Retrieval Enrichment Layer.

These tests protect deterministic, safe retrieval-text generation before the
text is appended to future chunks and embedded in ChromaDB.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from config.constants import LAB_TYPES, MEDICATION_NAMES, SOURCE_TYPES
from ingestion.retrieval_enricher import (
    build_allergy_retrieval_text,
    build_doctor_note_retrieval_text,
    build_lab_retrieval_text,
    build_prescription_retrieval_text,
    build_retrieval_text,
)


UNSAFE_RETRIEVAL_PHRASES = (
    "poor control",
    "poorly controlled",
    "well controlled",
    "uncontrolled",
    "worsening",
    "improving",
    "improved",
    "deteriorating",
    "above target",
    "below target",
    "target range",
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
    "at risk of",
    "likely has",
    "suggests diagnosis",
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


def test_build_retrieval_text_is_deterministic_for_same_input(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Same patient and visit should always produce identical retrieval text."""
    first = build_retrieval_text(sample_patient, sample_visit, "doctor_note")
    second = build_retrieval_text(sample_patient, sample_visit, "doctor_note")

    assert first == second


def test_build_retrieval_text_does_not_mutate_patient_or_visit(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Enrichment must not modify input dictionaries."""
    patient_before = deepcopy(sample_patient)
    visit_before = deepcopy(sample_visit)

    for source_type in SOURCE_TYPES:
        if source_type == "allergy":
            build_retrieval_text(sample_patient, None, source_type)
        else:
            build_retrieval_text(sample_patient, sample_visit, source_type)

    assert sample_patient == patient_before
    assert sample_visit == visit_before


def test_build_retrieval_text_rejects_invalid_source_type(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Unknown source_type should raise ValueError."""
    with pytest.raises(ValueError, match="Unsupported source_type"):
        build_retrieval_text(sample_patient, sample_visit, "timeline")


def test_non_allergy_source_type_requires_visit(
    sample_patient: dict[str, Any],
) -> None:
    """doctor_note, lab_result, and prescription require visit."""
    for source_type in ("doctor_note", "lab_result", "prescription"):
        with pytest.raises(ValueError, match="visit is required"):
            build_retrieval_text(sample_patient, visit=None, source_type=source_type)


def test_allergy_source_type_allows_visit_none(
    sample_patient: dict[str, Any],
) -> None:
    """allergy retrieval text is patient-level and supports visit=None."""
    text = build_retrieval_text(sample_patient, visit=None, source_type="allergy")

    assert "Allergy retrieval context" in text
    assert "PAT-MOD-003" in text
    assert "Penicillin" in text
    assert "VST-MOD-003-002" in text


def test_doctor_note_retrieval_text_includes_documented_conditions(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Documented conditions should appear in doctor_note retrieval text."""
    text = build_doctor_note_retrieval_text(sample_patient, sample_visit)

    assert "PAT-MOD-003" in text
    assert "VST-MOD-003-004" in text
    assert "T2DM" in text
    assert "HTN" in text
    assert "HbA1c" in text
    assert "FBG" in text
    assert "Metformin" in text
    assert "Lisinopril" in text


def test_lab_retrieval_text_includes_documented_lab_types_only(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Lab retrieval text should include only lab types present in visit labs."""
    text = build_lab_retrieval_text(sample_patient, sample_visit)

    assert "HbA1c" in text
    assert "FBG" in text
    assert "Creatinine" not in text
    assert "Hemoglobin" not in text
    assert "Ferritin" not in text


def test_lab_retrieval_text_adds_condition_context_only_when_supported(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Condition-related lab wording must require documented condition support."""
    supported_text = build_lab_retrieval_text(sample_patient, sample_visit)

    patient_without_t2dm = deepcopy(sample_patient)
    patient_without_t2dm["conditions"] = []
    visit_without_t2dm = deepcopy(sample_visit)
    visit_without_t2dm["diagnoses"] = []
    unsupported_text = build_lab_retrieval_text(
        patient_without_t2dm,
        visit_without_t2dm,
    )

    assert "diabetes-related" in supported_text
    assert "diabetes-related" not in unsupported_text
    assert "No chronic condition-specific lab wording is added" in unsupported_text


def test_prescription_retrieval_text_includes_documented_medications_only(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Prescription retrieval text should include only documented medications."""
    text = build_prescription_retrieval_text(sample_patient, sample_visit)

    assert "Metformin" in text
    assert "Lisinopril" in text
    assert "Amlodipine" not in text
    assert "Omeprazole" not in text
    assert "Salbutamol inhaler" not in text


def test_prescription_condition_context_uses_whitelist_and_documented_conditions(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Medication-condition wording must use whitelist plus documented conditions."""
    supported_text = build_prescription_retrieval_text(sample_patient, sample_visit)

    patient_without_conditions = deepcopy(sample_patient)
    patient_without_conditions["conditions"] = []
    visit_without_diagnoses = deepcopy(sample_visit)
    visit_without_diagnoses["diagnoses"] = []
    unsupported_text = build_prescription_retrieval_text(
        patient_without_conditions,
        visit_without_diagnoses,
    )

    assert "Metformin with documented T2DM" in supported_text
    assert "Lisinopril with documented HTN" in supported_text
    assert "Metformin with documented T2DM" not in unsupported_text
    assert "Lisinopril with documented HTN" not in unsupported_text
    assert "No medication-condition retrieval wording is added" in unsupported_text


def test_allergy_retrieval_text_includes_documented_allergies(
    sample_patient: dict[str, Any],
) -> None:
    """Allergy retrieval text should include documented allergens and reactions."""
    text = build_allergy_retrieval_text(sample_patient)

    assert "PAT-MOD-003" in text
    assert "Penicillin" in text
    assert "skin rash" in text
    assert "moderate" in text
    assert "2022-03-10" in text
    assert "VST-MOD-003-002" in text


def test_allergy_retrieval_text_handles_empty_registry(
    sample_patient: dict[str, Any],
) -> None:
    """Patients with no allergies should produce a safe empty-state sentence."""
    patient = deepcopy(sample_patient)
    patient["allergy_registry"] = []

    text = build_allergy_retrieval_text(patient)

    assert "PAT-MOD-003" in text
    assert "no documented allergy entries" in text
    assert "allergy_registry" in text


def test_retrieval_text_does_not_use_unsafe_interpretive_phrases(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """Retrieval text should not contain unsafe interpretation or treatment phrases."""
    generated_texts = [
        build_retrieval_text(sample_patient, sample_visit, "doctor_note"),
        build_retrieval_text(sample_patient, sample_visit, "lab_result"),
        build_retrieval_text(sample_patient, sample_visit, "prescription"),
        build_retrieval_text(sample_patient, None, "allergy"),
    ]

    combined_text = "\n".join(generated_texts).lower()

    for phrase in UNSAFE_RETRIEVAL_PHRASES:
        assert phrase not in combined_text


def test_source_types_align_with_config_constants(
    sample_patient: dict[str, Any],
    sample_visit: dict[str, Any],
) -> None:
    """The enricher should support every source_type in config.constants.SOURCE_TYPES."""
    assert SOURCE_TYPES == ("doctor_note", "lab_result", "prescription", "allergy")

    outputs: dict[str, str] = {}
    for source_type in SOURCE_TYPES:
        if source_type == "allergy":
            outputs[source_type] = build_retrieval_text(
                patient=sample_patient,
                visit=None,
                source_type=source_type,
            )
        else:
            outputs[source_type] = build_retrieval_text(
                patient=sample_patient,
                visit=sample_visit,
                source_type=source_type,
            )

    assert set(outputs) == set(SOURCE_TYPES)
    assert all(outputs[source_type].strip() for source_type in SOURCE_TYPES)


def test_lab_type_fixture_uses_locked_constants(
    sample_visit: dict[str, Any],
) -> None:
    """The test fixture should use lab types that exist in locked constants."""
    documented_lab_types = {
        lab["lab_type"] for lab in sample_visit["labs"]
    }

    assert documented_lab_types.issubset(set(LAB_TYPES))


def test_medication_fixture_uses_locked_constants(
    sample_visit: dict[str, Any],
) -> None:
    """The test fixture should use medication names that exist in the whitelist."""
    documented_medication_names = {
        medication["medication_name"] for medication in sample_visit["medications"]
    }

    assert documented_medication_names.issubset(set(MEDICATION_NAMES))
