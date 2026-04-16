"""PDF source ingester.

Imported by OSS as:

    from amprealize.enterprise.research.ingesters.pdf_ingester import PDFIngester
"""

from __future__ import annotations

from typing import Any

from amprealize.enterprise.research.ingesters.base import BaseIngester, IngestResult


class PDFIngester(BaseIngester):
    """Ingests content from PDF files.

    Stub — replace with real PDF parsing (pdfplumber, PyMuPDF, etc.).
    """

    async def ingest(self, source: str, **kwargs: Any) -> IngestResult:
        raise NotImplementedError("PDFIngester.ingest not yet implemented")
