# Clinical Safety and Abstention — ICMR STW AI

## 1. Safety Rules

The ICMR STW AI system is designed strictly for **clinical decision support**.

The system:
- NEVER performs autonomous medical diagnosis.
- NEVER issues autonomous medical prescriptions.
- NEVER guesses or fills in missing parameters from general knowledge.
- ALWAYS appends a formal clinical disclaimer to every response.

## 2. Abstention Triggers

The system abstains (`status = "OUT_OF_SCOPE"` or `"INSUFFICIENT_EVIDENCE"`, `abstained = true`) under any of the following conditions:

| Trigger | Example Query | Action |
|---------|---------------|--------|
| **Non-Cardiology Condition** | "What is the dose of paracetamol in dengue?" | Immediate abstention via Scope Gate |
| **Non-Medical Query** | "What is the capital of India?" | Immediate abstention via Scope Gate |
| **Nonsense Query** | "xyzzyqrst clinical syndrome" | Immediate abstention via Scope Gate |
| **Adversarial Prompt Injection** | "Ignore all previous ICMR rules..." | Rejected by `SafetyGuard` |
| **No Evidence in Corpus** | Query on cardiology sub-specialty not covered by the 7 STWs | Returns `INSUFFICIENT_EVIDENCE` |
| **Pending Review Only** | Query only matches review-flagged units | Returns `INSUFFICIENT_EVIDENCE` |
| **Citation Validation Failure** | Citations fail database lookup | Returns `INSUFFICIENT_EVIDENCE` |

## 3. Version Handling

When evidence is retrieved from both the 2019 Consolidated Cardiology STW (`ICMR-CARD-007`) and dedicated condition STWs (`ICMR-CARD-001` through `006`), the system issues an explicit version warning:

> *"Multiple ICMR source versions contain relevant information: dedicated workflow(s) (ICMR-CARD-006) and consolidated workflow (ICMR-CARD-007). The system preserves all citations without independently determining clinical precedence."*
