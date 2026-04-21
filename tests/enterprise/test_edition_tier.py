"""Tests for enterprise edition tier resolution (GUIDEAI-771)."""

from __future__ import annotations


from amprealize.enterprise.edition_tier import (
    _VALID_TIERS,
    _decode_license_tier,
    resolve_tier,
)


class TestResolveTier:
    """Test resolve_tier resolution order."""

    def test_default_is_starter(self, monkeypatch):
        monkeypatch.delenv("AMPREALIZE_TIER", raising=False)
        monkeypatch.delenv("AMPREALIZE_BILLING_DSN", raising=False)
        monkeypatch.delenv("AMPREALIZE_LICENSE_KEY", raising=False)
        assert resolve_tier() == "starter"

    def test_env_var_starter(self, monkeypatch):
        monkeypatch.setenv("AMPREALIZE_TIER", "starter")
        assert resolve_tier() == "starter"

    def test_env_var_premium(self, monkeypatch):
        monkeypatch.setenv("AMPREALIZE_TIER", "premium")
        assert resolve_tier() == "premium"

    def test_env_var_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("AMPREALIZE_TIER", "PREMIUM")
        assert resolve_tier() == "premium"

    def test_env_var_with_whitespace(self, monkeypatch):
        monkeypatch.setenv("AMPREALIZE_TIER", "  premium  ")
        assert resolve_tier() == "premium"

    def test_invalid_env_var_falls_through(self, monkeypatch):
        monkeypatch.setenv("AMPREALIZE_TIER", "invalid")
        monkeypatch.delenv("AMPREALIZE_BILLING_DSN", raising=False)
        monkeypatch.delenv("AMPREALIZE_LICENSE_KEY", raising=False)
        assert resolve_tier() == "starter"  # default

    def test_env_var_takes_priority_over_license(self, monkeypatch):
        monkeypatch.setenv("AMPREALIZE_TIER", "premium")
        monkeypatch.setenv("AMPREALIZE_LICENSE_KEY", "starter-abc123")
        assert resolve_tier() == "premium"


class TestDecodeLicenseTier:
    """Test the license key decoder."""

    def test_starter_key(self):
        assert _decode_license_tier("starter-abc123") == "starter"

    def test_premium_key(self):
        assert _decode_license_tier("premium-xyz789") == "premium"

    def test_case_insensitive(self):
        assert _decode_license_tier("PREMIUM-xyz") == "premium"

    def test_invalid_tier_prefix(self):
        assert _decode_license_tier("enterprise-xyz") is None

    def test_empty_key(self):
        assert _decode_license_tier("") is None

    def test_no_separator(self):
        assert _decode_license_tier("starterabc") is None


class TestLicenseKeyResolution:
    """Test resolve_tier with license key (no env var or billing)."""

    def test_license_key_starter(self, monkeypatch):
        monkeypatch.delenv("AMPREALIZE_TIER", raising=False)
        monkeypatch.delenv("AMPREALIZE_BILLING_DSN", raising=False)
        monkeypatch.setenv("AMPREALIZE_LICENSE_KEY", "starter-abc123")
        assert resolve_tier() == "starter"

    def test_license_key_premium(self, monkeypatch):
        monkeypatch.delenv("AMPREALIZE_TIER", raising=False)
        monkeypatch.delenv("AMPREALIZE_BILLING_DSN", raising=False)
        monkeypatch.setenv("AMPREALIZE_LICENSE_KEY", "premium-xyz789")
        assert resolve_tier() == "premium"

    def test_invalid_license_falls_to_default(self, monkeypatch):
        monkeypatch.delenv("AMPREALIZE_TIER", raising=False)
        monkeypatch.delenv("AMPREALIZE_BILLING_DSN", raising=False)
        monkeypatch.setenv("AMPREALIZE_LICENSE_KEY", "garbage-key")
        assert resolve_tier() == "starter"


class TestValidTiers:
    """Ensure the constant is correct."""

    def test_valid_tiers(self):
        assert _VALID_TIERS == ("starter", "premium")
