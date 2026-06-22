"""
generators/medication_generator.py

Deterministic v1.7 Lite medication record generator.

RESPONSIBILITY
--------------
This module populates patient["visits"][i]["medications"] in-place for every
visit in a patient shell that was already built by visit_generator.py.

It does NOT generate:
    - lab values          (→ generators/lab_generator.py)
    - allergy records     (→ generators/allergy_generator.py)
    - SOAP prose          (→ soap/soap_generator.py)
    - ChromaDB chunks     (→ ingestion/chunker.py)
    - SOAP notes          (→ soap/soap_generator.py)

BLUEPRINT CONTRACT
------------------
- initial_medications  : active from visit 1; usually carry simple_start_continue.
- added_medications    : introduced at a specific visit_role; carry second_medication_added.
- completed_medications: short-course drugs; stopped on course_completed / recovery_confirmed.
- stopped_medications  : permanently stopped (rarely used in this dataset).

Generators must use these structured fields.  medication_arc prose must NOT be parsed.

TRAJECTORY RULES
----------------
Visit 1 (initial_medications):       status=started,   trajectory=simple_start_continue
Continuation visits:                 status=continued, trajectory=simple_start_continue
Adherence visit, targeted med only:  status=continued, trajectory=adherence_interruption
  (only the condition-specific adherence target receives this trajectory;
   other initial medications fall through to simple_start_continue)
Second-medication-added visit:       status=added,     trajectory=second_medication_added
Symptom-flare visit (added meds):    status=added,     trajectory=second_medication_added
Course-completed / recovery visit:   status=completed, trajectory=course_completed
Medication-reconciliation visit:     status=continued, trajectory=post_discharge_reconciliation

DETERMINISM
-----------
All outputs are deterministic.
No random module is used anywhere in this file.
start_date for a medication is set once (at the visit where it first appears)
and never changed on subsequent visits.
"""

from __future__ import annotations

import re
from typing import Any

from config.constants import (
    DATE_REGEX,
    FREQUENCIES,
    MEDICATION_NAMES,
    MEDICATION_STATUS,
    MEDICATION_TRAJECTORY_EVENTS,
    MEDICATION_WHITELIST,
    REQUIRED_MEDICATION_FIELDS,
    ROUTES,
    SHORT_COURSE_MEDICATIONS,
)
from config.patient_blueprints import BLUEPRINT_BY_ID, PatientBlueprint
from generators._generator_utils import _format_conditions  # R2: shared utility


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

MedicationRecord = dict[str, Any]


# ---------------------------------------------------------------------------
# Visit-role sets that drive trajectory overrides
# ---------------------------------------------------------------------------

# Roles where an initial medication should carry adherence_interruption.
_ADHERENCE_ROLES: frozenset[str] = frozenset({
    "partial_adherence",
    "poor_adherence",
})

# Roles where an added medication first appears.
_ADDITION_ROLES: frozenset[str] = frozenset({
    "second_medication_added",
    "symptom_flare",
    "ckd_monitoring",       # PAT-CHR-005: Glibenclamide added at ckd_monitoring
})

# Roles where a short-course medication is marked completed.
_COMPLETION_ROLES: frozenset[str] = frozenset({
    "course_completed",
    "recovery_confirmed",
})

# Roles where all active medications use post_discharge_reconciliation.
_RECONCILIATION_ROLES: frozenset[str] = frozenset({
    "medication_reconciliation",
})


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------

class MedicationGenerationError(ValueError):
    """Raised when medication generation cannot proceed safely."""


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_medications_for_patient(
    patient: dict,
    blueprint: PatientBlueprint | None = None,
) -> dict:
    """Populate patient['visits'][i]['medications'] in-place.

    Iterates over all visits that visit_generator already created and
    assigns the correct medication list to each one, preserving:
    - start_date continuity (never reset on continuation visits)
    - trajectory_event changes at adherence/addition/completion roles
    - post-discharge reconciliation at medication_reconciliation visits

    Args:
        patient:   Patient dict with visits already populated by visit_generator.
        blueprint: PatientBlueprint.  If None, looked up by patient_id.

    Returns:
        The same patient dict with medications populated.
    """
    if blueprint is None:
        pid = patient.get("patient_id", "")
        if pid not in BLUEPRINT_BY_ID:
            raise MedicationGenerationError(
                f"No blueprint found for patient_id='{pid}'."
            )
        blueprint = BLUEPRINT_BY_ID[pid]

    _validate_preconditions(patient, blueprint)

    # Track start_dates per medication across visits.
    # Key: medication_name → ISO date string of first appearance.
    active_start_dates: dict[str, str] = {}

    for visit_index, visit in enumerate(patient["visits"]):
        meds = build_medications_for_visit(
            patient=patient,
            blueprint=blueprint,
            visit=visit,
            visit_index=visit_index,
            active_medication_start_dates=active_start_dates,
        )
        visit["medications"] = meds

    return patient


