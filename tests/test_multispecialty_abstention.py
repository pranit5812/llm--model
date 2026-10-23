"""Tests for 5-way clinical abstention in the multi-specialty RAG pipeline."""

import pytest

from src.knowledge.indexer import KnowledgeIndexer
from src.llm.schemas import RAGResponseStatus
from src.rag.pipeline import RAGPipeline


@pytest.fixture(scope="module")
def rag_pipeline():
    indexer = KnowledgeIndexer()
    indexer.load()
    return RAGPipeline(indexer=indexer)


def test_out_of_scope_abstention(rag_pipeline):
    query = "What is the fluid resuscitation protocol for severe dengue fever with shock?"
    response = rag_pipeline.answer(query=query)
    assert response.status == RAGResponseStatus.OUT_OF_SCOPE
    assert response.abstained is True
    assert len(response.citations) == 0


def test_insufficient_approved_evidence_abstention(rag_pipeline):
    query = "What is the first-line antiepileptic drug for generalized tonic-clonic seizures in adults?"
    response = rag_pipeline.answer(query=query)
    assert response.status == RAGResponseStatus.INSUFFICIENT_APPROVED_EVIDENCE
    assert response.abstained is True
    assert len(response.citations) == 0
    assert "pending clinical review" in response.answer.lower() or "quarantined" in str(response.cautions).lower()


def test_ambiguous_source_abstention(rag_pipeline):
    query = "What is the emergency thrombolysis protocol for tissue infarction?"
    response = rag_pipeline.answer(query=query)
    assert response.status == RAGResponseStatus.AMBIGUOUS_SOURCE
    assert response.abstained is True
    assert len(response.citations) == 0


def test_version_conflict_abstention(rag_pipeline):
    query = "What are the differences between 2019 and 2022 guidelines for hypertension targets?"
    response = rag_pipeline.answer(query=query)
    assert response.status == RAGResponseStatus.VERSION_CONFLICT
    assert response.abstained is True
    assert len(response.citations) == 0


def test_cardiology_grounded_success(rag_pipeline):
    query = "What is the recommended loading dose of aspirin in STEMI?"
    response = rag_pipeline.answer(query=query)
    assert response.status in [RAGResponseStatus.GROUNDED, RAGResponseStatus.PARTIALLY_GROUNDED]
    assert response.abstained is False
    assert len(response.citations) > 0
    assert all(c.document_id.startswith("ICMR-CARD") for c in response.citations)
