"""Tests for TableExtractor module."""

from pathlib import Path
import pytest
from src.extraction.pdf_loader import PDFLoader
from src.extraction.table_extractor import TableExtractor
from src.models.stw_schema import ReviewStatus, STWTable


VALID_PDF = Path("data/raw/cardiology/1768823342_cardiology_1-5.pdf")


def test_table_extraction_stemi():
    """Verify table extraction from STEMI PDF."""
    doc = PDFLoader.load(VALID_PDF, document_id="ICMR-CARD-006")
    page1 = doc.get_page(1)
    tables = TableExtractor.extract_tables_from_page(
        page_data=page1,
        document_id="ICMR-CARD-006",
        document_name="STEMI",
    )

    assert len(tables) >= 1
    for tab in tables:
        assert isinstance(tab, STWTable)
        assert tab.source.document_id == "ICMR-CARD-006"
        assert tab.source.page_number == 1
        assert len(tab.headers) > 0
        assert len(tab.rows) > 0

        # Verify row cells match declared headers
        header_set = set(tab.headers)
        for row in tab.rows:
            assert set(row.cells.keys()) == header_set
            assert row.source.document_id == "ICMR-CARD-006"

    doc.close()


def test_table_extraction_provenance_and_review_flags():
    """Verify table provenance fields and review flags."""
    doc = PDFLoader.load(VALID_PDF, document_id="ICMR-CARD-006")
    tables = TableExtractor.extract_tables_from_page(
        page_data=doc.get_page(1),
        document_id="ICMR-CARD-006",
        document_name="STEMI",
    )

    for tab in tables:
        assert tab.source.extraction_type == "table"
        assert tab.source.review_status in (ReviewStatus.EXTRACTED, ReviewStatus.NEEDS_REVIEW)
        if tab.source.requires_manual_review:
            assert tab.source.review_notes is not None

    doc.close()
