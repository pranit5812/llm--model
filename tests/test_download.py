"""Unit tests for STW download and integrity calculation logic."""

import hashlib
import tempfile
from pathlib import Path
import pytest
from scripts.download_stws import (
    calculate_sha256,
    inspect_pdf,
    is_allowed_domain,
    match_approved_condition,
    normalize_string,
)


def test_calculate_sha256(tmp_path: Path):
    test_file = tmp_path / "sample.bin"
    content = b"Official ICMR Clinical Protocol Standard Treatment Workflow"
    test_file.write_bytes(content)

    expected = hashlib.sha256(content).hexdigest()
    assert calculate_sha256(test_file) == expected


def test_inspect_pdf_invalid(tmp_path: Path):
    # Non-existent file
    valid, pages, err = inspect_pdf(tmp_path / "does_not_exist.pdf")
    assert valid is False
    assert pages == 0

    # Non-PDF content
    fake_pdf = tmp_path / "fake.pdf"
    fake_pdf.write_text("Hello World! Not a real PDF.")
    valid, pages, err = inspect_pdf(fake_pdf)
    assert valid is False
    assert "Invalid PDF signature" in err


def test_condition_matching():
    approved = [
        {"condition": "Atrial Fibrillation", "stw_id": "ICMR-CARD-001"},
        {"condition": "Bradyarrhythmias", "stw_id": "ICMR-CARD-002"},
        {"condition": "Heart Failure", "stw_id": "ICMR-CARD-003"},
        {"condition": "NSTEMI", "stw_id": "ICMR-CARD-004"},
        {"condition": "Stable Angina", "stw_id": "ICMR-CARD-005"},
        {"condition": "STEMI", "stw_id": "ICMR-CARD-006"},
        {"condition": "Cardiology (All)", "stw_id": "ICMR-CARD-007"},
    ]

    # Normal exact or case-insensitive match
    m1 = match_approved_condition("Atrial Fibrillation", approved)
    assert m1 is not None and m1["stw_id"] == "ICMR-CARD-001"

    # Variant spelling on ICMR portal: "Bradyarrythmias"
    m2 = match_approved_condition("Bradyarrythmias", approved)
    assert m2 is not None and m2["stw_id"] == "ICMR-CARD-002"

    # Lowercase title: "Heart failure"
    m3 = match_approved_condition("Heart failure", approved)
    assert m3 is not None and m3["stw_id"] == "ICMR-CARD-003"

    # Distinct matching for NSTEMI and STEMI
    m4 = match_approved_condition("NSTEMI", approved)
    assert m4 is not None and m4["stw_id"] == "ICMR-CARD-004"
    assert m4["condition"] == "NSTEMI"

    m6 = match_approved_condition("STEMI", approved)
    assert m6 is not None and m6["stw_id"] == "ICMR-CARD-006"
    assert m6["condition"] == "STEMI"

    # Consolidated: "Cardiology (All)"
    m7 = match_approved_condition("Cardiology (All)", approved)
    assert m7 is not None and m7["stw_id"] == "ICMR-CARD-007"

    # Unapproved specialty/condition
    assert match_approved_condition("Pediatric Oncology", approved) is None
