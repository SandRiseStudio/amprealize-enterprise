"""Enterprise billing API routes.

Imported by OSS as:

    from amprealize.enterprise.billing.api import (
        create_billing_router,
        CreateCustomerRequest,
        UpdateCustomerRequest,
        CustomerResponse,
        CreateSubscriptionRequest,
        UpdateSubscriptionRequest,
        SubscriptionResponse,
        RecordUsageRequest,
        UsageResponse,
        UsageSummaryResponse,
        InvoiceResponse,
        PlanResponse,
        LimitCheckResponse,
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# --- Request models ---

@dataclass
class CreateCustomerRequest:
    name: str = ""
    email: str = ""
    org_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UpdateCustomerRequest:
    name: str | None = None
    email: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class CreateSubscriptionRequest:
    customer_id: str = ""
    plan_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class UpdateSubscriptionRequest:
    plan_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RecordUsageRequest:
    subscription_id: str = ""
    quantity: int = 0
    timestamp: str | None = None


# --- Response models ---

@dataclass
class CustomerResponse:
    id: str = ""
    name: str = ""
    email: str = ""
    org_id: str = ""
    created_at: str = ""


@dataclass
class SubscriptionResponse:
    id: str = ""
    customer_id: str = ""
    plan_id: str = ""
    status: str = ""
    created_at: str = ""


@dataclass
class UsageResponse:
    id: str = ""
    subscription_id: str = ""
    quantity: int = 0
    timestamp: str = ""


@dataclass
class UsageSummaryResponse:
    subscription_id: str = ""
    total_quantity: int = 0
    period_start: str = ""
    period_end: str = ""


@dataclass
class InvoiceResponse:
    id: str = ""
    customer_id: str = ""
    amount_due: int = 0
    currency: str = "usd"
    status: str = ""
    created_at: str = ""


@dataclass
class PlanResponse:
    id: str = ""
    name: str = ""
    amount: int = 0
    currency: str = "usd"
    interval: str = "month"


@dataclass
class LimitCheckResponse:
    allowed: bool = True
    current_usage: int = 0
    limit: int = 0
    resource: str = ""


def create_billing_router(
    billing_service: Any = None,
    caps_enforcer: Any = None,
    **kwargs: Any,
):
    """Create a FastAPI router for billing API endpoints.

    GUIDEAI-794: Real billing routes backed by TierTransitionService.
    """
    import logging

    from fastapi import APIRouter, HTTPException

    from .tier_transitions import TierTransitionService, TransitionStatus

    logger = logging.getLogger(__name__)

    router = APIRouter(tags=["billing"])
    transition_svc = TierTransitionService(
        billing_service=billing_service,
        caps_enforcer=caps_enforcer,
    )

    @router.get("/v1/billing/status")
    def billing_status() -> dict[str, Any]:
        """Return the current edition tier and capabilities."""
        from amprealize.edition import detect_edition, get_caps

        edition = detect_edition()
        caps = get_caps(edition)
        return {
            "edition": edition.value,
            "tier": "premium" if "premium" in edition.value else (
                "starter" if "starter" in edition.value else "oss"
            ),
            "features": {
                fname: getattr(caps, fname)
                for fname in (
                    "orgs", "billing", "sso", "analytics", "audit_logs",
                    "conversations", "collaboration", "self_improving",
                )
            },
        }

    @router.get("/v1/billing/usage")
    def billing_usage() -> dict[str, Any]:
        """Return resource usage summary against current caps."""
        from amprealize.caps_enforcer import get_caps_enforcer

        enforcer = get_caps_enforcer()
        return {
            "caps": enforcer.get_usage_summary(),
        }

    @router.post("/v1/billing/transition/preview")
    def transition_preview(from_tier: str, to_tier: str) -> dict[str, Any]:
        """Preview a tier transition without executing it."""
        preview = transition_svc.preview(from_tier, to_tier)
        return {
            "from_tier": preview.from_tier,
            "to_tier": preview.to_tier,
            "features_gained": preview.features_gained,
            "features_lost": preview.features_lost,
            "data_preserved": preview.data_preserved,
            "cap_changes": preview.cap_changes,
            "warnings": preview.warnings,
        }

    @router.post("/v1/billing/transition/validate")
    def transition_validate(from_tier: str, to_tier: str) -> dict[str, Any]:
        """Validate a proposed tier transition."""
        result = transition_svc.validate(from_tier, to_tier)
        return {
            "status": result.status.value,
            "issues": [
                {"code": i.code, "message": i.message, "severity": i.severity}
                for i in result.issues
            ],
        }

    @router.post("/v1/billing/transition/execute")
    def transition_execute(
        from_tier: str,
        to_tier: str,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Execute a tier transition."""
        result = transition_svc.execute(from_tier, to_tier, dry_run=dry_run)
        if result.status == TransitionStatus.FAILED_VALIDATION:
            raise HTTPException(
                status_code=400,
                detail={
                    "status": result.status.value,
                    "issues": [
                        {"code": i.code, "message": i.message, "severity": i.severity}
                        for i in result.issues
                    ],
                },
            )
        resp: dict[str, Any] = {
            "status": result.status.value,
            "from_tier": result.from_tier,
            "to_tier": result.to_tier,
        }
        if result.preview:
            resp["preview"] = {
                "features_gained": result.preview.features_gained,
                "features_lost": result.preview.features_lost,
                "cap_changes": result.preview.cap_changes,
            }
        if result.error:
            resp["error"] = result.error
        return resp

    @router.get("/v1/billing/limits/{resource}")
    def check_limit(resource: str) -> dict[str, Any]:
        """Check the limit for a specific resource."""
        from amprealize.caps_enforcer import get_caps_enforcer

        enforcer = get_caps_enforcer()
        limit = enforcer.get_limit(resource)
        return {
            "resource": resource,
            "limit": limit,
            "unlimited": limit == -1,
        }

    return router
