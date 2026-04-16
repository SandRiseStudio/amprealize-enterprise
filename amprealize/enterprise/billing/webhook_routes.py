"""Enterprise billing webhook routes.

Imported by OSS as:

    from amprealize.enterprise.billing.webhook_routes import (
        create_webhook_router,
        create_amprealize_webhook_router,
        WebhookResponse,
        WebhookStatusResponse,
    )
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class WebhookResponse:
    """Response from processing a webhook event."""

    success: bool = True
    message: str = ""


@dataclass
class WebhookStatusResponse:
    """Status of webhook processing health."""

    healthy: bool = True
    last_event_at: str | None = None
    pending_count: int = 0


def create_webhook_router(**kwargs: Any):
    """Create a FastAPI router for generic billing webhooks.

    Stub — replace with real Stripe webhook handler.
    """
    from fastapi import APIRouter
    return APIRouter()


def create_amprealize_webhook_router(**kwargs: Any):
    """Create a FastAPI router for Amprealize-specific billing webhooks.

    Stub — replace with real implementation.
    """
    from fastapi import APIRouter
    return APIRouter()
