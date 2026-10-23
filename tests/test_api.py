"""Tests for FastAPI REST endpoints of the ICMR STW Retrieval system."""

import httpx
import pytest

from src.api.routes import create_app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module")
def app():
    return create_app()


@pytest.mark.anyio
async def test_health_check(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["total_production_units"] == 426
        assert data["total_documents"] == 7


@pytest.mark.anyio
async def test_list_documents(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/documents")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) == 7
        doc_ids = [d["document_id"] for d in data]
        assert "ICMR-CARD-006" in doc_ids


@pytest.mark.anyio
async def test_get_document_detail(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/documents/ICMR-CARD-006")
        assert res.status_code == 200
        data = res.json()
        assert data["document_id"] == "ICMR-CARD-006"
        assert data["condition"] == "STEMI"
        assert data["production_units"] > 0


@pytest.mark.anyio
async def test_get_nonexistent_document_detail(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/documents/NON-EXISTENT")
        assert res.status_code == 404


@pytest.mark.anyio
async def test_retrieve_positive_query(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        req = {
            "query": "STEMI aspirin loading dose",
            "top_k": 5,
        }
        res = await client.post("/api/v1/retrieve", json=req)
        assert res.status_code == 200
        data = res.json()
        assert data["total_results"] > 0
        assert len(data["results"]) <= 5
        top = data["results"][0]
        assert "source" in top
        assert top["source"]["document_id"].startswith("ICMR-CARD-")
        assert "password" not in str(data)
        assert "d:\\" not in str(data).lower()


@pytest.mark.anyio
async def test_retrieve_negative_out_of_scope_query(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        req = {
            "query": "dengue fever treatment protocol",
            "top_k": 5,
        }
        res = await client.post("/api/v1/retrieve", json=req)
        assert res.status_code == 200
        data = res.json()
        assert data["total_results"] == 0
        assert data["results"] == []
        assert data["no_evidence"] is True


@pytest.mark.anyio
async def test_review_queue_endpoint(app):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/api/v1/review/items?limit=10&offset=0")
        assert res.status_code == 200
        data = res.json()
        assert "total_items" in data
        assert "items" in data
        assert len(data["items"]) <= 10
