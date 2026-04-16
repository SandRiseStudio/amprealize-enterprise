"""Cloud client — enterprise fork re-export.

Delegates directly to ``amprealize.enterprise.cloud_client`` which
provides the real authenticated HTTP client to Amprealize.io.

Part of Phase 2 of GUIDEAI-782 (Enterprise Fork/Superset).
"""

from amprealize.enterprise.cloud_client import CloudClient  # noqa: F401


def get_cloud_client(
    cloud_url: str = "https://api.amprealize.io",
) -> CloudClient:
    """Return the enterprise cloud client."""
    return CloudClient(cloud_url=cloud_url)
