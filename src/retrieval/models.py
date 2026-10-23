"""Retrieval result models for the ICMR STW knowledge base.

RetrievalResult is the public-facing output of any retrieval operation.
All fields are explicitly defined — no internal paths or credentials leak.

The sentinel NO_RELIABLE_ICMR_EVIDENCE is returned when no result exceeds
the minimum confidence threshold, preventing forced retrieval of unrelated
evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Sentinel for negative / abstention queries
# ---------------------------------------------------------------------------

NO_RELIABLE_ICMR_EVIDENCE = "NO_RELIABLE_ICMR_EVIDENCE"
"""Returned when no knowledge unit exceeds the minimum retrieval threshold."""

# Minimum BM25 / cosine / RRF score to consider a result relevant
# (avoids forced retrieval when no evidence exists)
MIN_SCORE_THRESHOLD = 0.01


# ---------------------------------------------------------------------------
# RetrievalResult
# ---------------------------------------------------------------------------

@dataclass
class RetrievalResult:
    """A single retrieved evidence unit with provenance.

    Every field is deliberately named to avoid exposing internal
    implementation details (no file paths, no DB row IDs, no API keys).
    """

    unit_id: str
    """Unique unit identifier (document_id:entity_type:index)."""

    content: str
    """Human-readable text content of the retrieved knowledge unit."""

    score: float
    """Retrieval relevance score (higher = more relevant, range depends on method)."""

    document_id: str
    """ICMR STW document identifier, e.g. 'ICMR-CARD-006'."""

    condition: str
    """Clinical condition, e.g. 'STEMI'."""

    specialty: str
    """Medical specialty, e.g. 'Cardiology'."""

    page_number: int
    """1-indexed page in the source ICMR PDF."""

    section: str
    """Section heading in the source document."""

    entity_type: str
    """Type of knowledge unit: medication | investigation | contraindication | ..."""

    review_status: str
    """extracted | manually_verified (needs_review units never in production results)."""

    version_id: str = "v1.0"
    """Semantic version of the source STW document."""

    source_reference: Dict[str, Any] = field(default_factory=dict)
    """Full ICMR provenance citation — organisation, document, page, section, text."""

    rank: int = 0
    """Position in the ranked result list (1-indexed)."""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def citation(self) -> Dict[str, str]:
        """Structured citation for display."""
        sr = self.source_reference
        return {
            "organization": "Indian Council of Medical Research (ICMR)",
            "document_id": self.document_id,
            "condition": self.condition,
            "specialty": self.specialty,
            "version_id": self.version_id,
            "page_number": str(self.page_number),
            "section": self.section,
            "source_text_reference": sr.get("source_text_reference", ""),
        }


# ---------------------------------------------------------------------------
# Query model
# ---------------------------------------------------------------------------

@dataclass
class RetrievalQuery:
    """A retrieval query with optional metadata filters."""
    query: str
    top_k: int = 10
    # Pre-filters (all optional — None = no filter)
    specialty: Optional[str] = None
    condition: Optional[str] = None
    document_id: Optional[str] = None
    version_id: Optional[str] = None
    section: Optional[str] = None
    healthcare_tier: Optional[str] = None
    entity_type: Optional[str] = None

