"""Tests for the multi-specialty master catalogue discovery and validation."""

import csv
import json
from pathlib import Path
from urllib.parse import urlparse

import pytest

ALLOWED_DOMAINS = {"icmr.gov.in", "www.icmr.gov.in", "main.icmr.nic.in"}


def test_catalogue_json_structure():
    catalog_path = Path("data/metadata/all_discovered_stws.json")
    assert catalog_path.exists(), "Master catalogue JSON must exist."

    with open(catalog_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "metadata" in data
    assert "documents" in data

    meta = data["metadata"]
    assert meta["total_documents"] == 187
    assert meta["total_specialties"] == 27
    assert len(meta["specialties"]) == 27

    docs = data["documents"]
    assert len(docs) == 187

    # Check each document has required fields
    for doc in docs:
        assert doc["stw_id"]
        assert doc["specialty"]
        assert doc["condition"]
        assert doc["source_url"]
        assert doc["url_hash"]

        parsed = urlparse(doc["source_url"])
        assert parsed.netloc.lower() in ALLOWED_DOMAINS, f"Invalid domain: {parsed.netloc}"


def test_catalogue_csv_structure():
    csv_path = Path("data/metadata/stw_master_catalog.csv")
    assert csv_path.exists(), "Master catalogue CSV must exist."

    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    assert len(rows) == 187
    expected_fields = {"stw_id", "title", "specialty", "condition", "source_url", "url_hash", "status"}
    for f in expected_fields:
        assert f in reader.fieldnames, f"Missing column: {f}"

    specialties = set(r["specialty"] for r in rows)
    assert len(specialties) == 27
    assert "Cardiology" in specialties
    assert "Neurology" in specialties
    assert "Nephrology" in specialties
    assert "Pulmonology" in specialties
