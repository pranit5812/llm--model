"""Tests for Phase 7 Training Dataset Generation, Provenance, and Data Leakage Prevention."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.training.data_split import DatasetSplitter
from src.training.dataset_generator import TrainingDatasetGenerator


def test_training_dataset_uses_only_approved_units():
    generator = TrainingDatasetGenerator()
    approved_units = generator.get_approved_units()

    # All approved units must have requires_manual_review = 0
    assert len(approved_units) == 426

    examples = generator.generate_all_examples()
    assert len(examples) > 100

    # Ensure every single generated example has review_status == "approved"
    for ex in examples:
        assert ex["review_status"] == "approved"
        assert "training_example_id" in ex
        assert "messages" in ex
        assert len(ex["messages"]) == 3
        assert ex["messages"][0]["role"] == "system"
        assert ex["messages"][1]["role"] == "user"
        assert ex["messages"][2]["role"] == "assistant"


def test_training_examples_provenance_integrity():
    generator = TrainingDatasetGenerator()
    examples = generator.generate_all_examples()

    # Check that clinical examples carry full provenance
    clinical_ex = [e for e in examples if e["category"] != "safe_abstention"]
    for ex in clinical_ex:
        assert len(ex["knowledge_unit_ids"]) > 0
        assert ex["condition"] != ""
        assert ex["document_id"] != ""
        assert ex["source_page"] >= 1
        assert ex["source_section"] != ""


def test_dataset_splitting_and_leakage_prevention(tmp_path: Path):
    generator = TrainingDatasetGenerator()
    examples = generator.generate_all_examples()

    train_data, val_data, test_data = DatasetSplitter.split_dataset(
        examples,
        train_ratio=0.70,
        val_ratio=0.15,
        test_ratio=0.15,
        seed=42,
    )

    # Check partition counts
    assert len(train_data) > len(val_data)
    assert len(train_data) > len(test_data)
    assert len(train_data) + len(val_data) + len(test_data) == len(examples)

    # Zero leakage check: no training example ID in test or validation
    train_ids = set(e["training_example_id"] for e in train_data)
    val_ids = set(e["training_example_id"] for e in val_data)
    test_ids = set(e["training_example_id"] for e in test_data)

    assert len(train_ids & test_ids) == 0
    assert len(train_ids & val_ids) == 0
    assert len(val_ids & test_ids) == 0

    # Verify saving and hashing
    summary = DatasetSplitter.save_splits(train_data, val_data, test_data, output_dir=tmp_path)
    assert summary["train_count"] == len(train_data)
    assert "train_sha256" in summary["hashes"]
