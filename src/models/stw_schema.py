"""Canonical Pydantic schema for ICMR Standard Treatment Workflows (STWs).

This module defines the strongly-typed data structures for representing clinical
knowledge extracted from ICMR STW documents. Every clinical concept strictly
enforces source provenance to guarantee traceability back to the original PDF.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator, model_validator


# =====================================================================
# Source Provenance (Mandatory across all clinical objects)
# =====================================================================

class ReviewStatus(str, Enum):
    EXTRACTED = "extracted"
    NEEDS_REVIEW = "needs_review"
    MANUALLY_VERIFIED = "manually_verified"


class SourceReference(BaseModel):
    """Verifiable citation linking structured clinical data to source ICMR PDF."""
    document_id: str = Field(
        ...,
        description="Official STW catalog ID, e.g., 'ICMR-CARD-006'",
        min_length=3,
    )
    document_name: Optional[str] = Field(
        default=None,
        description="Human-readable title of the document",
    )
    page_number: int = Field(
        ...,
        description="1-indexed page number in the source PDF",
        ge=1,
    )
    section: str = Field(
        ...,
        description="Section header or visual container title in the PDF",
        min_length=1,
    )
    source_text_reference: str = Field(
        ...,
        description="Verbatim text quote from the ICMR document",
        min_length=1,
    )
    bounding_box: Optional[List[float]] = Field(
        default=None,
        description="Optional PDF coordinates [x0, y0, x1, y1] for bounding box audit",
    )
    extraction_type: Optional[str] = Field(
        default="text",
        description="Type of extraction: text, table, flowchart, metadata",
    )
    review_status: ReviewStatus = Field(
        default=ReviewStatus.EXTRACTED,
        description="Extraction review lifecycle status",
    )
    requires_manual_review: bool = Field(
        default=False,
        description="Flag indicating ambiguity, typo, or incomplete source data requiring human clinician review",
    )
    review_notes: Optional[str] = Field(
        default=None,
        description="Detailed explanation of why review is needed",
    )
    normalized_term: Optional[str] = Field(
        default=None,
        description="Explicit normalized concept term if distinct from verbatim source text",
    )

    @field_validator("document_id", "section", "source_text_reference")
    @classmethod
    def check_non_empty_string(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Provenance text fields cannot be empty or whitespace only")
        return v.strip()


# =====================================================================
# Document Metadata
# =====================================================================

class STWMetadata(BaseModel):
    """Bibliographic and administrative metadata for an ICMR STW document."""
    document_id: str = Field(..., min_length=3, description="Canonical STW ID, e.g. 'ICMR-CARD-006'")
    title: str = Field(..., min_length=2, description="Full guideline title")
    specialty: str = Field(..., min_length=2, description="Medical specialty, e.g. 'Cardiology'")
    condition: str = Field(..., min_length=2, description="Target disease or clinical syndrome")
    icd_11_code: Optional[str] = Field(default=None, description="Official ICD-11 coding, e.g. 'BA41.0'")
    volume: str = Field(default="Volume 1", description="STW publication volume")
    edition: str = Field(default="2019", description="Edition identifier")
    source_organization: str = Field(
        default="Indian Council of Medical Research (ICMR)",
        description="Issuing organization",
    )
    source_url: Optional[str] = Field(default=None, description="Official web portal URL")
    local_path: Optional[str] = Field(default=None, description="Relative path to local PDF file")
    total_pages: int = Field(..., ge=1, description="Total number of pages in the PDF document")
    document_hash: Optional[str] = Field(default=None, description="SHA-256 hash of the PDF file")


# =====================================================================
# Clinical Presentation & Diagnostic Criteria
# =====================================================================

class STWClinicalPresentation(BaseModel):
    """Clinical presentation, symptomatology, signs, and differential characteristics."""
    definition: Optional[str] = Field(default=None, description="Formal definition of the syndrome")
    typical_symptoms: List[str] = Field(default_factory=list, description="Classic symptoms")
    atypical_presentations: List[str] = Field(default_factory=list, description="Atypical clinical presentations")
    signs_and_physical_exam: List[str] = Field(default_factory=list, description="Physical examination findings")
    unlikely_features: List[str] = Field(default_factory=list, description="Features that make diagnosis unlikely")
    red_flags: List[str] = Field(default_factory=list, description="Immediate danger signs / high-risk indicators")
    source: SourceReference = Field(..., description="Verifiable provenance for clinical presentation")


class STWDiagnosticCriterion(BaseModel):
    """Formal diagnostic thresholds, risk scores, or classification criteria."""
    criterion_id: str = Field(..., min_length=2, description="Unique identifier for criterion")
    name: str = Field(..., min_length=2, description="Criterion name, e.g. 'STEMI ECG Diagnostic Criteria'")
    description: str = Field(..., description="Clinical description of the criterion")
    diagnostic_threshold: Optional[str] = Field(default=None, description="Quantitative cut-off or threshold")
    source: SourceReference = Field(..., description="Verifiable provenance for diagnostic criterion")


# =====================================================================
# Investigations & Diagnostics
# =====================================================================

class InvestigationTier(str, Enum):
    BASIC = "BASIC"          # Available at PHC / CHC / Secondary
    DESIRABLE = "DESIRABLE"  # Secondary / District Hospital
    OPTIONAL = "OPTIONAL"    # Tertiary / Advanced Care


class Investigation(BaseModel):
    """Laboratory, imaging, or functional investigation recommended in the STW."""
    investigation_id: str = Field(..., min_length=2)
    name: str = Field(..., min_length=2, description="Name of investigation, e.g. '12 lead ECG'")
    tier: InvestigationTier = Field(..., description="Resource level: BASIC, DESIRABLE, or OPTIONAL")
    modality: Optional[str] = Field(default=None, description="Laboratory, Imaging, ECG, etc.")
    indication: Optional[str] = Field(default=None, description="Clinical indication for test")
    target_findings: Optional[str] = Field(default=None, description="Key abnormal findings to look for")
    source: SourceReference = Field(..., description="Verifiable provenance for investigation")


# =====================================================================
# Pharmacotherapy & Medications
# =====================================================================

class MedicationDose(BaseModel):
    """Structured pharmacological recommendation with dosage and administration rules."""
    medication_id: str = Field(..., min_length=2)
    generic_name: str = Field(..., min_length=2, description="Generic drug name, e.g. 'Aspirin'")
    drug_class: Optional[str] = Field(default=None, description="Class, e.g. 'Antiplatelet'")
    dosage: str = Field(..., min_length=1, description="Dose amount and unit, e.g. '325 mg'")
    route: Optional[str] = Field(default=None, description="Route: Oral, IV, SC, etc.")
    frequency: Optional[str] = Field(default=None, description="Frequency: OD, BD, Stat, Infusion")
    duration: Optional[str] = Field(default=None, description="Duration: 'At least 1 year', etc.")
    is_loading_dose: bool = Field(default=False, description="Whether this is a loading/bolus dose")
    maintenance_dose: Optional[str] = Field(default=None, description="Maintenance regimen if applicable")
    weight_based: bool = Field(default=False, description="Whether dose depends on patient weight")
    weight_rules: Optional[List[Dict[str, Any]]] = Field(
        default=None,
        description="Weight tiers, e.g. [{'weight_range': '60-70 kg', 'dose': '35 mg'}]",
    )
    monitoring_parameters: Optional[List[str]] = Field(
        default=None,
        description="Lab tests or vitals to monitor, e.g. ['Serum K+', 'APTT 50-70 sec']",
    )
    cautions_and_contraindications: Optional[List[str]] = Field(
        default=None,
        description="Warnings or exclusions specific to this medication",
    )
    source: SourceReference = Field(..., description="Verifiable provenance for medication")


# =====================================================================
# Contraindications & Safety Exclusions
# =====================================================================

class ContraindicationType(str, Enum):
    ABSOLUTE = "ABSOLUTE"
    RELATIVE = "RELATIVE"


class Contraindication(BaseModel):
    """Clinical contraindication or caution explicitly identified in the STW."""
    contraindication_id: str = Field(..., min_length=2)
    type: ContraindicationType = Field(..., description="ABSOLUTE or RELATIVE")
    condition_description: str = Field(..., description="Contraindicated condition or event")
    intervention_affected: str = Field(..., description="Affected drug or procedure, e.g. 'Thrombolysis'")
    timeframe: Optional[str] = Field(default=None, description="Timeframe, e.g. 'in last 6 months'")
    source: SourceReference = Field(..., description="Verifiable provenance for contraindication")


# =====================================================================
# Tiered Healthcare Delivery & Referral Criteria
# =====================================================================

class HealthcareTier(str, Enum):
    PHC_CHC = "PHC_CHC"
    DISTRICT_HOSPITAL = "DISTRICT_HOSPITAL"
    TERTIARY_PCI = "TERTIARY_PCI"


class HealthcareTierManagement(BaseModel):
    """Specific clinical actions and capabilities designated for a healthcare tier."""
    tier_id: str = Field(..., min_length=2)
    tier: HealthcareTier = Field(..., description="Healthcare tier level")
    general_measures: List[str] = Field(default_factory=list, description="Immediate stabilization measures")
    investigations_performed: List[str] = Field(default_factory=list, description="Tests at this level")
    medications_initiated: List[str] = Field(default_factory=list, description="Medications started here")
    referral_actions: List[str] = Field(default_factory=list, description="Transfer / referral directives")
    source: SourceReference = Field(..., description="Verifiable provenance for tier management")


class ReferralUrgency(str, Enum):
    IMMEDIATE = "IMMEDIATE"  # Emergency transfer within hours
    URGENT = "URGENT"        # Within 24 hours
    ELECTIVE = "ELECTIVE"    # Scheduled outpatient / non-emergency transfer


class ReferralCriterion(BaseModel):
    """Explicit referral criteria between health system tiers."""
    referral_id: str = Field(..., min_length=2)
    urgency: ReferralUrgency = Field(..., description="IMMEDIATE, URGENT, or ELECTIVE")
    trigger_condition: str = Field(..., description="Clinical condition prompting referral")
    originating_tier: Optional[str] = Field(default=None, description="Referring facility type")
    target_facility_type: str = Field(..., description="Target: e.g. 'PCI capable centre'")
    time_window: Optional[str] = Field(default=None, description="Time limit, e.g. '<= 120 min'")
    source: SourceReference = Field(..., description="Verifiable provenance for referral criterion")


# =====================================================================
# Clinical Flowchart & Decision Tree Graph Models
# =====================================================================

class NodeType(str, Enum):
    START = "START"
    DECISION = "DECISION"
    ACTION = "ACTION"
    INVESTIGATION = "INVESTIGATION"
    REFERRAL = "REFERRAL"
    TERMINAL = "TERMINAL"


class DecisionBranch(BaseModel):
    """A conditional transition edge leading to another flowchart node."""
    branch_id: str = Field(..., min_length=2)
    condition: str = Field(..., description="Logical condition or clinical finding governing this branch")
    target_node_id: str = Field(..., description="node_id of destination node")
    rationale: Optional[str] = Field(default=None, description="Clinical rationale for branch")


class DecisionNode(BaseModel):
    """A node within a clinical algorithm or decision tree."""
    node_id: str = Field(..., min_length=2, description="Unique node identifier")
    node_type: NodeType = Field(..., description="Node categorization")
    label: str = Field(..., description="Short node label")
    description: Optional[str] = Field(default=None, description="Detailed text of action or decision")
    branches: List[DecisionBranch] = Field(
        default_factory=list,
        description="Outgoing branches (edges) to subsequent nodes",
    )
    source: SourceReference = Field(..., description="Verifiable provenance for decision node")


class FlowchartGraph(BaseModel):
    """Directed graph representing a complete clinical algorithm or decision flowchart."""
    flowchart_id: str = Field(..., min_length=2)
    title: str = Field(..., min_length=2)
    description: Optional[str] = Field(default=None)
    start_node_id: str = Field(..., description="node_id of entry node")
    nodes: List[DecisionNode] = Field(..., min_length=1)
    source: SourceReference = Field(..., description="Verifiable provenance for flowchart")

    @model_validator(mode="after")
    def validate_graph_integrity(self) -> FlowchartGraph:
        node_ids = {node.node_id for node in self.nodes}
        if self.start_node_id not in node_ids:
            raise ValueError(f"start_node_id '{self.start_node_id}' is not in nodes list: {node_ids}")
        for node in self.nodes:
            for branch in node.branches:
                if branch.target_node_id not in node_ids:
                    raise ValueError(
                        f"Branch '{branch.branch_id}' in node '{node.node_id}' targets unknown node '{branch.target_node_id}'"
                    )
        return self


# =====================================================================
# Clinical Tables (Tabular Data Preservation)
# =====================================================================

class STWTableRow(BaseModel):
    """Single row of a structured clinical table."""
    row_id: str = Field(..., min_length=1)
    cells: Dict[str, str] = Field(..., description="Key-value mapping of column header to cell text")
    source: SourceReference = Field(..., description="Verifiable provenance for table row")


class STWTable(BaseModel):
    """Multidimensional clinical table preserving column and row relationships."""
    table_id: str = Field(..., min_length=2)
    title: str = Field(..., min_length=2)
    headers: List[str] = Field(..., min_length=1, description="List of column headers")
    rows: List[STWTableRow] = Field(default_factory=list)
    source: SourceReference = Field(..., description="Verifiable provenance for table")

    @model_validator(mode="after")
    def validate_row_headers(self) -> STWTable:
        header_set = set(self.headers)
        for row in self.rows:
            missing = header_set - set(row.cells.keys())
            if missing:
                raise ValueError(f"Row '{row.row_id}' in table '{self.table_id}' missing headers: {missing}")
        return self


# =====================================================================
# References & Citations
# =====================================================================

class STWReference(BaseModel):
    """Formal medical guideline or literature citation cited in the STW."""
    reference_id: str = Field(..., min_length=1)
    citation_text: str = Field(..., min_length=3)
    doi_or_url: Optional[str] = Field(default=None)
    source: SourceReference = Field(..., description="Verifiable provenance for reference entry")


# =====================================================================
# Root Canonical STW Document Container
# =====================================================================

class STWDocument(BaseModel):
    """Root canonical representation of an ICMR Standard Treatment Workflow."""
    metadata: STWMetadata
    clinical_presentation: Optional[STWClinicalPresentation] = None
    diagnostic_criteria: List[STWDiagnosticCriterion] = Field(default_factory=list)
    investigations: List[Investigation] = Field(default_factory=list)
    tier_management: List[HealthcareTierManagement] = Field(default_factory=list)
    medications: List[MedicationDose] = Field(default_factory=list)
    contraindications: List[Contraindication] = Field(default_factory=list)
    referral_criteria: List[ReferralCriterion] = Field(default_factory=list)
    flowcharts: List[FlowchartGraph] = Field(default_factory=list)
    tables: List[STWTable] = Field(default_factory=list)
    references: List[STWReference] = Field(default_factory=list)
    abbreviations: Dict[str, str] = Field(default_factory=dict)
