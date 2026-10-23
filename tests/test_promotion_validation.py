"""Phase 9 Test: Pre-Promotion Validation Suite.

Verifies the 11 safety validation checks enforced by PromotionValidator before
any clinical content can enter the production hybrid retrieval index.
"""

import pytest
from src.review.queue import ReviewQueue
from src.review.promotion import PromotionValidator
from src.review.schemas import (
    ReviewPriority,
    ReviewReason,
    ReviewStatus,
    ReviewRiskCategory,
)


@pytest.fixture
def clean_queue(tmp_path):
    db_path = tmp_path / "test_promotion_val.db"
    return ReviewQueue(db_path=db_path)


def test_validator_blocks_unapproved_item(clean_queue):
    queue = clean_queue
    validator = PromotionValidator(queue=queue)

    unit_id = "UNIT-VAL-UNAPPROVED"
    queue.upsert_review_item(
        unit_id=unit_id,
        document_id="ICMR-CARD-001",
        condition="STEMI",
        section="Management",
        page_number=1,
        entity_type="drug_recommendation",
        content="Morphine 2-4 mg IV titrated slowly.",
        original_source_text="Morphine 2-4 mg IV titrated slowly.",
        review_reason=ReviewReason.FLOWCHART_AMBIGUITY,
        review_priority=ReviewPriority.HIGH,
        risk_category=ReviewRiskCategory.HIGH,
    )

    # Item is still in NEEDS_REVIEW / PENDING
    result = validator.validate(unit_id)
    assert result.eligible_for_production is False
    assert any("Unreviewed" in err or "Pending" in err or "APPROVED" in err for err in result.errors)


def test_validator_blocks_incomplete_provenance(clean_queue):
    queue = clean_queue
    validator = PromotionValidator(queue=queue)

    unit_id = "UNIT-VAL-NOPROV"
    queue.upsert_review_item(
        unit_id=unit_id,
        document_id="ICMR-CARD-001",
        condition="",  # Missing condition
        section="",    # Missing section
        page_number=0, # Invalid page
        entity_type="general",
        content="Some clinical note.",
        original_source_text="Some clinical note.",
        review_reason=ReviewReason.SOURCE_AMBIGUITY,
        review_priority=ReviewPriority.LOW,
        risk_category=ReviewRiskCategory.LOW,
    )
    # Force status to APPROVED in DB for test
    with queue._connect() as conn:
        conn.execute("UPDATE review_items SET review_status = 'APPROVED', reviewer_id = 'DR-TEST' WHERE review_item_id = ?", (unit_id,))

    result = validator.validate(unit_id)
    assert result.eligible_for_production is False
    assert any("provenance" in err.lower() or "page_number" in err.lower() or "condition" in err.lower() for err in result.errors)


def test_validator_blocks_missing_source_text(clean_queue):
    queue = clean_queue
    validator = PromotionValidator(queue=queue)

    unit_id = "UNIT-VAL-NOSOURCE"
    queue.upsert_review_item(
        unit_id=unit_id,
        document_id="ICMR-CARD-001",
        condition="STEMI",
        section="Management",
        page_number=1,
        entity_type="drug_recommendation",
        content="Aspirin 300 mg",
        original_source_text="",  # Empty source text violates source preservation invariant
        review_reason=ReviewReason.SOURCE_AMBIGUITY,
        review_priority=ReviewPriority.LOW,
        risk_category=ReviewRiskCategory.LOW,
    )
    with queue._connect() as conn:
        conn.execute("UPDATE review_items SET review_status = 'APPROVED', reviewer_id = 'DR-TEST' WHERE review_item_id = ?", (unit_id,))

    result = validator.validate(unit_id)
    assert result.eligible_for_production is False
    assert any("source text" in err.lower() for err in result.errors)


def test_validator_blocks_unregistered_document(clean_queue):
    queue = clean_queue
    validator = PromotionValidator(queue=queue)

    unit_id = "UNIT-VAL-BAD-DOC"
    queue.upsert_review_item(
        unit_id=unit_id,
        document_id="UNOFFICIAL-DOC-999",  # Not in official catalogue
        condition="Hypothetical Condition",
        section="Management",
        page_number=1,
        entity_type="guideline",
        content="Guideline statement.",
        original_source_text="Guideline statement.",
        review_reason=ReviewReason.SOURCE_AMBIGUITY,
        review_priority=ReviewPriority.LOW,
        risk_category=ReviewRiskCategory.LOW,
    )
    with queue._connect() as conn:
        conn.execute("UPDATE review_items SET review_status = 'APPROVED', reviewer_id = 'DR-TEST' WHERE review_item_id = ?", (unit_id,))

    result = validator.validate(unit_id)
    assert result.eligible_for_production is False
    assert any("catalogue" in err.lower() for err in result.errors)


def test_validator_passes_fully_compliant_unit(clean_queue):
    queue = clean_queue
    validator = PromotionValidator(queue=queue)

    unit_id = "UNIT-VAL-PASS"
    queue.upsert_review_item(
        unit_id=unit_id,
        document_id="ICMR-CARD-001",
        condition="STEMI",
        section="Emergency Management",
        page_number=2,
        entity_type="drug_recommendation",
        content="Sublingual Nitroglycerin 0.4 mg every 5 minutes up to 3 doses if SBP > 90 mmHg.",
        original_source_text="Sublingual Nitroglycerin 0.4 mg every 5 minutes up to 3 doses if SBP > 90 mmHg.",
        review_reason=ReviewReason.OCR_OR_EXTRACTION_ERROR,
        review_priority=ReviewPriority.MEDIUM,
        risk_category=ReviewRiskCategory.MEDIUM,
    )
    with queue._connect() as conn:
        conn.execute(
            "UPDATE review_items SET review_status = 'APPROVED', reviewer_id = 'DR-VERIFIED', review_notes = 'Verified' WHERE review_item_id = ?",
            (unit_id,)
        )

    result = validator.validate(unit_id)
    assert result.eligible_for_production is True
    assert len(result.errors) == 0
    assert len(result.validation_checks) == 11
    assert all(c["passed"] for c in result.validation_checks)
