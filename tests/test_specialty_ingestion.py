"""Tests for specialty ingestion and quarantine safety rules."""

import json
import sqlite3
from pathlib import Path
import pytest


def test_neurology_ingestion_artifacts():
    structured_dir = Path("data/processed/structured")
    neur_files = sorted(list(structured_dir.rglob("ICMR-NEUR-*.json")))
    assert len(neur_files) == 7, f"Expected 7 ingested Neurology guidelines, found {len(neur_files)}"

    for nf in neur_files:
        with open(nf, "r", encoding="utf-8") as f:
            data = json.load(f)
        assert "metadata" in data
        meta = data["metadata"]
        assert meta["specialty"] == "Neurology"
        assert meta["document_id"].startswith("ICMR-NEUR-")
        assert meta["total_pages"] >= 1


def test_quarantine_invariant_enforced():
    """Verify that 100% of ingested Neurology units are quarantined in review queue."""
    db_path = Path("data/knowledge/knowledge.db")
    assert db_path.exists()

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        # Check production units for Neurology
        neur_prod = conn.execute(
            "SELECT COUNT(*) as cnt FROM knowledge_units WHERE specialty = 'Neurology' AND requires_manual_review = 0"
        ).fetchone()["cnt"]
        assert neur_prod == 0, f"Clinical safety violation: {neur_prod} unreviewed Neurology units in production!"

        # Check quarantined review units for Neurology
        neur_review = conn.execute(
            "SELECT COUNT(*) as cnt FROM knowledge_units WHERE specialty = 'Neurology' AND requires_manual_review = 1"
        ).fetchone()["cnt"]
        assert neur_review == 149, f"Expected 149 quarantined Neurology units, found {neur_review}"

        # Verify review queue sync
        q_items = conn.execute(
            "SELECT COUNT(*) as cnt FROM review_items WHERE specialty = 'Neurology'"
        ).fetchone()["cnt"]
        assert q_items == 149, f"Expected 149 Neurology review items in queue, found {q_items}"
    finally:
        conn.close()


def test_cardiology_baseline_unaffected():
    """Verify that Cardiology baseline remains exactly 426 production units and 167 review items."""
    db_path = Path("data/knowledge/knowledge.db")
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        card_prod = conn.execute(
            "SELECT COUNT(*) as cnt FROM knowledge_units WHERE specialty = 'Cardiology' AND requires_manual_review = 0"
        ).fetchone()["cnt"]
        assert card_prod == 426, f"Cardiology regression: expected 426 production units, got {card_prod}"

        card_review = conn.execute(
            "SELECT COUNT(*) as cnt FROM knowledge_units WHERE specialty = 'Cardiology' AND requires_manual_review = 1"
        ).fetchone()["cnt"]
        assert card_review == 167, f"Cardiology regression: expected 167 review units, got {card_review}"
    finally:
        conn.close()
