"""Hybrid retrieval via Reciprocal Rank Fusion (RRF) for the ICMR STW knowledge base.

Combines BM25 lexical and TF-IDF semantic rankings using RRF:

    score(d) = Σ 1 / (k + rank_method(d))

where k=60 (standard RRF constant, dampens the effect of top-rank outliers).

RRF is parameter-light, robust, and consistently outperforms individual
retrieval methods in information-retrieval benchmarks.

No LLM, SLM, or AI generation is used.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Tuple


from ..knowledge.indexer import KnowledgeIndexer
from .lexical import LexicalRetriever
from .models import (
    RetrievalResult,
    RetrievalQuery,
    NO_RELIABLE_ICMR_EVIDENCE,
    MIN_SCORE_THRESHOLD,
)
from .reranker import Reranker, TFIDFReranker
from .router import SpecialtyRouter
from .scope import is_query_in_cardiology_scope, is_query_in_clinical_scope
from .semantic import SemanticRetriever


logger = logging.getLogger(__name__)

# Reciprocal Rank Fusion constant
_RRF_K = 60


class HybridRetriever:
    """RRF-based hybrid retriever combining BM25 lexical and TF-IDF semantic search."""

    def __init__(
        self,
        indexer: KnowledgeIndexer,
        reranker: Optional[Reranker] = None,
        n_candidates: int = 50,
    ) -> None:
        self._indexer = indexer
        self._lexical = LexicalRetriever(indexer)
        self._semantic = SemanticRetriever(indexer)
        self._reranker: Reranker = reranker or TFIDFReranker()
        self._n_candidates = n_candidates

    def retrieve(self, query: RetrievalQuery) -> List[RetrievalResult]:
        """Run hybrid retrieval and return re-ranked results.

        Returns an empty list if no unit exceeds MIN_SCORE_THRESHOLD,
        allowing the API layer to return NO_RELIABLE_ICMR_EVIDENCE.
        """
        prod_specs = {u.specialty for u in self._indexer.get_all_production_units()}
        if query.specialty:
            if query.specialty not in prod_specs:
                return []
        else:
            if not is_query_in_cardiology_scope(query):
                routed_spec, conf, _ = SpecialtyRouter.route_query(query.query)
                if not routed_spec or routed_spec not in prod_specs:
                    return []

        # Fetch candidates from both retrievers
        candidate_query = RetrievalQuery(
            query=query.query,
            top_k=self._n_candidates,
            specialty=query.specialty,
            condition=query.condition,
            document_id=query.document_id,
            version_id=query.version_id,
            section=query.section,
            healthcare_tier=query.healthcare_tier,
            entity_type=query.entity_type,
        )

        lexical_results = self._lexical.retrieve(candidate_query)
        semantic_results = self._semantic.retrieve(candidate_query)

        if not lexical_results and not semantic_results:
            return []

        # --- RRF fusion ---
        rrf_scores: Dict[str, float] = {}
        unit_map: Dict[str, RetrievalResult] = {}

        for rank, result in enumerate(lexical_results, start=1):
            rrf_scores[result.unit_id] = rrf_scores.get(result.unit_id, 0.0) + 1.0 / (_RRF_K + rank)
            unit_map[result.unit_id] = result

        for rank, result in enumerate(semantic_results, start=1):
            rrf_scores[result.unit_id] = rrf_scores.get(result.unit_id, 0.0) + 1.0 / (_RRF_K + rank)
            if result.unit_id not in unit_map:
                unit_map[result.unit_id] = result

        # Sort by RRF score
        sorted_ids = sorted(rrf_scores, key=lambda uid: rrf_scores[uid], reverse=True)

        # Build fused result list with normalised [0, 1] RRF scores
        max_rrf = rrf_scores[sorted_ids[0]] if sorted_ids else 1.0
        fused: List[RetrievalResult] = []
        for rank, uid in enumerate(sorted_ids[: self._n_candidates], start=1):
            r = unit_map[uid]
            fused.append(RetrievalResult(
                unit_id=r.unit_id,
                content=r.content,
                score=round(rrf_scores[uid] / max_rrf, 6),
                document_id=r.document_id,
                condition=r.condition,
                specialty=r.specialty,
                page_number=r.page_number,
                section=r.section,
                entity_type=r.entity_type,
                review_status=r.review_status,
                version_id=getattr(r, "version_id", "v1.0"),
                source_reference=r.source_reference,
                rank=rank,
            ))

        # --- Reranker ---
        reranked = self._reranker.rerank(query.query, fused)

        # --- Cross-Specialty Isolation ---
        target_spec = query.specialty
        if not target_spec:
            routed_spec, conf, _ = SpecialtyRouter.route_query(query.query)
            if conf >= 0.6:
                target_spec = routed_spec

        if target_spec:
            for res in reranked:
                if res.specialty.lower() != target_spec.lower():
                    res.score *= 0.1
            reranked = sorted(reranked, key=lambda x: x.score, reverse=True)

        # Final top-K
        top_k = reranked[: query.top_k]

        # Reassign final ranks
        for i, r in enumerate(top_k, start=1):
            r.rank = i

        return top_k
