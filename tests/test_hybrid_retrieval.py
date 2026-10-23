"""Tests for Hybrid RRF retrieval in ICMR STW knowledge system."""

import pytest
from pathlib import Path

from src.knowledge.indexer import KnowledgeIndexer
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.models import RetrievalQuery, RetrievalResult


@pytest.fixture(scope="module")
def indexer():
    idx = KnowledgeIndexer(
        structured_dir=Path("data/processed/structured"),
        knowledge_dir=Path("data/knowledge"),
    )
    idx.load()
    return idx


@pytest.fixture(scope="module")
def hybrid_retriever(indexer):
    return HybridRetriever(indexer)


class TestHybridRetrievalBasics:
    """Test hybrid BM25 + TF-IDF RRF retrieval."""

    def test_basic_hybrid_retrieval(self, hybrid_retriever):
        query = RetrievalQuery(query="streptokinase contraindications STEMI", top_k=5)
        results = hybrid_retriever.retrieve(query)
        assert len(results) > 0
        assert isinstance(results[0], RetrievalResult)
        assert results[0].rank == 1

    def test_no_duplicate_units(self, hybrid_retriever):
        query = RetrievalQuery(query="acute myocardial infarction thrombolysis", top_k=10)
        results = hybrid_retriever.retrieve(query)
        unit_ids = [r.unit_id for r in results]
        assert len(unit_ids) == len(set(unit_ids)), "Duplicate units found in hybrid results"

    def test_rank_sequence(self, hybrid_retriever):
        query = RetrievalQuery(query="hypertension guidelines", top_k=7)
        results = hybrid_retriever.retrieve(query)
        for expected_rank, r in enumerate(results, start=1):
            assert r.rank == expected_rank

    def test_scores_are_bounded(self, hybrid_retriever):
        query = RetrievalQuery(query="heart failure management", top_k=5)
        results = hybrid_retriever.retrieve(query)
        for r in results:
            assert 0.0 <= r.score <= 1.0


class TestHybridFiltering:
    """Test filtering applied in hybrid pipeline."""

    def test_filter_by_document(self, hybrid_retriever):
        query = RetrievalQuery(
            query="diagnosis and evaluation",
            document_id="ICMR-CARD-006",
            top_k=5,
        )
        results = hybrid_retriever.retrieve(query)
        assert len(results) > 0
        for r in results:
            assert r.document_id == "ICMR-CARD-006"

    def test_filter_by_entity_type(self, hybrid_retriever):
        query = RetrievalQuery(
            query="investigations laboratory ECG",
            entity_type="investigation",
            top_k=5,
        )
        results = hybrid_retriever.retrieve(query)
        assert len(results) > 0
        for r in results:
            assert r.entity_type == "investigation"


class TestHybridAbstention:
    """Test negative queries and abstention behavior."""

    def test_completely_out_of_domain_query(self, hybrid_retriever):
        query = RetrievalQuery(query="quantum string theory gravity black hole physics", top_k=5)
        results = hybrid_retriever.retrieve(query)
        # Should return empty list indicating no reliable evidence
        assert len(results) == 0

    def test_empty_query(self, hybrid_retriever):
        query = RetrievalQuery(query="", top_k=5)
        results = hybrid_retriever.retrieve(query)
        assert len(results) == 0
