"""Enterprise billing service.

Imported by OSS as:

    from amprealize.enterprise.billing.service import (
        AmprealizeBillingService,
        AmprealizeBillingHooks,
    )
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class AmprealizeBillingHooks:
    """Hooks that OSS core calls into for billing side-effects."""

    async def on_run_start(self, run_id: str, **kwargs: Any) -> None:
        pass

    async def on_run_complete(self, run_id: str, **kwargs: Any) -> None:
        pass

    async def on_usage(self, resource: str, amount: int, **kwargs: Any) -> None:
        pass


class AmprealizeBillingService:
    """Stripe-backed billing service.

    Stub — replace with real Stripe integration.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._config = kwargs
        self.hooks = AmprealizeBillingHooks()
        self._dsn = kwargs.get("dsn")

    # ----- Tier resolution support (GUIDEAI-771) -----

    def get_cached_tier(self) -> str:
        """Return the cached subscription tier for the current org.

        Falls back to ``AMPREALIZE_BILLING_TIER`` env var, then ``"starter"``.
        A real implementation would query the subscriptions table.
        """
        env_tier = os.environ.get("AMPREALIZE_BILLING_TIER", "").strip().lower()
        if env_tier in ("starter", "premium"):
            return env_tier
        return "starter"

    # ----- Customer / Subscription stubs -----

    async def create_customer(self, **kwargs: Any) -> dict:
        raise NotImplementedError

    async def get_customer(self, customer_id: str) -> dict:
        raise NotImplementedError

    async def create_subscription(self, **kwargs: Any) -> dict:
        raise NotImplementedError

    async def record_usage(self, **kwargs: Any) -> dict:
        raise NotImplementedError

    async def get_invoices(self, customer_id: str) -> list[dict]:
        raise NotImplementedError
