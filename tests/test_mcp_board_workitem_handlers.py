"""Unit tests for board/work item MCP handler routing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from amprealize.mcp.handlers.board_handlers import (
    BOARD_HANDLERS,
    COLUMN_HANDLERS,
    WORK_ITEM_HANDLERS,
    handle_post_comment,
)
from amprealize.mcp.handlers.work_item_execution_handlers import get_work_item_execution_tools


pytestmark = pytest.mark.unit


class _FakeCommentService:
    def resolve_work_item_id(self, identifier: str, org_id=None, project_id=None) -> str:
        return identifier

    def add_comment(self, **kwargs):
        return {
            "work_item_id": kwargs["work_item_id"],
            "author_id": kwargs["author_id"],
            "author_type": kwargs["author_type"],
            "content": kwargs["content"],
        }


def test_board_and_work_item_manifests_have_handlers() -> None:
    root = Path(__file__).resolve().parents[1]
    manifest_names = {
        json.loads(path.read_text())["name"]
        for path in (root / "mcp" / "tools").glob("*.json")
        if path.name.startswith(("board.", "boards.", "columns.", "workItems."))
    }
    execution_names = {tool["name"] for tool in get_work_item_execution_tools()}
    handled_names = set(BOARD_HANDLERS) | set(COLUMN_HANDLERS) | set(WORK_ITEM_HANDLERS) | execution_names

    assert manifest_names - handled_names == set()


def test_post_comment_defaults_author_from_session() -> None:
    result = handle_post_comment(
        _FakeCommentService(),
        {
            "work_item_id": "task-123",
            "body": "Looks good.",
            "_session": {"user_id": "user-123"},
        },
    )

    assert result["success"] is True
    assert result["comment"]["author_id"] == "user-123"


def test_post_comment_defaults_author_from_user_id_and_agent_role() -> None:
    result = handle_post_comment(
        _FakeCommentService(),
        {
            "work_item_id": "guideai-1052",
            "body": "Completed guideai-1052.",
            "user_id": "cursor-agent",
            "actor_role": "Student",
            "actor_surface": "mcp",
        },
    )

    assert result["success"] is True
    assert result["comment"]["author_id"] == "cursor-agent"
    assert result["comment"]["author_type"] == "agent"
