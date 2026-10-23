"""Section detection module identifying actual headings and grouping text blocks."""

from dataclasses import dataclass, field
from enum import Enum
import re
from typing import List, Optional
from src.extraction.text_extractor import ExtractedPage, TextBlock


class SectionCategory(str, Enum):
    TITLE_METADATA = "TITLE_METADATA"
    CLINICAL_PRESENTATION = "CLINICAL_PRESENTATION"
    DIAGNOSTIC_CRITERIA = "DIAGNOSTIC_CRITERIA"
    INVESTIGATIONS = "INVESTIGATIONS"
    DRUGS_DOSAGE = "DRUGS_DOSAGE"
    MANAGEMENT_TIERS = "MANAGEMENT_TIERS"
    CONTRAINDICATIONS = "CONTRAINDICATIONS"
    FLOWCHART = "FLOWCHART"
    REFERRAL = "REFERRAL"
    REFERENCES = "REFERENCES"
    COMMITTEE = "COMMITTEE"
    GENERAL = "GENERAL"


@dataclass
class DetectedSection:
    """A detected document section containing header text, category, and constituent blocks."""
    section_id: str
    page_number: int
    header_text: str
    category: SectionCategory
    bbox: List[float]
    blocks: List[TextBlock] = field(default_factory=list)
    confidence: float = 1.0


class SectionDetector:
    """Detects headings from visual typography, uppercase banners, and keywords."""

    # Heading signatures across ICMR STWs
    KNOWN_PATTERNS = [
        (re.compile(r"^(STANDARD TREATMENT WORKFLOW|ICD-11)", re.IGNORECASE), SectionCategory.TITLE_METADATA),
        (re.compile(r"^(CONSIDER ANGINA|ANGINA UNLIKELY|CATEGORIZE|WHEN TO SUSPECT|CLINICAL PRESENTATION|ACUTE CORONARY SYNDROME)", re.IGNORECASE), SectionCategory.CLINICAL_PRESENTATION),
        (re.compile(r"^(STEMI DIAGNOSIS|ECG REVEALS|DIAGNOSTIC CRITERIA)", re.IGNORECASE), SectionCategory.DIAGNOSTIC_CRITERIA),
        (re.compile(r"^(BASIC INVESTIGATIONS|DESIRABLE INVESTIGATIONS|OPTIONAL INVESTIGATIONS|ESSENTIAL INVESTIGATIONS|OTHER INVESTIGATIONS|INVESTIGATIONS)", re.IGNORECASE), SectionCategory.INVESTIGATIONS),
        (re.compile(r"^(DRUGS\s*&\s*DOSAGE|ANTI-PLATELETS|ANTI-ISCHEMIC|THROMBOLYIC THERAPY|ANTI THROMBOTICS|PHARMACOTHERAPY|SPIRONOLACTONE|FUROSEMIDE|ARNI|CHOICE OF ANTI-COAGULATION|RATE CONTROL DRUGS|ANTICOAGULANTS)", re.IGNORECASE), SectionCategory.DRUGS_DOSAGE),
        (re.compile(r"^(GENERAL MEASURES|MANAGEMENT AT PHC|MANAGEMENT AT DISTRICT|PCI CAPABLE|PCI INCAPABLE|DURING PROCEDURE|POST PROCEDURE|PHC/CHC LEVEL|DISTRICT HOSPITAL LEVEL|TERTIARY CARE LEVEL)", re.IGNORECASE), SectionCategory.MANAGEMENT_TIERS),
        (re.compile(r"^(ABSOLUTE CONTRA-INDICATIONS|CONTRA-INDICATIONS|CONTRAINDICATIONS|CAUTIONS|RULE OUT|LOOK FOR REVERSIBLE)", re.IGNORECASE), SectionCategory.CONTRAINDICATIONS),
        (re.compile(r"^(PATIENT WITH STEMI|MISSION:\s*LIFELINE|FLOWCHART|EVALUATION AND MANAGEMENT|EVALUATION AND TREATMENT|CATEGORIZE|RATE VS RHYTHM)", re.IGNORECASE), SectionCategory.FLOWCHART),
        (re.compile(r"^(REFERRAL|TRANSFER TO PCI|WHEN TO REFER|IMMEDIATE INTERVENTION|LOOK FOR IMMEDIATE INTERVENTION)", re.IGNORECASE), SectionCategory.REFERRAL),
        (re.compile(r"^(REFERENCES|SUGGESTED CITATION)", re.IGNORECASE), SectionCategory.REFERENCES),
        (re.compile(r"^(ADVISORY COMMITTEE|EXPERT GROUPS|SECRETARIAT)", re.IGNORECASE), SectionCategory.COMMITTEE),
    ]

    @classmethod
    def classify_heading(cls, text: str) -> SectionCategory:
        """Map header text to semantic SectionCategory using regex signatures."""
        clean = text.strip()
        for pattern, category in cls.KNOWN_PATTERNS:
            if pattern.search(clean):
                return category
        return SectionCategory.GENERAL

    @classmethod
    def is_likely_heading(cls, block: TextBlock) -> bool:
        """Determine if a text block represents a section heading."""
        if block.is_heading_candidate:
            return True

        first_line = block.lines[0].text.strip() if block.lines else ""
        if not first_line:
            return False

        # Short uppercase lines
        if len(first_line) < 60 and first_line.isupper() and not first_line.startswith(("•", "-", "*")):
            return True

        # Known pattern match
        for pattern, _ in cls.KNOWN_PATTERNS:
            if pattern.search(first_line):
                return True

        return False

    @classmethod
    def detect_sections(cls, page: ExtractedPage) -> List[DetectedSection]:
        """Detect sections and group text blocks under their respective headings."""
        sections: List[DetectedSection] = []
        current_section: Optional[DetectedSection] = None
        sec_counter = 0

        for block in page.blocks:
            if cls.is_likely_heading(block):
                sec_counter += 1
                first_line = block.lines[0].text.strip() if block.lines else block.text.split("\n")[0]
                category = cls.classify_heading(first_line)

                current_section = DetectedSection(
                    section_id=f"SEC_P{page.page_number}_{sec_counter:02d}",
                    page_number=page.page_number,
                    header_text=first_line,
                    category=category,
                    bbox=block.bbox,
                    blocks=[block],
                )
                sections.append(current_section)
            else:
                if current_section is not None:
                    current_section.blocks.append(block)
                else:
                    # Content before the first heading: place in introductory section
                    sec_counter += 1
                    current_section = DetectedSection(
                        section_id=f"SEC_P{page.page_number}_{sec_counter:02d}",
                        page_number=page.page_number,
                        header_text="INTRODUCTORY_CONTENT",
                        category=SectionCategory.GENERAL,
                        bbox=block.bbox,
                        blocks=[block],
                    )
                    sections.append(current_section)

        return sections
