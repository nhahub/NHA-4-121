"""
config/constants.py

Single source of truth for locked project constants.

This file intentionally contains no runtime side effects and no API calls.
Every generator, validator, SOAP utility, ingestion helper, RAG utility, and
script should import locked values from here instead of redefining enums locally.

v1.7 Lite focus:
- small curated 15-patient dataset,
- retrieval-oriented diversity fields,
- medication trajectory state,
- SOAP style control,
- minimal ChromaDB metadata contract,
- validation-friendly constants only.
"""

from __future__ import annotations

from typing import Final


# ---------------------------------------------------------------------
# Schema / project identity
# ---------------------------------------------------------------------

SCHEMA_VERSION: Final[str] = "1.0"
DATASET_VERSION: Final[str] = "v1.7-lite"
PROJECT_NAME: Final[str] = "AI-Based Clinical Record Summarization System"


# ---------------------------------------------------------------------
# Dataset generation modes
# ---------------------------------------------------------------------

DATASET_MODE_PILOT: Final[str] = "pilot"
DATASET_MODE_FULL: Final[str] = "full"
DATASET_MODE_V17_LITE: Final[str] = "v17_lite"

DEFAULT_DATASET_MODE: Final[str] = DATASET_MODE_V17_LITE
DATASET_RANDOM_SEED: Final[int] = 20260512


# ---------------------------------------------------------------------
# Locked clinical enums
# ---------------------------------------------------------------------

CONDITIONS: Final[tuple[str, ...]] = (
    "Acute_URTI",
    "T2DM",
    "HTN",
    "Asthma",
    "IDA",
    "GERD",
    "Dyslipidemia",
    "Allergic_Rhinitis",
    "UTI",
    "CKD",
)

CONDITION_DISPLAY_NAMES: Final[dict[str, str]] = {
    "Acute_URTI": "Acute upper respiratory tract infection",
    "T2DM": "Type 2 diabetes mellitus",
    "HTN": "Hypertension",
    "Asthma": "Asthma",
    "IDA": "Iron deficiency anemia",
    "GERD": "Gastroesophageal reflux disease",
    "Dyslipidemia": "Dyslipidemia",
    "Allergic_Rhinitis": "Allergic rhinitis",
    "UTI": "Urinary tract infection",
    "CKD": "Chronic kidney disease",
}

LAB_TYPES: Final[tuple[str, ...]] = (
    "HbA1c",
    "FBG",
    "Creatinine",
    "Hemoglobin",
    "Ferritin",
    "LDL",
)

VISIT_TYPES: Final[tuple[str, ...]] = (
    "initial",
    "follow_up",
    "emergency",
    "hospitalization",
)

FREQUENCIES: Final[tuple[str, ...]] = (
    "once_daily",
    "twice_daily",
    "as_needed",
)

ROUTES: Final[tuple[str, ...]] = (
    "oral",
    "inhaled",
)

FLAGS: Final[tuple[str, ...]] = (
    "NORMAL",
    "HIGH",
    "LOW",
)

SEVERITIES: Final[tuple[str, ...]] = (
    "mild",
    "moderate",
    "severe",
)

TIERS: Final[tuple[str, ...]] = (
    "normal",
    "moderate",
    "chronic",
)

SEX_VALUES: Final[tuple[str, ...]] = (
    "male",
    "female",
)


# ---------------------------------------------------------------------
# v1.7 Lite retrieval / diversity enums
# ---------------------------------------------------------------------

TIMELINE_PATTERNS: Final[tuple[str, ...]] = (
    "regular_quarterly",
    "delayed_followup",
    "irregular_followup",
    "seasonal_exacerbation",
    "post_hospitalization",
)

TIMELINE_GAP_DAYS: Final[dict[str, tuple[int, ...]]] = {
    "regular_quarterly": (0, 90, 180, 270, 360),
    "delayed_followup": (0, 120, 210),
    "irregular_followup": (0, 45, 170, 260, 360),
    "seasonal_exacerbation": (0, 75, 180, 270, 360),
    "post_hospitalization": (0, 90, 180, 188, 230),
}

