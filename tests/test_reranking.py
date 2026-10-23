"""Tests for reranking components in ICMR STW retrieval system."""

import pytest
from src.retrieval.models import RetrievalResult
from src.retrieval.reranker import Reranker, TFIDFReranker


def make_dummy_result(unit_id: str, content: str, score: float) -> RetrievalResult:
    return RetrievalResult(
        unit_id=unit_id,
        content=content,
        score=score,
        document_id="ICMR-CARD-006",
        condition="STEMI",
        specialty="Cardiology",
        page_number=1,
        section="Treatment",
        entity_type="medication",
        review_status="extracted",
        source_reference={"doc": "ICMR-CARD-006"},
        rank=1,
    )


class TestTFIDFReranker:
    """Test TFIDFReranker functionality."""

    def test_reranker_instance(self):
        reranker = TFIDFReranker(blend_alpha=0.4)
        assert isinstance(reranker, Reranker)

    def test_empty_results_handling(self):
        reranker = TFIDFReranker()
        assert reranker.rerank("query", []) == []

    def test_empty_query_returns_same_results(self):
        reranker = TFIDFReranker()
        results = [
            make_dummy_result("1", "streptokinase dose", 0.8),
            make_dummy_result("2", "aspirin dose", 0.7),
        ]
        reranked = reranker.rerank("", results)
        assert len(reranked) == 2
        assert reranked[0].unit_id == "1"

    def test_reranker_boosts_exact_token_overlap(self):
        # Result 1 has higher initial score, but Result 2 contains exact specific term 'urokinase'
        r1 = make_dummy_result("1", "treatment of myocardial infarction with standard drugs", 0.80)
        r2 = make_dummy_result("2", "urokinase dosage and administration protocol", 0.75)

        reranker = TFIDFReranker(blend_alpha=0.6)
        query = "urokinase administration"
        reranked = reranker.rerank(query, [r1, r2])

        assert len(reranked) == 2
        # r2 should now rank higher due to strong token overlap with 'urokinase' and 'administration'
        assert reranked[0].unit_id == "2"

    def test_reranker_preserves_metadata(self):
        r = make_dummy_result("unit_123", "beta blockers in STEMI", 0.85)
        reranker = TFIDFReranker()
        reranked = reranker.rerank("beta blockers", [r])
        assert len(reranked) == 1
        res = reranked[0]
        assert res.unit_id == "unit_123"
        assert res.document_id == "ICMR-CARD-006"
        assert res.condition == "STEMI"
        assert res.page_number == 1
        assert res.section == "Treatment"
        assert res.entity_type == "medication"
        assert res.source_reference == {"doc": "ICMR-CARD-006"}
