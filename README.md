# ICMR Standard Treatment Workflow AI (Phase 1)

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License: Proprietary](https://img.shields.io/badge/license-Clinical%20Gov-red.svg)](#)
[![Validation Status](https://img.shields.io/badge/validation-passing-brightgreen.svg)](#)

A production-grade, evidence-grounded system foundation for collecting, cataloguing, versioning, and verifying official Indian Council of Medical Research (ICMR) Standard Treatment Workflows (STWs).

---

## 1. Project Objective & Vision

The long-term goal of this project is to develop an LLM/SLM-powered clinical decision-support system to assist healthcare professionals across India in accessing standardized, evidence-grounded treatment workflows.

### Authoritative Source of Truth
This project does **not** construct an autonomous doctor, diagnostic predictor, or synthetic medical advisor. The system treats official ICMR STWs as the sole, authoritative source of clinical workflow knowledge. Under no circumstances does the system fabricate, extrapolate, or hallucinate clinical recommendations when supporting ICMR evidence is unavailable.

### Long-Term Architectural Roadmap
```
ICMR STW Documents (Official Source PDFs)
         ↓
Document Processing (Extraction & Normalization)
         ↓
Structured STW Knowledge (Graph / Entities / Decision Steps)
         ↓
Hybrid Retrieval (BM25 + Dense Semantic Search)
         ↓
LLM / SLM (Grounded Clinical Context Augmentation)
         ↓
Clinical Workflow Explanation (Interactive Decision Support)
         ↓
ICMR Evidence & Exact Citation (Traceable Verifiability)
```
> [!IMPORTANT]
> **Architectural Guardrail**: The system will **never** be built as a naive "PDF chatbot" that sends raw document text straight to an LLM context window. The structured knowledge layer is mandatory to ensure every decision step, escalation trigger, drug contraindication, and referral criterion is deterministic and grounded.

---

## 2. Phase 1 Scope: Cardiology Pilot

Phase 1 establishes the ingestion, provenance, versioning, and integrity-validation foundation. The pilot focuses exclusively on **Cardiology** STWs published on the official ICMR portal:

- **Official Source Portal**: [https://www.icmr.gov.in/standard-treatment-workflows-stws](https://www.icmr.gov.in/standard-treatment-workflows-stws)
- **Approved Cardiology Conditions**:
  1. `ICMR-CARD-001`: **Atrial Fibrillation** (`cardiology_1-1.pdf`)
  2. `ICMR-CARD-002`: **Bradyarrhythmias** (`bradyarrthymia13_2_2.pdf`)
  3. `ICMR-CARD-003`: **Heart Failure** (`cardiology_1-3.pdf`)
  4. `ICMR-CARD-004`: **NSTEMI** (`cardiology_1-4.pdf`)
  5. `ICMR-CARD-005`: **Stable Angina** (`cardiology_1-6.pdf`)
  6. `ICMR-CARD-006`: **STEMI** (`cardiology_1-5.pdf`)
  7. `ICMR-CARD-007`: **Cardiology (All)** (`cardiology_all.pdf` - 16-page consolidated guideline)

---

## 3. Repository Structure

```
icmr-stw-ai/
│
├── data/
│   ├── raw/
│   │   └── cardiology/           # Original, unmodified ICMR PDF documents
│   ├── processed/                # Normalized structured STWs (Phase 2)
│   └── metadata/
│       ├── discovered_stws.json  # Raw discovery manifest from ICMR portal
│       └── stw_catalog.csv       # Central CSV catalogue with SHA-256 digests
│
├── scripts/
│   ├── discover_stws.py          # Portal crawler & discovery manifest builder
│   ├── download_stws.py          # Safe downloader with cryptographic integrity checks
│   └── validate_documents.py     # Rigorous 11-point document integrity test suite
│
├── config/
│   └── settings.yaml             # Central configuration (URLs, whitelists, conditions)
│
├── tests/
│   ├── test_discovery.py         # Unit tests for scraping & domain whitelist logic
│   ├── test_download.py          # Unit tests for hashing, PDF inspection, matching
│   ├── test_validation.py        # Unit tests for validation rules & error handling
│   └── test_catalog.py           # Integrity & regex validation for stw_catalog.csv
│
├── docs/
│   └── data_dictionary.md        # Complete data dictionary for catalogue schema
│
├── .env.example                  # Environment configuration template
├── .gitignore                    # Git tracking rules
├── README.md                     # Project documentation & operational manual
└── requirements.txt              # Production and test dependencies
```

---

## 4. Setup & Installation

### Prerequisites
- Python 3.10+ (Python 3.11 recommended)
- Network connectivity to `www.icmr.gov.in`

### Install Dependencies
```bash
pip install -r requirements.txt
```

Core dependencies:
- `requests`: Safe HTTP streaming client with retry/backoff adapters
- `beautifulsoup4`: HTML parsing for portal discovery
- `pymupdf`: PDF signature verification and page count validation
- `pandas`: Structured CSV catalog management
- `pyyaml`: Configuration management
- `pytest`: Automated test execution

---

## 5. Operational Workflow & CLI Usage

### Step 1: Discover Available STWs
Scrapes the official ICMR portal to identify documents, without downloading:
```bash
python scripts/discover_stws.py
```
*Output*: Generates `data/metadata/discovered_stws.json` and prints discovered titles, URLs, and stated sizes.

### Step 2: Download & Catalog STWs
Securely downloads approved Cardiology STWs, enforces domain safety, calculates SHA-256 hashes, and records metadata:
```bash
python scripts/download_stws.py
```
*Flags*:
- `--force`: Force re-download even if an identical verified file exists locally.

### Step 3: Validate Repository & Document Integrity
Runs an 11-point cryptographic and metadata validation audit across all assets:
```bash
python scripts/validate_documents.py
```
Validation points:
1. `stw_id_format`: Complies with `^ICMR-[A-Z]+-\d{3}$`
2. `source_url_domain`: Originates from approved ICMR domains
3. `file_exists`: Local file exists on disk
4. `file_readable`: File can be opened for binary read
5. `pdf_signature`: Magic header bytes match `%PDF`
6. `page_count_readable`: PyMuPDF parses pages >= 1
7. `page_count_matches`: Page count matches catalogue record
8. `hash_calculable`: SHA-256 hash can be computed
9. `hash_matches_catalog`: Calculated hash matches catalogue record exactly
10. `no_duplicate_hash`: No two distinct STWs share the same hash
11. `status_verified`: Record is marked as `verified`

### Step 4: Run Automated Tests
```bash
python -m pytest tests/ -v
```

---

## 6. Document Provenance & Versioning Policy

- **Immutability**: Original downloaded PDFs under `data/raw/cardiology/` are **never** modified, reformatted, or overwritten in place.
- **Hash Tracking**: Each file's SHA-256 hash is recorded in `data/metadata/stw_catalog.csv`.
- **Drift Detection**: If an upstream document at ICMR is updated, the downloader detects a hash mismatch, preserves the previous version, increments the semantic version (`1.0` -> `1.1`), and logs the update timestamp.
- **Security Whitelist**: Requests will only download from domains matching `icmr.gov.in`, `www.icmr.gov.in`, or `main.icmr.nic.in`. Untrusted domains and external redirects are automatically rejected.

---

## 7. Phase 9: Clinical Review, Approval & Controlled Production Promotion

Phase 9 establishes the human-in-the-loop clinical governance layer under the mandate: **"One Standard of Care. Across India."**

```
Official ICMR PDF Extraction
             ↓
     [ Quarantined Unit ]  ─── requires_manual_review = 1 (Excluded from Retrieval)
             ↓
  Clinical Review Portal (/review)
  ├── Side-by-side immutable source vs extracted structured text
  ├── Two-Stage Approval (High-Risk items require 2 distinct clinicians)
  ├── Corrections alter structured payload only (Source text strictly immutable)
  └── Rejections permanently exclude unit with mandatory clinical notes
             ↓
  [ APPROVED / ELIGIBLE FOR PRODUCTION ]  (Still quarantined)
             ↓
  Pre-Promotion Compliance Engine (11 automated invariant checks)
             ↓
  Incremental Production Indexing (<100ms update to BM25 & TF-IDF, requires_manual_review = 0)
             ↓
  Active Production Search & Grounded Decision-Support Retrieval
```

### Key Safety Invariants

1. **Quarantine by Default**: Automated extraction never auto-promotes content. All newly ingested units enter the quarantine queue (`requires_manual_review = 1`).
2. **Approval != Indexing**: Setting an item to `APPROVED` / `ELIGIBLE_FOR_PRODUCTION` does not immediately index it. Promotion requires explicit validation and execution via the promotion manager.
3. **High-Risk Two-Stage Approval**: Medications, contraindications, and dosage specifications require sign-off by two distinct clinicians with mandatory justification notes.
4. **Source Immutability**: The verbatim source reference text is permanently immutable. Reviewer corrections only modify structured operational fields.
5. **Zero Cardiology Regressions**: Baseline Cardiology production index (426 units) remains fully intact and isolated.

### Clinical Review API Endpoints

- `GET /review`: Clinical Reviewer Dashboard & Interactive Workbench.
- `GET /api/review/summary`: Review queue KPIs and risk breakdown.
- `GET /api/review/items`: Filtered review queue with pagination, search, and sorting.
- `GET /api/review/items/{item_id}`: Detailed item inspect with immutable source text and audit history.
- `POST /api/review/items/{item_id}/start`: Claim unit for review (`IN_REVIEW`).
- `POST /api/review/items/{item_id}/approve`: Clinically approve unit (enforces two-stage approval for high-risk units).
- `POST /api/review/items/{item_id}/correct`: Correct extraction attributes (preserves source text verbatim).
- `POST /api/review/items/{item_id}/reject`: Permanently reject unit with mandatory clinical justification.
- `POST /api/review/items/{item_id}/promote`: Execute 11-point pre-promotion validation and incremental production indexing.

---

## 8. Running the Application & Test Suite

### Running the API & Review Workbench
```bash
# Start the FastAPI service (Chat UI + Retrieval API + Clinical Review Workbench)
python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000 --reload
```
- **Clinical Chat Assistant UI**: [http://localhost:8000](http://localhost:8000)
- **Clinical Review Workbench**: [http://localhost:8000/review](http://localhost:8000/review)
- **Interactive API Documentation (Swagger)**: [http://localhost:8000/docs](http://localhost:8000/docs)

### Running Automated Test Suites
```bash
# Run the complete test suite (210/210 passing tests)
venv\Scripts\pytest -v

# Run the Phase 9 Clinical Review & Promotion test suite
venv\Scripts\pytest tests/test_review_queue.py tests/test_review_approval.py tests/test_review_api.py tests/test_review_lifecycle.py tests/test_high_risk_two_stage_approval.py tests/test_promotion_validation.py tests/test_end_to_end_review_to_production.py -v

# Run the Multi-Specialty Safety Benchmark
venv\Scripts\python scripts/evaluate_multispecialty.py
```

