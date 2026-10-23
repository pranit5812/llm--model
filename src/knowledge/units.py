"""Knowledge Unit definitions for the ICMR STW retrieval system.

A KnowledgeUnit is the atomic, self-contained retrieval object derived from
one clinical entity within a canonical STW JSON document. Every unit carries
full provenance, enabling any retrieved result to be traced back to a specific
page, section, and verbatim text in the official ICMR PDF.

No LLM, SLM, or AI generation is involved in this module.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional

# ---------------------------------------------------------------------------
# Entity type constants
# ---------------------------------------------------------------------------

ENTITY_TYPES = {
    "clinical_presentation": "Clinical Presentation",
    "diagnostic_criterion": "Diagnostic Criterion",
    "investigation": "Investigation",
    "medication": "Medication / Drug",
    "contraindication": "Contraindication",
    "referral_criterion": "Referral Criterion",
    "tier_action": "Healthcare Tier Action",
    "flowchart_node": "Flowchart / Decision Node",
    "table_row": "Clinical Table Row",
    "reference": "Bibliographic Reference",
}


# ---------------------------------------------------------------------------
# KnowledgeUnit dataclass
# ---------------------------------------------------------------------------

@dataclass
class KnowledgeUnit:
    """Atomic retrieval unit derived from one clinical entity in an STW document.

    Each unit is self-contained: it carries both a searchable text
    representation (``content``) and full provenance (``source_reference``),
    so a retrieval result can always be traced to its exact origin.
    """

    # --- Identity ---
    unit_id: str
    """Unique identifier: '{document_id}:{entity_type}:{sequential_index}'"""

    # --- Routing metadata (for pre-filtering) ---
    document_id: str
    """e.g. 'ICMR-CARD-006'"""

    specialty: str
    """e.g. 'Cardiology'"""

    condition: str
    """e.g. 'STEMI'"""

    section: str
    """Section heading within the PDF, e.g. 'Management at Tertiary Level'"""

    page_number: int
    """1-indexed page number in the source PDF."""

    entity_type: str
    """One of the ENTITY_TYPES keys."""

    healthcare_tier: Optional[str]
    """PHC_CHC | DISTRICT_HOSPITAL | TERTIARY_PCI | None"""

    # --- Searchable content ---
    content: str
    """Human-readable text representation used for indexing and retrieval."""

    # --- Structured payload ---
    metadata: Dict[str, Any] = field(default_factory=dict)
    """Full structured data from the source entity (serialisable dict)."""

    # --- Review / quality gate ---
    review_status: str = "extracted"
    """extracted | needs_review | manually_verified"""

    requires_manual_review: bool = False
    """True → excluded from production retrieval index."""

    review_notes: Optional[str] = None

    version_id: str = "v1.0"
    """Semantic version of the source STW document (e.g. 'v1.0', 'v1.1')."""

    # --- Provenance ---
    source_reference: Dict[str, Any] = field(default_factory=dict)

    """Verbatim SourceReference fields for citation in retrieval results."""

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-serialisable dictionary representation."""
        return asdict(self)

    @classmethod
    def make_id(cls, document_id: str, entity_type: str, index: int) -> str:
        """Construct a deterministic unit ID."""
        return f"{document_id}:{entity_type}:{index:04d}"


# ---------------------------------------------------------------------------
# Decomposition helpers
# ---------------------------------------------------------------------------

def _source_to_dict(source: Any) -> Dict[str, Any]:
    """Convert a SourceReference Pydantic model (or dict) to a plain dict."""
    if hasattr(source, "model_dump"):
        return source.model_dump()
    if isinstance(source, dict):
        return source
    return {}


def _safe_str(value: Any) -> str:
    """Return a stripped string or empty string if value is None."""
    if value is None:
        return ""
    return str(value).strip()