def build_medications_for_visit(
    patient: dict,
    blueprint: PatientBlueprint,
    visit: dict,
    visit_index: int,
    active_medication_start_dates: dict[str, str],
) -> list[MedicationRecord]:
    """Build the medication list for one visit.

    Mutates active_medication_start_dates in-place as new medications
    appear, so that subsequent calls receive the correct persistent
    start_date for each already-seen medication.

    Args:
        patient:                      Full patient dict (used for patient_id).
        blueprint:                    PatientBlueprint for this patient.
        visit:                        Visit dict from visit_generator.
        visit_index:                  0-based index of this visit.
        active_medication_start_dates: Mutable dict tracking first appearance date.

    Returns:
        List of medication record dicts for this visit.
    """
    visit_role = visit["visit_role"]
    visit_date = visit["visit_date"]
    patient_id = patient["patient_id"]

    # Determine which medications are active at this visit.
    active_names = _resolve_active_medications(blueprint, visit_index, visit_role)

    records: list[MedicationRecord] = []

    for med_name in active_names:
        status, trajectory, reason = determine_medication_status_and_trajectory(
            medication_name=med_name,
            blueprint=blueprint,
            visit=visit,
            visit_index=visit_index,
            active_medication_start_dates=active_medication_start_dates,
        )

        # Record start_date on first appearance.
        if med_name not in active_medication_start_dates:
            active_medication_start_dates[med_name] = visit_date

        start_date = active_medication_start_dates[med_name]
        stop_date  = visit_date if status == "completed" else None

        record = build_medication_record(
            medication_name=med_name,
            visit_date=visit_date,
            start_date=start_date,
            medication_status=status,
            trajectory_event=trajectory,
            reason=reason,
        )

        _validate_medication_record(record, patient_id, visit_index)
        records.append(record)

    return records


def build_medication_record(
    medication_name: str,
    visit_date: str,
    start_date: str,
    medication_status: str,
    trajectory_event: str,
    reason: str | None = None,
) -> MedicationRecord:
    """Construct a single validated medication record dict.

    Args:
        medication_name:    Must be in MEDICATION_NAMES.
        visit_date:         ISO date of the current visit (informational only).
        start_date:         ISO date of first documented start.
        medication_status:  From MEDICATION_STATUS enum.
        trajectory_event:   From MEDICATION_TRAJECTORY_EVENTS enum.
        reason:             Optional retrieval-useful documentation string.

    Returns:
        Medication record dict matching REQUIRED_MEDICATION_FIELDS.
    """
    profile = medication_profile(medication_name)

    record: MedicationRecord = {
        "medication_name":  medication_name,
        "medication_class": profile["medication_class"],
        "dose":             profile["default_dose"],
        "frequency":        profile["frequency"],
        "route":            profile["route"],
        "start_date":       start_date,
        "stop_date":        None if medication_status != "completed" else visit_date,
        "medication_status": medication_status,
        "trajectory_event":  trajectory_event,
    }

    if reason is not None:
        record["reason"] = reason

    return record


