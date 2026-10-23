"""Pydantic schemas for the ICMR STW Grounded LLM/SLM RAG system."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

DEFAULT_CLINICAL_DISCLAIMER = (
    "NOTICE: This information is derived strictly from official Indian Council of Medical "
    "Research (ICMR) Standard Treatment Workflows (STWs) for clinical decision support. "
    "It is not a substitute for qualified professional medical evaluation, diagnosis, or prescription."
)


class RAGResponseStatus(str, Enum):
    """Grounded RAG generation status."""
    GROUNDED = "GROUNDED"
    PARTIALLY_GROUNDED = "PARTIALLY_GROUNDED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"  # preserved for backward compatibility
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    NO_RELIABLE_ICMR_EVIDENCE = "NO_RELIABLE_ICMR_EVIDENCE"
    INSUFFICIENT_APPROVED_EVIDENCE = "INSUFFICIENT_APPROVED_EVIDENCE"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    AMBIGUOUS_SOURCE = "AMBIGUOUS_SOURCE"



class CitationItem(BaseModel):
    """Verified clinical evidence citation directly tied to an ICMR STW unit."""
    document_id: str = Field(..., description="ICMR STW ID, e.g. ICMR-CARD-006")
    condition: str = Field(..., description="Clinical condition title")
    page_number: int = Field(..., description="Source page in official ICMR PDF")
    section: str = Field(..., description="Section title in source STW")
    knowledge_unit_id: str = Field(..., description="Unique ID of the underlying knowledge unit")
    source_text_reference: str = Field(..., description="Direct quote or snippet from the ICMR workflow")


class RAGResponse(BaseModel):
    """Structured response output for the ICMR STW RAG pipeline."""
    status: RAGResponseStatus = Field(..., description="Evidence grounding status")
    answer: str = Field(..., description="Grounded response text based strictly on retrieved evidence")
    key_points: List[str] = Field(default_factory=list, description="Extracted actionable clinical points")
    cautions: List[str] = Field(default_factory=list, description="Clinical contraindications, alerts, or limitations")
    citations: List[CitationItem] = Field(default_factory=list, description="Verified ICMR citations")
    evidence_ids: List[str] = Field(default_factory=list, description="List of knowledge unit IDs used")
    confidence: str = Field(default="HIGH", description="Confidence level: HIGH | MEDIUM | LOW | NONE")
    abstained: bool = Field(default=False, description="True if system safely refrained from answering")
    version_warning: Optional[str] = Field(default=None, description="Warning if multiple conflicting STW versions exist")
    clinical_disclaimer: str = Field(default=DEFAULT_CLINICAL_DISCLAIMER, description="Standard ICMR decision-support disclaimer")
    debug_info: Optional[Dict[str, Any]] = Field(default=None, description="Optional development debug data (no credentials)")
