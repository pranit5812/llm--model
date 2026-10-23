"""Unified Clinical Review Service for Phase 9 human review workflow."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .approval import ReviewAuditManager
from .promotion import PromotionManager
from .queue import ReviewQueue
from .schemas import (
    PromotionValidationResult,
    ReviewApprovalRequest,
    ReviewCorrectionRequest,
    ReviewItemSchema,
    ReviewPriority,
    ReviewQueueSummary,
    ReviewReason,
    ReviewRejectionRequest,
    ReviewStartRequest,
    ReviewStatus,
)


class ReviewService:
    """Provides high-level methods for clinical review queue query and mutation operations."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.queue = ReviewQueue(db_path=db_path)
        self.audit = ReviewAuditManager(db_path=db_path)
        self.promotion = PromotionManager(db_path=db_path)

    def get_summary(self) -> ReviewQueueSummary:
        return self.queue.get_summary()

    def list_items(
        self,
        status: Optional[Union[ReviewStatus, str]] = None,
        priority: Optional[Union[ReviewPriority, str]] = None,
        risk_category: Optional[str] = None,
        reason: Optional[Union[ReviewReason, str]] = None,
        specialty: Optional[str] = None,
        condition: Optional[str] = None,
        document_id: Optional[str] = None,
        version_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        reviewer_id: Optional[str] = None,
        search: Optional[str] = None,
        sort_by: str = "priority",
        sort_order: str = "asc",
        limit: int = 50,
        offset: int = 0,
    ) -> List[ReviewItemSchema]:
        return self.queue.get_review_items(
            status=status,
            priority=priority,
            risk_category=risk_category,
            reason=reason,
            specialty=specialty,
            condition=condition,
            document_id=document_id,
            version_id=version_id,
            entity_type=entity_type,
            reviewer_id=reviewer_id,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        )

    def get_item(self, item_id: str) -> Optional[ReviewItemSchema]:
        return self.queue.get_item_by_id(item_id)

    def start_review(self, item_id: str, request: ReviewStartRequest) -> ReviewItemSchema:
        return self.audit.start_review(
            item_id=item_id,
            reviewer_id=request.reviewer_id,
            reviewer_name=request.reviewer_name,
        )

    def approve_item(
        self,
        item_id: str,
        request: ReviewApprovalRequest,
        auto_promote: bool = False,
    ) -> ReviewItemSchema:
        return self.audit.approve_item(
            item_id=item_id,
            reviewer_id=request.reviewer_id,
            reviewer_name=request.reviewer_name,
            notes=request.notes or request.review_notes,
            confirmation=request.confirmation,
            auto_promote=auto_promote,
        )

    def reject_item(
        self,
        item_id: str,
        request: Union[ReviewRejectionRequest, Any],
    ) -> ReviewItemSchema:
        notes = getattr(request, "notes", None) or getattr(request, "review_notes", None)
        rejection_reason = getattr(request, "rejection_reason", "CLINICAL_REJECTION")
        reviewer_name = getattr(request, "reviewer_name", None)
        return self.audit.reject_item(
            item_id=item_id,
            reviewer_id=request.reviewer_id,
            notes=notes or "Rejected during clinical review.",
            reviewer_name=reviewer_name,
            rejection_reason=rejection_reason,
        )

    def record_correction(
        self,
        item_id: str,
        request: ReviewCorrectionRequest,
    ) -> ReviewItemSchema:
        return self.audit.record_correction(
            item_id=item_id,
            reviewer_id=request.reviewer_id,
            corrected_value=getattr(request, "corrected_structured_value", None) or getattr(request, "corrected_value", "") or "",
            notes=getattr(request, "notes", None) or getattr(request, "correction_note", None),
            reviewer_name=getattr(request, "reviewer_name", None),
            correction_reason=getattr(request, "correction_reason", None) or "CLINICAL_CORRECTION",
        )

    def promote_item(
        self,
        item_id: str,
        promoter_id: str,
        promoter_name: Optional[str] = None,
        notes: Optional[str] = None,
        indexer: Optional[Any] = None,
    ) -> PromotionValidationResult:
        return self.promotion.promote_item(
            review_id_or_unit_id=item_id,
            promoter_id=promoter_id,
            promoter_name=promoter_name,
            notes=notes,
            indexer=indexer,
        )

    def get_audit_history(self, item_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return self.audit.get_audit_history(item_id=item_id)

