"""
tests/test_soap_auditor.py

Tests for deterministic SOAP audit utilities.

Purpose:
    Validate that soap_auditor.py remains focused, deterministic, and safe.

The auditor must:
    - validate SOAP structure,
    - verify required structured facts are preserved,
    - verify BP appears in Objective,
    - detect unsafe clinical interpretation phrases,
    - detect unrendered template placeholders,
    - detect internal template/debug marker leakage,
    - detect allergen mentions near medication/treatment context,
    - avoid mutating patient or visit data.

These tests intentionally use deterministic fixtures and strict assertions.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from soap.soap_auditor import (
    SoapAuditIssue,
    SoapAuditResult,
    SoapAuditSeverity,
    audit_patient_soap,
    audit_soap_note_text,
    audit_visit_soap,
    flatten_issues,
    format_audit_report,
    has_failures,
)
from soap.soap_contract import SOAP_SECTIONS, SoapSection
from soap.soap_generator import generate_soap_note


SOAP_SECTION_KEYS: tuple[SoapSection, ...] = SOAP_SECTIONS


@pytest.fixture
def moderate_patient() -> dict[str, Any]:
    """Return a moderate-tier patient with a valid deterministic SOAP note."""
    patient = {
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

    patient["visits"][0]["soap_note"] = generate_soap_note(
        patient,
        patient["visits"][0],
    )
    return patient


@pytest.fixture
def normal_empty_patient() -> dict[str, Any]:
    """Return a normal-tier patient with valid empty-state SOAP text."""
    patient = {
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

    patient["visits"][0]["soap_note"] = generate_soap_note(
        patient,
        patient["visits"][0],
    )
    return patient


@pytest.fixture
def allergy_patient() -> dict[str, Any]:
    """Return a patient with an allergy registry for allergy-risk tests."""
    patient = {
        "schema_version": "1.0",
        "patient_id": "PAT-CHR-002",
        "demographics": {
            "name": "Synthetic Allergy Patient",
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
                    }
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
                    }
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

    patient["visits"][0]["soap_note"] = generate_soap_note(
        patient,
        patient["visits"][0],
    )
    return patient


def _issue_rule_ids(result: SoapAuditResult) -> set[str]:
    """Return the set of audit rule IDs from a result."""
    return {issue.rule_id for issue in result.issues}


def _assert_has_rule(result: SoapAuditResult, rule_id: str) -> None:
    """Assert that an audit result contains a specific rule ID."""
    assert rule_id in _issue_rule_ids(result)


def _combined_soap_text(soap_note: dict[str, str]) -> str:
    """Join SOAP sections into one text string."""
    return " ".join(soap_note[section] for section in SOAP_SECTION_KEYS)


def test_valid_moderate_patient_soap_passes_audit(
    moderate_patient: dict[str, Any],
) -> None:
    """A valid generated SOAP note should pass with no audit issues."""
    visit = moderate_patient["visits"][0]

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert isinstance(result, SoapAuditResult)
    assert result.patient_id == "PAT-MOD-003"
    assert result.visit_id == "VST-MOD-003-004"
    assert result.passed is True
    assert result.failed is False
    assert result.issues == ()
    assert result.failures == ()
    assert result.warnings == ()


def test_valid_normal_empty_state_soap_passes_audit(
    normal_empty_patient: dict[str, Any],
) -> None:
    """Valid empty-state SOAP text should pass audit."""
    visit = normal_empty_patient["visits"][0]

    result = audit_visit_soap(patient=normal_empty_patient, visit=visit)

    assert result.passed is True
    assert result.issues == ()


def test_audit_patient_soap_returns_result_per_visit(
    moderate_patient: dict[str, Any],
) -> None:
    """audit_patient_soap must return one result per visit."""
    second_visit = deepcopy(moderate_patient["visits"][0])
    second_visit["visit_id"] = "VST-MOD-003-005"
    second_visit["visit_date"] = "2024-09-15"
    second_visit["linked_documents"] = ["DOC-MOD-003-005"]
    second_visit["prior_visit_id"] = "VST-MOD-003-004"

    moderate_patient["visits"].append(second_visit)
    moderate_patient["visits"][1]["soap_note"] = generate_soap_note(
        moderate_patient,
        moderate_patient["visits"][1],
    )

    results = audit_patient_soap(moderate_patient)

    assert len(results) == 2
    assert all(isinstance(result, SoapAuditResult) for result in results)
    assert all(result.passed for result in results)


def test_audit_visit_soap_fails_when_soap_note_is_missing(
    moderate_patient: dict[str, Any],
) -> None:
    """Missing soap_note field must produce a structure failure."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit.pop("soap_note")

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    _assert_has_rule(result, "SOAP-STRUCT-001")


