"""URL source ingester.

Imported by OSS as:

    from amprealize.enterprise.research.ingesters.url_ingester import URLIngester
"""

from __future__ import annotations

from typing import Any

from amprealize.enterprise.research.ingesters.base import BaseIngester, IngestResult


class URLIngester(BaseIngester):
    """Ingests content from URLs.

    Stub — replace with real HTTP fetching and content extraction.
    """

    async def ingest(self, source: str, **kwargs: Any) -> IngestResult:
        raise NotImplementedError("URLIngester.ingest not yet implemented")
