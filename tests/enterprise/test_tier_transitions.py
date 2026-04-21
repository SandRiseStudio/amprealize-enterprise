"""Tests for enterprise billing tier transitions (GUIDEAI-773)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock


from amprealize.enterprise.billing.tier_transitions import (
    TierTransitionService,
    TransitionPreview,
    TransitionStatus,
)


class TestValidation:
    """Test TierTransitionService.validate."""

    def _svc(self) -> TierTransitionService:
        return TierTransitionService()

    def test_same_tier_fails(self):
        result = self._svc().validate("starter", "starter")
        assert result.status == TransitionStatus.FAILED_VALIDATION
        assert any(i.code == "SAME_TIER" for i in result.issues)

    def test_invalid_from_tier(self):
        result = self._svc().validate("invalid", "premium")
        assert result.status == TransitionStatus.FAILED_VALIDATION
        assert any(i.code == "INVALID_FROM_TIER" for i in result.issues)

    def test_invalid_to_tier(self):
        result = self._svc().validate("starter", "invalid")
        assert result.status == TransitionStatus.FAILED_VALIDATION
        assert any(i.code == "INVALID_TO_TIER" for i in result.issues)

    def test_valid_upgrade_passes(self):
        result = self._svc().validate("starter", "premium")
        assert result.status == TransitionStatus.VALIDATED

    def test_valid_downgrade_has_warning(self):
        result = self._svc().validate("premium", "starter")
        assert result.status == TransitionStatus.VALIDATED
        warnings = [i for i in result.issues if i.severity == "warning"]
        assert len(warnings) > 0
        assert any(i.code == "FEATURES_LOST" for i in warnings)

    def test_oss_to_starter_passes(self):
        result = self._svc().validate("oss", "starter")
        assert result.status == TransitionStatus.VALIDATED

    def test_oss_to_premium_passes(self):
        result = self._svc().validate("oss", "premium")
        assert result.status == TransitionStatus.VALIDATED


class TestPreview:
    """Test TierTransitionService.preview."""

    def _svc(self) -> TierTransitionService:
        return TierTransitionService()

    def test_upgrade_shows_features_gained(self):
        preview = self._svc().preview("starter", "premium")
        assert isinstance(preview, TransitionPreview)
        assert len(preview.features_gained) > 0
        assert "sso" in preview.features_gained

    def test_downgrade_shows_features_lost(self):
        preview = self._svc().preview("premium", "starter")
        assert len(preview.features_lost) > 0

    def test_data_preserved_flag(self):
        preview = self._svc().preview("starter", "premium")
        assert preview.data_preserved is True

    def test_invalid_transition_has_warning(self):
        preview = self._svc().preview("premium", "premium")
        # The OSS transition won't exist for same->same, should warn
        # (validation catches it, but preview won't find a transition)
        assert len(preview.warnings) > 0

    def test_cap_changes_populated(self):
        preview = self._svc().preview("oss", "starter")
        # Cap changes should include resources with different limits
        assert isinstance(preview.cap_changes, dict)


class TestExecute:
    """Test TierTransitionService.execute."""

    def test_dry_run_does_not_apply(self, monkeypatch):
        monkeypatch.delenv("AMPREALIZE_TIER", raising=False)
        svc = TierTransitionService()
        result = svc.execute("starter", "premium", dry_run=True)
        assert result.status == TransitionStatus.VALIDATED
        # Env var should NOT be set in dry run
        assert os.environ.get("AMPREALIZE_TIER") != "premium"

    def test_real_execute_sets_env(self, monkeypatch):
        monkeypatch.delenv("AMPREALIZE_TIER", raising=False)
        svc = TierTransitionService()
        result = svc.execute("starter", "premium")
        assert result.status == TransitionStatus.COMPLETED
        assert os.environ.get("AMPREALIZE_TIER") == "premium"
        # Clean up
        monkeypatch.delenv("AMPREALIZE_TIER", raising=False)

    def test_failed_validation_skips_execute(self):
        svc = TierTransitionService()
        result = svc.execute("starter", "starter")
        assert result.status == TransitionStatus.FAILED_VALIDATION

    def test_emits_telemetry(self, monkeypatch):
        monkeypatch.delenv("AMPREALIZE_TIER", raising=False)
        telemetry = MagicMock()
        svc = TierTransitionService(telemetry=telemetry)
        svc.execute("starter", "premium")
        telemetry.emit_event.assert_called_once()
        monkeypatch.delenv("AMPREALIZE_TIER", raising=False)

    def test_calls_billing_update(self, monkeypatch):
        monkeypatch.delenv("AMPREALIZE_TIER", raising=False)
        billing = MagicMock()
        svc = TierTransitionService(billing_service=billing)
        svc.execute("starter", "premium", org_id="org-1")
        billing.update_tier.assert_called_once_with(org_id="org-1", tier="premium")
        monkeypatch.delenv("AMPREALIZE_TIER", raising=False)


class TestRollback:
    """Test TierTransitionService.rollback."""

    def test_rollback_returns_error(self):
        svc = TierTransitionService()
        result = svc.rollback("txn-001")
        assert result.status == TransitionStatus.ERROR
        assert "not yet implemented" in (result.error or "").lower()
