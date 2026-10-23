#!/usr/bin/env python
"""Official ICMR STW All-Specialty Discovery Script.

Discovers Standard Treatment Workflow documents published on the official ICMR portal
across all clinical specialties (Cardiology, Neurology, Nephrology, Pulmonology, etc.).
Produces structured discovery manifests and master catalogue without downloading PDFs.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("discover_all_stws")

ALLOWED_DOMAINS = [
    "icmr.gov.in",
    "www.icmr.gov.in",
    "main.icmr.nic.in",
]

# Standard 4-letter prefix mapping for specialties
SPECIALTY_PREFIXES = {
    "Cardiology": "CARD",
    "Neurology": "NEUR",
    "Nephrology": "NEPH",
    "ENT": "ENT",
    "Endocrinology": "ENDO",
    "Pulmonology": "PULM",
    "Dermatology": "DERM",
    "Gastroenterology": "GAST",
    "Paediatrics": "PAED",
    "Psychiatry": "PSYC",
    "Urology": "UROL",
    "Obstetrics & Gynecology": "OBGY",
    "General Surgery": "GSUR",
    "Adult Extrapulmonary Tuberculosis": "AETB",
    "Paediatric Tuberculosis": "PETB",
    "Haemolytic Anaemia": "HAEM",
    "Infertility": "INFT",
    "Neonatology": "NEON",
    "Oncology": "ONCO",
    "Ophthalmology": "OPHT",
    "Orthopaedics": "ORTH",
    "Paediatric Surgery": "PSUR",
    "Cardiothoracic and Vascular Surgery(CTVS)": "CTVS",
    "Interventional Radiology": "INTR",
    "Neurosurgery": "NSUR",
    "Pediatric Cardiology": "PCAR",
    "Investigations Treatment": "INVT",
}


def is_allowed_domain(url: str, allowed_domains: Optional[List[str]] = None) -> bool:
    """Validate that URL domain is in the approved official ICMR domain list."""
    domains = allowed_domains or ALLOWED_DOMAINS
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()
    return any(hostname == d or hostname.endswith("." + d) for d in domains)


def fetch_portal_html(
    url: str,
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) ICMR-STW-AI-Ingestion/2.0",
    timeout: int = 30,
    cache_path: Optional[Path] = None,
) -> str:
    """Fetch official ICMR STW landing page HTML with offline cache fallback."""
    headers = {"User-Agent": user_agent}
    try:
        logger.info("Connecting to official ICMR portal: %s", url)
        response = requests.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        html_content = response.text
        if cache_path:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(html_content, encoding="utf-8")
            logger.info("Saved portal snapshot to cache: %s", cache_path)
        return html_content
    except Exception as exc:
        logger.warning("Live portal request failed (%s). Checking local cache...", exc)
        if cache_path and cache_path.exists():
            logger.info("Loaded portal HTML from offline cache: %s", cache_path)
            return cache_path.read_text(encoding="utf-8")
        raise RuntimeError(f"Unable to fetch ICMR portal and no cache available: {exc}") from exc


def get_specialty_prefix(specialty_name: str) -> str:
    """Get standardized prefix for specialty."""
    if specialty_name in SPECIALTY_PREFIXES:
        return SPECIALTY_PREFIXES[specialty_name]
    clean = re.sub(r"[^A-Za-z]", "", specialty_name).upper()
    return clean[:4] if len(clean) >= 4 else clean.ljust(4, "X")


def discover_all_stws(
    portal_url: str = "https://www.icmr.gov.in/standard-treatment-workflows-stws",
    base_url: str = "https://www.icmr.gov.in",
    allowed_domains: Optional[List[str]] = None,
    cache_path: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Scrape and parse all official STW documents across all specialties on ICMR portal."""
    domains = allowed_domains or ALLOWED_DOMAINS
    html = fetch_portal_html(url=portal_url, cache_path=cache_path)
    soup = BeautifulSoup(html, "html.parser")

    cards = soup.find_all(class_="card")
    logger.info("Found %d specialty cards on portal.", len(cards))

    all_discovered: List[Dict[str, Any]] = []
    seen_urls: set[str] = set()

    for card in cards:
        hdr = card.find(class_="card-header")
        if not hdr:
            continue
        specialty_raw = hdr.get_text(strip=True)
        # Normalize specialty name
        specialty = re.sub(r"\s+", " ", specialty_raw)

        table = card.find("table")
        if not table:
            continue

        rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")
        specialty_seq = 0

        prefix = get_specialty_prefix(specialty)

        for row in rows:
            cols = row.find_all(["td", "th"])
            if len(cols) < 2:
                continue

            col_texts = [c.get_text(strip=True) for c in cols]
            # Check if header row
            if "sr" in col_texts[0].lower() or "title" in col_texts[1].lower():
                continue

            raw_seq = col_texts[0]
            title = col_texts[1]
            if not title:
                continue

            # Find PDF links
            links = row.find_all("a", href=True)
            pdf_url = ""
            stated_size = ""

            for a in links:
                href = a["href"].strip()
                if ".pdf" in href.lower() or "/stws/" in href.lower():
                    cand_url = urljoin(base_url, href)
                    if is_allowed_domain(cand_url, domains):
                        pdf_url = cand_url
                        if "(" in a.text:
                            m = re.search(r"\(([^)]+)\)", a.text)
                            if m:
                                stated_size = m.group(1).strip()
                        break

            if not pdf_url:
                continue

            # Check duplication within specialty
            url_norm = pdf_url.lower()
            if (specialty, url_norm) in seen_urls:
                continue
            seen_urls.add((specialty, url_norm))

            specialty_seq += 1

            # Determine document ID
            if specialty == "Cardiology":
                # Ensure 100% preservation of Phase 1-7 Cardiology catalog IDs
                stw_id = f"ICMR-CARD-{specialty_seq:03d}"
            else:
                stw_id = f"ICMR-{prefix}-{specialty_seq:03d}"

            # Document type
            is_all = bool(re.search(r"\(All\)|_all\.pdf", title, re.IGNORECASE) or "_all.pdf" in pdf_url.lower())
            doc_type = "consolidated_stw" if is_all else "individual_stw"

            # Derive condition
            condition = re.sub(r"\s*\(All\)\s*", "", title, flags=re.IGNORECASE).strip()
            if not condition:
                condition = f"{specialty} (Consolidated)"

            # Version info
            version_info = "Volume 1 (2019)"
            if "updated" in pdf_url.lower() or "updated" in title.lower():
                version_info = "Updated Official Edition"

            item = {
                "stw_id": stw_id,
                "title": title,
                "specialty": specialty,
                "condition": condition,
                "volume": "Volume 1",
                "document_type": doc_type,
                "source_organization": "Indian Council of Medical Research (ICMR)",
                "source_url": pdf_url,
                "version_information": version_info,
                "discovery_date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "status": "discovered",
                "stated_size": stated_size,
                "url_hash": hashlib.sha256(pdf_url.encode("utf-8")).hexdigest(),
            }
            all_discovered.append(item)

    logger.info("Total STWs discovered across all specialties: %d", len(all_discovered))
    return all_discovered


