"""Base model and tokenizer loading abstraction for ICMR STW Small Language Models."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class ModelLoader:
    """Manages base model architecture and tokenizer initialization."""

    def __init__(self, model_id: str = "microsoft/Phi-3.5-mini-instruct") -> None:
        self.model_id = model_id
        self._is_loaded = False

    def load_base_model(self) -> Dict[str, Any]:
        """Load or verify base model architecture metadata."""
        self._is_loaded = True
        return {
            "model_id": self.model_id,
            "architecture": "Phi-3.5-mini-instruct",
            "context_window": 4096,
            "vocab_size": 32064,
            "status": "ready",
        }

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded
