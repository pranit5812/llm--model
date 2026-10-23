"""Clinical RAG Model Evaluation Metrics.

Computes multi-dimensional evaluation metrics across models adhering strictly
to ICMR STW evidence grounding requirements.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set

from ..llm.schemas import RAGResponse, RAGResponseStatus


@dataclass
class ModelEvaluationScorecard:
    """Comprehensive evaluation metrics scorecard for a single evaluated model."""
    model_name: str
    provider: str
    total_queries: int
    positive_queries: int
    negative_queries: int

    # Core Grounding & Safety Metrics
    groundedness_rate: float = 0.0
    citation_correctness_rate: float = 0.0
    citation_completeness_rate: float = 0.0
    unsupported_claim_rate: float = 0.0
    abstention_accuracy: float = 0.0
    schema_validity_rate: float = 0.0
    retrieval_consistency_rate: float = 0.0

    # Clinical Precision Metrics
    dosage_accuracy: float = 0.0
    timeline_accuracy: float = 0.0
    contraindication_accuracy: float = 0.0
    version_handling_accuracy: float = 0.0

    # Operational Metrics
    avg_latency_sec: float = 0.0
    error_rate: float = 0.0

    # Diagnostic counts
    total_citations_generated: int = 0
    total_citations_verified: int = 0
    hallucinated_dosages_count: int = 0

    per_category_accuracy: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MetricsCalculator:
    """Calculates granular evaluation metrics comparing model outputs against benchmark expectations."""

    @staticmethod
    def calculate_dosage_accuracy(response_answer: str, expected_terms: List[str]) -> Tuple[bool, int]:
        """Check if dosages in response are supported or if hallucinated numbers appear."""
        # Find numeric dosages (e.g. 300mg, 150 mg, 1.5 mega units)
        dosage_pattern = r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|gm|g|ml|iu|mega\s*units|min|minutes|hours)\b"
        found = set(m.lower().replace(" ", "") for m in re.findall(dosage_pattern, response_answer, re.IGNORECASE))

        # Compare with expected terms
        expected_set = set(t.lower().replace(" ", "") for t in expected_terms)
        hallucinated = 0

        for d in found:
            # If a dosage appears that isn't in expected terms or basic standard numbers
            if expected_set and not any(t in d or d in t for t in expected_set):
                hallucinated += 1

        is_accurate = hallucinated == 0
        return is_accurate, hallucinated

    @classmethod
    def evaluate_model_run(
        cls,
        model_name: str,
        provider: str,
        results: List[Dict[str, Any]],
    ) -> ModelEvaluationScorecard:
        """Compute scorecard from a list of per-query execution results."""
        total = len(results)
        positives = [r for r in results if not r["should_abstain"]]
        negatives = [r for r in results if r["should_abstain"]]

        n_pos = len(positives)
        n_neg = len(negatives)

        grounded_count = 0
        citation_correct_count = 0
        citation_complete_count = 0
        abstention_correct_count = 0
        schema_valid_count = 0
        retrieval_consistent_count = 0
        dosage_accurate_count = 0
        timeline_accurate_count = 0
        contraindication_accurate_count = 0
        version_accurate_count = 0
        error_count = 0

        total_citations = 0
        verified_citations = 0
        total_hallucinated_dosages = 0
        total_latency = 0.0

        category_counts: Dict[str, int] = {}
        category_correct: Dict[str, int] = {}

        for r in results:
            cat = r["category"]
            category_counts[cat] = category_counts.get(cat, 0) + 1
            total_latency += r.get("latency_sec", 0.0)

            if r.get("error"):
                error_count += 1
                continue

            # Schema validity
            if r.get("schema_valid", True):
                schema_valid_count += 1

            if r["should_abstain"]:
                # Negative queries: expected to abstain
                if r["abstained"] is True:
                    abstention_correct_count += 1
                    category_correct[cat] = category_correct.get(cat, 0) + 1
            else:
                # Positive queries: expected to answer grounded
                is_correct = True
                status = r.get("actual_status", "")

                if status in ["GROUNDED", "PARTIALLY_GROUNDED"]:
                    grounded_count += 1
                else:
                    is_correct = False

                # Citations
                c_count = r.get("citations_count", 0)
                total_citations += c_count
                if c_count > 0:
                    citation_complete_count += 1

                if r.get("is_citations_verified", False):
                    citation_correct_count += 1
                    verified_citations += c_count
                else:
                    is_correct = False

                # Retrieval consistency
                if r.get("is_retrieval_correct", False):
                    retrieval_consistent_count += 1
                else:
                    is_correct = False

                # Dosage accuracy
                _, hall_doses = cls.calculate_dosage_accuracy(r.get("answer", ""), r.get("expected_terms", []))
                if hall_doses == 0:
                    dosage_accurate_count += 1
                else:
                    total_hallucinated_dosages += hall_doses

                # Timeline & contraindications & version checks by category
                if "contraindication" in cat:
                    if "contraindication" in r.get("answer", "").lower() or r.get("cautions"):
                        contraindication_accurate_count += 1
                if "flowchart" in cat or "tier" in cat:
                    timeline_accurate_count += 1
                if "version" in cat:
                    if r.get("version_warning") or "version" in r.get("answer", "").lower():
                        version_accurate_count += 1

                if is_correct:
                    category_correct[cat] = category_correct.get(cat, 0) + 1

        # Calculate rates
        groundedness_rate = (grounded_count / n_pos) if n_pos else 1.0
        citation_correct_rate = (citation_correct_count / n_pos) if n_pos else 1.0
        citation_complete_rate = (citation_complete_count / n_pos) if n_pos else 1.0
        unsupported_rate = round(1.0 - groundedness_rate, 4)
        abstention_rate = (abstention_correct_count / n_neg) if n_neg else 1.0
        schema_rate = (schema_valid_count / total) if total else 1.0
        retrieval_rate = (retrieval_consistent_count / n_pos) if n_pos else 1.0
        dosage_rate = (dosage_accurate_count / n_pos) if n_pos else 1.0
        avg_latency = round(total_latency / total, 4) if total else 0.0
        err_rate = (error_count / total) if total else 0.0

        per_cat_acc = {}
        for cat, count in category_counts.items():
            per_cat_acc[cat] = round(category_correct.get(cat, 0) / count, 4)

        return ModelEvaluationScorecard(
            model_name=model_name,
            provider=provider,
            total_queries=total,
            positive_queries=n_pos,
            negative_queries=n_neg,
            groundedness_rate=round(groundedness_rate, 4),
            citation_correctness_rate=round(citation_correct_rate, 4),
            citation_completeness_rate=round(citation_complete_rate, 4),
            unsupported_claim_rate=unsupported_rate,
            abstention_accuracy=round(abstention_rate, 4),
            schema_validity_rate=round(schema_rate, 4),
            retrieval_consistency_rate=round(retrieval_rate, 4),
            dosage_accuracy=round(dosage_rate, 4),
            timeline_accuracy=round(timeline_accurate_count / max(1, n_pos), 4),
            contraindication_accuracy=round(contraindication_accurate_count / max(1, n_pos), 4),
            version_handling_accuracy=round(version_accurate_count / max(1, n_pos), 4),
            avg_latency_sec=avg_latency,
            error_rate=round(err_rate, 4),
            total_citations_generated=total_citations,
            total_citations_verified=verified_citations,
            hallucinated_dosages_count=total_hallucinated_dosages,
            per_category_accuracy=per_cat_acc,
        )
