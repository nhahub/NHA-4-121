"""
scripts/reset_chromadb.py  —  ChromaDB collection reset utility

Drops and recreates the clinical_records_v17_lite collection.
Does not affect any patient JSON files.

Usage
-----
    PYTHONPATH=. python scripts/reset_chromadb.py
    PYTHONPATH=. python scripts/reset_chromadb.py --collection my_collection
    PYTHONPATH=. python scripts/reset_chromadb.py --persist-dir /path/to/chromadb
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ingestion.ingest import (
    COLLECTION_NAME,
    CHROMA_PERSIST_DIR,
    IngestionError,
    reset_collection,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Reset the ChromaDB collection (drop + recreate, zero chunks)."
    )
    parser.add_argument(
        "--persist-dir",
        type=Path,
        default=CHROMA_PERSIST_DIR,
        help=f"ChromaDB persistence directory. Default: {CHROMA_PERSIST_DIR}",
    )
    parser.add_argument(
        "--collection",
        default=COLLECTION_NAME,
        help=f"Collection to reset. Default: {COLLECTION_NAME}",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt.",
    )
    args = parser.parse_args()

    if not args.yes:
        print(f"WARNING: This will permanently delete all chunks in collection "
              f"'{args.collection}' at {args.persist_dir}.")
        confirm = input("Type 'yes' to continue: ").strip().lower()
        if confirm != "yes":
            print("Reset cancelled.")
            return 0

    try:
        reset_collection(persist_dir=args.persist_dir, collection_name=args.collection)
        print(f"Collection '{args.collection}' reset successfully. "
              f"Re-ingest with: PYTHONPATH=. python scripts/ingest_all.py --clean")
    except IngestionError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
