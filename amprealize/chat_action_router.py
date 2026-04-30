"""Typed chat action routing for governed platform actions.

The router is intentionally deterministic for the first implementation slice:
natural-language messages and preset commands map to typed action candidates
that policy composition, approval UX, and execution services can consume.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .conversation_contracts import (
    ChatPermissionAction,
    ChatPermissionEffect,
    ChatPermissionRequirement,
    ChatPermissionScope,
    ChatPermissionSurface,
    ConversationScope,
    get_chat_permission_requirement,
    normalize_conversation_scope,
)
from .llm.client import LLMClient


class ChatActionCategory(str, Enum):
    """Top-level action families supported by Amprealize Chat."""

    READ_SYNTHESIS = "read_synthesis"
    WORK_MANAGEMENT = "work_management"
    AGENT_MANAGEMENT = "agent_management"
    EXECUTION_PLANNING = "execution_planning"
    EXECUTION_START = "execution_start"
    MCP_TOOL = "mcp_tool"
    ATTACHMENT = "attachment"
    INVITE_SHARE = "invite_share"


class ChatActionRisk(str, Enum):
    """Risk level used before policy evaluation."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class ChatActionCandidate:
    """A typed action candidate returned by the router."""

    action_id: str
    category: ChatActionCategory
    permission_surface: ChatPermissionSurface
    permission_action: ChatPermissionAction
    confidence: float
    risk: ChatActionRisk
    required_scopes: Sequence[ChatPermissionScope]
    requires_approval: bool = False
    requires_clarification: bool = False
    preset: Optional[str] = None
    target_resource_type: Optional[str] = None
    rationale: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_policy_context(self) -> Dict[str, Any]:
        return {
            "chat_surface": self.permission_surface.value,
            "chat_action": self.permission_action.value,
            "action_risk": self.risk.value,
            "sensitive_operation": self.requires_approval,
            "chat_action_candidate": self.to_dict(),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_id": self.action_id,
            "category": self.category.value,
            "permission_surface": self.permission_surface.value,
            "permission_action": self.permission_action.value,
            "confidence": self.confidence,
            "risk": self.risk.value,
            "required_scopes": [scope.value for scope in self.required_scopes],
            "requires_approval": self.requires_approval,
            "requires_clarification": self.requires_clarification,
            "preset": self.preset,
            "target_resource_type": self.target_resource_type,
            "rationale": self.rationale,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ChatActionRouteRequest:
    """Input to the chat action router."""

    message: str
    conversation_scope: ConversationScope = ConversationScope.GLOBAL_USER_HOME
    user_id: str = ""
    org_id: Optional[str] = None
    project_id: Optional[str] = None
    conversation_id: Optional[str] = None
    resource_links: Sequence[Dict[str, Any]] = field(default_factory=tuple)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatActionRouteResult:
    """Router output with one or more action candidates."""

    candidates: Sequence[ChatActionCandidate]
    requires_clarification: bool = False
    clarification_prompt: Optional[str] = None

    @property
    def primary(self) -> Optional[ChatActionCandidate]:
        return self.candidates[0] if self.candidates else None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "requires_clarification": self.requires_clarification,
            "clarification_prompt": self.clarification_prompt,
        }


@dataclass(frozen=True)
class _RoutePattern:
    category: ChatActionCategory
    permission_surface: ChatPermissionSurface
    permission_action: ChatPermissionAction
    risk: ChatActionRisk
    keywords: frozenset[str]
    action_id: str
    target_resource_type: Optional[str] = None
    preset: Optional[str] = None
    rationale: str = ""


_PRESET_ALIASES = {
    "/plan": "plan",
    "/execute": "execute",
    "/run": "execute",
    "/work-item": "work item",
    "/workitem": "work item",
    "/agent": "agent",
    "/tool": "tool",
    "/attach": "attach",
    "/invite": "invite",
}


