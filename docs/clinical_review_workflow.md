# ICMR STW Platform: Clinical Review, Approval & Controlled Promotion SOP

**Document ID:** SOP-ICMR-STW-REV-009  
**Version:** 1.0  
**Effective Date:** 2026-09-12  
**Status:** Approved Standard Operating Procedure  
**Target Audience:** Clinical Reviewers, Specialty Leads, Medical Knowledge Engineers, Chief Medical Officers  

---

## 1. Executive Summary & Core Principle

The Indian Council of Medical Research (ICMR) Standard Treatment Workflow (STW) AI Platform operates under a non-negotiable healthcare mandate:

> **"One Standard of Care. Across India."**

The platform is designed exclusively as an **ICMR-grounded clinical decision-support and workflow retrieval system**. It is **NOT** an autonomous diagnostic engine, and it must never invent medications, dosages, contraindications, or clinical recommendations.

Automated PDF extraction, layout analysis, flowchart parsing, and table conversion inherently risk introducing extraction noise, character artifacts, or structural ambiguities. To safeguard patient safety:
1. **Automated extraction NEVER promotes content directly into production.** All newly extracted knowledge units enter a quarantined backlog (`requires_manual_review = 1`).
2. **Approval does NOT equal immediate indexing.** Clinical approval marks content as `APPROVED` / `ELIGIBLE_FOR_PRODUCTION`. An explicit, validated promotion step is mandatory to induct units into the active production search indexes.
3. **High-Risk clinical knowledge requires Two-Stage Approval** by two distinct clinicians before becoming eligible for promotion.
4. **Original source text is strictly immutable.** Corrections only modify structured attributes, preserving verbatim source extracts for lifelong provenance and auditability.

---

## 2. Review Lifecycle State Machine

Each knowledge unit in the review pipeline progresses through a deterministic, irreversible-upon-rejection state machine:

```
                      [ Extracted Unit ]
                              │
                              ▼
                      ┌──────────────┐
                      │ NEEDS_REVIEW │ (Quarantined, requires_manual_review = 1)
                      └──────┬───────┘
                             │ Clinician Claims Item
                             ▼
                      ┌──────────────┐
                      │  IN_REVIEW   │
                      └──────┬───────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
            ▼                ▼                ▼
     [ REJECTED ]     [ CORRECTION ]   [ APPROVAL PATHWAY ]
     • Permanent      • Original text  • Stage 1 (Reviewer 1)
       exclusion        immutable      • Stage 2 (Reviewer 2, High-Risk)
     • Mandatory note • Unit remains   • Transitions to APPROVED /
     • Cannot index     in review        ELIGIBLE_FOR_PRODUCTION
                                              │
                                              ▼
                                    ┌──────────────────┐
                                    │     PROMOTED     │
                                    │ • Validated      │
                                    │ • Incremental idx│
                                    │ • requires_rev=0 │
                                    └──────────────────┘
```

### State Definitions

| State | Production Searchable? | Description |
|---|:---:|---|
| **`NEEDS_REVIEW`** / **`PENDING`** | ❌ No | Newly ingested unit placed in quarantine. Pending clinician triage. |
| **`IN_REVIEW`** | ❌ No | Claimed by an active clinician. Undergoing clinical evaluation. |
| **`APPROVED`** / **`ELIGIBLE_FOR_PRODUCTION`** | ❌ No | Clinically validated by authorized clinician(s). Awaiting promotion validation. |
| **`CORRECTED`** | ❌ No | Content corrected against source PDF; re-queued or ready for final sign-off. |
| **`REJECTED`** | ❌ NEVER | Permanently excluded from retrieval due to clinical obsolescence or error. |
| **`PROMOTED`** | ✅ Yes | Validated by pre-promotion engine and incrementally indexed into BM25/TF-IDF. |

---

## 3. Clinical Governance Roles & Permissions

