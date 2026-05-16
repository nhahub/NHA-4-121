"""
tests/test_soap_renderers.py

Unit tests for deterministic SOAP fact-rendering utilities.

These tests protect Phase 1 and Phase 2 preparation of the SOAP refactor:
    - no wording changes,
    - no formatting changes,
    - no normalization changes,
    - no schema changes,
    - no probabilistic behavior,
    - no LLM behavior,
    - no template rendering behavior inside soap_renderers.py.

The assertions in this file intentionally use exact string equality to preserve
compatibility with the deterministic SOAP generation pipeline.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from soap.soap_renderers import (
    _age_at_visit,
    _format_labs,
    _format_list,
    _format_medications,
    build_fact_context,
)


@pytest.fixture
def realistic_labs() -> list[dict[str, Any]]:
    """Return realistic synthetic lab records for exact formatting tests."""
    return [
        {
            "lab_type": "HbA1c",
            "value": 7.8,
            "unit": "%",
            "reference_range": "<5.7",
            "flag": "HIGH",
        },
        {
            "lab_type": "FBG",
            "value": 148,
            "unit": "mg/dL",
            "reference_range": "70-99",
            "flag": "HIGH",
        },
        {
            "lab_type": "Creatinine",
            "value": 1.1,
            "unit": "mg/dL",
            "reference_range": "0.7-1.3",
            "flag": "NORMAL",
        },
    ]


@pytest.fixture
def realistic_medications() -> list[dict[str, Any]]:
    """Return realistic synthetic medication records for exact formatting tests."""
    return [
        {
            "medication_name": "Metformin",
            "medication_class": "Biguanide",
            "dose": "500 mg",
            "frequency": "twice_daily",
            "route": "oral",
            "start_date": "2024-01-10",
            "stop_date": None,
        },
        {
            "medication_name": "Lisinopril",
            "medication_class": "ACE Inhibitor",
            "dose": "10 mg",
            "frequency": "once_daily",
            "route": "oral",
            "start_date": "2024-01-10",
            "stop_date": None,
        },
        {
            "medication_name": "Salbutamol inhaler",
            "medication_class": "SABA",
            "dose": "100 mcg",
            "frequency": "as_needed",
            "route": "inhaled",
            "start_date": "2024-03-20",
            "stop_date": None,
        },
    ]


@pytest.fixture
def sample_patient(
    realistic_labs: list[dict[str, Any]],
    realistic_medications: list[dict[str, Any]],
) -> dict[str, Any]:
    """Return a realistic synthetic patient record for fact-context tests."""
    return {
        "schema_version": "1.0",
        "patient_id": "PAT-CHR-002",
        "demographics": {
            "name": "Synthetic Patient",
            "date_of_birth": "1968-06-01",
            "sex": "male",
        },
        "conditions": ["T2DM", "HTN", "Asthma"],
        "allergy_registry": [
            {
                "allergen": "Penicillin",
                "reaction": "skin rash",
                "severity": "moderate",
                "recorded_date": "2022-04-12",
                "source_visit_id": "VST-CHR-002-002",
            }
        ],
        "visits": [
            {
                "visit_id": "VST-CHR-002-004",
                "visit_date": "2024-06-15",
                "visit_type": "follow_up",
                "attending_physician": "Dr. Synthetic",
                "diagnoses": ["T2DM", "HTN"],
                "vitals": {
                    "bp_systolic": 142,
                    "bp_diastolic": 88,
                    "heart_rate": 78,
                    "weight_kg": 82.4,
                    "bmi": 29.1,
                },
                "labs": deepcopy(realistic_labs),
                "medications": deepcopy(realistic_medications),
                "soap_note": {},
                "linked_documents": ["DOC-CHR-002-004"],
                "prior_visit_id": "VST-CHR-002-003",
            }
        ],
        "metadata": {
            "tier": "chronic",
        },
    }


def test_format_labs_preserves_exact_spacing_separators_and_flags(
    realistic_labs: list[dict[str, Any]],
) -> None:
    """_format_labs must preserve exact lab formatting and separators."""
    expected = (
        "HbA1c 7.8 % (HIGH); "
        "FBG 148 mg/dL (HIGH); "
        "Creatinine 1.1 mg/dL (NORMAL)"
    )

    assert _format_labs(realistic_labs) == expected


def test_format_labs_with_single_value_preserves_exact_formatting() -> None:
    """A single lab must not include separators or extra spacing."""
    labs = [
        {
            "lab_type": "Hemoglobin",
            "value": 10.8,
            "unit": "g/dL",
            "reference_range": "12-16",
            "flag": "LOW",
        }
    ]

    assert _format_labs(labs) == "Hemoglobin 10.8 g/dL (LOW)"


def test_format_labs_empty_preserves_exact_empty_state() -> None:
    """Empty labs must preserve the current exact empty-state string."""
    assert _format_labs([]) == "no lab results recorded"


def test_format_medications_preserves_exact_dose_frequency_route_formatting(
    realistic_medications: list[dict[str, Any]],
) -> None:
    """_format_medications must preserve exact medication formatting."""
    expected = (
        "Metformin 500 mg twice_daily via oral; "
        "Lisinopril 10 mg once_daily via oral; "
        "Salbutamol inhaler 100 mcg as_needed via inhaled"
    )

    assert _format_medications(realistic_medications) == expected


def test_format_medications_with_single_value_preserves_exact_formatting() -> None:
    """A single medication must not include separators or extra spacing."""
    medications = [
        {
            "medication_name": "Omeprazole",
            "medication_class": "PPI",
            "dose": "20 mg",
            "frequency": "once_daily",
            "route": "oral",
            "start_date": "2024-02-01",
            "stop_date": None,
        }
    ]

    assert _format_medications(medications) == "Omeprazole 20 mg once_daily via oral"


def test_format_medications_empty_preserves_exact_empty_state() -> None:
    """Empty medications must preserve the current exact empty-state string."""
    assert _format_medications([]) == "no active whitelisted medications recorded"


def test_format_list_preserves_exact_comma_formatting() -> None:
    """_format_list must preserve comma-space formatting for normal lists."""
    assert _format_list(["T2DM", "HTN", "Asthma"]) == "T2DM, HTN, Asthma"


def test_format_list_converts_values_with_str_without_normalization() -> None:
    """_format_list must convert values using str() without normalization."""
    assert _format_list(["DOC-001", 12, None]) == "DOC-001, 12, None"


def test_format_list_empty_preserves_default_empty_text() -> None:
    """Empty generic lists must preserve the exact default string 'none'."""
    assert _format_list([]) == "none"


def test_format_list_empty_preserves_custom_empty_text() -> None:
    """Custom empty-state text must be returned exactly."""
    assert _format_list([], empty_text="no chronic conditions") == "no chronic conditions"
    assert (
        _format_list([], empty_text="no chronic diagnosis listed")
        == "no chronic diagnosis listed"
    )


def test_age_at_visit_before_birthday() -> None:
    """Age calculation must subtract one year before the birthday in visit year."""
    assert _age_at_visit("1968-06-01", "2024-05-31") == 55


def test_age_at_visit_on_birthday() -> None:
    """Age calculation must count the new age on the birthday."""
    assert _age_at_visit("1968-06-01", "2024-06-01") == 56


def test_age_at_visit_after_birthday() -> None:
    """Age calculation must preserve deterministic age after birthday."""
    assert _age_at_visit("1968-06-01", "2024-06-15") == 56


def test_build_fact_context_extracts_raw_identifiers_exactly(
    sample_patient: dict[str, Any],
) -> None:
    """build_fact_context must preserve raw patient and visit identifiers."""
    visit = sample_patient["visits"][0]
    facts = build_fact_context(sample_patient, visit)

    assert facts["patient_id"] == "PAT-CHR-002"
    assert facts["visit_id"] == "VST-CHR-002-004"
    assert facts["date_of_birth"] == "1968-06-01"
    assert facts["visit_date"] == "2024-06-15"
    assert facts["prior_visit_id"] == "VST-CHR-002-003"


def test_build_fact_context_extracts_tier_exactly(
    sample_patient: dict[str, Any],
) -> None:
    """build_fact_context must expose metadata.tier for deterministic routing."""
    visit = sample_patient["visits"][0]
    facts = build_fact_context(sample_patient, visit)

    assert facts["tier"] == "chronic"


def test_build_fact_context_extracts_demographic_and_visit_facts_exactly(
    sample_patient: dict[str, Any],
) -> None:
    """build_fact_context must preserve demographic and visit facts exactly."""
    visit = sample_patient["visits"][0]
    facts = build_fact_context(sample_patient, visit)

    assert facts["age"] == 56
    assert facts["sex"] == "male"
    assert facts["visit_type"] == "follow_up"
    assert facts["conditions"] == ["T2DM", "HTN", "Asthma"]
    assert facts["diagnoses"] == ["T2DM", "HTN"]


def test_build_fact_context_preserves_exact_condition_and_diagnosis_text(
    sample_patient: dict[str, Any],
) -> None:
    """Rendered condition and diagnosis strings must preserve exact formatting."""
    visit = sample_patient["visits"][0]
    facts = build_fact_context(sample_patient, visit)

    assert facts["condition_text"] == "T2DM, HTN, Asthma"
    assert facts["diagnosis_text"] == "T2DM, HTN"


def test_build_fact_context_preserves_exact_vital_values_and_bp_formatting(
    sample_patient: dict[str, Any],
) -> None:
    """Vital facts and BP formatting must remain exact."""
    visit = sample_patient["visits"][0]
    facts = build_fact_context(sample_patient, visit)

    assert facts["vitals"] == {
        "bp_systolic": 142,
        "bp_diastolic": 88,
        "heart_rate": 78,
        "weight_kg": 82.4,
        "bmi": 29.1,
    }
    assert facts["bp_systolic"] == 142
    assert facts["bp_diastolic"] == 88
    assert facts["heart_rate"] == 78
    assert facts["weight_kg"] == 82.4
    assert facts["bmi"] == 29.1
    assert facts["bp_text"] == "142/88 mmHg"


def test_build_fact_context_preserves_exact_lab_text(
    sample_patient: dict[str, Any],
) -> None:
    """Rendered lab text must preserve exact lab formatting from _format_labs."""
    visit = sample_patient["visits"][0]
    facts = build_fact_context(sample_patient, visit)

    expected = (
        "HbA1c 7.8 % (HIGH); "
        "FBG 148 mg/dL (HIGH); "
        "Creatinine 1.1 mg/dL (NORMAL)"
    )

    assert facts["labs"] == visit["labs"]
    assert facts["lab_text"] == expected


def test_build_fact_context_preserves_exact_medication_text(
    sample_patient: dict[str, Any],
) -> None:
    """Rendered medication text must preserve exact medication formatting."""
    visit = sample_patient["visits"][0]
    facts = build_fact_context(sample_patient, visit)

    expected = (
        "Metformin 500 mg twice_daily via oral; "
        "Lisinopril 10 mg once_daily via oral; "
        "Salbutamol inhaler 100 mcg as_needed via inhaled"
    )

    assert facts["medications"] == visit["medications"]
    assert facts["medication_text"] == expected


def test_build_fact_context_preserves_exact_linked_documents_text(
    sample_patient: dict[str, Any],
) -> None:
    """Linked document rendering must use exact comma formatting."""
    visit = sample_patient["visits"][0]
    facts = build_fact_context(sample_patient, visit)

    assert facts["linked_documents"] == ["DOC-CHR-002-004"]
    assert facts["linked_documents_text"] == "DOC-CHR-002-004"


def test_build_fact_context_preserves_exact_prior_visit_text(
    sample_patient: dict[str, Any],
) -> None:
    """Prior visit text must preserve current exact wording."""
    visit = sample_patient["visits"][0]
    facts = build_fact_context(sample_patient, visit)

    assert facts["prior_text"] == "Prior visit reference is VST-CHR-002-003."


def test_build_fact_context_empty_labs_preserves_exact_empty_state(
    sample_patient: dict[str, Any],
) -> None:
    """Empty lab rendering in fact context must preserve exact empty-state text."""
    patient = deepcopy(sample_patient)
    visit = patient["visits"][0]
    visit["labs"] = []

    facts = build_fact_context(patient, visit)

    assert facts["labs"] == []
    assert facts["lab_text"] == "no lab results recorded"


def test_build_fact_context_empty_medications_preserves_exact_empty_state(
    sample_patient: dict[str, Any],
) -> None:
    """Empty medication rendering in fact context must preserve exact text."""
    patient = deepcopy(sample_patient)
    visit = patient["visits"][0]
    visit["medications"] = []

    facts = build_fact_context(patient, visit)

    assert facts["medications"] == []
    assert facts["medication_text"] == "no active whitelisted medications recorded"


def test_build_fact_context_empty_linked_documents_preserves_none(
    sample_patient: dict[str, Any],
) -> None:
    """Empty linked documents must preserve exact generic empty list text."""
    patient = deepcopy(sample_patient)
    visit = patient["visits"][0]
    visit["linked_documents"] = []

    facts = build_fact_context(patient, visit)

    assert facts["linked_documents"] == []
    assert facts["linked_documents_text"] == "none"


def test_build_fact_context_empty_conditions_preserves_exact_empty_state(
    sample_patient: dict[str, Any],
) -> None:
    """Normal patients with no chronic conditions must preserve exact wording."""
    patient = deepcopy(sample_patient)
    patient["conditions"] = []
    visit = patient["visits"][0]

    facts = build_fact_context(patient, visit)

    assert facts["conditions"] == []
    assert facts["condition_text"] == "no chronic conditions"


def test_build_fact_context_empty_diagnoses_preserves_exact_empty_state(
    sample_patient: dict[str, Any],
) -> None:
    """Empty diagnoses must preserve exact diagnosis empty-state wording."""
    patient = deepcopy(sample_patient)
    visit = patient["visits"][0]
    visit["diagnoses"] = []

    facts = build_fact_context(patient, visit)

    assert facts["diagnoses"] == []
    assert facts["diagnosis_text"] == "no chronic diagnosis listed"


def test_build_fact_context_null_prior_visit_preserves_exact_first_visit_text(
    sample_patient: dict[str, Any],
) -> None:
    """Null prior_visit_id must preserve exact first-visit wording."""
    patient = deepcopy(sample_patient)
    visit = patient["visits"][0]
    visit["prior_visit_id"] = None

    facts = build_fact_context(patient, visit)

    assert facts["prior_visit_id"] is None
    assert facts["prior_text"] == "This is the first recorded visit in the synthetic record."


def test_build_fact_context_combined_empty_state_behavior(
    sample_patient: dict[str, Any],
) -> None:
    """All empty-state strings must remain exact in a normal-patient scenario."""
    patient = deepcopy(sample_patient)
    patient["patient_id"] = "PAT-NRM-001"
    patient["conditions"] = []
    patient["metadata"] = {"tier": "normal"}

    visit = patient["visits"][0]
    visit["visit_id"] = "VST-NRM-001-001"
    visit["visit_type"] = "initial"
    visit["diagnoses"] = []
    visit["labs"] = []
    visit["medications"] = []
    visit["linked_documents"] = []
    visit["prior_visit_id"] = None

    facts = build_fact_context(patient, visit)

    assert facts["patient_id"] == "PAT-NRM-001"
    assert facts["visit_id"] == "VST-NRM-001-001"
    assert facts["tier"] == "normal"
    assert facts["condition_text"] == "no chronic conditions"
    assert facts["diagnosis_text"] == "no chronic diagnosis listed"
    assert facts["lab_text"] == "no lab results recorded"
    assert facts["medication_text"] == "no active whitelisted medications recorded"
    assert facts["linked_documents_text"] == "none"
    assert facts["prior_text"] == "This is the first recorded visit in the synthetic record."


def test_build_fact_context_is_deterministic_for_same_input(
    sample_patient: dict[str, Any],
) -> None:
    """Repeated fact-context construction must produce exactly equal output."""
    visit = sample_patient["visits"][0]

    first = build_fact_context(sample_patient, visit)
    second = build_fact_context(sample_patient, visit)

    assert first == second


def test_build_fact_context_does_not_mutate_patient_or_visit(
    sample_patient: dict[str, Any],
) -> None:
    """Fact rendering must not mutate the patient JSON or visit dictionary."""
    patient_before = deepcopy(sample_patient)
    visit_before = deepcopy(sample_patient["visits"][0])

    _ = build_fact_context(sample_patient, sample_patient["visits"][0])

    assert sample_patient == patient_before
    assert sample_patient["visits"][0] == visit_before