_ROUTE_PATTERNS: tuple[_RoutePattern, ...] = (
    _RoutePattern(
        category=ChatActionCategory.EXECUTION_PLANNING,
        permission_surface=ChatPermissionSurface.WORK_ITEM_THREAD,
        permission_action=ChatPermissionAction.EXECUTE,
        risk=ChatActionRisk.MEDIUM,
        keywords=frozenset({"plan", "draft", "proposal", "estimate"}),
        action_id="execution.plan",
        target_resource_type="plan",
        preset="/plan",
        rationale="Generate a plan artifact before execution.",
    ),
    _RoutePattern(
        category=ChatActionCategory.EXECUTION_START,
        permission_surface=ChatPermissionSurface.WORK_ITEM_THREAD,
        permission_action=ChatPermissionAction.EXECUTE,
        risk=ChatActionRisk.HIGH,
        keywords=frozenset({"execute", "start", "run", "implement", "ship"}),
        action_id="execution.start",
        target_resource_type="run",
        preset="/execute",
        rationale="Start or resume a governed execution run.",
    ),
    _RoutePattern(
        category=ChatActionCategory.WORK_MANAGEMENT,
        permission_surface=ChatPermissionSurface.PLATFORM_ACTION,
        permission_action=ChatPermissionAction.CREATE,
        risk=ChatActionRisk.MEDIUM,
        keywords=frozenset({"work item", "task", "bug", "feature", "goal", "research", "ticket"}),
        action_id="work_item.manage",
        target_resource_type="work_item",
        preset="/work-item",
        rationale="Create or update work tracking objects.",
    ),
    _RoutePattern(
        category=ChatActionCategory.AGENT_MANAGEMENT,
        permission_surface=ChatPermissionSurface.AGENT_LIFECYCLE,
        permission_action=ChatPermissionAction.UPDATE,
        risk=ChatActionRisk.HIGH,
        keywords=frozenset({"agent", "playbook", "publish", "archive"}),
        action_id="agent.manage",
        target_resource_type="agent",
        preset="/agent",
        rationale="Manage agent lifecycle or policy.",
    ),
    _RoutePattern(
        category=ChatActionCategory.MCP_TOOL,
        permission_surface=ChatPermissionSurface.MCP_TOOL,
        permission_action=ChatPermissionAction.EXECUTE,
        risk=ChatActionRisk.HIGH,
        keywords=frozenset({"mcp", "tool", "invoke"}),
        action_id="mcp_tool.invoke",
        target_resource_type="mcp_tool",
        preset="/tool",
        rationale="Invoke an MCP tool from chat.",
    ),
    _RoutePattern(
        category=ChatActionCategory.ATTACHMENT,
        permission_surface=ChatPermissionSurface.ATTACHMENT,
        permission_action=ChatPermissionAction.CREATE,
        risk=ChatActionRisk.MEDIUM,
        keywords=frozenset({"attach", "upload", "file", "image"}),
        action_id="attachment.add",
        target_resource_type="file",
        preset="/attach",
        rationale="Attach or reference files in the conversation.",
    ),
    _RoutePattern(
        category=ChatActionCategory.INVITE_SHARE,
        permission_surface=ChatPermissionSurface.PROJECT_SPACE,
        permission_action=ChatPermissionAction.INVITE_SHARE,
        risk=ChatActionRisk.HIGH,
        keywords=frozenset({"invite", "share", "add member", "collaborator"}),
        action_id="project.invite_share",
        target_resource_type="project",
        preset="/invite",
        rationale="Invite or share access with another actor.",
    ),
    _RoutePattern(
        category=ChatActionCategory.READ_SYNTHESIS,
        permission_surface=ChatPermissionSurface.GLOBAL_CHAT,
        permission_action=ChatPermissionAction.READ,
        risk=ChatActionRisk.LOW,
        keywords=frozenset({"summarize", "explain", "find", "search", "show"}),
        action_id="chat.read_synthesis",
        rationale="Read or synthesize accessible resources.",
    ),
)

_VALID_ACTION_IDS = frozenset(pattern.action_id for pattern in _ROUTE_PATTERNS)


class ChatRouteMode(str, Enum):
    """Routing implementation mode."""

    DETERMINISTIC = "deterministic"
    LLM = "llm"
    HYBRID = "hybrid"


