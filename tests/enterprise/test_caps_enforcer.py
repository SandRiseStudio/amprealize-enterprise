"""Tests for enterprise caps enforcer (GUIDEAI-770)."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from amprealize.enterprise.caps_enforcer import (
    CapsEnforcer,
    CapsExceededError,
    _RESOURCE_TO_CAP_FIELD,
)


# ---------------------------------------------------------------------------
# Fake EditionCapabilities for testing (avoids importing OSS in unit tests)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _FakeCaps:
    max_projects: int = 10
    max_boards_per_project: int = 5
    max_work_items: int = 1000
    max_agents: int = 3
    max_behaviors: int = 100
    monthly_api_calls: int = 50_000
    max_storage_bytes: int = 1_073_741_824  # 1 GiB
    max_members: int = 25


@dataclass(frozen=True)
class _UnlimitedCaps:
    max_projects: int = -1
    max_boards_per_project: int = -1
    max_work_items: int = -1
    max_agents: int = -1
    max_behaviors: int = -1
    monthly_api_calls: int = -1
    max_storage_bytes: int = -1
    max_members: int = -1


class TestCapsEnforcerWithCaps:
    """Test enterprise CapsEnforcer with capped edition (Starter)."""

    def _enforcer(self) -> CapsEnforcer:
        return CapsEnforcer(caps=_FakeCaps())

    def test_check_below_limit(self):
        enforcer = self._enforcer()
        assert enforcer.check("projects", current_count=5) is True

    def test_check_at_limit(self):
        enforcer = self._enforcer()
        assert enforcer.check("projects", current_count=10) is False

    def test_check_above_limit(self):
        enforcer = self._enforcer()
        assert enforcer.check("projects", current_count=15) is False

    def test_check_unknown_resource(self):
        enforcer = self._enforcer()
        assert enforcer.check("unknown_resource", current_count=999) is True

    def test_enforce_within_cap(self):
        enforcer = self._enforcer()
        enforcer.enforce("projects", current_count=5)  # should not raise

    def test_enforce_over_cap_raises(self):
        enforcer = self._enforcer()
        with pytest.raises(CapsExceededError) as exc_info:
            enforcer.enforce("projects", current_count=10)
        assert exc_info.value.resource == "projects"
        assert exc_info.value.limit == 10
        assert exc_info.value.current == 10

    def test_get_limit_known_resource(self):
        enforcer = self._enforcer()
        assert enforcer.get_limit("projects") == 10
        assert enforcer.get_limit("agents") == 3

    def test_get_limit_unknown_resource(self):
        enforcer = self._enforcer()
        assert enforcer.get_limit("nonexistent") == -1

    def test_get_remaining(self):
        enforcer = self._enforcer()
        assert enforcer.get_remaining("projects", current_count=3) == 7

    def test_get_remaining_at_limit(self):
        enforcer = self._enforcer()
        assert enforcer.get_remaining("projects", current_count=10) == 0

    def test_get_remaining_over_limit(self):
        enforcer = self._enforcer()
        assert enforcer.get_remaining("projects", current_count=15) == 0

    def test_get_remaining_unlimited(self):
        enforcer = CapsEnforcer(caps=_UnlimitedCaps())
        assert enforcer.get_remaining("projects") is None

    def test_get_usage_summary(self):
        enforcer = self._enforcer()
        summary = enforcer.get_usage_summary()
        assert "projects" in summary
        assert summary["projects"]["limit"] == 10
        assert "agents" in summary
        assert summary["agents"]["limit"] == 3


class TestCapsEnforcerUnlimited:
    """Test enterprise CapsEnforcer with unlimited caps (Premium)."""

    def _enforcer(self) -> CapsEnforcer:
        return CapsEnforcer(caps=_UnlimitedCaps())

    def test_check_always_passes(self):
        enforcer = self._enforcer()
        assert enforcer.check("projects", current_count=999_999) is True

    def test_enforce_never_raises(self):
        enforcer = self._enforcer()
        enforcer.enforce("projects", current_count=999_999)  # should not raise

    def test_get_usage_summary_empty(self):
        enforcer = self._enforcer()
        summary = enforcer.get_usage_summary()
        assert summary == {}


class TestResourceMapping:
    """Verify resource → cap field mapping is consistent with OSS."""

    def test_has_expected_resources(self):
        expected = {
            "projects", "boards", "work_items", "agents",
            "behaviors", "api_calls", "storage", "members",
        }
        assert set(_RESOURCE_TO_CAP_FIELD.keys()) == expected
