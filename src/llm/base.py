"""Abstract Base Class for LLM/SLM Providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional, Type, TypeVar
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(ABC):
    """Abstract interface for LLM/SLM providers.

    Decouples the RAG generation pipeline from any specific model vendor
    or runtime engine (e.g. Gemini, OpenAI, local quantized SLM, mock).
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier."""
        ...

    @abstractmethod
    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Generate free-text completion from prompt and optional system prompt."""
        ...

    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> T:
        """Generate a response parsed and validated against a Pydantic model."""
        ...
