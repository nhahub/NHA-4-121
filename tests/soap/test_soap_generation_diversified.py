"""
tests/test_soap_generation_diversified.py

Integration-style tests for deterministic diversified SOAP generation.

Purpose:
    Validate that the diversified SOAP generation pipeline remains:
        - deterministic,
        - schema-stable,
        - fact-preserving,
        - retrieval-safe,
        - validator-safe,
        - free from unsafe clinical interpretation.

Architecture under test:
    Structured JSON
        ↓
    build_fact_context()
        ↓
    deterministic template selection
        ↓
    template rendering
        ↓
    SOAP note dictionary

Safety contract:
    - No LLM calls.
    - No randomization.
    - No medical fact generation.
    - No diagnosis inference.
    - No medication invention.
    - No lab invention.
    - No vital-sign drift.
    - No schema drift.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from soap.soap_generator import add_soap_notes_to_patient, generate_soap_note
from soap.soap_renderers import build_fact_context
from soap.soap_contract import PATIENT_TIERS, SOAP_SECTIONS, SoapTemplate
from soap.soap_safety import DEBUG_TEMPLATE_MARKERS, FORBIDDEN_CLINICAL_PHRASES
from soap.soap_selector import select_templates_from_fact_context


SOAP_SECTION_KEYS = list(SOAP_SECTIONS)



MEDICATION_WHITELIST_NAMES = (
    "Metformin",
    "Glibenclamide",
    "Lisinopril",
    "Amlodipine",
    "Losartan",
    "Salbutamol inhaler",
    "Budesonide inhaler",
    "Ferrous sulfate",
    "Omeprazole",
)


@pytest.fixture
def normal_patient() -> dict[str, Any]:
    """Return a normal-tier patient with empty optional clinical lists."""
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
def moderate_patient() -> dict[str, Any]:
    """Return a moderate-tier patient with T2DM and HTN facts."""
    return {
        "schema_version": "1.0",
        "patient_id": "PAT-MOD-003",
        "demographics": {
            "name": "Synthetic Moderate Patient",
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
def chronic_patient() -> dict[str, Any]:
    """Return a chronic-tier patient with multiple conditions and medications."""
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


def _combined_soap_text(soap_note: dict[str, str]) -> str:
    """Return all SOAP sections joined into one text string."""
    return " ".join(soap_note[section] for section in SOAP_SECTION_KEYS)


def _assert_standard_soap_shape(soap_note: dict[str, str]) -> None:
    """Assert that generated SOAP preserves the exact four-section schema."""
    assert list(soap_note.keys()) == SOAP_SECTION_KEYS

    for section in SOAP_SECTION_KEYS:
        assert isinstance(soap_note[section], str)
        assert soap_note[section]
        assert soap_note[section] == soap_note[section].strip()


def _assert_no_unrendered_placeholders(soap_note: dict[str, str]) -> None:
    """Assert that rendered SOAP contains no leftover template placeholders."""
    for section_text in soap_note.values():
        assert "{" not in section_text
        assert "}" not in section_text


def _assert_no_unsafe_interpretive_phrases(soap_note: dict[str, str]) -> None:
    """Assert that SOAP text does not contain unsafe interpretation phrases."""
    normalized_text = " ".join(_combined_soap_text(soap_note).lower().split())

    for phrase in FORBIDDEN_CLINICAL_PHRASES:
        assert phrase not in normalized_text


def _assert_medication_mentions_are_current(
    soap_note: dict[str, str],
    visit: dict[str, Any],
) -> None:
    """Assert SOAP does not mention whitelisted medications outside current meds."""
    soap_text = _combined_soap_text(soap_note)
    current_med_names = {
        medication["medication_name"]
        for medication in visit.get("medications", [])
    }

    for medication_name in MEDICATION_WHITELIST_NAMES:
        if medication_name in soap_text:
            assert medication_name in current_med_names


def _assert_required_visit_facts_are_preserved(
    soap_note: dict[str, str],
    visit: dict[str, Any],
) -> None:
    """Assert core retrieval-critical visit facts are preserved in generated SOAP."""
    soap_text = _combined_soap_text(soap_note)
    vitals = visit["vitals"]

    assert f"{vitals['bp_systolic']}/{vitals['bp_diastolic']} mmHg" in soap_text
    assert f"{vitals['heart_rate']} bpm" in soap_text
    assert f"{vitals['weight_kg']} kg" in soap_text
    assert f"BMI {vitals['bmi']}" in soap_text

    for lab in visit.get("labs", []):
        expected_lab_text = (
            f"{lab['lab_type']} {lab['value']} {lab['unit']} ({lab['flag']})"
        )
        assert expected_lab_text in soap_text

    for medication in visit.get("medications", []):
        expected_medication_text = (
            f"{medication['medication_name']} {medication['dose']} "
            f"{medication['frequency']} via {medication['route']}"
        )
        assert expected_medication_text in soap_text

    for diagnosis in visit.get("diagnoses", []):
        assert diagnosis in soap_text

    for document_id in visit.get("linked_documents", []):
        assert document_id in soap_text

    if visit.get("prior_visit_id"):
        assert visit["prior_visit_id"] in soap_text


@pytest.mark.parametrize(
    "fixture_name, expected_tier",
    [
        ("normal_patient", "normal"),
        ("moderate_patient", "moderate"),
        ("chronic_patient", "chronic"),
    ],
)
def test_diversified_generation_produces_standard_soap_shape_for_each_tier(
    request: pytest.FixtureRequest,
    fixture_name: str,
    expected_tier: str,
) -> None:
    """SOAP generation must produce the standard four-section structure by tier."""
    patient = request.getfixturevalue(fixture_name)
    visit = patient["visits"][0]

    facts = build_fact_context(patient, visit)
    soap_note = generate_soap_note(patient, visit)

    assert facts["tier"] == expected_tier
    _assert_standard_soap_shape(soap_note)
    _assert_no_unrendered_placeholders(soap_note)
    _assert_no_unsafe_interpretive_phrases(soap_note)


@pytest.mark.parametrize(
    "fixture_name",
    [
        "normal_patient",
        "moderate_patient",
        "chronic_patient",
    ],
)
def test_diversified_generation_is_deterministic_for_same_input(
    request: pytest.FixtureRequest,
    fixture_name: str,
) -> None:
    """Same patient and same visit must always produce exactly the same SOAP."""
    patient = request.getfixturevalue(fixture_name)
    visit = patient["visits"][0]

    first = generate_soap_note(patient, visit)
    second = generate_soap_note(patient, visit)
    third = generate_soap_note(patient, visit)

    assert first == second
    assert second == third
    assert first == third


@pytest.mark.parametrize(
    "fixture_name",
    [
        "normal_patient",
        "moderate_patient",
        "chronic_patient",
    ],
)
def test_diversified_generation_does_not_mutate_patient_or_visit(
    request: pytest.FixtureRequest,
    fixture_name: str,
) -> None:
    """SOAP generation must not mutate the patient JSON or visit dictionary."""
    patient = request.getfixturevalue(fixture_name)
    original_patient = deepcopy(patient)
    original_visit = deepcopy(patient["visits"][0])

    _ = generate_soap_note(patient, patient["visits"][0])

    assert patient == original_patient
    assert patient["visits"][0] == original_visit


@pytest.mark.parametrize(
    "fixture_name",
    [
        "normal_patient",
        "moderate_patient",
        "chronic_patient",
    ],
)
def test_template_selection_routes_to_correct_tier(
    request: pytest.FixtureRequest,
    fixture_name: str,
) -> None:
    """Selected templates must come from the patient tier in fact context."""
    patient = request.getfixturevalue(fixture_name)
    visit = patient["visits"][0]
    facts = build_fact_context(patient, visit)
    selected_templates = select_templates_from_fact_context(facts)

    assert facts["tier"] in PATIENT_TIERS

    for section in SOAP_SECTIONS:
        selected_template = selected_templates[section]

        assert isinstance(selected_template, SoapTemplate)
        assert selected_template.section == section
        assert selected_template.tier == facts["tier"]


def test_normal_patient_empty_state_facts_are_preserved(
    normal_patient: dict[str, Any],
) -> None:
    """Normal-tier empty-state text must remain exact and retrieval-safe."""
    visit = normal_patient["visits"][0]
    soap_note = generate_soap_note(normal_patient, visit)
    soap_text = _combined_soap_text(soap_note)

    assert "no chronic conditions" in soap_text
    assert "no chronic diagnosis listed" in soap_text
    assert "no lab results recorded" in soap_text
    assert "no active whitelisted medications recorded" in soap_text
    assert "Linked document references: none." in soap_text
    assert "This is the first recorded visit in the available record." in soap_text
    assert "118/76 mmHg" in soap_text
    assert "72 bpm" in soap_text
    assert "64.5 kg" in soap_text
    assert "BMI 23.4" in soap_text


def test_moderate_patient_structured_facts_are_preserved(
    moderate_patient: dict[str, Any],
) -> None:
    """Moderate-tier SOAP must preserve all structured medical facts exactly."""
    visit = moderate_patient["visits"][0]
    soap_note = generate_soap_note(moderate_patient, visit)
    soap_text = _combined_soap_text(soap_note)

    assert "T2DM, HTN" in soap_text
    assert "142/88 mmHg" in soap_text
    assert "78 bpm" in soap_text
    assert "82.4 kg" in soap_text
    assert "BMI 29.1" in soap_text
    assert "HbA1c 7.8 % (HIGH)" in soap_text
    assert "FBG 148 mg/dL (HIGH)" in soap_text
    assert "Metformin 500 mg twice_daily via oral" in soap_text
    assert "Lisinopril 10 mg once_daily via oral" in soap_text
    assert "DOC-MOD-003-004" in soap_text
    assert "VST-MOD-003-003" in soap_text


def test_chronic_patient_structured_facts_are_preserved(
    chronic_patient: dict[str, Any],
) -> None:
    """Chronic-tier SOAP must preserve multi-condition facts exactly."""
    visit = chronic_patient["visits"][0]
    soap_note = generate_soap_note(chronic_patient, visit)
    soap_text = _combined_soap_text(soap_note)

    assert "T2DM, HTN, Asthma" in soap_text
    assert "T2DM, HTN" in soap_text
    assert "142/88 mmHg" in soap_text
    assert "78 bpm" in soap_text
    assert "82.4 kg" in soap_text
    assert "BMI 29.1" in soap_text
    assert "HbA1c 7.8 % (HIGH)" in soap_text
    assert "FBG 148 mg/dL (HIGH)" in soap_text
    assert "Creatinine 1.1 mg/dL (NORMAL)" in soap_text
    assert "Metformin 500 mg twice_daily via oral" in soap_text
    assert "Lisinopril 10 mg once_daily via oral" in soap_text
    assert "Salbutamol inhaler 100 mcg as_needed via inhaled" in soap_text
    assert "DOC-CHR-002-004" in soap_text
    assert "VST-CHR-002-003" in soap_text


@pytest.mark.parametrize(
    "fixture_name",
    [
        "normal_patient",
        "moderate_patient",
        "chronic_patient",
    ],
)
def test_no_hallucinated_whitelisted_medications_are_introduced(
    request: pytest.FixtureRequest,
    fixture_name: str,
) -> None:
    """SOAP text must not mention whitelisted medications absent from the visit."""
    patient = request.getfixturevalue(fixture_name)
    visit = patient["visits"][0]
    soap_note = generate_soap_note(patient, visit)

    _assert_medication_mentions_are_current(soap_note, visit)


@pytest.mark.parametrize(
    "fixture_name",
    [
        "normal_patient",
        "moderate_patient",
        "chronic_patient",
    ],
)
def test_required_visit_facts_are_preserved_for_each_tier(
    request: pytest.FixtureRequest,
    fixture_name: str,
) -> None:
    """Each tier must preserve vitals, labs, medications, diagnoses, and IDs."""
    patient = request.getfixturevalue(fixture_name)
    visit = patient["visits"][0]
    soap_note = generate_soap_note(patient, visit)

    _assert_required_visit_facts_are_preserved(soap_note, visit)


def test_visit_id_change_produces_deterministic_output_change(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Changing stable visit identifiers changes deterministic output context.

    This confirms the output remains deterministic while reflecting changed
    structured identifiers.
    """
    first_patient = deepcopy(moderate_patient)
    second_patient = deepcopy(moderate_patient)

    first_visit = first_patient["visits"][0]
    second_visit = second_patient["visits"][0]
    second_visit["visit_id"] = "VST-MOD-003-005"
    second_visit["linked_documents"] = ["DOC-MOD-003-005"]
    second_visit["prior_visit_id"] = "VST-MOD-003-004"

    first_output = generate_soap_note(first_patient, first_visit)
    second_output = generate_soap_note(second_patient, second_visit)

    assert first_output != second_output
    assert first_output == generate_soap_note(first_patient, first_visit)
    assert second_output == generate_soap_note(second_patient, second_visit)


