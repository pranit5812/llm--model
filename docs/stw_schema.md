# ICMR Standard Treatment Workflow (STW) — Canonical Knowledge Schema Specification

## 1. Architectural Purpose & Principles

The Canonical STW Knowledge Schema is the formal, machine-readable data contract for clinical guidelines published by the Indian Council of Medical Research (ICMR). It provides a structured bridge between unstructured clinical PDF documents and downstream clinical systems (such as knowledge bases, hybrid retrieval engines, and AI-assisted clinical decision support).

```
┌────────────────────────┐
│  Raw ICMR STW PDFs     │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Document Processing &  │
│ Semantic Extraction    │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│  Canonical STW Schema  │◄── THIS SPECIFICATION
│ (Pydantic / JSON Data) │
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Evidence-Grounded      │
│ Clinical Knowledge Base│
└───────────┬────────────┘
            │
            ▼
┌────────────────────────┐
│ Hybrid Retrieval & AI  │
└────────────────────────┘
```

### Core Design Axioms:
1. **Source Provenance Integrity (Non-Negotiable)**: Every extracted clinical statement, parameter, recommendation, dosage, or decision node MUST explicitly cite its source provenance (document ID, page number, section name, and exact verbatim source text reference). No floating clinical claims are permitted.
2. **Zero Clinical Hallucination / Zero Inferencing**: Missing medical information in the ICMR guideline must remain `null` or empty. The schema models *only* what is explicitly asserted in the source text.
3. **Preservation of Graph Logic (Flowcharts)**: Clinical algorithms, time windows, and triage decision trees are modeled as directed graphs (nodes and conditional branches) rather than flattened prose.
4. **Preservation of Tabular Semantics**: Dosing tables, contraindication lists, and multi-tier investigation matrices are stored with relational row/column fidelity.
5. **Tiered Healthcare Alignment**: The schema explicitly accounts for India's 3-tier healthcare delivery system:
   - Primary Health Centre / Community Health Centre (PHC/CHC)
   - District Hospital (Secondary Care)
   - Tertiary Care / Specialist Centers (e.g. PCI-capable facilities)

---

## 2. Source Provenance Model (`SourceReference`)

Every clinically meaningful entity in the schema inherits or contains a `SourceReference`.

```json
{
  "$defs": {
    "SourceReference": {
      "type": "object",
      "properties": {
        "document_id": {
          "type": "string",
          "description": "Standard STW identifier, e.g. 'ICMR-CARD-006'"
        },
        "document_name": {
          "type": "string",
          "description": "Human readable document name, e.g. 'STEMI'"
        },
        "page_number": {
          "type": "integer",
          "minimum": 1,
          "description": "1-indexed page number in the source PDF"
        },
        "section": {
          "type": "string",
          "description": "Section header in the source PDF, e.g. 'GENERAL MEASURES'"
        },
        "source_text_reference": {
          "type": "string",
          "description": "Verbatim quote or sentence extract from the document"
        },
        "bounding_box": {
          "type": "array",
          "items": { "type": "number" },
          "minItems": 4,
          "maxItems": 4,
          "description": "Optional PDF coordinates [x0, y0, x1, y1] for auditability"
        }
      },
      "required": ["document_id", "page_number", "section", "source_text_reference"]
    }
  }
}
```

---

## 3. Decision Pathways & Flowcharts (Graph Representation)

ICMR STWs rely heavily on time-sensitive, branching clinical algorithms (e.g. STEMI time-to-treatment reperfusion pathways). Flattening these into unstructured text destroys their computational utility.

### Node Types:
- `START`: Algorithm entry point (e.g., "Patient presents with STEMI symptoms").
- `DECISION`: Conditional branching point (e.g., "Time since symptom onset: <12h vs 12-24h vs >24h", "Is facility PCI capable?").
- `ACTION`: Direct clinical action, stabilization, or administration (e.g., "Administer Aspirin 325 mg chewed + Clopidogrel 300 mg").
- `INVESTIGATION`: Diagnostic evaluation step (e.g., "12-lead ECG within 10 minutes").
- `REFERRAL`: Inter-facility transfer directive (e.g., "Immediate transfer to PCI capable hospital if transfer door-to-balloon <= 120 min").
- `TERMINAL`: Clinical endpoint (e.g., "Transfer to ICU post-PCI").

### Graph Schema Definition:
```json
{
  "flowchart": {
    "flowchart_id": "STEMI-REPERFUSION-01",
    "title": "STEMI Reperfusion and Triage Algorithm",
    "description": "Time-dependent triage from symptom onset through PCI vs fibrinolysis selection",
    "source": { ... },
    "start_node_id": "NODE-01",
    "nodes": [
      {
        "node_id": "NODE-01",
        "node_type": "START",
        "label": "Patient with STEMI within 12 hours",
        "description": "Patient presenting within 12 hours of symptom onset",
        "branches": [
          {
            "condition": "Facility is PCI capable",
            "target_node_id": "NODE-PCI-CAPABLE",
            "rationale": "Direct primary PCI indicated"
          },
          {
            "condition": "Facility is PCI incapable",
            "target_node_id": "NODE-PCI-INCAPABLE",
            "rationale": "Requires transfer or thrombolysis assessment"
          }
        ],
        "source": { ... }
      }
    ]
  }
}
```

