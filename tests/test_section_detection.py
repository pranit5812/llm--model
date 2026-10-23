"""Tests for SectionDetector module."""

from pathlib import Path
import pytest

from src.extraction.pdf_loader import PDFLoader
from src.extraction.section_detector import DetectedSection, SectionCategory, SectionDetector
from src.extraction.text_extractor import TextExtractor


VALID_PDF = Path("data/raw/cardiology/1768823342_cardiology_1-5.pdf")


def test_heading_classification():
    """Verify regex heading classifier for standard STW titles."""
    assert SectionDetector.classify_heading("GENERAL MEASURES") == SectionCategory.MANAGEMENT_TIERS
    assert SectionDetector.classify_heading("DRUGS & DOSAGE") == SectionCategory.DRUGS_DOSAGE
    assert SectionDetector.classify_heading("ABSOLUTE CONTRA-INDICATIONS TO THROMBOLYIC THERAPY") == SectionCategory.CONTRAINDICATIONS
    assert SectionDetector.classify_heading("BASIC INVESTIGATIONS") == SectionCategory.INVESTIGATIONS
    assert SectionDetector.classify_heading("CONSIDER ANGINA IF") == SectionCategory.CLINICAL_PRESENTATION
    assert SectionDetector.classify_heading("STEMI DIAGNOSIS*") == SectionCategory.DIAGNOSTIC_CRITERIA
    assert SectionDetector.classify_heading("REFERENCES") == SectionCategory.REFERENCES


def test_section_detection_stemi():
    """Verify section extraction on the STEMI document."""
    doc = PDFLoader.load(VALID_PDF, document_id="ICMR-CARD-006")
    page1 = TextExtractor.extract_page(doc.get_page(1))
    sections = SectionDetector.detect_sections(page1)

    assert len(sections) >= 10
    categories = {s.category for s in sections}

    # STEMI must have clinical presentation, management, drugs, contraindications
    assert SectionCategory.CLINICAL_PRESENTATION in categories
    assert SectionCategory.MANAGEMENT_TIERS in categories
    assert SectionCategory.DRUGS_DOSAGE in categories
    assert SectionCategory.CONTRAINDICATIONS in categories

    # Verify each section has blocks and bboxes
    for sec in sections:
        assert isinstance(sec, DetectedSection)
        assert len(sec.blocks) > 0
        assert len(sec.bbox) == 4
        assert sec.page_number == 1

    doc.close()
