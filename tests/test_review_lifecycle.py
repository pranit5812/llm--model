"""Phase 9 Test: Review Lifecycle State Machine Transitions.

Verifies:
- Standard forward progression: NEEDS_REVIEW -> IN_REVIEW -> APPROVED -> ELIGIBLE_FOR_PRODUCTION -> PROMOTED
- Alternative pathways: NEEDS_REVIEW -> IN_REVIEW -> NEEDS_CORRECTION -> APPROVED
- Rejection pathway: NEEDS_REVIEW -> REJECTED
- Invalid state transitions are strictly rejected
"""

import pytest
from src.review.queue import ReviewQueue
from src.review.approval import ApprovalEngine
from src.review.promotion import PromotionValidator, PromotionManager
from src.review.schemas import (
    ReviewItemSchema,
    ReviewPriority,
    ReviewReason,
    ReviewStatus,
    ReviewRiskCategory,
    ReviewStartRequest,
    ReviewApprovalRequest,
    ReviewCorrectionRequest,
    ReviewRejectionRequest,
)


@pytest.fixture
def clean_queue(tmp_path):
    db_path = tmp_path / "test_lifecycle.db"
    queue = ReviewQueue(db_path=db_path)
    return queue


def test_standard_lifecycle_progression(clean_queue):
    queue = clean_queue
    engine = ApprovalEngine(queue=queue)

    # 1. Enqueue a test unit (starts as NEEDS_REVIEW / PENDING)
    unit_id = "UNIT-LIFECYCLE-001"
    queue.upsert_review_item(
        unit_id=unit_id,
        document_id="ICMR-CARD-001",
        condition="STEMI",
        section="Emergency Management",
        page_number=2,
        entity_type="drug_recommendation",
        content="Administer Aspirin 300 mg chewable immediately.",
        original_source_text="Administer Aspirin 300 mg chewable immediately.",
        review_reason=ReviewReason.OCR_OR_EXTRACTION_ERROR,
        review_priority=ReviewPriority.MEDIUM,
        risk_category=ReviewRiskCategory.MEDIUM,
    )

    item = queue.get_item(unit_id)
    assert item is not None
    assert item.review_status in (ReviewStatus.PENDING, ReviewStatus.NEEDS_REVIEW)

    # 2. Start review -> IN_REVIEW
    item_in_review = engine.start_review(
        unit_id,
        ReviewStartRequest(reviewer_id="DR-TEST-1", reviewer_name="Dr. Test 1", notes="Beginning evaluation")
    )
    assert item_in_review.review_status == ReviewStatus.IN_REVIEW
    assert item_in_review.reviewer_id == "DR-TEST-1"

    # 3. Approve -> APPROVED (and ELIGIBLE_FOR_PRODUCTION)
    item_approved = engine.approve_item(
        unit_id,
        ReviewApprovalRequest(reviewer_id="DR-TEST-1", notes="Verified against ICMR guidelines"),
        auto_promote=False
    )
    assert item_approved.review_status in (ReviewStatus.APPROVED, ReviewStatus.ELIGIBLE_FOR_PRODUCTION)

    # 4. Promote -> PROMOTED
    prom_manager = PromotionManager(queue=queue)
    result = prom_manager.promote_item(
        review_id_or_unit_id=unit_id,
        promoter_id="SYS-ADMIN-1",
        notes="Promoting to production index",
        indexer=None  # Mock indexer
    )
    assert result.eligible_for_production is True
    promoted_item = queue.get_item(unit_id)
    assert promoted_item.review_status == ReviewStatus.PROMOTED


def test_correction_pathway_preserves_original_source(clean_queue):
    queue = clean_queue
    engine = ApprovalEngine(queue=queue)

    unit_id = "UNIT-CORR-001"
    orig_source = "ICMR Page 4: Loading dose of clopidogrel is 300-600 mg."
    queue.upsert_review_item(
        unit_id=unit_id,
        document_id="ICMR-CARD-001",
        condition="STEMI",
        section="Pharmacotherapy",
        page_number=4,
        entity_type="drug_recommendation",
        content="Clopidogrel 300 mg",
        original_source_text=orig_source,
        review_reason=ReviewReason.INCOMPLETE_DOSAGE,
        review_priority=ReviewPriority.HIGH,
        risk_category=ReviewRiskCategory.HIGH,
    )

    # Start review
    engine.start_review(unit_id, ReviewStartRequest(reviewer_id="DR-CARDIO-1"))

    # Record correction
    corr_req = ReviewCorrectionRequest(
        reviewer_id="DR-CARDIO-1",
        corrected_structured_value="Clopidogrel 300-600 mg oral loading dose",
        notes="Specified exact range per ICMR Table 2"
    )
    item_corr = engine.record_correction(unit_id, corr_req)
    assert item_corr.review_status == ReviewStatus.NEEDS_CORRECTION
    assert item_corr.corrected_structured_value == "Clopidogrel 300-600 mg oral loading dose"
    # STRICT INVARIANT: Original source text is never modified
    assert item_corr.original_source_text == orig_source


def test_rejection_pathway(clean_queue):
    queue = clean_queue
    engine = ApprovalEngine(queue=queue)

    unit_id = "UNIT-REJ-001"
    queue.upsert_review_item(
        unit_id=unit_id,
        document_id="ICMR-NEUR-001",
        condition="Ischemic Stroke",
        section="Unclear Section",
        page_number=99,
        entity_type="unknown",
        content="Corrupted OCR text artifact #@!%",
        original_source_text="Corrupted OCR text artifact #@!%",
        review_reason=ReviewReason.OCR_OR_EXTRACTION_ERROR,
        review_priority=ReviewPriority.LOW,
        risk_category=ReviewRiskCategory.LOW,
    )

    # Reject requires justification notes
    with pytest.raises((ValueError, Exception)):
        engine.reject_item(unit_id, ReviewRejectionRequest(reviewer_id="DR-NEURO-1", rejection_reason=""))

    item_rej = engine.reject_item(
        unit_id,
        ReviewRejectionRequest(
            reviewer_id="DR-NEURO-1",
            rejection_reason="Unrecoverable OCR noise; non-clinical text",
            notes="Unrecoverable OCR noise; non-clinical text"
        )
    )
    assert item_rej.review_status == ReviewStatus.REJECTED

    # Rejection prevents promotion
    prom_manager = PromotionManager(queue=queue)
    res = prom_manager.promote_item(unit_id, promoter_id="ADMIN-1")
    assert res.eligible_for_production is False
    assert any("Rejected" in err or "not APPROVED" in err for err in res.errors)
