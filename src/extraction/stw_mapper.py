"""STW Mapper: Transforms extracted PDF text, tables, and sections into canonical STWDocument models."""

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Tuple

from src.extraction.provenance import create_source_reference
from src.extraction.section_detector import DetectedSection, SectionCategory, SectionDetector
from src.extraction.table_extractor import TableExtractor
from src.extraction.text_extractor import ExtractedDocument, ExtractedPage, TextBlock
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
    ReviewStatus,
    SourceReference,
    STWClinicalPresentation,
    STWDiagnosticCriterion,
    STWDocument,
    STWMetadata,
    STWReference,
    STWTable,
)


@dataclass
class ExtractionAuditReport:
    """Audit report tracking extraction statistics, review items, and provenance coverage."""
    document_id: str
    condition: str
    total_pages: int
    text_blocks_count: int
    sections_count: int
    tables_detected: int
    tables_extracted: int
    flowcharts_count: int
    medications_count: int
    investigations_count: int
    contraindications_count: int
    referral_rules_count: int
    provenance_coverage_percent: float
    manual_review_items_count: int
    manual_review_details: List[Dict[str, Any]] = field(default_factory=list)
    extraction_errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.document_id,
            "condition": self.condition,
            "total_pages": self.total_pages,
            "text_blocks_count": self.text_blocks_count,
            "sections_count": self.sections_count,
            "tables_detected": self.tables_detected,
            "tables_extracted": self.tables_extracted,
            "flowcharts_count": self.flowcharts_count,
            "medications_count": self.medications_count,
            "investigations_count": self.investigations_count,
            "contraindications_count": self.contraindications_count,
            "referral_rules_count": self.referral_rules_count,
            "provenance_coverage_percent": self.provenance_coverage_percent,
            "manual_review_items_count": self.manual_review_items_count,
            "manual_review_details": self.manual_review_details,
            "extraction_errors": self.extraction_errors,
        }


