"""Tests for PDFLoader module."""

from pathlib import Path
import pytest
from src.extraction.pdf_loader import PDFLoader


VALID_PDF = Path("data/raw/cardiology/1768823342_cardiology_1-5.pdf")
CONSOLIDATED_PDF = Path("data/raw/cardiology/1771492083_cardiology_all.pdf")


def test_pdf_loader_valid():
    """Verify loading a valid single-page STW PDF."""
    assert VALID_PDF.exists()
    doc = PDFLoader.load(VALID_PDF, document_id="ICMR-CARD-006")
    assert doc.document_id == "ICMR-CARD-006"
    assert doc.page_count == 1
    assert len(doc.sha256_hash) == 64

    page1 = doc.get_page(1)
    assert page1.page_number == 1
    assert page1.width > 0
    assert page1.height > 0
    assert len(page1.raw_text) > 500
    doc.close()


def test_pdf_loader_multi_page():
    """Verify loading a multi-page consolidated STW PDF."""
    assert CONSOLIDATED_PDF.exists()
    doc = PDFLoader.load(CONSOLIDATED_PDF, document_id="ICMR-CARD-007")
    assert doc.page_count == 16
    assert len(doc.pages) == 16

    page8 = doc.get_page(8)
    assert page8.page_number == 8
    assert "ATRIAL FIBRILLATION" in page8.raw_text
    doc.close()


def test_pdf_loader_invalid_path():
    """Verify error handling for nonexistent or non-pdf paths."""
    with pytest.raises(FileNotFoundError):
        PDFLoader.load("data/raw/cardiology/nonexistent.pdf")

    with pytest.raises(ValueError):
        PDFLoader.load("README.md")


def test_pdf_loader_page_out_of_bounds():
    """Verify error handling when accessing out of range pages."""
    doc = PDFLoader.load(VALID_PDF, document_id="ICMR-CARD-006")
    with pytest.raises(IndexError):
        doc.get_page(0)
    with pytest.raises(IndexError):
        doc.get_page(2)
    doc.close()
