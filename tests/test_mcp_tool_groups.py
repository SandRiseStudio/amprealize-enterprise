"""Regression tests for MCP tool grouping and lazy-loader discoverability."""

from __future__ import annotations

import importlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from types import ModuleType

import pytest


pytestmark = pytest.mark.unit


ROOT = Path(__file__).resolve().parents[1]


def _manifest_names() -> set[str]:
    return {
        json.loads(path.read_text())["name"]
        for path in (ROOT / "mcp" / "tools").glob("*.json")
    }


def _load_groups(monkeypatch: pytest.MonkeyPatch, *, whiteboard_enabled: bool) -> ModuleType:
    if whiteboard_enabled:
        monkeypatch.setenv("AMPREALIZE_ENABLE_WHITEBOARD", "true")
    else:
        monkeypatch.delenv("AMPREALIZE_ENABLE_WHITEBOARD", raising=False)

    import amprealize.mcp_tool_groups as groups

    return importlib.reload(groups)


def _load_lazy_loader_module() -> ModuleType:
    import amprealize.mcp_lazy_loader as lazy_loader

    return importlib.reload(lazy_loader)


def _discoverable_tools(groups: ModuleType, manifests: set[str]) -> set[str]:
    discoverable = set(groups.CORE_TOOLS) & manifests
    prefixes = [
        prefix
        for group in groups.TOOL_GROUPS.values()
        for prefix in group.tool_prefixes
    ]
    discoverable.update(
        name
        for name in manifests
        if any(name.startswith(prefix) for prefix in prefixes)
    )
    return discoverable


def test_core_tools_are_published_and_curated(monkeypatch: pytest.MonkeyPatch) -> None:
    groups = _load_groups(monkeypatch, whiteboard_enabled=False)
    manifests = _manifest_names()

    assert groups.CORE_TOOLS <= manifests
    assert len(groups.CORE_TOOLS) <= groups.TOOL_GROUPS[groups.ToolGroupId.CORE].max_tools
    assert not any(name.startswith(("research.", "wiki.", "whiteboard.", "brainstorm.")) for name in groups.CORE_TOOLS)
    assert {"tools.guide", "tools.catalog"} <= groups.CORE_TOOLS


def test_lazy_loader_initializes_startup_groups_without_specialized_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groups = _load_groups(monkeypatch, whiteboard_enabled=False)
    lazy_loader = _load_lazy_loader_module()

    loader = lazy_loader.MCPLazyToolLoader()
    loader.initialize(ROOT / "mcp" / "tools")
    loaded_original_names = {
        manifest["_original_name"]
        for manifest in loader.get_active_tools().values()
    }

    assert groups.CORE_TOOLS <= loaded_original_names
    assert groups.ToolGroupId.PROJECTS in loader._state.active_groups
    assert groups.ToolGroupId.WORK_ITEMS in loader._state.active_groups
    assert "project.setupComplete" in loaded_original_names
    assert "workItems.update" in loaded_original_names
    assert "columns.list" in loaded_original_names
    assert "analytics.fullReport" not in loaded_original_names
    assert "compliance.fullValidation" not in loaded_original_names


