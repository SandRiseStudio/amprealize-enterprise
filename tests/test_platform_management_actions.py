"""Tests for governed platform management chat actions."""

from __future__ import annotations

import pytest

from amprealize.platform_management_actions import (
    PlatformManagementActionRequest,
    PlatformManagementActionService,
    PlatformManagementActionType,
    PlatformResourceType,
)
from amprealize.session_audit import GovernedChatAuditLogger

pytestmark = pytest.mark.unit


class FakePlatformService:
    def __init__(self) -> None:
        self.calls = []

    def create_work_item(self, payload):
        self.calls.append(("create_work_item", payload))
        return {"item_id": "task-1", "title": payload["title"]}

    def invite_or_share(self, payload):
        self.calls.append(("invite_or_share", payload))
        return {"invite_id": "invite-1", "target": payload["target"]}

    def attach_file(self, payload):
        self.calls.append(("attach_file", payload))
        return {"file_id": "file-1", "project_id": payload["project_id"]}

    def grant_tool_access(self, payload):
        self.calls.append(("grant_tool_access", payload))
        return {"tool": payload["tool_name"], "target": payload["target"]}


@pytest.mark.asyncio
async def test_create_work_item_dispatches_without_approval_and_audits():
    platform = FakePlatformService()
    audit = GovernedChatAuditLogger()
    service = PlatformManagementActionService(
        services={PlatformResourceType.WORK_ITEM: platform},
        audit_logger=audit,
    )

    result = await service.execute(
        PlatformManagementActionRequest(
            action_type=PlatformManagementActionType.CREATE,
            resource_type=PlatformResourceType.WORK_ITEM,
            user_id="user-1",
            project_id="proj-1",
            payload={"title": "Fix gateway card"},
        )
    )

    assert result.success is True
    assert result.requires_approval is False
    assert platform.calls[0][0] == "create_work_item"
    assert platform.calls[0][1]["actor"]["surface"] == "chat"
    assert audit.records[0].action == "platform.work_item.create"
    assert audit.records[0].decision == "allow"


@pytest.mark.asyncio
async def test_invite_share_requires_target_and_approval_before_dispatch():
    platform = FakePlatformService()
    service = PlatformManagementActionService(
        services={PlatformResourceType.INVITE_SHARE: platform}
    )

    with pytest.raises(ValueError, match="explicit target"):
        await service.execute(
            PlatformManagementActionRequest(
                action_type=PlatformManagementActionType.INVITE_SHARE,
                resource_type=PlatformResourceType.INVITE_SHARE,
                user_id="user-1",
                project_id="proj-1",
            )
        )

    result = await service.execute(
        PlatformManagementActionRequest(
            action_type=PlatformManagementActionType.INVITE_SHARE,
            resource_type=PlatformResourceType.INVITE_SHARE,
            user_id="user-1",
            project_id="proj-1",
            payload={"target": "teammate@example.com"},
        )
    )

    assert result.success is False
    assert result.requires_approval is True
    assert platform.calls == []


@pytest.mark.asyncio
async def test_approved_invite_share_dispatches_to_typed_service():
    platform = FakePlatformService()
    audit = GovernedChatAuditLogger()
    service = PlatformManagementActionService(
        services={PlatformResourceType.INVITE_SHARE: platform},
        audit_logger=audit,
    )

    result = await service.execute(
        PlatformManagementActionRequest(
            action_type=PlatformManagementActionType.INVITE_SHARE,
            resource_type=PlatformResourceType.INVITE_SHARE,
            user_id="user-1",
            approved_by="owner-1",
            project_id="proj-1",
            payload={"target": "teammate@example.com"},
        )
    )

    assert result.success is True
    assert result.requires_approval is True
    assert platform.calls[0][0] == "invite_or_share"
    assert platform.calls[0][1]["actor"]["id"] == "owner-1"
    assert audit.records[0].decision == "approved"


@pytest.mark.asyncio
async def test_attachment_requires_scope_and_is_audited():
    platform = FakePlatformService()
    service = PlatformManagementActionService(
        services={PlatformResourceType.FILE: platform}
    )

    with pytest.raises(ValueError, match="project or conversation scope"):
        await service.execute(
            PlatformManagementActionRequest(
                action_type=PlatformManagementActionType.CREATE,
                resource_type=PlatformResourceType.FILE,
                user_id="user-1",
                payload={"filename": "plan.md"},
            )
        )

    result = await service.execute(
        PlatformManagementActionRequest(
            action_type=PlatformManagementActionType.CREATE,
            resource_type=PlatformResourceType.FILE,
            user_id="user-1",
            project_id="proj-1",
            payload={"filename": "plan.md"},
        )
    )

    assert result.success is True
    assert platform.calls[0][0] == "attach_file"
    assert platform.calls[0][1]["project_id"] == "proj-1"


@pytest.mark.asyncio
async def test_tool_access_grant_requires_approval():
    platform = FakePlatformService()
    service = PlatformManagementActionService(
        services={PlatformResourceType.MCP_TOOL: platform}
    )

    result = await service.execute(
        PlatformManagementActionRequest(
            action_type=PlatformManagementActionType.GRANT_TOOL_ACCESS,
            resource_type=PlatformResourceType.MCP_TOOL,
            user_id="user-1",
            project_id="proj-1",
            payload={"target": "agent-1", "tool_name": "write_file"},
        )
    )

    assert result.success is False
    assert result.requires_approval is True
    assert platform.calls == []
