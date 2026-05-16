"""
tests/test_soap_regression.py

Golden-output regression tests for deterministic diversified SOAP generation.

Purpose:
    This file acts as a hard safety gate against accidental SOAP drift after
    introducing deterministic diversified SOAP templates.

Safety contract:
    - Generated SOAP text must remain deterministic.
    - Same patient + same visit must always produce the same SOAP output.
    - No schema changes are allowed.
    - No LLM logic is allowed.
    - No randomization is allowed.
    - No medical fact generation is allowed.
    - No medication, lab, diagnosis, vital, or identifier drift is allowed.

These tests intentionally use strict equality assertions against hardcoded
golden outputs.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from soap.soap_generator import (
    add_soap_notes_to_patient,
    generate_soap_note,
)
from soap.soap_renderers import build_fact_context
from soap.soap_safety import FORBIDDEN_CLINICAL_PHRASES
from soap.soap_selector import select_templates_from_fact_context


@pytest.fixture
def moderate_patient() -> dict[str, Any]:
    """
    Return a moderate synthetic patient for golden-output regression.

    This fixture protects exact deterministic output for:
        - moderate tier template routing,
        - BP formatting,
        - lab formatting,
        - medication formatting,
        - diagnosis formatting,
        - prior visit rendering.
    """
    return {
        "schema_version": "1.0",
        "patient_id": "PAT-MOD-003",
        "demographics": {
            "name": "Synthetic Patient",
            "date_of_birth": "1968-06-01",
            "sex": "male",
        },
        "conditions": ["T2DM", "HTN"],
        "allergy_registry": [],
        "visits": [
            {
                "visit_id": "VST-MOD-003-004",
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
                "labs": [
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
                ],
                "medications": [
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
                ],
                "soap_note": {},
                "linked_documents": ["DOC-MOD-003-004"],
                "prior_visit_id": "VST-MOD-003-003",
            }
        ],
        "metadata": {
            "tier": "moderate",
        },
    }


@pytest.fixture
def normal_empty_state_patient() -> dict[str, Any]:
    """
    Return a normal synthetic patient with empty optional clinical lists.

    This fixture protects exact empty-state rendering for:
        - no chronic conditions,
        - no chronic diagnosis listed,
        - no lab results recorded,
        - no active whitelisted medications recorded,
        - none,
        - first recorded visit prior-reference text.
    """
    return {
        "schema_version": "1.0",
        "patient_id": "PAT-NRM-001",
        "demographics": {
            "name": "Synthetic Normal Patient",
            "date_of_birth": "1990-03-10",
            "sex": "female",
        },
        "conditions": [],
        "allergy_registry": [],
        "visits": [
            {
                "visit_id": "VST-NRM-001-001",
                "visit_date": "2024-02-20",
                "visit_type": "initial",
                "attending_physician": "Dr. Synthetic",
                "diagnoses": [],
                "vitals": {
                    "bp_systolic": 118,
                    "bp_diastolic": 76,
                    "heart_rate": 72,
                    "weight_kg": 64.5,
                    "bmi": 23.4,
                },
                "labs": [],
                "medications": [],
                "soap_note": {},
                "linked_documents": [],
                "prior_visit_id": None,
            }
        ],
        "metadata": {
            "tier": "normal",
        },
    }


@pytest.fixture
def chronic_patient() -> dict[str, Any]:
    """
    Return a chronic synthetic patient for tier-specific regression coverage.

    This fixture protects deterministic chronic-tier template routing and
    longitudinal-style wording without adding unsafe medical interpretation.
    """
    return {
        "schema_version": "1.0",
        "patient_id": "PAT-CHR-002",
        "demographics": {
            "name": "Synthetic Chronic Patient",
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
                "labs": [
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
                ],
                "medications": [
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
                ],
                "soap_note": {},
                "linked_documents": ["DOC-CHR-002-004"],
                "prior_visit_id": "VST-CHR-002-003",
            }
        ],
        "metadata": {
            "tier": "chronic",
        },
    }


def test_moderate_patient_soap_output_matches_golden_dictionary(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Moderate patient SOAP output must match deterministic golden output exactly.
    """
    visit = moderate_patient["visits"][0]

    expected = {
        "subjective": (
            "The synthetic record documents a 56-year-old male patient "
            "attending a follow_up visit. The structured condition list records "
            "T2DM, HTN. The note is generated only from stored synthetic facts and does "
            "not add diagnosis, prediction, or clinical judgment beyond the record."
        ),
        "objective": (
            "Objective measurements for this visit include blood pressure "
            "142/88 mmHg, heart rate 78 bpm, weight 82.4 kg, and BMI 29.1. "
            "Laboratory data for this visit: HbA1c 7.8 % (HIGH); FBG 148 mg/dL (HIGH). "
            "Linked document references: DOC-MOD-003-004."
        ),
        "assessment": (
            "The assessment section summarizes only documented diagnoses for this visit: "
            "T2DM, HTN. "
            "The visit remains grounded in the structured JSON record and does not infer "
            "unstated conditions."
        ),
        "plan": (
            "The documented plan records the whitelisted medication list exactly as stored: "
            "Metformin 500 mg twice_daily via oral; Lisinopril 10 mg once_daily via oral. "
            "Prior visit reference is VST-MOD-003-003. Follow-up context should be interpreted only "
            "as part of this synthetic academic dataset, not as medical advice."
        ),
    }

    assert generate_soap_note(moderate_patient, visit) == expected


