"""
ICMR STW Secure Download Script
Downloads approved Cardiology STW documents from the official ICMR portal.
Enforces strict domain verification, SHA-256 integrity calculation,
PyMuPDF page verification, and immutable versioned cataloguing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import pymupdf
import requests
import yaml
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("download_stws")

CATALOG_COLUMNS = [
    "stw_id",
    "volume",
    "specialty",
    "condition",
    "document_type",
    "source_organization",
    "source_url",
    "local_path",
    "download_date",
    "document_hash",
    "version",
    "status",
    "file_size_bytes",
    "page_count",
]


def load_config(config_path: Path | str = "config/settings.yaml") -> dict[str, Any]:
    """Load configuration settings from YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path.resolve()}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def is_allowed_domain(url: str, allowed_domains: list[str]) -> bool:
    """Validate that URL domain is strictly within the allowed ICMR whitelist."""
    hostname = urlparse(url).hostname or ""
    return any(hostname == domain or hostname.endswith("." + domain) for domain in allowed_domains)


def build_session(max_retries: int = 3, backoff_factor: float = 1.5) -> requests.Session:
    """Build a robust requests Session with automatic retries on network failures."""
    session = requests.Session()
    retries = Retry(
        total=max_retries,
        backoff_factor=backoff_factor,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def normalize_string(s: str) -> str:
    """Normalize string for robust condition matching."""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def match_approved_condition(title: str, approved_list: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Match discovered document title to an approved condition configuration."""
    norm_title = normalize_string(title)

    # 1. Exact normalized match first
    for app in approved_list:
        norm_app = normalize_string(app["condition"])
        if norm_app == norm_title:
            return app

    # 2. Specific clinical variants (e.g. Bradyarrythmias / Bradyarrhythmias)
    if "brady" in norm_title:
        for app in approved_list:
            if "brady" in normalize_string(app["condition"]):
                return app

    # 3. Fuzzy containment with strict discrimination for STEMI vs NSTEMI
    for app in approved_list:
        norm_app = normalize_string(app["condition"])
        if norm_title == "stemi" and norm_app != "stemi":
            continue
        if norm_title == "nstemi" and norm_app != "nstemi":
            continue
        if norm_app in norm_title or norm_title in norm_app:
            return app
    return None


def calculate_sha256(filepath: Path) -> str:
    """Calculate SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


def inspect_pdf(filepath: Path) -> tuple[bool, int, str]:
    """Verify that file is a valid PDF and return (is_valid, page_count, error_msg)."""
    if not filepath.exists():
        return False, 0, "File does not exist"

    # Check magic bytes
    with open(filepath, "rb") as f:
        header = f.read(4)
        if header != b"%PDF":
            return False, 0, f"Invalid PDF signature: {header!r}"

    try:
        doc = pymupdf.open(filepath)
        page_count = doc.page_count
        doc.close()
        if page_count < 1:
            return False, 0, "PDF contains 0 pages"
        return True, page_count, ""
    except Exception as e:
        return False, 0, f"PyMuPDF could not read file: {e}"


def load_existing_catalog(catalog_path: Path) -> pd.DataFrame:
    """Load existing catalog CSV or create empty DataFrame with standard columns."""
    if catalog_path.exists() and catalog_path.stat().st_size > 0:
        return pd.read_csv(catalog_path, dtype=str)
    return pd.DataFrame(columns=CATALOG_COLUMNS)


def save_catalog(df: pd.DataFrame, catalog_path: Path) -> None:
    """Persist catalog DataFrame to CSV."""
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    # Ensure standard column order
    cols = [c for c in CATALOG_COLUMNS if c in df.columns]
    for c in df.columns:
        if c not in cols:
            cols.append(c)
    df[cols].to_csv(catalog_path, index=False, encoding="utf-8")


def download_file(
    url: str,
    target_path: Path,
    session: requests.Session,
    user_agent: str,
    allowed_domains: list[str],
    timeout: int = 30,
) -> tuple[bool, str]:
    """
    Download a file via streaming GET with redirect and domain safety checks.
    Returns (success, message).
    """
    if not is_allowed_domain(url, allowed_domains):
        return False, f"Domain of URL {url} not permitted by policy"

    headers = {"User-Agent": user_agent}

    # Ensure target parent directory exists
    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_target = target_path.with_suffix(".tmp")

    try:
        with session.get(url, headers=headers, stream=True, timeout=timeout, allow_redirects=True) as resp:
            # Check final URL after redirects for security
            if not is_allowed_domain(resp.url, allowed_domains):
                return False, f"Redirect to untrusted domain: {resp.url}"

            if resp.status_code != 200:
                return False, f"HTTP Error {resp.status_code}: {resp.reason}"

            with open(temp_target, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)

        # Atomic replacement
        if target_path.exists():
            target_path.unlink()
        temp_target.rename(target_path)
        return True, "Download successful"
    except Exception as e:
        if temp_target.exists():
            temp_target.unlink()
        return False, f"Download failed: {e}"


def run_download_pipeline(
    config_path: Path | str = "config/settings.yaml",
    force: bool = False,
) -> list[dict[str, Any]]:
    """Execute download and cataloguing pipeline for approved Cardiology STWs."""
    config = load_config(config_path)
    paths_cfg = config.get("paths", {})
    source_cfg = config.get("source", {})
    pilot_cfg = config.get("pilot", {})
    net_cfg = config.get("network", {})

    raw_cardio_dir = Path(paths_cfg.get("cardiology_raw_dir", "data/raw/cardiology"))
    catalog_path = Path(paths_cfg.get("catalog_file", "data/metadata/stw_catalog.csv"))
    discovered_path = Path(paths_cfg.get("discovered_file", "data/metadata/discovered_stws.json"))

    allowed_domains = source_cfg.get("allowed_domains", ["icmr.gov.in"])
    user_agent = net_cfg.get("user_agent", "Mozilla/5.0")
    timeout = net_cfg.get("timeout_seconds", 30)
    max_retries = net_cfg.get("max_retries", 3)
    backoff = net_cfg.get("backoff_factor", 1.5)

    specialty = pilot_cfg.get("specialty", "Cardiology")
    volume = pilot_cfg.get("volume", "Volume 1")
    approved_conditions = pilot_cfg.get("approved_conditions", [])
    source_org = config.get("project", {}).get("source_organization", "Indian Council of Medical Research (ICMR)")

    if not discovered_path.exists():
        logger.error("Discovered manifest not found at %s. Run discover_stws.py first.", discovered_path)
        raise FileNotFoundError(f"Manifest missing: {discovered_path}")

    with open(discovered_path, "r", encoding="utf-8") as f:
        discovered_data = json.load(f)

    discovered_docs = discovered_data.get("documents", [])
    logger.info("Found %d documents in discovery manifest.", len(discovered_docs))

    catalog_df = load_existing_catalog(catalog_path)
    session = build_session(max_retries=max_retries, backoff_factor=backoff)
    results: list[dict[str, Any]] = []

    for item in discovered_docs:
        raw_title = item.get("title", "")
        pdf_url = item.get("pdf_url", "")
        doc_type_discovered = item.get("document_type", "individual_stw")

        matched = match_approved_condition(raw_title, approved_conditions)
        if not matched:
            logger.info("Skipping unapproved or out-of-scope document: '%s'", raw_title)
            continue

        stw_id = matched["stw_id"]
        condition_name = matched["condition"]
        document_type = matched.get("document_type", doc_type_discovered)

        # Derive clean original filename from URL
        url_filename = Path(urlparse(pdf_url).path).name
        if not url_filename:
            url_filename = f"{stw_id}.pdf"

        dest_file = raw_cardio_dir / url_filename
        posix_local_path = dest_file.as_posix()

        # Check existing catalog entry for this stw_id
        existing_rows = catalog_df[catalog_df["stw_id"] == stw_id]
        current_version = "1.0"
        should_download = True

        if dest_file.exists() and not force:
            # File exists locally. Verify its integrity
            is_pdf, pages, err = inspect_pdf(dest_file)
            if is_pdf:
                local_hash = calculate_sha256(dest_file)
                logger.info("[%s] Local copy already exists and verified (%s, %d pages).", stw_id, condition_name, pages)
                should_download = False
                download_timestamp = datetime.now(timezone.utc).isoformat()
                file_size = dest_file.stat().st_size

                if not existing_rows.empty:
                    # Update status and existing hash if needed
                    idx = existing_rows.index[0]
                    current_version = str(catalog_df.at[idx, "version"])
                    download_timestamp = str(catalog_df.at[idx, "download_date"])

                entry = {
                    "stw_id": stw_id,
                    "volume": volume,
                    "specialty": specialty,
                    "condition": condition_name,
                    "document_type": document_type,
                    "source_organization": source_org,
                    "source_url": pdf_url,
                    "local_path": posix_local_path,
                    "download_date": download_timestamp,
                    "document_hash": local_hash,
                    "version": current_version,
                    "status": "verified",
                    "file_size_bytes": str(file_size),
                    "page_count": str(pages),
                }
                results.append(entry)

        if should_download:
            logger.info("[%s] Downloading '%s' from %s...", stw_id, condition_name, pdf_url)
            success, msg = download_file(
                url=pdf_url,
                target_path=dest_file,
                session=session,
                user_agent=user_agent,
                allowed_domains=allowed_domains,
                timeout=timeout,
            )

            if not success:
                logger.error("[%s] Failed to download %s: %s", stw_id, condition_name, msg)
                entry = {
                    "stw_id": stw_id,
                    "volume": volume,
                    "specialty": specialty,
                    "condition": condition_name,
                    "document_type": document_type,
                    "source_organization": source_org,
                    "source_url": pdf_url,
                    "local_path": posix_local_path,
                    "download_date": datetime.now(timezone.utc).isoformat(),
                    "document_hash": "",
                    "version": current_version,
                    "status": f"failed: {msg}",
                    "file_size_bytes": "0",
                    "page_count": "0",
                }
                results.append(entry)
                continue

            # Verify downloaded PDF
            is_pdf, pages, err = inspect_pdf(dest_file)
            if not is_pdf:
                logger.error("[%s] Corrupt or invalid PDF for %s: %s", stw_id, condition_name, err)
                dest_file.unlink(missing_ok=True)
                entry = {
                    "stw_id": stw_id,
                    "volume": volume,
                    "specialty": specialty,
                    "condition": condition_name,
                    "document_type": document_type,
                    "source_organization": source_org,
                    "source_url": pdf_url,
                    "local_path": posix_local_path,
                    "download_date": datetime.now(timezone.utc).isoformat(),
                    "document_hash": "",
                    "version": current_version,
                    "status": f"failed: {err}",
                    "file_size_bytes": "0",
                    "page_count": "0",
                }
                results.append(entry)
                continue

            file_hash = calculate_sha256(dest_file)
            file_size = dest_file.stat().st_size
            now_iso = datetime.now(timezone.utc).isoformat()

            # Check if this is an updated version compared to previous catalog record
            if not existing_rows.empty:
                prev_hash = existing_rows.iloc[0].get("document_hash", "")
                prev_ver = existing_rows.iloc[0].get("version", "1.0")
                if prev_hash and prev_hash != file_hash:
                    # Increment minor version
                    try:
                        major, minor = prev_ver.split(".")
                        current_version = f"{major}.{int(minor) + 1}"
                    except Exception:
                        current_version = "1.1"
                    logger.warning("[%s] Document hash changed upstream! New version: %s", stw_id, current_version)

            entry = {
                "stw_id": stw_id,
                "volume": volume,
                "specialty": specialty,
                "condition": condition_name,
                "document_type": document_type,
                "source_organization": source_org,
                "source_url": pdf_url,
                "local_path": posix_local_path,
                "download_date": now_iso,
                "document_hash": file_hash,
                "version": current_version,
                "status": "verified",
                "file_size_bytes": str(file_size),
                "page_count": str(pages),
            }
            results.append(entry)
            logger.info("[%s] Ingestion verified: %d pages, %d bytes, SHA-256: %s...", stw_id, pages, file_size, file_hash[:12])

    # Update catalogue DataFrame
    for res in results:
        # If exists, replace row; else append
        if not catalog_df.empty and (catalog_df["stw_id"] == res["stw_id"]).any():
            idx = catalog_df[catalog_df["stw_id"] == res["stw_id"]].index[0]
            for k, v in res.items():
                catalog_df.at[idx, k] = v
        else:
            catalog_df = pd.concat([catalog_df, pd.DataFrame([res])], ignore_index=True)

    save_catalog(catalog_df, catalog_path)
    logger.info("Catalog updated with %d entries at %s", len(catalog_df), catalog_path)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Download and catalog official ICMR Cardiology STWs.")
    parser.add_argument("--config", default="config/settings.yaml", help="Path to settings.yaml")
    parser.add_argument("--force", action="store_true", help="Force re-download even if file exists locally")
    args = parser.parse_args()

    try:
        results = run_download_pipeline(config_path=args.config, force=args.force)
    except Exception as e:
        logger.error("Download pipeline failed: %s", e)
        return 1

    failed_count = sum(1 for r in results if r["status"] != "verified")
    print("\n" + "=" * 80)
    print(f"DOWNLOAD & CATALOGUE SUMMARY: {len(results)} processed, {failed_count} failed")
    print("=" * 80)
    for r in results:
        print(f"[{r['stw_id']}] {r['condition']} ({r['document_type']}) - Status: {r['status']}")
        print(f"    Path:  {r['local_path']}")
        print(f"    Hash:  {r['document_hash'][:20]}..." if r['document_hash'] else "    Hash:  None")
        print(f"    Pages: {r['page_count']} | Size: {r['file_size_bytes']} bytes | Version: {r['version']}")
    print("=" * 80 + "\n")
    return 1 if failed_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
