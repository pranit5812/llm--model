"""Extraction package for ICMR STW documents."""

from src.extraction.pdf_loader import LoadedDocument, PageData, PDFLoader
from src.extraction.provenance import create_source_reference
from src.extraction.section_detector import DetectedSection, SectionCategory, SectionDetector
from src.extraction.stw_mapper import ExtractionAuditReport, STWMapper
from src.extraction.table_extractor import TableExtractor
from src.extraction.text_extractor import (
    ExtractedDocument,
    ExtractedPage,
    TextBlock,
    TextExtractor,
    TextLine,
    TextSpan,
)

__all__ = [
    "PDFLoader",
    "LoadedDocument",
    "PageData",
    "create_source_reference",
    "TextExtractor",
    "ExtractedDocument",
    "ExtractedPage",
    "TextBlock",
    "TextLine",
    "TextSpan",
    "TableExtractor",
    "SectionCategory",
    "DetectedSection",
    "SectionDetector",
    "STWMapper",
    "ExtractionAuditReport",
]