def test_normal_empty_state_soap_output_matches_golden_dictionary(
    normal_empty_state_patient: dict[str, Any],
) -> None:
    """
    Normal patient empty-state SOAP output must preserve exact fallback strings.
    """
    visit = normal_empty_state_patient["visits"][0]

    expected = {
        "subjective": (
            "The synthetic record documents a 33-year-old female patient "
            "attending a initial visit. The structured condition list records "
            "no chronic conditions. The note is generated only from stored synthetic facts and does "
            "not add diagnosis, prediction, or clinical judgment beyond the record."
        ),
        "objective": (
            "Objective structured data records blood pressure "
            "118/76 mmHg, heart rate "
            "72 bpm, weight 64.5 kg, and BMI "
            "23.4. Laboratory data for this visit: no lab results recorded. "
            "Linked document references: none."
        ),
        "assessment": (
            "Assessment is limited to documented diagnoses for this visit: "
            "no chronic diagnosis listed. The visit remains grounded in the structured JSON record "
            "and does not infer unstated conditions."
        ),
        "plan": (
            "The documented plan records the whitelisted medication list exactly as stored: "
            "no active whitelisted medications recorded. "
            "This is the first recorded visit in the synthetic record. Follow-up context should be interpreted only "
            "as part of this synthetic academic dataset, not as medical advice."
        ),
    }

    assert generate_soap_note(normal_empty_state_patient, visit) == expected


def test_chronic_patient_soap_output_matches_golden_dictionary(
    chronic_patient: dict[str, Any],
) -> None:
    """
    Chronic patient SOAP output must match deterministic golden output exactly.
    """
    visit = chronic_patient["visits"][0]

    expected = {
        "subjective": (
            "For this follow_up entry, the stored synthetic data identifies a "
            "56-year-old male patient. The structured condition list records "
            "T2DM, HTN, Asthma. The section remains limited to documented facts."
        ),
        "objective": (
            "The structured visit record lists blood pressure 142/88 mmHg, "
            "heart rate 78 bpm, weight 82.4 kg, and BMI 29.1. "
            "Laboratory data for this visit: HbA1c 7.8 % (HIGH); "
            "FBG 148 mg/dL (HIGH); Creatinine 1.1 mg/dL (NORMAL). "
            "Linked document references: DOC-CHR-002-004."
        ),
        "assessment": (
            "The visit diagnosis summary includes only the structured diagnoses: "
            "T2DM, HTN. The section remains grounded in the JSON record and does "
            "not add unstated conditions."
        ),
        "plan": (
            "The structured plan data records the whitelisted medication list without change: "
            "Metformin 500 mg twice_daily via oral; Lisinopril 10 mg once_daily via oral; "
            "Salbutamol inhaler 100 mcg as_needed via inhaled. "
            "Prior visit reference is VST-CHR-002-003. Follow-up context is included only for the "
            "synthetic academic dataset and should not be used as medical advice."
        ),
    }

    assert generate_soap_note(chronic_patient, visit) == expected


