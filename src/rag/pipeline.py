"""End-to-end Grounded RAG Pipeline for ICMR Standard Treatment Workflows."""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..knowledge.indexer import KnowledgeIndexer
from ..llm.base import LLMProvider
from ..llm.citation_validator import CitationValidator
from ..llm.prompts import SYSTEM_PROMPT_V1, USER_PROMPT_TEMPLATE
from ..llm.provider import get_llm_provider
from ..llm.safety import SafetyGuard
from ..llm.schemas import RAGResponse, RAGResponseStatus
from ..retrieval.hybrid import HybridRetriever
from ..retrieval.models import RetrievalQuery, RetrievalResult
from ..retrieval.router import SpecialtyRouter
from ..retrieval.scope import is_query_in_cardiology_scope, is_query_in_clinical_scope
from .context_builder import ContextBuilder
from .response_validator import ResponseValidator


class RAGPipeline:
    """Orchestrates evidence retrieval, context construction, LLM generation,

    citation validation, and clinical safety enforcement.
    """

    def __init__(
        self,
        indexer: Optional[KnowledgeIndexer] = None,
        llm_provider: Optional[LLMProvider] = None,
        citation_validator: Optional[CitationValidator] = None,
        context_builder: Optional[ContextBuilder] = None,
        top_k: int = 5,
    ) -> None:
        self.indexer = indexer or KnowledgeIndexer(
            structured_dir=Path("data/processed/structured"),
            knowledge_dir=Path("data/knowledge"),
        )
        if not self.indexer.is_loaded():
            self.indexer.load()

        self.retriever = HybridRetriever(self.indexer)
        self.llm = llm_provider or get_llm_provider()
        self.citation_validator = citation_validator or CitationValidator(
            db_path=Path("data/knowledge/knowledge.db")
        )
        self.context_builder = context_builder or ContextBuilder(max_units=top_k)
        self.top_k = top_k

    def answer(
        self,
        query: str,
        top_k: Optional[int] = None,
        filters: Optional[Dict[str, Any]] = None,
        debug: bool = False,
    ) -> RAGResponse:
        """Run the full grounded RAG pipeline on a user query."""
        t_start = time.time()
        k = top_k or self.top_k
        filters = filters or {}
        debug_data: Dict[str, Any] = {}

        # -------------------------------------------------------------------
        # Step 1: Prompt Injection Defense
        # -------------------------------------------------------------------
        is_injection, injection_msg = SafetyGuard.inspect_query_for_injection(query)
        if is_injection:
            return RAGResponse(
                status=RAGResponseStatus.OUT_OF_SCOPE,
                answer="The query violates clinical safety policies and cannot be processed.",
                key_points=[],
                cautions=[injection_msg],
                citations=[],
                evidence_ids=[],
                confidence="NONE",
                abstained=True,
                debug_info={"adversarial": True, "reason": injection_msg} if debug else None,
            )

        # Detect if query asks for personal diagnosis / prescription
        lower_q = query.lower()
        is_personal = any(p in lower_q for p in ["what should i take", "should i take", "personally take", "prescribe for me", "my symptoms", "am i having"])

        # Check for version conflict in query
        if re.search(r"\b(20\d\d)\b.*\b(20\d\d)\b", lower_q) or ("differences between" in lower_q and "guideline" in lower_q):
            return RAGResponse(
                status=RAGResponseStatus.VERSION_CONFLICT,
                answer="The query references multiple guideline versions or publication years. ICMR Standard Treatment Workflows follow strict version precedence, and superseded recommendations cannot be combined.",
                key_points=[],
                cautions=["Version conflict detected in clinical query."],
                citations=[],
                evidence_ids=[],
                confidence="NONE",
                abstained=True,
                debug_info={"reason": "VERSION_CONFLICT"} if debug else None,
            )

        # Check for cross-specialty ambiguity
        if SpecialtyRouter.is_ambiguous(query):
            return RAGResponse(
                status=RAGResponseStatus.AMBIGUOUS_SOURCE,
                answer="The clinical query matches multiple medical specialties with similar confidence. Please specify the target specialty or clinical condition for safe retrieval.",
                key_points=[],
                cautions=["Ambiguous clinical source detected across specialties."],
                citations=[],
                evidence_ids=[],
                confidence="NONE",
                abstained=True,
                debug_info={"reason": "AMBIGUOUS_SOURCE"} if debug else None,
            )

        # -------------------------------------------------------------------
        # Step 2: Specialty Routing & Clinical Scope Check
        # -------------------------------------------------------------------
        target_specialty = filters.get("specialty")
        if not target_specialty:
            routed_spec, conf, _ = SpecialtyRouter.route_query(query)
            if conf >= 0.5:
                target_specialty = routed_spec

        rq = RetrievalQuery(
            query=query,
            top_k=k * 2,
            specialty=target_specialty,
            condition=filters.get("condition"),
            document_id=filters.get("document_id"),
            version_id=filters.get("version_id"),
            section=filters.get("section"),
            healthcare_tier=filters.get("healthcare_tier"),
            entity_type=filters.get("entity_type"),
        )

        if rq.specialty == "Cardiology":
            in_scope = is_query_in_cardiology_scope(rq)
        else:
            in_scope = is_query_in_clinical_scope(rq)

        if not in_scope:
            return RAGResponse(
                status=RAGResponseStatus.OUT_OF_SCOPE,
                answer=(
                    "The query is outside the clinical scope of the official ICMR "
                    "Standard Treatment Workflows."
                ),
                key_points=[],
                cautions=["No matching official ICMR STW found."],
                citations=[],
                evidence_ids=[],
                confidence="NONE",
                abstained=True,
                debug_info={"scope": "OUT_OF_SCOPE"} if debug else None,
            )

        # -------------------------------------------------------------------
        # Step 3: Hybrid Retrieval & Reranking
        # -------------------------------------------------------------------
        t_ret_start = time.time()
        retrieval_results = self.retriever.retrieve(rq)
        retrieval_latency = round(time.time() - t_ret_start, 4)
        debug_data["retrieval_latency_sec"] = retrieval_latency
        debug_data["retrieved_candidates_count"] = len(retrieval_results)

        if not retrieval_results:
            if target_specialty and target_specialty != "Cardiology":
                return RAGResponse(
                    status=RAGResponseStatus.INSUFFICIENT_APPROVED_EVIDENCE,
                    answer=f"Relevant ICMR Standard Treatment Workflow content for {target_specialty} is currently pending clinical review and cannot be provided as authoritative production evidence.",
                    key_points=[],
                    cautions=[f"{target_specialty} guidelines are currently quarantined in the clinical review queue."],
                    citations=[],
                    evidence_ids=[],
                    confidence="NONE",
                    abstained=True,
                    debug_info=debug_data if debug else None,
                )
            return RAGResponse(
                status=RAGResponseStatus.NO_RELIABLE_ICMR_EVIDENCE,
                answer="The available ICMR Standard Treatment Workflow evidence does not provide sufficient information to answer this question.",
                key_points=[],
                cautions=[],
                citations=[],
                evidence_ids=[],
                confidence="NONE",
                abstained=True,
                debug_info=debug_data if debug else None,
            )

        # -------------------------------------------------------------------
        # Step 4: Evidence Selection & Context Formatting
        # -------------------------------------------------------------------
        evidence_context, selected_results, unit_ids = self.context_builder.build_context(retrieval_results)

        if not selected_results:
            # Only unapproved or review units existed
            return RAGResponse(
                status=RAGResponseStatus.INSUFFICIENT_APPROVED_EVIDENCE,
                answer="Relevant ICMR source content is currently pending clinical review and cannot be provided as authoritative evidence.",
                key_points=[],
                cautions=["Source material flagged for clinical review."],
                citations=[],
                evidence_ids=[],
                confidence="NONE",
                abstained=True,
                debug_info=debug_data if debug else None,
            )

        debug_data["selected_units_count"] = len(selected_results)
        debug_data["selected_unit_ids"] = list(unit_ids)


        # -------------------------------------------------------------------
        # Step 5: LLM Generation
        # -------------------------------------------------------------------
        user_prompt = USER_PROMPT_TEMPLATE.format(
            query=query,
            evidence_context=evidence_context,
        )

        t_llm_start = time.time()
        try:
            raw_response = self.llm.generate_structured(
                prompt=user_prompt,
                response_model=RAGResponse,
                system_prompt=SYSTEM_PROMPT_V1,
            )
        except Exception as e:
            # Graceful generation fallback
            return RAGResponse(
                status=RAGResponseStatus.INSUFFICIENT_EVIDENCE,
                answer="An error occurred during evidence synthesis. Please consult the raw ICMR citations.",
                key_points=[],
                cautions=[f"Generation error: {str(e)}"],
                citations=[],
                evidence_ids=list(unit_ids),
                confidence="NONE",
                abstained=True,
                debug_info={"error": str(e)} if debug else None,
            )

        llm_latency = round(time.time() - t_llm_start, 4)
        debug_data["llm_latency_sec"] = llm_latency
        debug_data["llm_provider"] = self.llm.name

        # -------------------------------------------------------------------
        # Step 6: Citation Validation against SQLite & Evidence
        # -------------------------------------------------------------------
        val_result = self.citation_validator.validate_citations(
            raw_response.citations,
            retrieved_unit_ids=unit_ids,
        )

        debug_data["citation_validation"] = val_result.to_dict()

        if not val_result.is_valid:
            # If citations failed validation, use only the verified ones or downgrade
            if val_result.verified_citations:
                raw_response.citations = val_result.verified_citations
                raw_response.status = RAGResponseStatus.PARTIALLY_GROUNDED
                raw_response.cautions.append("Some generated citations failed database verification and were removed.")
            else:
                # No verified citations remain — force safe abstention
                raw_response.citations = []
                raw_response.status = RAGResponseStatus.INSUFFICIENT_EVIDENCE
                raw_response.abstained = True
                raw_response.answer = (
                    "The available ICMR Standard Treatment Workflow evidence could not reliably "
                    "validate the generated response."
                )

        # -------------------------------------------------------------------
        # Step 7: Grounding & Version Consistency Validation
        # -------------------------------------------------------------------
        validated_response = ResponseValidator.validate_response(
            raw_response,
            evidence_results=selected_results,
        )

        # -------------------------------------------------------------------
        # Step 8: Safety Advisory for Personal Medical Queries
        # -------------------------------------------------------------------
        if is_personal:
            validated_response.answer = SafetyGuard.format_safe_advisory(
                validated_response.answer, is_personal_query=True
            )

        # Total latency
        total_latency = round(time.time() - t_start, 4)
        debug_data["total_latency_sec"] = total_latency

        if debug:
            validated_response.debug_info = debug_data

        return validated_response
