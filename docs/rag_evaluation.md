# RAG Evaluation Benchmark — ICMR STW AI

## 1. Benchmark Dataset (`data/evaluation/rag_queries.json`)

The benchmark comprises 36 rigorous clinical queries covering:
- Factual medication queries (STEMI aspirin, ticagrelor, streptokinase, digoxin, furosemide, warfarin, nitrates)
- Contraindication queries (thrombolysis contraindications, beta blockers in heart failure)
- Diagnostic criteria (12-lead ECG STEMI criteria, CHA2DS2-VASc score)
- Investigations (echocardiography, troponin, blood panels)
- Referral criteria (PCI transfer timelines, complete heart block)
- Healthcare tier actions (PHC vs CHC vs District Hospital)
- Version-related queries (consolidated vs dedicated STW)
- Negative / out-of-scope queries (dengue, pneumonia, diabetes titration, hip fracture, non-medical questions)
- Adversarial prompt injection attacks

## 2. Evaluation Results Summary

Generated via `python scripts/evaluate_rag.py` on the complete 36-query suite:

| Metric | Score | Note |
|--------|:-----:|------|
| **Total Benchmark Queries** | 36 | 29 In-Scope, 7 Out-of-Scope / Adversarial |
| **Retrieval Correctness Rate** | **96.6%** | Expected document in retrieved candidates |
| **Citation Completeness Rate** | **100.0%** | Every grounded response had verified citations |
| **Evidence Grounding Rate** | **100.0%** | 0 ungrounded claims generated |
| **Safe Abstention Accuracy** | **100.0%** | All 7 negative/adversarial queries abstained |
| **Unsupported Claim Rate** | **0.0%** | Strict containment within ICMR corpus |
| **Average Retrieval Latency** | **0.0058s** | Sub-10ms BM25 + TF-IDF RRF retrieval |
| **Average LLM Generation Latency** | **0.0001s** | Local deterministic SLM provider |
| **Average Total Pipeline Latency** | **0.0067s** | 6.7 milliseconds end-to-end |

## 3. Failure Taxonomy & Known Limitations

- **Complex visual flowcharts**: 167 units with visual decision branches remain flagged for manual clinical review and are safely excluded from the production index.
- **Cross-condition multi-morbidities**: Queries combining multiple conditions (e.g. STEMI in a severe COPD patient) are bounded by what is explicitly written in the ICMR cardiology STWs; the system will not extrapolate drug interactions unless documented in the STW.
