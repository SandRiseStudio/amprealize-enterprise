"""Tests for centralized invite-only policy."""

from __future__ import annotations

import os

import pytest

from amprealize.auth.invite_policy import (
    NEW_USER_FORBIDDEN_MESSAGE,
    InviteOnlyRegistrationError,
    is_invite_only,
)


@pytest.fixture(autouse=True)
def _clear_invite_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AMPREALIZE_INVITE_ONLY", raising=False)


def test_is_invite_only_false_by_default() -> None:
    assert is_invite_only() is False


@pytest.mark.parametrize("raw", ("1", "true", "yes", "on", "TRUE", " Yes "))
def test_is_invite_only_true(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    monkeypatch.setenv("AMPREALIZE_INVITE_ONLY", raw)
    assert is_invite_only() is True


def test_invite_only_registration_error_default_message() -> None:
    err = InviteOnlyRegistrationError()
    assert str(err) == NEW_USER_FORBIDDEN_MESSAGE
