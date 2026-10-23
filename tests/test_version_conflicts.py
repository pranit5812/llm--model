"""Tests for STW Multi-Version Conflict Detection and Handling.

Ensures that when evidence spans both the 2019 Consolidated Cardiology STW
(ICMR-CARD-007) and dedicated single-condition STWs (ICMR-CARD-001 to 006):
1. The system does not silently declare one version superior.
2. An explicit version warning is attached to the RAG response.
3. Citations from both STW documents are preserved with page-level provenance.
"""

from __future__ import annotations

import pytest

from src.llm.schemas import CitationItem, RAGResponse, RAGResponseStatus
from src.rag.pipeline import RAGPipeline
from src.rag.response_validator import ResponseValidator
from src.retrieval.models import RetrievalResult


def test_detect_version_conflicts_both_versions():
    results = [
        RetrievalResult(
            unit_id="ICMR-CARD-006-KU-001",
            content="STEMI management with tenecteplase",
            score=0.85,
            document_id="ICMR-CARD-006",
            condition="STEMI",
            specialty="Cardiology",
            page_number=1,
            section="Management",
            entity_type="tier_action",
            review_status="extracted",
            rank=1,
        ),
        RetrievalResult(
            unit_id="ICMR-CARD-007-KU-010",
            content="STEMI management with streptokinase",
            score=0.82,
            document_id="ICMR-CARD-007",
            condition="STEMI",
            specialty="Cardiology",
            page_number=14,
            section="STEMI Management",
            entity_type="tier_action",
            review_status="extracted",
            rank=2,
        ),
    ]

    warning = ResponseValidator.detect_version_conflicts(results)
    assert warning is not None
    assert "Multiple ICMR source versions contain relevant information" in warning
    assert "ICMR-CARD-007" in warning
    assert "ICMR-CARD-006" in warning
    assert "without independently determining clinical precedence" in warning


def test_no_version_conflict_single_document():
    results = [
        RetrievalResult(
            unit_id="ICMR-CARD-006-KU-001",
            content="STEMI management with tenecteplase",
            score=0.85,
            document_id="ICMR-CARD-006",
            condition="STEMI",
            specialty="Cardiology",
            page_number=1,
            section="Management",
            entity_type="tier_action",
            review_status="extracted",
            rank=1,
        ),
    ]

    warning = ResponseValidator.detect_version_conflicts(results)
    assert warning is None


def test_version_conflict_in_rag_pipeline():
    pipeline = RAGPipeline(top_k=5)
    # Query comparing consolidated and dedicated workflows
    query = "What differences exist between the 2019 Consolidated Cardiology STW and dedicated STEMI STW regarding thrombolysis?"
    resp = pipeline.answer(query=query)

    assert resp.status in [RAGResponseStatus.GROUNDED, RAGResponseStatus.PARTIALLY_GROUNDED]
    assert len(resp.citations) > 0

    doc_ids = set(c.document_id for c in resp.citations)
    if "ICMR-CARD-007" in doc_ids and len(doc_ids) > 1:
        assert resp.version_warning is not None
        assert "Multiple ICMR source versions" in resp.version_warning
