"""Enterprise cloud client.

Imported by ``amprealize.cloud_client`` as:

    from amprealize.enterprise.cloud_client import CloudClient

Provides an authenticated HTTP client to the Amprealize cloud API.
"""

from __future__ import annotations

from typing import Any


class CloudClient:
    """Enterprise cloud deployment client.

    Authenticated HTTP client for Amprealize.io cloud API.
    Handles storage (upload/download), compute (job submission),
    authentication, and deployment lifecycle.
    """

    def __init__(self, *, cloud_url: str = "https://api.amprealize.io") -> None:
        self.cloud_url = cloud_url.rstrip("/")
        self._token: str | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_authenticated(self) -> None:
        """Raise if no auth token is set."""
        if self._token is None:
            raise RuntimeError(
                "Not authenticated. Call client.authenticate() first."
            )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Make an authenticated HTTP request to the cloud API."""
        import httpx

        self._ensure_authenticated()
        url = f"{self.cloud_url}{path}"
        headers = {"Authorization": f"Bearer {self._token}"}

        with httpx.Client(timeout=timeout) as http:
            resp = http.request(
                method,
                url,
                headers=headers,
                json=json_body,
                params=params,
            )
            resp.raise_for_status()
            if resp.status_code == 204:
                return {}
            return resp.json()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def authenticate(
        self,
        *,
        token: str | None = None,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Authenticate with the cloud API.

        Accepts either a bearer token or an API key. When an API key is
        provided, exchanges it for a bearer token via the token endpoint.
        """
        if token:
            self._token = token
            return {"status": "authenticated", "method": "token"}

        if api_key:
            import httpx

            with httpx.Client(timeout=30.0) as http:
                resp = http.post(
                    f"{self.cloud_url}/v1/auth/token",
                    json={"api_key": api_key},
                )
                resp.raise_for_status()
                data = resp.json()
                self._token = data["access_token"]
                return {"status": "authenticated", "method": "api_key"}

        raise ValueError("Provide either token= or api_key= to authenticate.")

    # ------------------------------------------------------------------
    # Storage
    # ------------------------------------------------------------------

    def upload(
        self,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Upload data to cloud storage."""
        import httpx

        self._ensure_authenticated()
        url = f"{self.cloud_url}/v1/storage/upload"
        headers = {"Authorization": f"Bearer {self._token}"}

        with httpx.Client(timeout=60.0) as http:
            resp = http.post(
                url,
                headers=headers,
                data={"key": key, "content_type": content_type, **(metadata or {})},
                files={"file": (key, data, content_type)},
            )
            resp.raise_for_status()
            return resp.json()

    def download(self, key: str) -> bytes:
        """Download data from cloud storage."""
        import httpx

        self._ensure_authenticated()
        url = f"{self.cloud_url}/v1/storage/download"
        headers = {"Authorization": f"Bearer {self._token}"}

        with httpx.Client(timeout=60.0) as http:
            resp = http.get(url, headers=headers, params={"key": key})
            resp.raise_for_status()
            return resp.content

    # ------------------------------------------------------------------
    # Compute
    # ------------------------------------------------------------------

    def submit_job(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        priority: str = "normal",
    ) -> dict[str, Any]:
        """Submit a compute job to the cloud."""
        return self._request(
            "POST",
            "/v1/compute/jobs",
            json_body={
                "job_type": job_type,
                "payload": payload,
                "priority": priority,
            },
        )

    def get_job_status(self, job_id: str) -> dict[str, Any]:
        """Get the status of a submitted compute job."""
        return self._request("GET", f"/v1/compute/jobs/{job_id}")

    # ------------------------------------------------------------------
    # Deployment lifecycle
    # ------------------------------------------------------------------

    def deploy(self, **kwargs: Any) -> dict[str, Any]:
        """Trigger a deployment."""
        return self._request("POST", "/v1/deployments", json_body=kwargs)

    def status(self, deployment_id: str) -> dict[str, Any]:
        """Get deployment status."""
        return self._request("GET", f"/v1/deployments/{deployment_id}")

    def rollback(self, deployment_id: str) -> dict[str, Any]:
        """Rollback a deployment."""
        return self._request("POST", f"/v1/deployments/{deployment_id}/rollback")

    # ------------------------------------------------------------------
    # Generic request (pass-through)
    # ------------------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        params: dict[str, str] | None = None,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        """Make an arbitrary authenticated request to the cloud API."""
        return self._request(
            method, path, json_body=json_body, params=params, timeout=timeout
        )
