"""Metadata filtering utilities for ICMR STW knowledge units.

All filters are applied as pre-conditions before retrieval scoring,
ensuring queries for one condition (e.g. STEMI) cannot be dominated by
unrelated evidence (e.g. Heart Failure).
"""

from __future__ import annotations

from typing import List, Optional

from .units import KnowledgeUnit


class MetadataFilter:
    """Chainable filter builder for KnowledgeUnit lists."""

    def __init__(self, units: List[KnowledgeUnit]) -> None:
        self._units = list(units)

    # ------------------------------------------------------------------
    # Filter methods (each returns a new MetadataFilter for chaining)
    # ------------------------------------------------------------------

    def by_specialty(self, specialty: Optional[str]) -> "MetadataFilter":
        if not specialty:
            return self
        s = specialty.strip().lower()
        return MetadataFilter([u for u in self._units if u.specialty.lower() == s])

    def by_condition(self, condition: Optional[str]) -> "MetadataFilter":
        if not condition:
            return self
        c = condition.strip().lower()
        return MetadataFilter([u for u in self._units if u.condition.lower() == c])

    def by_document_id(self, document_id: Optional[str]) -> "MetadataFilter":
        if not document_id:
            return self
        return MetadataFilter([u for u in self._units if u.document_id == document_id])

    def by_version_id(self, version_id: Optional[str]) -> "MetadataFilter":
        if not version_id:
            return self
        v = version_id.strip().lower()
        return MetadataFilter([u for u in self._units if getattr(u, "version_id", "v1.0").lower() == v])


    def by_section(self, section: Optional[str]) -> "MetadataFilter":
        if not section:
            return self
        s = section.strip().lower()
        return MetadataFilter([u for u in self._units if s in u.section.lower()])

    def by_healthcare_tier(self, tier: Optional[str]) -> "MetadataFilter":
        if not tier:
            return self
        t = tier.strip().lower()
        return MetadataFilter([
            u for u in self._units
            if u.healthcare_tier and u.healthcare_tier.lower() == t
        ])

    def by_entity_type(self, entity_type: Optional[str]) -> "MetadataFilter":
        if not entity_type:
            return self
        return MetadataFilter([u for u in self._units if u.entity_type == entity_type])

    def by_review_status(self, status: Optional[str]) -> "MetadataFilter":
        """Filter by review_status string (extracted | needs_review | manually_verified)."""
        if not status:
            return self
        return MetadataFilter([u for u in self._units if u.review_status == status])

    def exclude_needs_review(self) -> "MetadataFilter":
        """Exclude all units flagged as requiring manual review (production safety gate)."""
        return MetadataFilter([u for u in self._units if not u.requires_manual_review])

    def only_needs_review(self) -> "MetadataFilter":
        """Return only units that need review (for the review queue)."""
        return MetadataFilter([u for u in self._units if u.requires_manual_review])

    # ------------------------------------------------------------------
    # Terminal
    # ------------------------------------------------------------------

    def result(self) -> List[KnowledgeUnit]:
        """Return the filtered list of KnowledgeUnit objects."""
        return self._units

    def __len__(self) -> int:
        return len(self._units)

    def __iter__(self):
        return iter(self._units)
