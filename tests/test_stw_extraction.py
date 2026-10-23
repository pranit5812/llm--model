"""End-to-end tests for the complete ICMR STW extraction pipeline."""

import hashlib
import json
from pathlib import Path
import pytest
import pandas as pd

from src.extraction.pdf_loader import PDFLoader
from src.extraction.stw_mapper import STWMapper
from src.extraction.table_extractor import TableExtractor
from src.extraction.text_extractor import TextExtractor
from src.models.stw_schema import STWDocument


CATALOG_PATH = Path("data/metadata/stw_catalog.csv")
STRUCTURED_DIR = Path("data/processed/structured")
REPORTS_DIR = Path("data/review/extraction_reports")


def test_stemi_end_to_end_extraction():
    """Verify complete extraction and Pydantic validation for STEMI (ICMR-CARD-006)."""
    pdf_path = Path("data/raw/cardiology/1768823342_cardiology_1-5.pdf")
    loaded_doc = PDFLoader.load(pdf_path, document_id="ICMR-CARD-006")
    extracted_doc = TextExtractor.extract_document(loaded_doc)

    tables = []
    for p in loaded_doc.pages:
        tabs = TableExtractor.extract_tables_from_page(p, "ICMR-CARD-006", "STEMI")
        tables.extend(tabs)

    catalog_entry = {
        "stw_id": "ICMR-CARD-006",
        "condition": "STEMI",
        "specialty": "Cardiology",
        "icd_11_code": "BA41.0",
        "volume": "Volume 1",
        "version": "1.0",
        "source_organization": "Indian Council of Medical Research (ICMR)",
        "local_path": str(pdf_path),
    }

    stw_doc, audit_report = STWMapper.map_document(extracted_doc, catalog_entry, tables)

    # Validate with Pydantic
    json_str = stw_doc.model_dump_json()
    reloaded = STWDocument.model_validate_json(json_str)

    assert reloaded.metadata.document_id == "ICMR-CARD-006"
    assert reloaded.clinical_presentation is not None
    assert len(reloaded.medications) >= 5
    assert len(reloaded.contraindications) >= 5
    assert audit_report.provenance_coverage_percent == 100.0
    assert audit_report.manual_review_items_count > 0  # Typos detected and flagged

    loaded_doc.close()


def test_all_structured_json_files_exist_and_validate():
    """Verify that all 7 structured JSON outputs exist and pass STWDocument validation."""
    assert CATALOG_PATH.exists()
    df = pd.read_csv(CATALOG_PATH)

    for _, row in df.iterrows():
        doc_id = row["stw_id"]
        json_path = STRUCTURED_DIR / f"{doc_id}.json"
        report_path = REPORTS_DIR / f"{doc_id}.json"

        assert json_path.exists(), f"Structured JSON missing for {doc_id}"
        assert report_path.exists(), f"Audit report missing for {doc_id}"

        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Must pass Pydantic validation
        stw_doc = STWDocument.model_validate(data)
        assert stw_doc.metadata.document_id == doc_id
        assert stw_doc.metadata.condition == row["condition"]

        # Verify audit report
        with open(report_path, "r", encoding="utf-8") as f:
            report_data = json.load(f)

        assert report_data["document_id"] == doc_id
        assert report_data["provenance_coverage_percent"] == 100.0
        assert len(report_data["extraction_errors"]) == 0


def test_provenance_integrity_across_entities():
    """Verify that every clinical entity in structured JSON files has valid source provenance."""
    json_files = list(STRUCTURED_DIR.glob("*.json"))
    assert len(json_files) == 7

    for jf in json_files:
        with open(jf, "r", encoding="utf-8") as f:
            doc = STWDocument.model_validate(json.load(f))

        if doc.clinical_presentation:
            assert doc.clinical_presentation.source.page_number >= 1
            assert len(doc.clinical_presentation.source.source_text_reference) > 0

        for med in doc.medications:
            assert med.source.page_number >= 1
            assert len(med.source.source_text_reference) > 0

        for inv in doc.investigations:
            assert inv.source.page_number >= 1
            assert len(inv.source.source_text_reference) > 0

        for ci in doc.contraindications:
            assert ci.source.page_number >= 1
            assert len(ci.source.source_text_reference) > 0

        for ref in doc.referral_criteria:
            assert ref.source.page_number >= 1
            assert len(ref.source.source_text_reference) > 0

        for fc in doc.flowcharts:
            assert fc.source.page_number >= 1
            for n in fc.nodes:
                assert n.source.page_number >= 1


def test_raw_pdfs_remain_unmodified():
    """Verify that all raw PDFs have identical SHA-256 hashes matching the catalog."""
    df = pd.read_csv(CATALOG_PATH)
    for _, row in df.iterrows():
        p = Path(row["local_path"])
        expected_hash = row["document_hash"]
        with open(p, "rb") as f:
            actual_hash = hashlib.sha256(f.read()).hexdigest()
        assert actual_hash == expected_hash, f"Hash mismatch on {p}!"
