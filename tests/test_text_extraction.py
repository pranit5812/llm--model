"""Tests for TextExtractor module."""

import json
from pathlib import Path
import pytest

from src.extraction.pdf_loader import PDFLoader
from src.extraction.text_extractor import TextExtractor


VALID_PDF = Path("data/raw/cardiology/1768823342_cardiology_1-5.pdf")


def test_text_extraction_single_page():
    """Verify text block extraction and coordinate preservation on a page."""
    doc = PDFLoader.load(VALID_PDF, document_id="ICMR-CARD-006")
    page_data = doc.get_page(1)
    extracted_page = TextExtractor.extract_page(page_data)

    assert extracted_page.page_number == 1
    assert extracted_page.width > 0
    assert len(extracted_page.blocks) > 20

    # Verify bounding boxes and lines
    for block in extracted_page.blocks:
        assert len(block.bbox) == 4
        assert block.bbox[0] <= block.bbox[2]
        assert block.bbox[1] <= block.bbox[3]
        assert len(block.lines) > 0
        assert block.avg_font_size > 0

    doc.close()


def test_bullet_and_number_detection():
    """Verify bullet point and numbered item detection."""
    doc = PDFLoader.load(VALID_PDF, document_id="ICMR-CARD-006")
    extracted_page = TextExtractor.extract_page(doc.get_page(1))

    numbered_lines = []
    bullet_lines = []
    for b in extracted_page.blocks:
        for line in b.lines:
            if line.is_numbered:
                numbered_lines.append(line.text)
            if line.is_bullet:
                bullet_lines.append(line.text)

    # In STEMI, GENERAL MEASURES has "1. Admit in ICU...", "2. Routine bio-chemistry..."
    assert len(numbered_lines) >= 3
    doc.close()


def test_extracted_document_serialization(tmp_path):
    """Verify intermediate ExtractedDocument JSON serialization."""
    doc = PDFLoader.load(VALID_PDF, document_id="ICMR-CARD-006")
    extracted_doc = TextExtractor.extract_document(doc)

    out_file = tmp_path / "test_extracted.json"
    extracted_doc.save_json(out_file)
    assert out_file.exists()

    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["document_id"] == "ICMR-CARD-006"
    assert data["total_pages"] == 1
    assert len(data["pages"][0]["blocks"]) == len(extracted_doc.pages[0].blocks)
    doc.close()
