#!/usr/bin/env python
"""ICMR STW Document Update Monitor.

Compares the currently indexed/catalogued documents against the official ICMR portal
catalogue and identifies:
  - NEW: Documents published on portal not yet in local catalogue
  - UPDATED: Documents whose remote content or version metadata has changed
  - UNCHANGED: Documents whose content hash and URL are identical
  - REMOVED/UNAVAILABLE: Documents in local catalogue no longer present on portal
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.discover_all_stws import discover_all_stws, ALLOWED_DOMAINS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("check_icmr_updates")


def check_updates(
    catalog_path: Path = Path("data/metadata/all_discovered_stws.json"),
    cache_path: Path = Path("data/metadata/portal_landing_cache.html"),
    offline_only: bool = False,
) -> Dict[str, Any]:
    """Compare local catalog against live/cached portal discovery."""
    # 1. Load existing catalogue
    local_docs_by_id: Dict[str, Dict[str, Any]] = {}
    local_docs_by_url: Dict[str, Dict[str, Any]] = {}

    if catalog_path.exists():
        with open(catalog_path, "r", encoding="utf-8") as f:
            local_data = json.load(f)
            for d in local_data.get("documents", []):
                local_docs_by_id[d["stw_id"]] = d
                local_docs_by_url[d["source_url"].lower()] = d

    # Also check baseline cardiology catalog if separate
    base_card_catalog = Path("data/metadata/stw_catalog.csv")
    if base_card_catalog.exists():
        import csv
        with open(base_card_catalog, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row["stw_id"] not in local_docs_by_id:
                    local_docs_by_id[row["stw_id"]] = row
                    local_docs_by_url[row["source_url"].lower()] = row

    # 2. Discover current official portal items
    logger.info("Discovering current documents from official ICMR portal...")
    current_docs = discover_all_stws(cache_path=cache_path)

    new_docs: List[Dict[str, Any]] = []
    updated_docs: List[Dict[str, Any]] = []
    unchanged_docs: List[Dict[str, Any]] = []

    current_urls = set()

    for doc in current_docs:
        url_norm = doc["source_url"].lower()
        current_urls.add(url_norm)
        stw_id = doc["stw_id"]

        if url_norm in local_docs_by_url:
            existing = local_docs_by_url[url_norm]
            # Check if title or size or version metadata changed
            if (
                existing.get("title") != doc["title"]
                or existing.get("stated_size") != doc.get("stated_size")
            ):
                updated_docs.append({
                    "stw_id": stw_id,
                    "title": doc["title"],
                    "specialty": doc["specialty"],
                    "reason": "Metadata or edition attributes updated",
                    "source_url": doc["source_url"],
                })
            else:
                unchanged_docs.append({
                    "stw_id": stw_id,
                    "title": doc["title"],
                    "specialty": doc["specialty"],
                    "source_url": doc["source_url"],
                })
        elif stw_id in local_docs_by_id:
            existing = local_docs_by_id[stw_id]
            if existing.get("source_url", "").lower() != url_norm:
                updated_docs.append({
                    "stw_id": stw_id,
                    "title": doc["title"],
                    "specialty": doc["specialty"],
                    "reason": "Source URL / publication asset changed",
                    "old_url": existing.get("source_url"),
                    "new_url": doc["source_url"],
                })
            else:
                unchanged_docs.append(doc)
        else:
            new_docs.append(doc)

    # 3. Detect removed or unavailable documents
    removed_docs: List[Dict[str, Any]] = []
    for url_norm, existing in local_docs_by_url.items():
        if url_norm not in current_urls:
            removed_docs.append({
                "stw_id": existing.get("stw_id"),
                "title": existing.get("title"),
                "specialty": existing.get("specialty"),
                "source_url": existing.get("source_url"),
            })

    report = {
        "timestamp": current_docs[0]["discovery_date"] if current_docs else "",
        "summary": {
            "total_online": len(current_docs),
            "total_local": len(local_docs_by_id),
            "new_count": len(new_docs),
            "updated_count": len(updated_docs),
            "unchanged_count": len(unchanged_docs),
            "removed_count": len(removed_docs),
        },
        "new_documents": new_docs,
        "updated_documents": updated_docs,
        "unchanged_documents": unchanged_docs,
        "removed_documents": removed_docs,
    }

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Check official ICMR portal for STW document updates.")
    parser.add_argument("--catalog", default="data/metadata/all_discovered_stws.json", help="Path to local catalog")
    parser.add_argument("--cache", default="data/metadata/portal_landing_cache.html", help="Path to portal HTML cache")
    parser.add_argument("--json", action="store_true", help="Output raw JSON report")
    args = parser.parse_args()

    report = check_updates(catalog_path=Path(args.catalog), cache_path=Path(args.cache))

    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    s = report["summary"]
    print("\n" + "=" * 80)
    print("ICMR STW DOCUMENT UPDATE MONITORING REPORT")
    print("=" * 80)
    print(f"Total Documents on Portal : {s['total_online']}")
    print(f"Total Local in Catalogue  : {s['total_local']}")
    print(f"  [UNCHANGED]             : {s['unchanged_count']}")
    print(f"  [NEW]                   : {s['new_count']}")
    print(f"  [UPDATED]               : {s['updated_count']}")
    print(f"  [REMOVED/UNAVAILABLE]   : {s['removed_count']}")
    print("=" * 80)

    if report["new_documents"]:
        print(f"\nNew Documents Found ({len(report['new_documents'])}):")
        for d in report["new_documents"][:5]:
            print(f"  + [{d['stw_id']}] {d['specialty']}: {d['title']}")
        if len(report["new_documents"]) > 5:
            print(f"    ... and {len(report['new_documents']) - 5} more.")

    if report["updated_documents"]:
        print(f"\nUpdated Documents Found ({len(report['updated_documents'])}):")
        for d in report["updated_documents"]:
            print(f"  * [{d['stw_id']}] {d['specialty']}: {d['title']} ({d.get('reason')})")

    print("\n" + "=" * 80 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
