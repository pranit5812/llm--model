"""Pydantic schemas and Enums for the Clinical Knowledge Review Workflow."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, model_validator


class ReviewStatus(str, Enum):
    """Status of a knowledge unit in the human clinical review workflow."""
    EXTRACTED = "EXTRACTED"
    PENDING = "PENDING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    IN_REVIEW = "IN_REVIEW"
    NEEDS_CORRECTION = "NEEDS_CORRECTION"
    APPROVED = "APPROVED"
    ELIGIBLE_FOR_PRODUCTION = "ELIGIBLE_FOR_PRODUCTION"
    PRODUCTION_INDEX = "PRODUCTION_INDEX"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


class ReviewReason(str, Enum):
    """Clinical reason why a knowledge unit was flagged for manual review."""
    FLOWCHART_AMBIGUITY = "FLOWCHART_AMBIGUITY"
    TABLE_EXTRACTION = "TABLE_EXTRACTION"
    INCOMPLETE_DOSAGE = "INCOMPLETE_DOSAGE"
    TERMINOLOGY = "TERMINOLOGY"
    OCR_OR_EXTRACTION_ERROR = "OCR_OR_EXTRACTION_ERROR"
    SOURCE_AMBIGUITY = "SOURCE_AMBIGUITY"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    UNSAFE_INTERPRETATION = "UNSAFE_INTERPRETATION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    DUPLICATE = "DUPLICATE"
    OBSOLETE_VERSION = "OBSOLETE_VERSION"
    OTHER = "OTHER"


class ReviewPriority(str, Enum):
    """Clinical priority weighting for the human review backlog."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ReviewRiskCategory(str, Enum):
    """Clinical safety risk level."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    STANDARD = "STANDARD"


class ReviewItemSchema(BaseModel):
    """Detailed representation of a review-flagged knowledge unit."""
    review_item_id: str = Field(..., description="Unique review record ID")
    knowledge_unit_id: str = Field(..., description="Target knowledge unit ID")
    document_id: str = Field(..., description="Source STW ID, e.g. ICMR-CARD-006")
    version_id: str = Field(default="v1.0", description="STW edition version ID")
    specialty: str = Field(default="Cardiology", description="Clinical specialty (Cardiology, Neurology, etc.)")
    condition: str = Field(..., description="Clinical condition title")
    page_number: int = Field(..., description="Source PDF page number")
    section: str = Field(..., description="Source workflow section")
    entity_type: str = Field(..., description="Clinical entity type (table, flowchart, medication, etc.)")
    content: str = Field(..., description="Extracted structured content")
    original_source_text: str = Field(..., description="Immutable raw text from the ICMR PDF")
    normalized_value: Optional[str] = Field(default=None, description="Normalized canonical medical representation")
    corrected_structured_value: Optional[str] = Field(default=None, description="Human-corrected structured value if amended")
    correction_text: Optional[str] = Field(default=None, description="Correction text alias")
    review_reason: ReviewReason = Field(default=ReviewReason.OTHER, description="Categorized clinical review trigger")
    rejection_reason: Optional[str] = Field(default=None, description="Reason for rejection if rejected")
    review_priority: ReviewPriority = Field(default=ReviewPriority.MEDIUM, description="Clinical risk priority")
    risk_category: str = Field(default="STANDARD", description="Risk level (HIGH, MEDIUM, LOW, STANDARD)")
    review_status: ReviewStatus = Field(default=ReviewStatus.PENDING, description="Current workflow state")
    created_at: str = Field(..., description="Creation timestamp UTC")
    updated_at: Optional[str] = Field(default=None, description="Last update timestamp UTC")
    review_notes: Optional[str] = Field(default=None, description="Clinical reviewer observations or rationale")
    reviewer_id: Optional[str] = Field(default=None, description="Identifier of primary human clinical reviewer")
    reviewer_name: Optional[str] = Field(default=None, description="Name of primary human clinical reviewer")
    reviewed_at: Optional[str] = Field(default=None, description="Timestamp when primary review occurred")
    approval_timestamp: Optional[str] = Field(default=None, description="Timestamp when final approval was granted")
    second_reviewer_id: Optional[str] = Field(default=None, description="Identifier of secondary reviewer for two-stage approval")
    second_reviewer_name: Optional[str] = Field(default=None, description="Name of secondary reviewer")
    second_reviewed_at: Optional[str] = Field(default=None, description="Timestamp when secondary review occurred")
    second_reviewer_notes: Optional[str] = Field(default=None, description="Secondary reviewer notes")
    requires_two_stage_approval: bool = Field(default=False, description="Whether two distinct clinicians must approve")
    flowchart_context: Optional[Dict[str, Any]] = Field(default=None, description="Node and edge context for flowchart review")
    table_context: Optional[Dict[str, Any]] = Field(default=None, description="Row/col context for table review")
    source_reference: Dict[str, Any] = Field(default_factory=dict, description="Provenance metadata")

    # Convenient aliases
    @property
    def review_id(self) -> str:
        return self.review_item_id

    @property
    def source_page(self) -> int:
        return self.page_number

    @property
    def source_section(self) -> str:
        return self.section

    @property
    def source_text(self) -> str:
        return self.original_source_text

    @property
    def extracted_value(self) -> str:
        return self.content

    @property
    def priority(self) -> ReviewPriority:
        return self.review_priority

    @property
    def status(self) -> ReviewStatus:
        return self.review_status

    @property
    def unit_type(self) -> str:
        return self.entity_type

    @property
    def reviewer_notes_alias(self) -> Optional[str]:
        return self.review_notes


class ReviewStartRequest(BaseModel):
    """Payload to transition item from NEEDS_REVIEW to IN_REVIEW."""
    reviewer_id: str = Field(..., min_length=2, description="Authorized clinician identifier")
    reviewer_name: Optional[str] = Field(default=None, description="Full clinician name")


class ReviewApprovalRequest(BaseModel):
    """Human reviewer approval payload."""
    reviewer_id: str = Field(..., min_length=2, description="Authorized human reviewer identifier")
    reviewer_name: Optional[str] = Field(default=None, description="Reviewer full name")
    review_notes: Optional[str] = Field(default=None, description="Clinical review commentary (mandatory for HIGH risk)")
    notes: Optional[str] = Field(default=None, description="Alias for review_notes")
    confirmation: bool = Field(default=True, description="Explicit confirmation of clinical verification")

    @model_validator(mode="after")
    def populate_notes(self) -> ReviewApprovalRequest:
        if not self.review_notes and self.notes:
            self.review_notes = self.notes
        return self


# Backward-compatible alias
ReviewActionRequest = ReviewApprovalRequest


class ReviewCorrectionRequest(BaseModel):
    """Human correction payload for an extracted unit."""
    reviewer_id: str = Field(..., min_length=2, description="Authorized human reviewer identifier")
    reviewer_name: Optional[str] = Field(default=None, description="Reviewer full name")
    corrected_structured_value: Optional[str] = Field(default=None, description="Accurate clinical structured text")
    corrected_value: Optional[str] = Field(default=None, description="Alias for corrected_structured_value")
    correction_note: Optional[str] = Field(default=None, description="Justification for correction against original PDF")
    correction_reason: Optional[str] = Field(default="CLINICAL_CORRECTION", description="Reason for correction")
    notes: Optional[str] = Field(default=None, description="Alias for correction_note")

    @model_validator(mode="after")
    def populate_fields(self) -> ReviewCorrectionRequest:
        if not self.corrected_structured_value and self.corrected_value:
            self.corrected_structured_value = self.corrected_value
        if not self.corrected_value and self.corrected_structured_value:
            self.corrected_value = self.corrected_structured_value
        if not self.correction_note and self.notes:
            self.correction_note = self.notes
        if not self.notes and self.correction_note:
            self.notes = self.correction_note
        if not self.corrected_structured_value or len(self.corrected_structured_value.strip()) < 3:
            raise ValueError("Corrected structured value must be provided with minimum length 3.")
        return self


class ReviewRejectionRequest(BaseModel):
    """Human rejection payload for an extracted unit."""
    reviewer_id: str = Field(..., min_length=2, description="Authorized human reviewer identifier")
    reviewer_name: Optional[str] = Field(default=None, description="Reviewer full name")
    rejection_reason: str = Field(..., min_length=3, description="Standardized clinical rejection reason")
    review_notes: Optional[str] = Field(default=None, description="Clinical justification for rejecting item")
    notes: Optional[str] = Field(default=None, description="Alias for review_notes")

    @model_validator(mode="after")
    def populate_notes(self) -> ReviewRejectionRequest:
        if not self.review_notes and self.notes:
            self.review_notes = self.notes
        if not self.notes and self.review_notes:
            self.notes = self.review_notes
        if not self.review_notes or len(self.review_notes.strip()) < 3:
            raise ValueError("Clinical justification notes are strictly required when rejecting an item.")
        return self


class PromotionRequest(BaseModel):
    """Request payload to promote an approved item to production index."""
    promoter_id: str = Field(..., min_length=2, description="Authorized clinical administrator identifier")
    promoter_name: Optional[str] = Field(default=None, description="Administrator full name")
    notes: Optional[str] = Field(default=None, description="Optional promotion sign-off note")


class PromotionValidationResult(BaseModel):
    """Result of pre-promotion safety and schema checks."""
    is_valid: bool = Field(..., description="Whether all checks passed and unit is eligible for production")
    eligible_for_production: bool = Field(default=False, description="Whether unit is eligible for production")
    indexed_successfully: bool = Field(default=False, description="Whether incrementally indexed")
    indexing_latency_ms: float = Field(default=0.0, description="Incremental indexing latency in ms")
    validation_checks: List[Dict[str, Any]] = Field(default_factory=list, description="Individual checks")
    errors: List[str] = Field(default_factory=list, description="Blocking validation errors")
    warnings: List[str] = Field(default_factory=list, description="Non-blocking clinical warnings")
    unit_id: str
    document_id: str
    version_id: str
    promoted_at: Optional[str] = None


class ReviewQueueSummary(BaseModel):
    """Summary statistics for the clinical review backlog."""
    total_items: int
    pending: int
    in_review: int = 0
    approved: int
    eligible_for_production: int = 0
    promoted: int = 0
    rejected: int
    needs_correction: int
    high_priority_pending: int
    medium_priority_pending: int
    low_priority_pending: int
    by_document: Dict[str, int]
    by_reason: Dict[str, int]
    by_specialty: Dict[str, int] = Field(default_factory=dict)
    by_risk: Dict[str, int] = Field(default_factory=dict)
    by_priority: Dict[str, int] = Field(default_factory=dict)


