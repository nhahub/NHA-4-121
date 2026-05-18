"""
soap/soap_templates.py

Deterministic condition-aware SOAP template registry.

Purpose:
    Store approved deterministic SOAP templates for diversified, RAG-oriented
    SOAP generation.

This version uses semantic placeholders produced by soap_semantics.py through
build_fact_context(). The goal is to improve semantic diversity and retrieval
quality while preserving deterministic safety.

Safety contract:
    - Templates contain wording only.
    - Templates do not calculate medical values.
    - Templates do not infer diagnoses.
    - Templates do not select medications.
    - Templates do not select labs.
    - Templates do not modify structured facts.
    - Templates do not contain real patient data.
    - Templates do not contain hardcoded clinical values.
    - Templates do not contain hardcoded condition names, lab names, medication
      names, patient IDs, visit IDs, document IDs, or BP values.
    - Templates do not call LLMs.
    - Templates do not use randomization.

Important:
    The medical truth must continue to come only from structured patient JSON
    through build_fact_context() in soap_renderers.py.

Architecture:
    soap_contract.py   -> owns shared SOAP sections/types/template dataclass
    soap_safety.py     -> owns shared SOAP safety phrase constants
    soap_semantics.py  -> owns condition-aware semantic phrase construction
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

Template count:
    - normal:   3 templates per SOAP section
    - moderate: 4 templates per SOAP section
    - chronic:  5 templates per SOAP section

Total:
    48 templates.
"""

from __future__ import annotations

from typing import Final, Mapping

from soap.soap_contract import PatientTier, SoapSection, SoapTemplate


TEMPLATE_VERSION: Final[str] = "soap-templates-v1.1"