def test_audit_visit_soap_fails_when_soap_note_is_not_mapping(
    moderate_patient: dict[str, Any],
) -> None:
    """Invalid soap_note type must produce a structure failure."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit["soap_note"] = "not a soap dictionary"

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    _assert_has_rule(result, "SOAP-STRUCT-001")


def test_audit_fails_when_required_section_is_missing(
    moderate_patient: dict[str, Any],
) -> None:
    """Missing SOAP section must fail audit."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit["soap_note"].pop("objective")

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    _assert_has_rule(result, "SOAP-STRUCT-002")


def test_audit_fails_when_section_is_not_string(
    moderate_patient: dict[str, Any],
) -> None:
    """Non-string SOAP section values must fail audit."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit["soap_note"]["objective"] = {"text": "invalid"}

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    _assert_has_rule(result, "SOAP-STRUCT-003")


def test_audit_fails_when_section_is_empty(
    moderate_patient: dict[str, Any],
) -> None:
    """Empty SOAP section text must fail audit."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit["soap_note"]["assessment"] = "   "

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    _assert_has_rule(result, "SOAP-STRUCT-004")


def test_audit_warns_for_extra_section_without_failing(
    moderate_patient: dict[str, Any],
) -> None:
    """Unexpected extra SOAP keys should warn, not fail."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit["soap_note"]["extra"] = "Internal text that should not exist."

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.passed is True
    assert len(result.warnings) == 1
    _assert_has_rule(result, "SOAP-STRUCT-005")


def test_audit_fails_when_condition_text_is_missing(
    moderate_patient: dict[str, Any],
) -> None:
    """Missing condition_text must fail fact preservation audit."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit["soap_note"]["subjective"] = visit["soap_note"]["subjective"].replace(
        "T2DM, HTN",
        "documented conditions",
        1,
    )

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    _assert_has_rule(result, "SOAP-FACT-001")


def test_audit_fails_when_diagnosis_text_is_missing(
    moderate_patient: dict[str, Any],
) -> None:
    """Missing diagnosis_text must fail fact preservation audit."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit["soap_note"]["assessment"] = visit["soap_note"]["assessment"].replace(
        "T2DM, HTN",
        "documented diagnoses",
    )

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    _assert_has_rule(result, "SOAP-FACT-001")


def test_audit_fails_when_lab_text_is_changed(
    moderate_patient: dict[str, Any],
) -> None:
    """Changed lab text must fail fact preservation audit."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit["soap_note"]["objective"] = visit["soap_note"]["objective"].replace(
        "HbA1c 7.8 % (HIGH)",
        "HbA1c 7.6 % (HIGH)",
    )

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    _assert_has_rule(result, "SOAP-FACT-001")


def test_audit_fails_when_medication_text_is_changed(
    moderate_patient: dict[str, Any],
) -> None:
    """Changed medication text must fail fact preservation audit."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit["soap_note"]["plan"] = visit["soap_note"]["plan"].replace(
        "Metformin 500 mg twice_daily via oral",
        "Metformin 850 mg twice_daily via oral",
    )

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    _assert_has_rule(result, "SOAP-FACT-001")


def test_audit_fails_when_linked_document_text_is_missing(
    moderate_patient: dict[str, Any],
) -> None:
    """Missing linked document text must fail audit."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit["soap_note"]["objective"] = visit["soap_note"]["objective"].replace(
        "DOC-MOD-003-004",
        "document reference",
    )

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    _assert_has_rule(result, "SOAP-FACT-001")


