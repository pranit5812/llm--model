"""Tests for Phase 6 Review API Endpoints and Web Dashboard Route."""

from __future__ import annotations

import shutil
from pathlib import Path

import httpx
import pytest

from src.api.routes import create_app
from src.review.queue import ReviewQueue


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
def review_app(tmp_path: Path):
    orig_kb = Path("data/knowledge")
    test_kb = tmp_path / "knowledge"
    shutil.copytree(orig_kb, test_kb)

    # Sync review items in temp db
    queue = ReviewQueue(db_path=test_kb / "knowledge.db")
    queue.sync_from_knowledge_units()

    return create_app(
        structured_dir=Path("data/processed/structured"),
        knowledge_dir=test_kb,
    )


@pytest.mark.anyio
async def test_review_ui_endpoint(review_app):
    transport = httpx.ASGITransport(app=review_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/review")
        assert res.status_code == 200
        assert "Clinical Knowledge Verification Portal" in res.text
        assert "review.js" in res.text


@pytest.mark.anyio
async def test_review_summary_endpoint(review_app):
    transport = httpx.ASGITransport(app=review_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/review/summary")
        assert res.status_code == 200
        data = res.json()
        assert data["total_items"] >= 167
        assert data["pending"] >= 167
        if "by_specialty" in data and "Cardiology" in data["by_specialty"]:
            assert data["by_specialty"]["Cardiology"] == 167
        assert "high_priority_pending" in data


@pytest.mark.anyio
async def test_review_items_filtered(review_app):
    transport = httpx.ASGITransport(app=review_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/review/items?priority=HIGH&limit=10")
        assert res.status_code == 200
        data = res.json()
        assert len(data["items"]) > 0
        assert all(item["review_priority"] == "HIGH" for item in data["items"])


@pytest.mark.anyio
async def test_review_action_endpoints_flow(review_app):
    transport = httpx.ASGITransport(app=review_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Fetch first pending item
        res = await client.get("/api/v1/review/items?limit=1")
        assert res.status_code == 200
        item = res.json()["items"][0]
        item_id = item["review_item_id"]

        # 2. Submit correction
        res_corr = await client.post(
            f"/api/v1/review/items/{item_id}/correction",
            json={
                "reviewer_id": "DR-API-TEST",
                "corrected_structured_value": "Clarified step: Transfer within 120 min.",
                "notes": "Correction note",
            },
        )
        assert res_corr.status_code == 200
        corr_data = res_corr.json()
        assert corr_data["review_status"] == "NEEDS_CORRECTION"
        assert corr_data["corrected_structured_value"] == "Clarified step: Transfer within 120 min."

        # 3. Approve item
        res_appr = await client.post(
            f"/api/v1/review/items/{item_id}/approve",
            json={
                "reviewer_id": "DR-API-TEST",
                "notes": "Approved for retrieval.",
            },
        )
        assert res_appr.status_code == 200
        appr_data = res_appr.json()
        assert appr_data["review_status"] == "APPROVED"

        # 4. Check audit log
        res_audit = await client.get(f"/api/v1/review/audit?item_id={item_id}")
        assert res_audit.status_code == 200
        logs = res_audit.json()
        assert len(logs) >= 2
        actions = [l["action"] for l in logs]
        assert "CORRECTION" in actions
        assert "APPROVE" in actions