def determine_medication_status_and_trajectory(
    medication_name: str,
    blueprint: PatientBlueprint,
    visit: dict,
    visit_index: int,
    active_medication_start_dates: dict[str, str],
) -> tuple[str, str, str | None]:
    """Return (medication_status, trajectory_event, reason | None) for one med/visit.

    Logic applied in priority order:

    1. Reconciliation visit  → continued + post_discharge_reconciliation
    2. Completion visit (short-course meds that appear in completed_medications)
                             → completed  + course_completed
    3. Addition visit (added meds first appearing here)
                             → added      + second_medication_added
    4. Adherence visit (initial meds at partial/poor_adherence)
                             → continued  + adherence_interruption
    5. Visit 0 for initial meds that have not been seen yet
                             → started    + simple_start_continue
    6. Default continuation  → continued  + simple_start_continue
    """
    visit_role = visit["visit_role"]
    is_initial   = medication_name in blueprint.initial_medications
    is_added     = medication_name in blueprint.added_medications
    is_completed = medication_name in blueprint.completed_medications
    first_time   = medication_name not in active_medication_start_dates

    # --- 1. Reconciliation visit -------------------------------------------
    if visit_role in _RECONCILIATION_ROLES:
        return (
            "continued",
            "post_discharge_reconciliation",
            "Medication list was reviewed during post-discharge reconciliation.",
        )

    # --- 2. Short-course completion ----------------------------------------
    if is_completed and visit_role in _COMPLETION_ROLES:
        med_label = medication_name
        return (
            "completed",
            "course_completed",
            f"{med_label} short course was documented as completed at follow-up.",
        )

    # --- 3. Added medication first appearing at an addition visit ----------
    if is_added and visit_role in _ADDITION_ROLES and first_time:
        conditions_str = _format_conditions(blueprint.conditions)
        primary = blueprint.initial_medications[0] if blueprint.initial_medications else "existing therapy"
        return (
            "added",
            "second_medication_added",
            (
                f"{medication_name} was added for {conditions_str} "
                f"during the documented visit; {primary} continued."
            ),
        )

    # --- 4. Adherence interruption — only for the condition-targeted medication ---
    if (
        is_initial
        and visit_role in _ADHERENCE_ROLES
        and _is_adherence_target_medication(medication_name, blueprint)
    ):
        reason = _adherence_reason(medication_name, blueprint)
        return ("continued", "adherence_interruption", reason)

    # --- 5. First visit for initial medications ---------------------------
    if is_initial and first_time:
        return ("started", "simple_start_continue", None)

    # --- 6. Default: continuation -----------------------------------------
    return ("continued", "simple_start_continue", None)


def medication_profile(medication_name: str) -> dict[str, str]:
    """Return the whitelisted profile dict for a medication name.

    Uses MEDICATION_WHITELIST from constants as the authoritative source.

    Raises:
        MedicationGenerationError: if medication_name is not in the whitelist.
    """
    if medication_name not in MEDICATION_WHITELIST:
        raise MedicationGenerationError(
            f"'{medication_name}' is not in MEDICATION_WHITELIST. "
            f"Only medications from the locked whitelist may be generated."
        )
    return MEDICATION_WHITELIST[medication_name]


# ---------------------------------------------------------------------------
# Backward-compatible aliases
# ---------------------------------------------------------------------------

def generate_medications(
    patient: dict,
    blueprint: PatientBlueprint | None = None,
) -> dict:
    """Backward-compatible alias for generate_medications_for_patient."""
    return generate_medications_for_patient(patient, blueprint)


def generate_medications_for_visit(
    *,
    blueprint: PatientBlueprint,
    visit_index: int,
    visit_date: str,
    visit_role: str,
    clinical_event: dict | None = None,
) -> list[MedicationRecord]:
    """Backward-compatible adapter for the old per-visit calling convention.

    The old medication_generator accepted a visit-by-visit call pattern where
    each visit was processed independently.  The new architecture accumulates
    start_dates across visits via generate_medications_for_patient.

    This adapter builds a minimal patient stub with a single visit so callers
    that have not yet migrated to generate_medications_for_patient can still
    get a valid medication list.  NOTE: start_date continuity across visits
    is NOT preserved when using this function; use generate_medications_for_patient
    for full pipeline generation.

    Parameters match the old signature for drop-in compatibility.
    """
    # Build a minimal patient stub with just the one visit needed.
    stub_patient: dict = {
        "patient_id": blueprint.patient_id,
        "visits": [{
            "visit_id":   f"STUB-{visit_index:03d}",
            "visit_date": visit_date,
            "visit_role": visit_role,
            "visit_type": "follow_up",
            "medications": [],
            "labs": [],
        }],
    }
    active_start_dates: dict[str, str] = {}
    return build_medications_for_visit(
        patient=stub_patient,
        blueprint=blueprint,
        visit=stub_patient["visits"][0],
        visit_index=visit_index,
        active_medication_start_dates=active_start_dates,
    )