SOAP_STYLES: Final[tuple[str, ...]] = (
    "concise",
    "problem_oriented",
    "timeline_oriented",
)

SEMANTIC_FOCUS: Final[tuple[str, ...]] = (
    "recovery",
    "lab_improvement",
    "poor_adherence",
    "medication_escalation",
    "symptom_control",
    "hospitalization_recovery",
    "ckd_monitoring",
    "dual_lab_trend",
    "dual_condition_control",
    "acute_treatment_completion",
)

VISIT_ROLES: Final[tuple[str, ...]] = (
    "initial_diagnosis",
    "baseline_assessment",
    "routine_follow_up",
    "partial_adherence",
    "poor_adherence",
    "lab_trend_review",
    "medication_started",
    "medication_continued",
    "dose_adjustment",
    "second_medication_added",
    "acute_treatment_started",
    "course_completed",
    "symptom_flare",
    "symptom_control_review",
    "emergency_exacerbation",
    "hospitalization",
    "post_discharge_stabilization",
    "ckd_monitoring",
    "medication_reconciliation",
    "recovery_confirmed",
)

CLINICAL_EVENT_TYPES: Final[tuple[str, ...]] = (
    "diagnosis_documented",
    "baseline_labs_reviewed",
    "lab_improvement",
    "lab_worsening",
    "adherence_issue",
    "medication_started",
    "medication_continued",
    "dose_adjustment",
    "medication_added",
    "short_course_completed",
    "symptom_flare",
    "symptom_improvement",
    "emergency_visit",
    "hospitalization",
    "post_discharge_review",
    "allergy_reviewed",
    "recovery_confirmed",
)

RETRIEVAL_INTENT_TAGS: Final[tuple[str, ...]] = (
    "medication_query",
    "symptom_control_query",
    "acute_recovery",
    "diabetes_medication",
    "hba1c_trend",
    "fbg_trend",
    "metformin_response",
    "metformin_adherence",
    "missed_doses",
    "diabetes_escalation",
    "glibenclamide_added",
    "hypertension_control",
    "bp_followup",
    "asthma_control",
    "seasonal_asthma",
    "inhaler_adjustment",
    "ida_treatment",
    "ferrous_sulfate_adherence",
    "hemoglobin_trend",
    "ferritin_trend",
    "gerd_symptom_control",
    "dyslipidemia_treatment",
    "ldl_trend",
    "atorvastatin_response",
    "allergic_rhinitis_control",
    "cetirizine_response",
    "uti_treatment",
    "nitrofurantoin_completion",
    "ckd_monitoring",
    "creatinine_trend",
    "dual_lab_trend",
    "hospitalization_recovery",
    "post_discharge_stabilization",
    "medication_reconciliation",
    "allergy_query",
)

PRIMARY_RETRIEVAL_TARGETS: Final[tuple[str, ...]] = (
    "medication_query",
    "lab_trend_query",
    "allergy_query",
    "timeline_query",
    "symptom_control_query",
    "hospitalization_query",
    "post_discharge_query",
    "medication_change_query",
)

RETRIEVAL_SIGNATURE_SEPARATOR: Final[str] = "|"
MIN_RETRIEVAL_INTENT_TAGS: Final[int] = 3
MAX_RETRIEVAL_INTENT_TAGS: Final[int] = 5


# ---------------------------------------------------------------------
# Source types / chunk types
# ---------------------------------------------------------------------

CORE_SOURCE_TYPES: Final[tuple[str, ...]] = (
    "doctor_note",
    "lab_result",
    "prescription",
    "allergy",
)

OPTIONAL_SOURCE_TYPES_V17_LITE: Final[tuple[str, ...]] = (
    "discharge_summary",
    "medication_reconciliation",
)

SOURCE_TYPES: Final[tuple[str, ...]] = CORE_SOURCE_TYPES + OPTIONAL_SOURCE_TYPES_V17_LITE


# ---------------------------------------------------------------------
# Minimal ChromaDB metadata contract
# ---------------------------------------------------------------------

