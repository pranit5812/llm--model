"""TF-IDF + cosine similarity semantic retrieval for the ICMR STW knowledge base.

Uses sklearn TfidfVectorizer with bigrams and cosine similarity.
This is an offline-compatible semantic layer that does not require
model downloads or neural inference. It captures medical term co-occurrence
patterns effectively within the controlled ICMR vocabulary domain.

Metadata pre-filters are applied before similarity computation.
No LLM, SLM, or AI generation is used.
"""

from __future__ import annotations

from typing import List

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..knowledge.indexer import KnowledgeIndexer
from ..knowledge.metadata import MetadataFilter
from ..knowledge.units import KnowledgeUnit
from .models import RetrievalQuery, RetrievalResult, MIN_SCORE_THRESHOLD
from .scope import is_query_in_cardiology_scope, is_query_in_clinical_scope


class SemanticRetriever:
    """TF-IDF vector retrieval over the production knowledge index.

    Applies metadata pre-filters, vectorises the filtered subset using the
    global TF-IDF vocabulary, and ranks results by cosine similarity.
    """

    def __init__(self, indexer: KnowledgeIndexer) -> None:
        self._indexer = indexer
        if not indexer.is_loaded():
            indexer.load()

    def retrieve(self, query: RetrievalQuery) -> List[RetrievalResult]:
        """Run TF-IDF cosine similarity retrieval and return ranked results."""
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

        vectorizer, global_matrix = self._indexer.get_tfidf()
        prod_unit_ids = self._indexer.get_prod_unit_ids()

        # Map filtered units to their row indices in the global TF-IDF matrix
        id_to_idx = {uid: i for i, uid in enumerate(prod_unit_ids)}
        indices = [id_to_idx[u.unit_id] for u in filtered if u.unit_id in id_to_idx]
        filtered_for_index = [u for u in filtered if u.unit_id in id_to_idx]

        if not indices:
            return []

        # Extract the subset matrix
        subset_matrix = global_matrix[indices]

        # Vectorize the query
        query_vec = vectorizer.transform([query.query])

        # Compute cosine similarities
        similarities = cosine_similarity(query_vec, subset_matrix).flatten()

        # Sort and build results
        order = np.argsort(similarities)[::-1]
        results = []
        for rank, idx in enumerate(order[: query.top_k], start=1):
            score = float(similarities[idx])
            if score < MIN_SCORE_THRESHOLD:
                break
            unit = filtered_for_index[idx]
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
