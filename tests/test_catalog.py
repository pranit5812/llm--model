"""Unit tests for STW catalog structure and constraints."""

import re
from pathlib import Path
import pandas as pd
import pytest


def test_catalog_schema_and_id_format():
    catalog_path = Path("data/metadata/stw_catalog.csv")
    if not catalog_path.exists():
        pytest.skip("Catalog file not yet generated.")

    df = pd.read_csv(catalog_path, dtype=str)
    assert not df.empty, "Catalog should not be empty."

    expected_cols = [
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
    for col in expected_cols:
        assert col in df.columns, f"Missing required column: {col}"

    id_pattern = re.compile(r"^ICMR-[A-Z]+-\d{3}$")
    for stw_id in df["stw_id"]:
        assert id_pattern.match(stw_id), f"Invalid STW ID pattern: {stw_id}"

    # Check that document_hash is 64-char hex
    for h in df["document_hash"]:
        assert len(h) == 64, f"Invalid SHA-256 length: {h}"
        assert all(c in "0123456789abcdefABCDEF" for c in h)
