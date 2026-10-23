"""Tests for grounding validation and version conflict checks."""

import pytest

from src.llm.schemas import CitationItem, RAGResponse, RAGResponseStatus
from src.rag.response_validator import ResponseValidator
from src.retrieval.models import RetrievalResult


def make_dummy_evidence(doc_id: str, content: str) -> RetrievalResult:
    return RetrievalResult(
        unit_id=f"{doc_id}:med:0",
        content=content,
        score=0.9,
        document_id=doc_id,
        condition="STEMI" if doc_id == "ICMR-CARD-006" else "Cardiology (All)",
        specialty="Cardiology",
        page_number=1,
        section="Medication",
        entity_type="medication",
        review_status="extracted",
        source_reference={"doc": doc_id},
        rank=1,
    )


class TestResponseValidator:
    """Verify dosage verification and version conflict detection."""

    def test_detects_version_conflict_when_consolidated_and_dedicated_present(self):
        ev = [
            make_dummy_evidence("ICMR-CARD-006", "STEMI dedicated guideline"),
            make_dummy_evidence("ICMR-CARD-007", "Consolidated 2019 STW"),
        ]
        warning = ResponseValidator.detect_version_conflicts(ev)
        assert warning is not None
        assert "Multiple ICMR source versions" in warning
        assert "ICMR-CARD-007" in warning

    def test_no_version_conflict_when_single_document_version(self):
        ev = [
            make_dummy_evidence("ICMR-CARD-006", "STEMI dedicated guideline 1"),
            make_dummy_evidence("ICMR-CARD-006", "STEMI dedicated guideline 2"),
        ]
        warning = ResponseValidator.detect_version_conflicts(ev)
        assert warning is None

    def test_supported_dosage_passes(self):
        ev = [make_dummy_evidence("ICMR-CARD-006", "Give Aspirin 300 mg oral loading dose.")]
        is_grounded, unsupported = ResponseValidator.verify_dosage_grounding("Patient should receive Aspirin 300 mg.", ev)
        assert is_grounded is True
        assert unsupported == []

    def test_unsupported_dosage_flagged(self):
        ev = [make_dummy_evidence("ICMR-CARD-006", "Give Aspirin 300 mg oral loading dose.")]
        # Answer claims 1000 mg which does not exist in evidence
        is_grounded, unsupported = ResponseValidator.verify_dosage_grounding("Patient should receive Aspirin 1000 mg.", ev)
        assert is_grounded is False
        assert "1000mg" in unsupported

    def test_validate_response_downgrades_when_unsupported_dosage_present(self):
        ev = [make_dummy_evidence("ICMR-CARD-006", "Give Aspirin 300 mg.")]
        resp = RAGResponse(
            status=RAGResponseStatus.GROUNDED,
            answer="Take Aspirin 999 mg immediately.",
            citations=[
                CitationItem(
                    document_id="ICMR-CARD-006",
                    condition="STEMI",
                    page_number=1,
                    section="Medication",
                    knowledge_unit_id="ICMR-CARD-006:med:0",
                    source_text_reference="Aspirin 300 mg",
                )
            ],
            confidence="HIGH",
        )
        validated = ResponseValidator.validate_response(resp, ev)
        assert validated.status == RAGResponseStatus.PARTIALLY_GROUNDED
        assert any("Grounding Alert" in c for c in validated.cautions)
