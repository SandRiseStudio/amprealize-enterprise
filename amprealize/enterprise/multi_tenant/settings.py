"""Enterprise multi-tenant settings service and models.

Imported by OSS as:

    from amprealize.enterprise.multi_tenant.settings import (
        SettingsService,
        OrgSettings, ProjectSettings,
        BrandingSettings, NotificationSettings, SecuritySettings,
        IntegrationSettings, WorkflowSettings, AgentSettings,
        # Plus update request models
    )
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


# ---------------------------------------------------------------------------
# Settings data models
# ---------------------------------------------------------------------------

@dataclass
class BrandingSettings:
    logo_url: str = ""
    primary_color: str = ""
    display_name: str = ""
    tagline: str = ""


@dataclass
class NotificationSettings:
    email_enabled: bool = True
    slack_enabled: bool = False
    slack_webhook_url: str = ""


@dataclass
class SecuritySettings:
    require_mfa: bool = False
    sso_enabled: bool = False
    session_timeout_hours: int = 8
    allowed_domains: list[str] = field(default_factory=list)


@dataclass
class IntegrationSettings:
    github_enabled: bool = False
    github_org: str = ""
    gitlab_enabled: bool = False
    gitlab_url: str = ""


@dataclass
class WorkflowSettings:
    default_behaviors: list[str] = field(default_factory=list)
    max_concurrent_runs: int = 10
    default_token_budget: int = 100000


@dataclass
class AgentSettings:
    default_model: str = ""


@dataclass
class OrgSettings:
    """Aggregate of all org-level settings."""
    org_id: str = ""
    branding: BrandingSettings = field(default_factory=BrandingSettings)
    notifications: NotificationSettings = field(default_factory=NotificationSettings)
    security: SecuritySettings = field(default_factory=SecuritySettings)
    integrations: IntegrationSettings = field(default_factory=IntegrationSettings)
    workflow: WorkflowSettings = field(default_factory=WorkflowSettings)
    agents: AgentSettings = field(default_factory=AgentSettings)
    default_project_visibility: str = "private"
    default_member_role: str = "member"
    features: Dict[str, bool] = field(default_factory=dict)
    custom: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProjectSettings:
    """Project-level settings with optional org inheritance."""
    project_id: str = ""
    inherit_org_settings: bool = True
    workflow: WorkflowSettings = field(default_factory=WorkflowSettings)
    agents: AgentSettings = field(default_factory=AgentSettings)
    repository_url: str = ""
    default_branch: str = "main"
    protected_branches: list[str] = field(default_factory=list)
    environments: list[str] = field(default_factory=list)
    active_environment: str = ""
    features: Dict[str, bool] = field(default_factory=dict)
    custom: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Update request models
# ---------------------------------------------------------------------------

@dataclass
class UpdateBrandingRequest:
    logo_url: str | None = None
    primary_color: str | None = None
    display_name: str | None = None
    tagline: str | None = None


@dataclass
class UpdateNotificationRequest:
    email_enabled: bool | None = None
    slack_enabled: bool | None = None
    slack_webhook_url: str | None = None


@dataclass
class UpdateSecurityRequest:
    require_mfa: bool | None = None
    sso_enabled: bool | None = None
    session_timeout_hours: int | None = None
    allowed_domains: list[str] | None = None


@dataclass
class UpdateIntegrationRequest:
    github_enabled: bool | None = None
    github_org: str | None = None
    gitlab_enabled: bool | None = None
    gitlab_url: str | None = None


@dataclass
class UpdateWorkflowRequest:
    default_behaviors: list[str] | None = None
    max_concurrent_runs: int | None = None
    default_token_budget: int | None = None


# Legacy aliases expected by OSS shim
UpdateGeneralSettingsRequest = UpdateBrandingRequest
UpdateSecuritySettingsRequest = UpdateSecurityRequest
UpdateNotificationSettingsRequest = UpdateNotificationRequest
UpdateComplianceSettingsRequest = UpdateSecurityRequest

# Additional legacy dataclasses that may be imported
@dataclass
class GeneralSettings:
    org_name: str = ""
    timezone: str = "UTC"
    locale: str = "en"


@dataclass
class BillingSettings:
    plan_id: str = ""
    auto_renew: bool = True


@dataclass
class ComplianceSettings:
    data_retention_days: int = 365
    audit_log_enabled: bool = True


@dataclass
class FeatureSettings:
    enabled_features: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------

class SettingsService:
    """Manages per-org and per-project settings.

    Stub — replace with real Postgres-backed settings storage.
    All methods accept keyword arguments for future extensibility.
    """

    def __init__(self, **kwargs: Any) -> None:
        self._config = kwargs

    # -- Org settings --

    async def get_org_settings(self, org_id: str) -> OrgSettings:
        raise NotImplementedError

    async def update_org_settings(self, org_id: str, **kwargs: Any) -> OrgSettings:
        raise NotImplementedError

    async def update_org_branding(self, org_id: str, **kwargs: Any) -> BrandingSettings:
        raise NotImplementedError

    async def update_org_notifications(self, org_id: str, **kwargs: Any) -> NotificationSettings:
        raise NotImplementedError

    async def update_org_security(self, org_id: str, **kwargs: Any) -> SecuritySettings:
        raise NotImplementedError

    async def update_org_integrations(self, org_id: str, **kwargs: Any) -> IntegrationSettings:
        raise NotImplementedError

    async def update_org_workflow(self, org_id: str, **kwargs: Any) -> WorkflowSettings:
        raise NotImplementedError

    # -- Webhooks --

    async def add_org_webhook(self, org_id: str, **kwargs: Any) -> dict:
        raise NotImplementedError

    async def remove_org_webhook(self, org_id: str, webhook_id: str) -> bool:
        raise NotImplementedError

    # -- Feature flags --

    async def set_org_feature_flag(self, org_id: str, flag_name: str, enabled: bool) -> dict:
        raise NotImplementedError

    async def set_project_feature_flag(self, project_id: str, flag_name: str, enabled: bool) -> dict:
        raise NotImplementedError

    # -- Project settings --

    async def get_project_settings(self, project_id: str) -> ProjectSettings:
        raise NotImplementedError

    async def update_project_settings(self, project_id: str, **kwargs: Any) -> ProjectSettings:
        raise NotImplementedError

    async def update_project_workflow(self, project_id: str, **kwargs: Any) -> WorkflowSettings:
        raise NotImplementedError

    async def set_project_repository(self, project_id: str, **kwargs: Any) -> ProjectSettings:
        raise NotImplementedError
