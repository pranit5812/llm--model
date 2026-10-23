"""FastAPI routes for the ICMR STW Knowledge Retrieval API.

Endpoints:
    POST /api/v1/retrieve       — Hybrid retrieval with optional filters
    GET  /api/v1/documents      — List all indexed STW documents
    GET  /api/v1/documents/{id} — Document metadata and unit breakdown
    GET  /api/v1/review/items   — Paginated review queue
    GET  /api/v1/health         — Health check

Security:
    - No database credentials or file paths are exposed in responses.
    - No LLM, SLM, or AI generation.
    - Internal errors are logged server-side; only safe messages are returned.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..knowledge.indexer import KnowledgeIndexer
from ..llm.schemas import RAGResponse
from ..rag.pipeline import RAGPipeline
from ..retrieval.hybrid import HybridRetriever
from ..retrieval.models import (
    NO_RELIABLE_ICMR_EVIDENCE,
    RetrievalQuery,
)
from ..review.schemas import ReviewPriority, ReviewReason, ReviewStatus
from ..review.service import ReviewService
from .schemas import (
    ChatRequest,
    DocumentDetail,
    DocumentExplorerNode,
    DocumentSummary,
    HealthResponse,
    ICMRCitation,
    RetrievalResultItem,
    RetrieveRequest,
    RetrieveResponse,
    ReviewActionRequest,
    ReviewApprovalRequest,
    ReviewCorrectionRequest,
    ReviewItemSchema,
    ReviewQueueResponse,
    ReviewRejectionRequest,
    ReviewStartRequest,
    PromotionRequest,
    PromotionValidationResponse,
    SpecialtySummary,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------

def create_app(
    structured_dir: Path = Path("data/processed/structured"),
    knowledge_dir: Path = Path("data/knowledge"),
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        structured_dir: Directory containing canonical STW JSON files.
        knowledge_dir: Directory containing built knowledge indexes.
    """
    app = FastAPI(
        title="ICMR STW Knowledge Retrieval API",
        description=(
            "Evidence retrieval system for Indian Council of Medical Research (ICMR) "
            "Standard Treatment Workflow (STW) documents. "
            "Returns structured clinical evidence with source provenance. "
            "No LLM or AI answer generation."
        ),
        version="0.6.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    # --- State ---
    _indexer = KnowledgeIndexer(structured_dir=structured_dir, knowledge_dir=knowledge_dir)
    _retriever: Optional[HybridRetriever] = None
    _rag_pipeline: Optional[RAGPipeline] = None
    _review_service = ReviewService(db_path=knowledge_dir / "knowledge.db")
    _manifest: Optional[Dict[str, Any]] = None

    # Lazy initialisation helper
    def _get_retriever() -> HybridRetriever:
        nonlocal _retriever, _manifest
        if _retriever is None:
            _indexer.load()
            _retriever = HybridRetriever(_indexer)
            _manifest = _indexer.get_manifest()
        return _retriever

    def _get_rag_pipeline(model_mode: Optional[str] = None) -> RAGPipeline:
        nonlocal _rag_pipeline
        mode = (model_mode or "baseline").lower()
        if mode in ["fine_tuned", "finetuned", "lora"]:
            from ..llm.provider import get_llm_provider
            _indexer.load()
            return RAGPipeline(indexer=_indexer, llm_provider=get_llm_provider(model_mode="fine_tuned"))
        if _rag_pipeline is None:
            _indexer.load()
            _rag_pipeline = RAGPipeline(indexer=_indexer)
        return _rag_pipeline

    # -----------------------------------------------------------------------
    # Static files & Frontend Chat UI
    # -----------------------------------------------------------------------
    static_dir = Path(__file__).resolve().parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

        @app.get("/", tags=["UI"])
        async def get_root() -> FileResponse:
            """Serve interactive clinical evidence chat frontend."""
            return FileResponse(static_dir / "index.html")

        @app.get("/chat", tags=["UI"])
        async def get_chat() -> FileResponse:
            """Serve interactive clinical evidence chat frontend."""
            return FileResponse(static_dir / "index.html")

        @app.get("/review", tags=["UI"])
        async def get_review_ui() -> FileResponse:
            """Serve clinical knowledge review dashboard."""
            return FileResponse(static_dir / "review.html")

    # -----------------------------------------------------------------------
    # POST /api/v1/chat (Phase 5 Grounded RAG + Phase 7 Fine-Tuned Support)
    # -----------------------------------------------------------------------

    @app.post("/api/v1/chat", response_model=RAGResponse, tags=["RAG Chat"])
    async def chat(body: ChatRequest) -> RAGResponse:
        """Grounded clinical decision support response from ICMR STWs.

        Uses the Grounded RAG Pipeline:
        Scope check -> Hybrid Retrieval -> Reranker -> Context Builder ->
        LLM Structured Generation -> SQLite Citation Verification ->
        Grounding Validation -> Clinical Safety Enforcement.
        """
        try:
            pipeline = _get_rag_pipeline(model_mode=body.model_mode)
        except Exception as e:
            logger.error("Failed to initialize RAG pipeline: %s", e)
            raise HTTPException(status_code=503, detail="RAG pipeline initialization failed.")

        filters = {
            "specialty": body.specialty,
            "condition": body.condition,
            "document_id": body.document_id,
            "version_id": body.version_id,
            "section": body.section,
            "healthcare_tier": body.healthcare_tier,
            "entity_type": body.entity_type,
        }

        return pipeline.answer(
            query=body.query,
            top_k=body.top_k,
            filters=filters,
            debug=body.debug,
        )

    # -----------------------------------------------------------------------
    # POST /api/v1/retrieve
    # -----------------------------------------------------------------------

    @app.post("/api/v1/retrieve", response_model=RetrieveResponse, tags=["Retrieval"])
    async def retrieve(body: RetrieveRequest) -> RetrieveResponse:
        """Retrieve ICMR STW clinical evidence for a clinical query.

        Applies hybrid BM25 + TF-IDF retrieval with RRF fusion and
        token-overlap reranking. Supports metadata pre-filters.

        Returns NO_RELIABLE_ICMR_EVIDENCE when no unit meets the
        minimum confidence threshold.
        """
        try:
            retriever = _get_retriever()
        except FileNotFoundError as e:
            raise HTTPException(status_code=503, detail="Knowledge index not found. Run build_index.py first.")

        rq = RetrievalQuery(
            query=body.query,
            top_k=body.top_k,
            specialty=body.specialty,
            condition=body.condition,
            document_id=body.document_id,
            section=body.section,
            healthcare_tier=body.healthcare_tier,
            entity_type=body.entity_type,
        )

        results = retriever.retrieve(rq)

        items = []
        for r in results:
            items.append(RetrievalResultItem(
                unit_id=r.unit_id,
                content=r.content,
                score=r.score,
                rank=r.rank,
                document_id=r.document_id,
                condition=r.condition,
                specialty=r.specialty,
                page_number=r.page_number,
                section=r.section,
                entity_type=r.entity_type,
                review_status=r.review_status,
                source=ICMRCitation(**r.citation),
            ))

        return RetrieveResponse(
            query=body.query,
            total_results=len(items),
            method="hybrid",
            results=items,
            no_evidence=(len(items) == 0),
        )

    # -----------------------------------------------------------------------
    # GET /api/v1/specialties (Phase 8 Multi-Specialty)
    # -----------------------------------------------------------------------

    @app.get("/api/v1/specialties", response_model=List[SpecialtySummary], tags=["Documents"])
    async def list_specialties() -> List[SpecialtySummary]:
        """List all clinical specialties with document and unit counts across the STW platform."""
        try:
            _ = _get_retriever()
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail="Knowledge index not found.")

        all_units = _indexer.get_all_units()
        by_spec: Dict[str, List[Any]] = {}
        for u in all_units:
            spec = u.specialty or "Unknown"
            by_spec.setdefault(spec, []).append(u)

        summaries = []
        for spec, units in by_spec.items():
            doc_ids = set(u.document_id for u in units)
            conditions = sorted(list(set(u.condition for u in units if u.condition)))
            prod_units = sum(1 for u in units if not u.requires_manual_review)
            review_units = sum(1 for u in units if u.requires_manual_review)
            summaries.append(SpecialtySummary(
                specialty=spec,
                total_documents=len(doc_ids),
                production_units=prod_units,
                review_units=review_units,
                conditions=conditions,
            ))
        return sorted(summaries, key=lambda s: s.specialty)

    # -----------------------------------------------------------------------
    # GET /api/v1/explorer (Phase 8 Document Explorer)
    # -----------------------------------------------------------------------

    @app.get("/api/v1/explorer", response_model=List[DocumentExplorerNode], tags=["Documents"])
    async def get_explorer_tree() -> List[DocumentExplorerNode]:
        """Hierarchical document exploration tree: Specialty -> Condition -> Document -> Version -> Sections."""
        try:
            _ = _get_retriever()
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail="Knowledge index not found.")

        all_units = _indexer.get_all_units()
        by_doc: Dict[str, List[Any]] = {}
        for u in all_units:
            by_doc.setdefault(u.document_id, []).append(u)

        nodes = []
        for doc_id, units in sorted(by_doc.items()):
            sample = units[0]
            sections = sorted(list(set(u.section for u in units if u.section)))
            max_page = max(u.page_number for u in units) if units else 1
            prod_count = sum(1 for u in units if not u.requires_manual_review)
            status = "APPROVED" if prod_count > 0 else "NEEDS_REVIEW"
            v_id = getattr(sample, "version_id", "v1.0")
            nodes.append(DocumentExplorerNode(
                document_id=doc_id,
                specialty=sample.specialty,
                condition=sample.condition,
                title=f"{sample.condition} STW",
                version_id=v_id,
                total_pages=max_page,
                review_status=status,
                sections=sections,
            ))
        return nodes

    # -----------------------------------------------------------------------
    # GET /api/v1/documents
    # -----------------------------------------------------------------------

    @app.get("/api/v1/documents", response_model=List[DocumentSummary], tags=["Documents"])
    async def list_documents() -> List[DocumentSummary]:
        """List all indexed ICMR STW documents with unit counts."""
        try:
            _ = _get_retriever()
            manifest = _indexer.get_manifest()
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail="Knowledge index not found.")

        if not manifest:
            return []

        summaries = []
        for doc_id, info in manifest.get("per_document", {}).items():
            summaries.append(DocumentSummary(
                document_id=doc_id,
                condition=info.get("condition", ""),
                specialty=info.get("specialty", ""),
                total_units=info.get("total_units", 0),
                needs_review_units=info.get("needs_review_units", 0),
                production_units=info.get("production_units", 0),
            ))
        return sorted(summaries, key=lambda x: x.document_id)

    # -----------------------------------------------------------------------
    # GET /api/v1/documents/{document_id}
    # -----------------------------------------------------------------------

    @app.get("/api/v1/documents/{document_id}", response_model=DocumentDetail, tags=["Documents"])
    async def get_document(document_id: str) -> DocumentDetail:
        """Return metadata and unit breakdown for a specific STW document."""
        try:
            _ = _get_retriever()
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail="Knowledge index not found.")

        all_units = _indexer.get_all_units()
        doc_units = [u for u in all_units if u.document_id == document_id]
        if not doc_units:
            raise HTTPException(status_code=404, detail=f"Document '{document_id}' not found in index.")

        prod_units = [u for u in doc_units if not u.requires_manual_review]
        review_units = [u for u in doc_units if u.requires_manual_review]

        entity_counts: Dict[str, int] = {}
        for u in prod_units:
            entity_counts[u.entity_type] = entity_counts.get(u.entity_type, 0) + 1

        sample = doc_units[0]
        return DocumentDetail(
            document_id=document_id,
            condition=sample.condition,
            specialty=sample.specialty,
            total_units=len(doc_units),
            production_units=len(prod_units),
            needs_review_units=len(review_units),
            entity_type_breakdown=entity_counts,
        )

    # -----------------------------------------------------------------------
    # Review Queue & Workflow Endpoints (Phase 9 Comprehensive Lifecycle)
    # -----------------------------------------------------------------------

    def _schema_from_review_item(i: Any) -> ReviewItemSchema:
        return ReviewItemSchema(
            unit_id=i.knowledge_unit_id,
            document_id=i.document_id,
            version_id=getattr(i, "version_id", "v1.0"),
            specialty=getattr(i, "specialty", "Cardiology"),
            condition=i.condition,
            section=i.section,
            page_number=i.page_number,
            entity_type=i.entity_type,
            content=i.content,
            review_status=i.review_status.value if hasattr(i.review_status, "value") else str(i.review_status),
            review_notes=i.review_notes,
            review_item_id=i.review_item_id,
            review_reason=i.review_reason.value if hasattr(i.review_reason, "value") else str(i.review_reason),
            review_priority=i.review_priority.value if hasattr(i.review_priority, "value") else str(i.review_priority),
            risk_category=getattr(i, "risk_category", "STANDARD"),
            original_source_text=i.original_source_text,
            corrected_structured_value=i.corrected_structured_value,
            correction_text=getattr(i, "correction_text", i.corrected_structured_value),
            rejection_reason=getattr(i, "rejection_reason", None),
            reviewer_id=i.reviewer_id,
            reviewer_name=getattr(i, "reviewer_name", None),
            reviewed_at=i.reviewed_at,
            approval_timestamp=getattr(i, "approval_timestamp", None),
            second_reviewer_id=getattr(i, "second_reviewer_id", None),
            second_reviewer_name=getattr(i, "second_reviewer_name", None),
            second_reviewed_at=getattr(i, "second_reviewed_at", None),
            second_reviewer_notes=getattr(i, "second_reviewer_notes", None),
            requires_two_stage_approval=getattr(i, "requires_two_stage_approval", False),
            created_at=i.created_at,
            updated_at=getattr(i, "updated_at", i.created_at),
            flowchart_context=getattr(i, "flowchart_context", None),
            table_context=getattr(i, "table_context", None),
            source_reference=i.source_reference,
        )

    @app.get("/api/v1/review/items", response_model=ReviewQueueResponse, tags=["Review"])
    async def get_review_items(
        status: Optional[str] = Query(default=None, description="Filter by status (NEEDS_REVIEW, IN_REVIEW, APPROVED, NEEDS_CORRECTION, REJECTED)"),
        priority: Optional[str] = Query(default=None, description="Filter by priority (HIGH, MEDIUM, LOW)"),
        risk_category: Optional[str] = Query(default=None, description="Filter by risk category (HIGH, MEDIUM, LOW)"),
        reason: Optional[str] = Query(default=None, description="Filter by review reason"),
        specialty: Optional[str] = Query(default=None, description="Filter by clinical specialty"),
        condition: Optional[str] = Query(default=None, description="Filter by condition"),
        document_id: Optional[str] = Query(default=None, description="Filter by document ID"),
        version_id: Optional[str] = Query(default=None, description="Filter by version ID"),
        entity_type: Optional[str] = Query(default=None, description="Filter by entity type"),
        reviewer_id: Optional[str] = Query(default=None, description="Filter by reviewer ID"),
        search: Optional[str] = Query(default=None, description="Search condition, content, or source text"),
        sort_by: str = Query(default="priority", description="Sort by: risk, priority, date, specialty, document, page, status"),
        sort_order: str = Query(default="asc", description="Sort order: asc, desc"),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
    ) -> ReviewQueueResponse:
        """Return knowledge units flagged for manual clinical review with comprehensive filtering, sorting, and search."""
        try:
            items = _review_service.list_items(
                status=status,
                priority=priority,
                risk_category=risk_category,
                reason=reason,
                specialty=specialty,
                condition=condition,
                document_id=document_id,
                version_id=version_id,
                entity_type=entity_type,
                reviewer_id=reviewer_id,
                search=search,
                sort_by=sort_by,
                sort_order=sort_order,
                limit=limit,
                offset=offset,
            )

            summary = _review_service.get_summary()
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail="Knowledge database not found. Run build_index.py first.")
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

        schema_items = [_schema_from_review_item(i) for i in items]

        by_doc_list = [{"document_id": k, "count": v} for k, v in summary.by_document.items()]
        by_reason_list = [{"reason": k, "count": v} for k, v in summary.by_reason.items()]

        return ReviewQueueResponse(
            total_items=summary.total_items,
            items=schema_items,
            by_document=by_doc_list,
            by_entity_type=by_reason_list,
            by_priority={
                "HIGH": summary.high_priority_pending,
                "MEDIUM": summary.medium_priority_pending,
                "LOW": summary.low_priority_pending,
            },
            by_reason=summary.by_reason,
            by_specialty=summary.by_specialty,
            by_risk=summary.by_risk,
        )

    @app.get("/api/v1/review/items/{item_id}", response_model=ReviewItemSchema, tags=["Review"])
    async def get_review_item(item_id: str) -> ReviewItemSchema:
        """Fetch a specific review item with full clinical context and source provenance."""
        item = _review_service.get_item(item_id)
        if not item:
            raise HTTPException(status_code=404, detail=f"Review item '{item_id}' not found.")
        return _schema_from_review_item(item)

    @app.post("/api/v1/review/items/{item_id}/start", response_model=ReviewItemSchema, tags=["Review"])
    async def start_review_item(item_id: str, body: ReviewStartRequest) -> ReviewItemSchema:
        """Transition review item status to IN_REVIEW when a clinician begins evaluation."""
        try:
            item = _review_service.start_review(item_id, body)
            return _schema_from_review_item(item)
        except KeyError as ke:
            raise HTTPException(status_code=404, detail=str(ke))
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

    @app.post("/api/v1/review/items/{item_id}/approve", response_model=ReviewItemSchema, tags=["Review"])
    async def approve_review_item(item_id: str, body: ReviewApprovalRequest) -> ReviewItemSchema:
        """Approve a flagged knowledge unit.

        For HIGH-risk items, enforces two-stage approval:
        Stage 1 transitions to IN_REVIEW awaiting second clinician.
        Stage 2 transitions to APPROVED (and ELIGIBLE_FOR_PRODUCTION).
        """
        try:
            # Explicit promotion must be invoked separately via /promote
            item = _review_service.approve_item(item_id, body, auto_promote=False)
            return _schema_from_review_item(item)
        except KeyError as ke:
            raise HTTPException(status_code=404, detail=str(ke))
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

    @app.post("/api/v1/review/items/{item_id}/reject", response_model=ReviewItemSchema, tags=["Review"])
    async def reject_review_item(item_id: str, body: Union[ReviewRejectionRequest, ReviewActionRequest]) -> ReviewItemSchema:
        """Reject a flagged unit, keeping it permanently excluded from production retrieval."""
        try:
            item = _review_service.reject_item(item_id, body)
            return _schema_from_review_item(item)
        except KeyError as ke:
            raise HTTPException(status_code=404, detail=str(ke))
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

    @app.post("/api/v1/review/items/{item_id}/correct", response_model=ReviewItemSchema, tags=["Review"])
    @app.post("/api/v1/review/items/{item_id}/correction", response_model=ReviewItemSchema, tags=["Review"])
    async def record_review_correction(item_id: str, body: ReviewCorrectionRequest) -> ReviewItemSchema:
        """Record an expert clinical correction while preserving original ICMR source text immutably."""
        try:
            item = _review_service.record_correction(item_id, body)
            return _schema_from_review_item(item)
        except KeyError as ke:
            raise HTTPException(status_code=404, detail=str(ke))
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

    @app.post("/api/v1/review/items/{item_id}/promote", response_model=PromotionValidationResponse, tags=["Review"])
    async def promote_review_item(item_id: str, body: PromotionRequest) -> PromotionValidationResponse:
        """Explicit promotion step: Validate schema and provenance, then incrementally index into production retrieval."""
        try:
            result = _review_service.promote_item(
                item_id=item_id,
                promoter_id=body.promoter_id,
                promoter_name=body.promoter_name,
                notes=body.notes,
                indexer=_indexer,
            )
            if not result.is_valid:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "message": "Promotion validation failed.",
                        "errors": result.errors,
                        "warnings": result.warnings,
                        "unit_id": result.unit_id,
                    },
                )
            return PromotionValidationResponse(
                is_valid=True,
                errors=[],
                warnings=result.warnings,
                unit_id=result.unit_id,
                document_id=result.document_id,
                version_id=result.version_id,
                promoted_at=result.promoted_at,
            )
        except KeyError as ke:
            raise HTTPException(status_code=404, detail=str(ke))
        except ValueError as ve:
            raise HTTPException(status_code=400, detail=str(ve))

    @app.get("/api/v1/review/items/{item_id}/history", tags=["Review"])
    async def get_review_item_history(item_id: str) -> List[Dict[str, Any]]:
        """Retrieve the immutable audit history of an individual review item."""
        try:
            return _review_service.get_audit_history(item_id=item_id)
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail="Knowledge database not found.")

    @app.get("/api/v1/review/summary", tags=["Review"])
    @app.get("/api/v1/review/stats", tags=["Review"])
    async def get_review_summary() -> Dict[str, Any]:
        """Summary metrics of the review queue backlog, risk categories, and priority distribution."""
        try:
            summary = _review_service.get_summary()
            return summary.model_dump()
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail="Knowledge database not found.")

    @app.get("/api/v1/review/audit", tags=["Review"])
    async def get_review_audit(item_id: Optional[str] = Query(default=None)) -> List[Dict[str, Any]]:
        """Audit trail of all human review actions and decisions."""
        try:
            return _review_service.get_audit_history(item_id=item_id)
        except FileNotFoundError:
            raise HTTPException(status_code=503, detail="Knowledge database not found.")

    # -----------------------------------------------------------------------
    # GET /api/v1/health
    # -----------------------------------------------------------------------

    @app.get("/api/v1/health", response_model=HealthResponse, tags=["System"])
    async def health() -> HealthResponse:
        """Health check — verifies the knowledge index is loaded."""
        try:
            _ = _get_retriever()
            prod_units = len(_indexer.get_all_production_units())
            manifest = _indexer.get_manifest() or {}
            total_docs = manifest.get("total_documents", 0)
            loaded = True
        except Exception:
            prod_units = 0
            total_docs = 0
            loaded = False

        return HealthResponse(
            status="ok" if loaded else "degraded",
            index_loaded=loaded,
            total_production_units=prod_units,
            total_documents=total_docs,
        )

    return app
