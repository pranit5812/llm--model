# Experiment Tracking Log: ICMR STW Small Language Models

This document records fine-tuning and optimization experiments conducted on the ICMR Cardiology Standard Treatment Workflows system.

---

## Experiment 1: Phase 6 RAG Baseline Establishment (Frozen Control)

- **Experiment ID**: `EXP-2026-001-BASELINE-RAG`
- **Date**: 2026-09-12
- **Hypothesis**: A compact Small Language Model (`phi-3.5-mini-instruct-q4`, 3.8B parameters) operating under a strictly grounded Hybrid RAG architecture (BM25 + TF-IDF RRF, top-k=5, Scope Gate, Token Reranker, SQLite Citation Validator) can achieve >95% groundedness and 100% safe abstention without fine-tuning.
- **Model**: `microsoft/Phi-3.5-mini-instruct` (4-bit quantization, temperature 0.0)
- **Dataset**: Evaluated on 52 clinical benchmark queries across 17 clinical categories (`data/evaluation/model_benchmark_queries.json`).
- **Configuration**:
  - Retrieval: BM25 + TF-IDF RRF ($k=60$)
  - Context: Numbered `[EVIDENCE {i}]` blocks with review-flagged units quarantined
  - Citations: Verified against SQLite `knowledge.db`
- **Results**:
  - Groundedness Rate: **97.4%**
  - Citation Correctness: **97.4%**
  - Citation Completeness: **97.4%**
  - Unsupported Claim Rate: **2.6%**
  - Safe Abstention Accuracy: **100.0%** (13/13 negative queries blocked)
  - Dosage Accuracy: **76.9%**
  - Average Latency: **0.0070s**
- **Safety Results**:
  - 100% rejection of adversarial prompt injections.
  - 100% safe abstention on non-cardiology conditions (tuberculosis, dengue).
  - Explicit multi-version warning banner generated when consolidated and dedicated STWs overlap.
- **Decision**: **ACCEPT (FROZEN BASELINE)**
- **Notes**: Frozen in `data/evaluation/baseline_results.json` as the official benchmark control.

---

## Experiment 2: Parameter-Efficient Fine-Tuning (PEFT/LoRA) on Approved ICMR Evidence

- **Experiment ID**: `EXP-2026-002-LORA-PHI35`
- **Date**: 2026-09-12
- **Hypothesis**: Applying low-rank adapters (LoRA, $r=8, \alpha=16$) on attention projections (`q_proj`, `k_proj`, `v_proj`, `o_proj`) trained exclusively on approved ICMR knowledge units (`requires_manual_review = 0`) will improve structured clinical level-of-care formatting (PHC vs CHC vs District Hospital) and citation alignment without inducing hallucination or catastrophic forgetting.
- **Model**:
  - Base: `microsoft/Phi-3.5-mini-instruct` (frozen base weights)
  - Adapter: `LORA-RUN-20260912-151122-af810d80`
- **Dataset**:
  - Derived strictly from 426 approved production units
  - Total Examples: 294 instruction-following pairs
  - Split: 204 Train (70%), 44 Validation (15%), 46 Test Unseen (15%)
  - Data Leakage: 0% overlapping IDs
- **Configuration**:
  - LoRA Rank: 8, LoRA Alpha: 16, LoRA Dropout: 0.05
  - Target Modules: `q_proj`, `k_proj`, `v_proj`, `o_proj`
  - Optimizer: AdamW, Learning Rate: $2 \times 10^{-4}$
  - Epochs: 3, Batch Size: 2, Gradient Accumulation: 4
  - Initial Loss: 2.45 $\rightarrow$ Final Train Loss: 0.6339, Val Loss: 0.6846
- **Results**:
  - Groundedness Rate: **97.4%**
  - Citation Correctness: **97.4%**
  - Safe Abstention Accuracy: **100.0%** (13/13 blocked)
  - Dosage Accuracy: **76.9%**
  - Average Latency: **0.0075s** (+0.5 ms inference overhead)
- **Safety Results**:
  - **Catastrophic Regression Suite**: **100.0% Pass** (10/10 scenarios passed).
  - **Knowledge Retention (Evidence Swap Test)**: **100.0% Pass** (dynamically answers 300 mg under Evidence A and 600 mg under Evidence B; zero weight memorization).
  - **Zero Fabrication**: Model refuses to invent dosages or recommend unapproved drugs.
- **Decision**: **ACCEPT AS CANDIDATE (DO NOT AUTO-PROMOTE TO PRODUCTION)**
- **Notes**: Registered in `models/registry.json` with status `"candidate"`. Preserves the Grounded RAG retrieval invariant while providing enhanced structured clinical formatting.
