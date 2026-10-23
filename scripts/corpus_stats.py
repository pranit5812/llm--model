"""Corpus statistics and inventory summary for the ICMR STW Platform.

Outputs:
- Discovered specialties and total documents in the ICMR master catalogue.
- Ingested documents and document versions.
- Total structured knowledge units, production units, and quarantined review units.
- Priority and reason breakdowns for review queues.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict


def get_corpus_stats(db_path: Path = Path("data/knowledge/knowledge.db")) -> Dict[str, Any]:
    catalog_path = Path("data/metadata/all_discovered_stws.json")
    catalog_stws = []
    catalog_specialties = []
    if catalog_path.exists():
        with open(catalog_path, "r", encoding="utf-8") as f:
            cdata = json.load(f)
            catalog_stws = cdata.get("documents", [])
            catalog_specialties = cdata.get("metadata", {}).get("specialties", [])

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Document versions
        versions_rows = conn.execute("SELECT * FROM document_versions").fetchall()
        docs_by_spec: Dict[str, int] = {}
        status_counts: Dict[str, int] = {}
        for r in versions_rows:
            spec = r["specialty"]
            docs_by_spec[spec] = docs_by_spec.get(spec, 0) + 1
            st = r["review_status"]
            status_counts[st] = status_counts.get(st, 0) + 1

        # Knowledge units
        ku_rows = conn.execute("SELECT specialty, entity_type, requires_manual_review, version_id FROM knowledge_units").fetchall()
        total_units = len(ku_rows)
        prod_units = sum(1 for r in ku_rows if not r["requires_manual_review"])
        quarantined_units = sum(1 for r in ku_rows if r["requires_manual_review"])

        units_by_spec: Dict[str, Dict[str, int]] = {}
        entity_counts: Dict[str, int] = {}
        for r in ku_rows:
            spec = r["specialty"]
            if spec not in units_by_spec:
                units_by_spec[spec] = {"total": 0, "production": 0, "review": 0}
            units_by_spec[spec]["total"] += 1
            if r["requires_manual_review"]:
                units_by_spec[spec]["review"] += 1
            else:
                units_by_spec[spec]["production"] += 1

            et = r["entity_type"]
            entity_counts[et] = entity_counts.get(et, 0) + 1

        # Review items
        rev_rows = conn.execute("SELECT review_priority, review_reason, specialty, review_status FROM review_items").fetchall()
        rev_priorities: Dict[str, int] = {}
        rev_reasons: Dict[str, int] = {}
        rev_by_spec: Dict[str, int] = {}
        for r in rev_rows:
            p = r["review_priority"]
            rev_priorities[p] = rev_priorities.get(p, 0) + 1
            re = r["review_reason"]
            rev_reasons[re] = rev_reasons.get(re, 0) + 1
            sp = r["specialty"]
            rev_by_spec[sp] = rev_by_spec.get(sp, 0) + 1

    finally:
        conn.close()

    return {
        "master_catalog": {
            "total_discovered_stws": len(catalog_stws),
            "total_specialties": len(catalog_specialties),
        },
        "ingested_documents": {
            "total_documents": len(versions_rows),
            "by_specialty": docs_by_spec,
            "by_status": status_counts,
        },
        "knowledge_units": {
            "total": total_units,
            "production": prod_units,
            "quarantined_review": quarantined_units,
            "by_specialty": units_by_spec,
            "by_entity_type": entity_counts,
        },
        "review_queue": {
            "total_items": len(rev_rows),
            "by_priority": rev_priorities,
            "by_reason": rev_reasons,
            "by_specialty": rev_by_spec,
        },
    }


def print_report(stats: Dict[str, Any]) -> None:
    print("=" * 70)
    print("ICMR STANDARD TREATMENT WORKFLOWS — CORPUS INVENTORY & STATS")
    print("=" * 70)

    mc = stats["master_catalog"]
    print(f"\n1. Master Portal Discovery:")
    print(f"   - Total STWs discovered: {mc['total_discovered_stws']}")
    print(f"   - Total specialties:     {mc['total_specialties']}")

    ing = stats["ingested_documents"]
    print(f"\n2. Ingested Guidelines:")
    print(f"   - Ingested STW documents: {ing['total_documents']}")
    for spec, count in ing["by_specialty"].items():
        print(f"     * {spec}: {count} STWs")
    print(f"   - Review status breakdown: {ing['by_status']}")

    ku = stats["knowledge_units"]
    print(f"\n3. Structured Knowledge Units:")
    print(f"   - Total Units:        {ku['total']}")
    print(f"   - Production Units:   {ku['production']} (Available for RAG retrieval)")
    print(f"   - Quarantined Units:  {ku['quarantined_review']} (Protected in review queue)")
    print(f"   - Breakdown by specialty:")
    for spec, counts in ku["by_specialty"].items():
        print(f"     * {spec}: Total={counts['total']}, Prod={counts['production']}, Review={counts['review']}")

    rq = stats["review_queue"]
    print(f"\n4. Review Queue Backlog:")
    print(f"   - Total Review Items: {rq['total_items']}")
    print(f"   - By Specialty:       {rq['by_specialty']}")
    print(f"   - By Priority:        {rq['by_priority']}")
    print(f"   - By Reason:          {rq['by_reason']}")
    print("=" * 70)


if __name__ == "__main__":
    stats = get_corpus_stats()
    print_report(stats)
