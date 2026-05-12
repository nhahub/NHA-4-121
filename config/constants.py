"""
config/constants.py

Single source of truth for locked project constants.

This file intentionally contains no runtime side effects and no API calls.
Every generator, validator, SOAP utility, and script should import locked
values from here instead of redefining enums locally.
"""

from __future__ import annotations

from typing import Final


# ---------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------

SCHEMA_VERSION: Final[str] = "1.0"
PROJECT_NAME: Final[str] = "AI-Powered Medical Record Intelligence System"


# ---------------------------------------------------------------------
# Locked enums
# ---------------------------------------------------------------------

CONDITIONS: Final[tuple[str, ...]] = (
    "T2DM",
    "HTN",
    "Asthma",
    "IDA",
    "GERD",
    "CKD",
)

LAB_TYPES: Final[tuple[str, ...]] = (
    "HbA1c",
    "FBG",
    "Creatinine",
    "Hemoglobin",
    "Ferritin",
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

SOURCE_TYPES: Final[tuple[str, ...]] = (
    "doctor_note",
    "lab_result",
    "prescription",
    "allergy",
)

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
    "normal": 10,
    "moderate": 13,
    "chronic": 7,
}

EXPECTED_FULL_PATIENT_COUNT: Final[int] = 30

DATASET_RANDOM_SEED: Final[int] = 20260512


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


# ---------------------------------------------------------------------
# Blood pressure forbidden lab terms
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


# ---------------------------------------------------------------------
# Medication whitelist
# ---------------------------------------------------------------------

MEDICATION_WHITELIST: Final[dict[str, dict[str, str]]] = {
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
}

MEDICATION_NAMES: Final[tuple[str, ...]] = tuple(MEDICATION_WHITELIST.keys())


# ---------------------------------------------------------------------
# Lab metadata
# ---------------------------------------------------------------------

LAB_REFERENCE_RANGES: Final[dict[str, str]] = {
    "HbA1c": "4.0-5.6 %",
    "FBG": "70-99 mg/dL",
    "Creatinine": "0.6-1.2 mg/dL",
    "Hemoglobin": "12.0-16.0 g/dL",
    "Ferritin": "30-300 ng/mL",
}

LAB_UNITS: Final[dict[str, str]] = {
    "HbA1c": "%",
    "FBG": "mg/dL",
    "Creatinine": "mg/dL",
    "Hemoglobin": "g/dL",
    "Ferritin": "ng/mL",
}


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
# Deterministic disease archetype plans
# ---------------------------------------------------------------------

MODERATE_ARCHETYPES: Final[dict[int, tuple[str, ...]]] = {
    1: ("T2DM",),
    2: ("T2DM",),
    3: ("T2DM",),
    4: ("T2DM",),
    5: ("HTN",),
    6: ("HTN",),
    7: ("HTN",),
    8: ("IDA",),
    9: ("IDA",),
    10: ("IDA",),
    11: ("GERD",),
    12: ("GERD",),
    13: ("Asthma",),
}

CHRONIC_ARCHETYPES: Final[dict[int, tuple[str, ...]]] = {
    1: ("T2DM", "HTN", "CKD"),
    2: ("T2DM", "HTN", "CKD"),
    3: ("T2DM", "HTN"),
    4: ("T2DM", "HTN", "Asthma"),
    5: ("T2DM", "HTN"),
    6: ("T2DM", "HTN", "GERD"),
    7: ("T2DM", "HTN"),
}

# ---------------------------------------------------------------------
# Visit count patterns by tier
# ---------------------------------------------------------------------

VISIT_COUNT_PATTERNS: Final[dict[str, tuple[int, ...]]] = {
    "normal": (2, 3, 4),
    "moderate": (5, 6, 7),
    "chronic": (8, 9, 10),
}

# ---------------------------------------------------------------------
# Visit timeline spacing patterns
# ---------------------------------------------------------------------

VISIT_DATE_OFFSETS_DAYS: Final[dict[str, tuple[int, ...]]] = {
    "normal": (0, 7, 21, 45),
    "moderate": (0, 60, 120, 180, 270, 360, 450),
    "chronic": (0, 90, 180, 270, 360, 450, 540, 630, 720, 810),
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
    "Aspirin": "urticaria",
    "Latex": "contact dermatitis",
}

ALLERGY_SEVERITY_MAP: Final[dict[str, str]] = {
    "Penicillin": "moderate",
    "Sulfa": "moderate",
    "Ibuprofen": "mild",
    "Aspirin": "mild",
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

CKD_CREATININE_SERIES: Final[tuple[float, ...]] = (
    1.4,
    1.5,
    1.6,
    1.7,
    1.6,
    1.5,
    1.5,
    1.4,
    1.4,
    1.4,
)

NON_CKD_CREATININE_SERIES: Final[tuple[float, ...]] = (
    0.9,
    0.9,
    1.0,
    1.0,
    0.9,
    1.0,
    0.9,
    0.9,
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
IDA_STOP_AFTER_VISIT_INDEX: Final[int] = 5

# ---------------------------------------------------------------------
# Dataset generation modes
# ---------------------------------------------------------------------

DATASET_MODE_PILOT: Final[str] = "pilot"
DATASET_MODE_FULL: Final[str] = "full"

DEFAULT_DATASET_MODE: Final[str] = DATASET_MODE_FULL

# ---------------------------------------------------------------------
# JSON formatting
# ---------------------------------------------------------------------

JSON_INDENT: Final[int] = 2
JSON_ENCODING: Final[str] = "utf-8"