MINIMAL_CHROMA_METADATA_FIELDS_V17_LITE: Final[tuple[str, ...]] = (
    "patient_id",
    "visit_id",
    "visit_date",
    "source_type",
    "conditions",
    "visit_type",
    "visit_role",
    "semantic_focus",
    "timeline_pattern",
)

OPTIONAL_CHROMA_METADATA_FIELDS_V17_LITE: Final[tuple[str, ...]] = (
    "has_medication_change",
    "has_hospitalization",
    "has_lab_trend",
)

FORBIDDEN_CHROMA_METADATA_FIELDS_V17_LITE: Final[tuple[str, ...]] = (
    "bp",
    "blood_pressure",
    "bp_systolic",
    "bp_diastolic",
    "systolic",
    "diastolic",
    "sbp",
    "dbp",
    "lab_value",
    "lab_numeric_value",
    "full_soap_text",
    "full_allergy_reaction",
    "retrieval_signature",
    "safe_distractor_text",
    "lifestyle_details",
    "synonym_choices",
    "narrative_density",
    "physician_style",
    "full_medication_dose_history",
)

CONDITIONS_METADATA_SEPARATOR: Final[str] = "|"


# ---------------------------------------------------------------------
# ID formats
# ---------------------------------------------------------------------

TIER_TO_ID_PREFIX: Final[dict[str, str]] = {
    "normal": "NRM",
    "moderate": "MOD",
    "chronic": "CHR",
}

ID_PREFIX_TO_TIER: Final[dict[str, str]] = {
    value: key for key, value in TIER_TO_ID_PREFIX.items()
}

PATIENT_ID_REGEX: Final[str] = r"^PAT-(NRM|MOD|CHR)-\d{3}$"
VISIT_ID_REGEX: Final[str] = r"^VST-(NRM|MOD|CHR)-\d{3}-\d{3}$"
DOCUMENT_ID_REGEX: Final[str] = r"^DOC-(NRM|MOD|CHR)-\d{3}-\d{3}$"
CHUNK_ID_REGEX: Final[str] = r"^VST-(NRM|MOD|CHR)-\d{3}-\d{3}-(doctor_note|lab_result|prescription|allergy|discharge_summary|medication_reconciliation)-\d{2}$"


# ---------------------------------------------------------------------
# Dataset distribution
# ---------------------------------------------------------------------

PILOT_PATIENT_DISTRIBUTION: Final[dict[str, int]] = {
    "normal": 2,
    "moderate": 2,
    "chronic": 1,
}

EXPECTED_PILOT_PATIENT_COUNT: Final[int] = 5

FINAL_PATIENT_DISTRIBUTION: Final[dict[str, int]] = {
    "normal": 1,
    "moderate": 9,
    "chronic": 5,
}

EXPECTED_FULL_PATIENT_COUNT: Final[int] = 15
EXPECTED_V17_LITE_PATIENT_COUNT: Final[int] = 15
EXPECTED_V17_LITE_VISIT_COUNT_APPROX: Final[int] = 49


# ---------------------------------------------------------------------
# Required schema fields
# ---------------------------------------------------------------------

REQUIRED_TOP_LEVEL_FIELDS: Final[tuple[str, ...]] = (
    "schema_version",
    "patient_id",
    "demographics",
    "conditions",
    "allergy_registry",
    "visits",
    "metadata",
)

REQUIRED_DEMOGRAPHICS_FIELDS: Final[tuple[str, ...]] = (
    "name",
    "date_of_birth",
    "sex",
)

FORBIDDEN_DEMOGRAPHICS_FIELDS: Final[tuple[str, ...]] = (
    "age",
)

REQUIRED_PATIENT_METADATA_FIELDS_V17_LITE: Final[tuple[str, ...]] = (
    "tier",
    "dataset_version",
    "story_arc",
    "timeline_pattern",
    "semantic_focus",
    "retrieval_signature",
    "retrieval_intent_tags",
    "soap_style",
    "primary_retrieval_targets",
)

