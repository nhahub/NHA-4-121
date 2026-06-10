"""
config/patient_blueprints.py

Defines all 15 curated patient blueprints for the v1.7 Lite dataset.

PURPOSE
-------
This file is the single source of design intent for every synthetic patient.
Generators read blueprints to produce deterministic, diverse, retrieval-optimised
patient records.  No medical facts are generated here — only structural intent.

USAGE CONTRACT
--------------
* Consumed ONLY by generator modules (patient_generator, visit_generator,
  medication_generator, lab_generator, allergy_generator).
* Do NOT import from validators, SOAP, chunker, or ingestion layers.
  Those layers must read the generated patient JSON, not blueprints.
* Generators must use structured fields (initial_medications, added_medications,
  etc.) for deterministic logic.  The prose `medication_arc` field is
  documentation only — generators must NOT parse it.

DESIGN RULES (verified at import by _verify_blueprints)
---------------------------------------------------------
* Exactly 15 patients: 1 normal, 9 moderate, 5 chronic.
* Every retrieval_signature is globally unique.
* No two patients sharing a primary condition share both
  semantic_focus AND timeline_pattern (V12 rule).
* Every patient has 3–5 retrieval_intent_tags from constants.
* visit_roles length equals visit_count.
* Allergens never conflict with any medication in any structured field.
* CKD appears only in chronic tier with T2DM + HTN; max 2 CKD patients.
* All string values match locked enums in config/constants.py exactly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Blueprint dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PatientBlueprint:
    """
    Complete specification for one synthetic patient.

    Frozen so generators cannot mutate blueprints at runtime.
    Fields either map directly to patient JSON fields or drive generation logic.

    MEDICATION FIELDS
    -----------------
    Generators use the four structured tuple fields below — NOT medication_arc prose.

    initial_medications   : present from visit 1 onwards.
    added_medications     : introduced at a later visit (trajectory_event=second_medication_added
                            or medication_added; medication_status=added).
    completed_medications : short-course drugs finished during the story
                            (trajectory_event=course_completed; medication_status=completed).
    stopped_medications   : drugs permanently stopped (medication_status=stopped).

    medication_arc        : human-readable prose summary for documentation and
                            retrieval challenge query design only.
    """

    # --- identity -----------------------------------------------------------
    patient_id: str
    tier: str                            # "normal" | "moderate" | "chronic"
    sex: str                             # "male" | "female"
    conditions: tuple[str, ...]          # locked condition enums from constants

    # --- story / retrieval identity -----------------------------------------
    story_arc: str                       # short snake_case narrative label
    semantic_focus: str                  # from SEMANTIC_FOCUS enum
    timeline_pattern: str                # from TIMELINE_PATTERNS enum
    soap_style: str                      # from SOAP_STYLES enum

    # --- retrieval fingerprint ----------------------------------------------
    retrieval_signature: str             # validation-only pipe-joined fingerprint
    retrieval_intent_tags: tuple[str, ...]    # 3–5 tags from RETRIEVAL_INTENT_TAGS
    primary_retrieval_targets: tuple[str, ...]  # from PRIMARY_RETRIEVAL_TARGETS

    # --- visit design -------------------------------------------------------
    visit_count: int
    # One visit_role per visit in chronological order; from VISIT_ROLES enum.
    visit_roles: tuple[str, ...]

    # --- lab design ---------------------------------------------------------
    # Lab types present across this patient's visits; from LAB_TYPES enum.
    # Drives lab_generator selection logic.
    lab_focus: tuple[str, ...]

    # --- medication design (structured — generators use these) --------------
    # Medications present from visit 1.
    initial_medications: tuple[str, ...]
    # Medications introduced at a later visit.
    added_medications: tuple[str, ...] = ()
    # Short-course medications finished within the story arc.
    completed_medications: tuple[str, ...] = ()
    # Medications permanently stopped (rare in this dataset).
    stopped_medications: tuple[str, ...] = ()

    # --- medication arc (documentation only — do NOT parse in generators) ---
    medication_arc: str = ""

    # --- allergy design -----------------------------------------------------
    # None → no allergy for this patient.
    # Allergens are not required to be globally unique; patient-scoped
    # retrieval is the safety guarantee, not allergen uniqueness.
    # Allergen must come from SAFE_ALLERGEN_POOL and must not match any
    # medication name in any structured medication field (V2 pre-check).
    allergen: Optional[str] = None

    # --- safe distractor ----------------------------------------------------
    # 0-based index of the visit that receives a safe distractor, if any.
    # None → no distractor.  distractor_type from SAFE_DISTRACTORS enum.
    distractor_visit_index: Optional[int] = None
    distractor_type: Optional[str] = None

    # --- retrieval notes (documentation only) ------------------------------
    # Explains expected retrieval behaviour for challenge query design.
    # Not stored in generated JSON.
    retrieval_notes: str = ""


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _sig(*parts: str) -> str:
    """Join parts with '|' to form a retrieval_signature string."""
    return "|".join(parts)


# ---------------------------------------------------------------------------
# 15 Patient Blueprints
# ---------------------------------------------------------------------------
# Order: PAT-NRM-001, PAT-MOD-001..009, PAT-CHR-001..005
#
# V12 pre-verified by eye and by _verify_blueprints() below:
#   - all retrieval_signature values unique
#   - no two condition-overlapping patients share semantic_focus+timeline_pattern
# ---------------------------------------------------------------------------

# ── PAT-NRM-001 ─────────────────────────────────────────────────────────────
# Normal tier · Acute_URTI · 2 visits
# Story: acute illness → recovery confirmed.
# Retrieval value: clean negative case (no chronic disease, no labs, no allergy).
# Tests short-course medication completion arc.
PAT_NRM_001 = PatientBlueprint(
    patient_id="PAT-NRM-001",
    tier="normal",
    sex="male",
    conditions=("Acute_URTI",),

    story_arc="acute_urti_recovery",
    semantic_focus="recovery",
    timeline_pattern="delayed_followup",
    soap_style="concise",

    retrieval_signature=_sig("Acute_URTI", "Paracetamol", "recovery",
                             "delayed_followup", "acute"),

    retrieval_intent_tags=(
        "medication_query",
        "acute_recovery",
        "symptom_control_query",
    ),
    primary_retrieval_targets=(
        "medication_query",
        "symptom_control_query",
    ),

    visit_count=2,
    visit_roles=(
        "acute_treatment_started",
        "recovery_confirmed",
    ),

    lab_focus=(),

    initial_medications=("Paracetamol",),
    completed_medications=("Paracetamol",),   # short course; finished at visit 2
    medication_arc=(
        "Paracetamol started at initial visit for symptomatic relief; "
        "marked as completed at recovery-confirmed follow-up visit."
        " [Generators: initial_medications started at visit 1; "
        "completed_medications trajectory_event=course_completed at visit 2.]"
    ),

    allergen=None,
    distractor_visit_index=None,

    retrieval_notes=(
        "Clean negative-retrieval case. "
        "Allergy queries → no results. "
        "Lab trend queries → no results. "
        "Medication query → Paracetamol prescription chunk (completed status). "
        "recovery_confirmed visit_role vocabulary is unique to this patient."
    ),
)


# ── PAT-MOD-001 ─────────────────────────────────────────────────────────────
# Moderate tier · T2DM · 3 visits
# Story: Metformin started → progressive HbA1c improvement.
# Retrieval value: clearest HbA1c downward trend; lab_improvement semantic_focus.
PAT_MOD_001 = PatientBlueprint(
    patient_id="PAT-MOD-001",
    tier="moderate",
    sex="female",
    conditions=("T2DM",),

    story_arc="t2dm_metformin_hba1c_improvement",
    semantic_focus="lab_improvement",
    timeline_pattern="regular_quarterly",
    soap_style="problem_oriented",

    retrieval_signature=_sig("T2DM", "Metformin", "lab_improvement",
                             "regular_quarterly", "HbA1c-FBG"),

    retrieval_intent_tags=(
        "diabetes_medication",
        "hba1c_trend",
        "metformin_response",
    ),
    primary_retrieval_targets=(
        "medication_query",
        "lab_trend_query",
    ),

    visit_count=3,
    visit_roles=(
        "initial_diagnosis",
        "lab_trend_review",
        "lab_trend_review",
    ),

    lab_focus=("HbA1c", "FBG"),

    initial_medications=("Metformin",),
    medication_arc=(
        "Metformin started at initial diagnosis; continued and dose maintained "
        "across all follow-ups as HbA1c improves progressively."
        " [Generators: Metformin trajectory_event=simple_start_continue all visits.]"
    ),

    allergen="Penicillin",
    distractor_visit_index=None,

    retrieval_notes=(
        "HbA1c trends downward across all three visits — strongest pure T2DM lab "
        "trend case. "
        "Allergy query → Penicillin allergy chunk. "
        "Distinct from PAT-MOD-009 (dual T2DM+GERD) and PAT-CHR-001 (escalation). "
        "semantic_focus=lab_improvement + timeline_pattern=regular_quarterly are "
        "unique among T2DM patients, satisfying V12."
    ),
)


# ── PAT-MOD-002 ─────────────────────────────────────────────────────────────
# Moderate tier · HTN · 3 visits
# Story: Amlodipine started → BP trending toward target.
# Retrieval value: BP queries must retrieve doctor_note chunks (BP is NOT in labs
# or metadata — it lives only in visit.vitals and SOAP objective text).
PAT_MOD_002 = PatientBlueprint(
    patient_id="PAT-MOD-002",
    tier="moderate",
    sex="male",
    conditions=("HTN",),

    story_arc="htn_amlodipine_bp_control",
    semantic_focus="symptom_control",
    timeline_pattern="regular_quarterly",
    soap_style="problem_oriented",

    retrieval_signature=_sig("HTN", "Amlodipine", "symptom_control",
                             "regular_quarterly", "BP-vitals"),

    retrieval_intent_tags=(
        "hypertension_control",
        "bp_followup",
        "medication_query",
    ),
    primary_retrieval_targets=(
        "medication_query",
        "symptom_control_query",
    ),

    visit_count=3,
    visit_roles=(
        "initial_diagnosis",
        "routine_follow_up",
        "symptom_control_review",
    ),

    # HTN-only patient: Creatinine NOT generated (no T2DM co-morbidity).
    lab_focus=(),

    initial_medications=("Amlodipine",),
    medication_arc=(
        "Amlodipine started at initial diagnosis; continued with BP trending "
        "toward target across quarterly follow-ups."
        " [Generators: Amlodipine trajectory_event=simple_start_continue all visits.]"
    ),

    allergen=None,
    distractor_visit_index=1,
    distractor_type="mild_headache",

    retrieval_notes=(
        "BP values in vitals and SOAP objective only — never labs or metadata. "
        "BP queries → doctor_note chunks. "
        "Mild headache distractor at visit 1 must not become a retrieval anchor. "
        "timeline_pattern=regular_quarterly shared with PAT-MOD-001 but "
        "semantic_focus=symptom_control is different — V12 satisfied."
    ),
)


# ── PAT-MOD-003 ─────────────────────────────────────────────────────────────
# Moderate tier · Asthma · 3 visits
# Story: Salbutamol → seasonal flare → Budesonide added for controller therapy.
# Retrieval value: inhaler_adjustment; Aspirin allergy safety-critical test.
PAT_MOD_003 = PatientBlueprint(
    patient_id="PAT-MOD-003",
    tier="moderate",
    sex="female",
    conditions=("Asthma",),

    story_arc="asthma_seasonal_inhaler_adjustment",
    semantic_focus="symptom_control",
    timeline_pattern="seasonal_exacerbation",
    soap_style="concise",

    retrieval_signature=_sig("Asthma", "Salbutamol-Budesonide", "symptom_control",
                             "seasonal_exacerbation", "inhaler"),

    retrieval_intent_tags=(
        "asthma_control",
        "seasonal_asthma",
        "inhaler_adjustment",
    ),
    primary_retrieval_targets=(
        "medication_query",
        "symptom_control_query",
    ),

    visit_count=3,
    visit_roles=(
        "initial_diagnosis",
        "symptom_flare",
        "symptom_control_review",
    ),

    lab_focus=(),

    initial_medications=("Salbutamol inhaler",),
    added_medications=("Budesonide inhaler",),    # added at symptom_flare visit
    medication_arc=(
        "Salbutamol inhaler as-needed from initial visit. "
        "Budesonide inhaler added at symptom_flare visit (visit 2) "
        "after seasonal worsening documented."
        " [Generators: Budesonide trajectory_event=second_medication_added at visit 2; "
        "medication_status=added.]"
    ),

    allergen="Aspirin",
    distractor_visit_index=None,

    retrieval_notes=(
        "Seasonal vocabulary ('seasonal worsening', 'high-pollen period', 'symptom flare') "
        "is semantically distinct from PAT-CHR-003 (Asthma+HTN emergency). "
        "Aspirin allergy is safety-critical: allergy query must return this chunk. "
        "Only moderate-tier patient with inhaled medications — prescription "
        "chunks very distinctive. "
        "semantic_focus=symptom_control shared with PAT-MOD-002 but "
        "timeline_pattern=seasonal_exacerbation is different — V12 satisfied."
    ),
)


# ── PAT-MOD-004 ─────────────────────────────────────────────────────────────
# Moderate tier · IDA · 2 visits
# Story: Ferrous sulfate started → delayed return with missed doses documented.
# Retrieval value: poor_adherence semantic_focus; Hemoglobin+Ferritin lab trend.
PAT_MOD_004 = PatientBlueprint(
    patient_id="PAT-MOD-004",
    tier="moderate",
    sex="female",
    conditions=("IDA",),

    story_arc="ida_ferrous_sulfate_poor_adherence",
    semantic_focus="poor_adherence",
    timeline_pattern="delayed_followup",
    soap_style="concise",

    retrieval_signature=_sig("IDA", "Ferrous-sulfate", "poor_adherence",
                             "delayed_followup", "Hemoglobin-Ferritin"),

    retrieval_intent_tags=(
        "ida_treatment",
        "ferrous_sulfate_adherence",
        "hemoglobin_trend",
    ),
    primary_retrieval_targets=(
        "medication_query",
        "lab_trend_query",
    ),

    visit_count=2,
    visit_roles=(
        "initial_diagnosis",
        "poor_adherence",
    ),

    lab_focus=("Hemoglobin", "Ferritin"),

    initial_medications=("Ferrous sulfate",),
    medication_arc=(
        "Ferrous sulfate started at initial diagnosis. "
        "At delayed follow-up (visit 2), patient reported missed doses — "
        "medication_status=continued, trajectory_event=adherence_interruption."
        " [Generators: adherence_interruption at visit 2; medication continued "
        "but adherence issue documented in clinical_event and SOAP.]"
    ),

    allergen="Sulfa",   # Sulfa ≠ Ferrous sulfate — V2 satisfied
    distractor_visit_index=1,
    distractor_type="mild_fatigue",

    retrieval_notes=(
        "Delayed follow-up gap (120 days) and missed-doses vocabulary distinguish "
        "this patient clearly. "
        "Adherence query must retrieve poor_adherence visit_role doctor_note. "
        "Sulfa allergy does not conflict with Ferrous sulfate (different substance). "
        "Mild fatigue distractor at visit 1 must not become a retrieval anchor."
    ),
)


# ── PAT-MOD-005 ─────────────────────────────────────────────────────────────
# Moderate tier · GERD · 2 visits
# Story: Omeprazole started → symptom improvement confirmed at delayed return.
# Retrieval value: GERD-specific vocabulary; clean no-lab, no-allergy negative case.
PAT_MOD_005 = PatientBlueprint(
    patient_id="PAT-MOD-005",
    tier="moderate",
    sex="male",
    conditions=("GERD",),

    story_arc="gerd_omeprazole_symptom_improvement",
    semantic_focus="symptom_control",
    timeline_pattern="delayed_followup",
    soap_style="concise",

    retrieval_signature=_sig("GERD", "Omeprazole", "symptom_control",
                             "delayed_followup", "GI-symptoms"),

    retrieval_intent_tags=(
        "gerd_symptom_control",
        "medication_query",
        "symptom_control_query",
    ),
    primary_retrieval_targets=(
        "medication_query",
        "symptom_control_query",
    ),

    visit_count=2,
    visit_roles=(
        "initial_diagnosis",
        "symptom_control_review",
    ),

    lab_focus=(),

    initial_medications=("Omeprazole",),
    medication_arc=(
        "Omeprazole started at initial diagnosis; continued at delayed follow-up "
        "with documented symptom improvement."
        " [Generators: Omeprazole trajectory_event=simple_start_continue both visits.]"
    ),

    allergen=None,
    distractor_visit_index=None,

    retrieval_notes=(
        "GERD vocabulary (reflux, heartburn, epigastric discomfort) is semantically "
        "distinct from diabetes, HTN, IDA vocabulary. "
        "semantic_focus=symptom_control shared with PAT-MOD-002/003 but "
        "conditions=GERD and timeline_pattern=delayed_followup make signature unique. "
        "No labs, no allergy → negative-retrieval case for both."
    ),
)


# ── PAT-MOD-006 ─────────────────────────────────────────────────────────────
# Moderate tier · Dyslipidemia · 3 visits
# Story: Atorvastatin started → progressive LDL reduction over regular quarterly visits.
# Retrieval value: only moderate patient with LDL lab; Atorvastatin is unambiguous.
PAT_MOD_006 = PatientBlueprint(
    patient_id="PAT-MOD-006",
    tier="moderate",
    sex="male",
    conditions=("Dyslipidemia",),

    story_arc="dyslipidemia_atorvastatin_ldl_improvement",
    semantic_focus="lab_improvement",
    timeline_pattern="regular_quarterly",
    soap_style="problem_oriented",

    retrieval_signature=_sig("Dyslipidemia", "Atorvastatin", "lab_improvement",
                             "regular_quarterly", "LDL"),

    retrieval_intent_tags=(
        "dyslipidemia_treatment",
        "ldl_trend",
        "atorvastatin_response",
    ),
    primary_retrieval_targets=(
        "medication_query",
        "lab_trend_query",
    ),

    visit_count=3,
    visit_roles=(
        "initial_diagnosis",
        "lab_trend_review",
        "lab_trend_review",
    ),

    lab_focus=("LDL",),

    initial_medications=("Atorvastatin",),
    medication_arc=(
        "Atorvastatin started at initial diagnosis; continued across quarterly "
        "reviews with progressive LDL reduction documented."
        " [Generators: trajectory_event=simple_start_continue all visits.]"
    ),

    allergen=None,
    distractor_visit_index=None,

    retrieval_notes=(
        "LDL is unique to this patient and PAT-CHR-004 in moderate tier. "
        "semantic_focus=lab_improvement shared with PAT-MOD-001 (T2DM) but "
        "conditions=Dyslipidemia and lab_focus=LDL keep signature unique — V12 satisfied."
    ),
)


# ── PAT-MOD-007 ─────────────────────────────────────────────────────────────
# Moderate tier · Allergic_Rhinitis · 2 visits
# Story: Cetirizine started → seasonal symptom reduction confirmed.
# Retrieval value: Latex allergy (unique allergen); seasonal vocabulary shared
# with PAT-MOD-003 to test patient-scoped filter robustness.
PAT_MOD_007 = PatientBlueprint(
    patient_id="PAT-MOD-007",
    tier="moderate",
    sex="female",
    conditions=("Allergic_Rhinitis",),

    story_arc="allergic_rhinitis_cetirizine_seasonal_control",
    semantic_focus="symptom_control",
    timeline_pattern="seasonal_exacerbation",
    soap_style="concise",

    retrieval_signature=_sig("Allergic_Rhinitis", "Cetirizine", "symptom_control",
                             "seasonal_exacerbation", "rhinitis-pollen"),

    retrieval_intent_tags=(
        "allergic_rhinitis_control",
        "cetirizine_response",
        # Intentionally shares 'seasonal_asthma' tag with PAT-MOD-003 to test
        # that patient-scoped retrieval prevents cross-patient contamination.
        "seasonal_asthma",
    ),
    primary_retrieval_targets=(
        "medication_query",
        "symptom_control_query",
        "allergy_query",
    ),

    visit_count=2,
    visit_roles=(
        "initial_diagnosis",
        "symptom_control_review",
    ),

    lab_focus=(),

    initial_medications=("Cetirizine",),
    medication_arc=(
        "Cetirizine started at initial diagnosis; continued at follow-up "
        "with documented seasonal symptom reduction."
        " [Generators: trajectory_event=simple_start_continue both visits.]"
    ),

    allergen="Latex",   # unique allergen in dataset; easy allergy retrieval case
    distractor_visit_index=None,

    retrieval_notes=(
        "Latex allergy is unique across the dataset — allergy query is unambiguous. "
        "Shared seasonal vocabulary with PAT-MOD-003 deliberately tests that "
        "patient_id filter prevents cross-patient retrieval. "
        "conditions=Allergic_Rhinitis and Cetirizine keep retrieval_signature unique."
    ),
)


# ── PAT-MOD-008 ─────────────────────────────────────────────────────────────
# Moderate tier · UTI · 2 visits
# Story: Nitrofurantoin short course started → course completed at follow-up.
# Retrieval value: unique semantic_focus=acute_treatment_completion; tests
# medication_status=completed and trajectory_event=course_completed.
PAT_MOD_008 = PatientBlueprint(
    patient_id="PAT-MOD-008",
    tier="moderate",
    sex="female",
    conditions=("UTI",),

    story_arc="uti_nitrofurantoin_course_completed",
    semantic_focus="acute_treatment_completion",
    timeline_pattern="delayed_followup",
    soap_style="concise",

    retrieval_signature=_sig("UTI", "Nitrofurantoin", "acute_treatment_completion",
                             "delayed_followup", "short-course"),

    retrieval_intent_tags=(
        "uti_treatment",
        "nitrofurantoin_completion",
        "medication_query",
    ),
    primary_retrieval_targets=(
        "medication_query",
        "symptom_control_query",
    ),

    visit_count=2,
    visit_roles=(
        "acute_treatment_started",
        "course_completed",
    ),

    lab_focus=(),

    initial_medications=("Nitrofurantoin",),
    completed_medications=("Nitrofurantoin",),   # short-course; finished at visit 2
    medication_arc=(
        "Nitrofurantoin started at acute treatment visit. "
        "Course completed and medication stopped at follow-up after symptom resolution."
        " [Generators: trajectory_event=course_completed at visit 2; "
        "medication_status=completed.]"
    ),

    allergen=None,
    distractor_visit_index=None,

    retrieval_notes=(
        "semantic_focus=acute_treatment_completion is unique in the dataset. "
        "course_completed visit_role appears only here → zero embedding collision. "
        "No labs, no allergy → negative case for both."
    ),
)


# ── PAT-MOD-009 ─────────────────────────────────────────────────────────────
# Moderate tier · T2DM + GERD · 3 visits
# Story: Both conditions managed together; irregular follow-up gaps; HbA1c monitored.
# Retrieval value: dual-condition vocabulary; tests that medication queries return
# BOTH Metformin and Omeprazole prescription chunks.
PAT_MOD_009 = PatientBlueprint(
    patient_id="PAT-MOD-009",
    tier="moderate",
    sex="male",
    conditions=("T2DM", "GERD"),

    story_arc="t2dm_gerd_dual_condition_irregular_management",
    semantic_focus="dual_condition_control",
    timeline_pattern="irregular_followup",
    soap_style="problem_oriented",

    retrieval_signature=_sig("T2DM-GERD", "Metformin-Omeprazole",
                             "dual_condition_control", "irregular_followup",
                             "HbA1c-GI"),

    retrieval_intent_tags=(
        "diabetes_medication",
        "gerd_symptom_control",
        "hba1c_trend",
    ),
    primary_retrieval_targets=(
        "medication_query",
        "lab_trend_query",
        "symptom_control_query",
    ),

    visit_count=3,
    visit_roles=(
        "initial_diagnosis",
        "routine_follow_up",
        "lab_trend_review",
    ),

    lab_focus=("HbA1c", "FBG"),

    initial_medications=("Metformin", "Omeprazole"),
    medication_arc=(
        "Both Metformin (T2DM) and Omeprazole (GERD) started at initial diagnosis. "
        "Both continued across irregular follow-ups — no changes to either."
        " [Generators: both trajectory_event=simple_start_continue all visits.]"
    ),

    allergen=None,
    distractor_visit_index=1,
    distractor_type="poor_sleep",

    retrieval_notes=(
        "Irregular follow-up gaps (0, 45, 170, 260 days) produce temporal vocabulary "
        "distinct from regular quarterly patients. "
        "dual_condition_control semantic_focus is unique among moderate-tier patients. "
        "T2DM shared with PAT-MOD-001 but semantic_focus and timeline_pattern differ "
        "— V12 satisfied. "
        "Medication query must return BOTH Metformin and Omeprazole chunks."
    ),
)


# ── PAT-CHR-001 ─────────────────────────────────────────────────────────────
# Chronic tier · T2DM + HTN · 5 visits
# Story: Metformin+Amlodipine → partial adherence → Glibenclamide added → stabilised.
# PRIMARY retrieval value: the medication escalation arc is the dataset's hardest
# medication-change retrieval scenario.
PAT_CHR_001 = PatientBlueprint(
    patient_id="PAT-CHR-001",
    tier="chronic",
    sex="male",
    conditions=("T2DM", "HTN"),

    story_arc="t2dm_htn_metformin_glibenclamide_escalation",
    semantic_focus="medication_escalation",
    timeline_pattern="irregular_followup",
    soap_style="problem_oriented",

    retrieval_signature=_sig("T2DM-HTN", "Metformin-Glibenclamide",
                             "medication_escalation", "irregular_followup",
                             "HbA1c-escalation"),

    retrieval_intent_tags=(
        "diabetes_escalation",
        "glibenclamide_added",
        "metformin_adherence",
        "missed_doses",
    ),
    primary_retrieval_targets=(
        "medication_query",
        "medication_change_query",
        "lab_trend_query",
    ),

    visit_count=5,
    visit_roles=(
        "initial_diagnosis",
        "routine_follow_up",
        "partial_adherence",        # visit 3: missed Metformin evening doses
        "second_medication_added",  # visit 4: Glibenclamide added
        "lab_trend_review",         # visit 5: stability review
    ),

    lab_focus=("HbA1c", "FBG"),

    initial_medications=("Metformin", "Amlodipine"),  # Amlodipine for HTN from visit 1
    added_medications=("Glibenclamide",),              # added at visit 4 (second_medication_added)
    medication_arc=(
        "Metformin and Amlodipine from initial diagnosis. "
        "Partial adherence (missed evening Metformin doses) documented at visit 3. "
        "Glibenclamide added at visit 4 after HbA1c remained persistently elevated. "
        "All three medications continued at visit 5."
        " [Generators: Metformin trajectory_event=adherence_interruption at visit 3; "
        "Glibenclamide trajectory_event=second_medication_added at visit 4, "
        "medication_status=added.]"
    ),

    allergen=None,
    distractor_visit_index=2,
    distractor_type="stress",

    retrieval_notes=(
        "Escalation arc: missed doses (visit 3) → persistent HbA1c → drug added (visit 4). "
        "Hard query: 'Did the patient miss doses before the second medication was added?' "
        "requires retrieving partial_adherence AND second_medication_added visit chunks. "
        "irregular_followup gaps (0,45,170,260,360) are temporally distinct from "
        "PAT-CHR-002 (regular_quarterly). "
        "medication_escalation semantic_focus is unique in the dataset."
    ),
)


# ── PAT-CHR-002 ─────────────────────────────────────────────────────────────
# Chronic tier · T2DM + HTN + CKD · 5 visits
# Story: CKD monitoring with regular Creatinine, HbA1c, and FBG tracking.
# PRIMARY retrieval value: strongest Creatinine trend in dataset; ckd_monitoring
# visit_role repeated across four visits.
PAT_CHR_002 = PatientBlueprint(
    patient_id="PAT-CHR-002",
    tier="chronic",
    sex="female",
    conditions=("T2DM", "HTN", "CKD"),

    story_arc="t2dm_htn_ckd_creatinine_monitoring",
    semantic_focus="ckd_monitoring",
    timeline_pattern="regular_quarterly",
    soap_style="timeline_oriented",

    retrieval_signature=_sig("T2DM-HTN-CKD", "Metformin-Losartan",
                             "ckd_monitoring", "regular_quarterly",
                             "Creatinine-HbA1c"),

    retrieval_intent_tags=(
        "ckd_monitoring",
        "creatinine_trend",
        "hypertension_control",
        "diabetes_medication",
    ),
    primary_retrieval_targets=(
        "medication_query",
        "lab_trend_query",
        "timeline_query",
    ),

    visit_count=5,
    visit_roles=(
        "initial_diagnosis",
        "ckd_monitoring",
        "ckd_monitoring",
        "ckd_monitoring",
        "lab_trend_review",
    ),

    lab_focus=("HbA1c", "FBG", "Creatinine"),

    initial_medications=("Metformin", "Losartan"),   # Losartan for HTN + nephroprotection
    medication_arc=(
        "Metformin started for T2DM; Losartan started for HTN and nephroprotection. "
        "Both continued unchanged across all five quarterly CKD monitoring visits."
        " [Generators: trajectory_event=simple_start_continue all visits for both.]"
    ),

    # Penicillin shared with PAT-MOD-001; patient-scoped retrieval is the safety
    # mechanism — allergy allergens are NOT required to be globally unique.
    allergen="Penicillin",
    distractor_visit_index=None,

    retrieval_notes=(
        "CKD rule satisfied: T2DM + HTN + chronic tier. "
        "One of exactly two CKD patients. "
        "Creatinine across 5 visits → strongest lab_trend test. "
        "Penicillin allergy shared with PAT-MOD-001 — patient_id filter must prevent "
        "cross-patient allergy contamination. "
        "ckd_monitoring visit_role (4×) tests date-based chunk separation."
    ),
)


# ── PAT-CHR-003 ─────────────────────────────────────────────────────────────
# Chronic tier · Asthma + HTN · 5 visits
# Story: seasonal symptom flare → emergency exacerbation → post-exacerbation
# stabilisation (outpatient).
#
# IMPORTANT DISTINCTION FROM PAT-CHR-005:
#   PAT-CHR-003 has an OUTPATIENT emergency visit (visit_type=emergency,
#   visit_role=emergency_exacerbation).  This is NOT an inpatient hospitalisation.
#   Post-emergency follow-up is called post-exacerbation stabilisation.
#   True inpatient hospitalisation language ("admission", "discharge summary",
#   "post-discharge") belongs exclusively to PAT-CHR-005.
#
# semantic_focus=hospitalization_recovery is kept because this value is defined
# in constants.SEMANTIC_FOCUS and the emergency→recovery arc semantically fits,
# but retrieval_notes and SOAP must use OUTPATIENT emergency language only.
PAT_CHR_003 = PatientBlueprint(
    patient_id="PAT-CHR-003",
    tier="chronic",
    sex="female",
    conditions=("Asthma", "HTN"),

    story_arc="asthma_htn_emergency_exacerbation_outpatient_recovery",
    semantic_focus="hospitalization_recovery",   # kept for enum compatibility;
                                                 # represents emergency→recovery arc
    timeline_pattern="seasonal_exacerbation",
    soap_style="timeline_oriented",

    retrieval_signature=_sig("Asthma-HTN", "Salbutamol-Budesonide-Amlodipine",
                             "hospitalization_recovery", "seasonal_exacerbation",
                             "emergency-stabilisation"),

    retrieval_intent_tags=(
        "seasonal_asthma",
        "asthma_control",
        "hypertension_control",
        "hospitalization_recovery",
    ),
    primary_retrieval_targets=(
        "medication_query",
        "symptom_control_query",
        "hospitalization_query",
    ),

    visit_count=5,
    visit_roles=(
        "initial_diagnosis",
        "symptom_flare",
        "emergency_exacerbation",         # outpatient emergency visit
        "post_discharge_stabilization",   # post-exacerbation follow-up (NOT inpatient discharge)
        "symptom_control_review",
    ),

    lab_focus=(),

    initial_medications=("Salbutamol inhaler", "Amlodipine"),
    added_medications=("Budesonide inhaler",),    # added at symptom_flare visit (visit 2)
    medication_arc=(
        "Salbutamol inhaler as-needed and Amlodipine from initial visit. "
        "Budesonide inhaler added at symptom_flare visit (visit 2). "
        "All medications reviewed and continued following emergency exacerbation."
        " [Generators: Budesonide trajectory_event=second_medication_added at visit 2. "
        "All meds continued at visits 3–5 with trajectory_event=simple_start_continue.]"
    ),

    allergen=None,
    distractor_visit_index=None,

    retrieval_notes=(
        "OUTPATIENT EMERGENCY — not inpatient hospitalisation. "
        "SOAP for visit 3 must use: 'emergency exacerbation', 'acute presentation', "
        "'emergency clinic attendance' — NOT 'admitted', 'discharge', 'inpatient'. "
        "SOAP for visit 4 must use: 'post-exacerbation review', 'returning after "
        "emergency visit', 'stabilisation following acute episode' — NOT 'post-discharge'. "
        "Inpatient hospitalisation language is reserved for PAT-CHR-005 only. "
        "emergency_exacerbation visit_role is unique in the dataset. "
        "Hard query: 'What was documented after the emergency visit?' must retrieve "
        "the post_discharge_stabilization (post-exacerbation) visit chunks."
    ),
)


# ── PAT-CHR-004 ─────────────────────────────────────────────────────────────
# Chronic tier · T2DM + Dyslipidemia · 5 visits
# Story: Both HbA1c and LDL monitored quarterly — dual lab downward trends.
# PRIMARY retrieval value: only patient with BOTH HbA1c and LDL lab focus;
# dual_lab_trend semantic_focus is unique in the dataset.
PAT_CHR_004 = PatientBlueprint(
    patient_id="PAT-CHR-004",
    tier="chronic",
    sex="male",
    conditions=("T2DM", "Dyslipidemia"),

    story_arc="t2dm_dyslipidemia_dual_lab_trend_monitoring",
    semantic_focus="dual_lab_trend",
    timeline_pattern="regular_quarterly",
    soap_style="timeline_oriented",

    retrieval_signature=_sig("T2DM-Dyslipidemia", "Metformin-Atorvastatin",
                             "dual_lab_trend", "regular_quarterly",
                             "HbA1c-LDL"),

    retrieval_intent_tags=(
        "dual_lab_trend",
        "hba1c_trend",
        "ldl_trend",
        "diabetes_medication",
    ),
    primary_retrieval_targets=(
        "medication_query",
        "lab_trend_query",
        "timeline_query",
    ),

    visit_count=5,
    visit_roles=(
        "initial_diagnosis",
        "lab_trend_review",
        "lab_trend_review",
        "lab_trend_review",
        "lab_trend_review",
    ),

    lab_focus=("HbA1c", "FBG", "LDL"),

    initial_medications=("Metformin", "Atorvastatin"),
    medication_arc=(
        "Metformin for T2DM and Atorvastatin for Dyslipidemia both started "
        "at initial diagnosis. Both continued unchanged across all quarterly visits."
        " [Generators: trajectory_event=simple_start_continue all visits for both.]"
    ),

    allergen="Ibuprofen",   # does not conflict with any whitelist medication
    distractor_visit_index=None,

    retrieval_notes=(
        "dual_lab_trend semantic_focus is unique in the dataset. "
        "Only patient with LDL in a chronic tier. "
        "HbA1c shared with PAT-MOD-001, PAT-MOD-009, PAT-CHR-001, PAT-CHR-002, "
        "PAT-CHR-005 — patient-scoped retrieval handles this cleanly. "
        "T2DM shared with PAT-CHR-001 (medication_escalation) and PAT-CHR-002 "
        "(ckd_monitoring) — semantic_focus=dual_lab_trend is unique, V12 satisfied."
    ),
)


# ── PAT-CHR-005 ─────────────────────────────────────────────────────────────
# Chronic tier · T2DM + HTN + CKD · 5 visits
# Story: CKD monitoring → inpatient hospitalisation → post-discharge stabilisation
# → medication reconciliation review.
#
# PRIMARY retrieval value: ONLY patient with visit_type=hospitalization,
# discharge_summary chunk type, and medication_reconciliation chunk type.
# Hardest retrieval scenario in the dataset.
#
# TRUE INPATIENT HOSPITALISATION — distinct from PAT-CHR-003 (outpatient emergency).
PAT_CHR_005 = PatientBlueprint(
    patient_id="PAT-CHR-005",
    tier="chronic",
    sex="male",
    conditions=("T2DM", "HTN", "CKD"),

    story_arc="t2dm_htn_ckd_hospitalisation_post_discharge_stabilisation",
    semantic_focus="hospitalization_recovery",
    timeline_pattern="post_hospitalization",
    soap_style="timeline_oriented",

    retrieval_signature=_sig("T2DM-HTN-CKD", "Metformin-Glibenclamide-Losartan",
                             "hospitalization_recovery", "post_hospitalization",
                             "hospitalisation-CKD"),

    retrieval_intent_tags=(
        "hospitalization_recovery",
        "post_discharge_stabilization",
        "medication_reconciliation",
        "ckd_monitoring",
        "creatinine_trend",
    ),
    primary_retrieval_targets=(
        "hospitalization_query",
        "post_discharge_query",
        "medication_query",
        "lab_trend_query",
    ),

    visit_count=5,
    visit_roles=(
        "initial_diagnosis",
        "ckd_monitoring",
        "hospitalization",               # inpatient admission; visit_type=hospitalization
        "post_discharge_stabilization",  # short interval after discharge (day 188)
        "medication_reconciliation",     # formal medication review at day 230
    ),

    lab_focus=("HbA1c", "FBG", "Creatinine"),

    initial_medications=("Metformin", "Losartan"),
    added_medications=("Glibenclamide",),    # added before hospitalisation (visit 2 or 3)
    medication_arc=(
        "Metformin and Losartan from initial diagnosis. "
        "Glibenclamide added at visit 2 (ckd_monitoring) due to poor glycaemic control. "
        "All three continued and reconciled post-discharge."
        " [Generators: Glibenclamide trajectory_event=second_medication_added at visit 2; "
        "Metformin+Losartan+Glibenclamide trajectory_event=post_discharge_reconciliation "
        "at visit 5 (medication_reconciliation).]"
    ),

    allergen=None,
    distractor_visit_index=None,

    retrieval_notes=(
        "TRUE INPATIENT HOSPITALISATION — use 'admitted', 'inpatient stay', "
        "'discharge', 'post-discharge' language for visits 3–5. "
        "Second and final CKD patient. "
        "post_hospitalization gaps: (0, 90, 180, 188, 230) — "
        "visit 4 at day 188 is the short-interval post-discharge review. "
        "Chunker must produce discharge_summary chunk for visit 3 AND "
        "medication_reconciliation chunk for visit 5. "
        "Hard query: 'What changed after hospitalisation?' needs "
        "discharge_summary + post_discharge_stabilization doctor_note. "
        "semantic_focus=hospitalization_recovery shared with PAT-CHR-003 but "
        "timeline_pattern=post_hospitalization is unique — V12 satisfied."
    ),
)


# ---------------------------------------------------------------------------
# Ordered registry — consumed by generators
# ---------------------------------------------------------------------------

ALL_BLUEPRINTS: tuple[PatientBlueprint, ...] = (
    PAT_NRM_001,
    PAT_MOD_001,
    PAT_MOD_002,
    PAT_MOD_003,
    PAT_MOD_004,
    PAT_MOD_005,
    PAT_MOD_006,
    PAT_MOD_007,
    PAT_MOD_008,
    PAT_MOD_009,
    PAT_CHR_001,
    PAT_CHR_002,
    PAT_CHR_003,
    PAT_CHR_004,
    PAT_CHR_005,
)

# Quick lookup by patient_id — used by generators.
BLUEPRINT_BY_ID: dict[str, PatientBlueprint] = {
    bp.patient_id: bp for bp in ALL_BLUEPRINTS
}


# ---------------------------------------------------------------------------
# Pilot subset (5 patients)
# Covers: 1 normal, 3 moderate conditions, 1 complex chronic.
# Used for fast development smoke-testing before running the full dataset.
# ---------------------------------------------------------------------------

PILOT_BLUEPRINT_IDS: tuple[str, ...] = (
    "PAT-NRM-001",
    "PAT-MOD-001",
    "PAT-MOD-002",
    "PAT-MOD-003",
    "PAT-CHR-005",
)

PILOT_BLUEPRINTS: tuple[PatientBlueprint, ...] = tuple(
    BLUEPRINT_BY_ID[pid] for pid in PILOT_BLUEPRINT_IDS
)


# ---------------------------------------------------------------------------
# Module-level integrity verification
#
# Runs at import time for fast feedback during development.
# Mirrors V12 validation logic without importing from validators/
# (avoids circular dependencies).
#
# Generator scripts also run validate_all explicitly at runtime.
# ---------------------------------------------------------------------------

def _verify_blueprints() -> None:
    """
    Verify all 20 blueprint integrity rules at import time.

    Raises AssertionError with a descriptive message on the first violation.
    """
    from config.constants import (  # noqa: PLC0415 — local import avoids circular dep
        TIERS,
        CONDITIONS,
        TIMELINE_PATTERNS,
        SOAP_STYLES,
        SEMANTIC_FOCUS,
        VISIT_ROLES,
        RETRIEVAL_INTENT_TAGS,
        PRIMARY_RETRIEVAL_TARGETS,
        LAB_TYPES,
        MEDICATION_NAMES,
        SAFE_ALLERGEN_POOL,
        MIN_RETRIEVAL_INTENT_TAGS,
        MAX_RETRIEVAL_INTENT_TAGS,
        EXPECTED_V17_LITE_PATIENT_COUNT,
        FINAL_PATIENT_DISTRIBUTION,
        SEX_VALUES,
    )

    # 1. Exactly 15 patients ------------------------------------------------
    assert len(ALL_BLUEPRINTS) == EXPECTED_V17_LITE_PATIENT_COUNT, (
        f"Expected {EXPECTED_V17_LITE_PATIENT_COUNT} blueprints, "
        f"found {len(ALL_BLUEPRINTS)}."
    )

    # 2. Tier distribution --------------------------------------------------
    tier_counts: dict[str, int] = {}
    for bp in ALL_BLUEPRINTS:
        tier_counts[bp.tier] = tier_counts.get(bp.tier, 0) + 1
    for tier, expected in FINAL_PATIENT_DISTRIBUTION.items():
        actual = tier_counts.get(tier, 0)
        assert actual == expected, (
            f"Tier '{tier}': expected {expected} patients, found {actual}."
        )

    # --- per-patient checks -------------------------------------------------
    seen_signatures: set[str] = set()
    seen_patient_ids: set[str] = set()

    for bp in ALL_BLUEPRINTS:
        pid = bp.patient_id

        # 3. Unique patient_id ----------------------------------------------
        assert pid not in seen_patient_ids, f"Duplicate patient_id: {pid}"
        seen_patient_ids.add(pid)

        # 4. Unique retrieval_signature -------------------------------------
        assert bp.retrieval_signature not in seen_signatures, (
            f"{pid}: duplicate retrieval_signature '{bp.retrieval_signature}'"
        )
        seen_signatures.add(bp.retrieval_signature)

        # 5. Valid tier -------------------------------------------------------
        assert bp.tier in TIERS, f"{pid}: tier '{bp.tier}' not in TIERS"

        # 6. Valid sex --------------------------------------------------------
        assert bp.sex in SEX_VALUES, f"{pid}: sex '{bp.sex}' not in SEX_VALUES"

        # 7. Valid conditions -------------------------------------------------
        assert len(bp.conditions) > 0, f"{pid}: conditions tuple is empty"
        for c in bp.conditions:
            assert c in CONDITIONS, (
                f"{pid}: condition '{c}' not in CONDITIONS"
            )

        # 8. Valid semantic_focus ---------------------------------------------
        assert bp.semantic_focus in SEMANTIC_FOCUS, (
            f"{pid}: semantic_focus '{bp.semantic_focus}' not in SEMANTIC_FOCUS"
        )

        # 9. Valid timeline_pattern -------------------------------------------
        assert bp.timeline_pattern in TIMELINE_PATTERNS, (
            f"{pid}: timeline_pattern '{bp.timeline_pattern}' not in TIMELINE_PATTERNS"
        )

        # 10. Valid soap_style ------------------------------------------------
        assert bp.soap_style in SOAP_STYLES, (
            f"{pid}: soap_style '{bp.soap_style}' not in SOAP_STYLES"
        )

        # 11. retrieval_intent_tags count -------------------------------------
        n_tags = len(bp.retrieval_intent_tags)
        assert MIN_RETRIEVAL_INTENT_TAGS <= n_tags <= MAX_RETRIEVAL_INTENT_TAGS, (
            f"{pid}: retrieval_intent_tags count {n_tags} out of range "
            f"[{MIN_RETRIEVAL_INTENT_TAGS}, {MAX_RETRIEVAL_INTENT_TAGS}]"
        )

        # 12. All retrieval_intent_tags valid ---------------------------------
        for tag in bp.retrieval_intent_tags:
            assert tag in RETRIEVAL_INTENT_TAGS, (
                f"{pid}: retrieval_intent_tag '{tag}' not in RETRIEVAL_INTENT_TAGS"
            )

        # 13. Valid primary_retrieval_targets ----------------------------------
        assert len(bp.primary_retrieval_targets) > 0, (
            f"{pid}: primary_retrieval_targets is empty"
        )
        for tgt in bp.primary_retrieval_targets:
            assert tgt in PRIMARY_RETRIEVAL_TARGETS, (
                f"{pid}: primary_retrieval_target '{tgt}' not in PRIMARY_RETRIEVAL_TARGETS"
            )

        # 14. visit_count equals len(visit_roles) -----------------------------
        assert len(bp.visit_roles) == bp.visit_count, (
            f"{pid}: visit_count={bp.visit_count} but "
            f"len(visit_roles)={len(bp.visit_roles)}"
        )

        # 15. All visit_roles valid -------------------------------------------
        for role in bp.visit_roles:
            assert role in VISIT_ROLES, (
                f"{pid}: visit_role '{role}' not in VISIT_ROLES"
            )

        # 16. lab_focus values valid ------------------------------------------
        for lab in bp.lab_focus:
            assert lab in LAB_TYPES, (
                f"{pid}: lab_focus entry '{lab}' not in LAB_TYPES"
            )

        # 17. All structured medication fields valid --------------------------
        all_medications: list[str] = []
        for field_name, meds in (
            ("initial_medications", bp.initial_medications),
            ("added_medications", bp.added_medications),
            ("completed_medications", bp.completed_medications),
            ("stopped_medications", bp.stopped_medications),
        ):
            for med in meds:
                assert med in MEDICATION_NAMES, (
                    f"{pid}: {field_name} entry '{med}' not in MEDICATION_NAMES"
                )
                all_medications.append(med)

        # 18. No allergen conflicts with any structured medication field -------
        if bp.allergen is not None:
            assert bp.allergen in SAFE_ALLERGEN_POOL, (
                f"{pid}: allergen '{bp.allergen}' not in SAFE_ALLERGEN_POOL"
            )
            for med in all_medications:
                assert bp.allergen.lower() != med.lower(), (
                    f"{pid}: allergen '{bp.allergen}' conflicts with "
                    f"medication '{med}'"
                )

        # 19. CKD rule --------------------------------------------------------
        if "CKD" in bp.conditions:
            assert bp.tier == "chronic", (
                f"{pid}: CKD present but tier is '{bp.tier}' (must be 'chronic')"
            )
            assert "T2DM" in bp.conditions, (
                f"{pid}: CKD present but T2DM missing from conditions"
            )
            assert "HTN" in bp.conditions, (
                f"{pid}: CKD present but HTN missing from conditions"
            )

    # CKD patient count across dataset
    ckd_count = sum(1 for bp in ALL_BLUEPRINTS if "CKD" in bp.conditions)
    assert ckd_count <= 2, (
        f"CKD patient count {ckd_count} exceeds maximum of 2"
    )

    # 20. V12: no two condition-sharing patients may share semantic_focus
    #          AND timeline_pattern simultaneously.
    for i, bp_a in enumerate(ALL_BLUEPRINTS):
        for bp_b in ALL_BLUEPRINTS[i + 1:]:
            shared_conditions = set(bp_a.conditions) & set(bp_b.conditions)
            if shared_conditions:
                assert not (
                    bp_a.semantic_focus == bp_b.semantic_focus
                    and bp_a.timeline_pattern == bp_b.timeline_pattern
                ), (
                    f"V12 violation: {bp_a.patient_id} and {bp_b.patient_id} "
                    f"share condition(s) {shared_conditions} and both have "
                    f"semantic_focus='{bp_a.semantic_focus}' and "
                    f"timeline_pattern='{bp_a.timeline_pattern}'."
                )


# Run at import time.  Failures here indicate blueprint authoring errors
# that should be fixed before running any generator.
_verify_blueprints()