def test_template_selection_varies_across_multiple_visits_without_randomness(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Multiple deterministic visit IDs should route to multiple template variants.

    The goal is stable diversified coverage, not probabilistic randomness.
    """
    selected_ids_by_section: dict[str, set[str]] = {
        section: set()
        for section in SOAP_SECTIONS
    }

    for visit_number in range(1, 11):
        patient = deepcopy(moderate_patient)
        patient["patient_id"] = "PAT-MOD-999"

        visit = patient["visits"][0]
        visit["visit_id"] = f"VST-MOD-999-{visit_number:03d}"
        visit["linked_documents"] = [f"DOC-MOD-999-{visit_number:03d}"]
        visit["prior_visit_id"] = (
            f"VST-MOD-999-{visit_number - 1:03d}"
            if visit_number > 1
            else None
        )

        facts = build_fact_context(patient, visit)
        selected_templates = select_templates_from_fact_context(facts)

        for section, template in selected_templates.items():
            selected_ids_by_section[section].add(template.template_id)

    for section in SOAP_SECTIONS:
        assert len(selected_ids_by_section[section]) >= 2


def test_add_soap_notes_to_patient_handles_multiple_visits_deterministically(
    moderate_patient: dict[str, Any],
) -> None:
    """add_soap_notes_to_patient must populate all visits deterministically."""
    patient = deepcopy(moderate_patient)

    second_visit = deepcopy(patient["visits"][0])
    second_visit["visit_id"] = "VST-MOD-003-005"
    second_visit["visit_date"] = "2024-09-15"
    second_visit["linked_documents"] = ["DOC-MOD-003-005"]
    second_visit["prior_visit_id"] = "VST-MOD-003-004"

    patient["visits"].append(second_visit)

    original_patient = deepcopy(patient)
    updated_once = add_soap_notes_to_patient(patient)
    updated_twice = add_soap_notes_to_patient(patient)

    assert patient == original_patient
    assert updated_once == updated_twice
    assert len(updated_once["visits"]) == 2

    for visit in updated_once["visits"]:
        _assert_standard_soap_shape(visit["soap_note"])
        _assert_no_unrendered_placeholders(visit["soap_note"])


def test_generated_soap_preserves_schema_without_extra_sections(
    chronic_patient: dict[str, Any],
) -> None:
    """Generated SOAP note must contain no extra schema keys."""
    visit = chronic_patient["visits"][0]
    soap_note = generate_soap_note(chronic_patient, visit)

    assert set(soap_note.keys()) == {
        "subjective",
        "objective",
        "assessment",
        "plan",
    }
    assert list(soap_note.keys()) == SOAP_SECTION_KEYS


def test_generated_soap_does_not_include_template_ids_or_debug_metadata(
    chronic_patient: dict[str, Any],
) -> None:
    """SOAP text must not leak internal template IDs or selector metadata."""
    visit = chronic_patient["visits"][0]
    soap_note = generate_soap_note(chronic_patient, visit)
    soap_text = _combined_soap_text(soap_note)

    for marker in DEBUG_TEMPLATE_MARKERS:
        assert marker not in soap_text


def test_bp_remains_in_objective_section_text_only(
    moderate_patient: dict[str, Any],
) -> None:
    """
    BP should appear in SOAP objective text and not in other SOAP sections.

    This protects the project rule that BP is a vital sign rendered in text,
    not a lab or metadata field.
    """
    visit = moderate_patient["visits"][0]
    soap_note = generate_soap_note(moderate_patient, visit)

    assert "142/88 mmHg" in soap_note["objective"]
    assert "142/88 mmHg" not in soap_note["subjective"]
    assert "142/88 mmHg" not in soap_note["assessment"]
    assert "142/88 mmHg" not in soap_note["plan"]


def test_diversified_generation_keeps_fact_context_as_source_of_truth(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Rendered SOAP must reflect build_fact_context outputs exactly.
    """
    visit = moderate_patient["visits"][0]
    facts = build_fact_context(moderate_patient, visit)
    soap_note = generate_soap_note(moderate_patient, visit)
    soap_text = _combined_soap_text(soap_note)

    assert facts["condition_text"] in soap_text
    assert facts["diagnosis_text"] in soap_text
    assert facts["bp_text"] in soap_text
    assert facts["lab_text"] in soap_text
    assert facts["medication_text"] in soap_text
    assert facts["linked_documents_text"] in soap_text
    assert facts["prior_text"] in soap_text

    # Semantic v1.1 fields should also be generated from build_fact_context()
    # and made available to templates for stronger RAG retrieval quality.
    assert facts["condition_focus_text"] in soap_text
    assert facts["diagnosis_focus_text"] in soap_text
    assert facts["monitoring_focus_text"] in soap_text
    assert facts["medication_focus_text"] in soap_text


def test_semantic_fact_context_fields_are_present_and_retrieval_safe(
    moderate_patient: dict[str, Any],
) -> None:
    """
    Semantic SOAP v1.1 fields must be present in fact context and rendered SOAP.

    These fields improve RAG retrieval quality while remaining deterministic and
    grounded in structured patient and visit data.
    """
    visit = moderate_patient["visits"][0]
    facts = build_fact_context(moderate_patient, visit)
    soap_note = generate_soap_note(moderate_patient, visit)
    soap_text = _combined_soap_text(soap_note)

    semantic_keys = (
        "condition_focus_text",
        "diagnosis_focus_text",
        "monitoring_focus_text",
        "medication_focus_text",
        "visit_context_text",
        "timeline_context_text",
        "retrieval_focus_text",
    )

    for key in semantic_keys:
        assert key in facts
        assert isinstance(facts[key], str)
        assert facts[key]
        assert "{" not in facts[key]
        assert "}" not in facts[key]

    assert facts["condition_focus_text"] in soap_text
    assert facts["diagnosis_focus_text"] in soap_text
    assert facts["monitoring_focus_text"] in soap_text
    assert facts["medication_focus_text"] in soap_text


def test_tier_values_are_not_modified_by_generation(
    normal_patient: dict[str, Any],
    moderate_patient: dict[str, Any],
    chronic_patient: dict[str, Any],
) -> None:
    """SOAP generation must not modify metadata.tier values."""
    patients = [
        normal_patient,
        moderate_patient,
        chronic_patient,
    ]

    for patient in patients:
        original_tier = patient["metadata"]["tier"]
        visit = patient["visits"][0]

        _ = generate_soap_note(patient, visit)

        assert patient["metadata"]["tier"] == original_tier
        assert build_fact_context(patient, visit)["tier"] == original_tier