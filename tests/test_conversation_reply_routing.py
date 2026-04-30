from __future__ import annotations

from dataclasses import dataclass

import pytest

from amprealize.context_composer import ComposedContext
from amprealize.conversation_contracts import ActorType
from amprealize.services.conversation_reply_service import (
    ConversationReplyService,
    ReplyRequest,
)
from amprealize.session_audit import GovernedChatAuditLogger

pytestmark = pytest.mark.unit


class _FakeComposer:
    async def compose(self, **kwargs):
        return ComposedContext(
            composed_text="Project context",
            total_tokens=12,
            fragments_included=[],
            fragments_excluded=[],
            sources_included=["work_item:guideai-1"],
            token_allocation={},
            budget_utilization=0.1,
            composition_time_ms=1.0,
        )


@dataclass
class _FakeLLMResponse:
    content: str


class _FakeLLMClient:
    def __init__(self) -> None:
        self.calls = []

    def call(self, messages, **kwargs):
        self.calls.append({"messages": messages, **kwargs})
        return _FakeLLMResponse("Done.")


class _FakeConversationService:
    def __init__(self) -> None:
        self.messages = []
        self.participant_adds: list = []

    def add_participant(self, conversation_id, **kwargs):
        self.participant_adds.append({"conversation_id": conversation_id, **kwargs})

    def send_message(self, conversation_id, **kwargs):
        self.messages.append({"conversation_id": conversation_id, **kwargs})


@pytest.mark.asyncio
async def test_generate_reply_records_route_metadata_and_selected_model():
    llm_client = _FakeLLMClient()
    conversation_service = _FakeConversationService()
    audit = GovernedChatAuditLogger()
    service = ConversationReplyService(
        context_composer=_FakeComposer(),
        conversation_service=conversation_service,
        llm_client=llm_client,
        governed_chat_audit=audit,
    )

    result = await service.generate_reply(
        ReplyRequest(
            conversation_id="conv-1",
            user_message_id="msg-user-1",
            user_message_content="execute this work item",
            user_id="user-1",
            project_id="proj-1",
            org_id="org-1",
            metadata={
                "llm_model_id": "nvidia-deepseek-v4-flash",
                "credential_scope": "project",
                "resource_links": [
                    {"resource_type": "work_item", "resource_id": "guideai-1"}
                ],
            },
        )
    )

    assert result.success is True
    assert len(conversation_service.participant_adds) == 1
    assert conversation_service.participant_adds[0]["actor_id"] == "amprealize-agent"
    assert conversation_service.messages[0]["sender_type"] == ActorType.AGENT
    assert "actor_type" not in conversation_service.messages[0]
    assert llm_client.calls[0]["model"] == "nvidia-deepseek-v4-flash"
    assert llm_client.calls[0]["project_id"] == "proj-1"
    stored_metadata = conversation_service.messages[0]["metadata"]
    assert stored_metadata["chat_route"]["candidates"][0]["action_id"] == "execution.start"
    assert stored_metadata["chat_route_mode"] == "deterministic"
    assert stored_metadata["chat_route_requires_approval"] is True
    assert stored_metadata["chat_route_policy_context"]["chat_action"] == "execute"
    assert audit.records[0].event_type == "intent_classification"
    assert audit.records[0].metadata["selected_model"] == "nvidia-deepseek-v4-flash"
