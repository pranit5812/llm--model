"""Document loader for ICMR STW PDF files with integrity and page verification."""

from dataclasses import dataclass, field
import hashlib
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional
import pymupdf


@dataclass
class PageData:
    """Encapsulates page-level boundaries and layout dimensions."""
    page_number: int
    width: float
    height: float
    raw_text: str
    rect: List[float]
    doc_page: Any = field(repr=False)


@dataclass
class LoadedDocument:
    """Encapsulates a loaded ICMR PDF document with verified cryptographic hash."""
    document_id: str
    file_path: Path
    sha256_hash: str
    page_count: int
    pdf_metadata: Dict[str, Any]
    pages: List[PageData]
    doc: Any = field(repr=False)

    def get_page(self, page_number: int) -> PageData:
        """Retrieve 1-indexed page."""
        if page_number < 1 or page_number > self.page_count:
            raise IndexError(f"Page {page_number} out of bounds for document with {self.page_count} pages")
        return self.pages[page_number - 1]

    def close(self) -> None:
        """Release PyMuPDF document handle."""
        if self.doc:
            self.doc.close()


class PDFLoader:
    """Loader for ICMR STW PDF documents."""

    @staticmethod
    def calculate_sha256(file_path: Path) -> str:
        """Calculate SHA-256 checksum of file."""
        hasher = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()

    @classmethod
    def load(cls, file_path: str | Path, document_id: str = "UNKNOWN") -> LoadedDocument:
        """Load and validate an ICMR PDF document."""
        p = Path(file_path)
        if not p.exists():
            raise FileNotFoundError(f"PDF file not found at {p}")
        if not p.is_file() or p.suffix.lower() != ".pdf":
            raise ValueError(f"Path {p} is not a valid .pdf file")

        sha256_hash = cls.calculate_sha256(p)
        doc = pymupdf.open(str(p))

        pages: List[PageData] = []
        for i, page in enumerate(doc):
            rect = page.rect
            page_data = PageData(
                page_number=i + 1,
                width=float(rect.width),
                height=float(rect.height),
                raw_text=page.get_text(),
                rect=[float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)],
                doc_page=page,
            )
            pages.append(page_data)

        return LoadedDocument(
            document_id=document_id,
            file_path=p,
            sha256_hash=sha256_hash,
            page_count=len(pages),
            pdf_metadata=doc.metadata or {},
            pages=pages,
            doc=doc,
        )
