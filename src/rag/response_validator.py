"""Response validation and clinical grounding verification layer."""

from __future__ import annotations

import re
from typing import List, Optional, Set, Tuple

from ..llm.schemas import CitationItem, RAGResponse, RAGResponseStatus
from ..retrieval.models import RetrievalResult


class ResponseValidator:
    """Verifies that generated responses are strictly grounded in retrieved evidence."""

    @staticmethod
    def detect_version_conflicts(evidence_results: List[RetrievalResult]) -> Optional[str]:
        """Detect whether retrieved evidence spans multiple STWs for the same condition.

        For example: 2019 Consolidated Cardiology (ICMR-CARD-007) vs dedicated
        condition STWs (ICMR-CARD-001 through 006).
        """
        doc_ids = set(r.document_id for r in evidence_results)
        has_consolidated = "ICMR-CARD-007" in doc_ids
        has_dedicated = any(d != "ICMR-CARD-007" for d in doc_ids)

        if has_consolidated and has_dedicated:
            dedicated_docs = [d for d in doc_ids if d != "ICMR-CARD-007"]
            return (
                f"Multiple ICMR source versions contain relevant information: dedicated workflow(s) "
                f"({', '.join(dedicated_docs)}) and consolidated workflow (ICMR-CARD-007). "
                f"The system preserves all citations without independently determining clinical precedence."
            )
        return None

    @staticmethod
    def verify_dosage_grounding(answer: str, evidence_results: List[RetrievalResult]) -> Tuple[bool, List[str]]:
        """Verify that any dosages, quantities, or timelines in the answer exist in the evidence.

        Extracts numeric values followed by units (mg, mcg, gm, ml, hours, min, etc.)
        and checks for their presence in the combined evidence text.
        """
        # Match patterns like: 300 mg, 75mg, 1.5 mega units, 10 min, 120 minutes, 5-10 mg
        dosage_pattern = r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|gm|g|ml|iu|mega\s*units|min|minutes|hours|hrs|mmHg)\b"
        answer_dosages = set(m.lower().replace(" ", "") for m in re.findall(dosage_pattern, answer, re.IGNORECASE))

        if not answer_dosages:
            return True, []

        combined_evidence = " ".join(r.content for r in evidence_results).lower().replace(" ", "")
        unsupported = []

        for dose in answer_dosages:
            if dose not in combined_evidence:
                unsupported.append(dose)

        is_grounded = len(unsupported) == 0
        return is_grounded, unsupported

    @classmethod
    def validate_response(
        cls,
        response: RAGResponse,
        evidence_results: List[RetrievalResult],
    ) -> RAGResponse:
        """Perform comprehensive grounding and consistency validation.

        Adjusts response status and adds warnings if ungrounded elements are detected.
        """
        # If already abstained, nothing to ground
        if response.abstained:
            return response

        # 1. Version conflict check
        v_warning = cls.detect_version_conflicts(evidence_results)
        if v_warning:
            response.version_warning = v_warning

        # 2. Dosage grounding check
        is_dosage_grounded, ungrounded_doses = cls.verify_dosage_grounding(response.answer, evidence_results)
        if not is_dosage_grounded:
            response.status = RAGResponseStatus.PARTIALLY_GROUNDED
            response.cautions.append(
                f"Grounding Alert: Specific quantities or dosages ({', '.join(ungrounded_doses)}) "
                f"could not be deterministically verified against the retrieved evidence blocks."
            )

        # 3. Check citations non-empty
        if not response.citations and response.status == RAGResponseStatus.GROUNDED:
            response.status = RAGResponseStatus.PARTIALLY_GROUNDED

        return response
