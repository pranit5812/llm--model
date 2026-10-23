"""Evidence context builder for the ICMR STW Grounded RAG system."""

from __future__ import annotations

from typing import List, Optional, Set, Tuple

from ..llm.safety import SafetyGuard
from ..retrieval.models import RetrievalResult


class ContextBuilder:
    """Builds strict, standardized evidence context blocks from retrieval results."""

    def __init__(self, max_units: int = 5, max_chars_per_unit: int = 1500) -> None:
        self.max_units = max_units
        self.max_chars_per_unit = max_chars_per_unit

    def build_context(
        self,
        retrieval_results: List[RetrievalResult],
    ) -> Tuple[str, List[RetrievalResult], Set[str]]:
        """Construct structured evidence blocks for the LLM prompt.

        Returns:
            (formatted_context_str, selected_results, set_of_selected_unit_ids)
        """
        seen_units: Set[str] = set()
        selected: List[RetrievalResult] = []

        for r in retrieval_results:
            # 1. Deduplicate by unit_id
            if r.unit_id in seen_units:
                continue

            # 2. Strictly exclude any review-flagged or unverified content
            if r.review_status == "needs_review":
                continue

            seen_units.add(r.unit_id)
            selected.append(r)

            if len(selected) >= self.max_units:
                break

        if not selected:
            return "", [], set()

        blocks: List[str] = []
        unit_ids: Set[str] = set()

        for idx, r in enumerate(selected, start=1):
            unit_ids.add(r.unit_id)

            # Sanitize content against instruction injection
            clean_content = SafetyGuard.sanitize_evidence_text(r.content.strip())
            if len(clean_content) > self.max_chars_per_unit:
                clean_content = clean_content[: self.max_chars_per_unit] + " [TRUNCATED]"

            version_str = getattr(r, "version_id", "v1.0")
            block = (
                f"[EVIDENCE {idx}]\n"
                f"Specialty: {r.specialty}\n"
                f"Condition: {r.condition}\n"
                f"Document: {r.document_id}\n"
                f"Version: {version_str}\n"
                f"Page: {r.page_number}\n"
                f"Section: {r.section}\n"
                f"Source: Indian Council of Medical Research (ICMR) Official STW\n"
                f"[ID]: {r.unit_id}\n"
                f"[Status]: APPROVED\n"
                f"[Content]: {clean_content}"
            )
            blocks.append(block)

        context_str = "\n\n".join(blocks)
        return context_str, selected, unit_ids