REQUIRED_VISIT_FIELDS: Final[tuple[str, ...]] = (
    "visit_id",
    "visit_date",
    "visit_type",
    "attending_physician",
    "diagnoses",
    "vitals",
    "labs",
    "medications",
    "soap_note",
    "linked_documents",
    "prior_visit_id",
    "visit_role",
    "timeline_pattern",
    "timeline_gap_days",
    "clinical_event",
    "retrieval_context",
)

FORBIDDEN_VISIT_FIELDS: Final[tuple[str, ...]] = (
    "timeline_events",
)

REQUIRED_CLINICAL_EVENT_FIELDS: Final[tuple[str, ...]] = (
    "event_type",
    "event_label",
    "event_summary",
)

REQUIRED_RETRIEVAL_CONTEXT_FIELDS: Final[tuple[str, ...]] = (
    "semantic_focus",
    "retrieval_intent_tags",
)

REQUIRED_VITAL_FIELDS: Final[tuple[str, ...]] = (
    "bp_systolic",
    "bp_diastolic",
    "heart_rate",
    "weight_kg",
    "bmi",
)

REQUIRED_LAB_FIELDS: Final[tuple[str, ...]] = (
    "lab_type",
    "value",
    "unit",
    "reference_range",
    "flag",
)

REQUIRED_MEDICATION_FIELDS: Final[tuple[str, ...]] = (
    "medication_name",
    "medication_class",
    "dose",
    "frequency",
    "route",
    "start_date",
    "stop_date",
    "medication_status",
    "trajectory_event",
)

OPTIONAL_MEDICATION_FIELDS: Final[tuple[str, ...]] = (
    "reason",
)

REQUIRED_ALLERGY_FIELDS: Final[tuple[str, ...]] = (
    "allergen",
    "reaction",
    "severity",
    "recorded_date",
    "source_visit_id",
)

SOAP_SECTIONS: Final[tuple[str, ...]] = (
    "subjective",
    "objective",
    "assessment",
    "plan",
)


# ---------------------------------------------------------------------
# Date format
# ---------------------------------------------------------------------

DATE_FORMAT: Final[str] = "%Y-%m-%d"
DATE_REGEX: Final[str] = r"^\d{4}-\d{2}-\d{2}$"


# ---------------------------------------------------------------------
# Validation bounds
# ---------------------------------------------------------------------

VITAL_LIMITS: Final[dict[str, tuple[float, float]]] = {
    "bp_systolic": (70, 230),
    "bp_diastolic": (40, 140),
    "heart_rate": (30, 200),
    "bmi": (14, 55),
}

AGE_LIMITS: Final[tuple[int, int]] = (18, 80)
CKD_REQUIRED_CONDITIONS: Final[tuple[str, ...]] = ("T2DM", "HTN")
CKD_ALLOWED_TIER: Final[str] = "chronic"


# ---------------------------------------------------------------------
# Blood pressure forbidden terms
# ---------------------------------------------------------------------

BP_FORBIDDEN_LAB_TERMS: Final[tuple[str, ...]] = (
    "bp",
    "blood pressure",
    "blood_pressure",
    "systolic",
    "diastolic",
    "bp_systolic",
    "bp_diastolic",
    "sbp",
    "dbp",
)

BP_FORBIDDEN_METADATA_TERMS: Final[tuple[str, ...]] = BP_FORBIDDEN_LAB_TERMS


# ---------------------------------------------------------------------
# Medication whitelist and v1.7 Lite trajectory enums
# ---------------------------------------------------------------------

MEDICATION_STATUS: Final[tuple[str, ...]] = (
    "started",
    "continued",
    "dose_adjusted",
    "temporarily_stopped",
    "restarted",
    "completed",
    "added",
    "stopped",
)

MEDICATION_TRAJECTORY_EVENTS: Final[tuple[str, ...]] = (
    "simple_start_continue",
    "adherence_interruption",
    "dose_adjustment",
    "second_medication_added",
    "course_completed",
    "post_discharge_reconciliation",
)

