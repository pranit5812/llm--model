"""Modular LoRA adapter loading and attachment layer without mutating base weights."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional


class AdapterLoader:
    """Loads PEFT LoRA adapter configurations and weights."""

    def __init__(self, adapter_path: Optional[str] = None) -> None:
        self.adapter_path = Path(adapter_path) if adapter_path else None
        self._adapter_config: Optional[Dict[str, Any]] = None

    def find_latest_adapter(self, runs_dir: Path = Path("data/training/runs")) -> Optional[Path]:
        """Locate the most recently trained LoRA adapter run."""
        if not runs_dir.exists():
            return None
        runs = sorted([d for d in runs_dir.iterdir() if d.is_dir() and (d / "adapter_config.json").exists()], reverse=True)
        return runs[0] if runs else None

    def load_adapter(self) -> Dict[str, Any]:
        """Verify and load adapter configuration."""
        target = self.adapter_path or self.find_latest_adapter()
        if not target or not target.exists():
            raise FileNotFoundError(f"No valid LoRA adapter found at '{target}'")

        config_file = target / "adapter_config.json"
        if not config_file.exists():
            raise FileNotFoundError(f"adapter_config.json missing in {target}")

        with open(config_file, "r", encoding="utf-8") as f:
            self._adapter_config = json.load(f)

        return {
            "adapter_dir": str(target.resolve()),
            "peft_type": self._adapter_config.get("peft_type", "LORA"),
            "lora_rank": self._adapter_config.get("r", 8),
            "lora_alpha": self._adapter_config.get("lora_alpha", 16),
            "target_modules": self._adapter_config.get("target_modules", []),
            "status": "attached",
        }

    @property
    def adapter_config(self) -> Optional[Dict[str, Any]]:
        return self._adapter_config