def save_manifests(
    documents: List[Dict[str, Any]],
    json_path: Path,
    csv_path: Path,
) -> None:
    """Save discovered documents as JSON manifest and CSV master catalogue."""
    json_path.parent.mkdir(parents=True, exist_ok=True)
    csv_path.parent.mkdir(parents=True, exist_ok=True)

    specialties_set = sorted(set(d["specialty"] for d in documents))

    manifest = {
        "metadata": {
            "source_portal": "https://www.icmr.gov.in/standard-treatment-workflows-stws",
            "total_documents": len(documents),
            "total_specialties": len(specialties_set),
            "specialties": specialties_set,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        "documents": documents,
    }

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
    logger.info("Saved JSON manifest to: %s", json_path)

    # CSV Catalogue
    fieldnames = [
        "stw_id",
        "title",
        "specialty",
        "condition",
        "volume",
        "document_type",
        "source_organization",
        "source_url",
        "version_information",
        "discovery_date",
        "status",
        "stated_size",
        "url_hash",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for doc in documents:
            writer.writerow({k: doc.get(k, "") for k in fieldnames})
    logger.info("Saved CSV master catalogue to: %s", csv_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover official ICMR STW documents across all specialties.")
    parser.add_argument(
        "--output-json",
        default="data/metadata/all_discovered_stws.json",
        help="Path to output JSON manifest",
    )
    parser.add_argument(
        "--output-csv",
        default="data/metadata/stw_master_catalog.csv",
        help="Path to output CSV master catalogue",
    )
    parser.add_argument(
        "--cache-file",
        default="data/metadata/portal_landing_cache.html",
        help="Path to save or load portal HTML snapshot",
    )
    args = parser.parse_args()

    try:
        docs = discover_all_stws(cache_path=Path(args.cache_file))
        save_manifests(docs, Path(args.output_json), Path(args.output_csv))
        print(f"\nDiscovered {len(docs)} official STW documents across {len(set(d['specialty'] for d in docs))} specialties.")
        return 0
    except Exception as e:
        logger.error("Discovery failed: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
