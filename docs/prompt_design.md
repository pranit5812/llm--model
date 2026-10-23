# Version-Controlled Prompt Design — ICMR STW AI

## 1. System Prompt (`SYSTEM_PROMPT_V1`)

The system prompt in `src/llm/prompts.py` sets non-negotiable guardrails:

```
Role: Official ICMR Standard Treatment Workflow (STW) clinical evidence assistant.
Source of Truth: ONLY the supplied retrieved ICMR STW evidence blocks.
```

### Key Principles Enforced:
1. **Zero External Clinical Memory**: The model is forbidden from using training-set general medical knowledge to fill in gaps.
2. **Prohibition of Extrapolation**: It must not invent dosages, thresholds, diagnostic timelines, or contraindications.
3. **Mandatory Abstention**: If the evidence is silent on a question, the model must explicitly declare insufficient evidence and set `abstained: true`.
4. **Data Neutrality (Anti-Injection)**: All retrieved evidence is explicitly framed as passive DATA to prevent adversarial prompt overrides embedded in documents.
5. **Structured Schema**: Forces the output to be a valid JSON dictionary conforming to `RAGResponse`.

## 2. Evidence Context Template

The context builder (`src/rag/context_builder.py`) formats candidates into numbered blocks:

```
[EVIDENCE 1]
[ID]: ICMR-CARD-006:medication:0001
[Document]: ICMR-CARD-006
[Condition]: STEMI
[Page]: 1
[Section]: MANAGEMENT OF STEMI AT PHC / NON-PCI CAPABLE HOSPITAL
[Status]: APPROVED
[Content]: Aspirin loading dose 300 mg oral chewable.
```
