"""Version-controlled LoRA and training configuration for ICMR STW Small Language Models."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class TrainingConfig:
    """Hyperparameters and architectural settings for PEFT / LoRA fine-tuning."""

    base_model: str = "microsoft/Phi-3.5-mini-instruct"
    dataset_version: str = "v1.0-icmr-approved"
    max_seq_length: int = 2048
    learning_rate: float = 2e-4
    batch_size: int = 2
    gradient_accumulation_steps: int = 4
    num_epochs: int = 3
    warmup_ratio: float = 0.05
    weight_decay: float = 0.01

    # LoRA Specific Parameters
    lora_rank: int = 8
    lora_alpha: int = 16
    lora_dropout: float = 0.05
    target_modules: List[str] = field(default_factory=lambda: ["q_proj", "k_proj", "v_proj", "o_proj"])
    bias: str = "none"
    task_type: str = "CAUSAL_LM"

    # Optimization & Hardware
    quantization: str = "4bit"
    mixed_precision: str = "fp16"
    seed: int = 42

    # Paths (relative to workspace root)
    train_dataset_path: str = "data/evaluation/train.json"
    val_dataset_path: str = "data/evaluation/validation.json"
    output_dir: str = "data/training/runs"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> TrainingConfig:
        return cls(**data)

    def compute_hash(self) -> str:
        """Compute deterministic SHA-256 fingerprint of the configuration."""
        dumped = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(dumped.encode("utf-8")).hexdigest()

    def save(self, file_path: Path) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
