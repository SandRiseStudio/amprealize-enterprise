"""Ensure /api/v1/auth/device/login is public when auth middleware is on (M2 / GUIDEAI-998)."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from amprealize import api as api_module

pytestmark = pytest.mark.unit


def test_device_login_skips_auth_when_middleware_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AMPREALIZE_AUTH_ENABLED", "true")
    monkeypatch.setenv("AMPREALIZE_JWT_SECRET", "unit-test-jwt-secret-unit-test-jwt-secret-32")
    monkeypatch.setenv("AMPREALIZE_EXECUTION_ENABLED", "false")

    app = api_module.create_app(enable_auth_middleware=True)
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/device/login",
        json={
            "client_id": "amprealize-mcp-client",
            "scopes": ["projects.read"],
            "poll_interval": 5,
            "timeout": 300,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert "device_code" in body
    assert "user_code" in body
    assert "verification_uri" in body
