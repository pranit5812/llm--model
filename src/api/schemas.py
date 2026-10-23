"""Pydantic request/response schemas for the ICMR STW Retrieval API.

All schemas are designed to:
- Never expose internal file paths, database credentials, or implementation details.
- Always include ICMR provenance in retrieval responses.
- Validate inputs before retrieval.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class RetrieveRequest(BaseModel):
    """POST /api/v1/retrieve — clinical evidence retrieval query."""

    query: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Clinical query string",
        examples=["aspirin dose for STEMI", "thrombolysis contraindications"],
    )
    top_k: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Maximum number of results to return",
    )
    # Optional metadata filters
    specialty: Optional[str] = Field(default=None, description="Filter by specialty, e.g. 'Cardiology'")
    condition: Optional[str] = Field(default=None, description="Filter by condition, e.g. 'STEMI'")
    document_id: Optional[str] = Field(default=None, description="Filter by document ID, e.g. 'ICMR-CARD-006'")
    version_id: Optional[str] = Field(default=None, description="Filter by version ID, e.g. 'v1.0'")
    section: Optional[str] = Field(default=None, description="Filter by section keyword")
    healthcare_tier: Optional[str] = Field(default=None, description="Filter by tier: PHC_CHC | DISTRICT_HOSPITAL | TERTIARY_PCI")
    entity_type: Optional[str] = Field(default=None, description="Filter by entity type: medication | investigation | ...")


class ChatRequest(BaseModel):
    """POST /api/v1/chat — clinical inquiry for grounded RAG response."""

    model_config = ConfigDict(protected_namespaces=())

    query: str = Field(
        ...,
        min_length=3,
        max_length=1500,
        description="Clinical query or question",
        examples=["What is the recommended loading dose of aspirin in STEMI?"],
    )
    specialty: Optional[str] = Field(default=None, description="Optional target specialty filter")
    condition: Optional[str] = Field(default=None, description="Optional target condition filter")
    version_id: Optional[str] = Field(default=None, description="Optional document version filter")
    top_k: int = Field(
        default=5,
        ge=1,
        le=20,
        description="Maximum number of evidence units to feed to LLM context",
    )

    debug: bool = Field(
        default=False,
        description="Include non-sensitive diagnostic latency and validation metadata",
    )
    # Optional filters
    specialty: Optional[str] = Field(default=None, description="Filter by specialty")
    condition: Optional[str] = Field(default=None, description="Filter by condition")
    document_id: Optional[str] = Field(default=None, description="Filter by document ID")
    section: Optional[str] = Field(default=None, description="Filter by section keyword")
    healthcare_tier: Optional[str] = Field(default=None, description="Filter by healthcare tier")
    entity_type: Optional[str] = Field(default=None, description="Filter by entity type")
    model_mode: Optional[str] = Field(
        default="baseline",
        description="Development model mode: 'baseline' (Phase 6 SLM) or 'fine_tuned' (Phase 7 LoRA)",
    )


# ---------------------------------------------------------------------------
# Citation schema (always included in results)
# ---------------------------------------------------------------------------

class ICMRCitation(BaseModel):
    """Verifiable ICMR source citation returned with every retrieval result."""
    organization: str
    document_id: str
    condition: str
    page_number: str
    section: str
    source_text_reference: str


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class RetrievalResultItem(BaseModel):
    """A single retrieved evidence unit."""
    unit_id: str
    content: str
    score: float
    rank: int
    document_id: str
    condition: str
    specialty: str
    page_number: int
    section: str
    entity_type: str
    review_status: str
    source: ICMRCitation


class RetrieveResponse(BaseModel):
    """Response from POST /api/v1/retrieve."""
    query: str
    total_results: int
    method: str = "hybrid"
    results: List[RetrievalResultItem]
    no_evidence: bool = False
    """True when the system cannot find reliable ICMR evidence for this query."""


class DocumentSummary(BaseModel):
    """Summary of an indexed STW document."""
    document_id: str
    condition: str
    specialty: str
    total_units: int
    needs_review_units: int
    production_units: int


class DocumentDetail(BaseModel):
    """Detailed metadata for a specific indexed STW document."""
    document_id: str
    condition: str
    specialty: str
    total_units: int
    production_units: int
    needs_review_units: int
    entity_type_breakdown: Dict[str, int]


class ReviewItemSchema(BaseModel):
    """A review queue item requiring clinical expert verification."""
    unit_id: str
    document_id: str
    version_id: Optional[str] = "v1.0"
    specialty: Optional[str] = "Cardiology"
    condition: str
    section: str
    page_number: int
    entity_type: str
    content: str
    review_status: str
    review_notes: Optional[str] = None
    review_item_id: Optional[str] = None
    review_reason: Optional[str] = None
    review_priority: Optional[str] = None
    risk_category: Optional[str] = "STANDARD"
    original_source_text: Optional[str] = None
    corrected_structured_value: Optional[str] = None
    correction_text: Optional[str] = None
    rejection_reason: Optional[str] = None
    reviewer_id: Optional[str] = None
    reviewer_name: Optional[str] = None
    reviewed_at: Optional[str] = None
    approval_timestamp: Optional[str] = None
    second_reviewer_id: Optional[str] = None
    second_reviewer_name: Optional[str] = None
    second_reviewed_at: Optional[str] = None
    second_reviewer_notes: Optional[str] = None
    requires_two_stage_approval: Optional[bool] = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    flowchart_context: Optional[Dict[str, Any]] = None
    table_context: Optional[Dict[str, Any]] = None
    source_reference: Optional[Dict[str, Any]] = None


class ReviewQueueResponse(BaseModel):
    """Response from GET /api/v1/review/items."""
    total_items: int
    items: List[ReviewItemSchema]
    by_document: Optional[Any] = None
    by_entity_type: Optional[Any] = None
    by_priority: Optional[Dict[str, int]] = None
    by_reason: Optional[Dict[str, int]] = None
    by_specialty: Optional[Dict[str, int]] = None
    by_risk: Optional[Dict[str, int]] = None


class ReviewStartRequest(BaseModel):
    """Request payload to begin clinical evaluation of an item."""
    reviewer_id: str = Field(..., min_length=2, description="Clinician identifier")
    reviewer_name: Optional[str] = Field(default=None, description="Clinician name")


class PromotionRequest(BaseModel):
    """Request payload to promote an approved item to production index."""
    promoter_id: str = Field(..., min_length=2, description="Authorized administrator or clinical lead ID")
    promoter_name: Optional[str] = Field(default=None, description="Administrator full name")
    notes: Optional[str] = Field(default=None, description="Promotion audit sign-off note")


class PromotionValidationResponse(BaseModel):
    """Result of pre-promotion safety and schema checks."""
    is_valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    unit_id: str
    document_id: str
    version_id: str
    promoted_at: Optional[str] = None


class SpecialtySummary(BaseModel):
    """Summary of a clinical specialty across the STW platform."""
    specialty: str
    total_documents: int
    production_units: int
    review_units: int
    conditions: List[str]


class DocumentExplorerNode(BaseModel):
    """Document tree node for the clinical source explorer."""
    document_id: str
    specialty: str
    condition: str
    title: str
    version_id: str
    total_pages: int
    review_status: str
    sections: List[str]



class ReviewActionRequest(BaseModel):
    """Request payload to approve or reject a flagged unit."""
    reviewer_id: str
    notes: Optional[str] = None


class ReviewApprovalRequest(BaseModel):
    """Request payload to approve a flagged unit."""
    reviewer_id: str
    reviewer_name: Optional[str] = None
    notes: Optional[str] = None
    review_notes: Optional[str] = None
    confirmation: bool = True


class ReviewRejectionRequest(BaseModel):
    """Request payload to reject a flagged unit."""
    reviewer_id: str
    reviewer_name: Optional[str] = None
    rejection_reason: Optional[str] = "CLINICAL_REJECTION"
    notes: Optional[str] = None
    review_notes: Optional[str] = None


class ReviewCorrectionRequest(BaseModel):
    """Request payload to submit a clinical correction for a flagged unit."""
    reviewer_id: str
    reviewer_name: Optional[str] = None
    corrected_structured_value: str
    notes: Optional[str] = None
    correction_note: Optional[str] = None
    correction_reason: Optional[str] = "CLINICAL_CORRECTION"


class HealthResponse(BaseModel):
    """Response from GET /api/v1/health."""
    status: str
    index_loaded: bool
    total_production_units: int
    total_documents: int
