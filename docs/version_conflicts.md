# Cross-Version Analysis & Multi-STW Conflict Handling

## 1. Multi-Version Document Context

The ICMR Cardiology corpus in this repository consists of two distinct publication vintages:

1. **Dedicated Single-Topic STWs (2022 Series)**:
   - `ICMR-CARD-001`: Acute Coronary Syndrome (STEMI & NSTEMI)
   - `ICMR-CARD-002`: Hypertension
   - `ICMR-CARD-003`: Heart Failure
   - `ICMR-CARD-004`: Stable Coronary Artery Disease
   - `ICMR-CARD-005`: Dyslipidemia
   - `ICMR-CARD-006`: Bradyarrhythmias / Emergency STEMI pathways
2. **Consolidated Cardiology STW (2019 Publication)**:
   - `ICMR-CARD-007`: *Standard Treatment Workflows (STW) for Cardiology* (Consolidated volume covering STEMI, NSTE-ACS, Heart Failure, Chronic CAD, Hypertension, and Dyslipidemia).

---

## 2. Documented Cross-Version Divergences

| Clinical Domain | 2019 Consolidated STW (`ICMR-CARD-007`) | Dedicated STW Series (`ICMR-CARD-001` to `006`) | Clinical Significance |
|---|---|---|---|
| **STEMI Thrombolytic Agent** | Streptokinase 1.5 million units IV highlighted as primary agent across non-PCI hospitals. | Tenecteplase / Reteplase weight-adjusted dosing specified alongside Streptokinase. | Newer single-topic guideline reflects broader availability of fibrin-specific agents. |
| **STEMI Transfer Window** | "Transfer immediately if PCI feasible within 120 minutes." | Detailed hub-and-spoke flowchart mapping PHC -> CHC -> District Hospital -> Cath Lab. | Dedicated STW provides finer operational granularity for rural tiers. |
| **Dyslipidemia Target LDL** | Fasting lipid profile with baseline statin initiation thresholds. | High-intensity vs moderate-intensity statin titration targets based on ASCVD risk stratification. | Dedicated guideline provides deeper cardiovascular risk stratification. |
| **Heart Failure Staging** | Clinical NYHA Class I-IV with basic diuretic and ACEI titration. | GDMT (Guideline-Directed Medical Therapy) incorporating SGLT2 inhibitors and ARNI considerations. | Reflects evolving pharmacological standards in chronic heart failure. |

---

## 3. Strict Non-Arbitrary Version Policy

In algorithmic clinical decision support, resolving medical divergences automatically is dangerous:

1. **No Silent Precedence**: The system **NEVER** silently discards the 2019 Consolidated STW, nor does it assume the newer document completely invalidates the older one without explicit government/expert sanction.
2. **Dual Citation & Complete Provenance**: When a query retrieves evidence spanning both `ICMR-CARD-007` and dedicated STWs, the system presents citations from **both documents**, stating the document ID, condition, page number, and section.
3. **Automated Version Warning Banner**: The RAG pipeline (`ResponseValidator.detect_version_conflicts`) detects multi-version retrieval and attaches an explicit warning:
   > *"Multiple ICMR source versions contain relevant information: dedicated workflow(s) (ICMR-CARD-006) and consolidated workflow (ICMR-CARD-007). The system preserves all citations without independently determining clinical precedence."*
4. **Clinical Discretion Retained**: The attending clinician is provided the exact text from both documents and makes the final decision based on local drug availability and institutional protocol.

---

## 4. Conflict Resolution Workflow in Human Review

For units flagged under `review_reason = 'VERSION_CONFLICT'`:
1. The unit is assigned **HIGH Priority** in the Review Queue.
2. The review card displays both source citations side-by-side.
3. A medical expert reviews the divergence:
   - If the newer guideline supersedes the text for their specific healthcare tier, the reviewer records a clinical note in `review_notes`.
   - If both recommendations remain valid (e.g. Streptokinase remains standard where Tenecteplase is unavailable), the reviewer approves both units with an explanatory contextual note.
