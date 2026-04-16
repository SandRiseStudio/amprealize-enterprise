"""Markdown source ingester.

Imported by OSS as:

    from amprealize.enterprise.research.ingesters.markdown_ingester import MarkdownIngester
"""

from __future__ import annotations

from typing import Any

from amprealize.enterprise.research.ingesters.base import (
    BaseIngester,
    IngestResult,
    count_words,
    extract_metadata_from_markdown,
    parse_markdown_sections,
)


class MarkdownIngester(BaseIngester):
    """Ingests markdown files or strings.

    Stub — has basic implementation for parsing; extend for production.
    """

    async def ingest(self, source: str, **kwargs: Any) -> IngestResult:
        metadata = extract_metadata_from_markdown(source)
        sections = parse_markdown_sections(source)
        return IngestResult(
            content=source,
            metadata=metadata,
            word_count=count_words(source),
            sections=sections,
        )