MEDICATION_WHITELIST: Final[dict[str, dict[str, str]]] = {
    "Paracetamol": {
        "medication_class": "Analgesic/Antipyretic",
        "condition": "Acute_URTI",
        "default_dose": "500 mg",
        "frequency": "as_needed",
        "route": "oral",
    },
    "Metformin": {
        "medication_class": "Biguanide",
        "condition": "T2DM",
        "default_dose": "500 mg",
        "frequency": "twice_daily",
        "route": "oral",
    },
    "Glibenclamide": {
        "medication_class": "Sulfonylurea",
        "condition": "T2DM",
        "default_dose": "5 mg",
        "frequency": "once_daily",
        "route": "oral",
    },
    "Lisinopril": {
        "medication_class": "ACE Inhibitor",
        "condition": "HTN",
        "default_dose": "10 mg",
        "frequency": "once_daily",
        "route": "oral",
    },
    "Amlodipine": {
        "medication_class": "Calcium Channel Blocker",
        "condition": "HTN",
        "default_dose": "5 mg",
        "frequency": "once_daily",
        "route": "oral",
    },
    "Losartan": {
        "medication_class": "ARB",
        "condition": "HTN",
        "default_dose": "50 mg",
        "frequency": "once_daily",
        "route": "oral",
    },
    "Salbutamol inhaler": {
        "medication_class": "SABA",
        "condition": "Asthma",
        "default_dose": "100 mcg",
        "frequency": "as_needed",
        "route": "inhaled",
    },
    "Budesonide inhaler": {
        "medication_class": "ICS",
        "condition": "Asthma",
        "default_dose": "200 mcg",
        "frequency": "twice_daily",
        "route": "inhaled",
    },
    "Ferrous sulfate": {
        "medication_class": "Iron supplement",
        "condition": "IDA",
        "default_dose": "200 mg",
        "frequency": "twice_daily",
        "route": "oral",
    },
    "Omeprazole": {
        "medication_class": "PPI",
        "condition": "GERD",
        "default_dose": "20 mg",
        "frequency": "once_daily",
        "route": "oral",
    },
    "Atorvastatin": {
        "medication_class": "Statin",
        "condition": "Dyslipidemia",
        "default_dose": "20 mg",
        "frequency": "once_daily",
        "route": "oral",
    },
    "Cetirizine": {
        "medication_class": "Second-generation antihistamine",
        "condition": "Allergic_Rhinitis",
        "default_dose": "10 mg",
        "frequency": "once_daily",
        "route": "oral",
    },
    "Nitrofurantoin": {
        "medication_class": "Antibiotic",
        "condition": "UTI",
        "default_dose": "100 mg",
        "frequency": "twice_daily",
        "route": "oral",
    },
}

MEDICATION_NAMES: Final[tuple[str, ...]] = tuple(MEDICATION_WHITELIST.keys())
SHORT_COURSE_MEDICATIONS: Final[tuple[str, ...]] = (
    "Paracetamol",
    "Nitrofurantoin",
)

MEDICATION_CHANGE_STATUSES: Final[tuple[str, ...]] = (
    "started",
    "dose_adjusted",
    "temporarily_stopped",
    "restarted",
    "completed",
    "added",
    "stopped",
)


# ---------------------------------------------------------------------
# Lab metadata
# ---------------------------------------------------------------------

LAB_REFERENCE_RANGES: Final[dict[str, str]] = {
    "HbA1c": "4.0-5.6 %",
    "FBG": "70-99 mg/dL",
    "Creatinine": "0.6-1.2 mg/dL",
    "Hemoglobin": "12.0-16.0 g/dL",
    "Ferritin": "30-300 ng/mL",
    "LDL": "<100 mg/dL",
}

LAB_UNITS: Final[dict[str, str]] = {
    "HbA1c": "%",
    "FBG": "mg/dL",
    "Creatinine": "mg/dL",
    "Hemoglobin": "g/dL",
    "Ferritin": "ng/mL",
    "LDL": "mg/dL",
}

LAB_FOCUS_BY_CONDITION: Final[dict[str, tuple[str, ...]]] = {
    "T2DM": ("HbA1c", "FBG", "Creatinine"),
    "HTN": ("Creatinine",),
    "CKD": ("Creatinine",),
    "IDA": ("Hemoglobin", "Ferritin"),
    "Dyslipidemia": ("LDL",),
}


