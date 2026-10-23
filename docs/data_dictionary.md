# Data Dictionary: ICMR STW AI Catalog

This document defines the schema and data governance rules for the ICMR Standard Treatment Workflow (STW) catalog (`data/metadata/stw_catalog.csv`).

## Overview

The STW Catalog is the central metadata register for all ingested ICMR Standard Treatment Workflow documents. It maintains strict document provenance, cryptographic integrity checks, and version control.

## Schema Specifications

| Column Name | Data Type | Nullable | Description | Allowed Values / Constraints | Example |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `stw_id` | String | No | Unique, stable identifier assigned to each distinct STW document in the repository. | Format: `ICMR-<SPECIALTY_CODE>-<3_DIGIT_SEQ>` (e.g., `ICMR-CARD-001`) | `ICMR-CARD-001` |
| `volume` | String | No | Official ICMR STW publication volume. | e.g., `Volume 1`, `Volume 2`, `Volume 3`, etc. | `Volume 1` |
| `specialty` | String | No | Clinical domain or medical specialty as designated by ICMR. | Must match official ICMR specialty names (e.g., `Cardiology`, `Neurology`, etc.) | `Cardiology` |
| `condition` | String | No | Specific clinical condition or disease title addressed by the workflow. | Non-empty string; normalized title | `Atrial Fibrillation` |
| `document_type` | String | No | Classification of the document scope. | `individual_stw` (condition-specific workflow), `consolidated_stw` (full specialty compilation) | `individual_stw` |
| `source_organization` | String | No | Official publishing authority. | Must be `Indian Council of Medical Research (ICMR)` | `Indian Council of Medical Research (ICMR)` |
| `source_url` | String | No | Full canonical URL from which the PDF was fetched. | Must originate from approved ICMR domain (`*.icmr.gov.in` or `*.icmr.nic.in`) | `https://www.icmr.gov.in/icmrobject/uploads/STWs/1768823343_cardiology_1-1.pdf` |
| `local_path` | String | No | Relative filesystem path to the immutable raw PDF file from repository root. | Path formatted with forward slashes (e.g., `data/raw/<specialty>/<filename>.pdf`) | `data/raw/cardiology/1768823343_cardiology_1-1.pdf` |
| `download_date` | String | No | ISO 8601 UTC timestamp recording when the document was retrieved and verified. | Format: `YYYY-MM-DDTHH:MM:SSZ` | `2026-09-12T07:15:30Z` |
| `document_hash` | String | No | Cryptographic SHA-256 digest of the raw unmodified PDF file. | 64 lowercase hexadecimal characters | `7d1a...c4b2` |
| `version` | String | No | Semantic version of the document entry. Incremented if ICMR publishes updated content at the endpoint. | Format: `MAJOR.MINOR` (default initial version `1.0`) | `1.0` |
| `status` | String | No | Lifecycle status of the document in the repository. | `verified` (downloaded and passed validation), `pending` (discovered but not downloaded), `deprecated` (superseded by newer version), `failed` (validation error) | `verified` |
| `file_size_bytes` | Integer | No | Exact size of the raw PDF file in bytes. | Positive integer | `277780` |
| `page_count` | Integer | No | Total number of pages in the PDF document, verified via PyMuPDF. | Positive integer >= 1 | `1` |

## Integrity and Immutability Rules

1. **Cryptographic Invariance**: Once a PDF is saved under `data/raw/`, its bytes must NEVER be modified, compressed, watermarked, or edited.
2. **Hash Verification**: The `document_hash` must match the output of `hashlib.sha256(open(local_path, 'rb').read()).hexdigest()` at all times.
3. **No Phantom Records**: Every row in `stw_catalog.csv` with status `verified` must point to an existing, readable, valid PDF.
4. **No Uncatalogued Assets**: Every PDF in `data/raw/<specialty>/` must have a corresponding entry in `stw_catalog.csv`.
5. **Versioning on Drift**: If the upstream ICMR server updates a document, the original raw file remains untouched under its versioned name or hash, and a new catalog record or incremented version is created.
