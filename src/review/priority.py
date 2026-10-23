"""Automated Review Priority Engine for ICMR STW Knowledge Units.

Classifies review items into HIGH, MEDIUM, or LOW priority based strictly on clinical
structure and safety-criticality.
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional


class ReviewPriority(str, Enum):
    """Clinical review priority classification."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ReviewPriorityClassifier:
    """Classifies clinical knowledge units into review priorities."""

    @staticmethod
    def classify(
        entity_type: str,
        section: str = "",
        content: str = "",
        notes: Optional[str] = None,
    ) -> ReviewPriority:
        """Determine review priority based on clinical entity type and context.

        HIGH:
          - medication dose
          - contraindication
          - emergency workflow
          - referral criteria
          - critical decision branch / flowchart pathway

        MEDIUM:
          - investigation / diagnostics
          - diagnostic criteria
          - healthcare tier actions (PHC / CHC / District)

        LOW:
          - terminology / formatting
          - metadata / references
          - general documentation
        """
        et = (entity_type or "").lower().strip()
        sec = (section or "").lower()
        cnt = (content or "").lower()
        nts = (notes or "").lower()

        # HIGH Priority Checks
        if et in ["medication", "contraindication", "referral_criterion"]:
            return ReviewPriority.HIGH

        if any(w in sec for w in ["emergency", "contraindication", "referral", "thrombolysis", "pci", "resuscitation"]):
            return ReviewPriority.HIGH

        if any(w in nts for w in ["dose", "contraindication", "emergency", "drug interaction", "referral"]):
            return ReviewPriority.HIGH

        if et == "flowchart_node" and any(w in cnt for w in ["refer", "transfer", "emergency", "immediate", "shock", "arrest"]):
            return ReviewPriority.HIGH

        # MEDIUM Priority Checks
        if et in ["investigation", "diagnostic_criterion", "tier_action", "flowchart_node", "table_row"]:
            return ReviewPriority.MEDIUM

        if any(w in sec for w in ["investigation", "diagnostic", "criteria", "tier", "phc", "chc", "district hospital"]):
            return ReviewPriority.MEDIUM

        # LOW Priority (Default for metadata, references, formatting, terminology)
        return ReviewPriority.LOW
