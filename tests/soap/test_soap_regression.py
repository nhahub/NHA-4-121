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
            "A 56-year-old male patient is recorded for a follow_up visit. "
            "The documented condition list includes T2DM, HTN. "
            "The patient-level condition field documents type 2 diabetes and hypertension. "
            "This encounter is linked to a prior documented visit through "
            "prior_visit_id VST-MOD-003-003."
        ),
        "objective": (
            "Objective data from the encounter records blood pressure 142/88 mmHg, "
            "heart rate 78 bpm, weight 82.4 kg, and BMI 29.1. Laboratory results: "
            "HbA1c 7.8 % (HIGH); FBG 148 mg/dL (HIGH). The visit contains documented "
            "monitoring context for type 2 diabetes laboratory follow-up. "
            "Linked document references: DOC-MOD-003-004."
        ),
        "assessment": (
            "Diagnoses documented for this visit are summarized as T2DM, HTN. "
            "The visit diagnosis field documents type 2 diabetes and hypertension for this "
            "encounter. Retrieval focus includes patient-level conditions: type 2 diabetes "
            "and hypertension; visit diagnoses: type 2 diabetes and hypertension; "
            "laboratory entries: fbg and hba1c; medication entries: lisinopril and "
            "metformin; visit type: follow_up; timeline link: prior visit documented."
        ),
        "plan": (
            "The plan section records the active medication entries as documented: "
            "Metformin 500 mg twice_daily via oral; Lisinopril 10 mg once_daily via oral. "
            "The medication list includes documented entries related to type 2 diabetes "
            "medication documentation and hypertension medication documentation. "
            "Prior visit reference is VST-MOD-003-003."
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
            "The chart documents a 33-year-old female patient seen for a initial visit. "
            "The condition list records no chronic conditions. The record does not list "
            "chronic conditions in the patient-level condition field. This is documented "
            "as the first encounter type in the visit record."
        ),
        "objective": (
            "Recorded measurements include blood pressure 118/76 mmHg, heart rate 72 bpm, "
            "weight 64.5 kg, and BMI 23.4. The lab section records: no lab results "
            "recorded. No laboratory entries are documented for this visit. "
            "Linked document references: none."
        ),
        "assessment": (
            "The documented diagnosis summary for this encounter is: no chronic diagnosis "
            "listed. The visit diagnosis field does not list a chronic diagnosis for this "
            "encounter. This is documented as the first encounter type in the visit record."
        ),
        "plan": (
            "The plan section records the active medication entries as documented: "
            "no active whitelisted medications recorded. No active medication entries are "
            "documented for this visit. This is the first recorded visit in the available "
            "record."
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
            "For this follow_up entry, the record identifies a 56-year-old male patient. "
            "The condition list records T2DM, HTN, Asthma. The patient-level condition "
            "field documents type 2 diabetes, hypertension, and asthma. Retrieval focus "
            "includes patient-level conditions: type 2 diabetes, hypertension, and asthma; "
            "visit diagnoses: type 2 diabetes and hypertension; laboratory entries: "
            "creatinine, fbg, and hba1c; medication entries: lisinopril, metformin, and "
            "salbutamol inhaler; visit type: follow_up; timeline link: prior visit documented."
        ),
        "objective": (
            "The visit record lists blood pressure 142/88 mmHg, heart rate 78 bpm, "
            "weight 82.4 kg, and BMI 29.1. Documented lab results: HbA1c 7.8 % (HIGH); "
            "FBG 148 mg/dL (HIGH); Creatinine 1.1 mg/dL (NORMAL). The visit contains "
            "documented monitoring context for type 2 diabetes laboratory follow-up and "
            "hypertension kidney-related laboratory documentation. Linked document "
            "references: DOC-CHR-002-004."
        ),
        "assessment": (
            "Assessment summarizes the diagnoses documented for this visit: T2DM, HTN. "
            "The visit diagnosis field documents type 2 diabetes and hypertension for this "
            "encounter. The patient-level condition field documents type 2 diabetes, "
            "hypertension, and asthma."
        ),
        "plan": (
            "The documented plan keeps the medication list as recorded: Metformin 500 mg "
            "twice_daily via oral; Lisinopril 10 mg once_daily via oral; Salbutamol inhaler "
            "100 mcg as_needed via inhaled. The medication list includes documented entries "
            "related to type 2 diabetes medication documentation, hypertension medication "
            "documentation, and asthma medication documentation. Prior visit reference is "
            "VST-CHR-002-003. This encounter is linked to a prior documented visit through "
            "prior_visit_id VST-CHR-002-003."
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

    assert selected_templates["subjective"].template_id == "SUBJ-MOD-002"
    assert selected_templates["objective"].template_id == "OBJ-MOD-004"
    assert selected_templates["assessment"].template_id == "ASM-MOD-003"
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
    assert selected_templates["objective"].template_id == "OBJ-NRM-002"
    assert selected_templates["assessment"].template_id == "ASM-NRM-003"
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
    assert selected_templates["assessment"].template_id == "ASM-CHR-001"
    assert selected_templates["plan"].template_id == "PLAN-CHR-005"


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
    assert "This is the first recorded visit in the available record." in soap_text


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

    assert "This is the first recorded visit in the available record." in soap_note["plan"]


def test_subjective_section_regression_exact_text(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Subjective section wording must remain stable for this deterministic fixture.
    """
    visit = moderate_patient["visits"][0]
    soap_note = generate_soap_note(moderate_patient, visit)

    assert soap_note["subjective"] == (
        "A 56-year-old male patient is recorded for a follow_up visit. "
        "The documented condition list includes T2DM, HTN. "
        "The patient-level condition field documents type 2 diabetes and hypertension. "
        "This encounter is linked to a prior documented visit through "
        "prior_visit_id VST-MOD-003-003."
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
        "Objective data from the encounter records blood pressure 142/88 mmHg, "
        "heart rate 78 bpm, weight 82.4 kg, and BMI 29.1. Laboratory results: "
        "HbA1c 7.8 % (HIGH); FBG 148 mg/dL (HIGH). The visit contains documented "
        "monitoring context for type 2 diabetes laboratory follow-up. "
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
        "Diagnoses documented for this visit are summarized as T2DM, HTN. "
        "The visit diagnosis field documents type 2 diabetes and hypertension for this "
        "encounter. Retrieval focus includes patient-level conditions: type 2 diabetes "
        "and hypertension; visit diagnoses: type 2 diabetes and hypertension; "
        "laboratory entries: fbg and hba1c; medication entries: lisinopril and "
        "metformin; visit type: follow_up; timeline link: prior visit documented."
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
        "The plan section records the active medication entries as documented: "
        "Metformin 500 mg twice_daily via oral; Lisinopril 10 mg once_daily via oral. "
        "The medication list includes documented entries related to type 2 diabetes "
        "medication documentation and hypertension medication documentation. "
        "Prior visit reference is VST-MOD-003-003."
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


def test_generated_soap_contains_no_synthetic_dataset_disclaimer_text(
    moderate_patient: dict[str, Any],
    normal_empty_state_patient: dict[str, Any],
    chronic_patient: dict[str, Any],
) -> None:
    """Generated SOAP text must not expose dataset/disclaimer wording to RAG."""
    patients = (moderate_patient, normal_empty_state_patient, chronic_patient)
    forbidden_fragments = (
        "synthetic record",
        "synthetic facts",
        "synthetic academic dataset",
        "medical advice",
        "generated by ai",
    )

    for patient in patients:
        visit = patient["visits"][0]
        soap_note = generate_soap_note(patient, visit)
        normalized_text = " ".join(" ".join(soap_note.values()).lower().split())

        for fragment in forbidden_fragments:
            assert fragment not in normalized_text


def test_generated_soap_avoids_unsafe_interpretive_phrases(
    chronic_patient: dict[str, Any],
) -> None:
    """
    Generated SOAP must not introduce unsafe clinical interpretation language.
    """
    visit = chronic_patient["visits"][0]
    soap_note = generate_soap_note(chronic_patient, visit)
    normalized_text = " ".join(" ".join(soap_note.values()).lower().split())

    forbidden_phrases = (
        "likely",
        "suggestive of",
        "consistent with",
        "suspected",
        "appears to have",
        "probably",
        "may indicate",
        "may suggest",
        "poorly controlled",
        "well controlled",
        "uncontrolled",
        "deteriorating",
        "worsening",
        "improving clinically",
        "requires treatment",
        "should start",
        "recommend starting",
        "recommend treatment",
        "needs medication",
        "needs treatment",
        "rule out",
        "diagnosed with",
    )

    for phrase in forbidden_phrases:
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