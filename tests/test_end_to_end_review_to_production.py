"""Phase 9 Test: End-to-End Clinical Review to Production Promotion.

Verifies:
1. A quarantined knowledge unit is initially excluded from hybrid retrieval.
2. The unit progresses through clinical review: NEEDS_REVIEW -> IN_REVIEW -> APPROVED.
3. Promotion executes pre-promotion validation and performs incremental indexing.
4. The promoted unit is immediately retrievable via HybridRetriever without full reindexing.
5. Rejected units are permanently barred from retrieval.
6. Baseline Cardiology units remain unaffected (zero regression).
"""

import pickle
import pytest
from pathlib import Path
from src.knowledge.indexer import KnowledgeIndexer
from src.knowledge.units import KnowledgeUnit
from src.retrieval.hybrid import HybridRetriever
from src.retrieval.models import RetrievalQuery
from src.review.queue import ReviewQueue
from src.review.approval import ApprovalEngine
from src.review.promotion import PromotionManager
from src.review.schemas import (
    ReviewPriority,
    ReviewReason,
    ReviewStatus,
    ReviewRiskCategory,
    ReviewStartRequest,
    ReviewApprovalRequest,
    ReviewRejectionRequest,
)


@pytest.fixture
def e2e_env(tmp_path):
    """Sets up a temporary knowledge base and indexer."""
    db_path = tmp_path / "knowledge.db"
    index_dir = tmp_path / "index"
    index_dir.mkdir(parents=True, exist_ok=True)

    indexer = KnowledgeIndexer(knowledge_dir=index_dir, db_path=db_path)
    queue = ReviewQueue(db_path=db_path)
    engine = ApprovalEngine(queue=queue)
    prom_manager = PromotionManager(queue=queue)

    cardio_unit = KnowledgeUnit(
        unit_id="ICMR-CARD-PROD-001",
        document_id="ICMR-CARD-001",
        specialty="Cardiology",
        condition="STEMI",
        section="Emergency Management",
        page_number=2,
        entity_type="drug_recommendation",
        healthcare_tier="TERTIARY_PCI",
        content="Administer Aspirin 300 mg chewable tablet immediately upon arrival.",
        requires_manual_review=False,
        review_status="approved",
        source_reference={"source_text_reference": "Administer Aspirin 300 mg chewable tablet immediately upon arrival."}
    )

    neuro_unit = KnowledgeUnit(
        unit_id="ICMR-NEUR-QUAR-001",
        document_id="ICMR-NEUR-001",
        specialty="Neurology",
        condition="Ischemic Stroke",
        section="Thrombolytic Therapy",
        page_number=3,
        entity_type="drug_recommendation",
        healthcare_tier="TERTIARY_PCI",
        content="Intravenous Alteplase 0.9 mg/kg (maximum 90 mg) administered within 4.5 hours of stroke symptom onset.",
        requires_manual_review=True,
        review_status="needs_review",
        source_reference={"source_text_reference": "Intravenous Alteplase 0.9 mg/kg (maximum 90 mg) administered within 4.5 hours of stroke symptom onset."}
    )

    rej_unit = KnowledgeUnit(
        unit_id="ICMR-NEUR-QUAR-REJ",
        document_id="ICMR-NEUR-001",
        specialty="Neurology",
        condition="Ischemic Stroke",
        section="Outdated Section",
        page_number=10,
        entity_type="general_statement",
        healthcare_tier=None,
        content="Experimental outdated herbal infusion without clinical trial backing.",
        requires_manual_review=True,
        review_status="needs_review",
        source_reference={"source_text_reference": "Experimental outdated herbal infusion without clinical trial backing."}
    )

    # 1. Write units to SQLite
    indexer._write_sqlite([cardio_unit, neuro_unit, rej_unit])

    # 2. Build initial indexes containing ONLY the unflagged production unit
    bm25, tokenized = indexer._build_bm25([cardio_unit])
    vectorizer, matrix = indexer._build_tfidf([cardio_unit])

    with open(indexer.bm25_path, "wb") as f:
        pickle.dump({"bm25": bm25, "tokenized_corpus": tokenized}, f)
    with open(indexer.tfidf_path, "wb") as f:
        pickle.dump({"vectorizer": vectorizer, "matrix": matrix, "unit_ids": [cardio_unit.unit_id]}, f)

    # Load indexer state
    indexer.load()

    # 3. Populate review queue for both quarantined units
    queue.upsert_review_item(
        unit_id="ICMR-NEUR-QUAR-001",
        document_id="ICMR-NEUR-001",
        condition="Ischemic Stroke",
        section="Thrombolytic Therapy",
        page_number=3,
        entity_type="drug_recommendation",
        content="Intravenous Alteplase 0.9 mg/kg (maximum 90 mg) administered within 4.5 hours of stroke symptom onset.",
        original_source_text="Intravenous Alteplase 0.9 mg/kg (maximum 90 mg) administered within 4.5 hours of stroke symptom onset.",
        review_reason=ReviewReason.OCR_OR_EXTRACTION_ERROR,
        review_priority=ReviewPriority.HIGH,
        risk_category=ReviewRiskCategory.HIGH,
    )
    queue.upsert_review_item(
        unit_id="ICMR-NEUR-QUAR-REJ",
        document_id="ICMR-NEUR-001",
        condition="Ischemic Stroke",
        section="Outdated Section",
        page_number=10,
        entity_type="general_statement",
        content="Experimental outdated herbal infusion without clinical trial backing.",
        original_source_text="Experimental outdated herbal infusion without clinical trial backing.",
        review_reason=ReviewReason.SOURCE_AMBIGUITY,
        review_priority=ReviewPriority.LOW,
        risk_category=ReviewRiskCategory.LOW,
    )

    return {
        "indexer": indexer,
        "queue": queue,
        "engine": engine,
        "promotion_manager": prom_manager,
    }


