"""Controlled production promotion engine and pre-promotion validation layer."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schemas import (
    PromotionValidationResult,
    ReviewPriority,
    ReviewRiskCategory,
    ReviewStatus,
)

logger = logging.getLogger(__name__)
DEFAULT_DB_PATH = Path("data/knowledge/knowledge.db")


class PromotionValidator:
    """Performs rigorous pre-promotion safety, schema, and clinical checks."""

    def __init__(self, db_path: Optional[Path] = None, queue: Optional[Any] = None) -> None:
        if queue is not None:
            self.db_path = getattr(queue, "db_path", DEFAULT_DB_PATH)
        else:
            self.db_path = db_path or DEFAULT_DB_PATH

    def _connect(self) -> sqlite3.Connection:
        if not self.db_path.exists():
            raise FileNotFoundError(f"Knowledge database not found at {self.db_path.resolve()}")
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def validate(self, review_id_or_unit_id: str) -> PromotionValidationResult:
        """Run all mandatory validation checks before permitting promotion to production index."""
        errors: List[str] = []
        warnings: List[str] = []

        with self._connect() as conn:
            # 1. Fetch review item
            rev_row = conn.execute(
                "SELECT * FROM review_items WHERE review_item_id = ? OR knowledge_unit_id = ?",
                (review_id_or_unit_id, review_id_or_unit_id),
            ).fetchone()

            if not rev_row:
                return PromotionValidationResult(
                    is_valid=False,
                    errors=[f"Review item '{review_id_or_unit_id}' does not exist."],
                    warnings=[],
                    unit_id=review_id_or_unit_id,
                    document_id="UNKNOWN",
                    version_id="UNKNOWN",
                )

            unit_id = rev_row["knowledge_unit_id"]
            doc_id = rev_row["document_id"]
            ver_id = rev_row["version_id"] if "version_id" in rev_row.keys() and rev_row["version_id"] else "v1.0"
            status = rev_row["review_status"]
            risk = rev_row["risk_category"] if "risk_category" in rev_row.keys() else "STANDARD"
            two_stage = bool(rev_row["requires_two_stage_approval"]) if "requires_two_stage_approval" in rev_row.keys() else False

            # 2. Check review status
            if status in [ReviewStatus.REJECTED.value, "REJECTED"]:
                errors.append("Rejected content must NEVER be promoted to production index.")
            elif status in [ReviewStatus.NEEDS_CORRECTION.value, "NEEDS_CORRECTION"]:
                errors.append("Content marked as NEEDS_CORRECTION cannot enter production until approved.")
            elif status in [ReviewStatus.PENDING.value, ReviewStatus.NEEDS_REVIEW.value, "PENDING", "NEEDS_REVIEW"]:
                errors.append("Unreviewed/Pending content cannot be promoted to production index.")
            elif status in [ReviewStatus.IN_REVIEW.value, "IN_REVIEW"]:
                errors.append("Content currently IN_REVIEW has not completed clinical approval.")
            elif status not in [ReviewStatus.APPROVED.value, ReviewStatus.ELIGIBLE_FOR_PRODUCTION.value, "APPROVED", "ELIGIBLE_FOR_PRODUCTION", ReviewStatus.PROMOTED.value, "PROMOTED"]:
                errors.append(f"Invalid status '{status}' for production promotion.")

            # 3. Two-Stage Approval Safeguard
            if two_stage:
                rev1 = rev_row["reviewer_id"]
                rev2 = rev_row["second_reviewer_id"] if "second_reviewer_id" in rev_row.keys() else None
                if not rev1 or not rev1.strip():
                    errors.append("Two-stage approval item missing primary clinical reviewer ID.")
                if not rev2 or not rev2.strip():
                    errors.append("Two-stage clinical approval requires two distinct clinical approvals before promotion.")
                elif rev1.strip() == rev2.strip():
                    errors.append("Two-stage approval violation: primary and secondary reviewers cannot be the same person.")

            # Reviewer notes check
            if risk == "HIGH" or two_stage:
                rev1_notes = rev_row["review_notes"]
                if not rev1_notes or len(rev1_notes.strip()) < 3:
                    errors.append("Mandatory clinical justification notes missing for review of HIGH-risk item.")

            # 4. Fetch knowledge unit in SQLite
            ku_row = conn.execute("SELECT * FROM knowledge_units WHERE unit_id = ?", (unit_id,)).fetchone()
            if not ku_row:
                errors.append(f"Knowledge unit '{unit_id}' not found in knowledge_units database.")
            else:
                # Schema and Provenance Validation
                if not ku_row["content"] or len(ku_row["content"].strip()) < 5:
                    errors.append("Knowledge unit content is empty or incomplete.")
                if not ku_row["condition"] or len(ku_row["condition"].strip()) < 2:
                    errors.append("Knowledge unit condition title is missing.")
                if ku_row["page_number"] <= 0:
                    errors.append("Invalid page number (<= 0) in knowledge unit provenance.")
                if not ku_row["section"] or len(ku_row["section"].strip()) < 2:
                    errors.append("Knowledge unit section is missing.")

                # Provenance source text check
                orig_src = rev_row["original_source_text"]
                if not orig_src or len(orig_src.strip()) < 5:
                    errors.append("Original ICMR source text is missing or unverified.")

            # 5. Document & Version Catalogue Check
            import re
            if not re.match(r"^ICMR-[A-Z]+-\d{3}$", str(doc_id)):
                errors.append(f"Document '{doc_id}' is not in the official ICMR document catalogue.")

            has_doc_table = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='document_versions'").fetchone()
            if has_doc_table:
                doc_row = conn.execute(
                    "SELECT * FROM document_versions WHERE document_id = ?",
                    (doc_id,),
                ).fetchone()
                if doc_row:
                    precedence = doc_row["precedence"] if "precedence" in doc_row.keys() else "CURRENT"
                    if precedence == "SUPERSEDED":
                        warnings.append(
                            f"Document '{doc_id}' is marked as SUPERSEDED. Ensure clinical precedence warning is preserved."
                        )

            # 6. Check for duplicate active production units with contradictory content
            if ku_row:
                dup_rows = conn.execute("""
                    SELECT unit_id, content FROM knowledge_units
                    WHERE document_id = ? AND condition = ? AND page_number = ?
                      AND section = ? AND entity_type = ? AND requires_manual_review = 0
                      AND unit_id != ?
                """, (doc_id, ku_row["condition"], ku_row["page_number"], ku_row["section"], ku_row["entity_type"], unit_id)).fetchall()
                if dup_rows:
                    warnings.append(f"Found {len(dup_rows)} existing active production unit(s) for the same document page and section.")

            rev1_notes_val = rev_row["review_notes"] if "review_notes" in rev_row.keys() else ""
            rev1_val = rev_row["reviewer_id"] if "reviewer_id" in rev_row.keys() else ""
            rev2_val = rev_row["second_reviewer_id"] if "second_reviewer_id" in rev_row.keys() else ""

            validation_checks = [
                {"check_name": "check_item_exists", "passed": rev_row is not None, "message": "Review item exists in review database"},
                {"check_name": "check_review_status", "passed": status in [ReviewStatus.APPROVED.value, ReviewStatus.ELIGIBLE_FOR_PRODUCTION.value, "APPROVED", "ELIGIBLE_FOR_PRODUCTION", ReviewStatus.PROMOTED.value, "PROMOTED"], "message": f"Review status: {status}"},
                {"check_name": "check_two_stage_approval", "passed": not two_stage or (bool(rev1_val) and bool(rev2_val) and str(rev1_val).strip() != str(rev2_val).strip()), "message": "Two distinct clinical reviewers verified"},
                {"check_name": "check_primary_reviewer_notes", "passed": not (risk == "HIGH" or two_stage) or (bool(rev1_notes_val) and len(str(rev1_notes_val).strip()) >= 3), "message": "Mandatory clinical justification notes verified"},
                {"check_name": "check_unit_exists", "passed": ku_row is not None, "message": "Knowledge unit exists in SQLite"},
                {"check_name": "check_content_non_empty", "passed": ku_row is not None and bool(ku_row["content"]) and len(str(ku_row["content"]).strip()) >= 5, "message": "Knowledge unit content non-empty"},
                {"check_name": "check_provenance_condition", "passed": ku_row is not None and bool(ku_row["condition"]) and len(str(ku_row["condition"]).strip()) >= 2, "message": "Condition title valid"},
                {"check_name": "check_provenance_page", "passed": ku_row is not None and ku_row["page_number"] > 0, "message": "Page number > 0"},
                {"check_name": "check_provenance_section", "passed": ku_row is not None and bool(ku_row["section"]) and len(str(ku_row["section"]).strip()) >= 2, "message": "Section heading valid"},
                {"check_name": "check_source_text_integrity", "passed": bool(rev_row["original_source_text"]) and len(str(rev_row["original_source_text"]).strip()) >= 5, "message": "Original source text preserved"},
                {"check_name": "check_catalogue_registration", "passed": bool(re.match(r"^ICMR-[A-Z]+-\d{3}$", str(doc_id))), "message": f"Document catalogue registration ({doc_id})"},
            ]

        is_valid = len(errors) == 0
        return PromotionValidationResult(
            is_valid=is_valid,
            eligible_for_production=is_valid,
            validation_checks=validation_checks,
            errors=errors,
            warnings=warnings,
            unit_id=unit_id,
            document_id=doc_id,
            version_id=ver_id,
        )


class PromotionManager:
    """Manages atomic promotion of approved knowledge units into production index."""

    def __init__(self, db_path: Optional[Path] = None, queue: Optional[Any] = None) -> None:
        if queue is not None:
            self.db_path = getattr(queue, "db_path", DEFAULT_DB_PATH)
        else:
            self.db_path = db_path or DEFAULT_DB_PATH
        self.validator = PromotionValidator(db_path=self.db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def promote_item(
        self,
        review_id_or_unit_id: str,
        promoter_id: str,
        promoter_name: Optional[str] = None,
        notes: Optional[str] = None,
        indexer: Optional[Any] = None,
    ) -> PromotionValidationResult:
        """Validate and atomically promote an approved unit into production index.

        If validation fails, returns result with errors and logs a blocked attempt.
        If validation succeeds, clears requires_manual_review on knowledge_units,
        updates review_items to PROMOTED, logs audit entry, and calls incremental indexing.
        """
        if not promoter_id or not promoter_id.strip():
            raise ValueError("Authorized promoter ID is required to promote content to production.")

        now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        # 1. Run rigorous validation
        val_result = self.validator.validate(review_id_or_unit_id)

        with self._connect() as conn:
            cursor = conn.cursor()
            rev_row = cursor.execute(
                "SELECT review_item_id, knowledge_unit_id, review_status FROM review_items WHERE review_item_id = ? OR knowledge_unit_id = ?",
                (review_id_or_unit_id, review_id_or_unit_id),
            ).fetchone()

            if not rev_row:
                return val_result

            rev_id = rev_row["review_item_id"]
            unit_id = rev_row["knowledge_unit_id"]
            old_status = rev_row["review_status"]

            if not val_result.is_valid:
                # Log blocked promotion attempt
                cursor.execute("""
                    INSERT INTO review_audit_log (
                        review_item_id, knowledge_unit_id, action, old_status, new_status,
                        reviewer_id, reviewer_name, notes, corrected_value, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    rev_id, unit_id, "PROMOTION_BLOCKED", old_status, old_status,
                    promoter_id.strip(), promoter_name or promoter_id.strip(),
                    f"Blocked errors: {'; '.join(val_result.errors)}", None, now
                ))
                conn.commit()
                return val_result

            # 2. Validation passed — execute atomic promotion in SQLite
            cursor.execute("""
                UPDATE review_items
                SET review_status = ?,
                    updated_at = ?
                WHERE review_item_id = ?
            """, (ReviewStatus.PROMOTED.value, now, rev_id))

            cursor.execute("""
                UPDATE knowledge_units
                SET requires_manual_review = 0,
                    review_status = 'approved',
                    review_notes = CASE
                        WHEN review_notes IS NULL OR review_notes = '' THEN ?
                        ELSE review_notes || ' ' || ?
                    END
                WHERE unit_id = ?
            """, (
                f"[Promoted to production by {promoter_id} at {now}]",
                f"[Promoted to production by {promoter_id} at {now}]",
                unit_id,
            ))

            cursor.execute("""
                INSERT INTO review_audit_log (
                    review_item_id, knowledge_unit_id, action, old_status, new_status,
                    reviewer_id, reviewer_name, notes, corrected_value, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rev_id, unit_id, "PROMOTE", old_status, ReviewStatus.PROMOTED.value,
                promoter_id.strip(), promoter_name or promoter_id.strip(),
                notes or "Passed all promotion validation checks.", None, now
            ))

            conn.commit()

        # 3. Incremental indexing update
        t0 = time.perf_counter()
        indexed_ok = False
        try:
            if indexer is None:
                from ..knowledge.indexer import KnowledgeIndexer
                indexer = KnowledgeIndexer()
            indexed_ok = indexer.incremental_promote_unit(unit_id)
        except Exception as e:
            logger.error("Incremental indexing warning on unit %s: %s", unit_id, e)

        t1 = time.perf_counter()
        val_result.indexed_successfully = indexed_ok
        val_result.indexing_latency_ms = (t1 - t0) * 1000.0
        val_result.promoted_at = now
        logger.info("Successfully promoted unit %s to production index by %s in %.2f ms.", unit_id, promoter_id, val_result.indexing_latency_ms)
        return val_result
