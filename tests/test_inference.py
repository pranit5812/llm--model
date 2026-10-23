"""Tests for Phase 7 Inference Layer and Provider Switching."""

from __future__ import annotations

import pytest

from src.inference.adapter_loader import AdapterLoader
from src.inference.inference import SLMInferenceEngine
from src.inference.model_loader import ModelLoader
from src.llm.provider import FineTunedSLMProvider, get_llm_provider
from src.llm.schemas import RAGResponse, RAGResponseStatus


def test_model_loader_metadata():
    loader = ModelLoader()
    meta = loader.load_base_model()
    assert meta["architecture"] == "Phi-3.5-mini-instruct"
    assert meta["context_window"] == 4096
    assert loader.is_loaded is True


def test_adapter_loader_finds_latest_adapter():
    loader = AdapterLoader()
    latest = loader.find_latest_adapter()
    assert latest is not None
    assert latest.exists()

    adapter_info = loader.load_adapter()
    assert adapter_info["peft_type"] == "LORA"
    assert adapter_info["status"] == "attached"


def test_inference_engine_baseline_mode():
    engine = SLMInferenceEngine(mode="baseline")
    prompt = (
        "CLINICAL QUERY:\nWhat is the loading dose of aspirin in STEMI?\n\n"
        "RETRIEVED ICMR STW EVIDENCE BLOCKS:\n"
        "[EVIDENCE 1]\n"
        "[ID]: ICMR-CARD-006-KU-001\n"
        "[Document]: ICMR-CARD-006\n"
        "[Condition]: STEMI\n"
        "[Page]: 1\n"
        "[Section]: Loading Dose\n"
        "[Content]: Aspirin loading dose 300 mg orally stat.\n"
        "[Status]: approved\n\n"
        "INSTRUCTIONS:\nSynthesize answer."
    )

    resp = engine.generate_response(prompt)
    assert resp.status == RAGResponseStatus.GROUNDED
    assert resp.abstained is False
    assert len(resp.citations) == 1
    assert "300 mg" in resp.answer


def test_inference_engine_fine_tuned_mode():
    engine = SLMInferenceEngine(mode="fine_tuned")
    prompt = (
        "CLINICAL QUERY:\nWhat is the loading dose of aspirin in STEMI?\n\n"
        "RETRIEVED ICMR STW EVIDENCE BLOCKS:\n"
        "[EVIDENCE 1]\n"
        "[ID]: ICMR-CARD-006-KU-001\n"
        "[Document]: ICMR-CARD-006\n"
        "[Condition]: STEMI\n"
        "[Page]: 1\n"
        "[Section]: Loading Dose\n"
        "[Content]: Aspirin loading dose 300 mg orally stat.\n"
        "[Status]: approved\n\n"
        "INSTRUCTIONS:\nSynthesize answer."
    )

    resp = engine.generate_response(prompt)
    assert resp.status == RAGResponseStatus.GROUNDED
    assert "**ICMR Standard Treatment Workflow Evidence**" in resp.answer
    assert "• **Loading Dose**" in resp.answer
    assert len(resp.citations) == 1


def test_finetuned_provider_factory_selection():
    provider = get_llm_provider(model_mode="fine_tuned")
    assert isinstance(provider, FineTunedSLMProvider)
    assert "fine-tuned-slm:" in provider.name
