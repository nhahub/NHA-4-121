"""
generators/visit_generator.py

Deterministic v1.7 Lite visit timeline generator.

RESPONSIBILITY
--------------
This module builds the `visits` list inside a patient shell dict.  For each
visit it generates:

    visit_id, visit_date, visit_type, attending_physician, diagnoses,
    vitals, labs (empty), medications (empty), soap_note (empty),
    linked_documents (empty), prior_visit_id, visit_role,
    timeline_pattern, timeline_gap_days, clinical_event,
    retrieval_context

It does NOT generate:
    - lab values         (→ generators/lab_generator.py)
    - medication records (→ generators/medication_generator.py)
    - allergy records    (→ generators/allergy_generator.py)
    - SOAP prose         (→ soap/soap_generator.py)
    - ChromaDB chunks    (→ ingestion/chunker.py)
    - safe_distractor text appended to SOAP (→ soap/soap_generator.py)

BLUEPRINT CONTRACT
------------------
This file accepts PatientBlueprint dataclass instances from
config/patient_blueprints.py.  It does NOT accept the old dict-based
blueprint schema.

clinical_event is DERIVED from visit_role at generation time using the
_CLINICAL_EVENT_MAP table in this file.  Blueprints do not need to carry a
pre-built clinical_events list.

DETERMINISM
-----------
- Base visit date is derived from patient_id ordinal and tier.
- Timeline gaps come from TIMELINE_GAP_DAYS[blueprint.timeline_pattern].
- Vitals use tier, conditions, visit_index, and semantic_focus.
- Attending physician cycles using patient ordinal and visit index.
- No random module is used anywhere in this file.

LABS AND MEDICATIONS
--------------------
generate_visits_for_patient leaves labs=[] and medications=[] in every
visit.  The preferred integration pattern is:

    patient = generate_patient_from_blueprint(bp, idx)
    generate_visits_for_patient(patient, blueprint)  # visits populated here
    generate_labs_for_patient(patient, blueprint)    # labs added in-place
    generate_medications_for_patient(patient, blueprint)

Backward-compatible factory injection (lab_factory / medication_factory
kwargs) is preserved for scripts that do not yet call dedicated generators.
When lab_generator and medication_generator are complete, the fallback
factories in this file can be removed.

SAFE DISTRACTORS
----------------
If blueprint.distractor_visit_index is set, the corresponding visit dict
receives a 'safe_distractors' key with a single context_only entry.
This key is optional and schema-compatible (validators tolerate unknown
visit keys by WARN, not FAIL, as long as required keys are all present).
SOAP generation must place any distractor text AFTER primary clinical
content and must not make it a retrieval anchor.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from copy import deepcopy
from datetime import date, datetime, timedelta
from typing import Any, Final

from config.constants import (
    ATTENDING_PHYSICIANS,
    CLINICAL_EVENT_TYPES,
    DATE_FORMAT,
    EMPTY_SOAP_NOTE,
    FLAGS,
    LAB_REFERENCE_RANGES,
    LAB_TYPES,
    LAB_UNITS,
    MEDICATION_NAMES,
    MEDICATION_STATUS,
    MEDICATION_TRAJECTORY_EVENTS,
    MEDICATION_WHITELIST,
    REQUIRED_CLINICAL_EVENT_FIELDS,
    REQUIRED_LAB_FIELDS,
    REQUIRED_MEDICATION_FIELDS,
    REQUIRED_RETRIEVAL_CONTEXT_FIELDS,
    REQUIRED_VISIT_FIELDS,
    REQUIRED_VITAL_FIELDS,
    SAFE_DISTRACTORS,
    SAFE_DISTRACTOR_STATUS,
    SOAP_SECTIONS,
    TIMELINE_GAP_DAYS,
    TIMELINE_PATTERNS,
    VISIT_ROLES,
    VISIT_TYPES,
    VITAL_LIMITS,
)
from config.patient_blueprints import BLUEPRINT_BY_ID, PatientBlueprint

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

VisitRecord      = dict[str, Any]
LabRecord        = dict[str, Any]
MedicationRecord = dict[str, Any]
ClinicalEvent    = dict[str, str]

LabFactory        = Callable[..., list[LabRecord]]
MedicationFactory = Callable[..., list[MedicationRecord]]


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_REFERENCE_START_DATE: Final[date] = date(2023, 1, 10)

# Small per-tier offset so patients in the same tier don't all share
# identical visit dates, making timeline debugging easier.
_TIER_START_OFFSETS_DAYS: Final[dict[str, int]] = {
    "normal":   0,
    "moderate": 14,
    "chronic":  28,
}

_MEDICATION_STOP_STATUSES: Final[frozenset[str]] = frozenset({
    "completed",
    "stopped",
    "temporarily_stopped",
})

_MEDICATION_CHANGE_STATUSES: Final[frozenset[str]] = frozenset({
    "started",
    "dose_adjusted",
    "temporarily_stopped",
    "restarted",
    "completed",
    "added",
    "stopped",
})

# ---------------------------------------------------------------------------
# Visit-role → visit_type mapping
# ---------------------------------------------------------------------------
# Every visit_role from constants.VISIT_ROLES maps to exactly one visit_type.
# hospitalization and emergency_exacerbation are the only non-follow_up
# non-initial special cases.
#
# NOTE on PAT-CHR-003 vs PAT-CHR-005:
#   Both use visit_role "post_discharge_stabilization", but for CHR-003 this
#   means post-EXACERBATION (outpatient) while for CHR-005 it means true
#   post-DISCHARGE (inpatient).  The visit_type for both is "follow_up" —
#   the distinction lives in clinical_event.event_summary, which is derived
#   per-patient in _CLINICAL_EVENT_MAP below.
# ---------------------------------------------------------------------------

_VISIT_TYPE_MAP: Final[dict[str, str]] = {
    "initial_diagnosis":           "initial",
    "baseline_assessment":         "initial",
    "acute_treatment_started":     "initial",
    "medication_started":          "initial",
    "routine_follow_up":           "follow_up",
    "lab_trend_review":            "follow_up",
    "partial_adherence":           "follow_up",
    "poor_adherence":              "follow_up",
    "symptom_control_review":      "follow_up",
    "course_completed":            "follow_up",
    "second_medication_added":     "follow_up",
    "ckd_monitoring":              "follow_up",
    "medication_reconciliation":   "follow_up",
    "symptom_flare":               "follow_up",
    "post_discharge_stabilization":"follow_up",
    "recovery_confirmed":          "follow_up",
    "dose_adjustment":             "follow_up",
    "medication_continued":        "follow_up",
    "emergency_exacerbation":      "emergency",
    "hospitalization":             "hospitalization",
}

# ---------------------------------------------------------------------------
# visit_role → clinical_event base table
# ---------------------------------------------------------------------------
# Each entry provides event_type, event_label, and a TEMPLATE for
# event_summary.  The summary template may contain {conditions},
# {primary_medication}, and {added_medication} placeholders that are
# resolved per-patient at generation time.
#
# Rules:
#   - event_type values must exist in CLINICAL_EVENT_TYPES.
#   - event_summary must be plain-language and retrieval-useful.
#   - Do not use inpatient/discharge language for emergency_exacerbation
#     (that applies to PAT-CHR-003, not PAT-CHR-005).
#   - "hospitalization" role carries inpatient language (PAT-CHR-005 only).
# ---------------------------------------------------------------------------

_CLINICAL_EVENT_TEMPLATES: Final[dict[str, dict[str, str]]] = {
    "initial_diagnosis": {
        "event_type":    "diagnosis_documented",
        "event_label":   "Initial diagnosis documented",
        "event_summary": (
            "Initial {conditions} diagnosis was documented and baseline "
            "management plan established with {primary_medication}."
        ),
    },
    "baseline_assessment": {
        "event_type":    "baseline_labs_reviewed",
        "event_label":   "Baseline assessment completed",
        "event_summary": (
            "Baseline assessment for {conditions} was completed and "
            "initial management documented."
        ),
    },
    "acute_treatment_started": {
        "event_type":    "medication_started",
        "event_label":   "Acute treatment started",
        "event_summary": (
            "Acute treatment with {primary_medication} was started for "
            "{conditions} at initial presentation."
        ),
    },
    "medication_started": {
        "event_type":    "medication_started",
        "event_label":   "Medication started",
        "event_summary": (
            "{primary_medication} was started for documented {conditions}."
        ),
    },
    "routine_follow_up": {
        "event_type":    "medication_continued",
        "event_label":   "Routine follow-up visit",
        "event_summary": (
            "Routine follow-up for {conditions} with {primary_medication} "
            "continued and condition reviewed."
        ),
    },
    "lab_trend_review": {
        "event_type":    "lab_improvement",
        "event_label":   "Laboratory trend reviewed",
        "event_summary": (
            "Laboratory trend for {conditions} was reviewed at scheduled "
            "follow-up; {primary_medication} therapy continued."
        ),
    },
    "partial_adherence": {
        "event_type":    "adherence_issue",
        "event_label":   "Partial adherence documented",
        "event_summary": (
            "Patient reported partial adherence with missed {primary_medication} "
            "doses; {conditions} control reviewed and adherence counselling provided."
        ),
    },
    "poor_adherence": {
        "event_type":    "adherence_issue",
        "event_label":   "Poor adherence documented",
        "event_summary": (
            "Patient reported poor adherence with {primary_medication}; "
            "{conditions} monitoring labs reviewed and adherence barriers discussed."
        ),
    },
    "symptom_control_review": {
        "event_type":    "symptom_improvement",
        "event_label":   "Symptom control reviewed",
        "event_summary": (
            "Symptom control for {conditions} with {primary_medication} "
            "was reviewed and documented as improved at follow-up."
        ),
    },
    "course_completed": {
        "event_type":    "short_course_completed",
        "event_label":   "Short course completed",
        "event_summary": (
            "{primary_medication} short course for {conditions} was completed "
            "and resolution of symptoms was confirmed at follow-up."
        ),
    },
    "second_medication_added": {
        "event_type":    "medication_added",
        "event_label":   "Second medication added",
        "event_summary": (
            "{added_medication} was added for {conditions} after persistent "
            "condition-related concerns despite ongoing {primary_medication} therapy."
        ),
    },
    "ckd_monitoring": {
        "event_type":    "baseline_labs_reviewed",
        "event_label":   "CKD monitoring visit",
        "event_summary": (
            "Scheduled CKD monitoring visit completed; kidney function labs "
            "and {conditions} control reviewed with {primary_medication} continued."
        ),
    },
    "medication_reconciliation": {
        "event_type":    "post_discharge_review",
        "event_label":   "Medication reconciliation completed",
        "event_summary": (
            "Post-discharge medication reconciliation for {conditions} completed; "
            "all active medications including {primary_medication} reviewed and confirmed."
        ),
    },
    "symptom_flare": {
        "event_type":    "symptom_flare",
        "event_label":   "Symptom flare documented",
        "event_summary": (
            "Symptom flare for {conditions} was documented; {added_medication} "
            "added alongside ongoing {primary_medication} therapy."
        ),
    },
    "post_discharge_stabilization": {
        # Default template — overridden per-patient for CHR-003 vs CHR-005
        # via _build_clinical_event_summary below.
        "event_type":    "post_discharge_review",
        "event_label":   "Post-discharge stabilization visit",
        "event_summary": (
            "Post-discharge stabilization visit completed for {conditions}; "
            "{primary_medication} therapy reviewed following recent hospitalisation."
        ),
    },
    "recovery_confirmed": {
        "event_type":    "recovery_confirmed",
        "event_label":   "Recovery confirmed",
        "event_summary": (
            "Recovery from {conditions} was confirmed; {primary_medication} "
            "course completed and no further follow-up required at this time."
        ),
    },
    "dose_adjustment": {
        "event_type":    "dose_adjustment",
        "event_label":   "Dose adjustment documented",
        "event_summary": (
            "Dose adjustment for {primary_medication} was made for {conditions} "
            "based on monitoring results."
        ),
    },
    "medication_continued": {
        "event_type":    "medication_continued",
        "event_label":   "Medication continued",
        "event_summary": (
            "{primary_medication} was continued for {conditions} with no "
            "changes at this follow-up visit."
        ),
    },
    "emergency_exacerbation": {
        # Outpatient emergency only — used by PAT-CHR-003 (Asthma+HTN).
        # Must NOT use admitted / inpatient / discharge language.
        "event_type":    "emergency_visit",
        "event_label":   "Emergency exacerbation visit",
        "event_summary": (
            "Patient attended emergency clinic with acute {conditions} exacerbation; "
            "{primary_medication} reviewed and management plan updated."
        ),
    },
    "hospitalization": {
        # True inpatient admission — used by PAT-CHR-005 only.
        "event_type":    "hospitalization",
        "event_label":   "Inpatient hospitalisation documented",
        "event_summary": (
            "Inpatient hospitalisation for {conditions} was documented; "
            "{primary_medication} management reviewed and post-discharge "
            "stabilisation plan established."
        ),
    },
}


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------

class VisitGenerationError(ValueError):
    """Raised when a blueprint cannot produce a valid visit sequence."""


# ---------------------------------------------------------------------------
# Primary public API
# ---------------------------------------------------------------------------

def generate_visits_for_patient(
    patient: dict,
    blueprint: PatientBlueprint | None = None,
    *,
    lab_factory: LabFactory | None = None,
    medication_factory: MedicationFactory | None = None,
) -> dict:
    """Populate patient['visits'] in-place and return the patient dict.

    This is the standard integration point for the generation pipeline:

        patient = generate_patient_from_blueprint(bp, idx)
        generate_visits_for_patient(patient, blueprint)

    Args:
        patient:            Patient shell dict from patient_generator.
        blueprint:          PatientBlueprint dataclass.  If None, looked up
                            from BLUEPRINT_BY_ID using patient['patient_id'].
        lab_factory:        Optional factory; called with (blueprint,
                            visit_index, visit_date, visit_role,
                            clinical_event) kwargs. Defaults to empty list.
        medication_factory: Optional factory; same signature. Defaults to
                            empty list.

    Returns:
        The same patient dict with visits populated.
    """
    if blueprint is None:
        pid = patient.get("patient_id", "")
        if pid not in BLUEPRINT_BY_ID:
            raise VisitGenerationError(
                f"No blueprint found for patient_id='{pid}'. "
                "Pass blueprint explicitly or ensure BLUEPRINT_BY_ID is populated."
            )
        blueprint = BLUEPRINT_BY_ID[pid]

    visits = _build_all_visits(patient, blueprint,
                               lab_factory=lab_factory,
                               medication_factory=medication_factory)
    patient["visits"] = visits
    return patient


def generate_visits_for_blueprint(
    blueprint: PatientBlueprint,
    demographics: dict | None = None,
    *,
    lab_factory: LabFactory | None = None,
    medication_factory: MedicationFactory | None = None,
) -> list[VisitRecord]:
    """Generate and return visit list without mutating a patient dict.

    Kept for scripts that prefer the list-return pattern.
    demographics is accepted but unused (stable call signature).
    """
    del demographics
    patient_id = blueprint.patient_id
    # Build a minimal stub so _build_all_visits can extract patient_id.
    stub = {"patient_id": patient_id}
    return _build_all_visits(stub, blueprint,
                             lab_factory=lab_factory,
                             medication_factory=medication_factory)


# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------

def generate_visits(
    blueprint: PatientBlueprint,
    demographics: dict | None = None,
    *,
    lab_factory: LabFactory | None = None,
    medication_factory: MedicationFactory | None = None,
) -> list[VisitRecord]:
    """Backward-compatible alias for generate_visits_for_blueprint."""
    return generate_visits_for_blueprint(
        blueprint, demographics,
        lab_factory=lab_factory,
        medication_factory=medication_factory,
    )


def build_visits(
    blueprint: PatientBlueprint,
    demographics: dict | None = None,
    *,
    lab_factory: LabFactory | None = None,
    medication_factory: MedicationFactory | None = None,
) -> list[VisitRecord]:
    """Backward-compatible alias for older orchestration code."""
    return generate_visits_for_blueprint(
        blueprint, demographics,
        lab_factory=lab_factory,
        medication_factory=medication_factory,
    )


# ---------------------------------------------------------------------------
# Public helpers (used by tests and other generators)
# ---------------------------------------------------------------------------

def build_visit_id(patient_id: str, visit_index: int) -> str:
    """Build a deterministic visit ID from a patient_id and 1-based index.

    PAT-MOD-001 + index 3  →  VST-MOD-001-003
    """
    if visit_index < 1:
        raise VisitGenerationError(
            f"visit_index must be >= 1, got {visit_index}."
        )
    try:
        _, tier_prefix, patient_number = patient_id.split("-")
    except ValueError as exc:
        raise VisitGenerationError(
            f"Invalid patient_id format for visit ID: '{patient_id}'"
        ) from exc
    return f"VST-{tier_prefix}-{patient_number}-{visit_index:03d}"


def build_visit_date(blueprint: PatientBlueprint, visit_index: int) -> str:
    """Return the ISO visit date string for a 1-based visit_index."""
    gaps = _resolve_timeline_gaps(blueprint.timeline_pattern, blueprint.visit_count)
    base = _build_base_visit_date(blueprint.patient_id, blueprint.tier)
    return _date_to_str(base + timedelta(days=gaps[visit_index - 1]))


def build_visit_type(visit_role: str, blueprint: PatientBlueprint) -> str:
    """Map a visit_role to a visit_type string.

    Delegates to the module-level _VISIT_TYPE_MAP.  The PatientBlueprint is
    accepted for future extensibility (e.g. per-patient overrides) but is
    not currently needed — the mapping is fully determined by visit_role.
    """
    _ = blueprint  # reserved for per-patient override if needed
    if visit_role not in _VISIT_TYPE_MAP:
        raise VisitGenerationError(
            f"No visit_type mapping for visit_role '{visit_role}'. "
            f"Add it to _VISIT_TYPE_MAP."
        )
    return _VISIT_TYPE_MAP[visit_role]


def build_clinical_event(
    visit_role: str,
    blueprint: PatientBlueprint,
    visit_index: int,
) -> ClinicalEvent:
    """Build a clinical_event dict for one visit.

    event_summary is resolved from the template with blueprint context.
    PAT-CHR-003 post_discharge_stabilization receives outpatient wording.
    PAT-CHR-005 post_discharge_stabilization receives inpatient wording.
    """
    if visit_role not in _CLINICAL_EVENT_TEMPLATES:
        raise VisitGenerationError(
            f"No clinical_event template for visit_role '{visit_role}'."
        )

    template = _CLINICAL_EVENT_TEMPLATES[visit_role]
    event_type  = template["event_type"]
    event_label = template["event_label"]
    event_summary = _build_clinical_event_summary(
        visit_role=visit_role,
        template_summary=template["event_summary"],
        blueprint=blueprint,
        visit_index=visit_index,
    )

    event: ClinicalEvent = {
        "event_type":    event_type,
        "event_label":   event_label,
        "event_summary": event_summary,
    }
    _require_keys(event, REQUIRED_CLINICAL_EVENT_FIELDS, "clinical_event")

    if event["event_type"] not in CLINICAL_EVENT_TYPES:
        raise VisitGenerationError(
            f"event_type '{event['event_type']}' not in CLINICAL_EVENT_TYPES."
        )

    return event


def build_retrieval_context(
    blueprint: PatientBlueprint,
    visit_role: str | None = None,
    clinical_event: dict | None = None,
) -> dict[str, Any]:
    """Build visit-level retrieval_context from blueprint metadata.

    visit_role and clinical_event are accepted for backward compatibility
    but are not stored in retrieval_context (they are already in the visit
    dict proper).  This keeps retrieval_context minimal and safe.
    """
    _ = visit_role, clinical_event   # accepted; not stored in context
    context: dict[str, Any] = {
        "semantic_focus":       blueprint.semantic_focus,
        "retrieval_intent_tags": list(blueprint.retrieval_intent_tags),
    }
    _require_keys(context, REQUIRED_RETRIEVAL_CONTEXT_FIELDS, "retrieval_context")
    return context


def build_vitals(
    blueprint: PatientBlueprint,
    visit_index: int,
    visit_role: str | None = None,
    clinical_event: dict | None = None,
) -> dict[str, int | float]:
    """Generate deterministic vitals for one visit.

    BP lives ONLY in this dict.  It is never stored in labs, ChromaDB
    metadata, clinical_event, or retrieval_context.

    visit_role and clinical_event are accepted so existing callers don't
    break; the logic uses them internally for emergency/hospitalisation
    heart-rate adjustment.
    """
    conditions     = set(blueprint.conditions)
    semantic_focus = blueprint.semantic_focus
    event_type     = clinical_event.get("event_type", "") if clinical_event else ""

    # --- BP -----------------------------------------------------------------
    bp_systolic:  int
    bp_diastolic: int
    if "HTN" in conditions:
        bp_systolic  = max(126, 154 - (visit_index - 1) * 5)
        bp_diastolic = max(78,   96 - (visit_index - 1) * 3)
        if semantic_focus in {"poor_adherence", "medication_escalation"} and visit_index == 2:
            bp_systolic  += 6
            bp_diastolic += 3
    else:
        bp_systolic  = 120
        bp_diastolic = 78

    # --- Heart rate ---------------------------------------------------------
    heart_rate: int = 76
    if "Asthma" in conditions:
        heart_rate = 82
        if event_type in {"symptom_flare", "emergency_visit"}:
            heart_rate = 96
        elif event_type == "hospitalization":
            heart_rate = 104

    if event_type == "hospitalization":
        bp_systolic  = min(bp_systolic  + 8, int(VITAL_LIMITS["bp_systolic"][1]))
        bp_diastolic = min(bp_diastolic + 4, int(VITAL_LIMITS["bp_diastolic"][1]))
        heart_rate   = max(heart_rate, 102)

    # --- Weight / BMI -------------------------------------------------------
    weight_kg: float
    if "T2DM" in conditions or "Dyslipidemia" in conditions:
        weight_kg = 82.0 - min(visit_index - 1, 4) * 0.7
    elif "IDA" in conditions:
        weight_kg = 66.0
    elif "Acute_URTI" in conditions:
        weight_kg = 72.0
    else:
        weight_kg = 74.0

    height_m = _deterministic_height_m(blueprint.patient_id)
    bmi      = round(weight_kg / (height_m ** 2), 1)

    vitals: dict[str, int | float] = {
        "bp_systolic":  int(bp_systolic),
        "bp_diastolic": int(bp_diastolic),
        "heart_rate":   int(heart_rate),
        "weight_kg":    round(weight_kg, 1),
        "bmi":          bmi,
    }

    _require_keys(vitals, REQUIRED_VITAL_FIELDS, "vitals")
    _validate_vital_limits(vitals, blueprint.patient_id, visit_index)
    return vitals


def build_empty_soap_note() -> dict[str, str]:
    """Return a fresh empty SOAP-note dict."""
    soap_note = dict(EMPTY_SOAP_NOTE)
    _require_keys(soap_note, SOAP_SECTIONS, "soap_note")
    return soap_note


def infer_visit_type(
    visit_index: int,
    visit_role: str,
    clinical_event: dict | None = None,
) -> str:
    """Backward-compatible wrapper around build_visit_type.

    visit_index and clinical_event are accepted for API compatibility but
    the mapping is now entirely determined by visit_role.
    """
    _ = visit_index, clinical_event
    return _VISIT_TYPE_MAP.get(visit_role, "follow_up")


# ---------------------------------------------------------------------------
# Core internal builder
# ---------------------------------------------------------------------------

def _build_all_visits(
    patient_stub: dict,
    blueprint: PatientBlueprint,
    *,
    lab_factory: LabFactory | None,
    medication_factory: MedicationFactory | None,
) -> list[VisitRecord]:
    """Build the full ordered visit list for one patient blueprint."""

    _validate_blueprint_fields(blueprint)

    patient_id      = blueprint.patient_id
    visit_count     = blueprint.visit_count
    timeline_pattern = blueprint.timeline_pattern
    visit_roles     = blueprint.visit_roles
    timeline_gaps   = _resolve_timeline_gaps(timeline_pattern, visit_count)
    base_date       = _build_base_visit_date(patient_id, blueprint.tier)

    labs_fn  = lab_factory  or _empty_lab_factory
    meds_fn  = medication_factory or _empty_medication_factory

    visits: list[VisitRecord] = []

    for i in range(visit_count):
        visit_index      = i + 1                           # 1-based
        visit_role       = visit_roles[i]
        gap_days         = timeline_gaps[i]
        visit_date_str   = _date_to_str(base_date + timedelta(days=gap_days))
        visit_id         = build_visit_id(patient_id, visit_index)
        prior_visit_id   = visits[-1]["visit_id"] if visits else None
        visit_type       = _VISIT_TYPE_MAP.get(visit_role, "follow_up")
        clinical_event   = build_clinical_event(visit_role, blueprint, visit_index)

        visit: VisitRecord = {
            "visit_id":            visit_id,
            "visit_date":          visit_date_str,
            "visit_type":          visit_type,
            "attending_physician": _select_attending_physician(patient_id, visit_index),
            "diagnoses":           list(blueprint.conditions),
            "vitals":              build_vitals(blueprint, visit_index,
                                                visit_role, clinical_event),
            "labs":                labs_fn(
                blueprint=blueprint,
                visit_index=visit_index,
                visit_date=visit_date_str,
                visit_role=visit_role,
                clinical_event=deepcopy(clinical_event),
            ),
            "medications":         meds_fn(
                blueprint=blueprint,
                visit_index=visit_index,
                visit_date=visit_date_str,
                visit_role=visit_role,
                clinical_event=deepcopy(clinical_event),
            ),
            "soap_note":           build_empty_soap_note(),
            "linked_documents":    [],
            "prior_visit_id":      prior_visit_id,
            "visit_role":          visit_role,
            "timeline_pattern":    timeline_pattern,
            "timeline_gap_days":   gap_days,
            "clinical_event":      clinical_event,
            "retrieval_context":   build_retrieval_context(blueprint, visit_role,
                                                           clinical_event),
        }

        # Optional safe distractor — schema-compatible optional key.
        if (blueprint.distractor_visit_index is not None
                and blueprint.distractor_type is not None
                and i == blueprint.distractor_visit_index):
            visit["safe_distractors"] = _build_safe_distractor(
                blueprint.distractor_type, blueprint.patient_id
            )

        _validate_visit_shape(visit, patient_id=patient_id, visit_index=visit_index)
        visits.append(visit)

    return visits


# ---------------------------------------------------------------------------
# Clinical event summary resolver
# ---------------------------------------------------------------------------

def _build_clinical_event_summary(
    *,
    visit_role: str,
    template_summary: str,
    blueprint: PatientBlueprint,
    visit_index: int,
) -> str:
    """Resolve a template summary string with blueprint context.

    Template placeholders:
        {conditions}         → human-readable condition list
        {primary_medication} → first initial_medication name
        {added_medication}   → first added_medication name (or primary if none)

    PAT-CHR-003 post_discharge_stabilization:
        Outpatient wording — no 'admitted' / 'inpatient' / 'discharge' language.

    PAT-CHR-005 post_discharge_stabilization:
        Inpatient wording — full post-discharge language allowed.
    """
    conditions_str       = _format_conditions(blueprint.conditions)
    primary_med          = blueprint.initial_medications[0] if blueprint.initial_medications else "medication"
    added_med            = (blueprint.added_medications[0]
                            if blueprint.added_medications else primary_med)

    # Per-patient override for post_discharge_stabilization
    if visit_role == "post_discharge_stabilization":
        if blueprint.patient_id == "PAT-CHR-003":
            # Outpatient post-exacerbation — never use inpatient language
            return (
                f"Patient returned for post-exacerbation stabilisation after "
                f"emergency {conditions_str} visit; {primary_med} therapy "
                f"reviewed and recovery progress documented."
            )
        if blueprint.patient_id == "PAT-CHR-005":
            # True inpatient post-discharge
            return (
                f"Post-discharge stabilisation for {conditions_str} completed; "
                f"{primary_med} and all reconciled medications reviewed "
                f"following recent inpatient hospitalisation."
            )

    # symptom_flare: make added_med explicit when it exists
    if visit_role == "symptom_flare" and blueprint.added_medications:
        return (
            f"Symptom flare for {conditions_str} documented; "
            f"{added_med} added alongside ongoing {primary_med} therapy."
        )

    # General template resolution
    summary = template_summary.format(
        conditions=conditions_str,
        primary_medication=primary_med,
        added_medication=added_med,
    )
    return summary


def _format_conditions(conditions: tuple[str, ...]) -> str:
    """Join conditions into a readable string for event summaries."""
    display = {
        "T2DM":             "type 2 diabetes",
        "HTN":              "hypertension",
        "Asthma":           "asthma",
        "IDA":              "iron deficiency anaemia",
        "GERD":             "GERD",
        "Dyslipidemia":     "dyslipidaemia",
        "Allergic_Rhinitis":"allergic rhinitis",
        "UTI":              "urinary tract infection",
        "CKD":              "chronic kidney disease",
        "Acute_URTI":       "acute upper respiratory tract infection",
    }
    parts = [display.get(c, c) for c in conditions]
    if len(parts) == 1:
        return parts[0]
    return ", ".join(parts[:-1]) + " and " + parts[-1]


# ---------------------------------------------------------------------------
# Safe distractor builder
# ---------------------------------------------------------------------------

def _build_safe_distractor(distractor_type: str, patient_id: str) -> list[dict]:
    """Build a single safe_distractors list entry for one visit."""
    if distractor_type not in SAFE_DISTRACTORS:
        raise VisitGenerationError(
            f"{patient_id}: distractor_type '{distractor_type}' not in SAFE_DISTRACTORS."
        )
    text_map: dict[str, str] = {
        "mild_fatigue":      "Patient reported mild fatigue during the visit period.",
        "stress":            "Patient mentioned increased work-related stress during this period.",
        "poor_sleep":        "Patient reported reduced sleep quality during a busy period.",
        "diet_inconsistency":"Patient noted some inconsistency in dietary habits recently.",
        "mild_headache":     "Patient mentioned occasional mild headaches not related to primary condition.",
    }
    text = text_map.get(distractor_type, f"Patient reported {distractor_type.replace('_', ' ')}.")
    return [{
        "type":             distractor_type,
        "text":             text,
        "clinical_status":  SAFE_DISTRACTOR_STATUS,
    }]


# ---------------------------------------------------------------------------
# Timeline helpers
# ---------------------------------------------------------------------------

def _resolve_timeline_gaps(timeline_pattern: str, visit_count: int) -> tuple[int, ...]:
    """Return the correct gap-day offsets for the requested visit count.

    If visit_count is less than or equal to the pattern length, the first
    visit_count entries are returned.  If visit_count exceeds the pattern
    (should not happen with v1.7 Lite blueprints), the sequence is extended
    conservatively using the last observed interval.
    """
    if timeline_pattern not in TIMELINE_GAP_DAYS:
        raise VisitGenerationError(
            f"Unknown timeline_pattern: '{timeline_pattern}'. "
            f"Valid patterns: {list(TIMELINE_GAP_DAYS.keys())}"
        )
    gaps = tuple(int(g) for g in TIMELINE_GAP_DAYS[timeline_pattern])

    if len(gaps) >= visit_count:
        return gaps[:visit_count]

    if len(gaps) < 2:
        raise VisitGenerationError(
            f"Timeline pattern '{timeline_pattern}' must contain >= 2 gap values."
        )

    extended = list(gaps)
    last_interval = gaps[-1] - gaps[-2]
    while len(extended) < visit_count:
        extended.append(extended[-1] + last_interval)
    return tuple(extended)


def _build_base_visit_date(patient_id: str, tier: str) -> date:
    """Deterministic base date from patient ordinal and tier offset."""
    ordinal       = _patient_ordinal(patient_id)
    tier_offset   = _TIER_START_OFFSETS_DAYS.get(tier, 0)
    patient_offset = (ordinal - 1) * 3
    return _REFERENCE_START_DATE + timedelta(days=tier_offset + patient_offset)


def _date_to_str(value: date) -> str:
    return value.strftime(DATE_FORMAT)


# ---------------------------------------------------------------------------
# Physician and patient helpers
# ---------------------------------------------------------------------------

def _select_attending_physician(patient_id: str, visit_index: int) -> str:
    if not ATTENDING_PHYSICIANS:
        raise VisitGenerationError("ATTENDING_PHYSICIANS pool is empty.")
    ordinal = _patient_ordinal(patient_id)
    return ATTENDING_PHYSICIANS[(ordinal + visit_index - 2) % len(ATTENDING_PHYSICIANS)]


def _patient_ordinal(patient_id: str) -> int:
    """Extract the numeric suffix of a patient_id as an integer."""
    try:
        return int(patient_id.rsplit("-", maxsplit=1)[-1])
    except ValueError as exc:
        raise VisitGenerationError(
            f"Cannot extract patient ordinal from '{patient_id}'."
        ) from exc


def _deterministic_height_m(patient_id: str) -> float:
    ordinal = _patient_ordinal(patient_id)
    return 1.62 + ((ordinal - 1) % 7) * 0.025


# ---------------------------------------------------------------------------
# Empty fallback factories
# (labs=[] and medications=[] until dedicated generators are integrated)
# ---------------------------------------------------------------------------

def _empty_lab_factory(**_kwargs: Any) -> list[LabRecord]:
    """Default lab factory: returns empty list until lab_generator is ready."""
    return []


def _empty_medication_factory(**_kwargs: Any) -> list[MedicationRecord]:
    """Default medication factory: returns empty list until medication_generator is ready."""
    return []


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_blueprint_fields(blueprint: PatientBlueprint) -> None:
    """Pre-flight check on the fields this module needs."""
    pid = blueprint.patient_id

    if blueprint.visit_count <= 0:
        raise VisitGenerationError(f"{pid}: visit_count must be > 0.")

    if blueprint.timeline_pattern not in TIMELINE_PATTERNS:
        raise VisitGenerationError(
            f"{pid}: invalid timeline_pattern '{blueprint.timeline_pattern}'."
        )

    if len(blueprint.visit_roles) != blueprint.visit_count:
        raise VisitGenerationError(
            f"{pid}: len(visit_roles)={len(blueprint.visit_roles)} "
            f"!= visit_count={blueprint.visit_count}."
        )

    invalid_roles = sorted(set(blueprint.visit_roles) - set(VISIT_ROLES))
    if invalid_roles:
        raise VisitGenerationError(
            f"{pid}: unrecognised visit_roles: {invalid_roles}."
        )

    gaps = _resolve_timeline_gaps(blueprint.timeline_pattern, blueprint.visit_count)
    if len(gaps) < blueprint.visit_count:
        raise VisitGenerationError(
            f"{pid}: timeline_pattern '{blueprint.timeline_pattern}' "
            f"cannot supply {blueprint.visit_count} gap values."
        )


def _validate_visit_shape(
    visit: VisitRecord,
    *,
    patient_id: str,
    visit_index: int,
) -> None:
    """Check the generated visit satisfies schema and safety contracts."""
    label = f"{patient_id}.visit[{visit_index}]"

    _require_keys(visit, REQUIRED_VISIT_FIELDS, label)

    if visit["visit_type"] not in VISIT_TYPES:
        raise VisitGenerationError(
            f"{label}: invalid visit_type '{visit['visit_type']}'."
        )
    if visit["visit_role"] not in VISIT_ROLES:
        raise VisitGenerationError(
            f"{label}: invalid visit_role '{visit['visit_role']}'."
        )
    if visit["timeline_pattern"] not in TIMELINE_PATTERNS:
        raise VisitGenerationError(
            f"{label}: invalid timeline_pattern '{visit['timeline_pattern']}'."
        )

    # Date format
    try:
        datetime.strptime(str(visit["visit_date"]), DATE_FORMAT)
    except ValueError as exc:
        raise VisitGenerationError(
            f"{label}: invalid visit_date '{visit['visit_date']}'."
        ) from exc

    # prior_visit_id rules
    if visit_index == 1 and visit["prior_visit_id"] is not None:
        raise VisitGenerationError(f"{label}: first visit must have prior_visit_id=None.")
    if visit_index > 1 and not visit["prior_visit_id"]:
        raise VisitGenerationError(f"{label}: follow-up must have prior_visit_id set.")

    # Sub-object required keys
    _require_keys(visit["vitals"], REQUIRED_VITAL_FIELDS,
                  f"{label}.vitals")
    _require_keys(visit["clinical_event"], REQUIRED_CLINICAL_EVENT_FIELDS,
                  f"{label}.clinical_event")
    _require_keys(visit["retrieval_context"], REQUIRED_RETRIEVAL_CONTEXT_FIELDS,
                  f"{label}.retrieval_context")
    _require_keys(visit["soap_note"], SOAP_SECTIONS,
                  f"{label}.soap_note")

    # clinical_event type validity
    if visit["clinical_event"]["event_type"] not in CLINICAL_EVENT_TYPES:
        raise VisitGenerationError(
            f"{label}: invalid clinical_event.event_type "
            f"'{visit['clinical_event']['event_type']}'."
        )

    # Labs and medications must be lists
    if not isinstance(visit["labs"], list):
        raise VisitGenerationError(f"{label}.labs must be a list.")
    if not isinstance(visit["medications"], list):
        raise VisitGenerationError(f"{label}.medications must be a list.")

    # timeline_events is forbidden
    if "timeline_events" in visit:
        raise VisitGenerationError(
            f"{label}: 'timeline_events' is a forbidden field."
        )

    # BP must not appear outside vitals
    for forbidden_key in ("bp_systolic", "bp_diastolic", "blood_pressure",
                          "bp", "sbp", "dbp", "systolic", "diastolic"):
        if forbidden_key in visit.get("retrieval_context", {}):
            raise VisitGenerationError(
                f"{label}.retrieval_context must not contain BP field '{forbidden_key}'."
            )
        if forbidden_key in visit.get("clinical_event", {}):
            raise VisitGenerationError(
                f"{label}.clinical_event must not contain BP field '{forbidden_key}'."
            )


def _validate_vital_limits(
    vitals: dict[str, int | float],
    patient_id: str,
    visit_index: int,
) -> None:
    """Verify vital values stay inside VITAL_LIMITS from constants."""
    for field, (lo, hi) in VITAL_LIMITS.items():
        if field in vitals:
            val = vitals[field]
            if not (lo <= val <= hi):
                raise VisitGenerationError(
                    f"{patient_id}.visit[{visit_index}].vitals.{field}={val} "
                    f"outside allowed range [{lo}, {hi}]."
                )


def _require_keys(mapping: object, required_keys: Iterable[str], label: str) -> None:
    if not isinstance(mapping, Mapping):
        raise VisitGenerationError(f"{label} must be a mapping, got {type(mapping).__name__}.")
    missing = [k for k in required_keys if k not in mapping]
    if missing:
        raise VisitGenerationError(f"{label} missing required keys: {missing}")
