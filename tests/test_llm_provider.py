"""Tests for LLM/SLM provider layer."""

import os
import pytest

from src.llm.base import LLMProvider
from src.llm.provider import GeminiProvider, LocalSLMProvider, OpenAIProvider, get_llm_provider
from src.llm.schemas import RAGResponse, RAGResponseStatus


class TestLLMProviderBasics:
    """Test LLM provider instantiation and factory."""

    def test_local_slm_instantiation(self):
        provider = LocalSLMProvider()
        assert isinstance(provider, LLMProvider)
        assert provider.name == "local-deterministic-slm"

    def test_factory_defaults_to_local(self, monkeypatch):
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        provider = get_llm_provider()
        assert isinstance(provider, LocalSLMProvider)

    def test_factory_gemini_selection(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "gemini")
        provider = get_llm_provider()
        assert isinstance(provider, GeminiProvider)
        assert "gemini" in provider.name

    def test_factory_openai_selection(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "openai")
        provider = get_llm_provider()
        assert isinstance(provider, OpenAIProvider)
        assert "openai" in provider.name

    def test_local_slm_structured_generation_empty(self):
        provider = LocalSLMProvider()
        prompt = "CLINICAL QUERY: test query\nRETRIEVED ICMR STW EVIDENCE BLOCKS:\n\nINSTRUCTIONS: Answer."
        resp = provider.generate_structured(prompt, RAGResponse)
        assert isinstance(resp, RAGResponse)
        assert resp.abstained is True
        assert resp.status == RAGResponseStatus.INSUFFICIENT_EVIDENCE

    def test_local_slm_structured_generation_with_evidence(self):
        provider = LocalSLMProvider()
        prompt = (
            "CLINICAL QUERY: STEMI aspirin dose\n"
            "RETRIEVED ICMR STW EVIDENCE BLOCKS:\n"
            "[EVIDENCE 1]\n"
            "[ID]: ICMR-CARD-006:medication:0001\n"
            "[Document]: ICMR-CARD-006\n"
            "[Condition]: STEMI\n"
            "[Page]: 1\n"
            "[Section]: Medication\n"
            "[Status]: APPROVED\n"
            "[Content]: Aspirin loading dose 300 mg oral chewable.\n\n"
            "INSTRUCTIONS: Answer."
        )
        resp = provider.generate_structured(prompt, RAGResponse)
        assert isinstance(resp, RAGResponse)
        assert resp.status == RAGResponseStatus.GROUNDED
        assert resp.abstained is False
        assert len(resp.citations) == 1
        assert resp.citations[0].document_id == "ICMR-CARD-006"
        assert resp.citations[0].knowledge_unit_id == "ICMR-CARD-006:medication:0001"
        assert "300 mg" in resp.answer
