"""Tests for canonical ICMR STW Pydantic schema and provenance enforcement."""

import json
from pathlib import Path
import pytest
from pydantic import ValidationError

from src.models.stw_schema import (
    Contraindication,
    ContraindicationType,
    DecisionBranch,
    DecisionNode,
    FlowchartGraph,
    HealthcareTier,
    HealthcareTierManagement,
    Investigation,
    InvestigationTier,
    MedicationDose,
    NodeType,
    ReferralCriterion,
    ReferralUrgency,
    SourceReference,
    STWClinicalPresentation,
    STWDiagnosticCriterion,
    STWDocument,
    STWMetadata,
    STWReference,
    STWTable,
    STWTableRow,
)


EXAMPLE_JSON_PATH = Path("data/processed/examples/stemi_example.json")


@pytest.fixture
def valid_source():
    return SourceReference(
        document_id="ICMR-CARD-006",
        document_name="STEMI",
        page_number=1,
        section="DRUGS & DOSAGE",
        source_text_reference="Aspirin: Loading dose 325 mg followed by 75 mg OD",
    )


@pytest.fixture
def valid_metadata():
    return STWMetadata(
        document_id="ICMR-CARD-006",
        title="STEMI",
        specialty="Cardiology",
        condition="ST Elevation Myocardial Infarction",
        icd_11_code="BA41.0",
        total_pages=1,
    )


def test_stemi_example_file_validates():
    """Verify that the official STEMI example JSON strictly satisfies the STWDocument schema."""
    assert EXAMPLE_JSON_PATH.exists(), f"Example file missing at {EXAMPLE_JSON_PATH}"
    with open(EXAMPLE_JSON_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)

    doc = STWDocument.model_validate(data)
    assert doc.metadata.document_id == "ICMR-CARD-006"
    assert doc.metadata.icd_11_code == "BA41.0"
    assert len(doc.investigations) >= 4
    assert len(doc.medications) >= 10
    assert len(doc.contraindications) >= 6
    assert len(doc.flowcharts) >= 1
    assert len(doc.tables) >= 1

    # Test round-trip serialization
    json_str = doc.model_dump_json()
    reloaded = STWDocument.model_validate_json(json_str)
    assert reloaded.metadata.document_id == doc.metadata.document_id


def test_required_metadata_enforcement():
    """STWMetadata must reject missing required fields."""
    with pytest.raises(ValidationError):
        STWMetadata(
            # document_id missing
            title="STEMI",
            specialty="Cardiology",
            condition="STEMI",
            total_pages=1,
        )

    with pytest.raises(ValidationError):
        STWMetadata(
            document_id="ICMR-CARD-006",
            title="STEMI",
            specialty="Cardiology",
            condition="STEMI",
            total_pages=0,  # total_pages must be >= 1
        )


def test_source_provenance_page_number_validation():
    """Page numbers in source provenance must be >= 1."""
    with pytest.raises(ValidationError):
        SourceReference(
            document_id="ICMR-CARD-006",
            page_number=0,  # Invalid
            section="GENERAL MEASURES",
            source_text_reference="Pain relief by opioid",
        )

    with pytest.raises(ValidationError):
        SourceReference(
            document_id="ICMR-CARD-006",
            page_number=-5,  # Invalid
            section="GENERAL MEASURES",
            source_text_reference="Pain relief by opioid",
        )


def test_source_provenance_non_empty_strings():
    """Empty or whitespace-only provenance strings must be rejected."""
    with pytest.raises(ValidationError):
        SourceReference(
            document_id="   ",
            page_number=1,
            section="GENERAL MEASURES",
            source_text_reference="Valid quote",
        )

    with pytest.raises(ValidationError):
        SourceReference(
            document_id="ICMR-CARD-006",
            page_number=1,
            section="",
            source_text_reference="Valid quote",
        )

    with pytest.raises(ValidationError):
        SourceReference(
            document_id="ICMR-CARD-006",
            page_number=1,
            section="GENERAL MEASURES",
            source_text_reference="   ",
        )


def test_medication_requires_provenance(valid_source):
    """A MedicationDose object cannot exist without valid source provenance."""
    # Valid medication
    med = MedicationDose(
        medication_id="MED-01",
        generic_name="Aspirin",
        dosage="325 mg",
        source=valid_source,
    )
    assert med.generic_name == "Aspirin"

    # Missing source provenance must fail
    with pytest.raises(ValidationError):
        MedicationDose(
            medication_id="MED-01",
            generic_name="Aspirin",
            dosage="325 mg",
        )


def test_investigation_requires_provenance(valid_source):
    """An Investigation object cannot exist without valid source provenance."""
    inv = Investigation(
        investigation_id="INV-01",
        name="12-lead ECG",
        tier=InvestigationTier.BASIC,
        source=valid_source,
    )
    assert inv.tier == InvestigationTier.BASIC

    with pytest.raises(ValidationError):
        Investigation(
            investigation_id="INV-01",
            name="12-lead ECG",
            tier=InvestigationTier.BASIC,
        )


