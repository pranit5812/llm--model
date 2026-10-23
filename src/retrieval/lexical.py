"""BM25 lexical retrieval for the ICMR STW knowledge base.

Uses rank_bm25 (BM25Okapi) with simple whitespace tokenization.
Metadata pre-filters are applied before BM25 scoring.
No LLM, SLM, or AI generation is used.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from ..knowledge.indexer import KnowledgeIndexer
from ..knowledge.metadata import MetadataFilter
from ..knowledge.units import KnowledgeUnit
from .models import RetrievalQuery, RetrievalResult, MIN_SCORE_THRESHOLD
from .scope import is_query_in_cardiology_scope, is_query_in_clinical_scope

logger = logging.getLogger(__name__)


def _tokenize(text: str) -> List[str]:
    """Tokenize text into lowercase alpha tokens (min length 2)."""
    return [t for t in re.findall(r"\b[a-zA-Z0-9_\-]{2,}\b", text.lower())]


class LexicalRetriever:
    """BM25Okapi lexical retriever over the ICMR STW production knowledge base."""

    def __init__(self, indexer: KnowledgeIndexer) -> None:
        self._indexer = indexer

    def retrieve(
        self,
        query: RetrievalQuery,
    ) -> List[RetrievalResult]:
        """Run BM25 retrieval and return ranked results.

        Returns an empty list (or NO_RELIABLE_ICMR_EVIDENCE sentinel wrapped
        in a list) if no result meets the minimum score threshold.
        """
        prod_specs = {u.specialty for u in self._indexer.get_all_production_units()}
        if query.specialty:
            if query.specialty not in prod_specs:
                return []
        else:
            if not is_query_in_cardiology_scope(query):
                from .router import SpecialtyRouter
                routed_spec, conf, _ = SpecialtyRouter.route_query(query.query)
                if not routed_spec or routed_spec not in prod_specs:
                    return []

        prod_units = self._indexer.get_all_production_units()

        # Apply metadata pre-filters
        filtered = (
            MetadataFilter(prod_units)
            .by_specialty(query.specialty)
            .by_condition(query.condition)
            .by_document_id(query.document_id)
            .by_version_id(query.version_id)
            .by_section(query.section)
            .by_healthcare_tier(query.healthcare_tier)
            .by_entity_type(query.entity_type)
            .result()
        )

        if not filtered:
            return []

        # Build a local BM25 over the filtered subset
        tokenized_corpus = [_tokenize(u.content) for u in filtered]
        from rank_bm25 import BM25Okapi
        local_bm25 = BM25Okapi(tokenized_corpus)

        query_tokens = _tokenize(query.query)
        if not query_tokens:
            return []

        scores = local_bm25.get_scores(query_tokens)

        # Pair (unit, score) and sort
        pairs = sorted(zip(filtered, scores), key=lambda x: x[1], reverse=True)

        results = []
        for rank, (unit, score) in enumerate(pairs[: query.top_k], start=1):
            if score < MIN_SCORE_THRESHOLD:
                break
            results.append(self._to_result(unit, score, rank))

        return results

    @staticmethod
    def _to_result(unit: KnowledgeUnit, score: float, rank: int) -> RetrievalResult:
        return RetrievalResult(
            unit_id=unit.unit_id,
            content=unit.content,
            score=round(float(score), 6),
            document_id=unit.document_id,
            condition=unit.condition,
            specialty=unit.specialty,
            page_number=unit.page_number,
            section=unit.section,
            entity_type=unit.entity_type,
            review_status=unit.review_status,
            version_id=getattr(unit, "version_id", "v1.0"),
            source_reference=unit.source_reference,
            rank=rank,
        )
