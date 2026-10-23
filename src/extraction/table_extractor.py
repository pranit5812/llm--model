"""Table extraction module for ICMR STW documents with provenance preservation."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import pymupdf
from src.extraction.pdf_loader import PageData
from src.extraction.provenance import create_source_reference
from src.models.stw_schema import ReviewStatus, STWTable, STWTableRow


@dataclass
class RawTableExtraction:
    """Raw tabular extract from PDF before schema transformation."""
    page_number: int
    bbox: List[float]
    headers: List[str]
    rows: List[Dict[str, str]]
    source_text: str
    is_valid: bool
    requires_manual_review: bool
    review_notes: Optional[str] = None


class TableExtractor:
    """Extracts tables using PyMuPDF table finder and structural heuristics."""

    @classmethod
    def extract_tables_from_page(
        cls,
        page_data: PageData,
        document_id: str = "UNKNOWN",
        document_name: Optional[str] = None,
    ) -> List[STWTable]:
        """Extract structured STWTable instances from a given page."""
        doc_page = page_data.doc_page
        tables: List[STWTable] = []

        try:
            tab_finder = doc_page.find_tables()
            raw_tables = tab_finder.tables if hasattr(tab_finder, "tables") else []
        except Exception as e:
            # Table finder failed; do not invent table data
            return tables

        for t_idx, t in enumerate(raw_tables):
            try:
                extracted_grid = t.extract()
                if not extracted_grid or len(extracted_grid) < 2:
                    continue

                bbox = [float(x) for x in t.bbox]
                # First non-empty row serves as header candidate
                raw_headers = extracted_grid[0]
                headers = []
                for c_idx, h in enumerate(raw_headers):
                    clean_h = str(h).strip().replace("\n", " ") if h else f"Column_{c_idx+1}"
                    headers.append(clean_h)

                # Deduplicate headers if identical
                unique_headers = []
                seen_headers = {}
                for h in headers:
                    if h in seen_headers:
                        seen_headers[h] += 1
                        unique_headers.append(f"{h}_{seen_headers[h]}")
                    else:
                        seen_headers[h] = 1
                        unique_headers.append(h)
                headers = unique_headers

                rows_data: List[STWTableRow] = []
                table_text_lines = []

                for r_idx, row_values in enumerate(extracted_grid[1:]):
                    # Check if entire row is empty
                    if not any(v for v in row_values if v and str(v).strip()):
                        continue

                    cells_dict: Dict[str, str] = {}
                    row_text_parts = []
                    for c_idx, h in enumerate(headers):
                        val = row_values[c_idx] if c_idx < len(row_values) else ""
                        clean_val = str(val).strip().replace("\n", " ") if val is not None else ""
                        cells_dict[h] = clean_val
                        if clean_val:
                            row_text_parts.append(f"{h}: {clean_val}")

                    row_source_text = "; ".join(row_text_parts) if row_text_parts else f"Row {r_idx+1}"
                    table_text_lines.append(row_source_text)

                    # Determine if row is malformed or sparse
                    sparse_cells = sum(1 for v in cells_dict.values() if not v)
                    requires_review = sparse_cells > (len(headers) // 2)
                    review_notes = "Sparse row with potential merged columns" if requires_review else None

                    row_source = create_source_reference(
                        document_id=document_id,
                        document_name=document_name,
                        page_number=page_data.page_number,
                        section=f"TABLE_{t_idx+1}",
                        source_text=row_source_text,
                        bounding_box=bbox,
                        extraction_type="table",
                        review_status=ReviewStatus.NEEDS_REVIEW if requires_review else ReviewStatus.EXTRACTED,
                        requires_manual_review=requires_review,
                        review_notes=review_notes,
                    )

                    rows_data.append(STWTableRow(
                        row_id=f"T{t_idx+1}_R{r_idx+1}",
                        cells=cells_dict,
                        source=row_source,
                    ))

                if not rows_data:
                    continue

                full_table_text = "\n".join(table_text_lines)
                table_title = f"Table {t_idx+1} (Page {page_data.page_number})"

                table_source = create_source_reference(
                    document_id=document_id,
                    document_name=document_name,
                    page_number=page_data.page_number,
                    section=f"TABLE_{t_idx+1}",
                    source_text=full_table_text[:500],
                    bounding_box=bbox,
                    extraction_type="table",
                    review_status=ReviewStatus.EXTRACTED,
                    requires_manual_review=False,
                )

                stw_table = STWTable(
                    table_id=f"TAB_P{page_data.page_number}_{t_idx+1:02d}",
                    title=table_title,
                    headers=headers,
                    rows=rows_data,
                    source=table_source,
                )
                tables.append(stw_table)

            except Exception as ex:
                # Malformed table detected: create a fallback placeholder table marked for manual review
                error_source = create_source_reference(
                    document_id=document_id,
                    document_name=document_name,
                    page_number=page_data.page_number,
                    section=f"TABLE_{t_idx+1}",
                    source_text=f"Unparseable table: {str(ex)}",
                    bounding_box=[float(x) for x in t.bbox] if hasattr(t, "bbox") else None,
                    extraction_type="table",
                    review_status=ReviewStatus.NEEDS_REVIEW,
                    requires_manual_review=True,
                    review_notes=f"Table extraction failed with error: {str(ex)}",
                )
                fallback_row = STWTableRow(
                    row_id="ERR_R1",
                    cells={"Extraction_Error": f"Table extraction error: {str(ex)}"},
                    source=error_source,
                )
                fallback_table = STWTable(
                    table_id=f"TAB_P{page_data.page_number}_{t_idx+1:02d}_ERR",
                    title=f"Unparsed Table {t_idx+1} (Page {page_data.page_number})",
                    headers=["Extraction_Error"],
                    rows=[fallback_row],
                    source=error_source,
                )
                tables.append(fallback_table)

        return tables
