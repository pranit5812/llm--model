"""Tests for Phase 4 knowledge indexing pipeline.

Verifies:
- All 7 STW documents produce knowledge units.
- needs_review units are excluded from production index.
- Production units all have provenance.
- index_manifest.json is accurate.
- SQLite database is populated correctly.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from src.knowledge.indexer import KnowledgeIndexer
from src.knowledge.units import ENTITY_TYPES

STRUCTURED_DIR = Path("data/processed/structured")
KNOWLEDGE_DIR = Path("data/knowledge")

EXPECTED_DOCUMENT_IDS = {
    "ICMR-CARD-001",
    "ICMR-CARD-002",
    "ICMR-CARD-003",
    "ICMR-CARD-004",
    "ICMR-CARD-005",
    "ICMR-CARD-006",
    "ICMR-CARD-007",
}


@pytest.fixture(scope="module")
def indexer() -> KnowledgeIndexer:
    """Load the pre-built knowledge index."""
    ix = KnowledgeIndexer(structured_dir=STRUCTURED_DIR, knowledge_dir=KNOWLEDGE_DIR)
    ix.load()
    return ix


# ---------------------------------------------------------------------------
# Test: all 7 documents present
# ---------------------------------------------------------------------------

class TestDocumentCoverage:
    def test_all_seven_documents_indexed(self, indexer):
        """All 7 STW documents must be represented in the index."""
        manifest = indexer.get_manifest()
        assert manifest is not None, "Index manifest missing — run build_index.py first."
        indexed_ids = set(manifest["per_document"].keys())
        assert EXPECTED_DOCUMENT_IDS == indexed_ids, (
            f"Missing documents: {EXPECTED_DOCUMENT_IDS - indexed_ids}"
        )

    def test_total_documents_count(self, indexer):
        manifest = indexer.get_manifest()
        assert manifest["total_documents"] == 7

    def test_each_document_has_production_units(self, indexer):
        """Every document must have at least one production knowledge unit."""
        manifest = indexer.get_manifest()
        for doc_id, info in manifest["per_document"].items():
            assert info["production_units"] > 0, (
                f"Document {doc_id} has zero production units"
            )

    def test_total_units_positive(self, indexer):
        manifest = indexer.get_manifest()
        assert manifest["total_units"] > 0
        assert manifest["production_units"] > 0
        assert manifest["production_units"] <= manifest["total_units"]


# ---------------------------------------------------------------------------
# Test: needs_review exclusion
# ---------------------------------------------------------------------------

class TestReviewExclusion:
    def test_needs_review_excluded_from_production(self, indexer):
        """Production index must contain zero needs_review units."""
        prod_units = indexer.get_all_production_units()
        flagged = [u for u in prod_units if u.requires_manual_review]
        assert len(flagged) == 0, (
            f"Production index contains {len(flagged)} needs_review units: "
            f"{[u.unit_id for u in flagged[:5]]}"
        )

    def test_excluded_count_matches_manifest(self, indexer):
        manifest = indexer.get_manifest()
        total = manifest["total_units"]
        prod = manifest["production_units"]
        excluded = manifest["excluded_needs_review"]
        assert total == prod + excluded

    def test_all_units_include_review_flagged(self, indexer):
        """The all_units list must include both production and review units."""
        all_units = indexer.get_all_units()
        prod_units = indexer.get_all_production_units()
        assert len(all_units) >= len(prod_units)
        review_count = sum(1 for u in all_units if u.requires_manual_review)
        cardio_review = sum(1 for u in all_units if u.requires_manual_review and u.specialty == "Cardiology")
        manifest = indexer.get_manifest()
        assert review_count >= manifest["excluded_needs_review"]
        assert cardio_review == manifest["excluded_needs_review"]


# ---------------------------------------------------------------------------
# Test: provenance on all production units
# ---------------------------------------------------------------------------

class TestProvenance:
    def test_every_production_unit_has_source_reference(self, indexer):
        """Every production knowledge unit must have a non-empty source_reference."""
        prod_units = indexer.get_all_production_units()
        missing = [
            u.unit_id for u in prod_units
            if not u.source_reference or not u.source_reference.get("document_id")
        ]
        assert len(missing) == 0, (
            f"{len(missing)} production units have no source_reference: {missing[:5]}"
        )

    def test_every_unit_has_page_number(self, indexer):
        prod_units = indexer.get_all_production_units()
        bad = [u for u in prod_units if u.page_number < 1]
        assert len(bad) == 0, f"{len(bad)} units have invalid page_number"

    def test_every_unit_has_non_empty_content(self, indexer):
        prod_units = indexer.get_all_production_units()
        empty = [u for u in prod_units if not u.content or not u.content.strip()]
        assert len(empty) == 0, f"{len(empty)} units have empty content"


# ---------------------------------------------------------------------------
# Test: entity type coverage
# ---------------------------------------------------------------------------

class TestEntityTypeCoverage:
    def test_entity_type_counts(self, indexer):
        manifest = indexer.get_manifest()
        counts = manifest.get("entity_type_counts", {})
        # At minimum, these entity types must be present across production units
        required_types = ["medication", "investigation", "contraindication", "referral_criterion"]
        for etype in required_types:
            assert counts.get(etype, 0) > 0, f"No production units of type '{etype}'"


# ---------------------------------------------------------------------------
# Test: manifest integrity
# ---------------------------------------------------------------------------

class TestManifestIntegrity:
    def test_manifest_fields(self, indexer):
        manifest = indexer.get_manifest()
        required = ["built_at", "total_documents", "total_units", "production_units",
                    "excluded_needs_review", "per_document", "entity_type_counts"]
        for field in required:
            assert field in manifest, f"Manifest missing field: {field}"

    def test_manifest_arithmetic(self, indexer):
        manifest = indexer.get_manifest()
        assert manifest["total_units"] == (
            manifest["production_units"] + manifest["excluded_needs_review"]
        )


# ---------------------------------------------------------------------------
# Test: SQLite database
# ---------------------------------------------------------------------------

class TestSQLiteDatabase:
    def test_db_file_exists(self):
        db_path = KNOWLEDGE_DIR / "knowledge.db"
        assert db_path.exists(), f"SQLite database not found: {db_path}"

    def test_db_row_count_matches_manifest(self, indexer):
        db_path = KNOWLEDGE_DIR / "knowledge.db"
        conn = sqlite3.connect(db_path)
        try:
            count = conn.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()[0]
            cardio_count = conn.execute("SELECT COUNT(*) FROM knowledge_units WHERE specialty = 'Cardiology'").fetchone()[0]
        finally:
            conn.close()
        manifest = indexer.get_manifest()
        assert count >= manifest["total_units"]
        assert cardio_count == manifest["total_units"]

    def test_db_no_null_unit_ids(self):
        db_path = KNOWLEDGE_DIR / "knowledge.db"
        conn = sqlite3.connect(db_path)
        try:
            nulls = conn.execute(
                "SELECT COUNT(*) FROM knowledge_units WHERE unit_id IS NULL OR unit_id = ''"
            ).fetchone()[0]
        finally:
            conn.close()
        assert nulls == 0
