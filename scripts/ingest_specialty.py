#!/usr/bin/env python
"""ICMR STW Multi-Specialty Batch Ingestion Pipeline.

Supports:
    python scripts/ingest_specialty.py --specialty "Neurology"
    python scripts/ingest_specialty.py --specialty "Cardiology"
    python scripts/ingest_specialty.py --all

Pipeline stages:
    discover -> download -> validate -> extract -> map -> validate -> review queue -> index approved content

Safety Rule:
    Newly ingested specialty documents are NEVER auto-approved into production.
    All extracted units are routed to the review queue (needs_review) and only
    clinician-approved content enters the production retrieval index.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import logging
import re
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import pymupdf
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.discover_all_stws import discover_all_stws, ALLOWED_DOMAINS, is_allowed_domain
from src.extraction.pdf_loader import PDFLoader
from src.extraction.stw_mapper import STWMapper
from src.extraction.table_extractor import TableExtractor
from src.extraction.text_extractor import TextExtractor
from src.knowledge.indexer import KnowledgeIndexer
from src.knowledge.units import decompose_stw_document
from src.models.stw_schema import STWDocument
from src.models.version import DocumentVersion, VersionPrecedence
from src.review.priority import ReviewPriorityClassifier
from src.review.queue import ReviewQueue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ingest_specialty")


def calculate_sha256(file_path: Path) -> str:
    """Compute SHA-256 hex digest of a local file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def download_pdf(
    url: str,
    target_path: Path,
    timeout: int = 45,
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ICMR-STW-AI-Ingestion/2.0",
) -> bool:
    """Safely download PDF from official ICMR domain."""
    if not is_allowed_domain(url, ALLOWED_DOMAINS):
        logger.error("Security policy violation: Rejected unapproved domain for URL: %s", url)
        return False

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(".tmp")
    headers = {"User-Agent": user_agent}

    try:
        logger.info("Downloading official STW from: %s", url)
        response = requests.get(url, headers=headers, timeout=timeout, stream=True)
        response.raise_for_status()

        with open(temp_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=32768):
                if chunk:
                    f.write(chunk)

        # Validate PDF header bytes
        with open(temp_path, "rb") as f:
            header = f.read(5)
            if not header.startswith(b"%PDF-"):
                logger.error("Invalid PDF signature received for: %s", url)
                if temp_path.exists():
                    temp_path.unlink()
                return False

        temp_path.replace(target_path)
        logger.info("Downloaded successfully to: %s", target_path)
        return True
    except Exception as exc:
        logger.error("Download failed for %s: %s", url, exc)
        if temp_path.exists():
            temp_path.unlink()
        return False


def get_existing_version_hash(db_path: Path, document_id: str) -> Optional[str]:
    """Retrieve content hash for a document if already recorded in document_versions."""
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT content_hash FROM document_versions WHERE document_id = ? AND is_current = 1", (document_id,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else None
    except Exception:
        return None