class ChatActionRouter:
    """Route natural-language chat text to typed action candidates."""

    def route(self, request: ChatActionRouteRequest) -> ChatActionRouteResult:
        normalized_message = self._normalize_message(request.message)
        if not normalized_message:
            return ChatActionRouteResult(
                candidates=(),
                requires_clarification=True,
                clarification_prompt="What would you like Amprealize Chat to do?",
            )

        preset = self._extract_preset(normalized_message)
        candidates = [
            self._candidate_from_pattern(
                pattern,
                request=request,
                normalized_message=normalized_message,
                preset=preset,
            )
            for pattern in self._matching_patterns(normalized_message, preset)
        ]
        if not candidates:
            candidates = [
                self._candidate_from_pattern(
                    self._read_synthesis_pattern(),
                    request=request,
                    normalized_message=normalized_message,
                    preset=preset,
                    force_clarification=True,
                )
            ]

        candidates.sort(key=lambda candidate: candidate.confidence, reverse=True)
        ambiguous = self._is_ambiguous(candidates)
        if ambiguous:
            candidates = [
                self._with_clarification(
                    candidate,
                    "Multiple chat actions matched this request.",
                )
                for candidate in candidates
            ]
        return ChatActionRouteResult(
            candidates=tuple(candidates),
            requires_clarification=ambiguous or candidates[0].requires_clarification,
            clarification_prompt=(
                "Should I treat this as planning, execution, work management, "
                "agent management, a tool call, attachment handling, or sharing?"
                if ambiguous
                else (
                    "Please clarify the target resource or action."
                    if candidates[0].requires_clarification
                    else None
                )
            ),
        )

    def _matching_patterns(
        self,
        normalized_message: str,
        preset: Optional[str],
    ) -> Iterable[_RoutePattern]:
        for pattern in _ROUTE_PATTERNS:
            if preset and preset == pattern.preset:
                yield pattern
                continue
            if any(keyword in normalized_message for keyword in pattern.keywords):
                yield pattern

    def _candidate_from_pattern(
        self,
        pattern: _RoutePattern,
        *,
        request: ChatActionRouteRequest,
        normalized_message: str,
        preset: Optional[str],
        force_clarification: bool = False,
    ) -> ChatActionCandidate:
        permission_surface = self._surface_for_pattern(pattern, request)
        permission = get_chat_permission_requirement(
            permission_surface,
            pattern.permission_action,
        )
        confidence = self._confidence(pattern, normalized_message, preset)
        requires_approval = (
            pattern.risk == ChatActionRisk.HIGH
            or permission.effect == ChatPermissionEffect.REQUIRE_APPROVAL
        )
        requires_clarification = force_clarification or self._needs_clarification(
            pattern,
            request,
            normalized_message,
        )
        return ChatActionCandidate(
            action_id=pattern.action_id,
            category=pattern.category,
            permission_surface=permission_surface,
            permission_action=pattern.permission_action,
            confidence=confidence,
            risk=pattern.risk,
            required_scopes=permission.scopes,
            requires_approval=requires_approval,
            requires_clarification=requires_clarification,
            preset=pattern.preset if preset == pattern.preset else None,
            target_resource_type=pattern.target_resource_type,
            rationale=pattern.rationale or permission.notes,
            metadata={
                "conversation_scope": normalize_conversation_scope(
                    request.conversation_scope
                ).value,
                "conversation_id": request.conversation_id,
                "project_id": request.project_id,
                "org_id": request.org_id,
                "resource_link_count": len(request.resource_links),
                "permission_effect": permission.effect.value,
            },
        )

    def _needs_clarification(
        self,
        pattern: _RoutePattern,
        request: ChatActionRouteRequest,
        normalized_message: str,
    ) -> bool:
        if pattern.category == ChatActionCategory.READ_SYNTHESIS:
            return False
        if pattern.category in {
            ChatActionCategory.EXECUTION_PLANNING,
            ChatActionCategory.EXECUTION_START,
        }:
            has_linked_work = any(
                link.get("resource_type") in {"work_item", "plan", "run"}
                for link in request.resource_links
            )
            return not has_linked_work and not request.project_id
        if pattern.category in {
            ChatActionCategory.WORK_MANAGEMENT,
            ChatActionCategory.AGENT_MANAGEMENT,
            ChatActionCategory.INVITE_SHARE,
        }:
            if pattern.category == ChatActionCategory.WORK_MANAGEMENT:
                return not any(
                    keyword in normalized_message
                    for keyword in {"work item", "task", "bug", "feature", "goal", "research", "ticket"}
                )
            return pattern.target_resource_type not in normalized_message
        if pattern.category == ChatActionCategory.MCP_TOOL:
            return "tool" not in normalized_message and "mcp" not in normalized_message
        return False

    @staticmethod
    def _confidence(
        pattern: _RoutePattern,
        normalized_message: str,
        preset: Optional[str],
    ) -> float:
        if preset and preset == pattern.preset:
            return 0.98
        matches = sum(1 for keyword in pattern.keywords if keyword in normalized_message)
        return min(0.95, 0.55 + (matches * 0.12))

    @staticmethod
    def _is_ambiguous(candidates: Sequence[ChatActionCandidate]) -> bool:
        if len(candidates) < 2:
            return False
        return candidates[0].confidence - candidates[1].confidence < 0.1

    @staticmethod
    def _with_clarification(
        candidate: ChatActionCandidate,
        reason: str,
    ) -> ChatActionCandidate:
        return ChatActionCandidate(
            **{
                **candidate.__dict__,
                "requires_clarification": True,
                "metadata": {**candidate.metadata, "clarification_reason": reason},
            }
        )

    @staticmethod
    def _extract_preset(normalized_message: str) -> Optional[str]:
        first_token = normalized_message.split(" ", 1)[0]
        alias = _PRESET_ALIASES.get(first_token)
        if not alias:
            return None
        for pattern in _ROUTE_PATTERNS:
            if alias in pattern.keywords or first_token == pattern.preset:
                return pattern.preset
        return None

    @staticmethod
    def _normalize_message(message: str) -> str:
        return " ".join(message.strip().lower().split())

    @staticmethod
    def _read_synthesis_pattern() -> _RoutePattern:
        return next(
            pattern
            for pattern in _ROUTE_PATTERNS
            if pattern.category == ChatActionCategory.READ_SYNTHESIS
        )

    @staticmethod
    def _surface_for_pattern(
        pattern: _RoutePattern,
        request: ChatActionRouteRequest,
    ) -> ChatPermissionSurface:
        if pattern.category not in {
            ChatActionCategory.READ_SYNTHESIS,
            ChatActionCategory.EXECUTION_PLANNING,
            ChatActionCategory.EXECUTION_START,
            ChatActionCategory.INVITE_SHARE,
        }:
            return pattern.permission_surface

        scope = normalize_conversation_scope(request.conversation_scope)
        if scope == ConversationScope.GROUP_CHAT:
            return ChatPermissionSurface.GROUP_CHAT
        if scope in {ConversationScope.PROJECT_SPACE, ConversationScope.PROJECT_ROOM}:
            return ChatPermissionSurface.PROJECT_SPACE
        if scope == ConversationScope.RUN_THREAD:
            return ChatPermissionSurface.RUN_THREAD
        if scope == ConversationScope.WORK_ITEM_THREAD:
            return ChatPermissionSurface.WORK_ITEM_THREAD

        if pattern.category in {
            ChatActionCategory.EXECUTION_PLANNING,
            ChatActionCategory.EXECUTION_START,
        }:
            linked_types = {str(link.get("resource_type")) for link in request.resource_links}
            if "run" in linked_types:
                return ChatPermissionSurface.RUN_THREAD
            if linked_types & {"work_item", "plan"}:
                return ChatPermissionSurface.WORK_ITEM_THREAD
            if request.project_id:
                return ChatPermissionSurface.PROJECT_SPACE

        return pattern.permission_surface


