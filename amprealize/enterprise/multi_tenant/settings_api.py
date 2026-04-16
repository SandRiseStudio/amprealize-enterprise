"""Enterprise multi-tenant settings API routes.

Imported by OSS as:

    from amprealize.enterprise.multi_tenant.settings_api import create_settings_routes
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Request
from starlette.responses import JSONResponse


def _require_admin(request: Request) -> bool:
    """Check if request user has admin role. Returns True if admin."""
    org_ctx = getattr(request.state, "org_context", None)
    if org_ctx is None:
        return False
    role = getattr(org_ctx, "role", None)
    if role is None:
        return False
    role_val = role.value if hasattr(role, "value") else str(role)
    return role_val == "admin"


def create_settings_routes(
    service: Any | None = None,
    *,
    settings_service: Any | None = None,
    **kwargs: Any,
) -> APIRouter:
    """Create a FastAPI router for org/project settings endpoints.

    Accepts either ``service`` or the legacy ``settings_service`` keyword used
    by the main API wiring.
    """
    service = service or settings_service
    if service is None:
        raise TypeError("create_settings_routes() requires 'service' or 'settings_service'")

    router = APIRouter()

    # ---- Org settings ----

    @router.get("/v1/orgs/{org_id}/settings")
    async def get_org_settings(org_id: str, request: Request):
        try:
            settings = await service.get_org_settings(org_id)
            return JSONResponse(content=asdict(settings))
        except (ValueError, KeyError) as exc:
            return JSONResponse(status_code=404, content={"detail": str(exc)})

    @router.patch("/v1/orgs/{org_id}/settings")
    async def update_org_settings(org_id: str, request: Request):
        if not _require_admin(request):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        body = await request.json()
        settings = await service.update_org_settings(org_id, **body)
        return JSONResponse(content=asdict(settings))

    # ---- Branding ----

    @router.get("/v1/orgs/{org_id}/settings/branding")
    async def get_branding(org_id: str, request: Request):
        settings = await service.get_org_settings(org_id)
        return JSONResponse(content=asdict(settings.branding))

    @router.patch("/v1/orgs/{org_id}/settings/branding")
    async def update_branding(org_id: str, request: Request):
        if not _require_admin(request):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        body = await request.json()
        result = await service.update_org_branding(org_id, **body)
        return JSONResponse(content=asdict(result))

    # ---- Notifications ----

    @router.get("/v1/orgs/{org_id}/settings/notifications")
    async def get_notifications(org_id: str, request: Request):
        settings = await service.get_org_settings(org_id)
        return JSONResponse(content=asdict(settings.notifications))

    @router.patch("/v1/orgs/{org_id}/settings/notifications")
    async def update_notifications(org_id: str, request: Request):
        if not _require_admin(request):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        body = await request.json()
        result = await service.update_org_notifications(org_id, **body)
        return JSONResponse(content=asdict(result))

    # ---- Security ----

    @router.get("/v1/orgs/{org_id}/settings/security")
    async def get_security(org_id: str, request: Request):
        settings = await service.get_org_settings(org_id)
        return JSONResponse(content=asdict(settings.security))

    @router.patch("/v1/orgs/{org_id}/settings/security")
    async def update_security(org_id: str, request: Request):
        if not _require_admin(request):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        body = await request.json()
        result = await service.update_org_security(org_id, **body)
        return JSONResponse(content=asdict(result))

    # ---- Integrations ----

    @router.get("/v1/orgs/{org_id}/settings/integrations")
    async def get_integrations(org_id: str, request: Request):
        settings = await service.get_org_settings(org_id)
        return JSONResponse(content=asdict(settings.integrations))

    @router.patch("/v1/orgs/{org_id}/settings/integrations")
    async def update_integrations(org_id: str, request: Request):
        if not _require_admin(request):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        body = await request.json()
        result = await service.update_org_integrations(org_id, **body)
        return JSONResponse(content=asdict(result))

    # ---- Workflow ----

    @router.get("/v1/orgs/{org_id}/settings/workflow")
    async def get_workflow(org_id: str, request: Request):
        settings = await service.get_org_settings(org_id)
        return JSONResponse(content=asdict(settings.workflow))

    @router.patch("/v1/orgs/{org_id}/settings/workflow")
    async def update_workflow(org_id: str, request: Request):
        if not _require_admin(request):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        body = await request.json()
        result = await service.update_org_workflow(org_id, **body)
        return JSONResponse(content=asdict(result))

    # ---- Webhooks ----

    @router.post("/v1/orgs/{org_id}/settings/webhooks", status_code=201)
    async def add_webhook(org_id: str, request: Request):
        if not _require_admin(request):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        body = await request.json()
        result = await service.add_org_webhook(org_id, **body)
        return JSONResponse(content=result, status_code=201)

    @router.delete("/v1/orgs/{org_id}/settings/webhooks/{webhook_id}")
    async def remove_webhook(org_id: str, webhook_id: str, request: Request):
        if not _require_admin(request):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        removed = await service.remove_org_webhook(org_id, webhook_id)
        if not removed:
            return JSONResponse(status_code=404, content={"detail": "Webhook not found"})
        return JSONResponse(status_code=204, content=None)

    # ---- Feature flags ----

    @router.put("/v1/orgs/{org_id}/settings/features/{flag_name}")
    async def set_org_feature_flag(org_id: str, flag_name: str, request: Request):
        if not _require_admin(request):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        body = await request.json()
        result = await service.set_org_feature_flag(org_id, flag_name, body.get("enabled", False))
        return JSONResponse(content=result)

    @router.put("/v1/projects/{project_id}/settings/features/{flag_name}")
    async def set_project_feature_flag(project_id: str, flag_name: str, request: Request):
        if not _require_admin(request):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        body = await request.json()
        result = await service.set_project_feature_flag(project_id, flag_name, body.get("enabled", False))
        return JSONResponse(content=result)

    # ---- Project settings ----

    @router.get("/v1/projects/{project_id}/settings")
    async def get_project_settings(project_id: str, request: Request):
        settings = await service.get_project_settings(project_id)
        return JSONResponse(content=asdict(settings))

    @router.patch("/v1/projects/{project_id}/settings")
    async def update_project_settings(project_id: str, request: Request):
        if not _require_admin(request):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        body = await request.json()
        settings = await service.update_project_settings(project_id, **body)
        return JSONResponse(content=asdict(settings))

    @router.get("/v1/projects/{project_id}/settings/workflow")
    async def get_project_workflow(project_id: str, request: Request):
        settings = await service.get_project_settings(project_id)
        return JSONResponse(content=asdict(settings.workflow))

    @router.patch("/v1/projects/{project_id}/settings/workflow")
    async def update_project_workflow(project_id: str, request: Request):
        if not _require_admin(request):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        body = await request.json()
        result = await service.update_project_workflow(project_id, **body)
        return JSONResponse(content=asdict(result))

    @router.put("/v1/projects/{project_id}/settings/repository")
    async def set_project_repository(project_id: str, request: Request):
        if not _require_admin(request):
            return JSONResponse(status_code=403, content={"detail": "Forbidden"})
        body = await request.json()
        settings = await service.set_project_repository(project_id, **body)
        return JSONResponse(content=asdict(settings))

    return router
