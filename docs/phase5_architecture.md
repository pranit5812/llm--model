# Phase 5 Architecture — ICMR STW Grounded LLM/SLM RAG System

## 1. System Overview

Phase 5 establishes the **Grounded Clinical Decision Support Layer** on top of the canonical ICMR Cardiology Standard Treatment Workflows.

The LLM/SLM in this architecture functions solely as an **evidence-to-natural-language synthesizer**. It is strictly constrained by design from acting as an autonomous source of medical knowledge.

```
                  +-------------------------+
                  |       User Query        |
                  +-------------------------+
                               |
                               v
                  +-------------------------+
                  |  Prompt Injection Guard |  (src/llm/safety.py)
                  +-------------------------+
                               |
                               v
                  +-------------------------+
                  |   Clinical Scope Gate   |  (src/retrieval/scope.py)
                  +-------------------------+
                               |
                               v
                  +-------------------------+
                  |   Hybrid Retrieval RRF  |  (BM25 + TF-IDF, src/retrieval/hybrid.py)
                  +-------------------------+
                               |
                               v
                  +-------------------------+
                  |     Token Reranker      |  (src/retrieval/reranker.py)
                  +-------------------------+
                               |
                               v
                  +-------------------------+
                  |     Context Builder     |  (Strict [EVIDENCE] blocks, review units excluded)
                  +-------------------------+
                               |
                               v
                  +-------------------------+
                  |   LLM / SLM Provider    |  (src/llm/provider.py: LocalSLM, Gemini, OpenAI)
                  +-------------------------+
                               |
                               v
                  +-------------------------+
                  |   Citation Validator    |  (Verifies all citations in SQLite knowledge.db)
                  +-------------------------+
                               |
                               v
                  +-------------------------+
                  |   Grounding Validator   |  (Verifies dosage & version consistency)
                  +-------------------------+
                               |
                               v
                  +-------------------------+
                  | Final Grounded Response |
                  +-------------------------+
```

---

## 2. Core Architectural Guarantees

1. **Deterministic Authority**: All clinical claims, dosages, investigations, and criteria originate exclusively from official ICMR STW documents.
2. **Review-Content Exclusion**: Units with `requires_manual_review = True` (such as complex tables or flowchart snippets pending human verification) are filtered out prior to context construction.
3. **Double Verification**: Citations are verified against SQLite database records. If a citation references an unseen or nonexistent unit ID, it is stripped or triggers abstention.
4. **Offline Capability**: The default `LocalSLMProvider` requires zero cloud API keys, network calls, or GPU resources, ensuring reproducible evaluation and air-gapped clinical operation.
5. **No Credential Leakage**: Diagnostic/debug modes expose only non-sensitive latency and validation metrics. Database paths, connection strings, and API keys are completely shielded.