---

## 4. Tabular Structure Model (`ClinicalTable`)

Clinical tables represent structured multidimensional relationships (such as weight-based fibrinolytic doses or risk scoring).

```json
{
  "table_id": "TAB-THROMBOLYSIS-DOSING",
  "title": "Thrombolytic Therapy Regimens & Weight Tiers",
  "headers": ["Drug", "Weight Category / Dose", "Route", "Administration Instructions"],
  "rows": [
    {
      "row_id": "ROW-01",
      "cells": {
        "Drug": "Tenecteplase",
        "Weight Category / Dose": "35 mg if 60-70 Kg; 40 mg if 70-80 Kg; 45 mg if > 80 Kg",
        "Route": "IV",
        "Administration Instructions": "Single IV bolus"
      },
      "source": { ... }
    }
  ],
  "source": { ... }
}
```

---

## 5. Structured Clinical Entities

### 5.1. Medication Model (`MedicationDose`)
Captures complete pharmacological guidance while strictly preserving provenance.
- `generic_name`: Approved international non-proprietary name (e.g., "Aspirin", "Tenecteplase").
- `drug_class`: Pharmacological category (e.g., "Antiplatelet", "Fibrinolytic", "HMG-CoA Reductase Inhibitor").
- `dosage`: Quantitative dose specification (e.g., "325 mg", "40 mg").
- `route`: Route of administration (e.g., "Oral", "Intravenous bolus", "Subcutaneous").
- `frequency`: Frequency string (e.g., "Once daily", "BD", "Stat").
- `duration`: Course duration (e.g., "At least 1 year", "Indefinite").
- `is_loading_dose`: Boolean flag indicating if this is an initial bolus/loading dose.
- `maintenance_dose`: Complementary maintenance specification where applicable.
- `weight_based`: Boolean flag for weight-adjusted dosing.
- `weight_rules`: Specific dosage tiers by patient weight.
- `contraindications`: Specific contraindications noted for this medication.
- `monitoring_parameters`: Laboratory or hemodynamic checks required (e.g., "APTT 50-70 sec", "Serum K+ and creatinine").
- `source`: Mandatory `SourceReference`.

### 5.2. Diagnostic Workup & Investigations (`Investigation`)
Categorized according to clinical priority and tier availability:
- `tier`: `BASIC` / `DESIRABLE` / `OPTIONAL`.
- `name`: Name of investigation (e.g., "12-lead ECG", "Serum Troponin", "2D Echocardiography").
- `modality`: Laboratory, Imaging, Electrocardiography, Invasive.
- `purpose`: Stated clinical purpose (e.g., "Identify ST elevation", "Evaluate mechanical complications").
- `findings`: Key diagnostic findings or thresholds specified in the STW.
- `source`: Mandatory `SourceReference`.

### 5.3. Healthcare Delivery Tier Management (`HealthcareTierManagement`)
Maps management recommendations to India's tiered health system:
- `tier`: `PHC_CHC` (Primary/Community Health Centre), `DISTRICT_HOSPITAL` (Secondary), `TERTIARY_PCI` (Tertiary / Specialty).
- `immediate_actions`: Sequential actions to be performed at this level.
- `medications_initiated`: List of drugs that must be started at this level.
- `investigations_required`: Laboratory or diagnostic tests performed at this level.
- `referral_triggers`: Explicit clinical criteria necessitating transfer to the next level.
- `source`: Mandatory `SourceReference`.

### 5.4. Contraindications & Safety Rules (`Contraindication`)
- `type`: `ABSOLUTE` vs `RELATIVE`.
- `intervention_affected`: Procedure or drug class affected (e.g., "Thrombolytic therapy", "Prasugrel").
- `condition_description`: Clinical finding or historical event (e.g., "Previous intracerebral hemorrhage", "Ischemic stroke in last 6 months").
- `timeframe`: Time constraint where stated (e.g., "within 1 month", "in last 6 months").
- `source`: Mandatory `SourceReference`.

---

## 6. Top-Level Container (`STWDocument`)

The top-level entity binds all dimensions together:

```json
{
  "metadata": {
    "document_id": "ICMR-CARD-006",
    "title": "ST Elevation Myocardial Infarction (STEMI)",
    "specialty": "Cardiology",
    "condition": "STEMI",
    "icd_11_code": "BA41.0",
    "volume": "Volume 1",
    "edition": "2019",
    "source_organization": "Indian Council of Medical Research (ICMR)",
    "official_url": "https://www.icmr.gov.in/icmrobject/uploads/STWs/1768823342_cardiology_1-5.pdf",
    "source_file": "data/raw/cardiology/1768823342_cardiology_1-5.pdf",
    "total_pages": 1
  },
  "clinical_presentation": { ... },
  "diagnostic_criteria": [ ... ],
  "investigations": [ ... ],
  "tier_management": [ ... ],
  "medications": [ ... ],
  "contraindications": [ ... ],
  "referral_criteria": [ ... ],
  "flowcharts": [ ... ],
  "tables": [ ... ],
  "references": [ ... ],
  "abbreviations": { ... }
}
```
