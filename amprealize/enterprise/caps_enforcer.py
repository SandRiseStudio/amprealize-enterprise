"""Enterprise caps enforcer.

Imported by ``amprealize.caps_enforcer`` as:

    from amprealize.enterprise.caps_enforcer import CapsEnforcer

The OSS factory instantiates this class when ``amprealize.enterprise`` is
installed.  It must be duck-type compatible with the OSS
``amprealize.caps_enforcer.CapsEnforcer`` interface:

    - ``check(resource, *, current_count=0) -> bool``
    - ``enforce(resource, *, current_count=0) -> None``
    - ``get_limit(resource) -> int``
    - ``get_usage_summary() -> dict``

GUIDEAI-770: Implement real enterprise caps enforcer.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from amprealize.caps_enforcer import CapsExceededError  # noqa: F401 — re-export
from amprealize.caps_enforcer import EditionCapsEnforcer as _EditionCapsEnforcer

if TYPE_CHECKING:
    from amprealize.edition import EditionCapabilities

logger = logging.getLogger(__name__)


# Same mapping the OSS module uses — kept in sync.
_RESOURCE_TO_CAP_FIELD: dict[str, str] = {
    "projects": "max_projects",
    "boards": "max_boards_per_project",
    "work_items": "max_work_items",
    "agents": "max_agents",
    "behaviors": "max_behaviors",
    "api_calls": "monthly_api_calls",
    "storage": "max_storage_bytes",
    "members": "max_members",
}


class CapsEnforcer(_EditionCapsEnforcer):
    """Enterprise-grade caps enforcer backed by edition capabilities.

    Resolves the active edition's ``EditionCapabilities`` and checks
    resource counts against defined limits.  Enterprise Premium is
    uncapped (``-1``), so checks always pass for that tier.

    Optionally reads real-time usage from a DSN when
    ``AMPREALIZE_CAPS_DSN`` is set (future iteration).
    """

    def __init__(self, caps: EditionCapabilities | None = None) -> None:
        self._caps = caps

    @property
    def caps(self) -> EditionCapabilities:
        if self._caps is None:
            from amprealize.edition import get_caps

            self._caps = get_caps()
        return self._caps

    def check(self, resource: str, *, current_count: int = 0) -> bool:
        """Return ``True`` if *current_count* is below the cap (or uncapped)."""
        limit = self.get_limit(resource)
        if limit == -1:
            return True
        return current_count < limit

    def enforce(self, resource: str, *, current_count: int = 0) -> None:
        """Raise ``CapsExceededError`` if over cap."""
        if not self.check(resource, current_count=current_count):
            raise CapsExceededError(
                resource, self.get_limit(resource), current_count
            )

    def get_limit(self, resource: str) -> int:
        """Return the cap for *resource*, or ``-1`` if uncapped."""
        field_name = _RESOURCE_TO_CAP_FIELD.get(resource)
        if field_name is None:
            return -1
        return getattr(self.caps, field_name, -1)

    def get_remaining(self, resource: str, *, current_count: int = 0) -> int | None:
        """Return remaining quota for *resource*, or ``None`` if unlimited."""
        limit = self.get_limit(resource)
        if limit == -1:
            return None
        remaining = limit - current_count
        return max(remaining, 0)

    def get_usage_summary(self) -> dict[str, dict[str, int]]:
        """Return cap limits for all capped resources."""
        summary: dict[str, dict[str, int]] = {}
        for resource, field_name in _RESOURCE_TO_CAP_FIELD.items():
            limit = getattr(self.caps, field_name, -1)
            if limit != -1:
                summary[resource] = {"limit": limit}
        return summary
