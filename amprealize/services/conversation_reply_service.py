"""ConversationReplyService — Orchestrates agent replies in conversations.

This service bridges the conversation system with AI-powered response generation:
1. Receives user message context
2. Calls ContextComposer to assemble relevant context
3. Invokes LLM to generate response with composed context
4. Stores agent reply via ConversationService
5. Emits token stream via ConversationEventHub for SSE

Flow:
    User message -> ContextComposer.compose() -> LLM call -> ConversationService.send_message()

AMPREALIZE-581: Integrate ContextComposer with agent execution loop for conversation replies.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Dict, List, Optional

from amprealize.chat_action_router import ChatActionRouteRequest, ChatRouteGateway
from amprealize.context_composer import ContextComposer, ComposedContext
from amprealize.conversation_contracts import (
    ActorType,
    ConversationScope,
    MessageType,
    ParticipantRole,
)
from amprealize.conversation_event_hub import (
    EVENT_COMPLETE,
    EVENT_ERROR,
    EVENT_TOKEN,
    ConversationEventHub,
)
from amprealize.session_audit import GovernedChatAuditEventType, GovernedChatAuditLogger

logger = logging.getLogger(__name__)


@dataclass
class ReplyRequest:
    """Request to generate an agent reply in a conversation."""

    conversation_id: str
    """ID of the conversation where the agent should reply."""

    user_message_id: str
    """ID of the user message being replied to."""

    user_message_content: str
    """Content of the user message (used for relevance scoring)."""

    user_id: str
    """ID of the user who sent the message."""

    agent_id: str = "amprealize-agent"
    """ID of the agent generating the reply."""

    work_item_id: Optional[str] = None
    """Optional work item context."""

    run_id: Optional[str] = None
    """Optional run context."""

    org_id: Optional[str] = None
    """Organization ID for multi-tenant isolation."""

    project_id: Optional[str] = None
    """Project ID for context scoping."""

    system_prompt_override: Optional[str] = None
    """Optional override for the system prompt."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional metadata for the reply."""


@dataclass
class ReplyResult:
    """Result of generating an agent reply."""

    message_id: str
    """ID of the generated message."""

    content: str
    """Generated reply content."""

    conversation_id: str
    """Conversation where the reply was posted."""

    composed_context: ComposedContext
    """Context that was composed for generation."""

    token_count: int
    """Number of tokens in the generated response."""

    latency_ms: float
    """Total latency in milliseconds."""

    success: bool = True
    """Whether the reply was successful."""

    error: Optional[str] = None
    """Error message if failed."""