| Role | Permitted Actions | Minimum Credential Requirements |
|---|---|---|
| **Primary Reviewer** (`DR-REVIEWER-1`) | Claim review, record corrections, stage 1 approvals (high risk), standard approvals (medium/low risk), rejections. | Registered Medical Practitioner (MBBS / MD / DNB). |
| **Secondary Reviewer** (`DR-REVIEWER-2`) | Conduct independent secondary audit and sign off stage 2 approvals for high-risk items. | Independent Senior Specialist / Fellow (Distinct from Reviewer 1). |
| **Production Promotion Authority** (`CLINICAL-OPS-LEAD`) | Run pre-promotion automated compliance validation and execute incremental production indexing. | Medical Director, Chief Medical Officer, or Lead Clinical Knowledge Engineer. |

---

## 4. Risk Classification & Two-Stage Approval Mandate

Every quarantined item is automatically assigned a risk profile based on its clinical entity type:

| Risk Category | Clinical Entity Types | Two-Stage Approval Required? | Mandatory Justification Notes? |
|---|---|:---:|:---:|
| **HIGH** | `medication`, `drug_recommendation`, `contraindication`, `dosage_spec` | **YES** (Two distinct clinicians) | **YES** (Both stages) |
| **MEDIUM** | `investigation`, `tier_action`, `referral_criteria`, `table_row` | No (Single clinician sufficient) | **YES** |
| **LOW** | `clinical_overview`, `general_statement`, `terminology`, `administrative` | No (Single clinician sufficient) | Optional (Recommended) |

### Strict Invariant on Two-Stage Approval
When an item has `requires_two_stage_approval = True` or belongs to the `HIGH` risk category:
1. Reviewer 1 submits Stage 1 approval with mandatory justification notes. The item transitions to `IN_REVIEW` with `first_reviewer_id` and timestamp locked.
2. Reviewer 2 must evaluate the item. The system enforces:
   $$\text{Reviewer 2 ID} \neq \text{Reviewer 1 ID}$$
   Any attempt by Reviewer 1 to sign off on Stage 2 is blocked with an explicit error.
3. Both clinicians' names, IDs, timestamps, and notes are permanently captured in the immutable audit log.

---

## 5. Standard Operating Procedure (SOP) Step-by-Step

### Step 1: Accessing the Clinical Review Portal
1. Navigate to the clinical workbench at `http://localhost:8000/review`.
2. Ensure the active user is logged in with their institutional Clinician ID (e.g., `DR-KUMAR-NEURO`).
3. View the Backlog Summary KPIs:
   - **Total Backlog**: Total units in quarantine.
   - **High Risk**: Units requiring two-stage clinical approval.
   - **Needs Review**: Unclaimed items awaiting triage.
   - **In Review**: Items currently claimed by clinicians.
   - **Approved / Eligible**: Content ready for promotion validation.
   - **Production Index**: Live production units retrievable by clinical decision-support.

### Step 2: Queue Triage & Filtering
1. Utilize the advanced filter controls:
   - **Specialty Filter**: Filter by `Cardiology`, `Neurology`, `Nephrology`, etc.
   - **Status Filter**: Focus on `NEEDS_REVIEW` or `IN_REVIEW`.
   - **Risk Filter**: Prioritize `HIGH` risk items.
   - **Reason Filter**: Filter by `OCR_OR_EXTRACTION_ERROR`, `FLOWCHART_AMBIGUITY`, `TABLE_EXTRACTION`, etc.
   - **Search Query**: Find specific drug names, clinical concepts, or unit IDs.
2. Select an item from the queue table to open the Review Workbench.

### Step 3: Workbench Verification & Source Immutability
1. **Compare Side-by-Side:**
   - **Left Panel (Immutable Source Reference):** Displays the verbatim text extracted from the official ICMR guideline PDF, along with document ID, condition, section, and page number.
   - **Right Panel (Editable Structured Unit):** Displays the extracted clinical content, entity type, condition, and section.
2. **Inspect Complex Structures:**
   - For `FLOWCHART_AMBIGUITY`: Verify decision diamond conditions, branch logic, and transfer time thresholds.
   - For `TABLE_EXTRACTION`: Inspect column alignments and ensure values correspond correctly to patient tiers (PHC/CHC vs Sub-centre vs Tertiary).
3. **Verify Provenance Integrity:** Confirm that the source reference cites an authentic page number and section within the registered document catalogue.

