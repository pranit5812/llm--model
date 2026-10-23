"""Multi-specialty benchmark evaluation script for ICMR STW Platform.

Evaluates:
- Specialty routing accuracy
- Production retrieval & grounding rate
- Multi-specialty safe abstention rate (Out of Scope, Quarantined Evidence, Ambiguity, Version Conflict)
- Cross-specialty isolation
- SQLite citation validity
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.knowledge.indexer import KnowledgeIndexer
from src.rag.pipeline import RAGPipeline
from src.retrieval.router import SpecialtyRouter

logging.basicConfig(level=logging.WARNING)


def run_multispecialty_evaluation(
    benchmark_path: Path = Path("data/evaluation/multispecialty_queries.json"),
    db_path: Path = Path("data/knowledge/knowledge.db"),
) -> Dict[str, Any]:
    with open(benchmark_path, "r", encoding="utf-8") as f:
        queries: List[Dict[str, Any]] = json.load(f)

    indexer = KnowledgeIndexer()
    indexer.load()
    pipeline = RAGPipeline(indexer=indexer)
    router = SpecialtyRouter()

    total_queries = len(queries)
    routing_correct = 0
    status_correct = 0
    safe_abstentions = 0
    expected_abstentions = 0
    cross_contamination_count = 0
    citation_valid_count = 0
    grounded_queries = 0

    results_detail = []

    for q in queries:
        qid = q["id"]
        query_text = q["query"]
        expected_spec = q.get("expected_specialty")
        expected_status = q.get("expected_status")

        # 1. Routing check
        detected_spec, confidence, _ = router.route_query(query_text)
        is_ambiguous = router.is_ambiguous(query_text)

        if expected_spec == "AMBIGUOUS":
            routed_ok = is_ambiguous or (detected_spec is None)
        else:
            routed_ok = (detected_spec == expected_spec) or (confidence < 0.3)

        if routed_ok:
            routing_correct += 1

        # 2. Pipeline answer
        response = pipeline.answer(query=query_text)
        actual_status = response.status.value

        # Status check
        if expected_status == "GROUNDED":
            grounded_queries += 1
            status_ok = (actual_status in ["GROUNDED", "PARTIAL"])
            # Citation check
            if response.citations:
                c_valid = all(c.document_id.startswith("ICMR-CARD") for c in response.citations)
                if c_valid:
                    citation_valid_count += 1
        else:
            expected_abstentions += 1
            status_ok = response.abstained and (
                actual_status == expected_status or
                actual_status in ["OUT_OF_SCOPE", "NO_RELIABLE_ICMR_EVIDENCE", "INSUFFICIENT_APPROVED_EVIDENCE", "AMBIGUOUS_SOURCE", "VERSION_CONFLICT"]
            )
            if response.abstained:
                safe_abstentions += 1

            # Cross contamination check: unapproved / out of scope queries must NOT cite Cardiology
            if response.citations and expected_spec != "Cardiology":
                cross_contamination_count += 1

        if status_ok:
            status_correct += 1

        results_detail.append({
            "id": qid,
            "query": query_text,
            "expected_specialty": expected_spec,
            "detected_specialty": detected_spec,
            "expected_status": expected_status,
            "actual_status": actual_status,
            "abstained": response.abstained,
            "citations_count": len(response.citations),
            "status_ok": status_ok,
        })

    routing_acc = (routing_correct / total_queries) * 100.0 if total_queries else 0.0
    status_acc = (status_correct / total_queries) * 100.0 if total_queries else 0.0
    abstention_rate = (safe_abstentions / expected_abstentions) * 100.0 if expected_abstentions else 100.0
    citation_accuracy = (citation_valid_count / grounded_queries) * 100.0 if grounded_queries else 100.0

    return {
        "total_queries": total_queries,
        "routing_accuracy": round(routing_acc, 1),
        "status_accuracy": round(status_acc, 1),
        "safe_abstention_rate": round(abstention_rate, 1),
        "citation_accuracy": round(citation_accuracy, 1),
        "cross_contamination_errors": cross_contamination_count,
        "details": results_detail,
    }


def main():
    print("=" * 70)
    print("ICMR MULTI-SPECIALTY BENCHMARK EVALUATION")
    print("=" * 70)

    res = run_multispecialty_evaluation()

    print(f"\nTotal Queries Evaluated:    {res['total_queries']}")
    print(f"Specialty Routing Accuracy:  {res['routing_accuracy']}%")
    print(f"Status & Intent Accuracy:    {res['status_accuracy']}%")
    print(f"Safe Abstention Rate:        {res['safe_abstention_rate']}%")
    print(f"Citation Verification Rate:  {res['citation_accuracy']}%")
    print(f"Cross-Specialty Violations:  {res['cross_contamination_errors']}")
    print("-" * 70)
    for d in res["details"]:
        status_symbol = "PASS" if d["status_ok"] else "FAIL"
        print(f"[{status_symbol:<4}] {d['id']:<14} | Exp: {d['expected_status']:<28} | Got: {d['actual_status']:<28} | ExpSpec: {str(d['expected_specialty']):<14} | GotSpec: {str(d['detected_specialty']):<14}")
    print("=" * 70)


if __name__ == "__main__":
    main()
