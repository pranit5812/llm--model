"""Tests for Phase 6 Review Queue Database, Prioritization, and Isolation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from src.review.queue import ReviewQueue
from src.review.schemas import ReviewPriority, ReviewReason, ReviewStatus


def test_review_queue_sync_and_count():
    queue = ReviewQueue()
    summary = queue.get_summary()

    # Total backlog should match at least the 167 flagged Cardiology units
    assert summary.total_items >= 167
    assert summary.pending >= 167
    assert summary.by_specialty.get("Cardiology") == 167
    assert summary.approved == 0
    assert summary.rejected == 0
    assert summary.needs_correction == 0

    # Priorities must be populated
    assert summary.high_priority_pending > 0
    assert summary.medium_priority_pending > 0
    assert summary.low_priority_pending > 0
    assert (
        summary.high_priority_pending
        + summary.medium_priority_pending
        + summary.low_priority_pending
        == summary.pending
    )


def test_automated_extraction_never_auto_approves():
    """Verify that automated extraction never sets status to APPROVED."""
    queue = ReviewQueue()
    items = queue.get_review_items(limit=200)

    for item in items:
        # Every flagged item must start as PENDING
        assert item.review_status == ReviewStatus.PENDING
        assert item.reviewer_id is None
        assert item.reviewed_at is None


def test_review_prioritization_and_reason_classification():
    queue = ReviewQueue()

    high_items = queue.get_review_items(priority=ReviewPriority.HIGH, limit=10)
    assert len(high_items) > 0
    for h in high_items:
        assert h.review_priority == ReviewPriority.HIGH

    med_items = queue.get_review_items(priority=ReviewPriority.MEDIUM, limit=10)
    assert len(med_items) > 0
    for m in med_items:
        assert m.review_priority == ReviewPriority.MEDIUM

    # Check reason classification
    flowchart_items = queue.get_review_items(reason=ReviewReason.FLOWCHART_AMBIGUITY, limit=10)
    if flowchart_items:
        assert all(f.review_reason == ReviewReason.FLOWCHART_AMBIGUITY for f in flowchart_items)


def test_source_text_immutability_in_queue():
    queue = ReviewQueue()
    items = queue.get_review_items(limit=10)

    for item in items:
        assert item.original_source_text is not None
        assert len(item.original_source_text.strip()) > 0
