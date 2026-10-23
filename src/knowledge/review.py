"""Review queue for ICMR STW knowledge units flagged for manual review.

Surfaces content that requires clinical expert verification before it can be
promoted to the production retrieval index. This includes:
  - Ambiguous flowchart branches
  - Multi-column table wraps
  - Drug name typos
  - Incomplete dosage information
  - Version conflicts

No LLM, SLM, or AI generation is used.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

_DEFAULT_DB_PATH = Path("data/knowledge/knowledge.db")


@dataclass
class ReviewItem:
    """A knowledge unit flagged for human expert review."""
    unit_id: str
    document_id: str
    condition: str
    specialty: str
    section: str
    page_number: int
    entity_type: str
    content: str
    review_status: str
    review_notes: Optional[str]
    source_reference: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "document_id": self.document_id,
            "condition": self.condition,
            "specialty": self.specialty,
            "section": self.section,
            "page_number": self.page_number,
            "entity_type": self.entity_type,
            "content": self.content,
            "review_status": self.review_status,
            "review_notes": self.review_notes,
            "source_reference": self.source_reference,
        }


class ReviewQueue:
    """Queries the SQLite knowledge store for units requiring manual review.

    Provides structured access to the review backlog so a clinical expert
    can inspect and verify flagged evidence before it enters the production
    retrieval index.
    """

    def __init__(self, db_path: Path = _DEFAULT_DB_PATH) -> None:
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Knowledge database not found at {self.db_path}. "
                "Run 'python scripts/build_index.py' first."
            )
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_review_items(
        self,
        document_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ReviewItem]:
        """Return paginated list of units flagged for manual review."""
        import json

        conditions = ["requires_manual_review = 1"]
        params: List[Any] = []

        if document_id:
            conditions.append("document_id = ?")
            params.append(document_id)
        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)

        where = " AND ".join(conditions)
        params += [limit, offset]

        sql = f"""
            SELECT unit_id, document_id, condition, specialty, section,
                   page_number, entity_type, content, review_status,
                   review_notes, source_reference_json
            FROM knowledge_units
            WHERE {where}
            ORDER BY document_id, entity_type, unit_id
            LIMIT ? OFFSET ?
        """

        conn = self._connect()
        try:
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()

        return [
            ReviewItem(
                unit_id=r["unit_id"],
                document_id=r["document_id"],
                condition=r["condition"],
                specialty=r["specialty"],
                section=r["section"],
                page_number=r["page_number"],
                entity_type=r["entity_type"],
                content=r["content"],
                review_status=r["review_status"],
                review_notes=r["review_notes"],
                source_reference=json.loads(r["source_reference_json"]),
            )
            for r in rows
        ]

    def get_review_summary(self) -> Dict[str, Any]:
        """Return summary statistics of the review backlog."""
        conn = self._connect()
        try:
            total = conn.execute(
                "SELECT COUNT(*) FROM knowledge_units WHERE requires_manual_review = 1"
            ).fetchone()[0]

            by_doc = conn.execute("""
                SELECT document_id, condition, COUNT(*) as count
                FROM knowledge_units
                WHERE requires_manual_review = 1
                GROUP BY document_id
                ORDER BY document_id
            """).fetchall()

            by_type = conn.execute("""
                SELECT entity_type, COUNT(*) as count
                FROM knowledge_units
                WHERE requires_manual_review = 1
                GROUP BY entity_type
                ORDER BY count DESC
            """).fetchall()
        finally:
            conn.close()

        return {
            "total_review_items": total,
            "by_document": [
                {"document_id": r["document_id"], "condition": r["condition"], "count": r["count"]}
                for r in by_doc
            ],
            "by_entity_type": [
                {"entity_type": r["entity_type"], "count": r["count"]}
                for r in by_type
            ],
        }

    def count(self) -> int:
        conn = self._connect()
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM knowledge_units WHERE requires_manual_review = 1"
            ).fetchone()[0]
        finally:
            conn.close()
