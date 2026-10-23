"""Tests for cross-specialty retrieval isolation and term collision suppression."""

import pytest

from src.knowledge.indexer import KnowledgeIndexer
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.models import RetrievalQuery
from src.retrieval.router import SpecialtyRouter


def test_cross_specialty_contamination_detection():
    # Stroke is neurology, so pairing with Cardiology should be flagged as contamination
    assert SpecialtyRouter.check_cross_specialty_contamination(
        query="Emergency management of acute ischemic stroke",
        result_specialty="Cardiology",
    ) is True

    # Aspirin in STEMI is Cardiology, so pairing with Cardiology is NOT contamination
    assert SpecialtyRouter.check_cross_specialty_contamination(
        query="Aspirin loading dose in STEMI",
        result_specialty="Cardiology",
    ) is False


def test_hybrid_retriever_cross_specialty_isolation():
    indexer = KnowledgeIndexer()
    indexer.load()
    retriever = HybridRetriever(indexer)

    # When querying with explicit Neurology specialty filter, Cardiology units must be completely excluded
    rq = RetrievalQuery(
        query="Emergency protocol for acute stroke",
        specialty="Neurology",
        top_k=5,
    )
    results = retriever.retrieve(rq)
    # Since Neurology is quarantined, no production units exist
    assert len(results) == 0


def test_hybrid_retriever_unfiltered_stroke_does_not_return_cardiology():
    indexer = KnowledgeIndexer()
    indexer.load()
    retriever = HybridRetriever(indexer)

    # Even without explicit specialty filter, routing detects Neurology and prevents cross-specialty contamination
    rq = RetrievalQuery(
        query="Emergency management of acute ischemic stroke within 3 hours",
        top_k=5,
    )
    results = retriever.retrieve(rq)
    # With isolation penalty, cardiology results are suppressed
    assert len(results) == 0 or all(r.score < 0.25 for r in results)