def test_startup_groups_are_not_auto_deactivated(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_groups(monkeypatch, whiteboard_enabled=False)
    lazy_loader = _load_lazy_loader_module()

    loader = lazy_loader.MCPLazyToolLoader()
    loader.initialize(ROOT / "mcp" / "tools")
    stale_time = datetime.utcnow() - timedelta(minutes=60)
    loader._state.active_groups.add(lazy_loader.ToolGroupId.WIKI)
    loader._state.last_activation[lazy_loader.ToolGroupId.WIKI] = stale_time
    loader._state.last_activation[lazy_loader.ToolGroupId.PROJECTS] = stale_time
    loader._state.last_activation[lazy_loader.ToolGroupId.WORK_ITEMS] = stale_time

    assert loader._state.get_stale_groups() == [lazy_loader.ToolGroupId.WIKI]


def test_runtime_guide_and_catalog_include_onboarding_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _load_groups(monkeypatch, whiteboard_enabled=False)
    lazy_loader = _load_lazy_loader_module()

    loader = lazy_loader.MCPLazyToolLoader()
    loader.initialize(ROOT / "mcp" / "tools")

    guide = loader.get_usage_guide()
    assert guide["success"] is True
    assert "auth.authStatus" in guide["core_tools"]
    assert guide["startup_protocol"][0].startswith("Call auth.authStatus")
    assert any("approved automatically" in note for note in guide["authorization_notes"])
    assert "/Users/nick/Main/amprealize" in guide["repo_parity_notes"][0]
    assert "/Users/nick/Main/amprealize-enterprise" in guide["repo_parity_notes"][1]
    assert any("unless the user explicitly" in note for note in guide["repo_parity_notes"])
    assert "tools.catalog" in guide["core_tools"]
    assert "work_items" in guide["startup_groups"]
    assert any("context.getContext" in step for step in guide["startup_protocol"])

    catalog = loader.get_tool_catalog(group="work_items", query="get", include_inactive=True)
    assert catalog["success"] is True
    assert any(
        tool["original_name"] == "workItems.get"
        and tool["normalized_name"] == "workitems_get"
        for tool in catalog["tools"]
    )


def test_catalog_can_discover_inactive_group_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    _load_groups(monkeypatch, whiteboard_enabled=False)
    lazy_loader = _load_lazy_loader_module()

    loader = lazy_loader.MCPLazyToolLoader()
    loader.initialize(ROOT / "mcp" / "tools")

    catalog = loader.get_tool_catalog(group="wiki", query="page", include_inactive=True)

    assert catalog["success"] is True
    assert any(tool["group"] == "wiki" and not tool["is_active"] for tool in catalog["tools"])


def test_prompt_and_resource_guidance_are_available() -> None:
    from amprealize.mcp_guidance import MCP_GUIDE_PROMPT_NAME, MCP_GUIDE_RESOURCE_URI
    from amprealize.mcp_server import MCPServer

    server = MCPServer.__new__(MCPServer)
    prompts = json.loads(server._handle_prompts_list("prompts"))["result"]["prompts"]
    resources = json.loads(server._handle_resources_list("resources"))["result"]["resources"]

    assert prompts[0]["name"] == MCP_GUIDE_PROMPT_NAME
    assert resources[0]["uri"] == MCP_GUIDE_RESOURCE_URI

    prompt = json.loads(
        server._handle_prompts_get("prompt", {"name": MCP_GUIDE_PROMPT_NAME})
    )["result"]
    resource = json.loads(
        server._handle_resources_read("resource", {"uri": MCP_GUIDE_RESOURCE_URI})
    )["result"]

    assert "tools.catalog" in prompt["messages"][0]["content"]["text"]
    assert "auth.authStatus" in prompt["messages"][0]["content"]["text"]
    assert "/Users/nick/Main/amprealize-enterprise" in prompt["messages"][0]["content"]["text"]
    assert "tools.guide" in resource["contents"][0]["text"]
    assert "auth.deviceLogin" in resource["contents"][0]["text"]
    assert "/Users/nick/Main/amprealize" in resource["contents"][0]["text"]


def test_agent_docs_reference_mcp_startup_protocol() -> None:
    required_paths = [
        ROOT / "AGENTS.md",
        ROOT / "CLAUDE.md",
        ROOT / ".github" / "agents" / "WorkItemPlanner.agent.md",
        ROOT / "skills" / "work-item-planner" / "SKILL.md",
    ]

    for path in required_paths:
        text = path.read_text()
        assert "tools.guide" in text or "tools_guide" in text
        assert "tools.catalog" in text or "tools_catalog" in text
        assert "auth.authStatus" in text or "auth_authstatus" in text
        assert "/Users/nick/Main/amprealize" in text
        assert "/Users/nick/Main/amprealize-enterprise" in text


def test_every_manifest_is_discoverable_when_feature_groups_are_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groups = _load_groups(monkeypatch, whiteboard_enabled=True)
    manifests = _manifest_names()

    assert _discoverable_tools(groups, manifests) == manifests


def test_only_whiteboard_family_is_gated_when_whiteboard_is_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groups = _load_groups(monkeypatch, whiteboard_enabled=False)
    manifests = _manifest_names()

    missing = manifests - _discoverable_tools(groups, manifests)
    assert missing
    assert all(name.startswith(("whiteboard.", "brainstorm.")) for name in missing)


def test_group_prefixes_match_manifests_and_fit_budgets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groups = _load_groups(monkeypatch, whiteboard_enabled=True)
    manifests = _manifest_names()

    for group_id, group in groups.TOOL_GROUPS.items():
        if group_id == groups.ToolGroupId.CORE:
            continue

        matching = {
            name
            for name in manifests
            if any(name.startswith(prefix) for prefix in group.tool_prefixes)
        }
        assert matching, f"{group_id.value} does not match any published manifests"
        assert len(matching) <= group.max_tools, f"{group_id.value} exceeds max_tools"


def test_activation_keywords_cover_normalized_tool_families(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    groups = _load_groups(monkeypatch, whiteboard_enabled=True)

    assert groups.ToolGroupId.WIKI in groups.suggest_groups_for_query("query the platform wiki")
    assert groups.ToolGroupId.RESEARCH in groups.suggest_groups_for_query("evaluate this arxiv paper")
    assert groups.ToolGroupId.WORK_ITEMS in groups.suggest_groups_for_query("create a work item on the board")
    assert groups.ToolGroupId.AUTHORIZATION in groups.suggest_groups_for_query("check consent grant status")
    assert groups.ToolGroupId.WHITEBOARD in groups.suggest_groups_for_query("open a brainstorm whiteboard")
