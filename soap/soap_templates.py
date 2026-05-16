"""
soap/soap_templates.py

Deterministic SOAP template registry.

Purpose:
    Store approved deterministic SOAP templates for future diversified SOAP
    generation.

Safety contract:
    - Templates contain wording only.
    - Templates do not calculate medical values.
    - Templates do not infer diagnoses.
    - Templates do not select medications.
    - Templates do not select labs.
    - Templates do not modify structured facts.
    - Templates do not contain real patient data.
    - Templates do not contain hardcoded clinical values.
    - Templates do not call LLMs.
    - Templates do not use randomization.

Important:
    The medical truth must continue to come only from structured JSON through
    build_fact_context() in soap_renderers.py.

Architecture:
    soap_contract.py   -> owns shared SOAP sections/types/template dataclass
    soap_safety.py     -> owns shared SOAP safety phrase constants
    soap_renderers.py  -> owns fact extraction and exact formatting
    soap_templates.py  -> owns template registry only
    soap_selector.py   -> owns deterministic template selection
    soap_generator.py  -> owns final SOAP assembly
    soap_auditor.py    -> owns safety checks

Template grouping:
    section -> tier -> templates

Supported sections:
    - subjective
    - objective
    - assessment
    - plan

Supported tiers:
    - normal
    - moderate
    - chronic

Initial template count:
    - normal:   3 templates per SOAP section
    - moderate: 4 templates per SOAP section
    - chronic:  5 templates per SOAP section

Total:
    48 templates.
"""

from __future__ import annotations

from typing import Final, Mapping

from soap.soap_contract import PatientTier, SoapSection, SoapTemplate


TEMPLATE_VERSION: Final[str] = "soap-templates-v1.0"