class ConversationReplyService:
    """Orchestrates context-aware agent replies in conversations.

    This service integrates:
    - ContextComposer: Assembles project context for grounding
    - LLM Client: Generates responses
    - ConversationService: Persists messages
    - ConversationEventHub: Streams tokens via SSE
    """

    # Default system prompt for conversational replies
    DEFAULT_SYSTEM_PROMPT = """You are a helpful AI assistant with full context about the user's project.

Use the provided context to give accurate, relevant answers:
- Reference specific work items, runs, or conversations when relevant
- If you cite information from the context, mention the source
- If the question is about something not in the context, say so
- Keep responses concise but thorough

{context}"""

    def __init__(
        self,
        *,
        context_composer: Optional[ContextComposer] = None,
        conversation_service: Optional[Any] = None,  # ConversationService
        llm_client: Optional[Any] = None,  # LLMClient
        event_hub: Optional[ConversationEventHub] = None,
        telemetry: Optional[Any] = None,
        route_gateway: Optional[ChatRouteGateway] = None,
        governed_chat_audit: Optional[GovernedChatAuditLogger] = None,
    ):
        """Initialize ConversationReplyService.

        Args:
            context_composer: Composer for assembling context
            conversation_service: Service for message CRUD
            llm_client: Client for LLM calls
            event_hub: Hub for token streaming events
            telemetry: Telemetry client
        """
        self._composer = context_composer or ContextComposer()
        self._conversation_service = conversation_service
        self._llm_client = llm_client
        self._event_hub = event_hub
        self._telemetry = telemetry
        self._route_gateway = route_gateway or ChatRouteGateway()
        self._governed_chat_audit = governed_chat_audit

    def set_llm_client(self, client: Any) -> None:
        """Set the LLM client (avoids circular import)."""
        self._llm_client = client

    def set_conversation_service(self, service: Any) -> None:
        """Set the conversation service."""
        self._conversation_service = service

    async def generate_reply(
        self,
        request: ReplyRequest,
    ) -> ReplyResult:
        """Generate and store an agent reply in a conversation.

        Flow:
        1. Compose context via ContextComposer
        2. Build LLM messages with context
        3. Call LLM and stream tokens
        4. Store completed reply via ConversationService

        Args:
            request: Reply request with conversation context

        Returns:
            ReplyResult with generated message details
        """
        t_start = time.monotonic()
        message_id = f"msg-{uuid.uuid4().hex[:12]}"
        logger.info(
            "conversation_reply.generate_reply.start conversation_id=%s "
            "user_message_id=%s model=%s project_id=%s org_id=%s",
            request.conversation_id,
            request.user_message_id,
            (request.metadata or {}).get("llm_model_id"),
            request.project_id,
            request.org_id,
        )

        try:
            route_result = self._route_user_message(request)
            route_metadata = {
                "chat_route": route_result.to_dict(),
                "chat_route_mode": (
                    route_result.primary.metadata.get("route_mode", "deterministic")
                    if route_result.primary
                    else "deterministic"
                ),
                "chat_route_confidence": (
                    route_result.primary.confidence if route_result.primary else None
                ),
                "chat_route_requires_clarification": route_result.requires_clarification,
                "chat_route_requires_approval": (
                    route_result.primary.requires_approval if route_result.primary else False
                ),
                "chat_route_policy_context": (
                    route_result.primary.to_policy_context()
                    if route_result.primary
                    else {}
                ),
            }
            self._log_route_audit(request, route_metadata)

            # Step 1: Compose context
            composed = await self._composer.compose(
                conversation_id=request.conversation_id,
                user_id=request.user_id,
                query=request.user_message_content,
                work_item_id=request.work_item_id,
                run_id=request.run_id,
            )

            logger.info(
                f"Composed context for reply: {composed.total_tokens} tokens, "
                f"{len(composed.sources_included)} sources"
            )

            # Step 2: Build LLM messages
            system_prompt = (
                request.system_prompt_override
                or self.DEFAULT_SYSTEM_PROMPT.format(context=composed.composed_text)
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.user_message_content},
            ]

            # Step 3: Generate response
            if self._llm_client is None:
                raise RuntimeError("LLM client not configured")

            response_content = await self._generate_with_streaming(
                messages=messages,
                conversation_id=request.conversation_id,
                message_id=message_id,
                metadata=request.metadata,
                project_id=request.project_id,
                org_id=request.org_id,
                user_id=request.user_id,
            )

            # Step 4: Store the reply
            if self._conversation_service is not None:
                self._conversation_service.add_participant(
                    request.conversation_id,
                    actor_id=request.agent_id,
                    actor_type=ActorType.AGENT,
                    role=ParticipantRole.MEMBER,
                    added_by=request.user_id,
                    org_id=request.org_id,
                )
                self._conversation_service.send_message(
                    request.conversation_id,
                    sender_id=request.agent_id,
                    content=response_content,
                    message_type=MessageType.TEXT,
                    parent_id=request.user_message_id,
                    run_id=request.run_id,
                    work_item_id=request.work_item_id,
                    metadata={
                        **request.metadata,
                        **route_metadata,
                        "generated": True,
                        "composed_context_tokens": composed.total_tokens,
                        "sources_used": composed.sources_included,
                    },
                    org_id=request.org_id,
                    sender_type=ActorType.AGENT,
                )

            latency_ms = (time.monotonic() - t_start) * 1000

            # Emit telemetry
            if self._telemetry:
                self._telemetry.emit_event(
                    event_type="conversation_reply.generated",
                    payload={
                        "conversation_id": request.conversation_id,
                        "message_id": message_id,
                        "agent_id": request.agent_id,
                        "context_tokens": composed.total_tokens,
                        "response_length": len(response_content),
                        "latency_ms": latency_ms,
                        "sources_count": len(composed.sources_included),
                        **route_metadata,
                    },
                )

            logger.info(
                "conversation_reply.generate_reply.done conversation_id=%s "
                "stream_message_id=%s latency_ms=%.1f response_chars=%s",
                request.conversation_id,
                message_id,
                latency_ms,
                len(response_content),
            )
            return ReplyResult(
                message_id=message_id,
                content=response_content,
                conversation_id=request.conversation_id,
                composed_context=composed,
                token_count=len(response_content.split()),  # Rough estimate
                latency_ms=latency_ms,
            )

        except Exception as exc:
            logger.error(
                "conversation_reply.generate_reply.failed conversation_id=%s "
                "user_message_id=%s stream_message_id=%s err=%s",
                request.conversation_id,
                request.user_message_id,
                message_id,
                exc,
                exc_info=True,
            )
            latency_ms = (time.monotonic() - t_start) * 1000

            # Emit error event to SSE
            if self._event_hub:
                self._event_hub.publish_token(
                    request.conversation_id,
                    message_id,
                    {
                        "message_id": message_id,
                        "error": str(exc),
                    },
                    event_type=EVENT_ERROR,
                )

            return ReplyResult(
                message_id=message_id,
                content="",
                conversation_id=request.conversation_id,
                composed_context=ComposedContext(
                    composed_text="",
                    total_tokens=0,
                    fragments_included=[],
                    fragments_excluded=[],
                    sources_included=[],
                    token_allocation={},
                    budget_utilization=0.0,
                    composition_time_ms=0.0,
                ),
                token_count=0,
                latency_ms=latency_ms,
                success=False,
                error=str(exc),
            )

    async def _generate_with_streaming(
        self,
        messages: List[Dict[str, str]],
        conversation_id: str,
        message_id: str,
        metadata: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
        org_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> str:
        """Generate LLM response with optional token streaming.

        Args:
            messages: Chat messages for LLM
            conversation_id: For event routing
            message_id: For event routing

        Returns:
            Complete generated text
        """
        selected_model = (metadata or {}).get("llm_model_id")
        prefer_user_credential = (metadata or {}).get("credential_scope") == "user"

        # Check if LLM client supports async streaming
        if hasattr(self._llm_client, "astream"):
            tokens: List[str] = []
            last_stream_response: Any = None
            async for chunk in self._llm_client.astream(
                messages,
                model=selected_model,
                project_id=project_id,
                org_id=org_id,
                user_id=user_id,
                prefer_user_credential=prefer_user_credential,
            ):
                err = getattr(chunk, "error", None)
                if err:
                    raise RuntimeError(str(err))
                resp = getattr(chunk, "response", None)
                if resp is not None:
                    last_stream_response = resp
                token = getattr(chunk, "text", None) or getattr(chunk, "reasoning", None) or ""
                if not token:
                    continue
                tokens.append(token)

                # Broadcast token via event hub
                if self._event_hub:
                    self._event_hub.publish_token(
                        conversation_id,
                        message_id,
                        {
                            "message_id": message_id,
                            "token": token,
                        },
                        event_type=EVENT_TOKEN,
                    )

            content = "".join(tokens)
            if (not content or not str(content).strip()) and last_stream_response is not None:
                fallback = getattr(last_stream_response, "content", None) or ""
                if str(fallback).strip():
                    content = fallback

        elif hasattr(self._llm_client, "stream"):
            tokens = []
            async for token in self._llm_client.stream(messages):
                tokens.append(token)

                # Broadcast token via event hub
                if self._event_hub:
                    self._event_hub.publish_token(
                        conversation_id,
                        message_id,
                        {
                            "message_id": message_id,
                            "token": token,
                        },
                        event_type=EVENT_TOKEN,
                    )

            content = "".join(tokens)

        else:
            # Non-streaming fallback
            response = self._llm_client.call(
                messages,
                model=selected_model,
                project_id=project_id,
                org_id=org_id,
                user_id=user_id,
                prefer_user_credential=prefer_user_credential,
            )
            content = response.content if hasattr(response, "content") else str(response)

        # Publish completion event
        if self._event_hub:
            self._event_hub.publish_token(
                conversation_id,
                message_id,
                {
                    "message_id": message_id,
                    "content": content,
                },
                event_type=EVENT_COMPLETE,
            )

        return content

    def _route_user_message(self, request: ReplyRequest):
        conversation_scope = request.metadata.get("conversation_scope")
        if not conversation_scope:
            conversation_scope = (
                ConversationScope.PROJECT_SPACE.value
                if request.project_id
                else ConversationScope.GLOBAL_USER_HOME.value
            )
        route_request = ChatActionRouteRequest(
            message=request.user_message_content,
            conversation_scope=ConversationScope(conversation_scope),
            user_id=request.user_id,
            org_id=request.org_id,
            project_id=request.project_id,
            conversation_id=request.conversation_id,
            resource_links=request.metadata.get("resource_links", ()),
            metadata=request.metadata,
        )
        return self._route_gateway.route(route_request)

    def _log_route_audit(
        self,
        request: ReplyRequest,
        route_metadata: Dict[str, Any],
    ) -> None:
        audit = self._governed_chat_audit
        if audit is None and self._telemetry is not None:
            audit = GovernedChatAuditLogger(telemetry=self._telemetry)
        if audit is None:
            return

        route = route_metadata.get("chat_route", {})
        candidates = route.get("candidates", [])
        primary = candidates[0] if candidates else {}
        audit.log(
            event_type=GovernedChatAuditEventType.INTENT_CLASSIFICATION,
            user_id=request.user_id,
            action=str(primary.get("action_id") or "chat.unclassified"),
            decision=(
                "clarification_required"
                if route_metadata.get("chat_route_requires_clarification")
                else "classified"
            ),
            chat_scope=str(
                request.metadata.get("conversation_scope")
                or (
                    ConversationScope.PROJECT_SPACE.value
                    if request.project_id
                    else ConversationScope.GLOBAL_USER_HOME.value
                )
            ),
            target_resources=[
                {
                    "type": primary.get("target_resource_type") or "conversation",
                    "id": request.conversation_id,
                }
            ],
            run_id=request.run_id,
            work_item_id=request.work_item_id,
            conversation_id=request.conversation_id,
            message_id=request.user_message_id,
            metadata={
                "route_mode": route_metadata.get("chat_route_mode"),
                "selected_model": request.metadata.get("llm_model_id"),
                "credential_scope": request.metadata.get("credential_scope"),
                "confidence": route_metadata.get("chat_route_confidence"),
                "requires_approval": route_metadata.get("chat_route_requires_approval"),
                "requires_clarification": route_metadata.get(
                    "chat_route_requires_clarification"
                ),
                "permission_surface": primary.get("permission_surface"),
                "permission_action": primary.get("permission_action"),
            },
        )

    async def generate_reply_stream(
        self,
        request: ReplyRequest,
    ) -> AsyncGenerator[str, None]:
        """Generate reply as an async token stream.

        Yields tokens as they are generated. Useful for direct SSE streaming
        without going through ConversationEventHub.

        Args:
            request: Reply request

        Yields:
            Generated tokens
        """
        # Compose context
        composed = await self._composer.compose(
            conversation_id=request.conversation_id,
            user_id=request.user_id,
            query=request.user_message_content,
            work_item_id=request.work_item_id,
            run_id=request.run_id,
        )

        # Build messages
        system_prompt = (
            request.system_prompt_override
            or self.DEFAULT_SYSTEM_PROMPT.format(context=composed.composed_text)
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.user_message_content},
        ]

        if self._llm_client is None:
            raise RuntimeError("LLM client not configured")

        # Stream tokens
        if hasattr(self._llm_client, "stream"):
            async for token in self._llm_client.stream(messages):
                yield token
        else:
            # Non-streaming fallback - yield entire response
            response = self._llm_client.call(messages)
            content = response.content if hasattr(response, "content") else str(response)
            yield content


__all__ = [
    "ConversationReplyService",
    "ReplyRequest",
    "ReplyResult",
]
