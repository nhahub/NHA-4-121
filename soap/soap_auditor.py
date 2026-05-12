"""
soap/soap_auditor.py

Regex/string-based SOAP audit.

This is not a clinical validator. It only checks whether generated SOAP text
appears to contradict structured synthetic data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config.constants import MEDICATION_NAMES


@dataclass(frozen=True)
class SoapAuditIssue:
    severity: str
    patient_id: str
    visit_id: str
    message: str


PRESCRIPTION_VERBS = (
    "start",
    "started",
    "prescribe",
    "prescribed",
    "administer",
    "administered",
    "continue",
    "continued",
)


def audit_patient_soap(patient: dict[str, Any]) -> list[SoapAuditIssue]:
    """Audit all SOAP notes for a patient."""
    issues: list[SoapAuditIssue] = []

    for visit in patient.get("visits", []):
        issues.extend(audit_visit_soap(patient, visit))

    return issues


def audit_visit_soap(
    patient: dict[str, Any],
    visit: dict[str, Any],
) -> list[SoapAuditIssue]:
    """Audit one visit SOAP note."""
    issues: list[SoapAuditIssue] = []
    patient_id = patient.get("patient_id", "<missing-patient-id>")
    visit_id = visit.get("visit_id", "<missing-visit-id>")
    soap_text = _soap_as_text(visit.get("soap_note", {}))

    if not soap_text.strip():
        issues.append(
            SoapAuditIssue(
                severity="FAIL",
                patient_id=patient_id,
                visit_id=visit_id,
                message="SOAP note is empty.",
            )
        )
        return issues

    current_med_names = {
        med.get("medication_name")
        for med in visit.get("medications", [])
    }

    for med_name in MEDICATION_NAMES:
        if med_name.lower() in soap_text.lower() and med_name not in current_med_names:
            issues.append(
                SoapAuditIssue(
                    severity="FAIL",
                    patient_id=patient_id,
                    visit_id=visit_id,
                    message=f"SOAP mentions medication '{med_name}' not present in visit medications.",
                )
            )

    for lab in visit.get("labs", []):
        expected_value = str(lab.get("value"))
        expected_type = str(lab.get("lab_type"))

        if expected_type in soap_text and expected_value not in soap_text:
            issues.append(
                SoapAuditIssue(
                    severity="WARN",
                    patient_id=patient_id,
                    visit_id=visit_id,
                    message=(
                        f"SOAP mentions lab type '{expected_type}' but not "
                        f"its structured value '{expected_value}'."
                    ),
                )
            )

    vitals = visit.get("vitals", {})
    bp_text = f"{vitals.get('bp_systolic')}/{vitals.get('bp_diastolic')}"
    if bp_text not in soap_text:
        issues.append(
            SoapAuditIssue(
                severity="WARN",
                patient_id=patient_id,
                visit_id=visit_id,
                message=f"SOAP does not mention structured BP value {bp_text}.",
            )
        )

    for allergy in patient.get("allergy_registry", []):
        allergen = str(allergy.get("allergen", "")).lower().strip()
        if not allergen:
            continue

        lowered = soap_text.lower()
        if allergen in lowered and _appears_as_prescription(lowered, allergen):
            issues.append(
                SoapAuditIssue(
                    severity="FAIL",
                    patient_id=patient_id,
                    visit_id=visit_id,
                    message=f"SOAP may describe allergen '{allergen}' as a prescription.",
                )
            )

    return issues


def _soap_as_text(soap_note: dict[str, Any]) -> str:
    return " ".join(str(soap_note.get(section, "")) for section in (
        "subjective",
        "objective",
        "assessment",
        "plan",
    ))


def _appears_as_prescription(text: str, allergen: str) -> bool:
    for verb in PRESCRIPTION_VERBS:
        phrase = f"{verb} {allergen}"
        if phrase in text:
            return True

    return False