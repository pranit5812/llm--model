"""Provenance helper module for tracking source citations during extraction."""

from typing import List, Optional
from src.models.stw_schema import ReviewStatus, SourceReference


def create_source_reference(
    document_id: str,
    page_number: int,
    section: str,
    source_text: str,
    document_name: Optional[str] = None,
    bounding_box: Optional[List[float]] = None,
    extraction_type: str = "text",
    review_status: ReviewStatus = ReviewStatus.EXTRACTED,
    requires_manual_review: bool = False,
    review_notes: Optional[str] = None,
    normalized_term: Optional[str] = None,
) -> SourceReference:
    """Build a validated SourceReference instance with required traceability fields."""
    clean_doc_id = document_id.strip() if document_id else "UNKNOWN"
    clean_section = section.strip() if section else "GENERAL"
    clean_text = source_text.strip() if source_text else "[Source text not extracted]"
    
    # Ensure minimum non-empty constraints
    if not clean_text:
        clean_text = "[Empty text]"

    return SourceReference(
        document_id=clean_doc_id,
        document_name=document_name,
        page_number=max(1, page_number),
        section=clean_section,
        source_text_reference=clean_text,
        bounding_box=bounding_box,
        extraction_type=extraction_type,
        review_status=review_status,
        requires_manual_review=requires_manual_review,
        review_notes=review_notes,
        normalized_term=normalized_term,
    )
