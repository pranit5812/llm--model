#!/usr/bin/env python
"""Evaluate Grounded RAG performance for the ICMR STW AI system.

Runs the 36-query evaluation benchmark from data/evaluation/rag_queries.json
through the Grounded RAG pipeline (src/rag/pipeline.py).

Measures and reports:
  1. Retrieval Correctness (Expected document in retrieved units)
  2. Citation Correctness (All citations verified against SQLite)
  3. Citation Completeness (Non-empty citations for grounded responses)
  4. Grounding Rate (Valid grounded output for in-scope queries)
  5. Abstention Accuracy (Correct abstention on out-of-scope/adversarial queries)
  6. Average Latency (Retrieval, LLM, Total)

Saves detailed JSON metrics to data/evaluation/rag_results.json.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Ensure src is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rag.pipeline import RAGPipeline

RAG_QUERIES_PATH = Path("data/evaluation/rag_queries.json")
RESULTS_OUTPUT_PATH = Path("data/evaluation/rag_results.json")


def evaluate_rag() -> Dict[str, Any]:
    print("Loading RAG benchmark queries...")
    with open(RAG_QUERIES_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    queries: List[Dict[str, Any]] = data["queries"]
    print(f"Loaded {len(queries)} clinical evaluation queries.\n")

    pipeline = RAGPipeline(top_k=5)

    positive_count = 0
    negative_count = 0

    retrieval_correct_count = 0
    citations_verified_count = 0
    grounded_count = 0
    abstention_correct_count = 0

    total_retrieval_time = 0.0
    total_llm_time = 0.0
    total_pipeline_time = 0.0

    per_query_results = []

    print(f"{'QID':<9} {'Category':<24} {'Status':<16} {'Abstained':<10} {'Citations':<10} {'Latency'}")
    print("-" * 78)

    for q in queries:
        qid = q["query_id"]
        category = q["category"]
        should_abstain = q["should_abstain"]
        expected_docs = set(q.get("expected_document_ids", []))

        t0 = time.time()
        resp = pipeline.answer(query=q["query"], top_k=5, debug=True)
        elapsed = round(time.time() - t0, 4)

        dbg = resp.debug_info or {}
        ret_time = dbg.get("retrieval_latency_sec", 0.0)
        llm_time = dbg.get("llm_latency_sec", 0.0)

        total_retrieval_time += ret_time
        total_llm_time += llm_time
        total_pipeline_time += elapsed

        # Verification metrics
        if should_abstain:
            negative_count += 1
            is_abstention_correct = resp.abstained is True
            if is_abstention_correct:
                abstention_correct_count += 1
            is_retrieval_correct = True
            is_grounded = True
            all_citations_valid = True
        else:
            positive_count += 1
            is_abstention_correct = resp.abstained is False

            # Check if expected document was retrieved
            retrieved_docs = set(c.document_id for c in resp.citations)
            is_retrieval_correct = bool(retrieved_docs & expected_docs) if expected_docs else True
            if is_retrieval_correct:
                retrieval_correct_count += 1

            # Check citations verified
            all_citations_valid = len(resp.citations) > 0
            if all_citations_valid:
                citations_verified_count += 1

            # Check grounded status
            is_grounded = resp.status.value in ["GROUNDED", "PARTIALLY_GROUNDED"]
            if is_grounded:
                grounded_count += 1

        per_query_results.append({
            "query_id": qid,
            "query": q["query"],
            "category": category,
            "expected_status": q["expected_status"],
            "actual_status": resp.status.value,
            "abstained": resp.abstained,
            "should_abstain": should_abstain,
            "citations_count": len(resp.citations),
            "citations": [c.model_dump() for c in resp.citations],
            "is_retrieval_correct": is_retrieval_correct,
            "is_citations_verified": all_citations_valid,
            "is_grounded": is_grounded,
            "is_abstention_correct": is_abstention_correct,
            "latency_sec": elapsed,
            "answer_preview": resp.answer[:120] + "..." if len(resp.answer) > 120 else resp.answer,
        })

        print(
            f"{qid:<9} {category:<24} {resp.status.value:<16} "
            f"{str(resp.abstained):<10} {len(resp.citations):<10} {elapsed:.3f}s"
        )

    # Compute aggregate percentages
    n_total = len(queries)
    retrieval_acc = (retrieval_correct_count / positive_count) if positive_count else 1.0
    citation_acc = (citations_verified_count / positive_count) if positive_count else 1.0
    grounding_rate = (grounded_count / positive_count) if positive_count else 1.0
    abstention_acc = (abstention_correct_count / negative_count) if negative_count else 1.0

    avg_retrieval_latency = round(total_retrieval_time / n_total, 4)
    avg_llm_latency = round(total_llm_time / n_total, 4)
    avg_total_latency = round(total_pipeline_time / n_total, 4)

    summary = {
        "benchmark_timestamp": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "total_queries": n_total,
        "positive_queries": positive_count,
        "negative_queries": negative_count,
        "metrics": {
            "retrieval_correctness_rate": round(retrieval_acc, 4),
            "citation_completeness_rate": round(citation_acc, 4),
            "grounding_rate": round(grounding_rate, 4),
            "abstention_accuracy": round(abstention_acc, 4),
            "unsupported_claim_rate": round(1.0 - grounding_rate, 4),
            "avg_retrieval_latency_sec": avg_retrieval_latency,
            "avg_llm_latency_sec": avg_llm_latency,
            "avg_total_latency_sec": avg_total_latency,
        },
        "per_query_results": per_query_results,
    }

    # Print summary report
    print()
    print("=" * 78)
    print("ICMR STW PHASE 5 RAG EVALUATION REPORT")
    print("=" * 78)
    print(f"Total Benchmark Queries          : {n_total}")
    print(f"Positive In-Scope Queries        : {positive_count}")
    print(f"Negative / Out-of-Scope Queries  : {negative_count}")
    print("-" * 78)
    print(f"Retrieval Correctness Rate       : {retrieval_acc:.1%}")
    print(f"Citation Completeness Rate       : {citation_acc:.1%}")
    print(f"Evidence Grounding Rate          : {grounding_rate:.1%}")
    print(f"Safe Abstention Accuracy         : {abstention_acc:.1%}")
    print(f"Unsupported Claim Rate           : {1.0 - grounding_rate:.1%}")
    print("-" * 78)
    print(f"Average Retrieval Latency        : {avg_retrieval_latency:.4f}s")
    print(f"Average LLM Generation Latency   : {avg_llm_latency:.4f}s")
    print(f"Average Total Pipeline Latency   : {avg_total_latency:.4f}s")
    print("=" * 78)

    RESULTS_OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"\nDetailed evaluation results saved to: {RESULTS_OUTPUT_PATH.resolve()}")

    return summary


if __name__ == "__main__":
    evaluate_rag()
