# ICMR STW Schema Design Decisions & Architectural Rationale

## 1. Why This Schema Was Chosen

The canonical ICMR Standard Treatment Workflow (STW) schema was designed to solve a foundational challenge: bridging dense, visually formatted clinical posters into a rigorous, machine-computable clinical knowledge representation without losing medical meaning, context, or evidentiary traceability.

### Key Drivers:
* **Evidence-Grounded AI**: Future clinical AI systems (retrieval-augmented generation, clinical summaries) must never hallucinate clinical recommendations. The schema acts as a strict structural filter ensuring that every datum is verified before downstream ingestion.
* **Separation of Structure from Unstructured Prose**: ICMR STWs are visual workflow algorithms designed for busy clinicians in India. Storing them as raw text dumps or unstructured vector embeddings destroys the decision logic, branch conditions, and tabular drug relationships.
* **Tiered Healthcare Representation**: Healthcare delivery in India is fundamentally tiered (PHC/CHC -> District Hospital -> Tertiary Care / PCI Capable). A flat guideline schema would obscure which action is expected at which tier.
* **Type Safety & Schema Enforcement**: Built with Pydantic v2, the schema enforces type safety, non-empty text, valid integer page numbers, referential graph integrity, and tabular row-header matching.

---

## 2. How Clinical Workflows Are Represented

Clinical workflows in the ICMR documents are structured around specific clinical milestones:
1. **Clinical Presentation & Triage**: Capturing inclusion criteria (typical retrosternal pain, radiation, diaphoresis) and explicit exclusion criteria (pleuritic pain, fleeting symptoms, local tenderness).
2. **Diagnostic Workup Stratification**: Partitioning investigations into three distinct resource tiers:
   - `BASIC`: Available at primary health centers and community health centers (e.g. 12-lead ECG, blood glucose, routine chemistry).
   - `DESIRABLE`: Available at secondary / district hospitals (e.g. 2D echocardiography, troponin assays).
   - `OPTIONAL`: Advanced procedures available at tertiary centers (e.g. coronary angiography, stress imaging, FFR).
3. **Tiered Management Strategy**: Encapsulating actions specific to `PHC_CHC`, `DISTRICT_HOSPITAL`, and `TERTIARY_PCI` facilities.

---

## 3. How Decision Trees and Flowcharts Are Represented

ICMR STWs contain critical conditional logic (e.g., "Within 12 hours -> PCI capable? -> Yes: Primary PCI; No: Transfer < 120 min? -> Yes: Transfer; No: Fibrinolysis").

### Directed Graph Architecture:
Rather than flattening decision logic into linear text or nested if-then prose, the schema models clinical workflows as directed graphs (`FlowchartGraph`):
* **Nodes (`DecisionNode`)**:
  - `START`: Entry trigger (e.g. First Medical Contact with ischemic symptoms).
  - `DECISION`: Branching evaluations (e.g. time window elapsed, facility capabilities, clinical stability).
  - `ACTION`: Procedural or therapeutic interventions (e.g. drug loading, primary PCI).
  - `INVESTIGATION`: Diagnostic evaluation step (e.g. 12-lead ECG within 10 min).
  - `REFERRAL`: Inter-tier facility transfer directives (e.g. emergency transfer for rescue PCI).
  - `TERMINAL`: Completion or stabilization endpoint.
* **Edges (`DecisionBranch`)**:
  - Each branch specifies the exact `condition` string, `target_node_id`, and clinical `rationale`.
* **Referential Integrity Enforcement**:
  - The model validator automatically verifies that `start_node_id` exists within the graph and that every `target_node_id` across all branches points to an existing node, preventing broken pathways or dangling references.

---

## 4. How Tables Are Represented

Clinical tables—such as weight-based fibrinolytic dosing, risk stratification matrices (TIMI/GRACE), and multi-drug regimens—are preserved as structured relational entities (`STWTable`):
* **Column Headers**: Defined as explicit ordered lists of strings (`headers: ["Agent", "Dosing Protocol", "Route", "Key Considerations"]`).
* **Relational Rows (`STWTableRow`)**: Cell data is mapped as key-value pairs (`Dict[str, str]`) where every key corresponds to a declared column header.
* **Integrity Validation**: Pydantic validators guarantee that no row is missing declared headers, preventing column drift and ensuring semantic table preservation.

---

## 5. How Source Citations and Provenance Are Preserved

Source provenance is a mandatory architectural invariant. Every structured clinical entity (`STWClinicalPresentation`, `STWDiagnosticCriterion`, `Investigation`, `MedicationDose`, `Contraindication`, `ReferralCriterion`, `HealthcareTierManagement`, `DecisionNode`, `FlowchartGraph`, `STWTable`, `STWTableRow`, `STWReference`) contains an explicit `source: SourceReference` object:
* `document_id`: The canonical STW identifier (e.g. `ICMR-CARD-006`).
* `page_number`: 1-indexed positive integer pointing directly to the source page.
* `section`: The exact section header or visual container title.
* `source_text_reference`: Verbatim text snippet from the official ICMR document.
* `bounding_box`: Optional coordinates `[x0, y0, x1, y1]` for visual PDF annotation.

