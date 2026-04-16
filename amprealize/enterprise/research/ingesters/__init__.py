"""Enterprise research ingesters.

Imported by OSS as:

    from amprealize.enterprise.research.ingesters import (
        BaseIngester,
        MarkdownIngester,
        URLIngester,
        PDFIngester,
        count_words,
        extract_figure_captions,
        extract_metadata_from_markdown,
        extract_table_captions,
        parse_markdown_sections,
    )

Individual ingesters are also available via submodules:

    from amprealize.enterprise.research.ingesters.base import BaseIngester, ...
    from amprealize.enterprise.research.ingesters.markdown_ingester import MarkdownIngester
    from amprealize.enterprise.research.ingesters.url_ingester import URLIngester
    from amprealize.enterprise.research.ingesters.pdf_ingester import PDFIngester
"""

from amprealize.enterprise.research.ingesters.base import (
    BaseIngester,
    count_words,
    extract_figure_captions,
    extract_metadata_from_markdown,
    extract_table_captions,
    parse_markdown_sections,
)
from amprealize.enterprise.research.ingesters.markdown_ingester import MarkdownIngester
from amprealize.enterprise.research.ingesters.url_ingester import URLIngester
from amprealize.enterprise.research.ingesters.pdf_ingester import PDFIngester

__all__ = [
    "BaseIngester",
    "MarkdownIngester",
    "URLIngester",
    "PDFIngester",
    "count_words",
    "extract_figure_captions",
    "extract_metadata_from_markdown",
    "extract_table_captions",
    "parse_markdown_sections",
]
