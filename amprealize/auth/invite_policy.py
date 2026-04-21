"""Central invite-only policy for SaaS (AMPREALIZE_INVITE_ONLY).

New human identities must not be created when invite-only is enabled, except
when the principal already exists in ``auth.users`` (returning users).

Device-flow approval does **not** create ``auth.users`` rows; it binds an
already-logged-in approver to a pending CLI session. First-time sign-up is
primarily OAuth (web) and internal register — both gated in ``api.py`` and
defense-in-depth in :meth:`UserAuthService.create_internal_user`.
"""

from __future__ import annotations

import os

_INVITE_TRUE = frozenset({"1", "true", "yes", "on"})

NEW_USER_FORBIDDEN_MESSAGE = (
    "Amprealize is currently invite-only. Request access at https://amprealize.ai."
)


class InviteOnlyRegistrationError(Exception):
    """Raised when invite-only mode blocks creation of a new principal."""

    def __init__(self, message: str = NEW_USER_FORBIDDEN_MESSAGE) -> None:
        super().__init__(message)


def is_invite_only() -> bool:
    """Return True when new self-serve sign-ups must be rejected."""
    raw = os.getenv("AMPREALIZE_INVITE_ONLY", "").strip().lower()
    return raw in _INVITE_TRUE
