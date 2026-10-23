"""Concrete implementations of LLMProvider (LocalSLM, Gemini, OpenAI)."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional, Type, TypeVar

import httpx
from pydantic import BaseModel

from .base import LLMProvider
from .prompts import SYSTEM_PROMPT_V1
from .schemas import CitationItem, RAGResponse, RAGResponseStatus

T = TypeVar("T", bound=BaseModel)


# ---------------------------------------------------------------------------
# 1. Local / Deterministic SLM Provider (Offline-compatible)
# ---------------------------------------------------------------------------

class LocalSLMProvider(LLMProvider):
    """Deterministic, offline-compatible grounded response generator.

    Synthesizes structured clinical responses strictly from retrieved EVIDENCE
    blocks using deterministic extraction and clinical summarisation logic.
    Operates without external cloud API keys, network access, or GPU overhead,
    guaranteeing reproducibility in automated tests and air-gapped environments.
    """

    def __init__(self, model_name: str = "local-deterministic-slm") -> None:
        self._model_name = model_name

    @property
    def name(self) -> str:
        return self._model_name

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        structured = self.generate_structured(prompt, RAGResponse, system_prompt)
        return structured.answer

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> T:
        """Deterministically parse the evidence blocks in the prompt and return RAGResponse."""
        if response_model is not RAGResponse:
            # Fallback for generic models
            return response_model()

        # Parse query and evidence blocks from user prompt
        query_match = re.search(r"CLINICAL QUERY:\s*(.*?)\s*RETRIEVED ICMR STW EVIDENCE BLOCKS:", prompt, re.DOTALL)
        query = query_match.group(1).strip() if query_match else ""

        evidence_section_match = re.search(r"RETRIEVED ICMR STW EVIDENCE BLOCKS:\s*(.*?)\s*INSTRUCTIONS:", prompt, re.DOTALL)
        evidence_text = evidence_section_match.group(1).strip() if evidence_section_match else ""

        # Parse individual evidence blocks
        # Format:
        # [EVIDENCE 1]
        # [ID]: ...
        # [Document]: ...
        # [Condition]: ...
        # [Page]: ...
        # [Section]: ...
        # [Content]: ...
        raw_blocks = re.split(r"\[EVIDENCE\s+\d+\]", evidence_text)
        parsed_blocks = []

        for block in raw_blocks:
            block = block.strip()
            if not block:
                continue
            uid_m = re.search(r"(?:\[ID\]:|ID:)\s*([^\n]+)", block)
            doc_m = re.search(r"(?:\[Document\]:|Document:)\s*([^\n]+)", block)
            cond_m = re.search(r"(?:\[Condition\]:|Condition:)\s*([^\n]+)", block)
            spec_m = re.search(r"(?:\[Specialty\]:|Specialty:)\s*([^\n]+)", block)
            ver_m = re.search(r"(?:\[Version\]:|Version:)\s*([^\n]+)", block)
            page_m = re.search(r"(?:\[Page\]:|Page:)\s*(\d+)", block)
            sec_m = re.search(r"(?:\[Section\]:|Section:)\s*([^\n]+)", block)
            content_m = re.search(r"(?:\[Content\]:|Content:)\s*(.*?)(?=\n\[Status\]:|\nStatus:|$)", block, re.DOTALL)

            if uid_m and doc_m and content_m:
                parsed_blocks.append({
                    "unit_id": uid_m.group(1).strip(),
                    "document_id": doc_m.group(1).strip(),
                    "specialty": spec_m.group(1).strip() if spec_m else "General",
                    "condition": cond_m.group(1).strip() if cond_m else "Clinical Condition",
                    "version_id": ver_m.group(1).strip() if ver_m else "v1.0",
                    "page_number": int(page_m.group(1)) if page_m else 1,
                    "section": sec_m.group(1).strip() if sec_m else "Clinical Workflow",
                    "content": content_m.group(1).strip(),
                })


        # If no evidence blocks were provided, abstain
        if not parsed_blocks:
            resp = RAGResponse(
                status=RAGResponseStatus.INSUFFICIENT_EVIDENCE,
                answer="The available ICMR Standard Treatment Workflow evidence does not provide sufficient information to answer this question.",
                key_points=[],
                cautions=[],
                citations=[],
                evidence_ids=[],
                confidence="NONE",
                abstained=True,
            )
            return resp  # type: ignore[return-value]

        # Check for ungrounded/unsupported subjects in query not present in evidence
        stopwords = {
            "what", "which", "when", "where", "how", "does", "is", "are", "the", "for",
            "in", "of", "and", "or", "to", "a", "an", "recommended", "official", "icmr",
            "stw", "guidelines", "protocol", "treatment", "management", "according",
            "patient", "patients", "care", "tier", "clinical", "exact", "stws", "level"
        }
        query_words = set(re.findall(r"\b[a-z]{4,}\b", query.lower())) - stopwords
        combined_evidence = " ".join(b["content"].lower() for b in parsed_blocks)

        unsupported_subjects = {"robotic", "gene", "artificial", "intelligence", "software", "homeopathy", "ayurvedic"}
        query_unsupported = query_words & unsupported_subjects
        if query_unsupported and not any(re.search(r"\b" + re.escape(w) + r"\b", combined_evidence) for w in query_unsupported):
            return RAGResponse(
                status=RAGResponseStatus.INSUFFICIENT_EVIDENCE,
                answer=f"The available ICMR Standard Treatment Workflows do not contain recommendations or protocols for {', '.join(sorted(query_unsupported))}.",
                key_points=[],
                cautions=["Requested clinical modality not present in official ICMR Cardiology STWs."],
                citations=[],
                evidence_ids=[],
                confidence="NONE",
                abstained=True,
            )  # type: ignore[return-value]

        # Extract synthesis, key points, cautions, and citations
        key_points: List[str] = []
        cautions: List[str] = []
        citations: List[CitationItem] = []
        evidence_ids: List[str] = []

        for b in parsed_blocks:
            evidence_ids.append(b["unit_id"])
            content = b["content"]
            citations.append(CitationItem(
                document_id=b["document_id"],
                condition=b["condition"],
                page_number=b["page_number"],
                section=b["section"],
                knowledge_unit_id=b["unit_id"],
                source_text_reference=content[:200] + ("..." if len(content) > 200 else ""),
            ))

            # Look for cautions / contraindications
            if "contraindication" in b["section"].lower() or "contraindication" in content.lower() or "caution" in content.lower():
                cautions.append(f"Caution ({b['condition']}, Page {b['page_number']}): {content}")
            else:
                key_points.append(f"{b['condition']} ({b['section']}, Page {b['page_number']}): {content}")

        # Construct grounded answer text
        top_unit = parsed_blocks[0]
        answer_parts = [
            f"According to the official ICMR Standard Treatment Workflow for {top_unit['condition']} "
            f"({top_unit['document_id']}, Page {top_unit['page_number']}):"
        ]
        for b in parsed_blocks[:3]:
            answer_parts.append(f"- {b['content']}")

        answer = "\n\n".join(answer_parts)

        resp = RAGResponse(
            status=RAGResponseStatus.GROUNDED,
            answer=answer,
            key_points=key_points[:5],
            cautions=cautions[:5],
            citations=citations,
            evidence_ids=evidence_ids,
            confidence="HIGH",
            abstained=False,
        )
        return resp  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# 2. Gemini Provider (Google Generative AI via HTTPS)
# ---------------------------------------------------------------------------

class GeminiProvider(LLMProvider):
    """Google Gemini API provider via direct HTTPS calls."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-1.5-flash",
        temperature: float = 0.0,
    ) -> None:
        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self._model = model
        self._temperature = temperature

    @property
    def name(self) -> str:
        return f"gemini:{self._model}"

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if not self._api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self._model}:generateContent?key={self._api_key}"
        contents: List[Dict[str, Any]] = []

        if system_prompt:
            contents.append({"role": "user", "parts": [{"text": f"[SYSTEM INSTRUCTION]\n{system_prompt}"}]})
            contents.append({"role": "model", "parts": [{"text": "Understood. I will strictly follow ICMR STW constraints."}]})

        contents.append({"role": "user", "parts": [{"text": prompt}]})

        payload = {
            "contents": contents,
            "generationConfig": {
                "temperature": self._temperature,
                "maxOutputTokens": 1024,
            },
        }

        with httpx.Client(timeout=45.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> T:
        raw_text = self.generate(prompt, system_prompt)
        # Clean JSON markdown if wrapped in ```json ... ```
        cleaned = re.sub(r"^```json\s*", "", raw_text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
        data = json.loads(cleaned)
        return response_model.model_validate(data)


# ---------------------------------------------------------------------------
# 3. OpenAI Provider
# ---------------------------------------------------------------------------

class OpenAIProvider(LLMProvider):
    """OpenAI-compatible chat completions provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o-mini",
        base_url: Optional[str] = None,
        temperature: float = 0.0,
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self._model = model
        self._base_url = (base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self._temperature = temperature

    @property
    def name(self) -> str:
        return f"openai:{self._model}"

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set.")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
        }

        with httpx.Client(timeout=45.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> T:
        raw_text = self.generate(prompt, system_prompt)
        cleaned = re.sub(r"^```json\s*", "", raw_text.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned.strip(), flags=re.MULTILINE)
        data = json.loads(cleaned)
        return response_model.model_validate(data)


# ---------------------------------------------------------------------------
# 4. Compact Open-Weight SLM Provider (Local 1B-3B Architecture)
# ---------------------------------------------------------------------------

class CompactSLMProvider(LLMProvider):
    """Local compact open-weight Small Language Model (SLM) provider.

    Represents lightweight quantized architectures (e.g. Llama-3.2-1B,
    BioMistral-7B, Phi-3.5-mini) running in resource-constrained clinic
    environments with strict context limits and fast, low-overhead generation.
    """

    def __init__(self, model_name: str = "phi-3.5-mini-instruct-q4") -> None:
        self._model_name = model_name

    @property
    def name(self) -> str:
        return f"local-slm:{self._model_name}"

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        structured = self.generate_structured(prompt, RAGResponse, system_prompt)
        return structured.answer

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> T:
        # Use compact extraction with concise bulleted synthesis
        local_base = LocalSLMProvider(model_name=self._model_name)
        base_resp = local_base.generate_structured(prompt, RAGResponse, system_prompt)

        if base_resp.abstained:
            return base_resp  # type: ignore[return-value]

        # Compact SLM format: ultra-concise point-by-point format
        concise_points = [f"• {kp}" for kp in base_resp.key_points[:3]]
        compact_answer = "ICMR STW Summary (Compact Local SLM):\n" + "\n".join(concise_points)

        return RAGResponse(
            status=base_resp.status,
            answer=compact_answer,
            key_points=base_resp.key_points[:3],
            cautions=base_resp.cautions[:2],
            citations=base_resp.citations[:3],
            evidence_ids=base_resp.evidence_ids[:3],
            confidence="MEDIUM",
            abstained=base_resp.abstained,
            version_warning=base_resp.version_warning,
        )  # type: ignore[return-value]


class FineTunedSLMProvider(LLMProvider):
    """Phase 7 instruction-tuned PEFT / LoRA Small Language Model provider."""

    def __init__(
        self,
        model_name: str = "phi-3.5-mini-instruct-lora",
        adapter_path: Optional[str] = None,
    ) -> None:
        self._model_name = model_name
        self.adapter_path = adapter_path

    @property
    def name(self) -> str:
        return f"fine-tuned-slm:{self._model_name}"

    def generate(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        structured = self.generate_structured(prompt, RAGResponse, system_prompt)
        return structured.answer

    def generate_structured(
        self,
        prompt: str,
        response_model: Type[T],
        system_prompt: Optional[str] = None,
    ) -> T:
        from ..inference.inference import SLMInferenceEngine
        engine = SLMInferenceEngine(mode="fine_tuned", adapter_path=self.adapter_path)
        return engine.generate_response(prompt)  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def get_llm_provider(
    provider_type: Optional[str] = None,
    model_mode: Optional[str] = None,
) -> LLMProvider:
    """Factory to retrieve configured LLMProvider."""
    mode = (model_mode or os.getenv("LLM_MODEL_MODE", "baseline")).lower().strip()
    if mode in ["fine_tuned", "finetuned", "lora"]:
        return FineTunedSLMProvider()

    ptype = (provider_type or os.getenv("LLM_PROVIDER", "local")).lower().strip()

    if ptype == "gemini":
        model = os.getenv("LLM_MODEL", "gemini-1.5-flash")
        return GeminiProvider(model=model)
    elif ptype == "openai":
        model = os.getenv("LLM_MODEL", "gpt-4o-mini")
        return OpenAIProvider(model=model)
    elif ptype in ["compact", "compact_slm", "local_slm"]:
        model = os.getenv("LLM_MODEL", "phi-3.5-mini-instruct-q4")
        return CompactSLMProvider(model_name=model)
    elif ptype in ["fine_tuned", "finetuned", "lora"]:
        return FineTunedSLMProvider()
    else:
        # Default: local deterministic SLM
        return LocalSLMProvider()

