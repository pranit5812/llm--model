# LLM/SLM Provider Abstraction — ICMR STW AI

## 1. Provider Design

The LLM provider abstraction in `src/llm/` is vendor-agnostic and enforces strict separation between application business logic and model vendors.

```
                  LLMProvider (ABC)
                /         |        \
    LocalSLMProvider  GeminiProvider  OpenAIProvider
```

## 2. Supported Providers

### `LocalSLMProvider` (Default)
- **Engine**: In-process deterministic clinical extractor and summarizer.
- **Dependencies**: None (pure Python, zero external API keys, zero network traffic).
- **Use Case**: Offline clinics, test automation, CI/CD pipelines, reproducible benchmarks.
- **Groundedness**: 100% deterministic mapping from retrieved evidence to response.

### `GeminiProvider`
- **Engine**: Google Generative AI REST API (`gemini-1.5-flash`, `gemini-1.5-pro`).
- **Connection**: Direct HTTPS via `httpx` to `generativelanguage.googleapis.com`.
- **Configuration**: Set `LLM_PROVIDER=gemini` and `GEMINI_API_KEY=...` in `.env`.
- **Temperature**: Default `0.0` to minimize variance.

### `OpenAIProvider`
- **Engine**: OpenAI Chat Completions API (`gpt-4o-mini`, `gpt-4o`) or local vLLM/Ollama endpoints.
- **Connection**: Direct HTTPS via `httpx` or `openai` SDK.
- **Configuration**: Set `LLM_PROVIDER=openai` and `OPENAI_API_KEY=...` in `.env`.

## 3. Factory Usage

```python
from src.llm.provider import get_llm_provider

# Automatically selects provider based on LLM_PROVIDER env var
provider = get_llm_provider()
print(provider.name)
```