def register_document_version(
    db_path: Path,
    version: DocumentVersion,
) -> None:
    """Store or update document version metadata in database."""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    cur.execute("""
        INSERT OR REPLACE INTO document_versions (
            version_record_id, document_id, specialty, condition, version_id,
            version_label, source_url, download_date, content_hash,
            is_current, supersedes, review_status, version_precedence, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        f"VER-{version.document_id}-{version.version_id}",
        version.document_id,
        getattr(version, "specialty", "General"),
        getattr(version, "condition", "Unknown"),
        version.version_id,
        version.version_label,
        version.source_url,
        version.download_date,
        version.content_hash,
        1 if version.is_current else 0,
        version.supersedes,
        version.review_status,
        version.version_precedence.value if hasattr(version.version_precedence, "value") else str(version.version_precedence),
        now_iso,
    ))
    conn.commit()
    conn.close()


def ingest_document(
    doc_meta: Dict[str, Any],
    raw_dir: Path,
    extracted_dir: Path,
    structured_dir: Path,
    db_path: Path,
    auto_approve_existing_cardio: bool = True,
) -> Dict[str, Any]:
    """Ingest a single STW document through the full pipeline."""
    doc_id = doc_meta["stw_id"]
    specialty = doc_meta["specialty"]
    condition = doc_meta["condition"]
    source_url = doc_meta["source_url"]

    # Target file paths
    url_filename = Path(urlparse(source_url).path).name
    if not url_filename:
        url_filename = f"{doc_id.lower()}.pdf"

    spec_slug = re.sub(r"[^a-zA-Z0-9]", "_", specialty.lower()).strip("_")
    local_pdf = raw_dir / spec_slug / url_filename

    # Fallback to existing pilot directory if present
    if not local_pdf.exists() and (raw_dir / "cardiology" / url_filename).exists():
        local_pdf = raw_dir / "cardiology" / url_filename

    # Step 1: Check existing download and hash
    is_new = not local_pdf.exists()
    old_hash = get_existing_version_hash(db_path, doc_id)

    if not is_new:
        current_hash = calculate_sha256(local_pdf)
        if (structured_dir / f"{doc_id}.json").exists():
            if old_hash in (current_hash, "verified_baseline_hash") or not old_hash:
                if not old_hash:
                    is_cardio = (specialty == "Cardiology")
                    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
                    doc_ver = DocumentVersion(
                        document_id=doc_id,
                        version_id="v1.0",
                        version_label="Official Edition 2019",
                        source_url=source_url,
                        download_date=now_iso,
                        content_hash=current_hash,
                        is_current=True,
                        supersedes=None,
                        review_status="approved" if is_cardio else "needs_review",
                        version_precedence=VersionPrecedence.CURRENT,
                    )
                    setattr(doc_ver, "specialty", specialty)
                    setattr(doc_ver, "condition", condition)
                    register_document_version(db_path, doc_ver)
                logger.info("[UNCHANGED] Document %s (%s) already structured with valid PDF. Skipping re-extraction.", doc_id, condition)
                return {"status": "UNCHANGED", "document_id": doc_id, "specialty": specialty, "condition": condition}


    # Step 2: Download PDF if needed
    if is_new:
        ok = download_pdf(source_url, local_pdf)
        if not ok:
            return {"status": "FAILED", "reason": "Download error", "document_id": doc_id}

    current_hash = calculate_sha256(local_pdf)

    # Step 3: PyMuPDF verification
    try:
        doc = pymupdf.open(local_pdf)
        page_count = doc.page_count
        doc.close()
        if page_count < 1:
            return {"status": "FAILED", "reason": "Empty PDF", "document_id": doc_id}
    except Exception as exc:
        return {"status": "FAILED", "reason": f"Corrupt PDF: {exc}", "document_id": doc_id}

    # Step 4: Deterministic Extraction
    logger.info("Extracting %s (%s, %d pages)...", doc_id, condition, page_count)
    loaded_doc = PDFLoader.load(local_pdf, document_id=doc_id)
    extracted_text = TextExtractor.extract_document(loaded_doc)

    extracted_dir.mkdir(parents=True, exist_ok=True)
    extracted_text.save_json(extracted_dir / f"{doc_id}.json")

    tables = []
    for page_data in loaded_doc.pages:
        tabs = TableExtractor.extract_tables_from_page(
            page_data=page_data,
            document_id=doc_id,
            document_name=condition,
        )
        tables.extend(tabs)

    catalog_entry = {
        "stw_id": doc_id,
        "title": doc_meta.get("title", condition),
        "specialty": specialty,
        "condition": condition,
        "volume": doc_meta.get("volume", "Volume 1"),
        "edition": "2019",
        "source_url": source_url,
        "local_path": str(local_pdf),
        "document_type": doc_meta.get("document_type", "individual_stw"),
        "version": "1.0",
        "page_count": page_count,
    }

    # Map to Canonical STW Schema
    canonical_stw, audit_report = STWMapper.map_document(
        extracted_doc=extracted_text,
        catalog_entry=catalog_entry,
        raw_tables=tables,
    )


    # Check for Schema Extension requirement
    schema_extension_needed = False
    if page_count > 10 and not tables and not canonical_stw.flowchart:
        canonical_stw.metadata.document_hash = current_hash

    # Save structured canonical JSON
    structured_dir.mkdir(parents=True, exist_ok=True)
    structured_path = structured_dir / f"{doc_id}.json"
    with open(structured_path, "w", encoding="utf-8") as f:
        f.write(canonical_stw.model_dump_json(indent=2))

    # Step 5: Decompose into Knowledge Units and route to database
    units = decompose_stw_document(canonical_stw)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Determine whether this document is the pre-approved baseline
    is_cardio_baseline = (specialty == "Cardiology" and auto_approve_existing_cardio and doc_id in [
        f"ICMR-CARD-{i:03d}" for i in range(1, 8)
    ])

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    for u in units:
        # Clinical governance rule: non-baseline specialties MUST require manual review
        if is_cardio_baseline:
            # Preserve original review flag
            req_review = 1 if u.requires_manual_review else 0
            rev_status = u.review_status
        else:
            # Newly ingested specialty units are ALL placed into review backlog
            req_review = 1
            rev_status = "needs_review"

        cur.execute("""
            INSERT OR REPLACE INTO knowledge_units (
                unit_id, document_id, specialty, condition, section, page_number,
                entity_type, healthcare_tier, content, metadata_json, review_status,
                requires_manual_review, review_notes, source_reference_json, indexed_at, version_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            u.unit_id,
            u.document_id,
            specialty,
            condition,
            u.section,
            u.page_number,
            u.entity_type,
            u.healthcare_tier,
            u.content,
            json.dumps(u.metadata),
            rev_status,
            req_review,
            u.review_notes,
            json.dumps(u.source_reference.model_dump() if hasattr(u.source_reference, "model_dump") else u.source_reference),
            now_iso,
            "v1.0",
        ))


    conn.commit()
    conn.close()

    # Step 6: Sync to Review Queue
    rq = ReviewQueue(db_path=db_path)
    rq.sync_from_knowledge_units()

    # Step 7: Register Document Version
    doc_ver = DocumentVersion(
        document_id=doc_id,
        version_id="v1.0",
        version_label="Official Edition 2019",
        source_url=source_url,
        download_date=now_iso,
        content_hash=current_hash,
        is_current=True,
        supersedes=None,
        review_status="approved" if is_cardio_baseline else "needs_review",
        version_precedence=VersionPrecedence.CURRENT,
    )
    # inject specialty/condition attributes
    setattr(doc_ver, "specialty", specialty)
    setattr(doc_ver, "condition", condition)
    register_document_version(db_path, doc_ver)

    status_tag = "NEW" if is_new else "UPDATED"
    logger.info("[%s] Document %s (%s, %s): Extracted %d units (Needs Review: %s)",
                status_tag, doc_id, specialty, condition, len(units), "False" if is_cardio_baseline else "True")

    return {
        "status": status_tag,
        "document_id": doc_id,
        "specialty": specialty,
        "condition": condition,
        "units_count": len(units),
        "page_count": page_count,
    }


