"""Tests for TF-IDF semantic retrieval in ICMR STW knowledge system."""

import pytest
from pathlib import Path

from src.knowledge.indexer import KnowledgeIndexer
from src.retrieval.models import RetrievalQuery, RetrievalResult
from src.retrieval.semantic import SemanticRetriever


@pytest.fixture(scope="module")
def indexer():
    idx = KnowledgeIndexer(
        structured_dir=Path("data/processed/structured"),
        knowledge_dir=Path("data/knowledge"),
    )
    idx.load()
    return idx


@pytest.fixture(scope="module")
def retriever(indexer):
    return SemanticRetriever(indexer)


class TestSemanticRetrievalBasics:
    """Test TF-IDF cosine similarity retrieval."""

    def test_basic_semantic_query(self, retriever):
        query = RetrievalQuery(query="thrombolytic therapy myocardial infarction", top_k=5)
        results = retriever.retrieve(query)
        assert len(results) > 0
        assert isinstance(results[0], RetrievalResult)
        assert results[0].rank == 1
        assert results[0].score > 0.0

    def test_score_ordering(self, retriever):
        query = RetrievalQuery(query="heart failure ejection fraction guideline", top_k=5)
        results = retriever.retrieve(query)
        assert len(results) >= 2
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    def test_top_k_parameter(self, retriever):
        query = RetrievalQuery(query="hypertension treatment stage 1", top_k=3)
        results = retriever.retrieve(query)
        assert len(results) <= 3


class TestSemanticMetadataFiltering:
    """Test pre-filtering in semantic retriever."""

    def test_filter_by_condition(self, retriever):
        query = RetrievalQuery(
            query="acute coronary syndrome management",
            condition="STEMI",
            top_k=5,
        )
        results = retriever.retrieve(query)
        assert len(results) > 0
        for r in results:
            assert r.condition == "STEMI"

    def test_filter_by_document_id(self, retriever):
        query = RetrievalQuery(
            query="blood pressure targets",
            document_id="ICMR-CARD-001",
            top_k=5,
        )
        results = retriever.retrieve(query)
        assert len(results) > 0
        for r in results:
            assert r.document_id == "ICMR-CARD-001"

    def test_filter_nonexistent_returns_empty(self, retriever):
        query = RetrievalQuery(
            query="antihypertensive",
            document_id="NON_EXISTENT_DOC",
            top_k=5,
        )
        results = retriever.retrieve(query)
        assert results == []


class TestSemanticEdgeCases:
    """Test semantic retriever edge cases."""

    def test_completely_unrelated_query(self, retriever):
        # Query with terms completely outside vocabulary
        query = RetrievalQuery(query="quantum cryptography astrophysics telescope", top_k=5)
        results = retriever.retrieve(query)
        # Should either return empty or results with zero/very low scores
        assert len(results) == 0

    def test_empty_query(self, retriever):
        query = RetrievalQuery(query="", top_k=5)
        results = retriever.retrieve(query)
        assert results == []