def test_contraindication_requires_provenance(valid_source):
    """Contraindication requires valid provenance and explicit type."""
    ci = Contraindication(
        contraindication_id="CI-01",
        type=ContraindicationType.ABSOLUTE,
        condition_description="Aortic dissection",
        intervention_affected="Thrombolysis",
        source=valid_source,
    )
    assert ci.type == ContraindicationType.ABSOLUTE

    with pytest.raises(ValidationError):
        Contraindication(
            contraindication_id="CI-01",
            type=ContraindicationType.ABSOLUTE,
            condition_description="Aortic dissection",
            intervention_affected="Thrombolysis",
        )


def test_referral_criterion_requires_provenance(valid_source):
    """ReferralCriterion requires valid provenance and urgency."""
    ref = ReferralCriterion(
        referral_id="REF-01",
        urgency=ReferralUrgency.IMMEDIATE,
        trigger_condition="Failed thrombolysis",
        target_facility_type="PCI capable hospital",
        source=valid_source,
    )
    assert ref.urgency == ReferralUrgency.IMMEDIATE

    with pytest.raises(ValidationError):
        ReferralCriterion(
            referral_id="REF-01",
            urgency=ReferralUrgency.IMMEDIATE,
            trigger_condition="Failed thrombolysis",
            target_facility_type="PCI capable hospital",
        )


def test_flowchart_graph_integrity_validation(valid_source):
    """FlowchartGraph must validate that start_node_id and branch targets exist."""
    node1 = DecisionNode(
        node_id="NODE-1",
        node_type=NodeType.START,
        label="Start Node",
        branches=[
            DecisionBranch(branch_id="B1", condition="Yes", target_node_id="NODE-2"),
        ],
        source=valid_source,
    )
    node2 = DecisionNode(
        node_id="NODE-2",
        node_type=NodeType.TERMINAL,
        label="Terminal Node",
        source=valid_source,
    )

    # Valid graph
    graph = FlowchartGraph(
        flowchart_id="FC-01",
        title="Test Flowchart",
        start_node_id="NODE-1",
        nodes=[node1, node2],
        source=valid_source,
    )
    assert len(graph.nodes) == 2

    # Invalid start_node_id
    with pytest.raises(ValidationError) as excinfo:
        FlowchartGraph(
            flowchart_id="FC-01",
            title="Test Flowchart",
            start_node_id="NODE-NONEXISTENT",
            nodes=[node1, node2],
            source=valid_source,
        )
    assert "start_node_id" in str(excinfo.value)

    # Dangling branch target
    invalid_node1 = DecisionNode(
        node_id="NODE-1",
        node_type=NodeType.START,
        label="Start Node",
        branches=[
            DecisionBranch(branch_id="B1", condition="Yes", target_node_id="NODE-GHOST"),
        ],
        source=valid_source,
    )
    with pytest.raises(ValidationError) as excinfo:
        FlowchartGraph(
            flowchart_id="FC-01",
            title="Test Flowchart",
            start_node_id="NODE-1",
            nodes=[invalid_node1, node2],
            source=valid_source,
        )
    assert "NODE-GHOST" in str(excinfo.value)


def test_clinical_table_integrity_validation(valid_source):
    """STWTable must validate that row cells contain all required table headers."""
    row1 = STWTableRow(
        row_id="R1",
        cells={"Drug": "Tenecteplase", "Dose": "35-45 mg"},
        source=valid_source,
    )

    table = STWTable(
        table_id="TAB-01",
        title="Dosing Table",
        headers=["Drug", "Dose"],
        rows=[row1],
        source=valid_source,
    )
    assert len(table.rows) == 1

    # Row missing a declared header
    invalid_row = STWTableRow(
        row_id="R2",
        cells={"Drug": "Aspirin"},  # "Dose" missing
        source=valid_source,
    )
    with pytest.raises(ValidationError) as excinfo:
        STWTable(
            table_id="TAB-01",
            title="Dosing Table",
            headers=["Drug", "Dose"],
            rows=[invalid_row],
            source=valid_source,
        )
    assert "missing headers" in str(excinfo.value)


def test_all_clinical_entities_require_source_provenance(valid_source):
    """Every clinical concept class must fail if instantiated without source provenance."""
    # STWClinicalPresentation
    with pytest.raises(ValidationError):
        STWClinicalPresentation(
            typical_symptoms=["Chest pain"],
        )

    # STWDiagnosticCriterion
    with pytest.raises(ValidationError):
        STWDiagnosticCriterion(
            criterion_id="CRIT-1",
            name="Criteria",
            description="Details",
        )

    # HealthcareTierManagement
    with pytest.raises(ValidationError):
        HealthcareTierManagement(
            tier_id="T1",
            tier=HealthcareTier.PHC_CHC,
            general_measures=["Measure 1"],
        )

    # STWReference
    with pytest.raises(ValidationError):
        STWReference(
            reference_id="R1",
            citation_text="Guideline 2024",
        )