def ingest_specialties(
    target_specialty: Optional[str] = None,
    ingest_all: bool = False,
    catalog_path: Path = Path("data/metadata/all_discovered_stws.json"),
    raw_dir: Path = Path("data/raw"),
    extracted_dir: Path = Path("data/processed/extracted"),
    structured_dir: Path = Path("data/processed/structured"),
    knowledge_dir: Path = Path("data/knowledge"),
) -> Dict[str, Any]:
    """Ingest documents for a given specialty or across all specialties."""
    db_path = knowledge_dir / "knowledge.db"

    # Ensure discovery manifest is available
    if not catalog_path.exists():
        logger.info("Discovery catalogue not found. Running discovery...")
        discover_all_stws(cache_path=Path("data/metadata/portal_landing_cache.html"))

    with open(catalog_path, "r", encoding="utf-8") as f:
        cat_data = json.load(f)

    all_docs = cat_data.get("documents", [])

    if ingest_all:
        selected_docs = all_docs
        spec_label = "ALL"
    elif target_specialty:
        selected_docs = [d for d in all_docs if d["specialty"].lower() == target_specialty.lower()]
        spec_label = target_specialty
    else:
        raise ValueError("Must specify either target_specialty or ingest_all=True")

    logger.info("Found %d documents for specialty selection '%s'.", len(selected_docs), spec_label)

    results = {
        "specialty": spec_label,
        "total_selected": len(selected_docs),
        "new": 0,
        "updated": 0,
        "unchanged": 0,
        "failed": 0,
        "details": [],
    }

    for doc_meta in selected_docs:
        try:
            res = ingest_document(
                doc_meta=doc_meta,
                raw_dir=raw_dir,
                extracted_dir=extracted_dir,
                structured_dir=structured_dir,
                db_path=db_path,
            )
            st = res.get("status")
            if st == "NEW":
                results["new"] += 1
            elif st == "UPDATED":
                results["updated"] += 1
            elif st == "UNCHANGED":
                results["unchanged"] += 1
            else:
                results["failed"] += 1
            results["details"].append(res)
        except Exception as exc:
            logger.error("Error ingesting %s: %s", doc_meta.get("stw_id"), exc)
            results["failed"] += 1
            results["details"].append({"status": "FAILED", "document_id": doc_meta.get("stw_id"), "error": str(exc)})

    # Rebuild retrieval index only with approved units
    logger.info("Re-indexing approved knowledge units into production index...")
    indexer = KnowledgeIndexer(structured_dir=structured_dir, knowledge_dir=knowledge_dir)
    indexer.build(force=True)

    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Batch ingest ICMR STW documents by specialty.")
    parser.add_argument("--specialty", default=None, help="Name of clinical specialty to ingest (e.g. 'Cardiology', 'Neurology')")
    parser.add_argument("--all", action="store_true", help="Ingest all discovered specialties")
    args = parser.parse_args()

    if not args.specialty and not args.all:
        parser.error("Must specify either --specialty <name> or --all")

    t0 = time.time()
    res = ingest_specialties(target_specialty=args.specialty, ingest_all=args.all)
    elapsed = round(time.time() - t0, 2)

    print("\n" + "=" * 80)
    print("ICMR STW BATCH INGESTION SUMMARY")
    print("=" * 80)
    print(f"Target Specialty   : {res['specialty']}")
    print(f"Total Selected     : {res['total_selected']}")
    print(f"  [NEW] Ingested   : {res['new']}")
    print(f"  [UPDATED]        : {res['updated']}")
    print(f"  [UNCHANGED]      : {res['unchanged']}")
    print(f"  [FAILED]         : {res['failed']}")
    print(f"Elapsed Time       : {elapsed}s")
    print("=" * 80 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
