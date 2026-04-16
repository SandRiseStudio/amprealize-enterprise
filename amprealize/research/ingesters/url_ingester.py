"""URL ingester - OSS Stub. Full implementation in amprealize-enterprise."""

try:
    from amprealize.enterprise.research.ingesters.url_ingester import URLIngester
except ImportError:
    URLIngester = None  # type: ignore[assignment,misc]
