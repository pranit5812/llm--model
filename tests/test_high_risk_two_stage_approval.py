"""Phase 9 Test: High-Risk Two-Stage Clinical Approval.

Safety Invariants Verified:
1. High-risk or two-stage approval units require two distinct clinical reviewers.
2. The same reviewer cannot sign off on both stages.
3. Mandatory clinical justification notes are required for high-risk approvals.
4. Promotion is blocked until both approval stages are completed.
"""

import pytest
from src.review.queue import ReviewQueue
from src.review.approval import ApprovalEngine
from src.review.promotion import PromotionManager
from src.review.schemas import (
    ReviewPriority,
    ReviewReason,
    ReviewStatus,
    ReviewRiskCategory,
    ReviewApprovalRequest,
)


@pytest.fixture
def clean_queue(tmp_path):
    db_path = tmp_path / "test_two_stage.db"
    return ReviewQueue(db_path=db_path)


def test_high_risk_requires_mandatory_notes(clean_queue):
    queue = clean_queue
    engine = ApprovalEngine(queue=queue)

    unit_id = "UNIT-HIGH-RISK-001"
    queue.upsert_review_item(
        unit_id=unit_id,
        document_id="ICMR-CARD-001",
        condition="STEMI",
        section="Thrombolysis",
        page_number=3,
        entity_type="drug_recommendation",
        content="Tenecteplase weight-adjusted bolus 30-50 mg over 10 seconds.",
        original_source_text="Tenecteplase weight-adjusted bolus 30-50 mg over 10 seconds.",
        review_reason=ReviewReason.FLOWCHART_AMBIGUITY,
        review_priority=ReviewPriority.HIGH,
        risk_category=ReviewRiskCategory.HIGH,
        requires_two_stage_approval=True,
    )

    # Missing notes on high-risk approval must raise ValueError
    with pytest.raises(ValueError, match="Mandatory review notes.*HIGH risk"):
        engine.approve_item(
            unit_id,
            ReviewApprovalRequest(reviewer_id="DR-SENIOR-1", notes=""),
            auto_promote=False
        )


def test_two_stage_approval_requires_two_distinct_clinicians(clean_queue):
    queue = clean_queue
    engine = ApprovalEngine(queue=queue)
    prom_manager = PromotionManager(queue=queue)

    unit_id = "UNIT-HIGH-RISK-002"
    queue.upsert_review_item(
        unit_id=unit_id,
        document_id="ICMR-CARD-001",
        condition="STEMI",
        section="Emergency Management",
        page_number=2,
        entity_type="drug_recommendation",
        content="Streptokinase 1.5 million units IV infusion over 60 minutes.",
        original_source_text="Streptokinase 1.5 million units IV infusion over 60 minutes.",
        review_reason=ReviewReason.FLOWCHART_AMBIGUITY,
        review_priority=ReviewPriority.HIGH,
        risk_category=ReviewRiskCategory.HIGH,
        requires_two_stage_approval=True,
    )

    # 1. Stage 1 Approval by Clinician 1
    req1 = ReviewApprovalRequest(
        reviewer_id="DR-CARDIO-ALPHA",
        reviewer_name="Dr. Alpha (Cardiologist)",
        notes="Dosage and infusion rate verified against ICMR Table 1."
    )
    res_stage1 = engine.approve_item(unit_id, req1, auto_promote=False)
    
    # Status remains IN_REVIEW awaiting Stage 2
    assert res_stage1.review_status == ReviewStatus.IN_REVIEW
    assert res_stage1.reviewer_id == "DR-CARDIO-ALPHA"
    assert res_stage1.second_reviewer_id is None

    # Promotion attempt at this point MUST fail
    prom_res1 = prom_manager.promote_item(unit_id, promoter_id="ADMIN-1")
    assert prom_res1.eligible_for_production is False
    assert any("IN_REVIEW" in err or "two distinct clinical approvals" in err or "Stage 2" in err or "not APPROVED" in err for err in prom_res1.errors)

    # 2. Stage 2 Approval attempt by the SAME Clinician 1 MUST be rejected
    req2_duplicate = ReviewApprovalRequest(
        reviewer_id="DR-CARDIO-ALPHA",
        reviewer_name="Dr. Alpha (Cardiologist)",
        notes="Trying to approve stage 2 as well."
    )
    with pytest.raises(ValueError, match="Two distinct reviewers required"):
        engine.approve_item(unit_id, req2_duplicate, auto_promote=False)

    # 3. Stage 2 Approval by distinct Clinician 2 succeeds
    req2_valid = ReviewApprovalRequest(
        reviewer_id="DR-CARDIO-BETA",
        reviewer_name="Dr. Beta (Senior Consultant)",
        notes="Secondary clinical validation confirmed. No contraindications omitted."
    )
    res_stage2 = engine.approve_item(unit_id, req2_valid, auto_promote=False)

    # Status now transitions to APPROVED / ELIGIBLE_FOR_PRODUCTION
    assert res_stage2.review_status in (ReviewStatus.APPROVED, ReviewStatus.ELIGIBLE_FOR_PRODUCTION)
    assert res_stage2.reviewer_id == "DR-CARDIO-ALPHA"
    assert res_stage2.second_reviewer_id == "DR-CARDIO-BETA"

    # Now promotion validation passes
    prom_res2 = prom_manager.promote_item(unit_id, promoter_id="ADMIN-1")
    assert prom_res2.eligible_for_production is True
    promoted_item = queue.get_item(unit_id)
    assert promoted_item.review_status == ReviewStatus.PROMOTED
