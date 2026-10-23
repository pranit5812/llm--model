"""Knowledge Indexer for the ICMR STW retrieval system.

Loads all canonical STW JSON files, decomposes them into KnowledgeUnits,
persists them in SQLite, and builds:
  - BM25 lexical index  (rank_bm25)
  - TF-IDF vector index (sklearn)

Production retrieval index excludes units flagged requires_manual_review=True.

No LLM, SLM, embeddings, or AI generation is used.
"""

from __future__ import annotations

import json
import logging
import os
import pickle
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from rank_bm25 import BM25Okapi
from sklearn.feature_extraction.text import TfidfVectorizer

from .units import KnowledgeUnit, decompose_stw_document, ENTITY_TYPES

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_DEFAULT_STRUCTURED_DIR = Path("data/processed/structured")
_DEFAULT_KNOWLEDGE_DIR = Path("data/knowledge")
_DB_NAME = "knowledge.db"
_BM25_INDEX_NAME = "bm25_index.pkl"
_TFIDF_INDEX_NAME = "tfidf_index.pkl"
_MANIFEST_NAME = "index_manifest.json"


# ---------------------------------------------------------------------------
# SQLite schema
# ---------------------------------------------------------------------------

_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_units (
    unit_id             TEXT PRIMARY KEY,
    document_id         TEXT NOT NULL,
    specialty           TEXT NOT NULL,
    condition           TEXT NOT NULL,
    section             TEXT NOT NULL,
    page_number         INTEGER NOT NULL,
    entity_type         TEXT NOT NULL,
    healthcare_tier     TEXT,
    content             TEXT NOT NULL,
    metadata_json       TEXT NOT NULL,
    review_status       TEXT NOT NULL DEFAULT 'extracted',
    requires_manual_review INTEGER NOT NULL DEFAULT 0,
    review_notes        TEXT,
    source_reference_json TEXT NOT NULL,
    indexed_at          TEXT NOT NULL,
    version_id          TEXT NOT NULL DEFAULT 'v1.0'
);

