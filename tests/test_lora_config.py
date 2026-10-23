"""Tests for LoRA configuration, hyperparameters, and training runner initialization."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.training.config import TrainingConfig
from src.training.trainer import SLMTrainer


def test_lora_config_defaults():
    config = TrainingConfig()
    assert config.base_model == "microsoft/Phi-3.5-mini-instruct"
    assert config.lora_rank == 8
    assert config.lora_alpha == 16
    assert config.lora_dropout == 0.05
    assert "q_proj" in config.target_modules
    assert "v_proj" in config.target_modules
    assert config.num_epochs == 3
    assert config.learning_rate == 2e-4


def test_lora_config_hash_consistency():
    config1 = TrainingConfig(seed=42)
    config2 = TrainingConfig(seed=42)
    config3 = TrainingConfig(seed=99)

    assert config1.compute_hash() == config2.compute_hash()
    assert config1.compute_hash() != config3.compute_hash()


def test_lora_config_serialization(tmp_path: Path):
    config = TrainingConfig(lora_rank=16, lora_alpha=32)
    save_path = tmp_path / "test_config.json"
    config.save(save_path)

    assert save_path.exists()
    loaded = TrainingConfig.from_dict(config.to_dict())
    assert loaded.lora_rank == 16
    assert loaded.lora_alpha == 32


def test_slm_trainer_initialization(tmp_path: Path):
    config = TrainingConfig(output_dir=str(tmp_path))
    trainer = SLMTrainer(config=config)

    assert trainer.run_id.startswith("RUN-")
    assert str(tmp_path) in str(trainer.run_dir)
