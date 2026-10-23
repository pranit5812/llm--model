"""
ICMR STW Discovery Script
Discovers Standard Treatment Workflow documents published on the official ICMR portal.
Produces a structured discovery manifest without downloading the documents.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
import yaml
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("discover_stws")


def load_config(config_path: Path | str = "config/settings.yaml") -> dict[str, Any]:
    """Load configuration settings from YAML file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {path.resolve()}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def is_allowed_domain(url: str, allowed_domains: list[str]) -> bool:
    """Validate that URL domain is in the allowed list."""
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    return any(hostname == domain or hostname.endswith("." + domain) for domain in allowed_domains)


def fetch_landing_page(url: str, user_agent: str, timeout: int = 30) -> str:
    """Fetch official ICMR STW landing page HTML."""
    headers = {"User-Agent": user_agent}
    logger.info("Connecting to official ICMR portal: %s", url)
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.text


def parse_specialty_table(
    soup: BeautifulSoup,
    accordion_id: str,
    base_url: str,
    allowed_domains: list[str],
    specialty_name: str,
) -> list[dict[str, Any]]:
    """Parse table of STWs within an accordion collapse element."""
    collapse_div = soup.find(id=accordion_id)
    if not collapse_div:
        logger.warning("Accordion section id='%s' not found in HTML.", accordion_id)
        return []

    table = collapse_div.find("table")
    if not table:
        logger.warning("No table found inside section id='%s'.", accordion_id)
        return []

    rows = table.find("tbody").find_all("tr") if table.find("tbody") else table.find_all("tr")
    discovered_items: list[dict[str, Any]] = []

    for row in rows:
        cols = row.find_all("td")
        if len(cols) < 3:
            continue

        seq_text = cols[0].get_text(strip=True)
        title_text = cols[1].get_text(strip=True)

        # Look for PDF links in 3rd column
        links = cols[2].find_all("a", href=True)
        pdf_url = ""
        stated_size = ""

        for a in links:
            href = a["href"].strip()
            if href.lower().endswith(".pdf") or "/stws/" in href.lower():
                pdf_url = urljoin(base_url, href)
                # Check for stated size badge/span
                size_span = a.find("span", class_="value")
                if size_span and "(" in size_span.text:
                    stated_size = size_span.text.strip("() ")
                elif "(" in a.text:
                    match = re.search(r"\(([^)]+)\)", a.text)
                    if match:
                        stated_size = match.group(1).strip()
                break

        if not pdf_url:
            continue

        if not is_allowed_domain(pdf_url, allowed_domains):
            logger.error("Rejected non-ICMR link for '%s': %s", title_text, pdf_url)
            continue

        # Determine if individual condition or consolidated "All"
        is_all = bool(re.search(r"\(All\)|_all\.pdf", title_text, re.IGNORECASE) or "_all.pdf" in pdf_url.lower())
        doc_type = "consolidated_stw" if is_all else "individual_stw"

        item = {
            "sequence": seq_text,
            "specialty": specialty_name,
            "title": title_text,
            "pdf_url": pdf_url,
            "stated_size": stated_size,
            "document_type": doc_type,
            "source_domain": urlparse(pdf_url).hostname,
        }
        discovered_items.append(item)

    return discovered_items


def discover_cardiology_stws(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Discover official Cardiology STW documents based on configuration."""
    source_cfg = config.get("source", {})
    pilot_cfg = config.get("pilot", {})
    network_cfg = config.get("network", {})

    workflows_url = source_cfg.get("workflows_url", "https://www.icmr.gov.in/standard-treatment-workflows-stws")
    base_url = source_cfg.get("base_url", "https://www.icmr.gov.in")
    allowed_domains = source_cfg.get("allowed_domains", ["icmr.gov.in"])
    user_agent = network_cfg.get("user_agent", "Mozilla/5.0")
    timeout = network_cfg.get("timeout_seconds", 30)

    accordion_id = pilot_cfg.get("accordion_id", "eleven")
    specialty_name = pilot_cfg.get("specialty", "Cardiology")

    html = fetch_landing_page(workflows_url, user_agent=user_agent, timeout=timeout)
    soup = BeautifulSoup(html, "html.parser")

    items = parse_specialty_table(
        soup=soup,
        accordion_id=accordion_id,
        base_url=base_url,
        allowed_domains=allowed_domains,
        specialty_name=specialty_name,
    )

    logger.info("Discovered %d STW documents for %s.", len(items), specialty_name)
    return items


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover official ICMR STW documents.")
    parser.add_argument("--config", default="config/settings.yaml", help="Path to settings.yaml")
    parser.add_argument("--output", default=None, help="Path to save discovered JSON manifest")
    args = parser.parse_args()

    config = load_config(args.config)
    output_path = Path(args.output or config["paths"].get("discovered_file", "data/metadata/discovered_stws.json"))
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        discovered = discover_cardiology_stws(config)
    except Exception as e:
        logger.error("Failed to discover STW documents: %s", e)
        return 1

    manifest = {
        "metadata": {
            "source_portal": config["source"]["workflows_url"],
            "specialty": config["pilot"]["specialty"],
            "count": len(discovered),
        },
        "documents": discovered,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    logger.info("Discovery manifest saved successfully: %s", output_path)
    print("\n" + "=" * 80)
    print(f"DISCOVERED ICMR {config['pilot']['specialty'].upper()} STW DOCUMENTS ({len(discovered)} total)")
    print("=" * 80)
    for doc in discovered:
        print(f"[{doc['sequence']}] {doc['title']} ({doc['document_type']})")
        print(f"    URL:  {doc['pdf_url']}")
        print(f"    Size: {doc['stated_size'] or 'N/A'}")
    print("=" * 80 + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