### Step 4: Executing Clinical Actions

#### Pathway A: Starting / Claiming a Review
- Click **[Start Review]**.
- Enter your Clinician ID and Name.
- Status transitions to `IN_REVIEW`. The item is assigned to you.

#### Pathway B: Approving an Item
- Click **[Approve]**.
- If the item is **HIGH RISK**:
  - If Stage 1: Provide clinical notes confirming dosage and indication. Item remains in `IN_REVIEW` awaiting secondary review.
  - If Stage 2: A different clinician logs in, verifies the item, inputs independent notes, and submits. Item transitions to `APPROVED` / `ELIGIBLE_FOR_PRODUCTION`.
- If the item is **MEDIUM/LOW RISK**:
  - Provide clinical verification notes. Item transitions to `APPROVED` / `ELIGIBLE_FOR_PRODUCTION`.

#### Pathway C: Correcting an Item
- If extraction has minor typos, missing units (e.g. `mg` missing), or OCR noise:
- Edit the content in the right panel.
- Click **[Save Correction]**.
- Enter correction rationale (e.g., *"Fixed OCR typo: changed 'O.9 mg' to '0.9 mg/kg' per ICMR STW Page 3"*).
- **CRITICAL SAFEGUARD:** The left panel (`original_source_text`) remains completely unchanged. Only the operational payload is modified. The prior value, new value, reviewer ID, and timestamp are written to `review_audit_log`.

#### Pathway D: Rejecting an Item
- If extracted content is clinically obsolete, contradictory, unresolvably corrupted, or outside official ICMR endorsement:
- Click **[Reject]**.
- Enter mandatory clinical rejection justification (e.g., *"Experimental herbal infusion not endorsed by ICMR acute stroke workflow"*).
- Item transitions to `REJECTED`.
- **CRITICAL SAFEGUARD:** Rejected units are permanently locked. They are barred from production promotion and can never be retrieved by the RAG engine.

### Step 5: Production Promotion & Incremental Indexing
1. Once an item achieves status `APPROVED` / `ELIGIBLE_FOR_PRODUCTION`:
2. The Production Promotion Authority clicks **[Promote to Production]**.
3. **Automated Pre-Promotion Compliance Engine** executes 11 mandatory checks:
   - Check 1: Review status is `APPROVED` or `ELIGIBLE_FOR_PRODUCTION`.
   - Check 2: Two-stage approval satisfied (if high-risk).
   - Check 3: Primary review notes present and non-empty.
   - Check 4: Unit exists in persistent knowledge store.
   - Check 5: Content is non-empty and medically structured.
   - Check 6: Clinical condition is identified.
   - Check 7: Page number > 0.
   - Check 8: Guideline section is specified.
   - Check 9: Original source text reference is intact.
   - Check 10: Document ID exists in registered ICMR STW Document Catalogue.
   - Check 11: No unapproved clinical mutations detected.
4. **Execution:**
   - If ANY check fails: Promotion is aborted with HTTP 422. A detailed diagnostic report lists the failing invariant.
   - If ALL checks pass:
     - Database record updated: `requires_manual_review = 0`, status = `PROMOTED`.
     - In-memory BM25 index incrementally updated.
     - Global TF-IDF vocabulary matrix incrementally updated.
     - On-disk index pickles persisted.
     - Average indexing latency: **< 100 milliseconds** (zero system downtime, no full corpus rebuild).
     - Full event logged to `review_audit_log`.

---

## 6. Regulatory Audit & Compliance Invariants

1. **Complete Provenance:** Every response served to an end-user clinician cites the official ICMR document ID, section name, page number, and review audit hash.
2. **Tamper-Evident Audit Log:** All events in `review_audit_log` are append-only. Deletions or updates to audit history are prohibited at the database level.
3. **Cardiology Baseline Preservation:** Promotion of content from any specialty (e.g., Neurology) must never degrade the baseline Cardiology index (426 production units remain permanently intact).
4. **Offline Resilience:** All verification, indexing, and review workflows execute completely offline without cloud dependencies or unauthorized external telemetry.
