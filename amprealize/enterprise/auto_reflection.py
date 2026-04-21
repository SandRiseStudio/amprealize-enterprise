"""Enterprise auto-reflection hooks (Self-Improving Behaviors module).

The ``self_improving`` module in the OSS registry is gated to
``enterprise_premium``.  This module provides the enterprise-only hooks
that integrate with the OSS reflection pipeline to:

1. **Auto-propose** — automatically create behavior proposals from high-
   confidence reflection candidates.
2. **Auto-approve** — bypass Teacher review for candidates exceeding the
   quality threshold, integrating with the BehaviorService.
3. **Quality gate enforcement** — apply enterprise quality policies before
   candidates enter the review queue.
4. **Telemetry enrichment** — attach billing / org context to reflection
   telemetry events.
5. **ReviewQueueProcessor** — periodically drain the review queue, applying
   confidence-threshold-based approve/reject decisions.
6. **LifecyclePolicyEngine** — promote, deprecate, and archive behaviors
   automatically based on usage signals and age policies.

GUIDEAI-911: Implement auto-reflection hooks in enterprise repo.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_AUTO_APPROVE_THRESHOLD = 0.85
_DEFAULT_MAX_AUTO_APPROVALS_PER_RUN = 3
_DEFAULT_MIN_SUPPORTING_STEPS = 2


@dataclass
class AutoReflectionConfig:
    """Configuration for enterprise auto-reflection behavior."""

    auto_approve_threshold: float = _DEFAULT_AUTO_APPROVE_THRESHOLD
    max_auto_approvals_per_run: int = _DEFAULT_MAX_AUTO_APPROVALS_PER_RUN
    min_supporting_steps: int = _DEFAULT_MIN_SUPPORTING_STEPS
    require_quality_gate: bool = True
    enabled: bool = True


# ---------------------------------------------------------------------------
# Quality gate — enterprise validation before approval
# ---------------------------------------------------------------------------

@dataclass
class QualityGateResult:
    """Result of running the enterprise quality gate on a candidate."""

    passed: bool
    reasons: List[str] = field(default_factory=list)
    adjusted_confidence: float = 0.0


def run_quality_gate(
    candidate: Any,
    config: AutoReflectionConfig | None = None,
) -> QualityGateResult:
    """Evaluate a ``ReflectionCandidate`` against enterprise quality policies.

    Returns a ``QualityGateResult`` indicating pass/fail with reasons.
    """
    cfg = config or AutoReflectionConfig()
    reasons: list[str] = []

    scores = candidate.quality_scores
    min_dim = min(scores.clarity, scores.generality, scores.reusability, scores.correctness)

    # Gate 1: No quality dimension may be below 0.4
    if min_dim < 0.4:
        reasons.append(f"Minimum quality dimension {min_dim:.2f} < 0.40")

    # Gate 2: Must have enough supporting steps
    if len(candidate.supporting_steps) < cfg.min_supporting_steps:
        reasons.append(
            f"Too few supporting steps ({len(candidate.supporting_steps)}) "
            f"— minimum is {cfg.min_supporting_steps}"
        )

    # Gate 3: Instruction must be non-trivial
    if len(candidate.instruction.strip()) < 20:
        reasons.append("Instruction too short (< 20 chars)")

    # Gate 4: Must have a display name
    if not candidate.display_name.strip():
        reasons.append("Missing display name")

    passed = len(reasons) == 0

    # Adjusted confidence penalises low-quality dimensions
    adjusted = candidate.confidence * (1.0 if passed else 0.8)
    adjusted = max(0.0, min(1.0, adjusted))

    return QualityGateResult(
        passed=passed,
        reasons=reasons,
        adjusted_confidence=round(adjusted, 3),
    )


# ---------------------------------------------------------------------------
# Auto-reflection hooks
# ---------------------------------------------------------------------------

@dataclass
class AutoReflectionResult:
    """Summary of auto-reflection processing for a single run."""

    run_id: str
    candidates_received: int = 0
    gate_passed: int = 0
    gate_failed: int = 0
    auto_approved: int = 0
    queued_for_review: int = 0
    errors: List[str] = field(default_factory=list)


class AutoReflectionHooks:
    """Enterprise hooks that wire into the OSS reflection pipeline.

    Usage in OSS ``agent_execution_loop.py``::

        # After reflection produces candidates:
        if HAS_ENTERPRISE:
            from amprealize.enterprise.auto_reflection import AutoReflectionHooks
            hooks = AutoReflectionHooks(config=config)
            result = hooks.process_candidates(run_id, candidates)
    """

    def __init__(
        self,
        config: AutoReflectionConfig | None = None,
        behavior_service: Any = None,
        review_queue_service: Any = None,
        telemetry: Any = None,
    ) -> None:
        self._config = config or AutoReflectionConfig()
        self._behavior_service = behavior_service
        self._review_queue = review_queue_service
        self._telemetry = telemetry

    def process_candidates(
        self,
        run_id: str,
        candidates: List[Any],
        *,
        org_id: str | None = None,
    ) -> AutoReflectionResult:
        """Process reflection candidates through the enterprise pipeline.

        1. Run each candidate through the quality gate.
        2. Auto-approve candidates above the threshold.
        3. Route remaining passing candidates to the review queue.
        """
        result = AutoReflectionResult(
            run_id=run_id,
            candidates_received=len(candidates),
        )

        if not self._config.enabled:
            logger.debug("Auto-reflection disabled — skipping %d candidates", len(candidates))
            return result

        approved_count = 0

        for candidate in candidates:
            try:
                gate = run_quality_gate(candidate, self._config)

                if not gate.passed:
                    result.gate_failed += 1
                    logger.debug(
                        "Candidate %s failed quality gate: %s",
                        candidate.slug,
                        "; ".join(gate.reasons),
                    )
                    continue

                result.gate_passed += 1

                # Auto-approve if above threshold and under per-run limit
                if (
                    gate.adjusted_confidence >= self._config.auto_approve_threshold
                    and approved_count < self._config.max_auto_approvals_per_run
                ):
                    self._auto_approve(candidate, run_id, org_id=org_id)
                    result.auto_approved += 1
                    approved_count += 1
                else:
                    self._queue_for_review(candidate, run_id, org_id=org_id)
                    result.queued_for_review += 1

            except Exception as exc:
                msg = f"Error processing candidate {getattr(candidate, 'slug', '?')}: {exc}"
                logger.warning(msg, exc_info=True)
                result.errors.append(msg)

        logger.info(
            "Auto-reflection for run %s: %d received, %d passed gate, "
            "%d auto-approved, %d queued for review, %d errors",
            run_id,
            result.candidates_received,
            result.gate_passed,
            result.auto_approved,
            result.queued_for_review,
            len(result.errors),
        )

        self._emit_telemetry(result, org_id=org_id)
        return result

    # ----- Internal helpers -------------------------------------------------

    def _auto_approve(
        self,
        candidate: Any,
        run_id: str,
        *,
        org_id: str | None = None,
    ) -> None:
        """Persist a candidate as an approved behavior entry."""
        if self._behavior_service is None:
            logger.debug("No behavior service — skipping auto-approve for %s", candidate.slug)
            return

        try:
            self._behavior_service.create_behavior(
                name=candidate.slug,
                display_name=candidate.display_name,
                instruction=candidate.instruction,
                steps=candidate.supporting_steps,
                confidence=candidate.confidence,
                role="student",
                keywords=getattr(candidate, "tags", []),
                metadata={
                    "source": "auto_reflection",
                    "source_run_id": run_id,
                    "org_id": org_id,
                    "auto_approved": True,
                },
            )
            logger.info("Auto-approved behavior %s from run %s", candidate.slug, run_id)
        except Exception:
            logger.warning(
                "Failed to auto-approve behavior %s", candidate.slug, exc_info=True
            )

    def _queue_for_review(
        self,
        candidate: Any,
        run_id: str,
        *,
        org_id: str | None = None,
    ) -> None:
        """Add a candidate to the review queue for Teacher validation."""
        if self._review_queue is None:
            logger.debug("No review queue — skipping review queueing for %s", candidate.slug)
            return

        try:
            self._review_queue.enqueue(
                item_type="behavior_candidate",
                item_id=candidate.slug,
                metadata={
                    "display_name": candidate.display_name,
                    "instruction": candidate.instruction,
                    "confidence": candidate.confidence,
                    "source_run_id": run_id,
                    "org_id": org_id,
                },
            )
            logger.debug("Queued candidate %s for review", candidate.slug)
        except Exception:
            logger.warning(
                "Failed to queue candidate %s for review", candidate.slug, exc_info=True
            )

    def _emit_telemetry(
        self,
        result: AutoReflectionResult,
        *,
        org_id: str | None = None,
    ) -> None:
        """Emit telemetry for the auto-reflection pass."""
        if self._telemetry is None:
            return

        try:
            self._telemetry.emit_event(
                event_type="auto_reflection.completed",
                payload={
                    "run_id": result.run_id,
                    "candidates_received": result.candidates_received,
                    "gate_passed": result.gate_passed,
                    "gate_failed": result.gate_failed,
                    "auto_approved": result.auto_approved,
                    "queued_for_review": result.queued_for_review,
                    "error_count": len(result.errors),
                    "org_id": org_id,
                },
            )
        except Exception:
            logger.debug("Failed to emit auto-reflection telemetry", exc_info=True)


# ---------------------------------------------------------------------------
# Review queue processor
# ---------------------------------------------------------------------------

@dataclass
class ReviewQueueProcessorConfig:
    """Configuration for the review queue processor."""

    auto_approve_threshold: float = _DEFAULT_AUTO_APPROVE_THRESHOLD
    rejection_threshold: float = 0.4
    max_items_per_batch: int = 20
    enabled: bool = True


@dataclass
class ReviewQueueProcessorResult:
    """Summary of a single review queue processing pass."""

    items_inspected: int = 0
    approved: int = 0
    rejected: int = 0
    deferred: int = 0
    errors: List[str] = field(default_factory=list)


class ReviewQueueProcessor:
    """Drains the enterprise review queue on a schedule.

    For each queued candidate:
    - If ``confidence >= auto_approve_threshold``: auto-approve via BehaviorService.
    - If ``confidence < rejection_threshold``: reject and discard.
    - Otherwise: leave for human review.

    Intended to be invoked by the midnighter scheduler or a periodic task::

        processor = ReviewQueueProcessor(
            config=ReviewQueueProcessorConfig(),
            behavior_service=bs,
            review_queue_service=rqs,
        )
        result = processor.process_batch()
    """

    def __init__(
        self,
        config: ReviewQueueProcessorConfig | None = None,
        behavior_service: Any = None,
        review_queue_service: Any = None,
        telemetry: Any = None,
    ) -> None:
        self._config = config or ReviewQueueProcessorConfig()
        self._behavior_service = behavior_service
        self._review_queue = review_queue_service
        self._telemetry = telemetry

    def process_batch(self, *, org_id: str | None = None) -> ReviewQueueProcessorResult:
        """Process up to ``max_items_per_batch`` pending review items.

        Returns a summary of decisions made during this pass.
        """
        result = ReviewQueueProcessorResult()

        if not self._config.enabled:
            logger.debug("ReviewQueueProcessor disabled — skipping batch")
            return result

        if self._review_queue is None:
            logger.debug("No review queue service configured")
            return result

        try:
            items = self._review_queue.peek(
                item_type="behavior_candidate",
                limit=self._config.max_items_per_batch,
            )
        except Exception as exc:
            result.errors.append(f"Failed to fetch review queue items: {exc}")
            logger.warning("ReviewQueueProcessor could not fetch items", exc_info=True)
            return result

        for item in items:
            result.items_inspected += 1
            try:
                self._process_item(item, result, org_id=org_id)
            except Exception as exc:
                msg = f"Error processing review item {item.get('item_id', '?')}: {exc}"
                result.errors.append(msg)
                logger.warning(msg, exc_info=True)

        logger.info(
            "ReviewQueueProcessor pass: %d inspected, %d approved, "
            "%d rejected, %d deferred, %d errors",
            result.items_inspected,
            result.approved,
            result.rejected,
            result.deferred,
            len(result.errors),
        )

        if self._telemetry is not None:
            try:
                self._telemetry.emit_event(
                    event_type="review_queue.processed",
                    payload={
                        "items_inspected": result.items_inspected,
                        "approved": result.approved,
                        "rejected": result.rejected,
                        "deferred": result.deferred,
                        "error_count": len(result.errors),
                        "org_id": org_id,
                    },
                )
            except Exception:
                logger.debug("Failed to emit review queue telemetry", exc_info=True)

        return result

    def _process_item(
        self,
        item: Dict[str, Any],
        result: ReviewQueueProcessorResult,
        *,
        org_id: str | None,
    ) -> None:
        """Apply confidence-threshold decision to a single queue item."""
        meta = item.get("metadata", {})
        confidence = float(meta.get("confidence", 0.0))
        item_id = item.get("item_id", "")

        if confidence >= self._config.auto_approve_threshold:
            if self._behavior_service is not None:
                self._behavior_service.create_behavior(
                    name=item_id,
                    display_name=meta.get("display_name", item_id),
                    instruction=meta.get("instruction", ""),
                    steps=[],
                    confidence=confidence,
                    role="student",
                    metadata={
                        "source": "review_queue_auto_approved",
                        "source_run_id": meta.get("source_run_id"),
                        "org_id": org_id,
                        "auto_approved": True,
                    },
                )
            self._review_queue.remove(item_id)
            result.approved += 1
            logger.info("Review queue: auto-approved %s (confidence %.2f)", item_id, confidence)

        elif confidence < self._config.rejection_threshold:
            self._review_queue.remove(item_id)
            result.rejected += 1
            logger.debug("Review queue: rejected %s (confidence %.2f)", item_id, confidence)

        else:
            result.deferred += 1
            logger.debug("Review queue: deferred %s for human review (confidence %.2f)", item_id, confidence)


# ---------------------------------------------------------------------------
# Lifecycle policy engine
# ---------------------------------------------------------------------------

class BehaviorLifecycleAction(str, Enum):
    PROMOTE = "promote"
    DEPRECATE = "deprecate"
    ARCHIVE = "archive"
    RETAIN = "retain"


@dataclass
class LifecyclePolicy:
    """Rules that govern how a single lifecycle action is triggered."""

    action: BehaviorLifecycleAction
    min_confidence: float = 0.0
    max_confidence: float = 1.0
    min_usage_count: int = 0
    max_days_since_last_used: int | None = None
    min_days_since_created: int = 0
    description: str = ""


@dataclass
class LifecyclePolicyEngineConfig:
    """Bundle of lifecycle policies applied in order."""

    policies: List[LifecyclePolicy] = field(default_factory=lambda: [
        LifecyclePolicy(
            action=BehaviorLifecycleAction.PROMOTE,
            min_confidence=0.85,
            min_usage_count=10,
            description="High-confidence behaviors with strong usage get promoted",
        ),
        LifecyclePolicy(
            action=BehaviorLifecycleAction.DEPRECATE,
            max_confidence=0.5,
            max_days_since_last_used=30,
            min_days_since_created=14,
            description="Low-confidence behaviors unused for 30+ days are deprecated",
        ),
        LifecyclePolicy(
            action=BehaviorLifecycleAction.ARCHIVE,
            max_confidence=0.5,
            max_days_since_last_used=90,
            min_days_since_created=30,
            description="Deprecated behaviors inactive for 90+ days are archived",
        ),
    ])
    dry_run: bool = False
    enabled: bool = True


@dataclass
class LifecyclePolicyResult:
    """Summary of a lifecycle policy engine run."""

    behaviors_evaluated: int = 0
    promoted: int = 0
    deprecated: int = 0
    archived: int = 0
    retained: int = 0
    errors: List[str] = field(default_factory=list)


class LifecyclePolicyEngine:
    """Applies lifecycle policies to behaviors on a schedule.

    Evaluates each active behavior against the configured policy list and
    applies the first matching action (promote / deprecate / archive / retain).

    Usage::

        engine = LifecyclePolicyEngine(
            config=LifecyclePolicyEngineConfig(),
            behavior_service=bs,
        )
        result = engine.run()
    """

    def __init__(
        self,
        config: LifecyclePolicyEngineConfig | None = None,
        behavior_service: Any = None,
        telemetry: Any = None,
    ) -> None:
        self._config = config or LifecyclePolicyEngineConfig()
        self._behavior_service = behavior_service
        self._telemetry = telemetry

    def run(self, *, org_id: str | None = None) -> LifecyclePolicyResult:
        """Evaluate all active behaviors and apply lifecycle policies.

        Returns a summary of actions taken (or that would be taken in dry-run
        mode).
        """
        result = LifecyclePolicyResult()

        if not self._config.enabled:
            logger.debug("LifecyclePolicyEngine disabled — skipping run")
            return result

        if self._behavior_service is None:
            logger.debug("No behavior service configured for lifecycle engine")
            return result

        try:
            behaviors = self._behavior_service.list_behaviors(limit=500)
        except Exception as exc:
            result.errors.append(f"Failed to list behaviors: {exc}")
            logger.warning("LifecyclePolicyEngine could not list behaviors", exc_info=True)
            return result

        now = datetime.now(tz=timezone.utc)

        for behavior in behaviors:
            result.behaviors_evaluated += 1
            try:
                action = self._evaluate(behavior, now)
                self._apply(action, behavior, result, org_id=org_id)
            except Exception as exc:
                msg = f"Error evaluating behavior {getattr(behavior, 'name', '?')}: {exc}"
                result.errors.append(msg)
                logger.warning(msg, exc_info=True)

        logger.info(
            "LifecyclePolicyEngine run: %d evaluated, %d promoted, "
            "%d deprecated, %d archived, %d retained, %d errors%s",
            result.behaviors_evaluated,
            result.promoted,
            result.deprecated,
            result.archived,
            result.retained,
            len(result.errors),
            " [DRY RUN]" if self._config.dry_run else "",
        )

        if self._telemetry is not None:
            try:
                self._telemetry.emit_event(
                    event_type="lifecycle_policy.ran",
                    payload={
                        "behaviors_evaluated": result.behaviors_evaluated,
                        "promoted": result.promoted,
                        "deprecated": result.deprecated,
                        "archived": result.archived,
                        "retained": result.retained,
                        "error_count": len(result.errors),
                        "dry_run": self._config.dry_run,
                        "org_id": org_id,
                    },
                )
            except Exception:
                logger.debug("Failed to emit lifecycle telemetry", exc_info=True)

        return result

    def _evaluate(self, behavior: Any, now: datetime) -> BehaviorLifecycleAction:
        """Return the first matching lifecycle action for *behavior*."""
        confidence = float(getattr(behavior, "confidence", 0.0))
        usage_count = int(getattr(behavior, "usage_count", 0))

        last_used_at = getattr(behavior, "last_used_at", None)
        days_since_used: int | None = None
        if last_used_at is not None:
            if isinstance(last_used_at, str):
                last_used_at = datetime.fromisoformat(last_used_at)
            if last_used_at.tzinfo is None:
                last_used_at = last_used_at.replace(tzinfo=timezone.utc)
            days_since_used = (now - last_used_at).days

        created_at = getattr(behavior, "created_at", None)
        days_since_created = 0
        if created_at is not None:
            if isinstance(created_at, str):
                created_at = datetime.fromisoformat(created_at)
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            days_since_created = (now - created_at).days

        for policy in self._config.policies:
            if not (policy.min_confidence <= confidence <= policy.max_confidence):
                continue
            if usage_count < policy.min_usage_count:
                continue
            if days_since_created < policy.min_days_since_created:
                continue
            if policy.max_days_since_last_used is not None:
                if days_since_used is None or days_since_used < policy.max_days_since_last_used:
                    continue
            return policy.action

        return BehaviorLifecycleAction.RETAIN

    def _apply(
        self,
        action: BehaviorLifecycleAction,
        behavior: Any,
        result: LifecyclePolicyResult,
        *,
        org_id: str | None,
    ) -> None:
        """Persist the lifecycle action unless running in dry-run mode."""
        behavior_name = getattr(behavior, "name", "?")

        if action == BehaviorLifecycleAction.RETAIN:
            result.retained += 1
            return

        logger.info(
            "Lifecycle action %s for behavior %s%s",
            action.value,
            behavior_name,
            " [DRY RUN — not applied]" if self._config.dry_run else "",
        )

        if self._config.dry_run:
            if action == BehaviorLifecycleAction.PROMOTE:
                result.promoted += 1
            elif action == BehaviorLifecycleAction.DEPRECATE:
                result.deprecated += 1
            elif action == BehaviorLifecycleAction.ARCHIVE:
                result.archived += 1
            return

        try:
            if action == BehaviorLifecycleAction.PROMOTE:
                self._behavior_service.update_behavior_status(behavior_name, "promoted")
                result.promoted += 1
            elif action == BehaviorLifecycleAction.DEPRECATE:
                self._behavior_service.update_behavior_status(behavior_name, "deprecated")
                result.deprecated += 1
            elif action == BehaviorLifecycleAction.ARCHIVE:
                self._behavior_service.update_behavior_status(behavior_name, "archived")
                result.archived += 1
        except Exception as exc:
            raise RuntimeError(
                f"Failed to apply {action.value} to {behavior_name}: {exc}"
            ) from exc