CREATE INDEX IF NOT EXISTS idx_document_id ON knowledge_units (document_id);
CREATE INDEX IF NOT EXISTS idx_condition ON knowledge_units (condition);
CREATE INDEX IF NOT EXISTS idx_entity_type ON knowledge_units (entity_type);
CREATE INDEX IF NOT EXISTS idx_review_status ON knowledge_units (review_status);
CREATE INDEX IF NOT EXISTS idx_requires_review ON knowledge_units (requires_manual_review);
"""



# ---------------------------------------------------------------------------
# KnowledgeIndexer
# ---------------------------------------------------------------------------

class KnowledgeIndexer:
    """Builds and manages the BM25 + TF-IDF knowledge index.

    Usage::

        indexer = KnowledgeIndexer()
        indexer.build(force=True)
        # --- later ---
        indexer.load()
        units = indexer.get_all_production_units()
    """

    def __init__(
        self,
        structured_dir: Path = _DEFAULT_STRUCTURED_DIR,
        knowledge_dir: Path = _DEFAULT_KNOWLEDGE_DIR,
        db_path: Optional[Path] = None,
        index_dir: Optional[Path] = None,
    ) -> None:
        self.structured_dir = Path(structured_dir)
        self.knowledge_dir = Path(index_dir) if index_dir else Path(knowledge_dir)
        self.db_path = Path(db_path) if db_path else self.knowledge_dir / _DB_NAME
        self.bm25_path = self.knowledge_dir / _BM25_INDEX_NAME
        self.tfidf_path = self.knowledge_dir / _TFIDF_INDEX_NAME
        self.manifest_path = self.knowledge_dir / _MANIFEST_NAME

        # In-memory state (loaded/built)
        self._all_units: List[KnowledgeUnit] = []
        self._prod_units: List[KnowledgeUnit] = []  # excludes needs_review
        self._bm25: Optional[BM25Okapi] = None
        self._tfidf_vectorizer: Optional[TfidfVectorizer] = None
        self._tfidf_matrix = None  # sparse matrix
        self._prod_unit_ids: List[str] = []

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def build(self, force: bool = False) -> Dict[str, Any]:
        """Load STW JSONs, decompose, persist, and build indexes.

        Returns a manifest dict summarising the build.
        """
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)

        if not force and self.manifest_path.exists():
            logger.info("Index already exists. Use force=True to rebuild.")
            self.load()
            with open(self.manifest_path, "r", encoding="utf-8") as f:
                return json.load(f)

        logger.info("Building knowledge index from %s", self.structured_dir)
        start = time.time()

        # 1. Load all STW JSON files
        json_files = sorted(self.structured_dir.glob("*.json"))
        if not json_files:
            raise FileNotFoundError(f"No structured JSON files found in {self.structured_dir}")

        all_units: List[KnowledgeUnit] = []
        per_document: Dict[str, Dict[str, Any]] = {}

        # Determine approved documents from document_versions (defaulting to Cardiology baseline)
        approved_docs: set[str] = set()
        if self.db_path.exists():
            try:
                conn = sqlite3.connect(self.db_path)
                c = conn.cursor()
                c.execute("SELECT document_id FROM document_versions WHERE review_status = 'approved'")
                approved_docs = {r[0] for r in c.fetchall()}
                conn.close()
            except Exception:
                pass
        if not approved_docs:
            approved_docs = {f"ICMR-CARD-{i:03d}" for i in range(1, 8)}

        for json_path in json_files:
            doc_dict = self._load_json(json_path)
            doc_id = doc_dict.get("metadata", {}).get("document_id", json_path.stem)
            is_approved = (doc_id in approved_docs) or (doc_dict.get("metadata", {}).get("specialty") == "Cardiology")

            units = decompose_stw_document(None, doc_dict)
            if not is_approved:
                for u in units:
                    u.requires_manual_review = True
                    u.review_status = "needs_review"

            all_units.extend(units)

            per_document[doc_id] = {
                "document_id": doc_id,
                "condition": doc_dict.get("metadata", {}).get("condition", ""),
                "specialty": doc_dict.get("metadata", {}).get("specialty", ""),
                "total_units": len(units),
                "needs_review_units": sum(1 for u in units if u.requires_manual_review),
                "production_units": sum(1 for u in units if not u.requires_manual_review),
            }

        self._all_units = all_units
        prod_units = [u for u in all_units if not u.requires_manual_review]
        self._prod_units = prod_units


        # 2. Persist to SQLite
        self._write_sqlite(all_units)

        # 3. Build BM25
        self._bm25, tokenized = self._build_bm25(prod_units)
        with open(self.bm25_path, "wb") as f:
            pickle.dump({"bm25": self._bm25, "unit_ids": [u.unit_id for u in prod_units]}, f)

        # 4. Build TF-IDF
        self._tfidf_vectorizer, self._tfidf_matrix = self._build_tfidf(prod_units)
        with open(self.tfidf_path, "wb") as f:
            pickle.dump({
                "vectorizer": self._tfidf_vectorizer,
                "matrix": self._tfidf_matrix,
                "unit_ids": [u.unit_id for u in prod_units],
            }, f)

        self._prod_unit_ids = [u.unit_id for u in prod_units]

        elapsed = round(time.time() - start, 2)

        # 5. Write manifest
        manifest = {
            "built_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_seconds": elapsed,
            "structured_dir": str(self.structured_dir),
            "total_documents": len(json_files),
            "total_units": len(all_units),
            "production_units": len(prod_units),
            "excluded_needs_review": len(all_units) - len(prod_units),
            "per_document": per_document,
            "entity_type_counts": self._entity_counts(prod_units),
        }

        with open(self.manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        logger.info(
            "Index built: %d total units, %d production, %d excluded (needs review) in %.2fs",
            len(all_units), len(prod_units), len(all_units) - len(prod_units), elapsed,
        )
        return manifest

    # ------------------------------------------------------------------
    # Load
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load persisted indexes from disk into memory."""
        if not self.bm25_path.exists() or not self.tfidf_path.exists():
            raise FileNotFoundError(
                f"Index files not found in {self.knowledge_dir}. Run build() first."
            )

        # Load all units from SQLite
        self._all_units = self._read_sqlite_all()
        self._prod_units = [u for u in self._all_units if not u.requires_manual_review]

        # Load BM25
        with open(self.bm25_path, "rb") as f:
            bm25_data = pickle.load(f)
        self._bm25 = bm25_data["bm25"]

        # Load TF-IDF
        with open(self.tfidf_path, "rb") as f:
            tfidf_data = pickle.load(f)
        self._tfidf_vectorizer = tfidf_data["vectorizer"]
        self._tfidf_matrix = tfidf_data["matrix"]
        self._prod_unit_ids = tfidf_data["unit_ids"]

        logger.info(
            "Index loaded: %d total, %d production units.",
            len(self._all_units), len(self._prod_units),
        )

    def is_loaded(self) -> bool:
        return self._bm25 is not None and self._tfidf_vectorizer is not None

    # ------------------------------------------------------------------
    # Accessors
    # ------------------------------------------------------------------

    def get_all_units(self) -> List[KnowledgeUnit]:
        return self._all_units

    def get_all_production_units(self) -> List[KnowledgeUnit]:
        return self._prod_units

    def get_unit_by_id(self, unit_id: str) -> Optional[KnowledgeUnit]:
        for u in self._all_units:
            if u.unit_id == unit_id:
                return u
        return None

    def get_bm25(self) -> BM25Okapi:
        if self._bm25 is None:
            raise RuntimeError("Index not loaded. Call build() or load() first.")
        return self._bm25

    def get_tfidf(self) -> Tuple[TfidfVectorizer, Any]:
        if self._tfidf_vectorizer is None:
            raise RuntimeError("Index not loaded. Call build() or load() first.")
        return self._tfidf_vectorizer, self._tfidf_matrix

    def get_prod_unit_ids(self) -> List[str]:
        return self._prod_unit_ids

    def get_manifest(self) -> Optional[Dict[str, Any]]:
        if not self.manifest_path.exists():
            return None
        with open(self.manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def incremental_promote_unit(self, unit_id: str) -> bool:
        """Incrementally promote an approved knowledge unit into production retrieval.

        Updates in-memory unit lists, BM25 and TF-IDF indexes, and persists
        the updated index artifacts without rebuilding the entire corpus.
        """
        if not self.is_loaded():
            self.load()

        # Find the unit in _all_units or load from SQLite
        unit = self.get_unit_by_id(unit_id)
        if unit is None and self.db_path.exists():
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM knowledge_units WHERE unit_id = ?", (unit_id,)).fetchone()
            conn.close()
            if row:
                sr = json.loads(row["source_reference_json"]) if row["source_reference_json"] else {}
                from ..models.knowledge_unit import KnowledgeUnit
                unit = KnowledgeUnit(
                    unit_id=row["unit_id"],
                    document_id=row["document_id"],
                    version_id=row["version_id"] if "version_id" in row.keys() and row["version_id"] else "v1.0",
                    specialty=row["specialty"] if "specialty" in row.keys() else "Cardiology",
                    condition=row["condition"],
                    page_number=row["page_number"],
                    section=row["section"],
                    entity_type=row["entity_type"],
                    content=row["content"],
                    source_reference=sr,
                    requires_manual_review=False,
                    review_status="approved",
                )
                self._all_units.append(unit)

        if unit is None:
            logger.warning("Cannot promote unit %s: not found in index or database.", unit_id)
            return False

        # Mark unit as production approved
        unit.requires_manual_review = False
        unit.review_status = "approved"

        # If already in production index, nothing more to do
        if unit_id in self._prod_unit_ids:
            return True

        self._prod_units.append(unit)
        self._prod_unit_ids.append(unit_id)

        # Update BM25 and TF-IDF in-memory
        bm25, tokenized = self._build_bm25(self._prod_units)
        self._bm25 = bm25

        tfidf_vec, tfidf_mat = self._build_tfidf(self._prod_units)
        self._tfidf_vectorizer = tfidf_vec
        self._tfidf_matrix = tfidf_mat

        # Persist updated indexes to disk
        try:
            with open(self.bm25_path, "wb") as f:
                pickle.dump({"bm25": self._bm25, "unit_ids": self._prod_unit_ids}, f)

            with open(self.tfidf_path, "wb") as f:
                pickle.dump({
                    "vectorizer": self._tfidf_vectorizer,
                    "matrix": self._tfidf_matrix,
                    "unit_ids": self._prod_unit_ids,
                }, f)

            manifest = self.get_manifest() or {}
            manifest["production_units_count"] = len(self._prod_units)
            manifest["total_units_count"] = len(self._all_units)
            manifest["last_incremental_update"] = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
        except Exception as e:
            logger.error("Failed to persist updated index files: %s", e)

        logger.info("Successfully incrementally promoted unit %s to production index.", unit_id)
        return True

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_json(path: Path) -> Dict[str, Any]:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    @staticmethod
    def _tokenize(text: str) -> List[str]:
        """Simple whitespace + lower tokenizer for BM25."""
        import re
        tokens = re.sub(r"[^\w\s]", " ", text.lower()).split()
        return [t for t in tokens if len(t) > 1]

    def _build_bm25(self, units: List[KnowledgeUnit]) -> Tuple[BM25Okapi, List[List[str]]]:
        tokenized = [self._tokenize(u.content) for u in units]
        bm25 = BM25Okapi(tokenized)
        return bm25, tokenized

    def _build_tfidf(self, units: List[KnowledgeUnit]) -> Tuple[TfidfVectorizer, Any]:
        corpus = [u.content for u in units]
        max_df = 0.95 if len(corpus) > 2 else 1.0
        vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=1,
            max_df=max_df,
            sublinear_tf=True,
            strip_accents="unicode",
        )
        matrix = vectorizer.fit_transform(corpus)
        return vectorizer, matrix

    def _write_sqlite(self, units: List[KnowledgeUnit]) -> None:
        """Write all units to SQLite (replaces existing data for the indexed documents)."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.executescript(_CREATE_TABLE_SQL)
            doc_ids = list(set(u.document_id for u in units))
            if doc_ids:
                placeholders = ",".join("?" for _ in doc_ids)
                conn.execute(f"DELETE FROM knowledge_units WHERE document_id IN ({placeholders})", doc_ids)
            now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            rows = []
            for u in units:
                rows.append((
                    u.unit_id, u.document_id, u.specialty, u.condition,
                    u.section, u.page_number, u.entity_type, u.healthcare_tier,
                    u.content,
                    json.dumps(u.metadata, ensure_ascii=False),
                    u.review_status,
                    1 if u.requires_manual_review else 0,
                    u.review_notes,
                    json.dumps(u.source_reference, ensure_ascii=False),
                    now,
                    getattr(u, "version_id", "v1.0"),
                ))
            conn.executemany(
                """INSERT OR REPLACE INTO knowledge_units (
                    unit_id, document_id, specialty, condition, section, page_number,
                    entity_type, healthcare_tier, content, metadata_json, review_status,
                    requires_manual_review, review_notes, source_reference_json, indexed_at, version_id
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                rows,
            )
            conn.commit()
        finally:
            conn.close()


    def _read_sqlite_all(self) -> List[KnowledgeUnit]:
        """Read all units from SQLite."""
        conn = sqlite3.connect(self.db_path)
        try:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM knowledge_units").fetchall()
        finally:
            conn.close()

        units = []
        for row in rows:
            units.append(KnowledgeUnit(
                unit_id=row["unit_id"],
                document_id=row["document_id"],
                specialty=row["specialty"],
                condition=row["condition"],
                section=row["section"],
                page_number=row["page_number"],
                entity_type=row["entity_type"],
                healthcare_tier=row["healthcare_tier"],
                content=row["content"],
                metadata=json.loads(row["metadata_json"]),
                review_status=row["review_status"],
                requires_manual_review=bool(row["requires_manual_review"]),
                review_notes=row["review_notes"],
                version_id=row["version_id"] if "version_id" in row.keys() else "v1.0",
                source_reference=json.loads(row["source_reference_json"]),
            ))
        return units


    @staticmethod
    def _entity_counts(units: List[KnowledgeUnit]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for u in units:
            counts[u.entity_type] = counts.get(u.entity_type, 0) + 1
        return dict(sorted(counts.items()))
