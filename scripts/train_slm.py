#!/usr/bin/env python
"""CLI training script for Phase 7 PEFT / LoRA fine-tuning of ICMR STW Small Language Models."""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure src is on python path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.training.config import TrainingConfig
from src.training.trainer import SLMTrainer


def main() -> None:
    print("================================================================================")
    print("PHASE 7: ICMR STW PEFT / LoRA SLM FINE-TUNING RUNNER")
    print("================================================================================")

    config = TrainingConfig()
    print("Initializing training configuration:")
    print(f"  - Base Model       : {config.base_model}")
    print(f"  - Task Type        : {config.task_type}")
    print(f"  - LoRA Rank (r)    : {config.lora_rank}")
    print(f"  - LoRA Alpha       : {config.lora_alpha}")
    print(f"  - Target Modules   : {', '.join(config.target_modules)}")
    print(f"  - Learning Rate    : {config.learning_rate}")
    print(f"  - Epochs           : {config.num_epochs}")
    print(f"  - Config Hash      : {config.compute_hash()[:16]}...")
    print()

    trainer = SLMTrainer(config=config)
    print(f"Starting training run: {trainer.run_id}")
    print(f"Output directory: {trainer.run_dir}")

    metadata = trainer.train()

    print("\nTraining completed successfully!")
    print(f"  - Final Training Loss   : {metadata['final_training_loss']}")
    print(f"  - Final Validation Loss : {metadata['final_validation_loss']}")
    print(f"  - Training Duration     : {metadata['training_duration_seconds']}s")
    print(f"  - LoRA Adapter Saved To : {metadata['adapter_artifact_path']}")

    # Update models/registry.json
    registry_path = Path("models/registry.json")
    registry_path.parent.mkdir(parents=True, exist_ok=True)

    registry_data = {
        "version": "1.0",
        "models": [
            {
                "id": "BASELINE-PHASE6-COMPACT-SLM",
                "base_model": "microsoft/Phi-3.5-mini-instruct",
                "type": "baseline",
                "version": "v1.0",
                "quantization": "Q4_K_M",
                "adapter": None,
                "status": "evaluated_baseline",
                "description": "Phase 6 winning frozen baseline model without fine-tuning."
            },
            {
                "id": f"LORA-{trainer.run_id}",
                "base_model": config.base_model,
                "type": "lora_adapter",
                "version": "v1.0",
                "quantization": "4bit",
                "adapter_path": f"data/training/runs/{trainer.run_id}",
                "status": "candidate",
                "description": "Phase 7 instruction-tuned PEFT LoRA adapter for structured clinical grounding."
            }
        ]
    }

    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(registry_data, f, indent=2)

    print(f"\nUpdated model registry at {registry_path}")
    print("================================================================================")


if __name__ == "__main__":
    main()
