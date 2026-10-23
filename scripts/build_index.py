#!/usr/bin/env python
"""Build the ICMR STW knowledge index.

Loads all canonical STW JSON files from data/processed/structured/,
decomposes them into KnowledgeUnit objects, persists them to SQLite,
and builds BM25 + TF-IDF indexes for the hybrid retrieval system.

Usage:
    python scripts/build_index.py            # Build if not already built
    python scripts/build_index.py --force    # Force rebuild

Output:
    data/knowledge/knowledge.db        — SQLite knowledge store
    data/knowledge/bm25_index.pkl      — BM25 index (rank_bm25)
    data/knowledge/tfidf_index.pkl     — TF-IDF matrix + vectorizer (sklearn)
    data/knowledge/index_manifest.json — Build manifest with counts
"""

import argparse
import json
import sys
from pathlib import Path

# Ensure src is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.knowledge.indexer import KnowledgeIndexer


def main() -> None:
    parser = argparse.ArgumentParser(description="Build ICMR STW knowledge index")
    parser.add_argument("--force", action="store_true", help="Force rebuild even if index exists")
    parser.add_argument(
        "--structured-dir",
        default="data/processed/structured",
        help="Directory containing canonical STW JSON files",
    )
    parser.add_argument(
        "--knowledge-dir",
        default="data/knowledge",
        help="Output directory for index files",
    )
    args = parser.parse_args()

    structured_dir = Path(args.structured_dir)
    knowledge_dir = Path(args.knowledge_dir)

    if not structured_dir.exists():
        print(f"[ERROR] Structured JSON directory not found: {structured_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Building knowledge index...")
    print(f"  Source : {structured_dir.resolve()}")
    print(f"  Output : {knowledge_dir.resolve()}")
    print(f"  Force  : {args.force}")
    print()

    indexer = KnowledgeIndexer(structured_dir=structured_dir, knowledge_dir=knowledge_dir)
    manifest = indexer.build(force=args.force)

    print("=" * 60)
    print("INDEX BUILD COMPLETE")
    print("=" * 60)
    print(f"  Built at          : {manifest['built_at']}")
    print(f"  Elapsed           : {manifest['elapsed_seconds']}s")
    print(f"  Total documents   : {manifest['total_documents']}")
    print(f"  Total units       : {manifest['total_units']}")
    print(f"  Production units  : {manifest['production_units']}")
    print(f"  Excluded (review) : {manifest['excluded_needs_review']}")
    print()
    print("Entity type breakdown (production units):")
    for etype, count in manifest["entity_type_counts"].items():
        print(f"  {etype:<25} {count:>5}")
    print()
    print("Per-document summary:")
    for doc_id, info in manifest["per_document"].items():
        print(
            f"  {doc_id}  {info['condition']:<30}"
            f"  total={info['total_units']:>4}  "
            f"prod={info['production_units']:>4}  "
            f"review={info['needs_review_units']:>4}"
        )
    print()
    print(f"Manifest written to : {knowledge_dir / 'index_manifest.json'}")
    print(f"SQLite DB           : {knowledge_dir / 'knowledge.db'}")
    print(f"BM25 index          : {knowledge_dir / 'bm25_index.pkl'}")
    print(f"TF-IDF index        : {knowledge_dir / 'tfidf_index.pkl'}")


if __name__ == "__main__":
    main()