def test_end_to_end_quarantine_review_promotion_retrieval(e2e_env):
    indexer = e2e_env["indexer"]
    queue = e2e_env["queue"]
    engine = e2e_env["engine"]
    prom_manager = e2e_env["promotion_manager"]

    retriever = HybridRetriever(indexer=indexer)

    # 1. INITIAL RETRIEVAL: Quarantined Neurology unit must NOT be retrieved
    query_neurology = RetrievalQuery(query="Alteplase stroke 4.5 hours", top_k=5)
    initial_results = retriever.retrieve(query_neurology)
    retrieved_unit_ids = [r.unit_id for r in initial_results]
    assert "ICMR-NEUR-QUAR-001" not in retrieved_unit_ids

    # 2. START REVIEW
    engine.start_review(
        "ICMR-NEUR-QUAR-001",
        ReviewStartRequest(reviewer_id="DR-NEUROLOGIST-1", reviewer_name="Dr. Neurologist")
    )
    item = queue.get_item("ICMR-NEUR-QUAR-001")
    assert item.review_status == ReviewStatus.IN_REVIEW

    # 3. APPROVE
    engine.approve_item(
        "ICMR-NEUR-QUAR-001",
        ReviewApprovalRequest(
            reviewer_id="DR-NEUROLOGIST-1",
            notes="Dosage 0.9 mg/kg and 4.5 hr window verified against ICMR Stroke STW Section 3."
        ),
        auto_promote=False
    )
    item_app = queue.get_item("ICMR-NEUR-QUAR-001")
    assert item_app.review_status in (ReviewStatus.APPROVED, ReviewStatus.ELIGIBLE_FOR_PRODUCTION)

    # 4. REJECT the second unit
    engine.reject_item(
        "ICMR-NEUR-QUAR-REJ",
        ReviewRejectionRequest(
            reviewer_id="DR-NEUROLOGIST-1",
            rejection_reason="Outdated and not endorsed by ICMR guidelines.",
            notes="Outdated and not endorsed by ICMR guidelines."
        )
    )

    # 5. CONTROLLED PROMOTION to production index
    prom_result = prom_manager.promote_item(
        "ICMR-NEUR-QUAR-001",
        promoter_id="HEAD-OF-CLINICAL-OPS",
        promoter_name="Chief Medical Officer",
        indexer=indexer
    )
    assert prom_result.eligible_for_production is True
    assert prom_result.indexed_successfully is True
    assert prom_result.indexing_latency_ms < 1000.0  # Under 1 sec (incremental)

    # 6. POST-PROMOTION RETRIEVAL:
    # Newly promoted unit must NOW be immediately retrievable!
    post_results = retriever.retrieve(query_neurology)
    post_retrieved_ids = [r.unit_id for r in post_results]
    assert "ICMR-NEUR-QUAR-001" in post_retrieved_ids

    # Top result should be the promoted unit with correct provenance
    top_match = next(r for r in post_results if r.unit_id == "ICMR-NEUR-QUAR-001")
    assert top_match.document_id == "ICMR-NEUR-001"
    assert top_match.condition == "Ischemic Stroke"
    assert top_match.page_number == 3
    assert "Alteplase" in top_match.content

    # 7. INVARIANT: Rejected unit can NEVER be retrieved
    query_rejected = RetrievalQuery(query="Experimental outdated herbal infusion", top_k=5)
    rej_results = retriever.retrieve(query_rejected)
    rej_retrieved_ids = [r.unit_id for r in rej_results]
    assert "ICMR-NEUR-QUAR-REJ" not in rej_retrieved_ids

    # 8. INVARIANT: Baseline Cardiology unit is still present and retrievable
    query_cardio = RetrievalQuery(query="Aspirin 300 mg arrival", top_k=5)
    cardio_results = retriever.retrieve(query_cardio)
    cardio_ids = [r.unit_id for r in cardio_results]
    assert "ICMR-CARD-PROD-001" in cardio_ids
