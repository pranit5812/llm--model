"""Tests for citation validation against SQLite knowledge store."""

from pathlib import Path
import pytest

from src.llm.citation_validator import CitationValidator
from src.llm.schemas import CitationItem


@pytest.fixture(scope="module")
def validator():
    return CitationValidator(db_path=Path("data/knowledge/knowledge.db"))


class TestCitationValidator:
    """Verify database verification rules for clinical citations."""

    def test_valid_citation_passes(self, validator):
        # Existing known production unit in SQLite
        citation = CitationItem(
            document_id="ICMR-CARD-006",
            condition="STEMI",
            page_number=1,
            section="MANAGEMENT OF STEMI AT PHC / NON-PCI CAPABLE HOSPITAL",
            knowledge_unit_id="ICMR-CARD-006:medication:0000",
            source_text_reference="STEMI medication: Aspirin",
        )
        retrieved_set = {"ICMR-CARD-006:medication:0000"}
        res = validator.validate_citations([citation], retrieved_set)
        assert res.is_valid is True
        assert len(res.verified_citations) == 1
        assert len(res.rejected_citations) == 0

    def test_rejects_citation_not_in_retrieved_pool(self, validator):
        citation = CitationItem(
            document_id="ICMR-CARD-006",
            condition="STEMI",
            page_number=1,
            section="MANAGEMENT OF STEMI AT PHC / NON-PCI CAPABLE HOSPITAL",
            knowledge_unit_id="ICMR-CARD-006:medication:0000",
            source_text_reference="STEMI medication: Aspirin",
        )
        # Unit exists in DB but was NOT in the retrieved evidence candidate pool
        res = validator.validate_citations([citation], retrieved_unit_ids={"OTHER_UNIT"})
        assert res.is_valid is False
        assert len(res.rejected_citations) == 1
        assert "not in the retrieved evidence pool" in res.rejection_reasons[0]

    def test_rejects_hallucinated_unit_id(self, validator):
        citation = CitationItem(
            document_id="ICMR-CARD-006",
            condition="STEMI",
            page_number=1,
            section="MANAGEMENT",
            knowledge_unit_id="ICMR-FAKE-999:unit:0000",
            source_text_reference="Fake drug",
        )
        res = validator.validate_citations([citation], retrieved_unit_ids={"ICMR-FAKE-999:unit:0000"})
        assert res.is_valid is False
        assert len(res.rejected_citations) == 1
        assert "not found in SQLite" in res.rejection_reasons[0]

    def test_rejects_document_id_mismatch(self, validator):
        citation = CitationItem(
            document_id="WRONG-DOC-ID",
            condition="STEMI",
            page_number=1,
            section="MANAGEMENT",
            knowledge_unit_id="ICMR-CARD-006:medication:0000",
            source_text_reference="Aspirin",
        )
        res = validator.validate_citations([citation], retrieved_unit_ids={"ICMR-CARD-006:medication:0000"})
        assert res.is_valid is False
        assert "Document ID mismatch" in res.rejection_reasons[0]

    def test_rejects_page_number_mismatch(self, validator):
        citation = CitationItem(
            document_id="ICMR-CARD-006",
            condition="STEMI",
            page_number=99,  # Incorrect page
            section="MANAGEMENT",
            knowledge_unit_id="ICMR-CARD-006:medication:0000",
            source_text_reference="Aspirin",
        )
        res = validator.validate_citations([citation], retrieved_unit_ids={"ICMR-CARD-006:medication:0000"})
        assert res.is_valid is False
        assert "Page mismatch" in res.rejection_reasons[0]