def decompose_stw_document(doc: Any = None, document_dict: Optional[Dict[str, Any]] = None) -> list[KnowledgeUnit]:
    """Decompose an STWDocument (Pydantic model or dict) into KnowledgeUnit objects.

    Args:
        doc: STWDocument Pydantic instance or dict loaded from structured JSON.
        document_dict: Raw dict representation (used for metadata access).

    Returns:
        List of KnowledgeUnit objects (may include needs_review units).
    """
    if document_dict is None:
        if isinstance(doc, dict):
            document_dict = doc
        elif hasattr(doc, "model_dump"):
            document_dict = doc.model_dump()
        else:
            document_dict = {}

    units: list[KnowledgeUnit] = []
    counter: Dict[str, int] = {k: 0 for k in ENTITY_TYPES}

    meta = document_dict.get("metadata", {})
    doc_id = meta.get("document_id", "UNKNOWN")
    specialty = meta.get("specialty", "")
    condition = meta.get("condition", "")


    def _make(entity_type: str, content: str, section: str, page: int,
               source: Dict[str, Any], metadata: Dict[str, Any],
               tier: Optional[str] = None,
               review_status: str = "extracted",
               requires_review: bool = False,
               review_notes: Optional[str] = None) -> KnowledgeUnit:
        idx = counter[entity_type]
        counter[entity_type] += 1
        return KnowledgeUnit(
            unit_id=KnowledgeUnit.make_id(doc_id, entity_type, idx),
            document_id=doc_id,
            specialty=specialty,
            condition=condition,
            section=section,
            page_number=page,
            entity_type=entity_type,
            healthcare_tier=tier,
            content=content,
            metadata=metadata,
            review_status=review_status,
            requires_manual_review=requires_review,
            review_notes=review_notes,
            source_reference=source,
        )

    # ------------------------------------------------------------------
    # 1. Clinical Presentation
    # ------------------------------------------------------------------
    cp = document_dict.get("clinical_presentation")
    if cp:
        src = cp.get("source", {})
        parts = []
        if cp.get("definition"):
            parts.append(f"Definition: {cp['definition']}")
        if cp.get("typical_symptoms"):
            parts.append("Typical symptoms: " + "; ".join(cp["typical_symptoms"]))
        if cp.get("atypical_presentations"):
            parts.append("Atypical: " + "; ".join(cp["atypical_presentations"]))
        if cp.get("signs_and_physical_exam"):
            parts.append("Signs: " + "; ".join(cp["signs_and_physical_exam"]))
        if cp.get("red_flags"):
            parts.append("Red flags: " + "; ".join(cp["red_flags"]))
        content = f"{condition} clinical presentation. " + " ".join(parts)
        units.append(_make(
            "clinical_presentation", content,
            section=src.get("section", "Clinical Presentation"),
            page=src.get("page_number", 1),
            source=src, metadata=cp,
            review_status=src.get("review_status", "extracted"),
            requires_review=src.get("requires_manual_review", False),
            review_notes=src.get("review_notes"),
        ))

    # ------------------------------------------------------------------
    # 2. Diagnostic Criteria
    # ------------------------------------------------------------------
    for dc in document_dict.get("diagnostic_criteria", []):
        src = dc.get("source", {})
        content = (
            f"{condition} diagnostic criterion: {dc.get('name', '')}. "
            f"{dc.get('description', '')} "
            f"Threshold: {dc.get('diagnostic_threshold', 'not specified')}."
        )
        units.append(_make(
            "diagnostic_criterion", content,
            section=src.get("section", "Diagnostic Criteria"),
            page=src.get("page_number", 1),
            source=src, metadata=dc,
            review_status=src.get("review_status", "extracted"),
            requires_review=src.get("requires_manual_review", False),
            review_notes=src.get("review_notes"),
        ))

    # ------------------------------------------------------------------
    # 3. Investigations
    # ------------------------------------------------------------------
    for inv in document_dict.get("investigations", []):
        src = inv.get("source", {})
        content = (
            f"{condition} investigation: {inv.get('name', '')} "
            f"[{inv.get('tier', '')} tier, {inv.get('modality', '')}]. "
            f"Indication: {inv.get('indication', '')}. "
            f"Target findings: {inv.get('target_findings', '')}."
        )
        units.append(_make(
            "investigation", content,
            section=src.get("section", "Investigations"),
            page=src.get("page_number", 1),
            source=src, metadata=inv,
            review_status=src.get("review_status", "extracted"),
            requires_review=src.get("requires_manual_review", False),
            review_notes=src.get("review_notes"),
        ))

    # ------------------------------------------------------------------
    # 4. Medications
    # ------------------------------------------------------------------
    for med in document_dict.get("medications", []):
        src = med.get("source", {})
        content = (
            f"{condition} medication: {med.get('generic_name', '')} "
            f"[{med.get('drug_class', '')}]. "
            f"Dose: {med.get('dosage', '')} {med.get('route', '')} {med.get('frequency', '')}. "
            f"Duration: {med.get('duration', '')}."
        )
        if med.get("cautions_and_contraindications"):
            content += " Cautions: " + "; ".join(med["cautions_and_contraindications"]) + "."
        units.append(_make(
            "medication", content,
            section=src.get("section", "Pharmacotherapy"),
            page=src.get("page_number", 1),
            source=src, metadata=med,
            review_status=src.get("review_status", "extracted"),
            requires_review=src.get("requires_manual_review", False),
            review_notes=src.get("review_notes"),
        ))

    # ------------------------------------------------------------------
    # 5. Contraindications
    # ------------------------------------------------------------------
    for ci in document_dict.get("contraindications", []):
        src = ci.get("source", {})
        content = (
            f"{condition} contraindication [{ci.get('type', '')}]: "
            f"{ci.get('condition_description', '')}. "
            f"Affected intervention: {ci.get('intervention_affected', '')}. "
            f"Timeframe: {ci.get('timeframe', '')}."
        )
        units.append(_make(
            "contraindication", content,
            section=src.get("section", "Contraindications"),
            page=src.get("page_number", 1),
            source=src, metadata=ci,
            review_status=src.get("review_status", "extracted"),
            requires_review=src.get("requires_manual_review", False),
            review_notes=src.get("review_notes"),
        ))

    # ------------------------------------------------------------------
    # 6. Referral Criteria
    # ------------------------------------------------------------------
    for ref in document_dict.get("referral_criteria", []):
        src = ref.get("source", {})
        content = (
            f"{condition} referral criterion [{ref.get('urgency', '')}]: "
            f"{ref.get('trigger_condition', '')}. "
            f"Target facility: {ref.get('target_facility_type', '')}. "
            f"Time window: {ref.get('time_window', '')}."
        )
        units.append(_make(
            "referral_criterion", content,
            section=src.get("section", "Referral Criteria"),
            page=src.get("page_number", 1),
            source=src, metadata=ref,
            review_status=src.get("review_status", "extracted"),
            requires_review=src.get("requires_manual_review", False),
            review_notes=src.get("review_notes"),
        ))

    # ------------------------------------------------------------------
    # 7. Tier Management Actions
    # ------------------------------------------------------------------
    for tm in document_dict.get("tier_management", []):
        src = tm.get("source", {})
        tier_name = tm.get("tier", "")
        parts = []
        if tm.get("general_measures"):
            parts.append("General measures: " + "; ".join(tm["general_measures"]))
        if tm.get("investigations_performed"):
            parts.append("Investigations: " + "; ".join(tm["investigations_performed"]))
        if tm.get("medications_initiated"):
            parts.append("Medications: " + "; ".join(tm["medications_initiated"]))
        if tm.get("referral_actions"):
            parts.append("Referral: " + "; ".join(tm["referral_actions"]))
        content = (
            f"{condition} management at {tier_name} level. " + " ".join(parts)
        )
        units.append(_make(
            "tier_action", content,
            section=src.get("section", f"Management at {tier_name}"),
            page=src.get("page_number", 1),
            source=src, metadata=tm,
            tier=tier_name,
            review_status=src.get("review_status", "extracted"),
            requires_review=src.get("requires_manual_review", False),
            review_notes=src.get("review_notes"),
        ))

    # ------------------------------------------------------------------
    # 8. Flowchart Nodes
    # ------------------------------------------------------------------
    for fc in document_dict.get("flowcharts", []):
        fc_src = fc.get("source", {})
        for node in fc.get("nodes", []):
            node_src = node.get("source", {})
            branches_text = ""
            if node.get("branches"):
                branches_text = " Branches: " + "; ".join(
                    f"{b.get('condition', '')} → {b.get('target_node_id', '')}"
                    for b in node["branches"]
                )
            content = (
                f"{condition} flowchart '{fc.get('title', '')}' "
                f"[{node.get('node_type', '')}]: {node.get('label', '')}. "
                f"{node.get('description', '')}{branches_text}"
            )
            units.append(_make(
                "flowchart_node", content,
                section=node_src.get("section", fc_src.get("section", "Flowchart")),
                page=node_src.get("page_number", fc_src.get("page_number", 1)),
                source=node_src or fc_src,
                metadata={**node, "flowchart_id": fc.get("flowchart_id"), "flowchart_title": fc.get("title")},
                review_status=node_src.get("review_status", fc_src.get("review_status", "extracted")),
                requires_review=node_src.get("requires_manual_review", fc_src.get("requires_manual_review", False)),
                review_notes=node_src.get("review_notes", fc_src.get("review_notes")),
            ))

    # ------------------------------------------------------------------
    # 9. Table Rows
    # ------------------------------------------------------------------
    for tbl in document_dict.get("tables", []):
        tbl_src = tbl.get("source", {})
        for row in tbl.get("rows", []):
            row_src = row.get("source", {})
            cells = row.get("cells", {})
            cell_text = "; ".join(f"{k}: {v}" for k, v in cells.items() if v)
            content = (
                f"{condition} table '{tbl.get('title', '')}' row: {cell_text}"
            )
            units.append(_make(
                "table_row", content,
                section=row_src.get("section", tbl_src.get("section", "Table")),
                page=row_src.get("page_number", tbl_src.get("page_number", 1)),
                source=row_src or tbl_src,
                metadata={**cells, "table_id": tbl.get("table_id"), "table_title": tbl.get("title"), "row_id": row.get("row_id")},
                review_status=row_src.get("review_status", tbl_src.get("review_status", "extracted")),
                requires_review=row_src.get("requires_manual_review", tbl_src.get("requires_manual_review", False)),
                review_notes=row_src.get("review_notes", tbl_src.get("review_notes")),
            ))

    # ------------------------------------------------------------------
    # 10. References
    # ------------------------------------------------------------------
    for ref in document_dict.get("references", []):
        src = ref.get("source", {})
        content = (
            f"{condition} reference: {ref.get('citation_text', '')} "
            f"DOI: {ref.get('doi_or_url', '')}."
        )
        units.append(_make(
            "reference", content,
            section=src.get("section", "References"),
            page=src.get("page_number", 1),
            source=src, metadata=ref,
            review_status=src.get("review_status", "extracted"),
            requires_review=src.get("requires_manual_review", False),
            review_notes=src.get("review_notes"),
        ))

    return units