Any attempt to instantiate a clinical entity without provenance immediately raises a `pydantic.ValidationError`.

---

## 6. How Document Versions Are Handled

ICMR STWs have evolved across multiple iterations:
* **Original 2019 Print Edition**: Published in Volume 1 (16 pages for Cardiology).
* **Individual STW Updates**: Several online individual PDFs contain updated guidelines (for example, the STEMI individual PDF `1768823342_cardiology_1-5.pdf` is dated January 2026 and references the 2023 ESC ACS Guidelines and 2025 ACC/AHA ACS Guidelines).
* **Version Modeling**:
  - The `STWMetadata` object tracks `edition` (e.g., `"2019 (Updated Jan 2026)"`), `volume`, `document_hash` (SHA-256 for exact cryptographic verification), and `source_url`.
  - When new versions are released, `document_id` maintains family continuity while version fields and hashes capture the exact snapshot.

---

## 7. How Future STWs From Other Specialties Can Use the Same Schema

Although developed and validated on Cardiology STWs, the schema is specialty-agnostic:
1. **Generic Clinical Constructs**: Clinical presentation (symptoms, signs, red flags), investigations (basic, desirable, optional), medications, contraindications, and referrals are universal across internal medicine, pediatrics, oncology, neurology, etc.
2. **Standard Indian Healthcare Tiers**: The tier structure (`PHC_CHC`, `DISTRICT_HOSPITAL`, `TERTIARY_PCI` / `TERTIARY_SPECIALTY`) is standardized across all national health mission programs in India.
3. **Graph Algorithms**: Decision nodes and branches naturally represent triage trees for pediatric pneumonia, stroke thrombolysis, diabetic ketoacidosis, or oncological staging.
4. **Extensibility**: Future specialties can add domain-specific scoring systems or classification models without altering the core provenance and flowchart engine.

---

## 8. What Information Cannot Currently Be Represented

The current schema deliberately avoids capturing:
* **Visual Styling / Aesthetics**: Colors, fonts, layout box coordinates (except optional bounding boxes for provenance audit).
* **Implicit or Unwritten Clinical Assumptions**: For instance, standard nursing procedures, routine IV cannulation techniques, or general hospital bed management not explicitly specified in the text.
* **Real-Time Dynamic Calculations**: The schema stores formulas, thresholds, and scoring categories, but does not execute interactive calculators (which belongs in the application/decision-support layer).

---

## 9. Ambiguities Found in the ICMR Documents

During PDF inspection, several document anomalies and ambiguities were identified:
1. **Typographical Errors in Medical Names**:
   - In `1768823342_cardiology_1-5.pdf` (STEMI): "Ticagralor" (for Ticagrelor), "First Medical Contract" (for First Medical Contact), "surgey" (for surgery), "Mecahnical complication" (for Mechanical complication), "Isosorbide mono-nitare" (for Isosorbide mononitrate).
   - In `1768823343_cardiology_1-1.pdf` (AF): "AF lasing from 7 days" (for lasting), "Long standing perssistent" (for persistent).
   - In `1771492063_bradyarrthymia13_2_2.pdf`: "Bradyarrthymias" (for Bradyarrhythmias).
2. **Missing Units or Incomplete Sentences**:
   - In `1768823342_cardiology_1-5.pdf` (STEMI): Streptokinase dosage text ends abruptly as `"Streptokinase 1.5 million units IV over 60 min"`, while in some columns text wraps tightly.
   - In `1768823343_cardiology_1-1.pdf` (AF): "Systolic BP 90 mmHg" (omits the `<` sign in some text blocks though the context implies `< 90 mmHg`).
3. **Heading Under Heading Overlaps**:
   - In `1768823342_cardiology_1-5.pdf`: "B. If Transfer to PCI incapable hospital not feasible" appears under "THROMBOLYSE" whereas logically it refers to "If Transfer to PCI *capable* hospital not feasible".
4. **Resolution Rule**: The canonical schema faithfully quotes the verbatim text in `source_text_reference` while recording the cleaned clinical concept in structured fields, noting typographical discrepancies for clinical review.

---

## 10. Items Requiring Medical Expert Review

The following clinical items should be verified by a medical advisory panel during knowledge base curation:
1. **FMC Terminology Verification**: Confirm that "First Medical Contract (FMC)" is a typographical error for "First Medical Contact (FMC)" in the STEMI guideline.
2. **Blood Pressure Cutoff in AF**: Confirm the intended hemodynamic instability threshold: whether SBP `< 90 mmHg` was intended where text states `"Systolic BP 90 mmHg, HR > 150 or <50/min"`.
3. **Negative Statement in Reperfusion Heading**: Verify the text `"B. If Transfer to PCI incapable hospital not feasible"` which clinically means "If Transfer to PCI-capable hospital is *not* feasible, perform thrombolysis".
4. **Drug Name Normalization**: Authorize standardizing typographical variants (e.g. "Ticagralor" -> Ticagrelor, "Isosorbide mono-nitare" -> Isosorbide mononitrate) while preserving exact PDF quotations in provenance records.
5. **Guideline Version Reconciliation**: Establish clinical consensus on precedence between the 2019 Consolidated Volume 1 guideline and the January 2026 individual STW updates.
