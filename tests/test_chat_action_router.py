"""Tests for governed chat action routing."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from amprealize.chat_action_router import (
    ChatActionCategory,
    ChatActionRisk,
    ChatRouteGateway,
    ChatRouteMode,
    ChatActionRouteRequest,
    ChatActionRouter,
    LLMChatActionRouter,
)
from amprealize.conversation_contracts import (
    ChatPermissionAction,
    ChatPermissionScope,
    ChatPermissionSurface,
    ConversationScope,
)

pytestmark = pytest.mark.unit


@dataclass
class _FakeLLMResponse:
    content: str


class _FakeLLMClient:
    def __init__(self, content: str) -> None:
        self.content = content
        self.calls = []

    def call(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return _FakeLLMResponse(self.content)


def test_preset_plan_routes_to_execution_planning_candidate():
    router = ChatActionRouter()

    result = router.route(
        ChatActionRouteRequest(
            message="/plan guideai-1057",
            conversation_scope=ConversationScope.WORK_ITEM_THREAD,
            project_id="proj-1",
            resource_links=[
                {"resource_type": "work_item", "resource_id": "guideai-1057"}
            ],
        )
    )

    candidate = result.primary
    assert candidate is not None
    assert candidate.category == ChatActionCategory.EXECUTION_PLANNING
    assert candidate.action_id == "execution.plan"
    assert candidate.preset == "/plan"
    assert candidate.confidence == 0.98
    assert candidate.permission_surface == ChatPermissionSurface.WORK_ITEM_THREAD
    assert candidate.permission_action == ChatPermissionAction.EXECUTE
    assert candidate.requires_approval is True
    assert candidate.requires_clarification is False
    assert ChatPermissionScope.PROJECT in candidate.required_scopes


def test_high_risk_execute_requires_approval_and_policy_context():
    router = ChatActionRouter()

    result = router.route(
        ChatActionRouteRequest(
            message="execute this work item",
            project_id="proj-1",
            resource_links=[
                {"resource_type": "work_item", "resource_id": "guideai-1057"}
            ],
        )
    )

    candidate = result.primary
    assert candidate is not None
    policy_context = candidate.to_policy_context()
    assert candidate.category == ChatActionCategory.EXECUTION_START
    assert candidate.risk == ChatActionRisk.HIGH
    assert candidate.requires_approval is True
    assert policy_context["chat_surface"] == "work_item_thread"
    assert policy_context["chat_action"] == "execute"
    assert policy_context["sensitive_operation"] is True


def test_group_chat_execution_uses_group_chat_permission_surface():
    router = ChatActionRouter()

    result = router.route(
        ChatActionRouteRequest(
            message="execute this with the coding agent",
            conversation_scope=ConversationScope.GROUP_CHAT,
            project_id="proj-1",
            conversation_id="conv-group",
            resource_links=[
                {"resource_type": "work_item", "resource_id": "guideai-1057"}
            ],
        )
    )

    candidate = result.primary
    assert candidate is not None
    assert candidate.category == ChatActionCategory.EXECUTION_START
    assert candidate.permission_surface == ChatPermissionSurface.GROUP_CHAT
    assert {
        ChatPermissionScope.CONVERSATION,
        ChatPermissionScope.PROJECT,
        ChatPermissionScope.AGENT,
    }.issubset(set(candidate.required_scopes))
    assert candidate.requires_approval is True
    assert candidate.metadata["conversation_scope"] == "group_chat"


def test_ambiguous_plan_and_execute_asks_for_clarification():
    router = ChatActionRouter()

    result = router.route(
        ChatActionRouteRequest(
            message="plan and execute guideai-1057",
            project_id="proj-1",
        )
    )

    assert result.requires_clarification is True
    assert result.clarification_prompt is not None
    assert len(result.candidates) >= 2
    assert {candidate.category for candidate in result.candidates} >= {
        ChatActionCategory.EXECUTION_PLANNING,
        ChatActionCategory.EXECUTION_START,
    }
    assert all(candidate.requires_clarification for candidate in result.candidates)


def test_work_management_routes_to_platform_action_scope():
    router = ChatActionRouter()

    result = router.route(
        ChatActionRouteRequest(
            message="create a bug for the broken gateway card",
            conversation_scope=ConversationScope.PROJECT_SPACE,
            project_id="proj-1",
        )
    )

    candidate = result.primary
    assert candidate is not None
    assert candidate.category == ChatActionCategory.WORK_MANAGEMENT
    assert candidate.permission_surface == ChatPermissionSurface.PLATFORM_ACTION
    assert candidate.permission_action == ChatPermissionAction.CREATE
    assert candidate.target_resource_type == "work_item"
    assert candidate.requires_clarification is False


def test_unknown_message_defaults_to_read_synthesis_with_clarification():
    router = ChatActionRouter()

    result = router.route(ChatActionRouteRequest(message="maybe later"))

    candidate = result.primary
    assert candidate is not None
    assert result.requires_clarification is True
    assert candidate.category == ChatActionCategory.READ_SYNTHESIS
    assert candidate.requires_clarification is True


def test_llm_router_validates_structured_route_and_recomputes_permissions():
    llm_client = _FakeLLMClient(
        """
        {
          "candidates": [
            {
              "action_id": "execution.start",
              "category": "execution_start",
              "permission_surface": "work_item_thread",
              "permission_action": "execute",
              "confidence": 1.4,
              "risk": "high",
              "target_resource_type": "run",
              "rationale": "User asked to start implementation."
            }
          ],
          "requires_clarification": false,
          "clarification_prompt": null
        }
        """
    )
    router = LLMChatActionRouter(llm_client=llm_client)

    result = router.route(
        ChatActionRouteRequest(
            message="please implement this",
            user_id="user-1",
            project_id="proj-1",
            resource_links=[
                {"resource_type": "work_item", "resource_id": "guideai-1057"}
            ],
        )
    )

    candidate = result.primary
    assert candidate is not None
    assert candidate.action_id == "execution.start"
    assert candidate.confidence == 1.0
    assert candidate.permission_surface == ChatPermissionSurface.WORK_ITEM_THREAD
    assert candidate.permission_action == ChatPermissionAction.EXECUTE
    assert ChatPermissionScope.PROJECT in candidate.required_scopes
    assert candidate.requires_approval is True
    assert candidate.metadata["route_mode"] == "llm"


def test_llm_router_falls_back_on_unknown_action_id():
    llm_client = _FakeLLMClient(
        """
        {
          "candidates": [
            {
              "action_id": "dangerous.unknown",
              "category": "execution_start",
              "permission_surface": "work_item_thread",
              "permission_action": "execute",
              "confidence": 0.99,
              "risk": "high"
            }
          ]
        }
        """
    )
    router = LLMChatActionRouter(llm_client=llm_client)

    result = router.route(
        ChatActionRouteRequest(
            message="execute this work item",
            project_id="proj-1",
            resource_links=[
                {"resource_type": "work_item", "resource_id": "guideai-1057"}
            ],
        )
    )

    candidate = result.primary
    assert candidate is not None
    assert candidate.action_id == "execution.start"
    assert candidate.metadata["route_mode"] == "deterministic"
    assert candidate.metadata["fallback_reason"] == "llm_route_failed"


def test_chat_route_gateway_uses_llm_mode_when_enabled():
    llm_client = _FakeLLMClient(
        """
        {
          "candidates": [
            {
              "action_id": "chat.read_synthesis",
              "category": "read_synthesis",
              "permission_surface": "global_chat",
              "permission_action": "read",
              "confidence": 0.92,
              "risk": "low",
              "rationale": "User is asking for information."
            }
          ]
        }
        """
    )
    llm_router = LLMChatActionRouter(llm_client=llm_client)
    gateway = ChatRouteGateway(llm_router=llm_router, mode=ChatRouteMode.LLM)

    result = gateway.route(ChatActionRouteRequest(message="what happened yesterday?"))

    candidate = result.primary
    assert candidate is not None
    assert candidate.metadata["route_mode"] == "llm"
