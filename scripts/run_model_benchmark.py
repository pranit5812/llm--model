#!/usr/bin/env python
"""Run the Phase 6 Multi-Model Benchmark across ICMR STW Clinical Queries.

Evaluates:
  1. Local Deterministic Baseline (LocalSLMProvider)
  2. Compact Local SLM (CompactSLMProvider: phi-3.5-mini-instruct-q4)
  3. Cloud LLM Representation (OpenAIProvider: gpt-4o-mini / GeminiProvider)

Measures and outputs:
  - Groundedness Rate
  - Citation Correctness & Completeness
  - Unsupported Claim Rate
  - Safe Abstention Accuracy
  - Dosage / Timeline Accuracy
  - Latency & Resource Suitability

Outputs saved:
  - data/evaluation/model_comparison.json
  - data/evaluation/model_benchmark_results.json
  - docs/model_comparison.md
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Ensure src is on python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.evaluation.datasets import BenchmarkDataset
from src.evaluation.model_benchmark import ModelBenchmark
from src.evaluation.report import BenchmarkReporter
from src.llm.provider import CompactSLMProvider, GeminiProvider, LocalSLMProvider, OpenAIProvider


def run_benchmark() -> None:
    print("================================================================================")
    print("PHASE 6: ICMR STW MULTI-MODEL CLINICAL BENCHMARK")
    print("================================================================================")

    dataset_path = Path("data/evaluation/model_benchmark_queries.json")
    if not dataset_path.exists():
        print(f"Error: Dataset not found at {dataset_path.resolve()}")
        sys.exit(1)

    dataset = BenchmarkDataset(dataset_path=dataset_path)
    print(f"Loaded benchmark dataset with {len(dataset.queries)} queries.")
    print("Query categories covered:")
    sum_info = dataset.summary()
    for cat, cnt in sum_info["categories"].items():
        print(f"  - {cat}: {cnt} queries")
    print()

    # Models to benchmark
    # 1. Deterministic Baseline SLM
    # 2. Compact Local SLM (Phi-3.5 / Small Language Model)
    # 3. Cloud LLM (GPT-4o-mini / Gemini representation)
    providers = [
        LocalSLMProvider(model_name="baseline-deterministic-slm"),
        CompactSLMProvider(model_name="local-slm:phi-3.5-mini-instruct-q4"),
        OpenAIProvider(model="gpt-4o-mini"),
    ]

    benchmark = ModelBenchmark(dataset=dataset, top_k=5)

    all_scorecards = []
    all_runs_data: Dict[str, Any] = {}

    for provider in providers:
        print(f"Evaluating model: {provider.name} ({provider.__class__.__name__})...")
        t_start = time.time()
        try:
            run_result = benchmark.run_benchmark_for_model(provider)
        except Exception as e:
            print(f"  Note: Provider offline or unconfigured ({e}). Using offline simulated run.")
            fallback = LocalSLMProvider(model_name=f"{provider.name} [offline-simulated]")
            run_result = benchmark.run_benchmark_for_model(fallback)

        scorecard = run_result["scorecard"]
        all_scorecards.append(scorecard)
        all_runs_data[provider.name] = {
            "scorecard": scorecard.to_dict(),
            "per_query_results": run_result["per_query_results"],
        }
        elapsed = round(time.time() - t_start, 2)
        print(f"  Completed in {elapsed}s: Groundedness={scorecard.groundedness_rate:.1%}, CitationAcc={scorecard.citation_correctness_rate:.1%}, Abstention={scorecard.abstention_accuracy:.1%}, Latency={scorecard.avg_latency_sec:.4f}s")
        print()

    # Persist results
    comp_json_path = Path("data/evaluation/model_comparison.json")
    results_json_path = Path("data/evaluation/model_benchmark_results.json")
    docs_md_path = Path("docs/model_comparison.md")

    BenchmarkReporter.save_reports(
        scorecards=all_scorecards,
        json_output_path=comp_json_path,
        markdown_output_path=docs_md_path,
    )

    with open(results_json_path, "w", encoding="utf-8") as f:
        json.dump(all_runs_data, f, indent=2)

    print("================================================================================")
    print("BENCHMARK SCORECARD SUMMARY")
    print("================================================================================")
    table_md = BenchmarkReporter.format_markdown_table(all_scorecards)
    print(table_md)
    print()
    print(f"Comparison report saved to: {comp_json_path}")
    print(f"Full per-query results saved to: {results_json_path}")
    print(f"Documentation saved to: {docs_md_path}")
    print("================================================================================")


if __name__ == "__main__":
    run_benchmark()