def medication_has_change(medication: dict) -> bool:
    """Return True if the medication record represents a status change event.

    Useful for downstream metadata builders that need to set has_medication_change.
    """
    _CHANGE_STATUSES: frozenset[str] = frozenset({
        "started", "dose_adjusted", "temporarily_stopped",
        "restarted", "completed", "added", "stopped",
    })
    return str(medication.get("medication_status", "")) in _CHANGE_STATUSES


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _resolve_active_medications(
    blueprint: PatientBlueprint,
    visit_index: int,
    visit_role: str,
) -> list[str]:
    """Return the ordered list of medication names active at this visit.

    Rules:
    - Initial medications are active from visit 0 onward.
    - Added medications are active from their first addition visit onward.
      The addition visit is the first visit_index whose visit_role is in
      _ADDITION_ROLES, provided the blueprint lists the medication as added.
    - Completed medications are included on their completion visit (so the
      record can carry medication_status="completed"), then absent afterward.
    - Stopped medications are absent after their stop visit (not used in
      current 15-patient dataset, but the field is supported).

    Added medication timing:
      The generator scans from visit 0 up to the current visit_index to find
      the first _ADDITION_ROLES visit.  If such a visit exists at or before
      visit_index, the added medications are included.
    """
    active: list[str] = []

    # Initial medications are always active.
    active.extend(blueprint.initial_medications)

    # Added medications: include if an addition visit has been reached.
    if blueprint.added_medications:
        addition_visit_index = _find_addition_visit_index(blueprint)
        if addition_visit_index is not None and visit_index >= addition_visit_index:
            active.extend(blueprint.added_medications)

    # Completed medications: include on the completion visit itself, then remove.
    # (build_medications_for_visit will mark them as completed on that visit.)
    if blueprint.completed_medications:
        completion_index = _find_completion_visit_index(blueprint)
        if completion_index is not None:
            for med in blueprint.completed_medications:
                if med not in active:
                    # Include only up to and including the completion visit.
                    if visit_index <= completion_index:
                        active.append(med)
                # If already in active (also in initial_medications), it will be
                # marked completed by determine_medication_status_and_trajectory.

    return active


def _find_addition_visit_index(blueprint: PatientBlueprint) -> int | None:
    """Return 0-based index of the first visit where added medications appear.

    Scans blueprint.visit_roles for the first role in _ADDITION_ROLES.
    Returns None if no such role exists (shouldn't happen in a valid blueprint,
    but fails gracefully).
    """
    for idx, role in enumerate(blueprint.visit_roles):
        if role in _ADDITION_ROLES:
            return idx
    return None


def _find_completion_visit_index(blueprint: PatientBlueprint) -> int | None:
    """Return 0-based index of the first visit where medications are completed."""
    for idx, role in enumerate(blueprint.visit_roles):
        if role in _COMPLETION_ROLES:
            return idx
    return None


def _is_adherence_target_medication(
    medication_name: str,
    blueprint: PatientBlueprint,
) -> bool:
    """Return True if this medication is the documented adherence target.

    Adherence issues in the 15-patient dataset are always condition-specific:
    - T2DM patients miss Metformin doses (not their HTN medication).
    - IDA patients miss Ferrous sulfate doses.

    Any other initial medication at an adherence visit (e.g. Amlodipine for HTN
    in PAT-CHR-001) should continue with simple_start_continue — the story only
    documents adherence problems with the primary disease-management medication.

    If a new blueprint story requires a different adherence target, extend this
    function with the appropriate condition → medication mapping.
    """
    if "T2DM" in blueprint.conditions and medication_name == "Metformin":
        return True
    if "IDA" in blueprint.conditions and medication_name == "Ferrous sulfate":
        return True
    return False


