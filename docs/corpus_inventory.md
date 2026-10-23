# ICMR Standard Treatment Workflows (STW) — Corpus Inventory

## Overview
This document details the multi-specialty corpus inventory for the ICMR Standard Treatment Workflow platform. The platform has expanded beyond the initial 7-document Cardiology pilot into a generalizable, multi-specialty clinical evidence retrieval and decision support architecture.

---

## 1. Master Portal Discovery Statistics
- **Official Source Portal**: `https://www.icmr.gov.in/standard-treatment-workflows-stws`
- **Total Discovered STW Guidelines**: 187 official documents
- **Total Medical Specialties Represented**: 27 specialties
- **Specialty Directory**:
  1. Adult Extrapulmonary Tuberculosis
  2. Cardiology (Pilot baseline)
  3. Cardiothoracic and Vascular Surgery (CTVS)
  4. Dermatology
  5. ENT
  6. Endocrinology
  7. Gastroenterology
  8. General Surgery
  9. Haemolytic Anaemia
  10. Infertility
  11. Interventional Radiology
  12. Investigations Treatment
  13. Neonatology
  14. Nephrology
  15. Neurology (Phase 8 Expansion)
  16. Neurosurgery
  17. Obstetrics & Gynecology
  18. Oncology
  19. Ophthalmology
  20. Orthopaedics
  21. Paediatric Surgery
  22. Paediatric Tuberculosis
  23. Paediatrics
  24. Pediatric Cardiology
  25. Psychiatry
  26. Pulmonology
  27. Urology

---

## 2. Ingested Guidelines & Version Status

| Document ID | Specialty | Condition | Edition / Version | Review Status | Production Status | Total Units | Production Units | Quarantined Units |
|---|---|---|---|---|---|---|---|---|
| `ICMR-CARD-001` | Cardiology | Atrial Fibrillation | v1.0 | approved | Active Retrieval | 48 | 34 | 14 |
| `ICMR-CARD-002` | Cardiology | NSTE-ACS | v1.0 | approved | Active Retrieval | 32 | 23 | 9 |
| `ICMR-CARD-003` | Cardiology | Heart Failure | v1.0 | approved | Active Retrieval | 45 | 32 | 13 |
| `ICMR-CARD-004` | Cardiology | Stable CAD | v1.0 | approved | Active Retrieval | 68 | 49 | 19 |
| `ICMR-CARD-005` | Cardiology | Hypertension | v1.0 | approved | Active Retrieval | 54 | 39 | 15 |
| `ICMR-CARD-006` | Cardiology | Dyslipidemia | v1.0 | approved | Active Retrieval | 72 | 52 | 20 |
| `ICMR-CARD-007` | Cardiology | Consolidated Cardiology STW | v1.0 | approved | Active Retrieval | 274 | 197 | 77 |
| `ICMR-NEUR-001` | Neurology | Acute Ischemic Stroke | v1.0 | needs_review | Quarantined | 12 | 0 | 12 |
| `ICMR-NEUR-002` | Neurology | Epilepsy | v1.0 | needs_review | Quarantined | 24 | 0 | 24 |
| `ICMR-NEUR-003` | Neurology | Parkinson's Disease | v1.0 | needs_review | Quarantined | 28 | 0 | 28 |
| `ICMR-NEUR-004` | Neurology | Migraine | v1.0 | needs_review | Quarantined | 16 | 0 | 16 |
| `ICMR-NEUR-005` | Neurology | Bacterial Meningitis | v1.0 | needs_review | Quarantined | 34 | 0 | 34 |
| `ICMR-NEUR-006` | Neurology | Peripheral Neuropathy | v1.0 | needs_review | Quarantined | 15 | 0 | 15 |
| `ICMR-NEUR-007` | Neurology | Consolidated Neurology STW | v1.0 | needs_review | Quarantined | 20 | 0 | 20 |

---

## 3. Clinical Safety Invariant: Quarantine Rule
In adherence to strict clinical safety principles:
1. **Zero Auto-Promotion**: Newly ingested clinical specialties (such as Neurology) are **never** auto-promoted into the production hybrid retrieval index.
2. **Quarantine State**: All newly extracted knowledge units automatically enter the human-in-the-loop review queue (`requires_manual_review = 1`).
3. **Verified Production Index**: Only explicitly approved clinical units (the 426 validated Cardiology pilot units) remain active in production search. Unreviewed specialty units return safe clinical abstention (`INSUFFICIENT_APPROVED_EVIDENCE`) until verified by a qualified clinician.

---

## 4. Review Queue Backlog & Priority Classification
- **Total Flagged Units in Queue**: 316
- **Breakdown by Specialty**:
  - Cardiology: 167 items
  - Neurology: 149 items
- **Breakdown by Clinical Priority**:
  - **HIGH Priority** (196 items): Emergency treatment workflows, medication dosing, contraindications, PCI/thrombolysis referral criteria.
  - **MEDIUM Priority** (103 items): Diagnostic thresholds, laboratory investigations, level-of-care tier actions.
  - **LOW Priority** (17 items): General background terminology, structural formatting, metadata artifacts.