# ---------------------------------------------------------------------
# Safe distractor policy
# ---------------------------------------------------------------------

SAFE_DISTRACTORS: Final[tuple[str, ...]] = (
    "mild_fatigue",
    "stress",
    "poor_sleep",
    "diet_inconsistency",
    "mild_headache",
)

SAFE_DISTRACTOR_STATUS: Final[str] = "context_only"
MAX_SAFE_DISTRACTORS_PER_VISIT: Final[int] = 1


# ---------------------------------------------------------------------
# Deterministic patient identity pools
# ---------------------------------------------------------------------

MALE_PATIENT_NAMES: Final[tuple[str, ...]] = (
    "Omar Samir",
    "Karim Hassan",
    "Youssef Mahmoud",
    "Ahmed Nader",
    "Mostafa Adel",
    "Hassan Tarek",
    "Ali Fawzy",
    "Mahmoud Sherif",
    "Khaled Emad",
    "Tamer Yasser",
    "Ibrahim Hany",
    "Sherif Magdy",
    "Nabil Fouad",
    "Amr Salah",
    "Ziad Ashraf",
    "Mohamed Ashraf",
    "Fady Sameh",
    "Hussein Gamal",
)

FEMALE_PATIENT_NAMES: Final[tuple[str, ...]] = (
    "Mariam Adel",
    "Nour Ahmed",
    "Salma Mostafa",
    "Laila Hassan",
    "Hana Youssef",
    "Farah Mahmoud",
    "Nada Tarek",
    "Dina Samir",
    "Reem Khaled",
    "Aya Sherif",
    "Mona Fawzy",
    "Yasmin Hany",
    "Sara Nabil",
    "Rana Emad",
    "Jana Ahmed",
    "Mariam Tarek",
    "Nadine Mostafa",
    "Heba Samir",
)


# ---------------------------------------------------------------------
# Deterministic attending physicians
# ---------------------------------------------------------------------

ATTENDING_PHYSICIANS: Final[tuple[str, ...]] = (
    "Dr. Salma Nabil",
    "Dr. Ahmed Farid",
    "Dr. Laila Mostafa",
    "Dr. Hany Fawzy",
    "Dr. Mona Kareem",
    "Dr. Yasser Amin",
)


# ---------------------------------------------------------------------
# Deterministic disease archetype plans for 15-patient v1.7 Lite set
# ---------------------------------------------------------------------

NORMAL_ARCHETYPES: Final[dict[int, tuple[str, ...]]] = {
    1: ("Acute_URTI",),
}

MODERATE_ARCHETYPES: Final[dict[int, tuple[str, ...]]] = {
    1: ("T2DM",),
    2: ("HTN",),
    3: ("Asthma",),
    4: ("IDA",),
    5: ("GERD",),
    6: ("Dyslipidemia",),
    7: ("Allergic_Rhinitis",),
    8: ("UTI",),
    9: ("T2DM", "GERD"),
}

CHRONIC_ARCHETYPES: Final[dict[int, tuple[str, ...]]] = {
    1: ("T2DM", "HTN"),
    2: ("T2DM", "HTN", "CKD"),
    3: ("Asthma", "HTN"),
    4: ("T2DM", "Dyslipidemia"),
    5: ("T2DM", "HTN", "CKD"),
}


# ---------------------------------------------------------------------
# Visit count patterns by tier
# ---------------------------------------------------------------------

VISIT_COUNT_PATTERNS: Final[dict[str, tuple[int, ...]]] = {
    "normal": (2,),
    "moderate": (2, 3),
    "chronic": (5,),
}

# Kept for backward compatibility with older tier-based generators.
# New v1.7 Lite generators should prefer TIMELINE_GAP_DAYS via blueprint.timeline_pattern.
VISIT_DATE_OFFSETS_DAYS: Final[dict[str, tuple[int, ...]]] = {
    "normal": (0, 21),
    "moderate": (0, 90, 180),
    "chronic": (0, 90, 180, 270, 360),
}