SOAP_TEMPLATES: Final[Mapping[SoapSection, Mapping[PatientTier, tuple[SoapTemplate, ...]]]] = {
    "subjective": {
        "normal": (
            SoapTemplate(
                template_id="SUBJ-NRM-001",
                section="subjective",
                tier="normal",
                text=(
                    "The synthetic record documents a {age}-year-old {sex} patient "
                    "attending a {visit_type} visit. The structured condition list records "
                    "{condition_text}. The note is generated only from stored synthetic facts and does "
                    "not add diagnosis, prediction, or clinical judgment beyond the record."
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-NRM-002",
                section="subjective",
                tier="normal",
                text=(
                    "This {visit_type} encounter describes a {age}-year-old {sex} patient. "
                    "The structured condition list records {condition_text}. The narrative is limited "
                    "to stored synthetic facts and does not add diagnosis, prediction, or clinical judgment."
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-NRM-003",
                section="subjective",
                tier="normal",
                text=(
                    "For this {visit_type} visit, the synthetic chart records a {age}-year-old "
                    "{sex} patient. Documented conditions in the structured list are {condition_text}. "
                    "No diagnosis, prediction, or clinical judgment is added beyond the stored record."
                ),
            ),
        ),
        "moderate": (
            SoapTemplate(
                template_id="SUBJ-MOD-001",
                section="subjective",
                tier="moderate",
                text=(
                    "The synthetic record documents a {age}-year-old {sex} patient "
                    "attending a {visit_type} visit. The structured condition list records "
                    "{condition_text}. The note is generated only from stored synthetic facts and does "
                    "not add diagnosis, prediction, or clinical judgment beyond the record."
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-MOD-002",
                section="subjective",
                tier="moderate",
                text=(
                    "A {age}-year-old {sex} patient is documented in the structured record for a "
                    "{visit_type} visit. The condition list records {condition_text}. This section "
                    "uses only stored synthetic facts and adds no diagnosis, prediction, or clinical judgment."
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-MOD-003",
                section="subjective",
                tier="moderate",
                text=(
                    "This {visit_type} record describes a {age}-year-old {sex} patient with "
                    "structured conditions listed as {condition_text}. The wording remains grounded "
                    "in the stored synthetic JSON facts without adding clinical interpretation."
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-MOD-004",
                section="subjective",
                tier="moderate",
                text=(
                    "The encounter entry records a {age}-year-old {sex} patient attending a "
                    "{visit_type} visit. The structured condition list includes {condition_text}. "
                    "No unstated diagnosis, prediction, or medical judgment is introduced."
                ),
            ),
        ),
        "chronic": (
            SoapTemplate(
                template_id="SUBJ-CHR-001",
                section="subjective",
                tier="chronic",
                text=(
                    "The synthetic record documents a {age}-year-old {sex} patient "
                    "attending a {visit_type} visit. The structured condition list records "
                    "{condition_text}. The note is generated only from stored synthetic facts and does "
                    "not add diagnosis, prediction, or clinical judgment beyond the record."
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-CHR-002",
                section="subjective",
                tier="chronic",
                text=(
                    "This {visit_type} visit is recorded for a {age}-year-old {sex} patient. "
                    "The structured condition list records {condition_text}. The narrative reflects "
                    "only documented synthetic facts and does not introduce additional clinical judgment."
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-CHR-003",
                section="subjective",
                tier="chronic",
                text=(
                    "The structured chart documents a {age}-year-old {sex} patient seen for a "
                    "{visit_type} encounter. Listed conditions are {condition_text}. This SOAP text "
                    "does not add diagnosis, prediction, or interpretation beyond the record."
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-CHR-004",
                section="subjective",
                tier="chronic",
                text=(
                    "For this {visit_type} entry, the stored synthetic data identifies a "
                    "{age}-year-old {sex} patient. The structured condition list records "
                    "{condition_text}. The section remains limited to documented facts."
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-CHR-005",
                section="subjective",
                tier="chronic",
                text=(
                    "This longitudinal record entry describes a {age}-year-old {sex} patient at a "
                    "{visit_type} visit. The condition list in the structured JSON records "
                    "{condition_text}. No additional diagnosis, prediction, or clinical judgment is added."
                ),
            ),
        ),
    },
    "objective": {
        "normal": (
            SoapTemplate(
                template_id="OBJ-NRM-001",
                section="objective",
                tier="normal",
                text=(
                    "Objective structured data records blood pressure "
                    "{bp_systolic}/{bp_diastolic} mmHg, heart rate "
                    "{heart_rate} bpm, weight {weight_kg} kg, and BMI "
                    "{bmi}. Laboratory data for this visit: {lab_text}. "
                    "Linked document references: {linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-NRM-002",
                section="objective",
                tier="normal",
                text=(
                    "Recorded objective findings include blood pressure {bp_systolic}/{bp_diastolic} mmHg, "
                    "heart rate {heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                    "Laboratory data for this visit: {lab_text}. Linked document references: "
                    "{linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-NRM-003",
                section="objective",
                tier="normal",
                text=(
                    "Visit vitals show blood pressure {bp_systolic}/{bp_diastolic} mmHg, "
                    "heart rate {heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                    "Laboratory data for this visit: {lab_text}. Linked document references: "
                    "{linked_documents_text}."
                ),
            ),
        ),
        "moderate": (
            SoapTemplate(
                template_id="OBJ-MOD-001",
                section="objective",
                tier="moderate",
                text=(
                    "Objective structured data records blood pressure "
                    "{bp_systolic}/{bp_diastolic} mmHg, heart rate "
                    "{heart_rate} bpm, weight {weight_kg} kg, and BMI "
                    "{bmi}. Laboratory data for this visit: {lab_text}. "
                    "Linked document references: {linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-MOD-002",
                section="objective",
                tier="moderate",
                text=(
                    "Objective measurements for this visit include blood pressure "
                    "{bp_systolic}/{bp_diastolic} mmHg, heart rate {heart_rate} bpm, "
                    "weight {weight_kg} kg, and BMI {bmi}. Laboratory data for this visit: "
                    "{lab_text}. Linked document references: {linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-MOD-003",
                section="objective",
                tier="moderate",
                text=(
                    "Structured vital signs document blood pressure {bp_systolic}/{bp_diastolic} mmHg, "
                    "heart rate {heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                    "Laboratory data for this visit: {lab_text}. Linked document references: "
                    "{linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-MOD-004",
                section="objective",
                tier="moderate",
                text=(
                    "The objective section records blood pressure {bp_systolic}/{bp_diastolic} mmHg, "
                    "heart rate {heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                    "Laboratory data for this visit: {lab_text}. Linked document references: "
                    "{linked_documents_text}."
                ),
            ),
        ),
        "chronic": (
            SoapTemplate(
                template_id="OBJ-CHR-001",
                section="objective",
                tier="chronic",
                text=(
                    "Objective structured data records blood pressure "
                    "{bp_systolic}/{bp_diastolic} mmHg, heart rate "
                    "{heart_rate} bpm, weight {weight_kg} kg, and BMI "
                    "{bmi}. Laboratory data for this visit: {lab_text}. "
                    "Linked document references: {linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-CHR-002",
                section="objective",
                tier="chronic",
                text=(
                    "Objective data from this visit include blood pressure "
                    "{bp_systolic}/{bp_diastolic} mmHg, heart rate {heart_rate} bpm, "
                    "weight {weight_kg} kg, and BMI {bmi}. Laboratory data for this visit: "
                    "{lab_text}. Linked document references: {linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-CHR-003",
                section="objective",
                tier="chronic",
                text=(
                    "The structured visit record lists blood pressure {bp_systolic}/{bp_diastolic} mmHg, "
                    "heart rate {heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                    "Laboratory data for this visit: {lab_text}. Linked document references: "
                    "{linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-CHR-004",
                section="objective",
                tier="chronic",
                text=(
                    "Recorded vital signs include blood pressure {bp_systolic}/{bp_diastolic} mmHg, "
                    "heart rate {heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                    "Laboratory data for this visit: {lab_text}. Linked document references: "
                    "{linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-CHR-005",
                section="objective",
                tier="chronic",
                text=(
                    "For this encounter, objective structured values include blood pressure "
                    "{bp_systolic}/{bp_diastolic} mmHg, heart rate {heart_rate} bpm, "
                    "weight {weight_kg} kg, and BMI {bmi}. Laboratory data for this visit: "
                    "{lab_text}. Linked document references: {linked_documents_text}."
                ),
            ),
        ),
    },
    "assessment": {
        "normal": (
            SoapTemplate(
                template_id="ASM-NRM-001",
                section="assessment",
                tier="normal",
                text=(
                    "The assessment section summarizes only documented diagnoses for this visit: "
                    "{diagnosis_text}. "
                    "The visit remains grounded in the structured JSON record and does not infer "
                    "unstated conditions."
                ),
            ),
            SoapTemplate(
                template_id="ASM-NRM-002",
                section="assessment",
                tier="normal",
                text=(
                    "Assessment is limited to documented diagnoses for this visit: "
                    "{diagnosis_text}. The visit remains grounded in the structured JSON record "
                    "and does not infer unstated conditions."
                ),
            ),
            SoapTemplate(
                template_id="ASM-NRM-003",
                section="assessment",
                tier="normal",
                text=(
                    "The documented diagnosis list for this visit is summarized as: "
                    "{diagnosis_text}. The section remains grounded in the structured JSON record "
                    "and does not infer unstated conditions."
                ),
            ),
        ),
        "moderate": (
            SoapTemplate(
                template_id="ASM-MOD-001",
                section="assessment",
                tier="moderate",
                text=(
                    "The assessment section summarizes only documented diagnoses for this visit: "
                    "{diagnosis_text}. "
                    "The visit remains grounded in the structured JSON record and does not infer "
                    "unstated conditions."
                ),
            ),
            SoapTemplate(
                template_id="ASM-MOD-002",
                section="assessment",
                tier="moderate",
                text=(
                    "The assessment is restricted to the recorded visit diagnoses: "
                    "{diagnosis_text}. The visit remains grounded in the structured JSON record "
                    "and does not infer unstated conditions."
                ),
            ),
            SoapTemplate(
                template_id="ASM-MOD-003",
                section="assessment",
                tier="moderate",
                text=(
                    "Documented diagnoses for this encounter are summarized as: "
                    "{diagnosis_text}. This section uses only the structured JSON record and "
                    "does not infer unstated conditions."
                ),
            ),
            SoapTemplate(
                template_id="ASM-MOD-004",
                section="assessment",
                tier="moderate",
                text=(
                    "The structured visit diagnosis list records: {diagnosis_text}. "
                    "The assessment text remains grounded in the structured JSON record and "
                    "does not infer unstated conditions."
                ),
            ),
        ),
        "chronic": (
            SoapTemplate(
                template_id="ASM-CHR-001",
                section="assessment",
                tier="chronic",
                text=(
                    "The assessment section summarizes only documented diagnoses for this visit: "
                    "{diagnosis_text}. "
                    "The visit remains grounded in the structured JSON record and does not infer "
                    "unstated conditions."
                ),
            ),
            SoapTemplate(
                template_id="ASM-CHR-002",
                section="assessment",
                tier="chronic",
                text=(
                    "Assessment content is limited to documented diagnoses for this visit: "
                    "{diagnosis_text}. The visit remains grounded in the structured JSON record "
                    "and does not infer unstated conditions."
                ),
            ),
            SoapTemplate(
                template_id="ASM-CHR-003",
                section="assessment",
                tier="chronic",
                text=(
                    "For this longitudinal record entry, the documented visit diagnoses are: "
                    "{diagnosis_text}. The assessment does not infer unstated conditions beyond "
                    "the structured JSON record."
                ),
            ),
            SoapTemplate(
                template_id="ASM-CHR-004",
                section="assessment",
                tier="chronic",
                text=(
                    "The visit diagnosis summary includes only the structured diagnoses: "
                    "{diagnosis_text}. The section remains grounded in the JSON record and does "
                    "not add unstated conditions."
                ),
            ),
            SoapTemplate(
                template_id="ASM-CHR-005",
                section="assessment",
                tier="chronic",
                text=(
                    "The recorded diagnoses for this visit are summarized as: {diagnosis_text}. "
                    "This assessment is descriptive only and does not infer conditions outside "
                    "the structured record."
                ),
            ),
        ),
    },
    "plan": {
        "normal": (
            SoapTemplate(
                template_id="PLAN-NRM-001",
                section="plan",
                tier="normal",
                text=(
                    "The documented plan records the whitelisted medication list exactly as stored: "
                    "{medication_text}. {prior_text} Follow-up context should be interpreted only "
                    "as part of this synthetic academic dataset, not as medical advice."
                ),
            ),
            SoapTemplate(
                template_id="PLAN-NRM-002",
                section="plan",
                tier="normal",
                text=(
                    "The plan section lists the stored whitelisted medications exactly as recorded: "
                    "{medication_text}. {prior_text} Follow-up context is included only as part "
                    "of this synthetic academic dataset, not as medical advice."
                ),
            ),
            SoapTemplate(
                template_id="PLAN-NRM-003",
                section="plan",
                tier="normal",
                text=(
                    "The structured plan records the whitelisted medication list exactly as stored: "
                    "{medication_text}. {prior_text} This synthetic dataset context should not "
                    "be interpreted as medical advice."
                ),
            ),
        ),
        "moderate": (
            SoapTemplate(
                template_id="PLAN-MOD-001",
                section="plan",
                tier="moderate",
                text=(
                    "The documented plan records the whitelisted medication list exactly as stored: "
                    "{medication_text}. {prior_text} Follow-up context should be interpreted only "
                    "as part of this synthetic academic dataset, not as medical advice."
                ),
            ),
            SoapTemplate(
                template_id="PLAN-MOD-002",
                section="plan",
                tier="moderate",
                text=(
                    "The plan records stored whitelisted medications without modification: "
                    "{medication_text}. {prior_text} Follow-up context should be interpreted only "
                    "as part of this synthetic academic dataset, not as medical advice."
                ),
            ),
            SoapTemplate(
                template_id="PLAN-MOD-003",
                section="plan",
                tier="moderate",
                text=(
                    "Medication data in the plan is listed exactly as stored in the structured record: "
                    "{medication_text}. {prior_text} This content belongs only to the synthetic "
                    "academic dataset and is not medical advice."
                ),
            ),
            SoapTemplate(
                template_id="PLAN-MOD-004",
                section="plan",
                tier="moderate",
                text=(
                    "The documented plan preserves the whitelisted medication list as recorded: "
                    "{medication_text}. {prior_text} Follow-up context remains part of the "
                    "synthetic academic dataset and should not be interpreted as medical advice."
                ),
            ),
        ),
        "chronic": (
            SoapTemplate(
                template_id="PLAN-CHR-001",
                section="plan",
                tier="chronic",
                text=(
                    "The documented plan records the whitelisted medication list exactly as stored: "
                    "{medication_text}. {prior_text} Follow-up context should be interpreted only "
                    "as part of this synthetic academic dataset, not as medical advice."
                ),
            ),
            SoapTemplate(
                template_id="PLAN-CHR-002",
                section="plan",
                tier="chronic",
                text=(
                    "The plan section preserves the stored whitelisted medication list exactly: "
                    "{medication_text}. {prior_text} Follow-up context should be interpreted only "
                    "as part of this synthetic academic dataset, not as medical advice."
                ),
            ),
            SoapTemplate(
                template_id="PLAN-CHR-003",
                section="plan",
                tier="chronic",
                text=(
                    "For this record entry, the documented plan lists medications exactly as stored: "
                    "{medication_text}. {prior_text} This wording is part of a synthetic academic "
                    "dataset and is not medical advice."
                ),
            ),
            SoapTemplate(
                template_id="PLAN-CHR-004",
                section="plan",
                tier="chronic",
                text=(
                    "The structured plan data records the whitelisted medication list without change: "
                    "{medication_text}. {prior_text} Follow-up context is included only for the "
                    "synthetic academic dataset and should not be used as medical advice."
                ),
            ),
            SoapTemplate(
                template_id="PLAN-CHR-005",
                section="plan",
                tier="chronic",
                text=(
                    "The documented plan keeps the medication list exactly as stored in the JSON record: "
                    "{medication_text}. {prior_text} Any follow-up context is limited to this "
                    "synthetic academic dataset and is not medical advice."
                ),
            ),
        ),
    },
}



TOTAL_TEMPLATE_COUNT: Final[int] = sum(
    len(tier_templates)
    for section_templates in SOAP_TEMPLATES.values()
    for tier_templates in section_templates.values()
)


__all__ = [
    "SOAP_TEMPLATES",
    "TEMPLATE_VERSION",
    "TOTAL_TEMPLATE_COUNT",
]
