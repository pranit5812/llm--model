"""CLI script to run the ICMR STW extraction pipeline and generate canonical representations."""

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from src.extraction.pdf_loader import PDFLoader
from src.extraction.stw_mapper import STWMapper
from src.extraction.table_extractor import TableExtractor
from src.extraction.text_extractor import TextExtractor
from src.models.stw_schema import STWDocument


def process_document(
    catalog_entry: Dict[str, Any],
    extracted_dir: Path,
    structured_dir: Path,
    reports_dir: Path,
) -> bool:
    """Run full extraction pipeline on a single document entry from the catalog."""
    doc_id = catalog_entry["stw_id"]
    pdf_path = Path(catalog_entry["local_path"])
    condition = catalog_entry.get("condition", "Unknown")

    print(f"\n=======================================================")
    print(f"Processing: {doc_id} - {condition}")
    print(f"File: {pdf_path}")
    print(f"=======================================================")

    if not pdf_path.exists():
        print(f"ERROR: PDF file not found at {pdf_path}", file=sys.stderr)
        return False

    # 1. Load document with cryptographic hash verification
    print(f"--> [1/5] Loading PDF with SHA-256 verification...")
    loaded_doc = PDFLoader.load(pdf_path, document_id=doc_id)
    print(f"    Loaded {loaded_doc.page_count} pages. Hash: {loaded_doc.sha256_hash[:16]}...")

    # 2. Extract structured text page-by-page
    print(f"--> [2/5] Extracting text layout & coordinates...")
    extracted_doc = TextExtractor.extract_document(loaded_doc)
    extracted_json_path = extracted_dir / f"{doc_id}.json"
    extracted_doc.save_json(extracted_json_path)
    print(f"    Intermediate JSON saved: {extracted_json_path}")

    # 3. Extract tables
    print(f"--> [3/5] Detecting and extracting clinical tables...")
    all_tables = []
    for page_data in loaded_doc.pages:
        tabs = TableExtractor.extract_tables_from_page(
            page_data=page_data,
            document_id=doc_id,
            document_name=condition,
        )
        all_tables.extend(tabs)
    print(f"    Extracted {len(all_tables)} tables.")

    # 4. Canonical schema mapping
    print(f"--> [4/5] Mapping to Canonical STW Schema...")
    stw_doc, audit_report = STWMapper.map_document(
        extracted_doc=extracted_doc,
        catalog_entry=catalog_entry,
        raw_tables=all_tables,
    )

    # 5. Pydantic validation & Serialization
    print(f"--> [5/5] Performing Pydantic validation & saving structured outputs...")
    # Validate by dumping and reloading
    json_data = stw_doc.model_dump_json(indent=2)
    revalidated = STWDocument.model_validate_json(json_data)

    structured_json_path = structured_dir / f"{doc_id}.json"
    with open(structured_json_path, "w", encoding="utf-8") as f:
        f.write(json_data)
    print(f"    Canonical JSON saved: {structured_json_path}")

    # Save audit report
    report_path = reports_dir / f"{doc_id}.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(audit_report.to_dict(), f, indent=2, ensure_ascii=False)
    print(f"    Audit report saved: {report_path}")

    print(f"    [SUMMARY] Blocks: {audit_report.text_blocks_count} | Sections: {audit_report.sections_count} | "
          f"Medications: {audit_report.medications_count} | Flowcharts: {audit_report.flowcharts_count} | "
          f"Review items: {audit_report.manual_review_items_count}")

    loaded_doc.close()
    return True


def main():
    parser = argparse.ArgumentParser(description="ICMR STW Extraction Pipeline CLI")
    parser.add_argument(
        "--document-id",
        type=str,
        help="Process a specific document by STW ID (e.g. ICMR-CARD-006)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Process all documents in the STW catalog",
    )
    parser.add_argument(
        "--catalog",
        type=Path,
        default=Path("data/metadata/stw_catalog.csv"),
        help="Path to stw_catalog.csv",
    )
    parser.add_argument(
        "--extracted-dir",
        type=Path,
        default=Path("data/processed/extracted"),
        help="Directory for intermediate extracted text",
    )
    parser.add_argument(
        "--structured-dir",
        type=Path,
        default=Path("data/processed/structured"),
        help="Directory for canonical structured STW JSONs",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=Path("data/review/extraction_reports"),
        help="Directory for extraction audit reports",
    )

    args = parser.parse_args()

    if not args.document_id and not args.all:
        parser.error("Must specify either --document-id or --all")

    if not args.catalog.exists():
        print(f"Catalog file not found at {args.catalog}", file=sys.stderr)
        sys.exit(1)

    # Ensure output directories exist
    args.extracted_dir.mkdir(parents=True, exist_ok=True)
    args.structured_dir.mkdir(parents=True, exist_ok=True)
    args.reports_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.catalog)

    if args.document_id:
        matches = df[df["stw_id"] == args.document_id]
        if matches.empty:
            print(f"No entry found in catalog for {args.document_id}", file=sys.stderr)
            sys.exit(1)
        entries = matches.to_dict(orient="records")
    else:
        entries = df.to_dict(orient="records")

    success_count = 0
    total = len(entries)

    for entry in entries:
        success = process_document(
            catalog_entry=entry,
            extracted_dir=args.extracted_dir,
            structured_dir=args.structured_dir,
            reports_dir=args.reports_dir,
        )
        if success:
            success_count += 1

    print(f"\n=======================================================")
    print(f"EXTRACTION COMPLETE: {success_count}/{total} documents successfully processed.")
    print(f"=======================================================")

    if success_count < total:
        sys.exit(1)


if __name__ == "__main__":
    main()
