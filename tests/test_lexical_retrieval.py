"""Tests for BM25 lexical retrieval in ICMR STW knowledge system."""

import pytest
from pathlib import Path

from src.knowledge.indexer import KnowledgeIndexer
from src.retrieval.lexical import LexicalRetriever
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
def retriever(indexer):
    return LexicalRetriever(indexer)


class TestBM25RetrievalBasics:
    """Test basic BM25 retrieval functionality."""

    def test_basic_query_returns_results(self, retriever):
        query = RetrievalQuery(query="streptokinase dose STEMI", top_k=5)
        results = retriever.retrieve(query)
        assert len(results) > 0
        assert isinstance(results[0], RetrievalResult)
        assert results[0].rank == 1

    def test_results_ordered_by_score_descending(self, retriever):
        query = RetrievalQuery(query="aspirin clopidogrel loading dose", top_k=5)
        results = retriever.retrieve(query)
        assert len(results) >= 2
        for i in range(len(results) - 1):
            assert results[i].score >= results[i + 1].score

    def test_ranks_are_sequential(self, retriever):
        query = RetrievalQuery(query="hypertension treatment", top_k=5)
        results = retriever.retrieve(query)
        for expected_rank, res in enumerate(results, start=1):
            assert res.rank == expected_rank

    def test_top_k_respected(self, retriever):
        for k in [1, 3, 7]:
            query = RetrievalQuery(query="heart failure", top_k=k)
            results = retriever.retrieve(query)
            assert len(results) <= k


class TestBM25MetadataFiltering:
    """Test metadata pre-filters before scoring."""

    def test_filter_by_document_id(self, retriever):
        query = RetrievalQuery(
            query="chest pain management",
            document_id="ICMR-CARD-006",
            top_k=10,
        )
        results = retriever.retrieve(query)
        assert len(results) > 0
        for r in results:
            assert r.document_id == "ICMR-CARD-006"

    def test_filter_by_condition(self, retriever):
        query = RetrievalQuery(
            query="diagnosis",
            condition="STEMI",
            top_k=5,
        )
        results = retriever.retrieve(query)
        assert len(results) > 0
        for r in results:
            assert r.condition == "STEMI"

    def test_filter_by_entity_type(self, retriever):
        query = RetrievalQuery(
            query="aspirin",
            entity_type="medication",
            top_k=5,
        )
        results = retriever.retrieve(query)
        assert len(results) > 0
        for r in results:
            assert r.entity_type == "medication"

    def test_filter_nonexistent_returns_empty(self, retriever):
        query = RetrievalQuery(
            query="streptokinase",
            document_id="NON-EXISTENT-ID",
            top_k=5,
        )
        results = retriever.retrieve(query)
        assert results == []


class TestBM25EdgeCases:
    """Test edge cases such as empty queries or punctuation."""

    def test_empty_query_returns_empty(self, retriever):
        query = RetrievalQuery(query="", top_k=5)
        results = retriever.retrieve(query)
        assert results == []

    def test_punctuation_only_query_returns_empty(self, retriever):
        query = RetrievalQuery(query="??? ... !!!", top_k=5)
        results = retriever.retrieve(query)
        assert results == []

    def test_no_credential_leakage(self, retriever):
        query = RetrievalQuery(query="thrombolysis", top_k=3)
        results = retriever.retrieve(query)
        assert len(results) > 0
        for r in results:
            d = r.to_dict()
            for key in ["password", "secret", "token", "db_path", "connection_string"]:
                assert key not in d
