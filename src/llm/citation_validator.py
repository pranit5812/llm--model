"""Citation validator for verifying RAG citations against SQLite and retrieved evidence."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .schemas import CitationItem


class CitationValidationResult:
    """Result of citation validation."""

    def __init__(
        self,
        is_valid: bool,
        verified_citations: List[CitationItem],
        rejected_citations: List[Dict[str, Any]],
        rejection_reasons: List[str],
    ) -> None:
        self.is_valid = is_valid
        self.verified_citations = verified_citations
        self.rejected_citations = rejected_citations
        self.rejection_reasons = rejection_reasons

    def to_dict(self) -> Dict[str, Any]:
        return {
            "is_valid": self.is_valid,
            "verified_count": len(self.verified_citations),
            "rejected_count": len(self.rejected_citations),
            "rejection_reasons": self.rejection_reasons,
        }


class CitationValidator:
    """Validates citations against the SQLite knowledge store and retrieved context."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = db_path or Path("data/knowledge/knowledge.db")

    def _get_db_unit(self, unit_id: str) -> Optional[Dict[str, Any]]:
        """Look up knowledge unit record from SQLite."""
        if not self.db_path.exists():
            return None
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT unit_id, document_id, condition, page_number, section, "
                "content, requires_manual_review, source_reference_json "
                "FROM knowledge_units WHERE unit_id = ?",
                (unit_id,),
            )
            row = cursor.fetchone()
            if row:
                return dict(row)
        return None

    def validate_citations(
        self,
        citations: List[CitationItem],
        retrieved_unit_ids: Set[str],
    ) -> CitationValidationResult:
        """Verify that every citation is grounded in retrieved, production-approved evidence.

        Checks:
        1. Unit ID exists.
        2. Unit ID was actually retrieved in the current session.
        3. Unit exists in SQLite database.
        4. Document ID matches database.
        5. Page number matches database.
        6. Unit is approved for production (requires_manual_review == 0).
        """
        verified: List[CitationItem] = []
        rejected: List[Dict[str, Any]] = []
        reasons: List[str] = []

        for citation in citations:
            uid = citation.knowledge_unit_id

            # 1. Did the LLM cite a unit that was in the retrieved evidence?
            if uid not in retrieved_unit_ids:
                rejected.append(citation.model_dump())
                reasons.append(f"Citation unit '{uid}' was not in the retrieved evidence pool.")
                continue

            # 2. Does unit exist in SQLite?
            db_row = self._get_db_unit(uid)
            if not db_row:
                rejected.append(citation.model_dump())
                reasons.append(f"Citation unit '{uid}' not found in SQLite knowledge store.")
                continue

            # 3. Document ID match
            if db_row["document_id"] != citation.document_id:
                rejected.append(citation.model_dump())
                reasons.append(
                    f"Document ID mismatch for '{uid}': cited '{citation.document_id}' vs DB '{db_row['document_id']}'."
                )
                continue

            # 4. Page number match
            if db_row["page_number"] != citation.page_number:
                rejected.append(citation.model_dump())
                reasons.append(
                    f"Page mismatch for '{uid}': cited {citation.page_number} vs DB {db_row['page_number']}."
                )
                continue

            # 5. Production approval check
            if bool(db_row.get("requires_manual_review", 0)):
                rejected.append(citation.model_dump())
                reasons.append(f"Citation unit '{uid}' is flagged as requiring manual review.")
                continue

            # Citation verified
            verified.append(citation)

        is_valid = len(rejected) == 0 and len(verified) > 0
        return CitationValidationResult(
            is_valid=is_valid,
            verified_citations=verified,
            rejected_citations=rejected,
            rejection_reasons=reasons,
        )
