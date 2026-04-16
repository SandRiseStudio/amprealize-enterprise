"""Tests for enterprise auto-reflection hooks (GUIDEAI-772)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List
from unittest.mock import MagicMock

import pytest

from amprealize.enterprise.auto_reflection import (
    AutoReflectionConfig,
    AutoReflectionHooks,
    AutoReflectionResult,
    QualityGateResult,
    run_quality_gate,
)


# ---------------------------------------------------------------------------
# Helpers — fake reflection candidates
# ---------------------------------------------------------------------------

@dataclass
class _FakeScores:
    clarity: float = 0.9
    generality: float = 0.8
    reusability: float = 0.85
    correctness: float = 0.9


@dataclass
class _FakeCandidate:
    slug: str = "behavior_test_candidate"
    display_name: str = "Test Candidate"
    instruction: str = "Follow established testing patterns for unit tests."
    supporting_steps: list = field(default_factory=lambda: ["Step 1", "Step 2", "Step 3"])
    quality_scores: _FakeScores = field(default_factory=_FakeScores)
    confidence: float = 0.9
    tags: list = field(default_factory=lambda: ["testing", "patterns"])


def _make_candidate(**overrides) -> _FakeCandidate:
    return _FakeCandidate(**overrides)


# ---------------------------------------------------------------------------
# Quality gate tests
# ---------------------------------------------------------------------------

class TestQualityGate:
    """Test run_quality_gate."""

    def test_passes_good_candidate(self):
        result = run_quality_gate(_make_candidate())
        assert result.passed is True
        assert result.reasons == []
        assert result.adjusted_confidence > 0

    def test_fails_low_quality_dimension(self):
        scores = _FakeScores(clarity=0.3, generality=0.8, reusability=0.8, correctness=0.8)
        result = run_quality_gate(_make_candidate(quality_scores=scores))
        assert result.passed is False
        assert any("quality dimension" in r.lower() for r in result.reasons)

    def test_fails_too_few_steps(self):
        config = AutoReflectionConfig(min_supporting_steps=5)
        result = run_quality_gate(_make_candidate(supporting_steps=["Step 1"]), config)
        assert result.passed is False
        assert any("supporting steps" in r.lower() for r in result.reasons)

    def test_fails_short_instruction(self):
        result = run_quality_gate(_make_candidate(instruction="short"))
        assert result.passed is False
        assert any("instruction too short" in r.lower() for r in result.reasons)

    def test_fails_empty_display_name(self):
        result = run_quality_gate(_make_candidate(display_name=""))
        assert result.passed is False
        assert any("display name" in r.lower() for r in result.reasons)

    def test_adjusted_confidence_penalized_on_failure(self):
        scores = _FakeScores(clarity=0.3)
        candidate = _make_candidate(quality_scores=scores, confidence=0.9)
        result = run_quality_gate(candidate)
        assert result.adjusted_confidence < candidate.confidence


# ---------------------------------------------------------------------------
# AutoReflectionHooks tests
# ---------------------------------------------------------------------------

class TestAutoReflectionHooks:
    """Test AutoReflectionHooks.process_candidates."""

    def test_returns_result_with_counts(self):
        hooks = AutoReflectionHooks()
        candidates = [_make_candidate(), _make_candidate(slug="behavior_second")]
        result = hooks.process_candidates("run-001", candidates)
        assert isinstance(result, AutoReflectionResult)
        assert result.run_id == "run-001"
        assert result.candidates_received == 2

    def test_disabled_config_skips_processing(self):
        config = AutoReflectionConfig(enabled=False)
        hooks = AutoReflectionHooks(config=config)
        result = hooks.process_candidates("run-001", [_make_candidate()])
        assert result.candidates_received == 1
        assert result.gate_passed == 0
        assert result.auto_approved == 0

    def test_auto_approves_high_confidence(self):
        behavior_svc = MagicMock()
        config = AutoReflectionConfig(auto_approve_threshold=0.8)
        hooks = AutoReflectionHooks(config=config, behavior_service=behavior_svc)
        result = hooks.process_candidates("run-001", [_make_candidate(confidence=0.95)])
        assert result.auto_approved == 1
        behavior_svc.create_behavior.assert_called_once()

    def test_queues_below_threshold_for_review(self):
        review_queue = MagicMock()
        config = AutoReflectionConfig(auto_approve_threshold=0.95)
        hooks = AutoReflectionHooks(
            config=config,
            review_queue_service=review_queue,
        )
        # Confidence 0.9 is below 0.95 threshold → queued
        result = hooks.process_candidates("run-001", [_make_candidate(confidence=0.9)])
        assert result.queued_for_review == 1
        review_queue.enqueue.assert_called_once()

    def test_respects_max_auto_approvals_per_run(self):
        behavior_svc = MagicMock()
        review_queue = MagicMock()
        config = AutoReflectionConfig(
            auto_approve_threshold=0.8,
            max_auto_approvals_per_run=1,
        )
        hooks = AutoReflectionHooks(
            config=config,
            behavior_service=behavior_svc,
            review_queue_service=review_queue,
        )
        candidates = [
            _make_candidate(slug="behavior_a", confidence=0.95),
            _make_candidate(slug="behavior_b", confidence=0.95),
        ]
        result = hooks.process_candidates("run-001", candidates)
        assert result.auto_approved == 1
        assert result.queued_for_review == 1

    def test_gate_failure_skips_candidate(self):
        hooks = AutoReflectionHooks()
        bad = _make_candidate(instruction="x")  # too short
        result = hooks.process_candidates("run-001", [bad])
        assert result.gate_failed == 1
        assert result.auto_approved == 0
        assert result.queued_for_review == 0

    def test_emits_telemetry(self):
        telemetry = MagicMock()
        hooks = AutoReflectionHooks(telemetry=telemetry)
        hooks.process_candidates("run-001", [_make_candidate()])
        telemetry.emit_event.assert_called_once()
        call_kwargs = telemetry.emit_event.call_args
        assert call_kwargs[1]["event_type"] == "auto_reflection.completed"

    def test_graceful_on_service_errors(self):
        behavior_svc = MagicMock()
        behavior_svc.create_behavior.side_effect = RuntimeError("DB down")
        config = AutoReflectionConfig(auto_approve_threshold=0.8)
        hooks = AutoReflectionHooks(config=config, behavior_service=behavior_svc)
        result = hooks.process_candidates("run-001", [_make_candidate()])
        # Should not raise — errors are captured
        assert len(result.errors) == 0  # error is logged but auto_approved fails silently
        # The behavior_svc was called but failed — auto_approved still counted
        # (the service call error is logged, not propagated as errors list)