def test_audit_fails_when_prior_text_is_missing(
    moderate_patient: dict[str, Any],
) -> None:
    """Missing prior visit text must fail audit."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit["soap_note"]["plan"] = visit["soap_note"]["plan"].replace(
        "Prior visit reference is VST-MOD-003-003.",
        "Prior visit reference is documented.",
    )

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    _assert_has_rule(result, "SOAP-FACT-001")


def test_audit_fails_when_bp_is_not_in_objective_section(
    moderate_patient: dict[str, Any],
) -> None:
    """BP must appear in the Objective section specifically."""
    visit = deepcopy(moderate_patient["visits"][0])
    bp_text = "142/88 mmHg"

    visit["soap_note"]["objective"] = visit["soap_note"]["objective"].replace(
        bp_text,
        "blood pressure value documented",
    )
    visit["soap_note"]["subjective"] = (
        visit["soap_note"]["subjective"] + f" BP reference: {bp_text}."
    )

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    _assert_has_rule(result, "SOAP-BP-001")


def test_audit_fails_when_medication_name_is_missing(
    moderate_patient: dict[str, Any],
) -> None:
    """Medication names from visit.medications must appear in SOAP."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit["soap_note"]["plan"] = visit["soap_note"]["plan"].replace(
        "Metformin",
        "Medication A",
    )

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    rule_ids = _issue_rule_ids(result)

    assert "SOAP-FACT-001" in rule_ids
    assert "SOAP-MED-001" in rule_ids


def test_audit_fails_on_unsafe_interpretive_phrase(
    moderate_patient: dict[str, Any],
) -> None:
    """Unsafe clinical interpretation language must fail audit."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit["soap_note"]["assessment"] = (
        visit["soap_note"]["assessment"] + " This is likely related to poor control."
    )

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    _assert_has_rule(result, "SOAP-SAFE-001")


def test_audit_fails_on_unrendered_template_placeholder(
    moderate_patient: dict[str, Any],
) -> None:
    """Leftover template placeholders must fail audit."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit["soap_note"]["objective"] = (
        visit["soap_note"]["objective"] + " Extra placeholder {bp_text}."
    )

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    _assert_has_rule(result, "SOAP-TEMPLATE-001")


