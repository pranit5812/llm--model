"""
ICMR STW Document Validation Script
Validates all downloaded STW PDF documents against integrity standards,
cryptographic hash records, and catalogue metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import pymupdf
import yaml

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("validate_documents")

REQUIRED_COLUMNS = [
    "stw_id",
    "volume",
    "specialty",
    "condition",
    "document_type",
    "source_organization",
    "source_url",
    "local_path",
    "download_date",
    "document_hash",
    "version",
    "status",
]


def load_config(config_path: Path | str = "config/settings.yaml") -> dict[str, Any]:
    """Load configuration settings from YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path.resolve()}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def calculate_sha256(filepath: Path) -> str:
    """Calculate SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def is_allowed_domain(url: str, allowed_domains: list[str]) -> bool:
    """Validate that URL domain is in the allowed list."""
    hostname = urlparse(url).hostname or ""
    return any(hostname == domain or hostname.endswith("." + domain) for domain in allowed_domains)


class ValidationResult:
    def __init__(self, stw_id: str, condition: str, local_path: str):
        self.stw_id = stw_id
        self.condition = condition
        self.local_path = local_path
        self.passed = True
        self.checks: dict[str, bool] = {}
        self.errors: list[str] = []

    def add_check(self, check_name: str, success: bool, error_msg: str = "") -> None:
        self.checks[check_name] = success
        if not success:
            self.passed = False
            if error_msg:
                self.errors.append(error_msg)


def validate_catalog_and_documents(config: dict[str, Any]) -> tuple[bool, list[ValidationResult], list[str]]:
    """
    Run full validation suite across metadata catalog and raw PDF documents.
    Returns (all_passed, results_list, global_errors).
    """
    paths_cfg = config.get("paths", {})
    source_cfg = config.get("source", {})
    allowed_domains = source_cfg.get("allowed_domains", ["icmr.gov.in"])

    catalog_path = Path(paths_cfg.get("catalog_file", "data/metadata/stw_catalog.csv"))
    raw_cardio_dir = Path(paths_cfg.get("cardiology_raw_dir", "data/raw/cardiology"))

    global_errors: list[str] = []
    results: list[ValidationResult] = []

    # 1. Verify Catalog Exists
    if not catalog_path.exists():
        global_errors.append(f"Catalogue file not found at: {catalog_path}")
        return False, results, global_errors

    try:
        df = pd.read_csv(catalog_path, dtype=str)
    except Exception as e:
        global_errors.append(f"Could not read catalogue CSV: {e}")
        return False, results, global_errors

    if df.empty:
        global_errors.append("Catalogue is empty (no records found).")
        return False, results, global_errors

    # 2. Check required columns
    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        global_errors.append(f"Catalogue is missing required columns: {missing_cols}")
        return False, results, global_errors

    # Track seen hashes to detect duplicates
    seen_hashes: dict[str, str] = {}
    catalogued_files: set[Path] = set()

    for idx, row in df.iterrows():
        stw_id = str(row.get("stw_id", "")).strip()
        condition = str(row.get("condition", "")).strip()
        local_path_str = str(row.get("local_path", "")).strip()
        source_url = str(row.get("source_url", "")).strip()
        expected_hash = str(row.get("document_hash", "")).strip()
        expected_pages_str = str(row.get("page_count", "")).strip()
        status = str(row.get("status", "")).strip()

        vr = ValidationResult(stw_id=stw_id, condition=condition, local_path=local_path_str)

        # Check STW ID format
        id_valid = bool(re.match(r"^ICMR-[A-Z]+-\d{3}$", stw_id))
        vr.add_check("stw_id_format", id_valid, f"Invalid STW ID format: '{stw_id}'" if not id_valid else "")

        # Check Source URL
        url_valid = bool(source_url.startswith("https://") and is_allowed_domain(source_url, allowed_domains))
        vr.add_check("source_url_domain", url_valid, f"Source URL not from approved domain: {source_url}" if not url_valid else "")

        # Check Local File Exists
        local_path = Path(local_path_str)
        file_exists = local_path.exists()
        vr.add_check("file_exists", file_exists, f"Local file does not exist: {local_path}" if not file_exists else "")

        if not file_exists:
            results.append(vr)
            continue

        catalogued_files.add(local_path.resolve())

        # Check File Readable and Magic Bytes
        is_pdf_magic = False
        try:
            with open(local_path, "rb") as f:
                header = f.read(4)
                is_pdf_magic = (header == b"%PDF")
        except Exception as e:
            vr.add_check("file_readable", False, f"Could not open file: {e}")
        else:
            vr.add_check("file_readable", True)

        vr.add_check("pdf_signature", is_pdf_magic, f"File does not have %PDF header: {local_path}" if not is_pdf_magic else "")

        # Check Page Count via PyMuPDF
        page_count_determined = False
        actual_pages = 0
        try:
            doc = pymupdf.open(local_path)
            actual_pages = doc.page_count
            doc.close()
            page_count_determined = (actual_pages > 0)
        except Exception as e:
            vr.add_check("page_count_readable", False, f"PyMuPDF error reading {local_path}: {e}")
        else:
            vr.add_check("page_count_readable", page_count_determined, "PyMuPDF reported 0 pages" if not page_count_determined else "")

        # Compare with catalog page count if recorded
        if expected_pages_str and expected_pages_str.isdigit():
            expected_pages = int(expected_pages_str)
            pages_match = (actual_pages == expected_pages)
            vr.add_check("page_count_matches", pages_match, f"Page count mismatch: catalog={expected_pages}, actual={actual_pages}" if not pages_match else "")

        # Calculate SHA-256 Hash
        actual_hash = ""
        try:
            actual_hash = calculate_sha256(local_path)
            vr.add_check("hash_calculable", True)
        except Exception as e:
            vr.add_check("hash_calculable", False, f"Could not compute SHA-256: {e}")

        # Check hash against catalog
        if expected_hash:
            hash_match = (actual_hash.lower() == expected_hash.lower())
            vr.add_check("hash_matches_catalog", hash_match, f"Hash mismatch: catalog={expected_hash}, file={actual_hash}" if not hash_match else "")
        else:
            vr.add_check("hash_in_catalog", False, "Catalogue entry is missing document_hash")

        # Duplicate Hash Check (different STWs having identical hash)
        if actual_hash:
            if actual_hash in seen_hashes:
                other_id = seen_hashes[actual_hash]
                vr.add_check("no_duplicate_hash", False, f"Duplicate document hash detected! Matches {other_id} ({actual_hash})")
            else:
                seen_hashes[actual_hash] = stw_id
                vr.add_check("no_duplicate_hash", True)

        # Status Check
        status_ok = (status == "verified")
        vr.add_check("status_verified", status_ok, f"Status is not 'verified' (current: {status})")

        results.append(vr)

    # 3. Check for uncatalogued files in raw directory
    if raw_cardio_dir.exists():
        for f in raw_cardio_dir.glob("*.pdf"):
            if f.resolve() not in catalogued_files:
                global_errors.append(f"Uncatalogued PDF found in raw directory: {f}")

    all_passed = len(global_errors) == 0 and all(r.passed for r in results)
    return all_passed, results, global_errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate official ICMR STW repository documents.")
    parser.add_argument("--config", default="config/settings.yaml", help="Path to settings.yaml")
    args = parser.parse_args()

    config = load_config(args.config)
    logger.info("Initiating comprehensive validation for ICMR STW documents...")

    all_passed, results, global_errors = validate_catalog_and_documents(config)

    print("\n" + "=" * 80)
    print("ICMR STW DOCUMENT INTEGRITY & CATALOGUE VALIDATION REPORT")
    print("=" * 80)

    for r in results:
        status_symbol = "[PASS]" if r.passed else "[FAIL]"
        print(f"\n{status_symbol} {r.stw_id}: {r.condition}")
        print(f"       Path: {r.local_path}")
        for check, passed in r.checks.items():
            check_sym = "  + " if passed else "  X "
            print(f"       {check_sym}{check}")
        if r.errors:
            for err in r.errors:
                print(f"       [ERROR] {err}")

    if global_errors:
        print("\n" + "-" * 80)
        print("GLOBAL REPOSITORY ERRORS:")
        for err in global_errors:
            print(f"  [X] {err}")

    print("\n" + "=" * 80)
    total_docs = len(results)
    passed_docs = sum(1 for r in results if r.passed)
    print(f"SUMMARY: {passed_docs}/{total_docs} documents fully validated. All passed: {all_passed}")
    print("=" * 80 + "\n")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
