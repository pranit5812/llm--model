"""Unit tests for document validation rules."""

import hashlib
from pathlib import Path
import pandas as pd
import pytest
from scripts.validate_documents import (
    REQUIRED_COLUMNS,
    ValidationResult,
    calculate_sha256,
    is_allowed_domain,
    validate_catalog_and_documents,
)


def test_required_columns_specification():
    assert "stw_id" in REQUIRED_COLUMNS
    assert "document_hash" in REQUIRED_COLUMNS
    assert "source_url" in REQUIRED_COLUMNS
    assert "local_path" in REQUIRED_COLUMNS
    assert "status" in REQUIRED_COLUMNS
    assert "version" in REQUIRED_COLUMNS


def test_validation_result_tracking():
    vr = ValidationResult(
        stw_id="ICMR-CARD-001",
        condition="Atrial Fibrillation",
        local_path="data/raw/cardiology/test.pdf",
    )
    vr.add_check("file_exists", True)
    assert vr.passed is True

    vr.add_check("pdf_signature", False, "Invalid signature")
    assert vr.passed is False
    assert len(vr.errors) == 1
    assert "Invalid signature" in vr.errors[0]


def test_validate_catalog_and_documents_mock(tmp_path: Path):
    # Setup temporary environment
    config = {
        "source": {"allowed_domains": ["icmr.gov.in"]},
        "paths": {
            "catalog_file": str(tmp_path / "catalog.csv"),
            "cardiology_raw_dir": str(tmp_path / "cardiology"),
        },
    }

    # When catalog does not exist
    passed, results, errors = validate_catalog_and_documents(config)
    assert passed is False
    assert any("Catalogue file not found" in e for e in errors)
