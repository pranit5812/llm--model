"""Tests for document version models, precedence rules, and database version tracking."""

import sqlite3
from pathlib import Path
import pytest

from src.models.version import DocumentVersion, VersionPrecedence


def test_document_version_model():
    dv = DocumentVersion(
        document_id="ICMR-CARD-001",
        specialty="Cardiology",
        condition="Atrial Fibrillation",
        version_id="v1.0",
        source_url="https://www.icmr.gov.in/test.pdf",
        download_date="2026-09-12T10:00:00Z",
        content_hash="a" * 64,
        is_current=True,
        review_status="approved",
    )
    assert dv.document_id == "ICMR-CARD-001"
    assert dv.version_id == "v1.0"
    assert dv.is_current is True
    assert dv.supersedes is None

    # Serialization check
    d = dv.model_dump()
    assert d["content_hash"] == "a" * 64


def test_version_precedence_enum():
    assert VersionPrecedence.CURRENT.value == "CURRENT"
    assert VersionPrecedence.SUPERSEDED.value == "SUPERSEDED"
    assert VersionPrecedence.VERSION_PRECEDENCE_UNKNOWN.value == "VERSION_PRECEDENCE_UNKNOWN"


def test_document_versions_sqlite_records():
    db_path = Path("data/knowledge/knowledge.db")
    assert db_path.exists()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM document_versions ORDER BY document_id").fetchall()
        assert len(rows) == 14, f"Expected 14 document version rows, got {len(rows)}"

        card_rows = [r for r in rows if r["specialty"] == "Cardiology"]
        neur_rows = [r for r in rows if r["specialty"] == "Neurology"]

        assert len(card_rows) == 7
        assert len(neur_rows) == 7

        for cr in card_rows:
            assert cr["review_status"] == "approved"
            assert cr["is_current"] == 1
            assert cr["version_id"] == "v1.0"

        for nr in neur_rows:
            assert nr["review_status"] == "needs_review"
            assert nr["is_current"] == 1
            assert nr["version_id"] == "v1.0"
    finally:
        conn.close()