def test_soap_generation_is_deterministically_stable_for_same_input(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Repeated SOAP generation for identical input must produce identical output.
    """
    visit = moderate_patient["visits"][0]

    first_output = generate_soap_note(moderate_patient, visit)
    second_output = generate_soap_note(moderate_patient, visit)
    third_output = generate_soap_note(moderate_patient, visit)

    assert first_output == second_output
    assert second_output == third_output
    assert first_output == third_output


def test_soap_generation_does_not_mutate_patient_or_visit(
    moderate_patient: dict[str, Any],
) -> None:
    """
    SOAP generation must not mutate the patient JSON or visit dictionary.
    """
    patient_before = deepcopy(moderate_patient)
    visit_before = deepcopy(moderate_patient["visits"][0])

    _ = generate_soap_note(moderate_patient, moderate_patient["visits"][0])

    assert moderate_patient == patient_before
    assert moderate_patient["visits"][0] == visit_before


def test_add_soap_notes_to_patient_returns_deepcopy_with_soap_notes(
    moderate_patient: dict[str, Any],
) -> None:
    """
    add_soap_notes_to_patient must return a copied patient with SOAP notes added.
    """
    original_patient = deepcopy(moderate_patient)
    updated_patient = add_soap_notes_to_patient(moderate_patient)

    assert moderate_patient == original_patient
    assert updated_patient is not moderate_patient
    assert updated_patient["visits"][0] is not moderate_patient["visits"][0]
    assert updated_patient["visits"][0]["soap_note"] == generate_soap_note(
        updated_patient,
        updated_patient["visits"][0],
    )


def test_generated_soap_contains_only_expected_section_keys(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Generated SOAP schema must remain exactly four SOAP sections.
    """
    visit = moderate_patient["visits"][0]
    soap_note = generate_soap_note(moderate_patient, visit)

    assert list(soap_note.keys()) == [
        "subjective",
        "objective",
        "assessment",
        "plan",
    ]


def test_template_selection_for_moderate_patient_is_regression_stable(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Selected template IDs must remain stable for the moderate golden fixture.
    """
    visit = moderate_patient["visits"][0]
    facts = build_fact_context(moderate_patient, visit)
    selected_templates = select_templates_from_fact_context(facts)

    assert selected_templates["subjective"].template_id == "SUBJ-MOD-001"
    assert selected_templates["objective"].template_id == "OBJ-MOD-002"
    assert selected_templates["assessment"].template_id == "ASM-MOD-001"
    assert selected_templates["plan"].template_id == "PLAN-MOD-001"


def test_template_selection_for_normal_patient_is_regression_stable(
    normal_empty_state_patient: dict[str, Any],
) -> None:
    """
    Selected template IDs must remain stable for the normal golden fixture.
    """
    visit = normal_empty_state_patient["visits"][0]
    facts = build_fact_context(normal_empty_state_patient, visit)
    selected_templates = select_templates_from_fact_context(facts)

    assert selected_templates["subjective"].template_id == "SUBJ-NRM-001"
    assert selected_templates["objective"].template_id == "OBJ-NRM-001"
    assert selected_templates["assessment"].template_id == "ASM-NRM-002"
    assert selected_templates["plan"].template_id == "PLAN-NRM-001"


def test_template_selection_for_chronic_patient_is_regression_stable(
    chronic_patient: dict[str, Any],
) -> None:
    """
    Selected template IDs must remain stable for the chronic golden fixture.
    """
    visit = chronic_patient["visits"][0]
    facts = build_fact_context(chronic_patient, visit)
    selected_templates = select_templates_from_fact_context(facts)

    assert selected_templates["subjective"].template_id == "SUBJ-CHR-004"
    assert selected_templates["objective"].template_id == "OBJ-CHR-003"
    assert selected_templates["assessment"].template_id == "ASM-CHR-004"
    assert selected_templates["plan"].template_id == "PLAN-CHR-004"


def test_empty_state_strings_are_preserved_exactly(
    normal_empty_state_patient: dict[str, Any],
) -> None:
    """
    Generated SOAP must preserve exact empty-state strings currently used.
    """
    visit = normal_empty_state_patient["visits"][0]
    soap_note = generate_soap_note(normal_empty_state_patient, visit)
    soap_text = " ".join(soap_note.values())

    assert "no lab results recorded" in soap_text
    assert "no active whitelisted medications recorded" in soap_text
    assert "no chronic conditions" in soap_text
    assert "no chronic diagnosis listed" in soap_text
    assert "Linked document references: none." in soap_text
    assert "This is the first recorded visit in the synthetic record." in soap_text


def test_medication_formatting_regression_exact_phrase(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Medication formatting must preserve exact name, dose, frequency, and route.
    """
    visit = moderate_patient["visits"][0]
    soap_note = generate_soap_note(moderate_patient, visit)

    assert "Metformin 500 mg twice_daily via oral" in soap_note["plan"]
    assert "Lisinopril 10 mg once_daily via oral" in soap_note["plan"]
    assert (
        "Metformin 500 mg twice_daily via oral; "
        "Lisinopril 10 mg once_daily via oral"
        in soap_note["plan"]
    )


def test_lab_formatting_regression_exact_phrase(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Lab formatting must preserve exact lab type, value, unit, flag, and spacing.
    """
    visit = moderate_patient["visits"][0]
    soap_note = generate_soap_note(moderate_patient, visit)

    assert "HbA1c 7.8 % (HIGH)" in soap_note["objective"]
    assert "FBG 148 mg/dL (HIGH)" in soap_note["objective"]
    assert (
        "HbA1c 7.8 % (HIGH); FBG 148 mg/dL (HIGH)"
        in soap_note["objective"]
    )


def test_bp_formatting_regression_exact_phrase(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Blood pressure formatting must preserve exact systolic/diastolic text.
    """
    visit = moderate_patient["visits"][0]
    soap_note = generate_soap_note(moderate_patient, visit)

    assert "142/88 mmHg" in soap_note["objective"]
    assert "heart rate 78 bpm" in soap_note["objective"]
    assert "weight 82.4 kg" in soap_note["objective"]
    assert "BMI 29.1" in soap_note["objective"]


def test_prior_visit_rendering_regression_exact_phrase(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Prior visit rendering must preserve the exact current wording.
    """
    visit = moderate_patient["visits"][0]
    soap_note = generate_soap_note(moderate_patient, visit)

    assert "Prior visit reference is VST-MOD-003-003." in soap_note["plan"]


def test_first_visit_prior_rendering_regression_exact_phrase(
    normal_empty_state_patient: dict[str, Any],
) -> None:
    """
    First-visit prior rendering must preserve the exact current wording.
    """
    visit = normal_empty_state_patient["visits"][0]
    soap_note = generate_soap_note(normal_empty_state_patient, visit)

    assert "This is the first recorded visit in the synthetic record." in soap_note["plan"]


def test_subjective_section_regression_exact_text(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Subjective section wording must remain stable for this deterministic fixture.
    """
    visit = moderate_patient["visits"][0]
    soap_note = generate_soap_note(moderate_patient, visit)

    assert soap_note["subjective"] == (
        "The synthetic record documents a 56-year-old male patient "
        "attending a follow_up visit. The structured condition list records "
        "T2DM, HTN. The note is generated only from stored synthetic facts and does "
        "not add diagnosis, prediction, or clinical judgment beyond the record."
    )


def test_objective_section_regression_exact_text(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Objective section wording must remain stable for this deterministic fixture.
    """
    visit = moderate_patient["visits"][0]
    soap_note = generate_soap_note(moderate_patient, visit)

    assert soap_note["objective"] == (
        "Objective measurements for this visit include blood pressure "
        "142/88 mmHg, heart rate 78 bpm, weight 82.4 kg, and BMI 29.1. "
        "Laboratory data for this visit: HbA1c 7.8 % (HIGH); FBG 148 mg/dL (HIGH). "
        "Linked document references: DOC-MOD-003-004."
    )


def test_assessment_section_regression_exact_text(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Assessment section wording must remain stable for this deterministic fixture.
    """
    visit = moderate_patient["visits"][0]
    soap_note = generate_soap_note(moderate_patient, visit)

    assert soap_note["assessment"] == (
        "The assessment section summarizes only documented diagnoses for this visit: "
        "T2DM, HTN. "
        "The visit remains grounded in the structured JSON record and does not infer "
        "unstated conditions."
    )


def test_plan_section_regression_exact_text(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Plan section wording must remain stable for this deterministic fixture.
    """
    visit = moderate_patient["visits"][0]
    soap_note = generate_soap_note(moderate_patient, visit)

    assert soap_note["plan"] == (
        "The documented plan records the whitelisted medication list exactly as stored: "
        "Metformin 500 mg twice_daily via oral; Lisinopril 10 mg once_daily via oral. "
        "Prior visit reference is VST-MOD-003-003. Follow-up context should be interpreted only "
        "as part of this synthetic academic dataset, not as medical advice."
    )


def test_all_generated_sections_are_non_empty_strings(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Every generated SOAP section must be a non-empty string.
    """
    visit = moderate_patient["visits"][0]
    soap_note = generate_soap_note(moderate_patient, visit)

    for section_text in soap_note.values():
        assert isinstance(section_text, str)
        assert section_text
        assert section_text == section_text.strip()


def test_generated_soap_contains_no_unrendered_placeholders(
    chronic_patient: dict[str, Any],
) -> None:
    """
    Generated SOAP must not contain unrendered template placeholders.
    """
    visit = chronic_patient["visits"][0]
    soap_note = generate_soap_note(chronic_patient, visit)

    for section_text in soap_note.values():
        assert "{" not in section_text
        assert "}" not in section_text


def test_generated_soap_preserves_required_facts_across_sections(
    chronic_patient: dict[str, Any],
) -> None:
    """
    Generated SOAP must preserve retrieval-critical structured facts.
    """
    visit = chronic_patient["visits"][0]
    soap_note = generate_soap_note(chronic_patient, visit)
    soap_text = " ".join(soap_note.values())

    assert "T2DM, HTN, Asthma" in soap_text
    assert "T2DM, HTN" in soap_text
    assert "142/88 mmHg" in soap_text
    assert "HbA1c 7.8 % (HIGH)" in soap_text
    assert "FBG 148 mg/dL (HIGH)" in soap_text
    assert "Creatinine 1.1 mg/dL (NORMAL)" in soap_text
    assert "Metformin 500 mg twice_daily via oral" in soap_text
    assert "Lisinopril 10 mg once_daily via oral" in soap_text
    assert "Salbutamol inhaler 100 mcg as_needed via inhaled" in soap_text
    assert "DOC-CHR-002-004" in soap_text
    assert "VST-CHR-002-003" in soap_text


def test_generated_soap_avoids_unsafe_interpretive_phrases(
    chronic_patient: dict[str, Any],
) -> None:
    """
    Generated SOAP must not introduce unsafe clinical interpretation language.
    """
    visit = chronic_patient["visits"][0]
    soap_note = generate_soap_note(chronic_patient, visit)
    normalized_text = " ".join(" ".join(soap_note.values()).lower().split())

    for phrase in FORBIDDEN_CLINICAL_PHRASES:
        assert phrase not in normalized_text


def test_realistic_patient_fixture_is_not_modified_across_regression_checks(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Multiple regression checks must not introduce stateful behavior.
    """
    patient_copy = deepcopy(moderate_patient)
    visit = moderate_patient["visits"][0]

    output_one = generate_soap_note(moderate_patient, visit)
    output_two = generate_soap_note(moderate_patient, visit)

    assert output_one == output_two
    assert moderate_patient == patient_copy