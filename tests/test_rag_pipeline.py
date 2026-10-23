"""Tests for end-to-end Grounded RAG pipeline."""

import pytest

from src.llm.schemas import RAGResponse, RAGResponseStatus
from src.rag.pipeline import RAGPipeline


@pytest.fixture(scope="module")
def pipeline():
    return RAGPipeline(top_k=5)


class TestRAGPipelineEndToEnd:
    """Verify full RAG pipeline behavior on clinical queries."""

    def test_direct_factual_query(self, pipeline):
        resp = pipeline.answer("What is the loading dose of aspirin in STEMI?", debug=True)
        assert isinstance(resp, RAGResponse)
        assert resp.status == RAGResponseStatus.GROUNDED
        assert resp.abstained is False
        assert len(resp.citations) > 0
        # Citation fields check
        c0 = resp.citations[0]
        assert c0.document_id.startswith("ICMR-CARD-")
        assert c0.page_number >= 1
        assert len(c0.source_text_reference) > 0
        # Disclaimer check
        assert resp.clinical_disclaimer is not None
        assert "Indian Council of Medical Research" in resp.clinical_disclaimer
        # Debug check
        assert resp.debug_info is not None
        assert "retrieval_latency_sec" in resp.debug_info

    def test_contraindication_query(self, pipeline):
        resp = pipeline.answer("What are the contraindications to thrombolysis in STEMI?")
        assert resp.status == RAGResponseStatus.GROUNDED
        assert resp.abstained is False
        assert len(resp.citations) > 0
        assert any(c.document_id == "ICMR-CARD-006" for c in resp.citations)

    def test_healthcare_tier_query(self, pipeline):
        resp = pipeline.answer("What STEMI management is described at the community health centre (CHC)?")
        assert resp.status == RAGResponseStatus.GROUNDED
        assert resp.abstained is False
        assert len(resp.citations) > 0

    def test_referral_query(self, pipeline):
        resp = pipeline.answer("When is referral indicated for complete heart block?")
        assert resp.status == RAGResponseStatus.GROUNDED
        assert resp.abstained is False
        assert len(resp.citations) > 0

    def test_safe_abstention_out_of_scope(self, pipeline):
        resp = pipeline.answer("What is the recommended treatment for dengue fever?")
        assert resp.status == RAGResponseStatus.OUT_OF_SCOPE
        assert resp.abstained is True
        assert len(resp.citations) == 0
        assert "outside the clinical scope" in resp.answer

    def test_no_credential_leak_in_debug(self, pipeline):
        resp = pipeline.answer("STEMI aspirin", debug=True)
        dbg_str = str(resp.debug_info).lower()
        for forbidden in ["password", "secret", "api_key", "token", "c:\\", "d:\\"]:
            assert forbidden not in dbg_str, f"Leaked {forbidden} in debug info"
