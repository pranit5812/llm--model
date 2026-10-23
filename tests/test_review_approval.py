"""Tests for Review Decisions (Approval, Rejection, Correction) and Audit Trail."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from src.review.approval import ReviewAuditManager
from src.review.queue import ReviewQueue
from src.review.schemas import ReviewStatus


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create an isolated copy of knowledge.db for mutation tests."""
    orig_db = Path("data/knowledge/knowledge.db")
    target_db = tmp_path / "test_knowledge.db"
    shutil.copy(orig_db, target_db)
    # Ensure queue tables are populated
    queue = ReviewQueue(db_path=target_db)
    queue.sync_from_knowledge_units()
    return target_db


def test_approve_requires_reviewer_id(temp_db: Path):
    audit = ReviewAuditManager(db_path=temp_db)
    with pytest.raises(ValueError, match="Reviewer ID is strictly required"):
        audit.approve_item(item_id="REV-ICMR-CARD-001-KU-001", reviewer_id="")


def test_approve_item_flow(temp_db: Path):
    queue = ReviewQueue(db_path=temp_db)
    audit = ReviewAuditManager(db_path=temp_db)

    pending_items = queue.get_review_items(status=ReviewStatus.PENDING, limit=1)
    assert len(pending_items) == 1
    target = pending_items[0]

    # Approve
    updated = audit.approve_item(
        item_id=target.review_item_id,
        reviewer_id="DR-TEST-001",
        notes="Clinically verified from PDF page.",
    )

    assert updated.review_status == ReviewStatus.APPROVED
    assert updated.reviewer_id == "DR-TEST-001"
    assert updated.reviewed_at is not None

    # Check that knowledge_units.requires_manual_review is now 0 (entering production)
    with sqlite3.connect(temp_db) as conn:
        row = conn.execute(
            "SELECT requires_manual_review FROM knowledge_units WHERE unit_id = ?",
            (target.knowledge_unit_id,),
        ).fetchone()
        assert row[0] == 0

    # Verify audit log entry
    history = audit.get_audit_history(item_id=target.review_item_id)
    assert len(history) >= 1
    assert history[0]["action"] == "APPROVE"
    assert history[0]["reviewer_id"] == "DR-TEST-001"


def test_reject_item_flow(temp_db: Path):
    queue = ReviewQueue(db_path=temp_db)
    audit = ReviewAuditManager(db_path=temp_db)

    pending_items = queue.get_review_items(status=ReviewStatus.PENDING, limit=1)
    target = pending_items[0]

    # Rejection requires reason notes
    with pytest.raises(ValueError, match="justification notes are required"):
        audit.reject_item(item_id=target.review_item_id, reviewer_id="DR-TEST-001", notes="")

    # Reject
    updated = audit.reject_item(
        item_id=target.review_item_id,
        reviewer_id="DR-TEST-001",
        notes="Unresolvable extraction artifact.",
    )

    assert updated.review_status == ReviewStatus.REJECTED
    assert updated.reviewer_id == "DR-TEST-001"

    # Check knowledge_units remains excluded
    with sqlite3.connect(temp_db) as conn:
        row = conn.execute(
            "SELECT requires_manual_review FROM knowledge_units WHERE unit_id = ?",
            (target.knowledge_unit_id,),
        ).fetchone()
        assert row[0] == 1


def test_record_correction_preserves_immutable_source_text(temp_db: Path):
    queue = ReviewQueue(db_path=temp_db)
    audit = ReviewAuditManager(db_path=temp_db)

    pending_items = queue.get_review_items(status=ReviewStatus.PENDING, limit=1)
    target = pending_items[0]
    orig_source = target.original_source_text

    # Record correction
    updated = audit.record_correction(
        item_id=target.review_item_id,
        reviewer_id="DR-TEST-001",
        corrected_value="Aspirin: Loading dose 300 mg orally stat.",
        notes="Clarified dosage.",
    )

    assert updated.review_status == ReviewStatus.NEEDS_CORRECTION
    assert updated.corrected_structured_value == "Aspirin: Loading dose 300 mg orally stat."
    # CRITICAL: original source text must remain intact!
    assert updated.original_source_text == orig_source

    history = audit.get_audit_history(item_id=target.review_item_id)
    assert any(h["action"] == "CORRECTION" for h in history)
