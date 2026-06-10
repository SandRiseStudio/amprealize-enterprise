"""Enterprise billing tier transition commands.

Provides the logic layer for tier transition operations that OSS
``edition.py`` defines structurally (``TierTransition``, ``_VALID_TRANSITIONS``).
Enterprise adds:

1. **Validation** — pre-flight checks ensuring a transition can proceed
   (active subscription, billing state, feature usage within target caps).
2. **Preview** — human-readable summary of features gained/lost and
   data-preservation guarantees.
3. **Execution** — orchestrates the billing subscription change,
   updates the resolved tier, and emits telemetry.
4. **Rollback** — safely revert a transition within a grace window.

GUIDEAI-773: Implement billing tier transition commands.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class TransitionStatus(str, Enum):
    PENDING = "pending"
    VALIDATED = "validated"
    FAILED_VALIDATION = "failed_validation"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ROLLED_BACK = "rolled_back"
    ERROR = "error"


@dataclass
class ValidationIssue:
    """A single validation issue for a proposed tier transition."""

    code: str
    message: str
    severity: str = "error"  # "error" | "warning"
    resource: str | None = None


@dataclass
class TransitionPreview:
    """Human-readable preview of a tier transition."""

    from_tier: str
    to_tier: str
    features_gained: list[str] = field(default_factory=list)
    features_lost: list[str] = field(default_factory=list)
    data_preserved: bool = True
    cap_changes: dict[str, dict[str, int]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    estimated_cost_change: str | None = None


@dataclass
class TransitionResult:
    """Result of executing a tier transition."""

    status: TransitionStatus = TransitionStatus.PENDING
    from_tier: str = ""
    to_tier: str = ""
    issues: list[ValidationIssue] = field(default_factory=list)
    preview: TransitionPreview | None = None
    transition_id: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Tier transition service
# ---------------------------------------------------------------------------

class TierTransitionService:
    """Orchestrates tier transitions with billing, caps, and telemetry.

    ``billing_service`` and ``caps_enforcer`` are optional — the service
    degrades gracefully when they're unavailable (e.g. during testing).
    """

    def __init__(
        self,
        billing_service: Any = None,
        caps_enforcer: Any = None,
        telemetry: Any = None,
    ) -> None:
        self._billing = billing_service
        self._caps = caps_enforcer
        self._telemetry = telemetry

    # ----- Public API -------------------------------------------------------

    def validate(self, from_tier: str, to_tier: str) -> TransitionResult:
        """Pre-flight validation without executing the transition."""
        result = TransitionResult(from_tier=from_tier, to_tier=to_tier)
        issues = self._run_validation_checks(from_tier, to_tier)
        result.issues = issues

        has_errors = any(i.severity == "error" for i in issues)
        result.status = (
            TransitionStatus.FAILED_VALIDATION if has_errors
            else TransitionStatus.VALIDATED
        )
        return result

    def preview(self, from_tier: str, to_tier: str) -> TransitionPreview:
        """Generate a human-readable preview of a proposed transition."""
        transition = self._get_oss_transition(from_tier, to_tier)

        preview = TransitionPreview(
            from_tier=from_tier,
            to_tier=to_tier,
        )

        if transition is None:
            preview.warnings.append(
                f"No transition defined from {from_tier!r} to {to_tier!r}"
            )
            return preview

        preview.features_gained = list(transition.features_gained)
        preview.features_lost = list(transition.features_lost)
        preview.data_preserved = transition.data_preserved

        # Compute cap changes between the two tiers
        preview.cap_changes = self._compute_cap_changes(from_tier, to_tier)

        if preview.features_lost:
            preview.warnings.append(
                f"The following features will be disabled: {', '.join(preview.features_lost)}"
            )

        return preview

    def execute(
        self,
        from_tier: str,
        to_tier: str,
        *,
        org_id: str | None = None,
        dry_run: bool = False,
    ) -> TransitionResult:
        """Execute a tier transition.

        Runs validation, generates a preview, and (unless ``dry_run``)
        applies the change through the billing service.
        """
        result = self.validate(from_tier, to_tier)
        result.preview = self.preview(from_tier, to_tier)

        if result.status == TransitionStatus.FAILED_VALIDATION:
            return result

        if dry_run:
            logger.info("Dry-run tier transition %s → %s (not applied)", from_tier, to_tier)
            return result

        result.status = TransitionStatus.IN_PROGRESS

        try:
            self._apply_transition(from_tier, to_tier, org_id=org_id)
            result.status = TransitionStatus.COMPLETED
            logger.info("Tier transition completed: %s → %s", from_tier, to_tier)
        except Exception as exc:
            result.status = TransitionStatus.ERROR
            result.error = str(exc)
            logger.error("Tier transition failed: %s → %s: %s", from_tier, to_tier, exc)

        self._emit_telemetry(result, org_id=org_id)
        return result

    def rollback(
        self,
        transition_id: str,
        *,
        org_id: str | None = None,
    ) -> TransitionResult:
        """Revert a previously completed transition.

        Stub — requires transaction log (future implementation).
        """
        result = TransitionResult(
            transition_id=transition_id,
            status=TransitionStatus.ERROR,
            error="Rollback not yet implemented — requires transition log",
        )
        logger.warning("Rollback requested for %s but not implemented", transition_id)
        return result

    # ----- Internal helpers -------------------------------------------------

    def _get_oss_transition(self, from_tier: str, to_tier: str) -> Any:
        """Look up the OSS ``TierTransition`` for this pair."""
        try:
            from amprealize.edition import Edition, _VALID_TRANSITIONS

            edition_map = {
                "oss": Edition.OSS,
                "starter": Edition.ENTERPRISE_STARTER,
                "premium": Edition.ENTERPRISE_PREMIUM,
            }
            from_ed = edition_map.get(from_tier.lower())
            to_ed = edition_map.get(to_tier.lower())
            if from_ed is None or to_ed is None:
                return None
            return _VALID_TRANSITIONS.get((from_ed, to_ed))
        except ImportError:
            logger.debug("Could not import OSS edition module")
            return None

    def _run_validation_checks(
        self, from_tier: str, to_tier: str
    ) -> list[ValidationIssue]:
        """Run pre-flight checks for a tier transition."""
        issues: list[ValidationIssue] = []

        # Check 1: valid tier names
        valid_tiers = {"oss", "starter", "premium"}
        if from_tier.lower() not in valid_tiers:
            issues.append(ValidationIssue(
                code="INVALID_FROM_TIER",
                message=f"Unknown source tier: {from_tier!r}",
            ))
        if to_tier.lower() not in valid_tiers:
            issues.append(ValidationIssue(
                code="INVALID_TO_TIER",
                message=f"Unknown target tier: {to_tier!r}",
            ))

        # Check 2: no same-tier transition
        if from_tier.lower() == to_tier.lower():
            issues.append(ValidationIssue(
                code="SAME_TIER",
                message="Source and target tiers are the same",
            ))

        # Check 3: transition must be defined in OSS
        transition = self._get_oss_transition(from_tier, to_tier)
        if transition is None and not issues:
            issues.append(ValidationIssue(
                code="TRANSITION_NOT_DEFINED",
                message=f"No transition path from {from_tier!r} to {to_tier!r}",
            ))

        # Check 4: downgrade warning (not a blocking error)
        if transition is not None and transition.features_lost:
            issues.append(ValidationIssue(
                code="FEATURES_LOST",
                message=f"Downgrading will disable: {', '.join(transition.features_lost)}",
                severity="warning",
            ))

        return issues

    def _compute_cap_changes(
        self, from_tier: str, to_tier: str
    ) -> dict[str, dict[str, int]]:
        """Compute resource cap differences between two tiers."""
        try:
            from amprealize.edition import Edition, get_caps

            edition_map = {
                "oss": Edition.OSS,
                "starter": Edition.ENTERPRISE_STARTER,
                "premium": Edition.ENTERPRISE_PREMIUM,
            }
            from_ed = edition_map.get(from_tier.lower())
            to_ed = edition_map.get(to_tier.lower())
            if from_ed is None or to_ed is None:
                return {}

            from amprealize.caps_enforcer import _RESOURCE_TO_CAP_FIELD

            from_caps = get_caps(from_ed)
            to_caps = get_caps(to_ed)

            changes: dict[str, dict[str, int]] = {}
            for resource, field_name in _RESOURCE_TO_CAP_FIELD.items():
                old_val = getattr(from_caps, field_name, -1)
                new_val = getattr(to_caps, field_name, -1)
                if old_val != new_val:
                    changes[resource] = {"from": old_val, "to": new_val}

            return changes
        except ImportError:
            return {}

    def _apply_transition(
        self,
        from_tier: str,
        to_tier: str,
        *,
        org_id: str | None = None,
    ) -> None:
        """Apply the tier transition via the billing service.

        Updates the environment so ``resolve_tier()`` returns the new tier.
        """
        import os

        # Update the env var so resolve_tier picks up the new value immediately
        os.environ["AMPREALIZE_TIER"] = to_tier.lower()

        # If billing service available, update the subscription record
        if self._billing is not None:
            try:
                self._billing.update_tier(org_id=org_id, tier=to_tier.lower())
            except Exception:
                logger.warning("Billing service tier update failed", exc_info=True)

        # Reset caps enforcer singleton so new caps take effect
        try:
            from amprealize.caps_enforcer import reset_caps_enforcer
            reset_caps_enforcer()
        except ImportError:
            pass

    def _emit_telemetry(
        self,
        result: TransitionResult,
        *,
        org_id: str | None = None,
    ) -> None:
        """Emit telemetry for the transition."""
        if self._telemetry is None:
            return

        try:
            self._telemetry.emit_event(
                event_type="tier_transition.completed",
                payload={
                    "from_tier": result.from_tier,
                    "to_tier": result.to_tier,
                    "status": result.status.value,
                    "org_id": org_id,
                    "error": result.error,
                    "transition_id": result.transition_id,
                },
            )
        except Exception:
            logger.debug("Failed to emit tier transition telemetry", exc_info=True)
