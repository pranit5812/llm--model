# Grounding and Citation Verification — ICMR STW AI

## 1. Citation Integrity

Every clinical assertion returned by the RAG system must be tied to a verified citation object:

```json
{
  "document_id": "ICMR-CARD-006",
  "condition": "STEMI",
  "page_number": 1,
  "section": "MANAGEMENT OF STEMI AT PHC / NON-PCI CAPABLE HOSPITAL",
  "knowledge_unit_id": "ICMR-CARD-006:medication:0000",
  "source_text_reference": "STEMI medication: Aspirin..."
}
```

## 2. Citation Validation Rules

In `src/llm/citation_validator.py`, the validator verifies:
1. **Candidate Membership**: The cited `knowledge_unit_id` must have been present in the retrieved candidates supplied to the LLM.
2. **Database Existence**: The `knowledge_unit_id` must physically exist in SQLite `knowledge.db`.
3. **Metadata Alignment**: The cited `document_id` and `page_number` must match the SQLite record exactly.
4. **Production Approval**: The unit must have `requires_manual_review = 0`.

If a citation fails, it is removed. If no verified citations remain, the response status is flipped to `INSUFFICIENT_EVIDENCE` and `abstained: true`.

## 3. Dosage Grounding Verification

In `src/rag/response_validator.py`:
- All dosages (e.g. `300 mg`, `1.5 mega units`, `120 min`) mentioned in the answer text are extracted and searched in the concatenated retrieved evidence text.
- If an ungrounded quantity appears in the answer, the response is downgraded to `PARTIALLY_GROUNDED` and an alert is appended to the cautions list.
