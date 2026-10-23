"""Tests for provenance tracking and citation integrity in retrieval results."""

import pytest
from pathlib import Path

from src.knowledge.indexer import KnowledgeIndexer
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.models import RetrievalQuery


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


class TestProvenanceIntegrity:
    """Verify that every retrieved result has complete, verifiable clinical provenance."""

    def test_all_results_have_provenance(self, hybrid_retriever):
        query = RetrievalQuery(query="ECG troponin chest pain", top_k=10)
        results = hybrid_retriever.retrieve(query)
        assert len(results) > 0

        for r in results:
            assert r.document_id.startswith("ICMR-CARD-")
            assert len(r.condition) > 0
            assert r.page_number >= 1
            assert len(r.section) > 0
            assert len(r.entity_type) > 0
            assert isinstance(r.source_reference, dict)
            assert len(r.source_reference) > 0

    def test_citation_structure(self, hybrid_retriever):
        query = RetrievalQuery(query="thrombolysis STEMI", top_k=5)
        results = hybrid_retriever.retrieve(query)
        assert len(results) > 0

        for r in results:
            citation = r.citation
            assert isinstance(citation, dict)
            assert citation["organization"] == "Indian Council of Medical Research (ICMR)"
            assert citation["document_id"] == r.document_id
            assert citation["condition"] == r.condition
            assert citation["page_number"] == str(r.page_number)
            assert citation["section"] == r.section
            assert "source_text_reference" in citation

    def test_no_internal_paths_or_secrets_exposed(self, hybrid_retriever):
        query = RetrievalQuery(query="hypertension emergency", top_k=5)
        results = hybrid_retriever.retrieve(query)
        assert len(results) > 0

        forbidden_substrings = ["c:\\", "d:\\", "/data/knowledge", "knowledge.db", "password", "secret"]
        for r in results:
            d_str = str(r.to_dict()).lower()
            for forbidden in forbidden_substrings:
                assert forbidden not in d_str, f"Found leaked internal string '{forbidden}' in result"