class LLMChatActionRouter:
    """Schema-constrained LLM router with deterministic post-validation."""

    def __init__(
        self,
        *,
        llm_client: Any = None,
        fallback_router: Optional[ChatActionRouter] = None,
        model: Optional[str] = None,
    ) -> None:
        self._llm_client = llm_client
        self._fallback_router = fallback_router or ChatActionRouter()
        self._model = model or os.getenv("AMPREALIZE_CHAT_ROUTING_MODEL")

    def route(self, request: ChatActionRouteRequest) -> ChatActionRouteResult:
        fallback_result = self._fallback_router.route(request)
        try:
            response = self._call_llm(request, fallback_result)
            payload = self._parse_json_payload(response.content)
            result = self._result_from_payload(payload, request)
            if not result.candidates:
                return self._with_fallback_metadata(fallback_result, "empty_llm_candidates")
            return result
        except Exception as exc:
            return self._with_fallback_metadata(
                fallback_result,
                "llm_route_failed",
                {"error": exc.__class__.__name__},
            )

    def _call_llm(
        self,
        request: ChatActionRouteRequest,
        fallback_result: ChatActionRouteResult,
    ) -> Any:
        client = self._llm_client
        if client is None:
            client = LLMClient()

        routing_model = (
            request.metadata.get("routing_model_id")
            or self._model
            or request.metadata.get("llm_model_id")
        )
        messages = [
            {
                "role": "system",
                "content": self._system_prompt(),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "message": request.message,
                        "conversation_scope": normalize_conversation_scope(
                            request.conversation_scope
                        ).value,
                        "project_id": request.project_id,
                        "org_id": request.org_id,
                        "resource_links": list(request.resource_links),
                        "deterministic_route": fallback_result.to_dict(),
                    },
                    sort_keys=True,
                ),
            },
        ]
        return client.call(
            messages,
            model=routing_model,
            temperature=0,
            max_tokens=1200,
            project_id=request.project_id,
            org_id=request.org_id,
            user_id=request.user_id,
            prefer_user_credential=request.metadata.get("credential_scope") == "user",
        )

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You route Amprealize chat messages into a strict JSON object. "
            "Return only JSON with keys candidates, requires_clarification, "
            "clarification_prompt. candidates is an array of objects with keys: "
            "action_id, category, permission_surface, permission_action, "
            "confidence, risk, target_resource_type, rationale. "
            f"Allowed action_id values: {sorted(_VALID_ACTION_IDS)}. "
            f"Allowed category values: {[item.value for item in ChatActionCategory]}. "
            f"Allowed permission_surface values: {[item.value for item in ChatPermissionSurface]}. "
            f"Allowed permission_action values: {[item.value for item in ChatPermissionAction]}. "
            f"Allowed risk values: {[item.value for item in ChatActionRisk]}. "
            "Prefer the deterministic route unless the user intent clearly differs. "
            "Do not invent actions, permissions, tools, or resource identifiers."
        )

    @staticmethod
    def _parse_json_payload(content: str) -> Dict[str, Any]:
        stripped = content.strip()
        if stripped.startswith("```"):
            stripped = stripped.strip("`")
            if stripped.startswith("json"):
                stripped = stripped[4:]
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("LLM route response did not contain JSON object")
        payload = json.loads(stripped[start : end + 1])
        if not isinstance(payload, dict):
            raise ValueError("LLM route response JSON must be an object")
        return payload

    def _result_from_payload(
        self,
        payload: Dict[str, Any],
        request: ChatActionRouteRequest,
    ) -> ChatActionRouteResult:
        raw_candidates = payload.get("candidates", [])
        if not isinstance(raw_candidates, list):
            raise ValueError("LLM route candidates must be a list")

        candidates: list[ChatActionCandidate] = []
        for raw_candidate in raw_candidates[:3]:
            if not isinstance(raw_candidate, dict):
                continue
            candidates.append(self._candidate_from_payload(raw_candidate, request))

        candidates.sort(key=lambda candidate: candidate.confidence, reverse=True)
        requires_clarification = bool(payload.get("requires_clarification"))
        if candidates and candidates[0].confidence < 0.55:
            requires_clarification = True
        return ChatActionRouteResult(
            candidates=tuple(candidates),
            requires_clarification=requires_clarification
            or any(candidate.requires_clarification for candidate in candidates),
            clarification_prompt=(
                str(payload.get("clarification_prompt"))
                if payload.get("clarification_prompt")
                else (
                    "Please clarify the target resource or action."
                    if requires_clarification
                    else None
                )
            ),
        )

    @staticmethod
    def _candidate_from_payload(
        raw_candidate: Dict[str, Any],
        request: ChatActionRouteRequest,
    ) -> ChatActionCandidate:
        action_id = str(raw_candidate.get("action_id", ""))
        if action_id not in _VALID_ACTION_IDS:
            raise ValueError(f"Unknown chat action id: {action_id}")

        category = ChatActionCategory(str(raw_candidate.get("category", "")))
        permission_surface = ChatPermissionSurface(
            str(raw_candidate.get("permission_surface", ""))
        )
        permission_action = ChatPermissionAction(
            str(raw_candidate.get("permission_action", ""))
        )
        risk = ChatActionRisk(str(raw_candidate.get("risk", ChatActionRisk.MEDIUM.value)))
        permission = get_chat_permission_requirement(
            permission_surface,
            permission_action,
        )
        confidence = max(0.0, min(1.0, float(raw_candidate.get("confidence", 0.0))))
        requires_clarification = confidence < 0.55
        requires_approval = (
            risk == ChatActionRisk.HIGH
            or permission.effect == ChatPermissionEffect.REQUIRE_APPROVAL
        )
        return ChatActionCandidate(
            action_id=action_id,
            category=category,
            permission_surface=permission_surface,
            permission_action=permission_action,
            confidence=confidence,
            risk=risk,
            required_scopes=permission.scopes,
            requires_approval=requires_approval,
            requires_clarification=requires_clarification,
            target_resource_type=raw_candidate.get("target_resource_type"),
            rationale=str(raw_candidate.get("rationale") or permission.notes),
            metadata={
                "route_mode": ChatRouteMode.LLM.value,
                "conversation_scope": normalize_conversation_scope(
                    request.conversation_scope
                ).value,
                "conversation_id": request.conversation_id,
                "project_id": request.project_id,
                "org_id": request.org_id,
                "resource_link_count": len(request.resource_links),
                "permission_effect": permission.effect.value,
            },
        )

    @staticmethod
    def _with_fallback_metadata(
        result: ChatActionRouteResult,
        reason: str,
        extra_metadata: Optional[Dict[str, Any]] = None,
    ) -> ChatActionRouteResult:
        candidates = tuple(
            ChatActionCandidate(
                **{
                    **candidate.__dict__,
                    "metadata": {
                        **candidate.metadata,
                        "route_mode": ChatRouteMode.DETERMINISTIC.value,
                        "fallback_reason": reason,
                        **(extra_metadata or {}),
                    },
                }
            )
            for candidate in result.candidates
        )
        return ChatActionRouteResult(
            candidates=candidates,
            requires_clarification=result.requires_clarification,
            clarification_prompt=result.clarification_prompt,
        )


class ChatRouteGateway:
    """Choose deterministic, LLM, or hybrid routing behind one stable contract."""

    def __init__(
        self,
        *,
        deterministic_router: Optional[ChatActionRouter] = None,
        llm_router: Optional[LLMChatActionRouter] = None,
        mode: Optional[ChatRouteMode | str] = None,
    ) -> None:
        self._deterministic_router = deterministic_router or ChatActionRouter()
        self._llm_router = llm_router or LLMChatActionRouter(
            fallback_router=self._deterministic_router
        )
        configured_mode = mode or os.getenv(
            "AMPREALIZE_CHAT_ROUTE_MODE",
            ChatRouteMode.DETERMINISTIC.value,
        )
        self._mode = ChatRouteMode(configured_mode)

    def route(self, request: ChatActionRouteRequest) -> ChatActionRouteResult:
        mode = ChatRouteMode(request.metadata.get("chat_route_mode") or self._mode)
        if mode == ChatRouteMode.DETERMINISTIC:
            return self._deterministic_router.route(request)
        if mode in {ChatRouteMode.LLM, ChatRouteMode.HYBRID}:
            return self._llm_router.route(request)
        return self._deterministic_router.route(request)
