"""Tests for retrieval evaluation dataset, metrics, and pipeline."""

import json
from pathlib import Path
import pytest

from scripts.evaluate_retrieval import recall_at_k, reciprocal_rank, run_evaluation
from src.knowledge.indexer import KnowledgeIndexer
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.lexical import LexicalRetriever


EVAL_DATASET_PATH = Path("data/evaluation/retrieval_queries.json")


@pytest.fixture(scope="module")
def eval_dataset():
    assert EVAL_DATASET_PATH.exists(), f"Evaluation dataset not found at {EVAL_DATASET_PATH}"
    with open(EVAL_DATASET_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["queries"]


@pytest.fixture(scope="module")
def indexer():
    idx = KnowledgeIndexer(
        structured_dir=Path("data/processed/structured"),
        knowledge_dir=Path("data/knowledge"),
    )
    idx.load()
    return idx


class TestEvaluationDatasetStructure:
    """Validate format and completeness of the evaluation benchmark."""

    def test_dataset_non_empty(self, eval_dataset):
        assert len(eval_dataset) >= 30

    def test_required_fields_in_each_query(self, eval_dataset):
        required_fields = ["query_id", "query", "should_return_evidence"]
        for q in eval_dataset:
            for f in required_fields:
                assert f in q, f"Missing {f} in query {q.get('query_id')}"

    def test_has_both_positive_and_negative_queries(self, eval_dataset):
        positives = [q for q in eval_dataset if q["should_return_evidence"]]
        negatives = [q for q in eval_dataset if not q["should_return_evidence"]]
        assert len(positives) >= 20
        assert len(negatives) >= 3


class TestEvaluationMetricsMath:
    """Test metric computation helpers."""

    def test_recall_at_k_perfect(self):
        retrieved = ["DOC-1", "DOC-2", "DOC-3"]
        expected = {"DOC-1", "DOC-2"}
        assert recall_at_k(retrieved, expected, 2) == 1.0

    def test_recall_at_k_partial(self):
        retrieved = ["DOC-1", "DOC-3", "DOC-4"]
        expected = {"DOC-1", "DOC-2"}
        assert recall_at_k(retrieved, expected, 2) == 0.5

    def test_recall_at_k_zero(self):
        retrieved = ["DOC-3", "DOC-4"]
        expected = {"DOC-1", "DOC-2"}
        assert recall_at_k(retrieved, expected, 2) == 0.0

    def test_reciprocal_rank(self):
        retrieved = ["DOC-3", "DOC-1", "DOC-2"]
        expected = {"DOC-1"}
        # DOC-1 is at rank 2 -> RR = 0.5
        assert reciprocal_rank(retrieved, expected) == 0.5

        # Not found -> RR = 0.0
        assert reciprocal_rank(["DOC-4"], expected) == 0.0


class TestEvaluationRunOnDataset:
    """Run evaluation and verify hybrid pipeline performance."""

    def test_hybrid_evaluation_runs_and_yields_high_mrr(self, eval_dataset, indexer):
        hybrid = HybridRetriever(indexer)
        summary = run_evaluation(eval_dataset, "Hybrid", hybrid.retrieve)

        assert summary["recall@5"] >= 0.67, f"Expected Recall@5 >= 0.67, got {summary['recall@5']}"
        assert summary["mrr"] >= 0.60, f"Expected MRR >= 0.60, got {summary['mrr']}"
        assert summary["abstention_accuracy"] >= 0.80, f"Expected abstention >= 0.80, got {summary['abstention_accuracy']}"
