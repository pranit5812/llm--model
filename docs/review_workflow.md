# Clinical Knowledge Review Workflow (Human-in-the-Loop)

## 1. Overview & Objectives

Automated PDF extraction of complex clinical workflows, multi-column dosage tables, and visual decision trees inherently introduces potential ambiguity or OCR imperfections.

Phase 6 implements a **controlled, audit-logged human clinical review system** for all **167 review-flagged knowledge units**.

```
                ┌──────────────────────────────────────────────┐
                │   Flagged Knowledge Units (167 items)        │
                │   requires_manual_review = 1 (Quarantined)   │
                └──────────────────────┬───────────────────────┘
                                       │
                                       ▼
                     Review Reason & Priority Classification
                     ├── HIGH (Medications, Contraindications)
                     ├── MEDIUM (Investigations, Tier actions)
                     └── LOW (Terminology, Generic references)
                                       │
                                       ▼
                         Clinician Review Dashboard
                     (/review Workbench & REST APIs)
                                       │
                ┌──────────────────────┼──────────────────────┐
                │                      │                      │
                ▼                      ▼                      ▼
         [APPROVE]                [CORRECTION]            [REJECT]
   • Requires Reviewer ID    • Modifies structured   • Requires rationale
   • requires_review = 0       value only            • Permanently excluded
   • Promoted to Retrieval   • Source text IMMUTABLE • Logged in audit trail
   • Logged in audit trail   • Logged in audit trail
```

---

## 2. Strict Human Approval & Isolation Guarantee

1. **Zero Auto-Approval**: The automated extraction pipeline, indexers, and algorithms are strictly forbidden from setting `review_status = 'APPROVED'` or clearing `requires_manual_review`.
2. **Quarantine by Default**: Production retrieval queries (`SELECT ... FROM knowledge_units WHERE requires_manual_review = 0`) never expose unreviewed flagged units to the RAG pipeline or clinical end-users.
3. **Mandatory Clinician Identity**: Every review action requires a non-empty `reviewer_id` (e.g. `DR-SHARMA-CARDIO`) and clinical justification. Anonymous or automated promotions are rejected with HTTP 400.

---

## 3. Review Reason Taxonomy

Every flagged item is categorized into one of six distinct clinical review reasons:

| Review Reason | Description | Example Trigger |
|---|---|---|
| **`FLOWCHART_AMBIGUITY`** | Visual branch logic, decision diamond, or directional flow requiring human confirmation. | Flowchart node: "Transfer to PCI capable hospital within 120 min". |
| **`TABLE_EXTRACTION`** | Multi-column table row where cell alignment or headers required verification. | Multi-tier medication dosing tables with merged headers. |
| **`INCOMPLETE_DOSAGE`** | Medication entry where dosage, frequency, or route was incomplete in source text. | Medication entry extracted with "Dose: None" or missing unit. |
| **`OCR_OR_EXTRACTION_ERROR`** | Text noise, line breaks, or special symbols resulting from PDF rendering. | Punctuation artifacts or split acronyms in PDF columns. |
| **`VERSION_CONFLICT`** | Divergence or overlap between 2019 Consolidated STW and dedicated STWs. | Overlapping STEMI or Dyslipidemia criteria across versions. |
| **`SOURCE_AMBIGUITY`** | Text in the source PDF itself that is clinically open to multiple interpretations. | Unspecified time intervals or ambiguous diagnostic thresholds. |

---

## 4. Clinical Priority Tiers

To maximize clinical safety, the review queue is triaged into three priority tiers:

- **HIGH PRIORITY (Red)**:
  - **Scope**: Medications, active drug dosages, absolute and relative contraindications, acute emergency pathways, reperfusion / thrombolysis time windows, and emergency transfer criteria.
  - **Rule**: Must be reviewed by a specialist cardiologist or senior physician before any unit can be promoted.
- **MEDIUM PRIORITY (Amber)**:
  - **Scope**: Diagnostic investigations, lab workups (Troponin, ECG, Echo), healthcare tier assignments (PHC vs CHC vs District Hospital), and clinical table rows.
- **LOW PRIORITY (Blue)**:
  - **Scope**: Clinical definitions, terminology, footnotes, and document metadata.

---

## 5. Immutable Source Text Guarantee

A foundational principle of the ICMR STW system is **the immutability of the source of truth**:

- The original raw text extracted from the official ICMR PDF is stored in `review_items.original_source_text`.
- **Under no circumstances is `original_source_text` modified, overwritten, or truncated during human review.**
- If a clinician identifies an extraction mistake (e.g. a missed dose or typographical error), they record the fix in `corrected_structured_value`.
- Both the original source text and the human correction are stored side-by-side, preserving an uncompromised audit trail of what the PDF literally stated versus what the expert human clinician clarified.

---

## 6. Audit Trail & Governance (`review_audit_log`)

Every review event is recorded in the SQLite table `review_audit_log` with:
- `log_id`: Auto-incrementing unique sequential identifier.
- `review_item_id`: Reference to review backlog item (`REV-ICMR-CARD-001-KU-001`).
- `knowledge_unit_id`: Reference to underlying knowledge unit.
- `action`: `APPROVE`, `REJECT`, or `CORRECTION`.
- `reviewer_id`: Medical practitioner identifier.
- `notes`: Justification notes provided by the reviewer.
- `corrected_value`: The structured correction (if applicable).
- `timestamp`: UTC ISO timestamp of action.

---

## 7. Reviewer Workbench Guide (`/review`)

1. Open the review portal at `http://localhost:8000/review` (or click "Review Portal" from `/chat`).
2. Review the summary metrics at the top of the dashboard.
3. Select an item from the queue list (default sorted by **HIGH** priority first).
4. Inspect the **Immutable ICMR PDF Source Text** pane (blue bordered reference box).
5. Compare with the **Extracted Knowledge Content** pane.
6. Enter your `Clinician / Reviewer ID` and `Clinical Notes`.
7. Choose the appropriate action:
   - **Approve for Production**: Promotes the unit (`requires_manual_review = 0`).
   - **Save Correction**: Enters the structured correction while preserving raw text.
   - **Reject Unit**: Permanently quarantines the unit from clinical decision support.
