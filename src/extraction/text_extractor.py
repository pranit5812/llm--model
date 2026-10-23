"""Text extraction module for ICMR STWs with bounding boxes and layout preservation."""

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional
from src.extraction.pdf_loader import LoadedDocument, PageData


@dataclass
class TextSpan:
    """A granular span of text with font and size styling."""
    text: str
    bbox: List[float]
    font: str
    size: float
    flags: int


@dataclass
class TextLine:
    """A single line of text with bounding box and constituent spans."""
    text: str
    bbox: List[float]
    spans: List[TextSpan]
    is_bullet: bool = False
    is_numbered: bool = False


@dataclass
class TextBlock:
    """A block of text containing one or more lines."""
    block_id: str
    page_number: int
    bbox: List[float]
    text: str
    lines: List[TextLine]
    avg_font_size: float
    max_font_size: float
    is_heading_candidate: bool = False


@dataclass
class ExtractedPage:
    """Structured extraction output for a single PDF page."""
    page_number: int
    width: float
    height: float
    blocks: List[TextBlock]


@dataclass
class ExtractedDocument:
    """Intermediate extracted representation for an ICMR STW document."""
    document_id: str
    file_path: str
    sha256_hash: str
    total_pages: int
    pages: List[ExtractedPage]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize intermediate representation to JSON-compatible dictionary."""
        pages_data = []
        for p in self.pages:
            blocks_data = []
            for b in p.blocks:
                lines_data = []
                for l in b.lines:
                    spans_data = [asdict(s) for s in l.spans]
                    lines_data.append({
                        "text": l.text,
                        "bbox": l.bbox,
                        "is_bullet": l.is_bullet,
                        "is_numbered": l.is_numbered,
                        "spans": spans_data,
                    })
                blocks_data.append({
                    "block_id": b.block_id,
                    "page_number": b.page_number,
                    "bbox": b.bbox,
                    "text": b.text,
                    "avg_font_size": b.avg_font_size,
                    "max_font_size": b.max_font_size,
                    "is_heading_candidate": b.is_heading_candidate,
                    "lines": lines_data,
                })
            pages_data.append({
                "page_number": p.page_number,
                "width": p.width,
                "height": p.height,
                "blocks": blocks_data,
            })
        return {
            "document_id": self.document_id,
            "file_path": self.file_path,
            "sha256_hash": self.sha256_hash,
            "total_pages": self.total_pages,
            "pages": pages_data,
        }

    def save_json(self, output_path: str | Path) -> Path:
        """Save intermediate extracted JSON to disk."""
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        return out


class TextExtractor:
    """Extracts text elements with spatial coordinates and font metadata from PDF pages."""

    BULLET_REGEX = re.compile(r"^[•\-\*▪▫‣–—]\s*(.*)$")
    NUMBERED_REGEX = re.compile(r"^(\d+[\.\)]|[A-Za-z][\.\)])\s*(.*)$")

    @classmethod
    def extract_page(cls, page_data: PageData) -> ExtractedPage:
        """Extract structured text blocks from a single page."""
        doc_page = page_data.doc_page
        text_dict = doc_page.get_text("dict")
        raw_blocks = text_dict.get("blocks", [])

        structured_blocks: List[TextBlock] = []
        block_counter = 0

        for rb in raw_blocks:
            # We only process text blocks (type 0 in PyMuPDF)
            if rb.get("type", 0) != 0 or "lines" not in rb:
                continue

            block_counter += 1
            block_bbox = [float(x) for x in rb.get("bbox", [0, 0, 0, 0])]
            lines_list: List[TextLine] = []
            block_text_parts: List[str] = []
            font_sizes: List[float] = []

            for rl in rb.get("lines", []):
                line_spans: List[TextSpan] = []
                line_text_parts: List[str] = []
                line_bbox = [float(x) for x in rl.get("bbox", [0, 0, 0, 0])]

                for rs in rl.get("spans", []):
                    span_text = rs.get("text", "")
                    span_bbox = [float(x) for x in rs.get("bbox", [0, 0, 0, 0])]
                    span_font = rs.get("font", "")
                    span_size = float(rs.get("size", 0.0))
                    span_flags = int(rs.get("flags", 0))

                    if span_text.strip():
                        font_sizes.append(span_size)

                    line_text_parts.append(span_text)
                    line_spans.append(TextSpan(
                        text=span_text,
                        bbox=span_bbox,
                        font=span_font,
                        size=span_size,
                        flags=span_flags,
                    ))

                line_full_text = "".join(line_text_parts).strip()
                if not line_full_text:
                    continue

                is_bullet = bool(cls.BULLET_REGEX.match(line_full_text))
                is_numbered = bool(cls.NUMBERED_REGEX.match(line_full_text))

                lines_list.append(TextLine(
                    text=line_full_text,
                    bbox=line_bbox,
                    spans=line_spans,
                    is_bullet=is_bullet,
                    is_numbered=is_numbered,
                ))
                block_text_parts.append(line_full_text)

            if not lines_list:
                continue

            full_block_text = "\n".join(block_text_parts)
            avg_font = sum(font_sizes) / len(font_sizes) if font_sizes else 0.0
            max_font = max(font_sizes) if font_sizes else 0.0
            is_heading = max_font >= 13.0 or (avg_font >= 12.0 and full_block_text.isupper())

            structured_blocks.append(TextBlock(
                block_id=f"P{page_data.page_number}_B{block_counter:03d}",
                page_number=page_data.page_number,
                bbox=block_bbox,
                text=full_block_text,
                lines=lines_list,
                avg_font_size=round(avg_font, 2),
                max_font_size=round(max_font, 2),
                is_heading_candidate=is_heading,
            ))

        return ExtractedPage(
            page_number=page_data.page_number,
            width=page_data.width,
            height=page_data.height,
            blocks=structured_blocks,
        )

    @classmethod
    def extract_document(cls, loaded_doc: LoadedDocument) -> ExtractedDocument:
        """Extract structured text from all pages in a LoadedDocument."""
        pages: List[ExtractedPage] = []
        for page_data in loaded_doc.pages:
            pages.append(cls.extract_page(page_data))

        return ExtractedDocument(
            document_id=loaded_doc.document_id,
            file_path=str(loaded_doc.file_path),
            sha256_hash=loaded_doc.sha256_hash,
            total_pages=loaded_doc.page_count,
            pages=pages,
        )
