"""
Optional live checks against the deployed SaaS API (GUIDEAI-5 / M2).

Not collected by default; enable with AMPREALIZE_REMOTE_DEVICE_FLOW_SMOKE=1
(see `.github/workflows/ci.yml` job `device-flow-api-smoke`).

Exercises `/health` and `POST /api/v1/auth/device/authorize` (CLI device flow start).
The `/api/v1/auth/device/login` alias is covered by `tests/unit/test_device_login_auth_skip.py`
and matches `/authorize` once the API revision is deployed.
"""

from __future__ import annotations

import os

import httpx
import pytest

_DEFAULT_BASE = "https://api.amprealize.ai"


def _base_url() -> str:
    raw = (
        os.getenv("AMPREALIZE_DEVICE_FLOW_SMOKE_URL")
        or os.getenv("AMPREALIZE_GATEWAY_URL")
        or _DEFAULT_BASE
    )
    return raw.rstrip("/")


@pytest.mark.integration
def test_remote_api_health() -> None:
    with httpx.Client(timeout=20.0) as client:
        r = client.get(f"{_base_url()}/health")
    r.raise_for_status()
    data = r.json()
    assert data.get("status") == "healthy"


@pytest.mark.integration
def test_remote_device_authorize_start() -> None:
    """CLI `amprealize auth login` uses this JSON path; must work without a Bearer token."""
    with httpx.Client(timeout=20.0) as client:
        r = client.post(
            f"{_base_url()}/api/v1/auth/device/authorize",
            json={"client_id": "amprealize-mcp-client", "scopes": ["projects.read"]},
        )
    r.raise_for_status()
    body = r.json()
    for key in ("device_code", "user_code", "verification_uri", "expires_in", "interval", "status"):
        assert key in body, body
