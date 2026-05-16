"""
config/paths.py

Centralized filesystem paths for the data engineering layer and local project runtime.

This module uses pathlib only and should be imported by scripts, validators,
generators, ingestion utilities, and demo helpers instead of hardcoding paths.
"""

from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CONFIG_DIR = PROJECT_ROOT / "config"
GENERATORS_DIR = PROJECT_ROOT / "generators"
VALIDATORS_DIR = PROJECT_ROOT / "validators"
SOAP_DIR = PROJECT_ROOT / "soap"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
INGESTION_DIR = PROJECT_ROOT / "ingestion"
RAG_DIR = PROJECT_ROOT / "rag"
OCR_DIR = PROJECT_ROOT / "ocr"
DOCS_DIR = PROJECT_ROOT / "docs"

DATA_DIR = PROJECT_ROOT / "data"
PATIENTS_DIR = DATA_DIR / "patients"
QUARANTINE_DIR = DATA_DIR / "quarantine"
SCHEMAS_DIR = DATA_DIR / "schemas"
CHROMADB_DIR = DATA_DIR / "chromadb"

PATIENT_SCHEMA_PATH = SCHEMAS_DIR / "patient_schema.json"

LOGS_DIR = PROJECT_ROOT / "logs"
VALIDATION_REPORTS_DIR = LOGS_DIR / "validation_reports"


def ensure_project_directories() -> None:
    """
    Create required runtime directories.

    This function is safe to call repeatedly.
    """
    for directory in (
        DATA_DIR,
        PATIENTS_DIR,
        QUARANTINE_DIR,
        SCHEMAS_DIR,
        CHROMADB_DIR,
        LOGS_DIR,
        VALIDATION_REPORTS_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def patient_file_path(patient_id: str) -> Path:
    """Return the approved patient JSON path for a patient ID."""
    return PATIENTS_DIR / f"{patient_id}.json"


def quarantine_file_path(patient_id: str) -> Path:
    """Return the quarantine JSON path for a patient ID."""
    return QUARANTINE_DIR / f"{patient_id}.json"


def validation_report_path(stem: str = "validation_report") -> Path:
    """Return a timestamp-independent validation report path."""
    return VALIDATION_REPORTS_DIR / f"{stem}.json"