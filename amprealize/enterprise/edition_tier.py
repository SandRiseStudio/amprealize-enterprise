"""Enterprise edition tier resolution.

The OSS ``amprealize.edition`` module has ``resolve_tier = None`` by default.
When this package is installed, the OSS module can delegate to this function
to determine the active enterprise tier.

Resolution order:
1. ``AMPREALIZE_TIER`` environment variable (``"starter"`` or ``"premium"``)
2. Billing service lookup (when configured via ``AMPREALIZE_BILLING_DSN``)
3. License key validation (when ``AMPREALIZE_LICENSE_KEY`` is set)
4. Default: ``"starter"``

GUIDEAI-771: Implement enterprise edition tier resolver.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_VALID_TIERS = ("starter", "premium")


def resolve_tier() -> str:
    """Determine the active enterprise tier.

    Returns ``"starter"`` or ``"premium"``.
    """
    # 1. Explicit env-var override (useful for testing / staging)
    env_tier = os.environ.get("AMPREALIZE_TIER", "").strip().lower()
    if env_tier in _VALID_TIERS:
        logger.debug("Tier resolved from AMPREALIZE_TIER env: %s", env_tier)
        return env_tier

    # 2. Billing service lookup
    tier = _resolve_from_billing()
    if tier is not None:
        return tier

    # 3. License key validation
    tier = _resolve_from_license()
    if tier is not None:
        return tier

    # 4. Default
    logger.debug("No tier source configured — defaulting to starter")
    return "starter"


def _resolve_from_billing() -> str | None:
    """Query the billing service for the org's active subscription tier."""
    dsn = os.environ.get("AMPREALIZE_BILLING_DSN")
    if not dsn:
        return None

    try:
        from amprealize.enterprise.billing.service import AmprealizeBillingService

        # The billing service stores subscription tier as part of the
        # active subscription record.  We read the cached org tier.
        svc = AmprealizeBillingService(dsn=dsn)
        tier = svc.get_cached_tier()
        if tier in _VALID_TIERS:
            logger.debug("Tier resolved from billing service: %s", tier)
            return tier
    except Exception:
        logger.debug("Billing tier lookup failed — falling through", exc_info=True)

    return None


def _resolve_from_license() -> str | None:
    """Validate a license key and extract the tier claim."""
    license_key = os.environ.get("AMPREALIZE_LICENSE_KEY", "").strip()
    if not license_key:
        return None

    tier = _decode_license_tier(license_key)
    if tier in _VALID_TIERS:
        logger.debug("Tier resolved from license key: %s", tier)
        return tier

    logger.warning("License key present but tier claim invalid: %r", tier)
    return None


def _decode_license_tier(key: str) -> str | None:
    """Decode the tier from a license key.

    License keys use the format ``<tier>-<signature>`` where valid tiers
    are ``starter`` and ``premium``.  Full cryptographic verification
    will be added in a future release.
    """
    parts = key.split("-", 1)
    if parts and parts[0].lower() in _VALID_TIERS:
        return parts[0].lower()
    return None