class STWMapper:
    """Maps extracted document data into canonical Pydantic models."""

    # Known typographical discrepancies in source ICMR documents
    KNOWN_TYPOS = {
        "ticagralor": ("Ticagrelor", "Typographical variant 'Ticagralor' in ICMR source PDF"),
        "first medical contract": ("First Medical Contact", "Typographical error 'First Medical Contract' for First Medical Contact"),
        "surgey": ("surgery", "Typographical error 'surgey' for surgery"),
        "isosorbide mono-nitare": ("Isosorbide mononitrate", "Typographical variant 'mono-nitare' in source text"),
        "mecahnical": ("mechanical", "Typographical variant 'Mecahnical' in source text"),
        "bradyarrthymia": ("Bradyarrhythmia", "Typographical variant 'Bradyarrthymia' in header/filename"),
        "bradyarrthymias": ("Bradyarrhythmias", "Typographical variant 'Bradyarrthymias' in header/filename"),
        "lasing": ("lasting", "Typographical variant 'lasing' for lasting"),
        "perssistent": ("persistent", "Typographical variant 'perssistent' for persistent"),
    }

    @classmethod
    def check_typo_and_normalize(cls, text: str) -> Tuple[Optional[str], bool, Optional[str]]:
        """Check if source text contains known typos and return normalization."""
        lower = text.lower()
        for typo, (norm, note) in cls.KNOWN_TYPOS.items():
            if typo in lower:
                return norm, True, note
        return None, False, None

    @classmethod
    def map_document(
        cls,
        extracted_doc: ExtractedDocument,
        catalog_entry: Dict[str, Any],
        raw_tables: Optional[List[STWTable]] = None,
    ) -> Tuple[STWDocument, ExtractionAuditReport]:
        """Transform an ExtractedDocument into a validated STWDocument and audit report."""
        doc_id = catalog_entry.get("stw_id", extracted_doc.document_id)
        condition = catalog_entry.get("condition", "Cardiology Condition")
        specialty = catalog_entry.get("specialty", "Cardiology")
        total_pages = extracted_doc.total_pages

        # Clean catalog fields from pandas types
        raw_icd = catalog_entry.get("icd_11_code")
        icd_11_code = str(raw_icd).strip() if raw_icd and str(raw_icd) != "nan" else None

        raw_edition = catalog_entry.get("version", "2019")
        edition = str(raw_edition) if raw_edition and str(raw_edition) != "nan" else "2019"

        raw_vol = catalog_entry.get("volume", "Volume 1")
        volume = str(raw_vol) if raw_vol and str(raw_vol) != "nan" else "Volume 1"

        raw_url = catalog_entry.get("source_url")
        source_url = str(raw_url) if raw_url and str(raw_url) != "nan" else None

        raw_path = catalog_entry.get("local_path")
        local_path = str(raw_path) if raw_path and str(raw_path) != "nan" else None

        # 1. Metadata mapping
        metadata = STWMetadata(
            document_id=doc_id,
            title=condition,
            specialty=specialty,
            condition=condition,
            icd_11_code=icd_11_code,
            volume=volume,
            edition=edition,
            source_organization=str(catalog_entry.get("source_organization", "Indian Council of Medical Research (ICMR)")),
            source_url=source_url,
            local_path=local_path,
            total_pages=max(1, total_pages),
            document_hash=extracted_doc.sha256_hash,
        )

        manual_review_items: List[Dict[str, Any]] = []
        errors: List[str] = []

        # 2. Section detection across all pages
        all_sections: List[DetectedSection] = []
        total_blocks_count = 0
        for page in extracted_doc.pages:
            total_blocks_count += len(page.blocks)
            secs = SectionDetector.detect_sections(page)
            all_sections.extend(secs)

        # 3. Extract clinical presentations
        clinical_presentation = cls._extract_clinical_presentation(
            all_sections, doc_id, condition, manual_review_items
        )

        # 4. Extract diagnostic criteria
        diagnostic_criteria = cls._extract_diagnostic_criteria(
            all_sections, doc_id, condition, manual_review_items
        )

        # 5. Extract investigations
        investigations = cls._extract_investigations(
            all_sections, doc_id, condition, manual_review_items
        )

        # 6. Extract medications
        medications = cls._extract_medications(
            all_sections, doc_id, condition, manual_review_items
        )

        # 7. Extract contraindications
        contraindications = cls._extract_contraindications(
            all_sections, doc_id, condition, manual_review_items
        )

        # 8. Extract tier management
        tier_management = cls._extract_tier_management(
            all_sections, doc_id, condition, manual_review_items
        )

        # 9. Extract referral criteria
        referral_criteria = cls._extract_referral_criteria(
            all_sections, doc_id, condition, manual_review_items
        )

        # 10. Extract flowcharts
        flowcharts = cls._extract_flowcharts(
            all_sections, doc_id, condition, manual_review_items
        )

        # 11. Extract references
        references = cls._extract_references(
            all_sections, doc_id, condition, manual_review_items
        )

        # 12. Tables from TableExtractor
        tables: List[STWTable] = raw_tables or []
        for tab in tables:
            if tab.source.requires_manual_review:
                manual_review_items.append({
                    "entity": "table",
                    "id": tab.table_id,
                    "reason": tab.source.review_notes or "Table flagged for manual review",
                    "page": tab.source.page_number,
                })

        # Calculate provenance coverage
        total_clinical_elements = (
            (1 if clinical_presentation else 0)
            + len(diagnostic_criteria)
            + len(investigations)
            + len(medications)
            + len(contraindications)
            + len(tier_management)
            + len(referral_criteria)
            + len(flowcharts)
            + len(tables)
            + len(references)
        )
        provenance_coverage = 100.0 if total_clinical_elements > 0 else 0.0

        audit_report = ExtractionAuditReport(
            document_id=doc_id,
            condition=condition,
            total_pages=total_pages,
            text_blocks_count=total_blocks_count,
            sections_count=len(all_sections),
            tables_detected=len(tables),
            tables_extracted=len(tables),
            flowcharts_count=len(flowcharts),
            medications_count=len(medications),
            investigations_count=len(investigations),
            contraindications_count=len(contraindications),
            referral_rules_count=len(referral_criteria),
            provenance_coverage_percent=provenance_coverage,
            manual_review_items_count=len(manual_review_items),
            manual_review_details=manual_review_items,
            extraction_errors=errors,
        )

        stw_doc = STWDocument(
            metadata=metadata,
            clinical_presentation=clinical_presentation,
            diagnostic_criteria=diagnostic_criteria,
            investigations=investigations,
            tier_management=tier_management,
            medications=medications,
            contraindications=contraindications,
            referral_criteria=referral_criteria,
            flowcharts=flowcharts,
            tables=tables,
            references=references,
            abbreviations=cls._extract_abbreviations(all_sections),
        )

        return stw_doc, audit_report

    @classmethod
    def _extract_clinical_presentation(
        cls,
        sections: List[DetectedSection],
        doc_id: str,
        condition: str,
        review_items: List[Dict[str, Any]],
    ) -> Optional[STWClinicalPresentation]:
        """Extract clinical presentation features from designated sections."""
        pres_sections = [s for s in sections if s.category == SectionCategory.CLINICAL_PRESENTATION]
        if not pres_sections:
            return None

        typical_symptoms: List[str] = []
        atypical_presentations: List[str] = []
        signs: List[str] = []
        unlikely_features: List[str] = []
        red_flags: List[str] = []
        source_texts: List[str] = []
        page_num = pres_sections[0].page_number

        for sec in pres_sections:
            header_lower = sec.header_text.lower()
            for b in sec.blocks:
                source_texts.append(b.text)
                for line in b.lines:
                    txt = line.text.strip()
                    if not txt or txt.isupper() and len(txt) < 30:
                        continue
                    clean_txt = re.sub(r"^[•\-\*▪▫‣–—\d\.\)]\s*", "", txt)

                    if "unlikely" in header_lower or "angina unlikely" in clean_txt.lower():
                        unlikely_features.append(clean_txt)
                    elif "atypical" in clean_txt.lower() or "exertional fatigue" in clean_txt.lower():
                        atypical_presentations.append(clean_txt)
                    elif "syncope" in clean_txt.lower() or "pulse rate <" in clean_txt.lower():
                        signs.append(clean_txt)
                    elif "acute coronary syndrome" in header_lower or "angina at rest" in clean_txt.lower():
                        red_flags.append(clean_txt)
                    else:
                        typical_symptoms.append(clean_txt)

        combined_source_text = "\n".join(source_texts)[:1000]
        norm, has_typo, note = cls.check_typo_and_normalize(combined_source_text)
        if has_typo:
            review_items.append({
                "entity": "clinical_presentation",
                "reason": note,
                "page": page_num,
            })

        source = create_source_reference(
            document_id=doc_id,
            document_name=condition,
            page_number=page_num,
            section="CLINICAL PRESENTATION",
            source_text=combined_source_text,
            extraction_type="text",
            review_status=ReviewStatus.NEEDS_REVIEW if has_typo else ReviewStatus.EXTRACTED,
            requires_manual_review=has_typo,
            review_notes=note,
            normalized_term=norm,
        )

        return STWClinicalPresentation(
            definition=f"Clinical presentation and diagnostic characteristics of {condition} per ICMR STW.",
            typical_symptoms=typical_symptoms[:10],
            atypical_presentations=atypical_presentations[:5],
            signs_and_physical_exam=signs[:5],
            unlikely_features=unlikely_features[:8],
            red_flags=red_flags[:6],
            source=source,
        )

    @classmethod
    def _extract_diagnostic_criteria(
        cls,
        sections: List[DetectedSection],
        doc_id: str,
        condition: str,
        review_items: List[Dict[str, Any]],
    ) -> List[STWDiagnosticCriterion]:
        """Extract explicit diagnostic criteria from diagnosis sections."""
        diag_sections = [s for s in sections if s.category == SectionCategory.DIAGNOSTIC_CRITERIA]
        criteria: List[STWDiagnosticCriterion] = []

        for s_idx, sec in enumerate(diag_sections):
            for b_idx, b in enumerate(sec.blocks):
                norm, has_typo, note = cls.check_typo_and_normalize(b.text)
                if has_typo:
                    review_items.append({
                        "entity": "diagnostic_criterion",
                        "text": b.text[:60],
                        "reason": note,
                        "page": sec.page_number,
                    })

                source = create_source_reference(
                    document_id=doc_id,
                    document_name=condition,
                    page_number=sec.page_number,
                    section=sec.header_text,
                    source_text=b.text,
                    bounding_box=b.bbox,
                    extraction_type="text",
                    review_status=ReviewStatus.NEEDS_REVIEW if has_typo else ReviewStatus.EXTRACTED,
                    requires_manual_review=has_typo,
                    review_notes=note,
                    normalized_term=norm,
                )

                criteria.append(STWDiagnosticCriterion(
                    criterion_id=f"CRIT_{sec.page_number}_{s_idx+1}_{b_idx+1}",
                    name=sec.header_text,
                    description=b.text[:300].replace("\n", " "),
                    diagnostic_threshold=None,
                    source=source,
                ))

        return criteria

    @classmethod
    def _extract_investigations(
        cls,
        sections: List[DetectedSection],
        doc_id: str,
        condition: str,
        review_items: List[Dict[str, Any]],
    ) -> List[Investigation]:
        """Extract investigations classified into Basic, Desirable, or Optional tiers."""
        inv_sections = [s for s in sections if s.category == SectionCategory.INVESTIGATIONS]
        investigations: List[Investigation] = []
        inv_count = 0

        # If no dedicated investigations section, also check management/general measures for diagnostic tests
        if not inv_sections:
            inv_sections = [
                s for s in sections
                if s.category in (SectionCategory.MANAGEMENT_TIERS, SectionCategory.GENERAL, SectionCategory.DIAGNOSTIC_CRITERIA)
            ]

        test_keywords = ("ecg", "troponin", "bio-chemistry", "biochemistry", "echocardiography",
                         "hemogram", "sugar", "urea", "creatinine", "x-ray", "holter", "angiography")

        for sec in inv_sections:
            hdr_lower = sec.header_text.lower()
            if "desirable" in hdr_lower or "other" in hdr_lower or "echo" in hdr_lower:
                tier = InvestigationTier.DESIRABLE
            elif "optional" in hdr_lower or "angio" in hdr_lower:
                tier = InvestigationTier.OPTIONAL
            else:
                tier = InvestigationTier.BASIC

            for b in sec.blocks:
                for line in b.lines:
                    txt = line.text.strip()
                    if not txt or (txt.isupper() and len(txt) < 35):
                        continue
                    clean_name = re.sub(r"^[•\-\*▪▫‣–—\d\.\)]\s*", "", txt).strip()
                    if len(clean_name) < 3 or clean_name.lower().startswith("investigation"):
                        continue

                    # If searching in general sections, require match with known test keywords
                    if sec.category != SectionCategory.INVESTIGATIONS:
                        if not any(kw in clean_name.lower() for kw in test_keywords):
                            continue

                    inv_count += 1
                    source = create_source_reference(
                        document_id=doc_id,
                        document_name=condition,
                        page_number=sec.page_number,
                        section=sec.header_text,
                        source_text=line.text,
                        bounding_box=line.bbox,
                        extraction_type="text",
                    )
                    investigations.append(Investigation(
                        investigation_id=f"INV_P{sec.page_number}_{inv_count:02d}",
                        name=clean_name,
                        tier=tier,
                        modality="Laboratory / Diagnostic Imaging",
                        indication=f"Workup for {condition}",
                        source=source,
                    ))

        return investigations

    @classmethod
    def _extract_medications(
        cls,
        sections: List[DetectedSection],
        doc_id: str,
        condition: str,
        review_items: List[Dict[str, Any]],
    ) -> List[MedicationDose]:
        """Extract medication dosing guidance preserving exact text and flagging discrepancies."""
        # In visual poster STWs, medications are distributed across multiple flowchart panels
        med_sections = sections

        medications: List[MedicationDose] = []
        med_count = 0
        seen_doses = set()

        drug_pattern = re.compile(
            r"\b(Aspirin|Clopidogrel|Prasugrel|Ticagralor|Ticagrelor|Atorvastatin|Rosuvastatin|"
            r"Metoprolol|Tenecteplase|Reteplase|Alteplase|Streptokinase|Enoxaparin|Heparin|"
            r"Morphine|Furosemide|Spironolactone|Ramipril|Enalapril|Amlodipine|Verapamil|Diltiazem|"
            r"Digoxin|Amiodarone|Dabigatran|Rivaroxaban|Apixaban|Warfarin|Atropine|Dopamine|"
            r"Epinephrine|Empagliflozin|Dapagliflozin|Carvedilol|ARNI|Nitrates|Isosorbide|Nicorandil|"
            r"Ranolazine|Trimetazidine|Flecainide|Propafenone|Sotalol|DOAC|OAC)\b",
            re.IGNORECASE,
        )

        dose_unit_pattern = re.compile(r"\b(mg|mcg|units|u/kg|bolus|infusion|daily|od|bd|tds|po|iv|sc|inr|sos|tab|tablet)\b", re.IGNORECASE)

        for sec in med_sections:
            sec_header_match = drug_pattern.search(sec.header_text)
            for b in sec.blocks:
                for line in b.lines:
                    txt = line.text.strip()
                    if not txt:
                        continue
                    clean_line = re.sub(r"^[•\-\*▪▫‣–—\d\.\)]\s*", "", txt).strip()

                    match = drug_pattern.search(clean_line)
                    drug_name = None

                    if match:
                        drug_name = match.group(1).capitalize()
                    elif sec_header_match and dose_unit_pattern.search(clean_line):
                        drug_name = sec_header_match.group(1).capitalize()

                    if drug_name:
                        has_dose_units = bool(dose_unit_pattern.search(clean_line))
                        # Skip pure section headers or long non-drug sentences unless they contain dosage
                        if not has_dose_units and (len(clean_line) > 70 or clean_line.isupper()):
                            continue

                        dose_sig = f"{drug_name}_{clean_line.lower()}"
                        if dose_sig in seen_doses:
                            continue
                        seen_doses.add(dose_sig)

                        med_count += 1
                        norm, has_typo, note = cls.check_typo_and_normalize(clean_line)

                        requires_review = has_typo or not has_dose_units
                        if not has_dose_units:
                            review_reason = f"Medication '{drug_name}' mentioned in workflow without explicit dosage or units in source text"
                        else:
                            review_reason = note

                        if requires_review:
                            review_items.append({
                                "entity": "medication",
                                "raw_text": clean_line,
                                "reason": review_reason,
                                "page": sec.page_number,
                            })

                        is_loading = "loading" in clean_line.lower() or "bolus" in clean_line.lower()
                        weight_based = "kg" in clean_line.lower()

                        source = create_source_reference(
                            document_id=doc_id,
                            document_name=condition,
                            page_number=sec.page_number,
                            section=sec.header_text,
                            source_text=line.text,
                            bounding_box=line.bbox,
                            extraction_type="text",
                            review_status=ReviewStatus.NEEDS_REVIEW if requires_review else ReviewStatus.EXTRACTED,
                            requires_manual_review=requires_review,
                            review_notes=review_reason,
                            normalized_term=norm,
                        )

                        medications.append(MedicationDose(
                            medication_id=f"MED_P{sec.page_number}_{med_count:02d}",
                            generic_name=drug_name,
                            dosage=clean_line if has_dose_units else f"{clean_line} (Dose not specified in text)",
                            route="Oral / Intravenous / Subcutaneous",
                            is_loading_dose=is_loading,
                            weight_based=weight_based,
                            source=source,
                        ))

        return medications

    @classmethod
    def _extract_contraindications(
        cls,
        sections: List[DetectedSection],
        doc_id: str,
        condition: str,
        review_items: List[Dict[str, Any]],
    ) -> List[Contraindication]:
        """Extract contraindication checklists."""
        ci_sections = [s for s in sections if s.category == SectionCategory.CONTRAINDICATIONS]
        contraindications: List[Contraindication] = []
        ci_count = 0

        for sec in ci_sections:
            is_absolute = "absolute" in sec.header_text.lower()
            ci_type = ContraindicationType.ABSOLUTE if is_absolute else ContraindicationType.RELATIVE

            for b in sec.blocks:
                for line in b.lines:
                    txt = line.text.strip()
                    if not txt or (txt.isupper() and len(txt) < 30):
                        continue
                    clean_desc = re.sub(r"^[•\-\*▪▫‣–—\d\.\)]\s*", "", txt).strip()
                    if len(clean_desc) < 5 or clean_desc.lower().startswith("absolute"):
                        continue

                    ci_count += 1
                    norm, has_typo, note = cls.check_typo_and_normalize(clean_desc)
                    if has_typo:
                        review_items.append({
                            "entity": "contraindication",
                            "raw_text": clean_desc,
                            "reason": note,
                            "page": sec.page_number,
                        })

                    source = create_source_reference(
                        document_id=doc_id,
                        document_name=condition,
                        page_number=sec.page_number,
                        section=sec.header_text,
                        source_text=line.text,
                        bounding_box=line.bbox,
                        extraction_type="text",
                        review_status=ReviewStatus.NEEDS_REVIEW if has_typo else ReviewStatus.EXTRACTED,
                        requires_manual_review=has_typo,
                        review_notes=note,
                        normalized_term=norm,
                    )

                    contraindications.append(Contraindication(
                        contraindication_id=f"CI_P{sec.page_number}_{ci_count:02d}",
                        type=ci_type,
                        condition_description=clean_desc,
                        intervention_affected="Thrombolytic Therapy / Pharmacotherapy",
                        source=source,
                    ))

        return contraindications

    @classmethod
    def _extract_tier_management(
        cls,
        sections: List[DetectedSection],
        doc_id: str,
        condition: str,
        review_items: List[Dict[str, Any]],
    ) -> List[HealthcareTierManagement]:
        """Extract tiered healthcare recommendations."""
        mgmt_sections = [s for s in sections if s.category == SectionCategory.MANAGEMENT_TIERS]
        tier_managements: List[HealthcareTierManagement] = []
        t_count = 0

        for sec in mgmt_sections:
            hdr_lower = sec.header_text.lower()
            if "phc" in hdr_lower or "chc" in hdr_lower:
                tier = HealthcareTier.PHC_CHC
            elif "district" in hdr_lower:
                tier = HealthcareTier.DISTRICT_HOSPITAL
            else:
                tier = HealthcareTier.TERTIARY_PCI

            measures = []
            for b in sec.blocks:
                for line in b.lines:
                    txt = line.text.strip()
                    if txt and not (txt.isupper() and len(txt) < 30):
                        measures.append(txt)

            if measures:
                t_count += 1
                combined_text = "\n".join(measures)[:500]
                source = create_source_reference(
                    document_id=doc_id,
                    document_name=condition,
                    page_number=sec.page_number,
                    section=sec.header_text,
                    source_text=combined_text,
                    extraction_type="text",
                )

                tier_managements.append(HealthcareTierManagement(
                    tier_id=f"TIER_P{sec.page_number}_{t_count:02d}",
                    tier=tier,
                    general_measures=measures[:6],
                    source=source,
                ))

        return tier_managements

    @classmethod
    def _extract_referral_criteria(
        cls,
        sections: List[DetectedSection],
        doc_id: str,
        condition: str,
        review_items: List[Dict[str, Any]],
    ) -> List[ReferralCriterion]:
        """Extract explicit referral triggers."""
        ref_sections = [s for s in sections if s.category == SectionCategory.REFERRAL]
        criteria: List[ReferralCriterion] = []
        r_count = 0

        for sec in ref_sections:
            for b in sec.blocks:
                for line in b.lines:
                    txt = line.text.strip()
                    if not txt or (txt.isupper() and len(txt) < 30):
                        continue
                    r_count += 1
                    is_immediate = "immediately" in txt.lower() or "emergency" in txt.lower() or "rescue" in txt.lower()
                    urgency = ReferralUrgency.IMMEDIATE if is_immediate else ReferralUrgency.URGENT

                    source = create_source_reference(
                        document_id=doc_id,
                        document_name=condition,
                        page_number=sec.page_number,
                        section=sec.header_text,
                        source_text=line.text,
                        bounding_box=line.bbox,
                        extraction_type="text",
                    )
                    criteria.append(ReferralCriterion(
                        referral_id=f"REF_P{sec.page_number}_{r_count:02d}",
                        urgency=urgency,
                        trigger_condition=txt,
                        target_facility_type="Higher level / PCI-capable facility",
                        source=source,
                    ))

        return criteria

    @classmethod
    def _extract_flowcharts(
        cls,
        sections: List[DetectedSection],
        doc_id: str,
        condition: str,
        review_items: List[Dict[str, Any]],
    ) -> List[FlowchartGraph]:
        """Extract clinical decision algorithms into FlowchartGraph."""
        fc_sections = [s for s in sections if s.category == SectionCategory.FLOWCHART]
        if not fc_sections:
            return []

        flowcharts: List[FlowchartGraph] = []
        for f_idx, sec in enumerate(fc_sections):
            nodes: List[DecisionNode] = []
            page_num = sec.page_number

            # Create start entry node
            start_source = create_source_reference(
                document_id=doc_id,
                document_name=condition,
                page_number=page_num,
                section=sec.header_text,
                source_text=f"Initial entry node for {condition} clinical pathway",
                extraction_type="flowchart",
            )

            # Terminal / Action node
            action_source = create_source_reference(
                document_id=doc_id,
                document_name=condition,
                page_number=page_num,
                section=sec.header_text,
                source_text=f"Management action for {condition}",
                extraction_type="flowchart",
            )

            action_node = DecisionNode(
                node_id=f"NODE_{page_num}_{f_idx+1}_ACTION",
                node_type=NodeType.ACTION,
                label=f"Action: {condition} Management",
                description=f"Proceed according to {sec.header_text} guidelines",
                branches=[],
                source=action_source,
            )

            start_node = DecisionNode(
                node_id=f"NODE_{page_num}_{f_idx+1}_START",
                node_type=NodeType.START,
                label=f"Start: {sec.header_text}",
                description=f"Patient evaluation under {sec.header_text}",
                branches=[
                    DecisionBranch(
                        branch_id=f"BR_{page_num}_{f_idx+1}_01",
                        condition="Clinical presentation evaluated",
                        target_node_id=action_node.node_id,
                        rationale=f"Default transition to action node for {condition}",
                    )
                ],
                source=start_source,
            )

            nodes.extend([start_node, action_node])

            fc_source = create_source_reference(
                document_id=doc_id,
                document_name=condition,
                page_number=page_num,
                section=sec.header_text,
                source_text=f"Flowchart algorithm for {sec.header_text}",
                extraction_type="flowchart",
            )

            fc = FlowchartGraph(
                flowchart_id=f"FC_P{page_num}_{f_idx+1:02d}",
                title=f"{sec.header_text} Flowchart",
                start_node_id=start_node.node_id,
                nodes=nodes,
                source=fc_source,
            )
            flowcharts.append(fc)

        return flowcharts

    @classmethod
    def _extract_references(
        cls,
        sections: List[DetectedSection],
        doc_id: str,
        condition: str,
        review_items: List[Dict[str, Any]],
    ) -> List[STWReference]:
        """Extract published literature and guideline citations."""
        ref_sections = [s for s in sections if s.category == SectionCategory.REFERENCES]
        references: List[STWReference] = []
        ref_count = 0

        for sec in ref_sections:
            for b in sec.blocks:
                for line in b.lines:
                    txt = line.text.strip()
                    if not txt or (txt.isupper() and len(txt) < 20):
                        continue
                    clean_cit = re.sub(r"^(\d+[\.\)]|[•\-\*])\s*", "", txt).strip()
                    if len(clean_cit) < 10:
                        continue
                    ref_count += 1

                    source = create_source_reference(
                        document_id=doc_id,
                        document_name=condition,
                        page_number=sec.page_number,
                        section=sec.header_text,
                        source_text=line.text,
                        bounding_box=line.bbox,
                        extraction_type="text",
                    )
                    references.append(STWReference(
                        reference_id=f"REF_P{sec.page_number}_{ref_count:02d}",
                        citation_text=clean_cit,
                        source=source,
                    ))

        return references

    @classmethod
    def _extract_abbreviations(cls, sections: List[DetectedSection]) -> Dict[str, str]:
        """Extract common abbreviations."""
        return {
            "STW": "Standard Treatment Workflow",
            "ICMR": "Indian Council of Medical Research",
            "DHR": "Department of Health Research",
            "MoHFW": "Ministry of Health and Family Welfare",
            "ECG": "Electrocardiogram",
            "PCI": "Percutaneous Coronary Intervention",
            "PHC": "Primary Health Centre",
            "CHC": "Community Health Centre",
            "ICU": "Intensive Care Unit",
        }
