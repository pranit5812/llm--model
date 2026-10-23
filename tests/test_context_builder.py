"""Tests for evidence context builder."""

import pytest

from src.rag.context_builder import ContextBuilder
from src.retrieval.models import RetrievalResult


def make_test_result(
    unit_id: str,
    doc_id: str = "ICMR-CARD-006",
    content: str = "Sample clinical content",
    review_status: str = "extracted",
) -> RetrievalResult:
    return RetrievalResult(
        unit_id=unit_id,
        content=content,
        score=0.9,
        document_id=doc_id,
        condition="STEMI",
        specialty="Cardiology",
        page_number=1,
        section="Treatment",
        entity_type="medication",
        review_status=review_status,
        source_reference={"doc": doc_id},
        rank=1,
    )


class TestContextBuilder:
    """Validate evidence context builder constraints."""

    def test_empty_results_returns_empty_context(self):
        builder = ContextBuilder()
        context_str, selected, unit_ids = builder.build_context([])
        assert context_str == ""
        assert selected == []
        assert len(unit_ids) == 0

    def test_formats_numbered_evidence_blocks(self):
        builder = ContextBuilder(max_units=3)
        results = [
            make_test_result("unit_1", content="Aspirin 300mg"),
            make_test_result("unit_2", content="Clopidogrel 300mg"),
        ]
        context_str, selected, unit_ids = builder.build_context(results)
        assert "[EVIDENCE 1]" in context_str
        assert "[EVIDENCE 2]" in context_str
        assert "unit_1" in unit_ids
        assert "unit_2" in unit_ids
        assert len(selected) == 2

    def test_deduplicates_by_unit_id(self):
        builder = ContextBuilder()
        results = [
            make_test_result("unit_1", content="Aspirin"),
            make_test_result("unit_1", content="Aspirin duplicate"),
        ]
        context_str, selected, unit_ids = builder.build_context(results)
        assert len(selected) == 1
        assert len(unit_ids) == 1

    def test_strictly_excludes_needs_review_units(self):
        builder = ContextBuilder()
        results = [
            make_test_result("unit_1", review_status="needs_review", content="Unverified table data"),
            make_test_result("unit_2", review_status="extracted", content="Verified recommendation"),
        ]
        context_str, selected, unit_ids = builder.build_context(results)
        assert len(selected) == 1
        assert "unit_1" not in unit_ids
        assert "unit_2" in unit_ids
        assert "Unverified table data" not in context_str

    def test_respects_max_units_ceiling(self):
        builder = ContextBuilder(max_units=2)
        results = [make_test_result(f"unit_{i}") for i in range(5)]
        context_str, selected, unit_ids = builder.build_context(results)
        assert len(selected) == 2
        assert len(unit_ids) == 2
