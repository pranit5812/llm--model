"""Tests for Catastrophic Safety Regression and Dynamic Knowledge Retention."""

from __future__ import annotations

import pytest

from src.evaluation.regression_tests import RegressionTestRunner
from src.llm.provider import CompactSLMProvider, FineTunedSLMProvider


def test_catastrophic_regression_suite_baseline():
    provider = CompactSLMProvider(model_name="phi-3.5-mini-instruct-q4")
    suite = RegressionTestRunner.run_regression_suite(provider)

    assert suite["all_passed"] is True
    assert suite["pass_rate"] == 1.0
    assert suite["passed_scenarios"] == 10


def test_catastrophic_regression_suite_finetuned():
    provider = FineTunedSLMProvider(model_name="phi-3.5-mini-instruct-lora")
    suite = RegressionTestRunner.run_regression_suite(provider)

    assert suite["all_passed"] is True
    assert suite["pass_rate"] == 1.0
    assert suite["passed_scenarios"] == 10


def test_dynamic_evidence_retention_not_memorized():
    """Verify that fine-tuned SLM strictly follows provided dynamic evidence instead of memorized static weights."""
    provider = FineTunedSLMProvider(model_name="phi-3.5-mini-instruct-lora")
    res = RegressionTestRunner.run_knowledge_retention_test(provider)

    assert res["passed"] is True
    assert res["evidence_a_response_contains_300"] is True
    assert res["evidence_b_response_contains_600"] is True