def test_audit_fails_on_internal_debug_marker(
    moderate_patient: dict[str, Any],
) -> None:
    """Template IDs and internal selector metadata must not leak into SOAP."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit["soap_note"]["plan"] = visit["soap_note"]["plan"] + " SUBJ-MOD-001"

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    _assert_has_rule(result, "SOAP-DEBUG-001")


def test_audit_fails_when_allergen_appears_near_prescription_context(
    allergy_patient: dict[str, Any],
) -> None:
    """Allergen mention near medication/treatment context must fail audit."""
    visit = deepcopy(allergy_patient["visits"][0])
    visit["soap_note"]["plan"] = (
        visit["soap_note"]["plan"] + " Penicillin was prescribed in the plan."
    )

    result = audit_visit_soap(patient=allergy_patient, visit=visit)

    assert result.failed is True
    _assert_has_rule(result, "SOAP-ALLERGY-001")


def test_audit_allows_allergen_mention_without_prescription_context(
    allergy_patient: dict[str, Any],
) -> None:
    """
    Non-prescription allergy mention should be allowed if all other facts remain valid.

    The auditor is conservative: it flags allergy mentions only near medication,
    treatment, or plan context.
    """
    visit = deepcopy(allergy_patient["visits"][0])
    visit["soap_note"]["subjective"] = (
        visit["soap_note"]["subjective"]
        + " Documented allergy history includes Penicillin allergy."
    )

    result = audit_visit_soap(patient=allergy_patient, visit=visit)

    assert result.passed is True
    assert result.issues == ()


def test_audit_soap_note_text_audits_candidate_note_without_mutating_visit(
    moderate_patient: dict[str, Any],
) -> None:
    """audit_soap_note_text should audit supplied text without mutating the visit."""
    visit = moderate_patient["visits"][0]
    original_visit = deepcopy(visit)
    soap_note = deepcopy(visit["soap_note"])

    result = audit_soap_note_text(
        soap_note=soap_note,
        patient=moderate_patient,
        visit=visit,
    )

    assert result.passed is True
    assert visit == original_visit


def test_audit_visit_soap_does_not_mutate_patient_or_visit(
    moderate_patient: dict[str, Any],
) -> None:
    """Auditing must not mutate patient or visit dictionaries."""
    original_patient = deepcopy(moderate_patient)
    original_visit = deepcopy(moderate_patient["visits"][0])

    _ = audit_visit_soap(
        patient=moderate_patient,
        visit=moderate_patient["visits"][0],
    )

    assert moderate_patient == original_patient
    assert moderate_patient["visits"][0] == original_visit


def test_flatten_issues_returns_all_issues(
    moderate_patient: dict[str, Any],
) -> None:
    """flatten_issues must combine issues from multiple audit results."""
    good_result = audit_visit_soap(
        patient=moderate_patient,
        visit=moderate_patient["visits"][0],
    )

    bad_visit = deepcopy(moderate_patient["visits"][0])
    bad_visit["soap_note"]["assessment"] = ""

    bad_result = audit_visit_soap(
        patient=moderate_patient,
        visit=bad_visit,
    )

    issues = flatten_issues([good_result, bad_result])

    assert good_result.issues == ()
    assert len(issues) == len(bad_result.issues)
    assert all(isinstance(issue, SoapAuditIssue) for issue in issues)


def test_has_failures_returns_false_for_passing_results(
    moderate_patient: dict[str, Any],
) -> None:
    """has_failures must return False when all results pass."""
    result = audit_visit_soap(
        patient=moderate_patient,
        visit=moderate_patient["visits"][0],
    )

    assert has_failures([result]) is False


def test_has_failures_returns_true_for_failed_results(
    moderate_patient: dict[str, Any],
) -> None:
    """has_failures must return True when any result fails."""
    bad_visit = deepcopy(moderate_patient["visits"][0])
    bad_visit["soap_note"]["objective"] = ""

    result = audit_visit_soap(patient=moderate_patient, visit=bad_visit)

    assert has_failures([result]) is True


def test_format_audit_report_for_passing_result(
    moderate_patient: dict[str, Any],
) -> None:
    """Passing audit report must include counts and PASS status."""
    result = audit_visit_soap(
        patient=moderate_patient,
        visit=moderate_patient["visits"][0],
    )

    report = format_audit_report([result])

    assert "=== SOAP AUDIT REPORT ===" in report
    assert "Visits checked: 1" in report
    assert "FAIL issues:   0" in report
    assert "WARN issues:   0" in report
    assert "Status: PASS — no SOAP audit issues detected." in report


def test_format_audit_report_for_failed_result(
    moderate_patient: dict[str, Any],
) -> None:
    """Failed audit report must include issue details."""
    bad_visit = deepcopy(moderate_patient["visits"][0])
    bad_visit["soap_note"]["plan"] = ""

    result = audit_visit_soap(patient=moderate_patient, visit=bad_visit)
    report = format_audit_report([result])

    assert "=== SOAP AUDIT REPORT ===" in report
    assert "FAIL issues:   " in report
    assert "[FAIL]" in report
    assert "PAT-MOD-003" in report
    assert "VST-MOD-003-004" in report
    assert "SOAP-STRUCT-004" in report


def test_audit_result_properties_split_failures_and_warnings(
    moderate_patient: dict[str, Any],
) -> None:
    """SoapAuditResult properties must separate FAIL and WARN issues correctly."""
    visit = deepcopy(moderate_patient["visits"][0])
    visit["soap_note"]["extra"] = "Unexpected extra section."
    visit["soap_note"]["assessment"] = ""

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.failed is True
    assert result.passed is False
    assert len(result.failures) >= 1
    assert len(result.warnings) >= 1
    assert all(issue.severity == SoapAuditSeverity.FAIL for issue in result.failures)
    assert all(issue.severity == SoapAuditSeverity.WARN for issue in result.warnings)


def test_soap_section_keys_are_locked() -> None:
    """SOAP section keys must remain exactly four canonical sections."""
    assert SOAP_SECTION_KEYS == (
        "subjective",
        "objective",
        "assessment",
        "plan",
    )


def test_auditor_preserves_generated_fact_values_in_valid_note(
    moderate_patient: dict[str, Any],
) -> None:
    """Valid audited SOAP should contain all critical structured facts."""
    visit = moderate_patient["visits"][0]
    soap_text = _combined_soap_text(visit["soap_note"])

    assert "T2DM, HTN" in soap_text
    assert "142/88 mmHg" in soap_text
    assert "HbA1c 7.8 % (HIGH)" in soap_text
    assert "FBG 148 mg/dL (HIGH)" in soap_text
    assert "Metformin 500 mg twice_daily via oral" in soap_text
    assert "Lisinopril 10 mg once_daily via oral" in soap_text
    assert "DOC-MOD-003-004" in soap_text
    assert "Prior visit reference is VST-MOD-003-003." in soap_text

    result = audit_visit_soap(patient=moderate_patient, visit=visit)

    assert result.passed is True