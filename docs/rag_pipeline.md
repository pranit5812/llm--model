# RAG Pipeline Design — ICMR STW AI

## 1. Pipeline Execution Lifecycle

The Grounded RAG Pipeline is implemented in `src/rag/pipeline.py` and coordinates eight distinct stages:

### Stage 1: Adversarial & Safety Inspection
- Detects prompt injection attempts (e.g. "ignore previous instructions", "system override").
- Detects personal prescribing inquiries ("what pills should I take") to attach immediate emergency advisories.

### Stage 2: Domain Scope Validation
- `src/retrieval/scope.py` determines if the query contains cardiovascular domain anchors or targets out-of-scope non-cardiology conditions (e.g. dengue, pneumonia, orthopaedics).
- Queries without relevant evidence safely abstain immediately without triggering unnecessary LLM inference.

### Stage 3: Hybrid Retrieval & Reranking
- Uses Reciprocal Rank Fusion (RRF, $k=60$) over BM25 and TF-IDF semantic matrices.
- Token overlap reranker rescores top candidates based on exact clinical keyword matches.

### Stage 4: Evidence Selection & Context Formatting
- Deduplicates units by `unit_id`.
- Selects top-$K$ units (default $K=5$).
- Excludes `needs_review` items.
- Formats units into explicit numbered `[EVIDENCE {i}]` blocks.

### Stage 5: Structured LLM Generation
- Prompts LLM using `SYSTEM_PROMPT_V1` and structured JSON schema (`RAGResponse`).

### Stage 6: SQLite Citation Verification
- `src/llm/citation_validator.py` confirms that every cited knowledge unit actually exists in `knowledge.db`, was present in the candidate pool, and matches the document ID and page number.

### Stage 7: Grounding & Version Consistency Validation
- `src/rag/response_validator.py` scans the answer for dosage numbers and verifies them against the source evidence.
- Flags version discrepancies if both consolidated and individual STWs are retrieved.

### Stage 8: Delivery
- Final response packaged as `RAGResponse` and returned to caller / REST API.
