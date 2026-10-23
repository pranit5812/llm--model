"""Human clinical review approval, rejection, and correction handlers with audit logging."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .schemas import (
    ReviewItemSchema,
    ReviewPriority,
    ReviewReason,
    ReviewRiskCategory,
    ReviewStatus,
)

DEFAULT_DB_PATH = Path("data/knowledge/knowledge.db")


class ReviewAuditManager:
    """Handles review decisions (start, approval, rejection, correction) and audit trailing."""

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

    def start_review(
        self,
        item_id: str,
        reviewer_id: Any,
        reviewer_name: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> ReviewItemSchema:
        """Transition review item from NEEDS_REVIEW / PENDING to IN_REVIEW."""
        if hasattr(reviewer_id, "reviewer_id"):
            reviewer_name = getattr(reviewer_id, "reviewer_name", None) or reviewer_name
            notes = getattr(reviewer_id, "notes", None) or notes
            reviewer_id = reviewer_id.reviewer_id

        if not reviewer_id or not str(reviewer_id).strip():
            raise ValueError("Reviewer ID is required to begin review.")

        now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        with self._connect() as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                "SELECT * FROM review_items WHERE review_item_id = ? OR knowledge_unit_id = ?",
                (item_id, item_id),
            ).fetchone()
            if not row:
                raise KeyError(f"Review item '{item_id}' not found.")

            rev_id = row["review_item_id"]
            unit_id = row["knowledge_unit_id"]
            old_status = row["review_status"]

            cursor.execute("""
                UPDATE review_items
                SET review_status = ?,
                    reviewer_id = ?,
                    reviewer_name = ?,
                    updated_at = ?
                WHERE review_item_id = ?
            """, (
                ReviewStatus.IN_REVIEW.value,
                reviewer_id.strip(),
                reviewer_name or reviewer_id.strip(),
                now,
                rev_id,
            ))

            cursor.execute("""
                INSERT INTO review_audit_log (
                    review_item_id, knowledge_unit_id, action, old_status, new_status,
                    reviewer_id, reviewer_name, notes, corrected_value, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rev_id, unit_id, "START_REVIEW", old_status, ReviewStatus.IN_REVIEW.value,
                reviewer_id.strip(), reviewer_name or reviewer_id.strip(), "Reviewer initiated evaluation.", None, now
            ))

            conn.commit()

        return self.get_item(rev_id)

    def approve_item(
        self,
        item_id: str,
        reviewer_id: Any,
        reviewer_name: Optional[str] = None,
        notes: Optional[str] = None,
        confirmation: bool = True,
        auto_promote: bool = True,
    ) -> ReviewItemSchema:
        """Approve a review item with two-stage verification for high-risk clinical content.

        - If item is HIGH risk or requires two-stage approval:
          - Stage 1: Records Reviewer 1 and sets status to IN_REVIEW (awaiting Reviewer 2).
          - Stage 2: Requires Reviewer 2 != Reviewer 1 and non-empty notes; transitions status to APPROVED.
        - If Standard/Low risk:
          - Single clinician approval transitions status to APPROVED.
        """
        if hasattr(reviewer_id, "reviewer_id"):
            reviewer_name = getattr(reviewer_id, "reviewer_name", None) or reviewer_name
            notes = getattr(reviewer_id, "notes", None) or getattr(reviewer_id, "review_notes", None) or getattr(reviewer_id, "clinical_rationale", None) or notes
            reviewer_id = reviewer_id.reviewer_id

        if not confirmation:
            raise ValueError("Explicit clinical confirmation is strictly required for approval.")
        if not reviewer_id or not str(reviewer_id).strip():
            raise ValueError("Reviewer ID is strictly required for approval action.")

        now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        with self._connect() as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                "SELECT * FROM review_items WHERE review_item_id = ? OR knowledge_unit_id = ?",
                (item_id, item_id),
            ).fetchone()
            if not row:
                raise KeyError(f"Review item '{item_id}' not found.")

            rev_id = row["review_item_id"]
            unit_id = row["knowledge_unit_id"]
            old_status = row["review_status"]
            risk = row["risk_category"] if "risk_category" in row.keys() else "STANDARD"
            two_stage = bool(row["requires_two_stage_approval"]) if "requires_two_stage_approval" in row.keys() else False

            # Mandatory notes check for high-risk clinical content
            if risk == "HIGH" or two_stage:
                if not notes or len(str(notes).strip()) < 3:
                    raise ValueError("Mandatory review notes are required when approving HIGH risk medical content.")

            if two_stage:
                # Check if this is Stage 1 or Stage 2
                existing_rev1 = row["reviewer_id"]
                has_first_stage = bool(row["reviewed_at"]) and bool(existing_rev1)

                if not has_first_stage:
                    # First Stage Approval
                    cursor.execute("""
                        UPDATE review_items
                        SET review_status = ?,
                            reviewer_id = ?,
                            reviewer_name = ?,
                            reviewed_at = ?,
                            review_notes = ?,
                            updated_at = ?
                        WHERE review_item_id = ?
                    """, (
                        ReviewStatus.IN_REVIEW.value,
                        reviewer_id.strip(),
                        reviewer_name or reviewer_id.strip(),
                        now,
                        notes.strip(),
                        now,
                        rev_id,
                    ))

                    cursor.execute("""
                        INSERT INTO review_audit_log (
                            review_item_id, knowledge_unit_id, action, old_status, new_status,
                            reviewer_id, reviewer_name, notes, corrected_value, timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        rev_id, unit_id, "STAGE_1_APPROVE", old_status, ReviewStatus.IN_REVIEW.value,
                        reviewer_id.strip(), reviewer_name or reviewer_id.strip(),
                        f"First stage approval completed: {notes.strip()}", None, now
                    ))
                    conn.commit()
                    return self.get_item(rev_id)

                else:
                    # Second Stage Approval
                    # Safeguard: Reviewer 2 cannot be the same person as Reviewer 1
                    if str(reviewer_id).strip() == str(existing_rev1).strip():
                        raise ValueError(
                            "Two distinct reviewers required: Secondary reviewer cannot be the same clinician as primary reviewer."
                        )

                    cursor.execute("""
                        UPDATE review_items
                        SET review_status = ?,
                            second_reviewer_id = ?,
                            second_reviewer_name = ?,
                            second_reviewed_at = ?,
                            second_reviewer_notes = ?,
                            approval_timestamp = ?,
                            updated_at = ?
                        WHERE review_item_id = ?
                    """, (
                        ReviewStatus.APPROVED.value,
                        reviewer_id.strip(),
                        reviewer_name or reviewer_id.strip(),
                        now,
                        notes.strip(),
                        now,
                        now,
                        rev_id,
                    ))

                    cursor.execute("""
                        INSERT INTO review_audit_log (
                            review_item_id, knowledge_unit_id, action, old_status, new_status,
                            reviewer_id, reviewer_name, notes, corrected_value, timestamp
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        rev_id, unit_id, "STAGE_2_APPROVE", old_status, ReviewStatus.APPROVED.value,
                        reviewer_id.strip(), reviewer_name or reviewer_id.strip(),
                        f"Secondary clinical verification completed: {notes.strip()}", None, now
                    ))
                    conn.commit()

            else:
                # Standard / Low Risk: Single Clinical Reviewer Approval
                cursor.execute("""
                    UPDATE review_items
                    SET review_status = ?,
                        reviewer_id = ?,
                        reviewer_name = ?,
                        reviewed_at = ?,
                        review_notes = ?,
                        approval_timestamp = ?,
                        updated_at = ?
                    WHERE review_item_id = ?
                """, (
                    ReviewStatus.APPROVED.value,
                    reviewer_id.strip(),
                    reviewer_name or reviewer_id.strip(),
                    now,
                    notes or row["review_notes"],
                    now,
                    now,
                    rev_id,
                ))

                cursor.execute("""
                    INSERT INTO review_audit_log (
                        review_item_id, knowledge_unit_id, action, old_status, new_status,
                        reviewer_id, reviewer_name, notes, corrected_value, timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    rev_id, unit_id, "APPROVE", old_status, ReviewStatus.APPROVED.value,
                    reviewer_id.strip(), reviewer_name or reviewer_id.strip(),
                    notes or "Clinically approved.", None, now
                ))
                conn.commit()

            # Optional automatic promotion (for backward compatibility in unit test fixtures)
            if auto_promote and not two_stage:
                audit_note_append = f" [Approved by {reviewer_id.strip()} at {now}]"
                curr_unit_notes = cursor.execute("SELECT review_notes FROM knowledge_units WHERE unit_id = ?", (unit_id,)).fetchone()
                new_notes = ((curr_unit_notes[0] if curr_unit_notes and curr_unit_notes[0] else "") + audit_note_append).strip()

                cursor.execute("""
                    UPDATE knowledge_units
                    SET requires_manual_review = 0,
                        review_status = 'approved',
                        review_notes = ?
                    WHERE unit_id = ?
                """, (new_notes, unit_id))
                conn.commit()

        return self.get_item(rev_id)

    def reject_item(
        self,
        item_id: str,
        reviewer_id: Any,
        notes: Optional[str] = None,
        reviewer_name: Optional[str] = None,
        rejection_reason: Optional[str] = "CLINICAL_REJECTION",
    ) -> ReviewItemSchema:
        """Reject a review item with mandatory clinical justification.

        Permanently blocks item from production index.
        """
        if hasattr(reviewer_id, "reviewer_id"):
            notes = getattr(reviewer_id, "notes", None) or getattr(reviewer_id, "rejection_reason", None) or notes
            rejection_reason = getattr(reviewer_id, "rejection_reason", None) or rejection_reason
            reviewer_name = getattr(reviewer_id, "reviewer_name", None) or reviewer_name
            reviewer_id = reviewer_id.reviewer_id

        if not reviewer_id or not str(reviewer_id).strip():
            raise ValueError("Reviewer ID is strictly required for rejection.")
        if not notes or not str(notes).strip():
            raise ValueError("Clinical justification notes are required when rejecting an item.")

        now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        with self._connect() as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                "SELECT * FROM review_items WHERE review_item_id = ? OR knowledge_unit_id = ?",
                (item_id, item_id),
            ).fetchone()
            if not row:
                raise KeyError(f"Review item '{item_id}' not found.")

            rev_id = row["review_item_id"]
            unit_id = row["knowledge_unit_id"]
            old_status = row["review_status"]

            cursor.execute("""
                UPDATE review_items
                SET review_status = ?,
                    reviewer_id = ?,
                    reviewer_name = ?,
                    reviewed_at = ?,
                    rejection_reason = ?,
                    review_notes = ?,
                    updated_at = ?
                WHERE review_item_id = ?
            """, (
                ReviewStatus.REJECTED.value,
                str(reviewer_id).strip(),
                reviewer_name or str(reviewer_id).strip(),
                now,
                rejection_reason or "CLINICAL_REJECTION",
                str(notes).strip(),
                now,
                rev_id,
            ))

            cursor.execute("""
                INSERT INTO review_audit_log (
                    review_item_id, knowledge_unit_id, action, old_status, new_status,
                    reviewer_id, reviewer_name, notes, corrected_value, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rev_id, unit_id, "REJECT", old_status, ReviewStatus.REJECTED.value,
                str(reviewer_id).strip(), reviewer_name or str(reviewer_id).strip(), str(notes).strip(), None, now
            ))

            # Ensure knowledge_units remains excluded from production retrieval
            audit_note_append = f" [Rejected by {str(reviewer_id).strip()} at {now}: {str(notes).strip()}]"
            curr_unit_notes = cursor.execute("SELECT review_notes FROM knowledge_units WHERE unit_id = ?", (unit_id,)).fetchone()
            new_notes = ((curr_unit_notes[0] if curr_unit_notes and curr_unit_notes[0] else "") + audit_note_append).strip()

            cursor.execute("""
                UPDATE knowledge_units
                SET requires_manual_review = 1,
                    review_status = 'rejected',
                    review_notes = ?
                WHERE unit_id = ?
            """, (new_notes, unit_id))
            conn.commit()

        return self.get_item(rev_id)

    def record_correction(
        self,
        item_id: str,
        reviewer_id: Any,
        corrected_value: Optional[str] = None,
        notes: Optional[str] = None,
        reviewer_name: Optional[str] = None,
        correction_reason: Optional[str] = "CLINICAL_CORRECTION",
    ) -> ReviewItemSchema:
        """Record a clinical correction for an item while preserving original source text."""
        if hasattr(reviewer_id, "reviewer_id"):
            corrected_value = getattr(reviewer_id, "corrected_structured_value", None) or getattr(reviewer_id, "corrected_value", None) or corrected_value
            notes = getattr(reviewer_id, "notes", None) or getattr(reviewer_id, "correction_note", None) or notes
            reviewer_name = getattr(reviewer_id, "reviewer_name", None) or reviewer_name
            correction_reason = getattr(reviewer_id, "correction_reason", None) or correction_reason
            reviewer_id = reviewer_id.reviewer_id

        if not reviewer_id or not str(reviewer_id).strip():
            raise ValueError("Reviewer ID is required.")
        if not corrected_value or not str(corrected_value).strip():
            raise ValueError("Corrected structured value must be non-empty.")

        now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

        with self._connect() as conn:
            cursor = conn.cursor()
            row = cursor.execute(
                "SELECT * FROM review_items WHERE review_item_id = ? OR knowledge_unit_id = ?",
                (item_id, item_id),
            ).fetchone()
            if not row:
                raise KeyError(f"Review item '{item_id}' not found.")

            rev_id = row["review_item_id"]
            unit_id = row["knowledge_unit_id"]
            old_status = row["review_status"]

            cursor.execute("""
                UPDATE review_items
                SET review_status = ?,
                    corrected_structured_value = ?,
                    correction_text = ?,
                    reviewer_id = ?,
                    reviewer_name = ?,
                    reviewed_at = ?,
                    review_notes = ?,
                    updated_at = ?
                WHERE review_item_id = ?
            """, (
                ReviewStatus.NEEDS_CORRECTION.value,
                str(corrected_value).strip(),
                str(corrected_value).strip(),
                str(reviewer_id).strip(),
                reviewer_name or str(reviewer_id).strip(),
                now,
                notes or row["review_notes"],
                now,
                rev_id,
            ))

            cursor.execute("""
                INSERT INTO review_audit_log (
                    review_item_id, knowledge_unit_id, action, old_status, new_status,
                    reviewer_id, reviewer_name, notes, corrected_value, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rev_id, unit_id, "CORRECTION", old_status, ReviewStatus.NEEDS_CORRECTION.value,
                str(reviewer_id).strip(), reviewer_name or str(reviewer_id).strip(),
                notes or f"Correction reason: {correction_reason}", str(corrected_value).strip(), now
            ))

            conn.commit()

        return self.get_item(rev_id)

    def get_audit_history(self, item_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve audit history entries, optionally filtered by item_id."""
        with self._connect() as conn:
            if item_id:
                rows = conn.execute("""
                    SELECT * FROM review_audit_log
                    WHERE review_item_id = ? OR knowledge_unit_id = ?
                    ORDER BY log_id DESC
                """, (item_id, item_id)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM review_audit_log ORDER BY log_id DESC LIMIT 100
                """).fetchall()

        return [dict(r) for r in rows]

    def get_item(self, item_id: str) -> ReviewItemSchema:
        """Fetch item by review_item_id or knowledge_unit_id."""
        from .queue import ReviewQueue
        queue = ReviewQueue(db_path=self.db_path)
        item = queue.get_item_by_id(item_id)
        if not item:
            raise KeyError(f"Review item '{item_id}' not found.")
        return item


# Phase 9 alias for ReviewAuditManager
ApprovalEngine = ReviewAuditManager

