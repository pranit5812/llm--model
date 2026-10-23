#!/usr/bin/env python
"""Evaluate retrieval performance of the ICMR STW knowledge system.

Runs all queries from data/evaluation/retrieval_queries.json through
lexical (BM25), semantic (TF-IDF), and hybrid (RRF) retrievers.

Computes:
  - Recall@1, Recall@3, Recall@5, Recall@10
  - MRR (Mean Reciprocal Rank)
  - Abstention accuracy (negative queries returning NO_RELIABLE_ICMR_EVIDENCE)

Outputs:
  - Console report table
  - data/evaluation/retrieval_results.json

No LLM, SLM, or AI generation.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.knowledge.indexer import KnowledgeIndexer
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.lexical import LexicalRetriever
from src.retrieval.models import (
    NO_RELIABLE_ICMR_EVIDENCE,
    MIN_SCORE_THRESHOLD,
    RetrievalQuery,
    RetrievalResult,
)
from src.retrieval.semantic import SemanticRetriever

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

EVAL_DATASET_PATH = Path("data/evaluation/retrieval_queries.json")
RESULTS_PATH = Path("data/evaluation/retrieval_results.json")
KNOWLEDGE_DIR = Path("data/knowledge")
STRUCTURED_DIR = Path("data/processed/structured")
TOP_K = 10
ABSTENTION_THRESHOLD = MIN_SCORE_THRESHOLD


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------

def recall_at_k(retrieved_doc_ids: List[str], expected_doc_ids: Set[str], k: int) -> float:
    """Recall@K: fraction of expected documents found in top-K results."""
    if not expected_doc_ids:
        return 1.0  # negative queries: recall is not applicable
    top_k = retrieved_doc_ids[:k]
    found = len(set(top_k) & expected_doc_ids)
    return found / len(expected_doc_ids)


def reciprocal_rank(retrieved_doc_ids: List[str], expected_doc_ids: Set[str]) -> float:
    """Reciprocal rank of the first relevant result."""
    if not expected_doc_ids:
        return 0.0
    for rank, doc_id in enumerate(retrieved_doc_ids, start=1):
        if doc_id in expected_doc_ids:
            return 1.0 / rank
    return 0.0


def run_evaluation(
    queries: List[Dict[str, Any]],
    retriever_name: str,
    retrieve_fn,
) -> Dict[str, Any]:
    """Run evaluation for one retriever."""
    positive_queries = [q for q in queries if q["should_return_evidence"]]
    negative_queries = [q for q in queries if not q["should_return_evidence"]]

    recall_1 = recall_3 = recall_5 = recall_10 = mrr = 0.0
    abstention_correct = 0
    per_query_results = []

    # --- Positive queries ---
    for q in positive_queries:
        rq = RetrievalQuery(
            query=q["query"],
            top_k=TOP_K,
            **{k: v for k, v in q.get("filters", {}).items() if v},
        )
        results: List[RetrievalResult] = retrieve_fn(rq)
        retrieved_doc_ids = [r.document_id for r in results]
        expected = set(q.get("expected_document_ids", []))

        r1 = recall_at_k(retrieved_doc_ids, expected, 1)
        r3 = recall_at_k(retrieved_doc_ids, expected, 3)
        r5 = recall_at_k(retrieved_doc_ids, expected, 5)
        r10 = recall_at_k(retrieved_doc_ids, expected, 10)
        rr = reciprocal_rank(retrieved_doc_ids, expected)

        recall_1 += r1
        recall_3 += r3
        recall_5 += r5
        recall_10 += r10
        mrr += rr

        per_query_results.append({
            "query_id": q["query_id"],
            "query": q["query"],
            "category": q["category"],
            "should_return_evidence": True,
            "expected_doc_ids": list(expected),
            "retrieved_doc_ids": retrieved_doc_ids[:5],
            "recall@1": r1,
            "recall@3": r3,
            "recall@5": r5,
            "recall@10": r10,
            "reciprocal_rank": rr,
            "top_result": results[0].to_dict() if results else None,
        })

    n_pos = len(positive_queries)
    if n_pos > 0:
        recall_1 /= n_pos
        recall_3 /= n_pos
        recall_5 /= n_pos
        recall_10 /= n_pos
        mrr /= n_pos

    # --- Negative queries (abstention) ---
    for q in negative_queries:
        rq = RetrievalQuery(query=q["query"], top_k=TOP_K)
        results = retrieve_fn(rq)
        abstained = len(results) == 0
        if abstained:
            abstention_correct += 1
        per_query_results.append({
            "query_id": q["query_id"],
            "query": q["query"],
            "category": q["category"],
            "should_return_evidence": False,
            "abstained": abstained,
            "results_returned": len(results),
            "top_result": results[0].to_dict() if results else None,
        })

    abstention_acc = abstention_correct / len(negative_queries) if negative_queries else 1.0

    return {
        "retriever": retriever_name,
        "positive_queries": n_pos,
        "negative_queries": len(negative_queries),
        "recall@1": round(recall_1, 4),
        "recall@3": round(recall_3, 4),
        "recall@5": round(recall_5, 4),
        "recall@10": round(recall_10, 4),
        "mrr": round(mrr, 4),
        "abstention_accuracy": round(abstention_acc, 4),
        "abstention_correct": abstention_correct,
        "per_query": per_query_results,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Load evaluation dataset
    if not EVAL_DATASET_PATH.exists():
        print(f"[ERROR] Evaluation dataset not found: {EVAL_DATASET_PATH}", file=sys.stderr)
        sys.exit(1)

    with open(EVAL_DATASET_PATH, "r", encoding="utf-8") as f:
        dataset = json.load(f)
    queries = dataset["queries"]
    print(f"Loaded {len(queries)} queries ({dataset['total_queries']} declared).")

    # Load index
    print("Loading knowledge index...")
    indexer = KnowledgeIndexer(structured_dir=STRUCTURED_DIR, knowledge_dir=KNOWLEDGE_DIR)
    indexer.load()

    lexical = LexicalRetriever(indexer)
    semantic = SemanticRetriever(indexer)
    hybrid = HybridRetriever(indexer)

    print(f"Index loaded: {len(indexer.get_all_production_units())} production units.\n")

    # Run evaluations
    evaluations = []
    for name, fn in [
        ("lexical (BM25)", lambda rq: lexical.retrieve(rq)),
        ("semantic (TF-IDF)", lambda rq: semantic.retrieve(rq)),
        ("hybrid (RRF)", lambda rq: hybrid.retrieve(rq)),
    ]:
        print(f"Evaluating: {name}...")
        result = run_evaluation(queries, name, fn)
        evaluations.append(result)

    # --- Print report ---
    print()
    print("=" * 72)
    print("ICMR STW PHASE 4 RETRIEVAL EVALUATION REPORT")
    print("=" * 72)
    print(f"{'Retriever':<22} {'R@1':>6} {'R@3':>6} {'R@5':>6} {'R@10':>6} {'MRR':>6} {'Abstain':>8}")
    print("-" * 72)
    for ev in evaluations:
        print(
            f"{ev['retriever']:<22} "
            f"{ev['recall@1']:>6.3f} "
            f"{ev['recall@3']:>6.3f} "
            f"{ev['recall@5']:>6.3f} "
            f"{ev['recall@10']:>6.3f} "
            f"{ev['mrr']:>6.3f} "
            f"{ev['abstention_accuracy']:>7.0%}"
        )
    print("=" * 72)
    print()

    # Per-category breakdown for hybrid
    hybrid_ev = evaluations[2]
    print("Hybrid per-query highlights (positive queries):")
    print(f"  {'QID':<6} {'Category':<28} {'R@5':>5} {'RR':>5} {'Query'}")
    print("-" * 80)
    for pq in hybrid_ev["per_query"]:
        if not pq.get("should_return_evidence", True):
            continue
        print(
            f"  {pq['query_id']:<6} "
            f"{pq['category']:<28} "
            f"{pq.get('recall@5', 0):>5.2f} "
            f"{pq.get('reciprocal_rank', 0):>5.2f} "
            f"{pq['query'][:45]}"
        )
    print()

    print("Negative query (abstention) results - hybrid:")
    for pq in hybrid_ev["per_query"]:
        if pq.get("should_return_evidence", True):
            continue
        status = "[ABSTAINED]" if pq.get("abstained") else f"[RETURNED {pq.get('results_returned')} result(s)]"
        print(f"  {pq['query_id']}  {status:<20}  {pq['query']}")
    print()

    # Save results
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    output = {
        "evaluation_dataset": str(EVAL_DATASET_PATH),
        "total_queries": len(queries),
        "top_k": TOP_K,
        "evaluations": evaluations,
    }
    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"Results saved to: {RESULTS_PATH}")


if __name__ == "__main__":
    main()
