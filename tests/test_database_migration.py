"""Tests for SQLite database schema migration and zero-data-loss verification."""

import shutil
import sqlite3
from pathlib import Path
import pytest

from src.knowledge.migration import run_migration


def test_migration_schema_integrity():
    db_path = Path("data/knowledge/knowledge.db")
    assert db_path.exists(), "Knowledge database must exist."

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    try:
        # Check document_versions exists and has required columns
        cursor.execute("PRAGMA table_info(document_versions)")
        dv_cols = {row[1] for row in cursor.fetchall()}
        required_dv_cols = {
            "version_record_id", "document_id", "specialty", "condition",
            "version_id", "version_label", "source_url", "content_hash",
            "is_current", "review_status", "version_precedence", "created_at"
        }
        for col in required_dv_cols:
            assert col in dv_cols, f"Missing column in document_versions: {col}"

        # Check knowledge_units has version_id
        cursor.execute("PRAGMA table_info(knowledge_units)")
        ku_cols = {row[1] for row in cursor.fetchall()}
        assert "version_id" in ku_cols

        # Check review_items has specialty
        cursor.execute("PRAGMA table_info(review_items)")
        ri_cols = {row[1] for row in cursor.fetchall()}
        assert "specialty" in ri_cols
    finally:
        conn.close()


def test_backup_file_exists():
    backup_path = Path("data/knowledge/knowledge.db.bak")
    assert backup_path.exists(), "Pre-migration database backup must exist."
    assert backup_path.stat().st_size > 0, "Backup file must not be empty."


def test_migration_idempotence(tmp_path):
    # Copy current db to a temporary path
    temp_db = tmp_path / "test_knowledge.db"
    temp_backup = tmp_path / "test_knowledge.db.bak"
    shutil.copy2(Path("data/knowledge/knowledge.db"), temp_db)

    # Run migration on temporary copy
    res1 = run_migration(db_path=temp_db, backup_path=temp_backup)
    assert res1["status"] == "SUCCESS"
    assert res1["production_units_preserved"] is True
    assert res1["review_items_preserved"] is True

    # Run migration a second time to ensure idempotency
    res2 = run_migration(db_path=temp_db, backup_path=temp_backup)
    assert res2["status"] == "SUCCESS"
    assert res2["production_units"] == res1["production_units"]
    assert res2["review_items"] == res1["review_items"]
