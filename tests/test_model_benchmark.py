"""Tests for Phase 6 Model Benchmark and Evaluation Framework."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.evaluation.datasets import BenchmarkDataset
from src.evaluation.metrics import MetricsCalculator, ModelEvaluationScorecard
from src.evaluation.model_benchmark import ModelBenchmark
from src.evaluation.report import BenchmarkReporter
from src.llm.provider import CompactSLMProvider, LocalSLMProvider


def test_benchmark_dataset_loading():
    dataset = BenchmarkDataset()
    assert len(dataset.queries) >= 50
    assert "description" in dataset.metadata

    # Check categories
    summary = dataset.summary()
    assert summary["total_queries"] >= 50
    assert summary["in_scope_queries"] > 0
    assert summary["abstention_queries"] > 0
    assert "STEMI" in summary["categories"]
    assert "Adversarial/prompt-injection questions" in summary["categories"]


def test_dosage_accuracy_calculator():
    # Correct dosage
    acc, hall = MetricsCalculator.calculate_dosage_accuracy(
        "Loading dose of aspirin is 300 mg orally.",
        ["aspirin", "300", "300 mg"],
    )
    assert acc is True
    assert hall == 0

    # Hallucinated unexpected dosage
    acc, hall = MetricsCalculator.calculate_dosage_accuracy(
        "Administer 950 mg of heparin stat.",
        ["aspirin", "300"],
    )
    assert acc is False
    assert hall > 0


def test_model_benchmark_execution():
    dataset = BenchmarkDataset()
    # Test on a small 3-query subset for speed
    mini_dataset = BenchmarkDataset()
    mini_dataset._queries = dataset.queries[:3]

    benchmark = ModelBenchmark(dataset=mini_dataset, top_k=3)
    provider = LocalSLMProvider("test-slm")
    run_result = benchmark.run_benchmark_for_model(provider)

    assert "scorecard" in run_result
    assert "per_query_results" in run_result
    scorecard: ModelEvaluationScorecard = run_result["scorecard"]

    assert scorecard.model_name == "test-slm"
    assert scorecard.total_queries == 3
    assert scorecard.groundedness_rate > 0.0
    assert scorecard.citation_correctness_rate > 0.0


def test_benchmark_reporter_markdown():
    scorecard = ModelEvaluationScorecard(
        model_name="phi-3.5-mini",
        provider="CompactSLMProvider",
        total_queries=50,
        positive_queries=38,
        negative_queries=12,
        groundedness_rate=0.98,
        citation_correctness_rate=1.0,
        citation_completeness_rate=1.0,
        unsupported_claim_rate=0.0,
        abstention_accuracy=1.0,
        schema_validity_rate=1.0,
        retrieval_consistency_rate=0.92,
        dosage_accuracy=0.85,
        timeline_accuracy=0.80,
        contraindication_accuracy=0.90,
        version_handling_accuracy=0.85,
        avg_latency_sec=0.015,
        error_rate=0.0,
        total_citations_generated=150,
        total_citations_verified=150,
        hallucinated_dosages_count=0,
        per_category_accuracy={"STEMI": 1.0},
    )

    table_md = BenchmarkReporter.format_markdown_table([scorecard])
    assert "| **phi-3.5-mini** |" in table_md
    assert "98.0%" in table_md
    assert "100.0%" in table_md