def _adherence_reason(medication_name: str, blueprint: PatientBlueprint) -> str:
    """Build a retrieval-useful reason string for adherence visits."""
    conditions_str = _format_conditions(blueprint.conditions)
    return (
        f"Patient reported missed {medication_name} doses "
        f"during {conditions_str} follow-up."
    )


# R2: _format_conditions removed — now imported from generators._generator_utils.


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def _validate_preconditions(patient: dict, blueprint: PatientBlueprint) -> None:
    """Lightweight pre-flight check before iterating visits."""
    pid = patient.get("patient_id", "")
    if pid != blueprint.patient_id:
        raise MedicationGenerationError(
            f"patient_id mismatch: patient has '{pid}', "
            f"blueprint has '{blueprint.patient_id}'."
        )
    if not patient.get("visits"):
        raise MedicationGenerationError(
            f"{pid}: patient has no visits. "
            "Run visit_generator.generate_visits_for_patient first."
        )


def _validate_medication_record(
    record: MedicationRecord,
    patient_id: str,
    visit_index: int,
) -> None:
    """Check one medication record against schema and safety rules."""
    label = f"{patient_id}.visit[{visit_index + 1}].medication[{record.get('medication_name', '?')}]"

    # Required fields present.
    missing = [f for f in REQUIRED_MEDICATION_FIELDS if f not in record]
    if missing:
        raise MedicationGenerationError(f"{label}: missing required fields: {missing}")

    med_name = record["medication_name"]

    # Medication in whitelist.
    if med_name not in MEDICATION_NAMES:
        raise MedicationGenerationError(
            f"{label}: '{med_name}' is not in MEDICATION_NAMES."
        )

    # Route enum.
    if record["route"] not in ROUTES:
        raise MedicationGenerationError(
            f"{label}: route '{record['route']}' not in ROUTES."
        )

    # Frequency enum.
    if record["frequency"] not in FREQUENCIES:
        raise MedicationGenerationError(
            f"{label}: frequency '{record['frequency']}' not in FREQUENCIES."
        )

    # Status enum.
    if record["medication_status"] not in MEDICATION_STATUS:
        raise MedicationGenerationError(
            f"{label}: medication_status '{record['medication_status']}' "
            "not in MEDICATION_STATUS."
        )

    # Trajectory enum.
    if record["trajectory_event"] not in MEDICATION_TRAJECTORY_EVENTS:
        raise MedicationGenerationError(
            f"{label}: trajectory_event '{record['trajectory_event']}' "
            "not in MEDICATION_TRAJECTORY_EVENTS."
        )

    # start_date non-empty and valid format.
    if not record.get("start_date"):
        raise MedicationGenerationError(f"{label}: start_date is empty.")
    if not re.fullmatch(DATE_REGEX, str(record["start_date"])):
        raise MedicationGenerationError(
            f"{label}: start_date '{record['start_date']}' does not match "
            f"DATE_REGEX '{DATE_REGEX}'."
        )

    # stop_date None or valid format.
    if record["stop_date"] is not None:
        if not re.fullmatch(DATE_REGEX, str(record["stop_date"])):
            raise MedicationGenerationError(
                f"{label}: stop_date '{record['stop_date']}' does not match "
                f"DATE_REGEX '{DATE_REGEX}'."
            )

    # Completed medications must use course_completed trajectory.
    if record["medication_status"] == "completed":
        if record["trajectory_event"] != "course_completed":
            raise MedicationGenerationError(
                f"{label}: status='completed' but trajectory_event="
                f"'{record['trajectory_event']}' (expected 'course_completed')."
            )
        # Only short-course medications may carry completed status.
        if med_name not in SHORT_COURSE_MEDICATIONS:
            raise MedicationGenerationError(
                f"{label}: medication_status='completed' is only allowed for "
                f"short-course medications {SHORT_COURSE_MEDICATIONS}; "
                f"'{med_name}' is not in that list."
            )

    # No BP fields anywhere in the record.
    _bp_keys = {"bp", "blood_pressure", "bp_systolic", "bp_diastolic",
                "systolic", "diastolic", "sbp", "dbp"}
    for key in record:
        if key.lower() in _bp_keys:
            raise MedicationGenerationError(
                f"{label}: BP field '{key}' must not appear in medication records."
            )
