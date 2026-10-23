"""Reranking abstraction for the ICMR STW retrieval system.

Provides a base Reranker interface and a default TFIDFReranker
implementation that rescores candidates by token overlap between
the query and each candidate's content.

The interface is designed to be easily replaced in Phase 5 with a
neural cross-encoder model without changing downstream code.

No LLM, SLM, or AI generation is used.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import List

from .models import RetrievalResult


def _token_set(text: str) -> set:
    """Extract a set of lower-case tokens from text."""
    return set(re.sub(r"[^\w\s]", " ", text.lower()).split())


class Reranker(ABC):
    """Abstract base class for result rerankers.

    Implementations must be stateless and thread-safe.
    The interface is intentionally minimal to facilitate replacement.
    """

    @abstractmethod
    def rerank(self, query: str, results: List[RetrievalResult]) -> List[RetrievalResult]:
        """Rerank a list of retrieval results for the given query.

        Args:
            query: The original user query string.
            results: Candidate results from a prior retrieval stage.

        Returns:
            Reranked list (same objects, potentially in different order).
            Must return the same number of results as input.
        """
        ...


class TFIDFReranker(Reranker):
    """Lightweight token-overlap reranker.

    Rescores each candidate by computing the Jaccard-style token overlap
    between the query tokens and the candidate content tokens, then blends
    this with the incoming retrieval score.

    This is a deterministic, interpretable, offline reranker that improves
    ordering when the query contains specific medical terms present in only
    a subset of the candidate pool.

    Replacement in Phase 5:
        Subclass Reranker and implement rerank() using a cross-encoder model
        (e.g. cross-encoder/ms-marco-MiniLM-L-6-v2) once sentence-transformers
        compatibility is resolved.
    """

    def __init__(self, blend_alpha: float = 0.4) -> None:
        """
        Args:
            blend_alpha: Weight of token-overlap score in final blend.
                         Final score = (1-alpha)*retrieval_score + alpha*overlap_score.
        """
        self._alpha = blend_alpha

    def rerank(self, query: str, results: List[RetrievalResult]) -> List[RetrievalResult]:
        if not results:
            return results

        query_tokens = _token_set(query)
        if not query_tokens:
            return results

        rescored = []
        for r in results:
            candidate_tokens = _token_set(r.content)
            intersection = query_tokens & candidate_tokens
            union = query_tokens | candidate_tokens
            overlap = len(intersection) / len(union) if union else 0.0

            blended = (1.0 - self._alpha) * r.score + self._alpha * overlap
            # Create a new result with blended score (preserve all other fields)
            rescored.append(RetrievalResult(
                unit_id=r.unit_id,
                content=r.content,
                score=round(blended, 6),
                document_id=r.document_id,
                condition=r.condition,
                specialty=r.specialty,
                page_number=r.page_number,
                section=r.section,
                entity_type=r.entity_type,
                review_status=r.review_status,
                source_reference=r.source_reference,
                rank=r.rank,
            ))

        rescored.sort(key=lambda x: x.score, reverse=True)
        return rescored
