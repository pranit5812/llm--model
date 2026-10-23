# Phase 6 Architecture: Real SLM/LLM Evaluation & Clinical Review Workflow

## 1. System Overview

Phase 6 implements two foundational capabilities for the ICMR Standard Treatment Workflow (STW) AI system:

```
                               ┌───────────────────────────────────────────────┐
                               │       ICMR STW OFFICIAL CORPUS (7 PDFs)       │
                               └───────────────────────┬───────────────────────┘
                                                       │
                           ┌───────────────────────────┴───────────────────────────┐
                           │                                                       │
                           ▼                                                       ▼
            ┌─────────────────────────────┐                         ┌─────────────────────────────┐
            │   PRODUCTION RETRIEVAL      │                         │     CLINICAL REVIEW QUEUE   │
            │   (426 Verified Units)      │                         │     (167 Flagged Units)     │
            └──────────────┬──────────────┘                         └──────────────┬──────────────┘
                           │                                                       │
            ┌──────────────▼──────────────┐                         ┌──────────────▼──────────────┐
            │     GROUNDED RAG PIPELINE   │                         │   HUMAN-IN-THE-LOOP WORKBENCH│
            │  (BM25 + TF-IDF + Scope +   │                         │  • Priority Queue (H/M/L)   │
            │   Reranker + Citations)     │                         │  • Immutable Source Text    │
            └──────────────┬──────────────┘                         │  • Clinician Decisions      │
                           │                                        │  • Immutable Audit Trail    │
                           │                                        └──────────────┬──────────────┘
            ┌──────────────▼──────────────┐                                        │
            │   MULTI-MODEL BENCHMARK     │                                        │
            │ • Baseline Deterministic    │                         ┌──────────────▼──────────────┐
            │ • Compact Local SLM (Phi)   │                         │   Promoted to Production    │
            │ • Cloud LLM (GPT / Gemini)  │                         │   (requires_manual_review=0)│
            │ (52 Queries across 17 cats) │                         └─────────────────────────────┘
            └─────────────────────────────┘
```

---

## 2. Objective A: Real SLM / LLM Model Evaluation Framework

### 2.1 Principle of Strictly Identical Retrieval Context
To ensure scientific fairness and eliminate retrieval confounding:
1. Every candidate model is evaluated on the exact same retrieved evidence blocks (top-k = 5).
2. Every model is fed the exact same system instructions (`SYSTEM_PROMPT_V1`) and temperature (`0.0`).
3. No model is granted external web search or fine-tuned prior knowledge.
4. Output schema adherence, citation verification against SQLite (`knowledge.db`), and dosage grounding validation are applied identically to all models.

### 2.2 Model Architecture Triad
1. **Local Deterministic Baseline (`LocalSLMProvider`)**:
   - Parses retrieved ICMR blocks and constructs grounded clinical responses with 100% verified citations.
   - Serves as the reproducibility anchor for automated testing and air-gapped CI/CD environments.
2. **Compact Local SLM (`CompactSLMProvider: phi-3.5-mini-instruct-q4`)**:
   - Represents small, highly quantised language models (3.8B parameters, 4-bit integer quantization) capable of running on edge hardware, local clinics, District Hospitals, or Primary Health Centres without internet connectivity.
   - Memory footprint: ~2.3 GB VRAM / RAM.
3. **Cloud LLM Representation (`OpenAIProvider: gpt-4o-mini` / `GeminiProvider: gemini-1.5-flash`)**:
   - Evaluates API-based frontier models for structural fidelity and reasoning capabilities.
   - Enforces graceful offline fallback and zero credential leaks when API keys are unconfigured.

### 2.3 Evaluation Benchmark Suite (52 Queries, 17 Categories)
Covering:
- STEMI, NSTEMI / Unstable Angina, Stable Angina, Heart Failure, Atrial Fibrillation, Bradyarrhythmias
- Investigations, Medications, Contraindications, Referral Criteria, Healthcare-tier Management
- Flowchart logic, Table extraction, Multi-version handling
- Insufficient evidence, Out-of-scope clinical queries, and Adversarial / prompt-injection attempts.

---

## 3. Objective B: Controlled Clinical Knowledge Review Workflow

### 3.1 Review Backlog Isolation
The 167 knowledge units flagged during extraction are stored in `data/knowledge/knowledge.db`:
- **Isolation Guarantee**: In `knowledge_units`, `requires_manual_review = 1`. Production retrieval queries filter `WHERE requires_manual_review = 0`.
- Flagged units are completely quarantined from the RAG retrieval pipeline until a human clinician explicitly reviews and approves them.

### 3.2 Human Review Architecture (`src/review/`)
- **`ReviewQueue` (`src/review/queue.py`)**:
  - Initializes SQLite table `review_items` (keyed by `REV-<unit_id>`) and synchronizes flagged units.
  - Automatically categorizes review reason: `FLOWCHART_AMBIGUITY`, `TABLE_EXTRACTION`, `INCOMPLETE_DOSAGE`, `OCR_OR_EXTRACTION_ERROR`, `VERSION_CONFLICT`, `SOURCE_AMBIGUITY`.
  - Automatically assigns clinical priority: `HIGH` (Medications, Contraindications, Emergency pathways), `MEDIUM` (Investigations, Diagnostic criteria, Healthcare tiers), `LOW` (Terminology, References).
- **`ReviewAuditManager` (`src/review/approval.py`)**:
  - Requires mandatory `reviewer_id` and clinical justification notes.
  - `approve_item()`: Sets `review_status = 'APPROVED'`, logs action to `review_audit_log`, and sets `requires_manual_review = 0` on `knowledge_units` to safely promote the item into production retrieval.
  - `reject_item()`: Sets `review_status = 'REJECTED'`, logs action, and ensures the item remains permanently excluded.
  - `record_correction()`: Records corrected structured value in `corrected_structured_value` and sets status to `NEEDS_CORRECTION`. **CRITICAL**: The original source text in `original_source_text` is immutable and never overwritten.
- **`ReviewService` (`src/review/service.py`)**: Unified service layer consumed by API endpoints.

---

## 4. API & Web Review Dashboard

### 4.1 REST API (`src/api/routes.py`)
- `GET  /api/v1/review/items`: Filter by status, priority, reason, document ID, entity type with pagination.
- `GET  /api/v1/review/items/{id}`: Single item detail with full provenance and original text.
- `POST /api/v1/review/items/{id}/approve`: Clinician approval.
- `POST /api/v1/review/items/{id}/reject`: Clinician rejection with mandatory reason.
- `POST /api/v1/review/items/{id}/correction`: Expert structured correction without altering raw text.
- `GET  /api/v1/review/summary`: Real-time queue counters (total backlog, priority breakdowns, status counts).
- `GET  /api/v1/review/audit`: Full immutable audit log of all human actions.

### 4.2 Web Interface (`/review`)
- Responsive dark-mode dashboard with KPI cards (`Total Backlog`, `High Priority Pending`, `Medium Priority Pending`, `Promoted to Production`).
- Filtering by Status, Priority, Reason, and Document.
- Dedicated side-by-side verification pane highlighting the immutable source text directly alongside extracted content and reviewer action controls.