SOAP_TEMPLATES: Final[Mapping[SoapSection, Mapping[PatientTier, tuple[SoapTemplate, ...]]]] = {
    "subjective": {
        "normal": (
            SoapTemplate(
                template_id="SUBJ-NRM-001",
                section="subjective",
                tier="normal",
                text=(
                    "The chart documents a {age}-year-old {sex} patient seen for a "
                    "{visit_type} visit. The condition list records {condition_text}. "
                    "{condition_focus_text} {visit_context_text}"
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-NRM-002",
                section="subjective",
                tier="normal",
                text=(
                    "For this {visit_type} encounter, the record describes a "
                    "{age}-year-old {sex} patient. Documented conditions are listed as "
                    "{condition_text}. {condition_focus_text} {timeline_context_text}"
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-NRM-003",
                section="subjective",
                tier="normal",
                text=(
                    "This visit note concerns a {age}-year-old {sex} patient presenting "
                    "for a {visit_type} encounter. The recorded condition list includes "
                    "{condition_text}. {visit_context_text} {condition_focus_text}"
                ),
            ),
        ),
        "moderate": (
            SoapTemplate(
                template_id="SUBJ-MOD-001",
                section="subjective",
                tier="moderate",
                text=(
                    "The chart documents a {age}-year-old {sex} patient seen for a "
                    "{visit_type} visit. The condition list records {condition_text}. "
                    "{condition_focus_text} {visit_context_text}"
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-MOD-002",
                section="subjective",
                tier="moderate",
                text=(
                    "A {age}-year-old {sex} patient is recorded for a {visit_type} visit. "
                    "The documented condition list includes {condition_text}. "
                    "{condition_focus_text} {timeline_context_text}"
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-MOD-003",
                section="subjective",
                tier="moderate",
                text=(
                    "This {visit_type} note describes a {age}-year-old {sex} patient. "
                    "Conditions recorded in the chart are {condition_text}. "
                    "{visit_context_text} {condition_focus_text}"
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-MOD-004",
                section="subjective",
                tier="moderate",
                text=(
                    "During this {visit_type} encounter, the record identifies a "
                    "{age}-year-old {sex} patient. The condition list includes "
                    "{condition_text}. {condition_focus_text} {retrieval_focus_text}"
                ),
            ),
        ),
        "chronic": (
            SoapTemplate(
                template_id="SUBJ-CHR-001",
                section="subjective",
                tier="chronic",
                text=(
                    "The chart documents a {age}-year-old {sex} patient seen for a "
                    "{visit_type} visit. The condition list records {condition_text}. "
                    "{condition_focus_text} {visit_context_text}"
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-CHR-002",
                section="subjective",
                tier="chronic",
                text=(
                    "This {visit_type} encounter is recorded for a {age}-year-old {sex} "
                    "patient. The charted condition list records {condition_text}. "
                    "{condition_focus_text} {timeline_context_text}"
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-CHR-003",
                section="subjective",
                tier="chronic",
                text=(
                    "The longitudinal chart includes a {visit_type} visit for a "
                    "{age}-year-old {sex} patient. Documented conditions are "
                    "{condition_text}. {visit_context_text} {condition_focus_text}"
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-CHR-004",
                section="subjective",
                tier="chronic",
                text=(
                    "For this {visit_type} entry, the record identifies a {age}-year-old "
                    "{sex} patient. The condition list records {condition_text}. "
                    "{condition_focus_text} {retrieval_focus_text}"
                ),
            ),
            SoapTemplate(
                template_id="SUBJ-CHR-005",
                section="subjective",
                tier="chronic",
                text=(
                    "This follow-up record section describes a {age}-year-old {sex} "
                    "patient at a {visit_type} visit. The documented condition list "
                    "includes {condition_text}. {timeline_context_text} "
                    "{condition_focus_text}"
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
                    "Objective findings record blood pressure {bp_systolic}/{bp_diastolic} mmHg, "
                    "heart rate {heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                    "Laboratory results for this visit: {lab_text}. "
                    "{monitoring_focus_text} Linked document references: "
                    "{linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-NRM-002",
                section="objective",
                tier="normal",
                text=(
                    "Recorded measurements include blood pressure {bp_systolic}/{bp_diastolic} mmHg, "
                    "heart rate {heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                    "The lab section records: {lab_text}. {monitoring_focus_text} "
                    "Linked document references: {linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-NRM-003",
                section="objective",
                tier="normal",
                text=(
                    "Vitals for the encounter show blood pressure {bp_systolic}/{bp_diastolic} mmHg, "
                    "heart rate {heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                    "Available laboratory results: {lab_text}. {monitoring_focus_text} "
                    "Linked document references: {linked_documents_text}."
                ),
            ),
        ),
        "moderate": (
            SoapTemplate(
                template_id="OBJ-MOD-001",
                section="objective",
                tier="moderate",
                text=(
                    "Objective findings record blood pressure {bp_systolic}/{bp_diastolic} mmHg, "
                    "heart rate {heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                    "Laboratory results for this visit: {lab_text}. "
                    "{monitoring_focus_text} Linked document references: "
                    "{linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-MOD-002",
                section="objective",
                tier="moderate",
                text=(
                    "The visit measurements include blood pressure {bp_systolic}/{bp_diastolic} mmHg, "
                    "heart rate {heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                    "Laboratory entries are recorded as: {lab_text}. "
                    "{monitoring_focus_text} Linked document references: "
                    "{linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-MOD-003",
                section="objective",
                tier="moderate",
                text=(
                    "Structured objective data lists blood pressure {bp_systolic}/{bp_diastolic} mmHg, "
                    "heart rate {heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                    "Lab results documented for the visit: {lab_text}. "
                    "{monitoring_focus_text} Linked document references: {linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-MOD-004",
                section="objective",
                tier="moderate",
                text=(
                    "Objective data from the encounter records blood pressure "
                    "{bp_systolic}/{bp_diastolic} mmHg, heart rate {heart_rate} bpm, "
                    "weight {weight_kg} kg, and BMI {bmi}. Laboratory results: "
                    "{lab_text}. {monitoring_focus_text} Linked document references: "
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
                    "Objective findings record blood pressure {bp_systolic}/{bp_diastolic} mmHg, "
                    "heart rate {heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                    "Laboratory results for this visit: {lab_text}. "
                    "{monitoring_focus_text} Linked document references: "
                    "{linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-CHR-002",
                section="objective",
                tier="chronic",
                text=(
                    "For this encounter, recorded objective data includes blood pressure "
                    "{bp_systolic}/{bp_diastolic} mmHg, heart rate {heart_rate} bpm, "
                    "weight {weight_kg} kg, and BMI {bmi}. Laboratory results: "
                    "{lab_text}. {monitoring_focus_text} Linked document references: "
                    "{linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-CHR-003",
                section="objective",
                tier="chronic",
                text=(
                    "The visit record lists blood pressure {bp_systolic}/{bp_diastolic} mmHg, "
                    "heart rate {heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                    "Documented lab results: {lab_text}. {monitoring_focus_text} "
                    "Linked document references: {linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-CHR-004",
                section="objective",
                tier="chronic",
                text=(
                    "Recorded vitals include blood pressure {bp_systolic}/{bp_diastolic} mmHg, "
                    "heart rate {heart_rate} bpm, weight {weight_kg} kg, and BMI {bmi}. "
                    "Laboratory results for the encounter: {lab_text}. "
                    "{monitoring_focus_text} Linked document references: {linked_documents_text}."
                ),
            ),
            SoapTemplate(
                template_id="OBJ-CHR-005",
                section="objective",
                tier="chronic",
                text=(
                    "The objective record for this visit includes blood pressure "
                    "{bp_systolic}/{bp_diastolic} mmHg, heart rate {heart_rate} bpm, "
                    "weight {weight_kg} kg, and BMI {bmi}. Laboratory values are "
                    "recorded as: {lab_text}. {monitoring_focus_text} Linked document "
                    "references: {linked_documents_text}."
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
                    "Assessment summarizes the diagnoses documented for this visit: "
                    "{diagnosis_text}. {diagnosis_focus_text} {condition_focus_text}"
                ),
            ),
            SoapTemplate(
                template_id="ASM-NRM-002",
                section="assessment",
                tier="normal",
                text=(
                    "The assessment entry lists the visit diagnoses as {diagnosis_text}. "
                    "{diagnosis_focus_text} {retrieval_focus_text}"
                ),
            ),
            SoapTemplate(
                template_id="ASM-NRM-003",
                section="assessment",
                tier="normal",
                text=(
                    "The documented diagnosis summary for this encounter is: "
                    "{diagnosis_text}. {diagnosis_focus_text} {visit_context_text}"
                ),
            ),
        ),
        "moderate": (
            SoapTemplate(
                template_id="ASM-MOD-001",
                section="assessment",
                tier="moderate",
                text=(
                    "Assessment summarizes the diagnoses documented for this visit: "
                    "{diagnosis_text}. {diagnosis_focus_text} {condition_focus_text}"
                ),
            ),
            SoapTemplate(
                template_id="ASM-MOD-002",
                section="assessment",
                tier="moderate",
                text=(
                    "The recorded assessment for this encounter is based on the visit "
                    "diagnosis list: {diagnosis_text}. {diagnosis_focus_text} "
                    "{monitoring_focus_text}"
                ),
            ),
            SoapTemplate(
                template_id="ASM-MOD-003",
                section="assessment",
                tier="moderate",
                text=(
                    "Diagnoses documented for this visit are summarized as "
                    "{diagnosis_text}. {diagnosis_focus_text} {retrieval_focus_text}"
                ),
            ),
            SoapTemplate(
                template_id="ASM-MOD-004",
                section="assessment",
                tier="moderate",
                text=(
                    "The visit diagnosis list records {diagnosis_text}. "
                    "{diagnosis_focus_text} {condition_focus_text}"
                ),
            ),
        ),
        "chronic": (
            SoapTemplate(
                template_id="ASM-CHR-001",
                section="assessment",
                tier="chronic",
                text=(
                    "Assessment summarizes the diagnoses documented for this visit: "
                    "{diagnosis_text}. {diagnosis_focus_text} {condition_focus_text}"
                ),
            ),
            SoapTemplate(
                template_id="ASM-CHR-002",
                section="assessment",
                tier="chronic",
                text=(
                    "The assessment entry is limited to the diagnoses recorded for this "
                    "visit: {diagnosis_text}. {diagnosis_focus_text} "
                    "{timeline_context_text}"
                ),
            ),
            SoapTemplate(
                template_id="ASM-CHR-003",
                section="assessment",
                tier="chronic",
                text=(
                    "For this longitudinal record entry, the visit diagnoses are "
                    "documented as {diagnosis_text}. {diagnosis_focus_text} "
                    "{monitoring_focus_text}"
                ),
            ),
            SoapTemplate(
                template_id="ASM-CHR-004",
                section="assessment",
                tier="chronic",
                text=(
                    "The visit diagnosis summary includes {diagnosis_text}. "
                    "{diagnosis_focus_text} {retrieval_focus_text}"
                ),
            ),
            SoapTemplate(
                template_id="ASM-CHR-005",
                section="assessment",
                tier="chronic",
                text=(
                    "Recorded diagnoses for this encounter are summarized as "
                    "{diagnosis_text}. {diagnosis_focus_text} {condition_focus_text}"
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
                    "The plan section records the active medication entries as documented: "
                    "{medication_text}. {medication_focus_text} {prior_text}"
                ),
            ),
            SoapTemplate(
                template_id="PLAN-NRM-002",
                section="plan",
                tier="normal",
                text=(
                    "Medication information in the plan is documented as "
                    "{medication_text}. {medication_focus_text} {prior_text} "
                    "{timeline_context_text}"
                ),
            ),
            SoapTemplate(
                template_id="PLAN-NRM-003",
                section="plan",
                tier="normal",
                text=(
                    "The recorded plan lists medication entries as {medication_text}. "
                    "{medication_focus_text} {prior_text}"
                ),
            ),
        ),
        "moderate": (
            SoapTemplate(
                template_id="PLAN-MOD-001",
                section="plan",
                tier="moderate",
                text=(
                    "The plan section records the active medication entries as documented: "
                    "{medication_text}. {medication_focus_text} {prior_text}"
                ),
            ),
            SoapTemplate(
                template_id="PLAN-MOD-002",
                section="plan",
                tier="moderate",
                text=(
                    "The visit plan lists the medication entries documented in the "
                    "record: {medication_text}. {medication_focus_text} "
                    "{prior_text} {timeline_context_text}"
                ),
            ),
            SoapTemplate(
                template_id="PLAN-MOD-003",
                section="plan",
                tier="moderate",
                text=(
                    "Medication details in the plan are recorded as {medication_text}. "
                    "{medication_focus_text} {prior_text}"
                ),
            ),
            SoapTemplate(
                template_id="PLAN-MOD-004",
                section="plan",
                tier="moderate",
                text=(
                    "The documented plan includes the following medication entries: "
                    "{medication_text}. {medication_focus_text} "
                    "{prior_text} {retrieval_focus_text}"
                ),
            ),
        ),
        "chronic": (
            SoapTemplate(
                template_id="PLAN-CHR-001",
                section="plan",
                tier="chronic",
                text=(
                    "The plan section records the active medication entries as documented: "
                    "{medication_text}. {medication_focus_text} {prior_text}"
                ),
            ),
            SoapTemplate(
                template_id="PLAN-CHR-002",
                section="plan",
                tier="chronic",
                text=(
                    "The care plan entry lists medication details as {medication_text}. "
                    "{medication_focus_text} {prior_text} {timeline_context_text}"
                ),
            ),
            SoapTemplate(
                template_id="PLAN-CHR-003",
                section="plan",
                tier="chronic",
                text=(
                    "For this record entry, the plan documents medications as "
                    "{medication_text}. {medication_focus_text} {prior_text}"
                ),
            ),
            SoapTemplate(
                template_id="PLAN-CHR-004",
                section="plan",
                tier="chronic",
                text=(
                    "The plan data records medication entries without changing their "
                    "documented form: {medication_text}. {medication_focus_text} "
                    "{prior_text} {retrieval_focus_text}"
                ),
            ),
            SoapTemplate(
                template_id="PLAN-CHR-005",
                section="plan",
                tier="chronic",
                text=(
                    "The documented plan keeps the medication list as recorded: "
                    "{medication_text}. {medication_focus_text} "
                    "{prior_text} {timeline_context_text}"
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