# ---------------------------------------------------------------------
# Allergy generation constants
# ---------------------------------------------------------------------

SAFE_ALLERGEN_POOL: Final[tuple[str, ...]] = (
    "Penicillin",
    "Sulfa",
    "Ibuprofen",
    "Aspirin",
    "Latex",
)

ALLERGY_REACTION_MAP: Final[dict[str, str]] = {
    "Penicillin": "skin rash",
    "Sulfa": "itching",
    "Ibuprofen": "gastric discomfort",
    "Aspirin": "bronchospasm",
    "Latex": "contact dermatitis",
}

ALLERGY_SEVERITY_MAP: Final[dict[str, str]] = {
    "Penicillin": "moderate",
    "Sulfa": "moderate",
    "Ibuprofen": "mild",
    "Aspirin": "moderate",
    "Latex": "mild",
}


# ---------------------------------------------------------------------
# Lab progression profiles
# ---------------------------------------------------------------------

T2DM_BASELINE_PROFILES: Final[tuple[dict[str, float | int], ...]] = (
    {"hba1c": 8.4, "fbg": 172},
    {"hba1c": 8.1, "fbg": 165},
    {"hba1c": 7.8, "fbg": 154},
    {"hba1c": 8.7, "fbg": 181},
)

HTN_BASELINE_BP_PROFILES: Final[tuple[dict[str, int], ...]] = (
    {"systolic": 150, "diastolic": 94},
    {"systolic": 146, "diastolic": 92},
    {"systolic": 154, "diastolic": 96},
)

IDA_BASELINE_PROFILES: Final[tuple[dict[str, float | int], ...]] = (
    {"hemoglobin": 9.6, "ferritin": 10},
    {"hemoglobin": 9.9, "ferritin": 12},
    {"hemoglobin": 10.1, "ferritin": 14},
)

DYSLIPIDEMIA_BASELINE_PROFILES: Final[tuple[dict[str, float | int], ...]] = (
    {"ldl": 168},
    {"ldl": 156},
    {"ldl": 148},
)

CKD_CREATININE_SERIES: Final[tuple[float, ...]] = (
    1.4,
    1.5,
    1.6,
    1.7,
    1.6,
)

NON_CKD_CREATININE_SERIES: Final[tuple[float, ...]] = (
    0.9,
    0.9,
    1.0,
    1.0,
    0.9,
)


# ---------------------------------------------------------------------
# SOAP defaults
# ---------------------------------------------------------------------

EMPTY_SOAP_NOTE: Final[dict[str, str]] = {
    "subjective": "",
    "objective": "",
    "assessment": "",
    "plan": "",
}


# ---------------------------------------------------------------------
# Medication escalation rules
# ---------------------------------------------------------------------

T2DM_ADD_ON_VISIT_INDEX: Final[int] = 3
HTN_SECOND_DRUG_VISIT_INDEX: Final[int] = 4
ASTHMA_CONTROLLER_VISIT_INDEX: Final[int] = 2
IDA_STOP_AFTER_VISIT_INDEX: Final[int] = 3


# ---------------------------------------------------------------------
# Retrieval challenge thresholds / V13 report-only audit
# ---------------------------------------------------------------------

EMBEDDING_MODEL_NAME: Final[str] = "sentence-transformers/all-MiniLM-L6-v2"
V13_SIMILARITY_WARN_THRESHOLD: Final[float] = 0.87
V13_SIMILARITY_CRITICAL_THRESHOLD: Final[float] = 0.92

RETRIEVAL_CHALLENGE_PASS_CRITERIA: Final[dict[str, float]] = {
    "critical": 1.00,
    "easy": 0.95,
    "medium": 0.85,
    "hard": 0.75,
}

WRONG_PATIENT_RETRIEVAL_ALLOWED: Final[int] = 0


# ---------------------------------------------------------------------
# JSON formatting
# ---------------------------------------------------------------------

JSON_INDENT: Final[int] = 2
JSON_ENCODING: Final[str] = "utf-8"
