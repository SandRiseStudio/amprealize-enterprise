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

GUIDEAI-772: Implement enterprise auto-reflection hooks.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

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
