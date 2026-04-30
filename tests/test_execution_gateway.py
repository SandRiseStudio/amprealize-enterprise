"""Tests for Phase 1 — ExecutionGateway, contracts, and mode executors.

Covers:
- execution_gateway_contracts: mode resolution, output target resolution
- execution_gateway: gateway orchestration with mocked services
- mode_executors: provisioning and cleanup for each mode
"""

from __future__ import annotations

import pytest
from types import SimpleNamespace
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock

from amprealize.execution_gateway_contracts import (
    ExecutionIntent,
    ExecutionRequest,
    GatewayQueuePayload,
    NewExecutionMode,
    OutputTarget,
    ResolvedExecution,
    SourceType,
    resolve_execution_mode,
    resolve_output_target,
)
from amprealize.multi_tenant.board_contracts import AssigneeType
from amprealize.session_audit import GovernedChatAuditLogger
from amprealize.work_item_execution_contracts import (
    ExecutionPolicy,
    ExecutionState,
    ToolPermissionLevel,
)

pytestmark = pytest.mark.unit


# =============================================================================
# Contract helpers
# =============================================================================


class TestResolveExecutionMode:
    """Tests for resolve_execution_mode()."""

    def test_surface_defaults(self):
        assert resolve_execution_mode("web") == NewExecutionMode.CONTAINER_ISOLATED
        assert resolve_execution_mode("api") == NewExecutionMode.CONTAINER_ISOLATED
        assert resolve_execution_mode("mcp") == NewExecutionMode.CONTAINER_ISOLATED
        assert resolve_execution_mode("cli") == NewExecutionMode.CONTAINER_CONNECTED
        assert resolve_execution_mode("vscode") == NewExecutionMode.CONTAINER_CONNECTED

    def test_explicit_override_wins(self):
        # cli surface supports LOCAL_DIRECT
        assert resolve_execution_mode(
            "cli", mode_override=NewExecutionMode.LOCAL_DIRECT,
        ) == NewExecutionMode.LOCAL_DIRECT

    def test_project_mode_overrides_default(self):
        assert resolve_execution_mode(
            "web", project_mode=NewExecutionMode.CONTAINER_CONNECTED,
        ) == NewExecutionMode.CONTAINER_CONNECTED

    def test_override_beats_project(self):
        assert resolve_execution_mode(
            "cli",
            mode_override=NewExecutionMode.LOCAL_DIRECT,
            project_mode=NewExecutionMode.CONTAINER_CONNECTED,
        ) == NewExecutionMode.LOCAL_DIRECT

    def test_unknown_surface_defaults_isolated(self):
        assert resolve_execution_mode("unknown") == NewExecutionMode.CONTAINER_ISOLATED

    def test_local_direct_rejected_for_non_capable_surface(self):
        """LOCAL_DIRECT should raise ValueError for web surface."""
        with pytest.raises(ValueError, match="LOCAL_DIRECT mode requires a local-capable surface"):
            resolve_execution_mode("web", mode_override=NewExecutionMode.LOCAL_DIRECT)

    def test_local_direct_accepted_for_cli(self):
        assert resolve_execution_mode(
            "cli", mode_override=NewExecutionMode.LOCAL_DIRECT,
        ) == NewExecutionMode.LOCAL_DIRECT

    def test_local_direct_accepted_for_vscode(self):
        assert resolve_execution_mode(
            "vscode", mode_override=NewExecutionMode.LOCAL_DIRECT,
        ) == NewExecutionMode.LOCAL_DIRECT

    def test_case_insensitive_surface(self):
        assert resolve_execution_mode("Web") == NewExecutionMode.CONTAINER_ISOLATED
        assert resolve_execution_mode("CLI") == NewExecutionMode.CONTAINER_CONNECTED


class TestResolveOutputTarget:
    """Tests for resolve_output_target()."""

    def test_explicit_override(self):
        assert resolve_output_target(
            NewExecutionMode.CONTAINER_ISOLATED,
            output_override=OutputTarget.ARCHIVE,
        ) == OutputTarget.ARCHIVE

    def test_isolated_github_defaults_to_pr(self):
        result = resolve_output_target(
            NewExecutionMode.CONTAINER_ISOLATED,
            source_type=SourceType.GITHUB,
        )
        assert result == OutputTarget.PULL_REQUEST

    def test_isolated_gitlab_defaults_to_pr(self):
        result = resolve_output_target(
            NewExecutionMode.CONTAINER_ISOLATED,
            source_type=SourceType.GITLAB,
        )
        assert result == OutputTarget.PULL_REQUEST

    def test_isolated_local_defaults_to_patch(self):
        result = resolve_output_target(
            NewExecutionMode.CONTAINER_ISOLATED,
            source_type=SourceType.LOCAL_DIR,
        )
        assert result == OutputTarget.PATCH_FILE

    def test_isolated_no_source_defaults_to_patch(self):
        result = resolve_output_target(
            NewExecutionMode.CONTAINER_ISOLATED,
        )
        assert result == OutputTarget.PATCH_FILE

    def test_connected_defaults_to_local_sync(self):
        result = resolve_output_target(
            NewExecutionMode.CONTAINER_CONNECTED,
        )
        assert result == OutputTarget.LOCAL_SYNC

    def test_local_direct_defaults_to_local_sync(self):
        result = resolve_output_target(
            NewExecutionMode.LOCAL_DIRECT,
        )
        assert result == OutputTarget.LOCAL_SYNC


class TestExecutionRequest:
    """Basic tests for ExecutionRequest dataclass."""

    def test_defaults(self):
        req = ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
        )
        assert req.surface == "api"
        assert req.mode_override is None
        assert req.request_id.startswith("req-")

    def test_overrides(self):
        req = ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
            surface="vscode",
            mode_override=NewExecutionMode.LOCAL_DIRECT,
        )
        assert req.surface == "vscode"
        assert req.mode_override == NewExecutionMode.LOCAL_DIRECT


class TestGatewayQueuePayload:
    """Tests for the normalized queue payload contract."""

    def test_from_resolved_preserves_gateway_context(self):
        resolved = _make_resolved()
        resolved.request.intent = ExecutionIntent.PLAN_ONLY
        resolved.request.surface = "chat"
        resolved.request.conversation_id = "conv-1"
        resolved.request.message_id = "msg-1"
        resolved.request.idempotency_key = "idem-1"
        resolved.request.policy_context = {"tool_profile": "read_only"}
        resolved.request.risk_classification = "low"
        resolved.request.requires_approval = True
        resolved.request.metadata = {"source": "unit-test"}

        payload = GatewayQueuePayload.from_resolved(resolved).to_dict()

        assert payload["gateway_request_id"] == resolved.request.request_id
        assert payload["intent"] == "plan_only"
        assert payload["surface"] == "chat"
        assert payload["mode"] == "container_isolated"
        assert payload["output_target"] == "pull_request"
        assert payload["source_type"] == "github"
        assert payload["conversation_id"] == "conv-1"
        assert payload["message_id"] == "msg-1"
        assert payload["idempotency_key"] == "idem-1"
        assert payload["policy_context"] == {"tool_profile": "read_only"}
        assert payload["risk_classification"] == "low"
        assert payload["requires_approval"] is True
        assert payload["metadata"] == {"source": "unit-test"}


# =============================================================================
# ExecutionGateway
# =============================================================================


def _make_work_item(**overrides):
    """Create a minimal mock WorkItem."""
    defaults = dict(
        item_id="task-abc123def456",
        title="Test task",
        project_id="proj-1",
        assignee_id="agent-1",
        assignee_type=AssigneeType.AGENT,
        run_id=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_agent(**overrides):
    defaults = dict(agent_id="agent-1", name="TestAgent")
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_version(**overrides):
    defaults = dict(
        version_id="v1",
        version="1.0.0",
        playbook={"phases": {}},
        execution_policy=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _build_gateway(
    *,
    work_item=None,
    agent=None,
    version=None,
    cred_result=("sk-test", "platform", False),
    executor: Optional[Any] = None,
    queue_publisher: Optional[Any] = None,
    dispatch_mode: str = "background",
    telemetry: Optional[Any] = None,
    governed_chat_audit: Optional[GovernedChatAuditLogger] = None,
):
    """Build a gateway with mocked services."""
    from amprealize.execution_gateway import ExecutionGateway

    board = MagicMock()
    wi = work_item or _make_work_item()
    board.get_work_item.return_value = wi

    run_service = MagicMock()
    run_obj = SimpleNamespace(run_id="run-test123")
    run_service.create_run.return_value = run_obj
    run_service.get_run.return_value = None

    cycle_service = MagicMock()
    cycle_obj = SimpleNamespace(cycle=SimpleNamespace(cycle_id="cyc-test123"))
    cycle_service.create_cycle.return_value = cycle_obj

    agent_reg = MagicMock()
    ag = agent or _make_agent()
    ver = version or _make_version()
    agent_reg.get_agent.return_value = ag
    agent_reg.get_latest_version.return_value = ver

    cred_store = MagicMock()
    cred_store.get_credential_for_model.return_value = cred_result

    executors = {}
    if executor:
        executors[executor.mode] = executor

    gw = ExecutionGateway(
        board_service=board,
        run_service=run_service,
        task_cycle_service=cycle_service,
        agent_registry=agent_reg,
        credential_store=cred_store,
        telemetry=telemetry,
        executors=executors,
        queue_publisher=queue_publisher,
        dispatch_mode=dispatch_mode,
        governed_chat_audit=governed_chat_audit,
    )
    return gw


class _FakeQueuePublisher:
    def __init__(self):
        self.jobs = []

    async def enqueue(self, job):
        self.jobs.append(job)
        return "stream-1"


class TestExecutionGateway:

    @pytest.mark.asyncio
    async def test_execute_denied_by_composed_policy_before_records(self):
        telemetry = MagicMock()
        gw = _build_gateway(telemetry=telemetry)

        req = ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
            surface="api",
            policy_context={
                "policy_decisions": {
                    "org": {
                        "decision": "deny",
                        "reason": "Org policy blocks autonomous execution.",
                    }
                }
            },
        )
        result = await gw.execute(req)

        assert result.success is False
        assert "Policy denied execution" in (result.error or "")
        gw._runs.create_run.assert_not_called()
        gw._cycles.create_cycle.assert_not_called()
        telemetry.emit_event.assert_called_once()
        assert telemetry.emit_event.call_args.kwargs["event_type"] == (
            "policy.composition.evaluated"
        )

    @pytest.mark.asyncio
    async def test_execute_review_policy_requires_approval_before_records(self):
        gw = _build_gateway()

        req = ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
            surface="api",
            risk_classification="critical",
        )
        result = await gw.execute(req)

        assert result.success is False
        assert "Policy review required" in (result.error or "")
        assert req.requires_approval is True
        gw._runs.create_run.assert_not_called()
        gw._cycles.create_cycle.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_policy_failure_fails_closed_before_records(self):
        telemetry = MagicMock()
        gw = _build_gateway(telemetry=telemetry)

        req = ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
            surface="api",
            policy_context={"policy_decisions": {"not_a_layer": "allow"}},
        )
        result = await gw.execute(req)

        assert result.success is False
        assert "Policy denied execution" in (result.error or "")
        assert req.policy_context["policy_evaluation"]["failed_closed"] is True
        gw._runs.create_run.assert_not_called()
        gw._cycles.create_cycle.assert_not_called()
        assert telemetry.emit_event.call_args.kwargs["event_type"] == (
            "policy.composition.failed_closed"
        )

    @pytest.mark.asyncio
    async def test_execute_tool_policy_denies_before_records(self):
        policy = ExecutionPolicy(tool_permissions={"delete_file": ToolPermissionLevel.DENY})
        gw = _build_gateway(version=_make_version(execution_policy=policy))

        req = ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
            surface="api",
            policy_context={"mcp_tool_name": "delete_file"},
        )
        result = await gw.execute(req)

        assert result.success is False
        assert "Tool policy denies delete_file" in (result.error or "")
        gw._runs.create_run.assert_not_called()
        gw._cycles.create_cycle.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_denied_policy_writes_governed_chat_audit(self):
        chat_audit = GovernedChatAuditLogger()
        gw = _build_gateway(governed_chat_audit=chat_audit)

        req = ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
            user_id="user-1",
            surface="api",
            conversation_id="conv-1",
            message_id="msg-1",
            policy_context={
                "chat_scope": "work_item_thread",
                "policy_decisions": {
                    "org": {
                        "decision": "deny",
                        "reason": "Org policy blocks autonomous execution.",
                    }
                },
            },
        )
        await gw.execute(req)

        blocked_records = chat_audit.denied_or_review_required()
        assert [record.event_type for record in blocked_records] == [
            "policy_decision",
            "denial",
        ]
        assert blocked_records[0].conversation_id == "conv-1"
        assert blocked_records[0].message_id == "msg-1"
        assert blocked_records[0].target_resources[0] == {
            "type": "work_item",
            "id": "task-abc123def456",
        }

    @pytest.mark.asyncio
    async def test_execute_success_writes_execution_start_audit(self):
        chat_audit = GovernedChatAuditLogger()
        executor = MagicMock()
        executor.mode = NewExecutionMode.CONTAINER_ISOLATED
        executor.provision_workspace = AsyncMock(side_effect=lambda r: r)
        executor.execute = AsyncMock(return_value={})
        executor.cleanup = AsyncMock()
        gw = _build_gateway(executor=executor, governed_chat_audit=chat_audit)

        req = ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
            user_id="user-1",
            surface="api",
            conversation_id="conv-1",
        )
        result = await gw.execute(req)

        assert result.success is True
        execution_records = chat_audit.query(event_types={"execution_start"})
        assert len(execution_records) == 1
        assert execution_records[0].run_id == "run-test123"
        assert execution_records[0].conversation_id == "conv-1"

    @pytest.mark.asyncio
    async def test_execute_returns_run_id(self):
        executor = MagicMock()
        executor.mode = NewExecutionMode.CONTAINER_ISOLATED
        executor.provision_workspace = AsyncMock(side_effect=lambda r: r)
        executor.execute = AsyncMock(return_value={})
        executor.cleanup = AsyncMock()

        gw = _build_gateway(executor=executor)
        req = ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
            surface="web",
        )

        result = await gw.execute(req)

        assert result.success is True
        assert result.run_id == "run-test123"
        assert result.mode == NewExecutionMode.CONTAINER_ISOLATED

    @pytest.mark.asyncio
    async def test_execute_fails_without_executor(self):
        gw = _build_gateway()  # no executor registered
        req = ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
            surface="web",
        )
        result = await gw.execute(req)
        assert result.success is False
        assert "No executor registered" in (result.error or "")

    @pytest.mark.asyncio
    async def test_execute_fails_for_missing_work_item(self):
        gw = _build_gateway()
        gw._board.get_work_item.return_value = None

        req = ExecutionRequest(
            work_item_id="task-nonexistent00",
            project_id="proj-1",
        )
        result = await gw.execute(req)
        assert result.success is False
        assert "not found" in (result.error or "")

    @pytest.mark.asyncio
    async def test_execute_fails_for_missing_credentials(self):
        gw = _build_gateway(cred_result=None)
        # Register a dummy executor so mode resolution passes
        executor = MagicMock()
        executor.mode = NewExecutionMode.CONTAINER_ISOLATED
        gw.register_executor(executor)

        req = ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
            surface="web",
        )
        result = await gw.execute(req)
        assert result.success is False
        assert "No available model" in (result.error or "")

    @pytest.mark.asyncio
    async def test_execute_queue_dispatch_enqueues_without_executor(self):
        publisher = _FakeQueuePublisher()
        gw = _build_gateway(
            queue_publisher=publisher,
            dispatch_mode="queue",
        )

        req = ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
            surface="api",
            idempotency_key="idem-1",
        )
        result = await gw.execute(req)

        assert result.success is True
        assert result.message == "Execution queued"
        assert result.queue_job_id == "stream-1"
        assert len(publisher.jobs) == 1
        job = publisher.jobs[0]
        assert job.run_id == "run-test123"
        assert job.job_id == "run-test123"
        assert job.work_item_id == "task-abc123def456"
        assert job.agent_id == "agent-1"
        assert job.cycle_id == "cyc-test123"
        assert job.model_override == "claude-opus-4-6"
        assert job.payload["gateway_request_id"] == req.request_id
        assert job.payload["surface"] == "api"
        assert job.payload["intent"] == "execute"
        assert job.payload["mode"] == "container_isolated"
        assert job.payload["output_target"] == "patch_file"
        assert job.payload["idempotency_key"] == "idem-1"

    @pytest.mark.asyncio
    async def test_execute_queue_dispatch_requires_publisher_before_records(self):
        gw = _build_gateway(dispatch_mode="queue")

        req = ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
            surface="api",
        )
        result = await gw.execute(req)

        assert result.success is False
        assert "no queue publisher" in (result.error or "").lower()
        gw._runs.create_run.assert_not_called()
        gw._cycles.create_cycle.assert_not_called()

    @pytest.mark.asyncio
    async def test_execute_plan_only_creates_artifact_without_dispatch(self):
        gw = _build_gateway(
            dispatch_mode="queue",
        )

        req = ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
            user_id="user-1",
            surface="chat",
            intent=ExecutionIntent.PLAN_ONLY,
            conversation_id="conv-1",
            message_id="msg-1",
        )
        result = await gw.execute(req)

        assert result.success is True
        assert result.intent == ExecutionIntent.PLAN_ONLY
        assert result.message == "Plan artifact created"
        assert result.queue_job_id is None
        assert result.plan_artifact_id
        assert result.plan_artifact_id == req.plan_artifact_id
        assert result.compatibility["status"] == ExecutionState.COMPLETED.value
        assert result.compatibility["phase"] == "completed"
        assert result.compatibility["summary_card"]["type"] == "plan_summary"
        assert (
            result.compatibility["summary_card"]["plan_artifact_id"]
            == result.plan_artifact_id
        )
        assert result.compatibility["plan_artifact"]["conversation_id"] == "conv-1"

        create_run_request = gw._runs.create_run.call_args.args[0]
        assert create_run_request.metadata["run_type"] == "plan_only"
        assert create_run_request.metadata["execution_intent"] == "plan_only"
        policy = create_run_request.metadata["execution_policy"]
        assert policy["write_scope"] == "read_only"
        assert policy["require_workspace"] is False
        assert policy["tool_permissions"]["write_file"] == "deny"
        assert policy["tool_permissions"]["workItems.create"] == "deny"

        final_update = gw._runs.update_run.call_args.args[1]
        assert final_update.status == "COMPLETED"
        assert final_update.progress_pct == 100.0
        assert final_update.metadata["run_type"] == "plan_only"
        assert final_update.metadata["plan_artifact_id"] == result.plan_artifact_id

    @pytest.mark.asyncio
    async def test_execute_review_policy_with_approval_enqueues(self):
        publisher = _FakeQueuePublisher()
        gw = _build_gateway(
            queue_publisher=publisher,
            dispatch_mode="queue",
        )

        req = ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
            surface="api",
            risk_classification="critical",
            approved_by="user-approver",
        )
        result = await gw.execute(req)

        assert result.success is True
        assert result.queue_job_id == "stream-1"
        assert req.requires_approval is True
        assert publisher.jobs[0].payload["requires_approval"] is True
        assert (
            publisher.jobs[0].payload["policy_context"]["policy_evaluation"]["decision"]
            == "review"
        )

    @pytest.mark.asyncio
    async def test_execute_fails_for_non_agent_assignee(self):
        wi = _make_work_item(assignee_type=AssigneeType.USER)
        gw = _build_gateway(work_item=wi)

        executor = MagicMock()
        executor.mode = NewExecutionMode.CONTAINER_ISOLATED
        gw.register_executor(executor)

        req = ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
            surface="web",
        )
        result = await gw.execute(req)
        assert result.success is False
        assert "not an agent" in (result.error or "")

    @pytest.mark.asyncio
    async def test_register_executor(self):

        gw = _build_gateway()
        executor = MagicMock()
        executor.mode = NewExecutionMode.LOCAL_DIRECT
        gw.register_executor(executor)

        assert NewExecutionMode.LOCAL_DIRECT in gw._executors


# =============================================================================
# Mode Executors
# =============================================================================


class TestContainerIsolatedExecutor:

    @pytest.mark.asyncio
    async def test_provision_calls_orchestrator(self):
        from amprealize.mode_executors import ContainerIsolatedExecutor

        orch = AsyncMock()
        orch.provision_workspace.return_value = SimpleNamespace(
            run_id="run-123",
            workspace_path="/workspace",
            container_id="abc123",
        )

        executor = ContainerIsolatedExecutor(orchestrator=orch)
        assert executor.mode == NewExecutionMode.CONTAINER_ISOLATED

        resolved = _make_resolved()
        updated = await executor.provision_workspace(resolved)

        orch.provision_workspace.assert_awaited_once()
        assert updated.workspace_path == "/workspace"
        assert updated.container_id == "abc123"

    @pytest.mark.asyncio
    async def test_cleanup_calls_orchestrator(self):
        from amprealize.mode_executors import ContainerIsolatedExecutor

        orch = AsyncMock()
        executor = ContainerIsolatedExecutor(orchestrator=orch)

        resolved = _make_resolved(workspace_id="run-123")
        await executor.cleanup(resolved)
        orch.cleanup_workspace.assert_awaited_once_with(
            "run-123", retain_on_failure=True,
        )

    @pytest.mark.asyncio
    async def test_cleanup_noop_without_workspace_id(self):
        from amprealize.mode_executors import ContainerIsolatedExecutor

        orch = AsyncMock()
        executor = ContainerIsolatedExecutor(orchestrator=orch)

        resolved = _make_resolved(workspace_id=None)
        await executor.cleanup(resolved)
        orch.cleanup_workspace.assert_not_awaited()


class TestContainerConnectedExecutor:

    @pytest.mark.asyncio
    async def test_provision_requires_workspace_path(self):
        from amprealize.mode_executors import ContainerConnectedExecutor

        orch = AsyncMock()
        executor = ContainerConnectedExecutor(orchestrator=orch)

        resolved = _make_resolved()
        resolved.request.workspace_path = None

        with pytest.raises(ValueError, match="workspace_path"):
            await executor.provision_workspace(resolved)

    @pytest.mark.asyncio
    async def test_provision_with_valid_path(self, tmp_path):
        from amprealize.mode_executors import ContainerConnectedExecutor

        mock_podman = AsyncMock()
        mock_podman.create_container.return_value = "ctr123"

        orch = AsyncMock()
        orch._get_podman.return_value = mock_podman

        executor = ContainerConnectedExecutor(orchestrator=orch)

        resolved = _make_resolved()
        resolved.request.workspace_path = str(tmp_path)

        updated = await executor.provision_workspace(resolved)

        mock_podman.create_container.assert_awaited_once()
        call_kwargs = mock_podman.create_container.call_args
        # Verify the local path is in the volumes dict
        volumes = call_kwargs.kwargs.get("volumes", {})
        assert str(tmp_path) in volumes
        assert updated.container_id == "ctr123"
        assert updated.workspace_path == "/workspace"


class TestLocalDirectExecutor:

    @pytest.mark.asyncio
    async def test_provision_validates_path(self, tmp_path):
        from amprealize.mode_executors import LocalDirectExecutor

        executor = LocalDirectExecutor()
        assert executor.mode == NewExecutionMode.LOCAL_DIRECT

        resolved = _make_resolved()
        resolved.request.workspace_path = str(tmp_path)

        updated = await executor.provision_workspace(resolved)
        assert updated.workspace_path == str(tmp_path.resolve())
        assert updated.container_id is None

    @pytest.mark.asyncio
    async def test_provision_fails_for_missing_path(self):
        from amprealize.mode_executors import LocalDirectExecutor

        executor = LocalDirectExecutor()
        resolved = _make_resolved()
        resolved.request.workspace_path = "/nonexistent/path/xyz"

        with pytest.raises(ValueError, match="does not exist"):
            await executor.provision_workspace(resolved)

    @pytest.mark.asyncio
    async def test_provision_fails_without_path(self):
        from amprealize.mode_executors import LocalDirectExecutor

        executor = LocalDirectExecutor()
        resolved = _make_resolved()
        resolved.request.workspace_path = None

        with pytest.raises(ValueError, match="workspace_path"):
            await executor.provision_workspace(resolved)

    @pytest.mark.asyncio
    async def test_cleanup_is_noop(self):
        from amprealize.mode_executors import LocalDirectExecutor

        executor = LocalDirectExecutor()
        resolved = _make_resolved()
        await executor.cleanup(resolved)  # should not raise


# =============================================================================
# Helpers
# =============================================================================


def _make_resolved(**overrides) -> ResolvedExecution:
    defaults = dict(
        run_id="run-test",
        cycle_id="cyc-test",
        request=ExecutionRequest(
            work_item_id="task-abc123def456",
            project_id="proj-1",
            user_id="user-1",
            org_id="org-1",
            surface="web",
        ),
        mode=NewExecutionMode.CONTAINER_ISOLATED,
        output_target=OutputTarget.PULL_REQUEST,
        source_type=SourceType.GITHUB,
        source_url="owner/repo",
        source_ref="main",
        model_id="claude-sonnet-4-5",
        api_key="sk-test",
        credential_source="platform",
        is_byok=False,
        agent_id="agent-1",
    )
    defaults.update(overrides)
    return ResolvedExecution(**defaults)


# =============================================================================
# Output handler wiring tests (Phase 4 / S3.8 — T3.8.6)
# =============================================================================


class TestGatewayOutputWiring:
    """Tests for the output handler integration in ExecutionGateway."""

    def _make_gateway(self, **kwargs):
        from amprealize.execution_gateway import ExecutionGateway

        defaults = dict(
            board_service=MagicMock(),
            run_service=MagicMock(),
            task_cycle_service=MagicMock(),
            agent_registry=MagicMock(),
            credential_store=MagicMock(),
        )
        defaults.update(kwargs)
        return ExecutionGateway(**defaults)

    def test_init_output_context(self):
        """_init_output_context creates a properly-populated OutputContext."""
        from amprealize.output_handlers import OutputContext

        gw = self._make_gateway()
        resolved = _make_resolved()
        work_item = MagicMock()
        work_item.title = "Fix the bug"

        ctx = gw._init_output_context(resolved, work_item)

        assert isinstance(ctx, OutputContext)
        assert ctx.run_id == "run-test"
        assert ctx.work_item_id == "task-abc123def456"
        assert ctx.work_item_title == "Fix the bug"
        assert ctx.repo == "owner/repo"
        assert ctx.base_branch == "main"
        assert "run-test" in ctx.branch_name
        assert ctx.project_id == "proj-1"
        assert ctx.org_id == "org-1"

    def test_build_output_handler_pr_with_github(self):
        """PR output target produces GitHubPRHandler when github_service exists."""
        from amprealize.output_handlers import GitHubPRHandler

        mock_gh = MagicMock()
        gw = self._make_gateway(github_service=mock_gh)
        resolved = _make_resolved(output_target=OutputTarget.PULL_REQUEST)

        handler = gw._build_output_handler(resolved)
        assert isinstance(handler, GitHubPRHandler)

    def test_build_output_handler_pr_without_github(self):
        """PR output target returns None when no github_service."""
        gw = self._make_gateway()
        resolved = _make_resolved(output_target=OutputTarget.PULL_REQUEST)

        handler = gw._build_output_handler(resolved)
        assert handler is None

    def test_build_output_handler_patch_file(self):
        from amprealize.output_handlers import PatchFileHandler

        gw = self._make_gateway()
        resolved = _make_resolved(output_target=OutputTarget.PATCH_FILE)

        handler = gw._build_output_handler(resolved)
        assert isinstance(handler, PatchFileHandler)

    def test_build_output_handler_local_sync(self):
        from amprealize.output_handlers import LocalSyncHandler

        gw = self._make_gateway()
        resolved = _make_resolved(output_target=OutputTarget.LOCAL_SYNC)

        handler = gw._build_output_handler(resolved)
        assert isinstance(handler, LocalSyncHandler)

    def test_build_output_handler_archive_returns_none(self):
        """ARCHIVE output target has no handler yet — returns None."""
        gw = self._make_gateway()
        resolved = _make_resolved(output_target=OutputTarget.ARCHIVE)

        handler = gw._build_output_handler(resolved)
        assert handler is None

    @pytest.mark.asyncio
    async def test_deliver_output_no_context(self):
        """_deliver_output returns None when no output context."""
        gw = self._make_gateway()
        resolved = _make_resolved()
        resolved.output_context = None

        result = await gw._deliver_output(resolved, MagicMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_deliver_output_no_changes(self):
        """_deliver_output returns None when context has no changes."""
        from amprealize.output_handlers import OutputContext

        gw = self._make_gateway()
        resolved = _make_resolved()
        resolved.output_context = OutputContext(
            run_id="r", work_item_id="w", work_item_title="t",
            repo="o/r", base_branch="main", branch_name="b",
            project_id="p", org_id="o",
        )

        result = await gw._deliver_output(resolved, MagicMock())
        assert result is None

    @pytest.mark.asyncio
    async def test_deliver_output_calls_handler(self):
        """_deliver_output invokes handler.deliver() with the context."""
        from amprealize.output_handlers import OutputContext, OutputStatus

        gw = self._make_gateway()
        resolved = _make_resolved(output_target=OutputTarget.PATCH_FILE)

        ctx = OutputContext(
            run_id="r", work_item_id="w", work_item_title="t",
            repo="o/r", base_branch="main", branch_name="b",
            project_id="p", org_id="o",
        )
        ctx.add_change("test.py", "code\n", "create")
        resolved.output_context = ctx

        result = await gw._deliver_output(resolved, MagicMock())

        assert result is not None
        assert result.status == OutputStatus.SUCCESS
        assert result.handler_type == "patch_file"
        assert result.files_changed == 1

    @pytest.mark.asyncio
    async def test_on_success_includes_output_result(self):
        """_on_success passes output result to run update metadata."""
        from amprealize.output_handlers import OutputResult, OutputStatus

        mock_runs = MagicMock()
        gw = self._make_gateway(run_service=mock_runs)
        resolved = _make_resolved()

        output_result = OutputResult(
            status=OutputStatus.SUCCESS,
            handler_type="github_pr",
            files_changed=5,
            pr_url="https://github.com/o/r/pull/99",
        )

        await gw._on_success(resolved, MagicMock(), output_result=output_result)

        call_args = mock_runs.update_run.call_args
        assert call_args is not None
        progress = call_args[0][1]
        assert progress.metadata is not None
        assert progress.metadata["output"]["pr_url"] == "https://github.com/o/r/pull/99"

    @pytest.mark.asyncio
    async def test_on_success_without_output_result(self):
        """_on_success works fine without output_result (backward compat)."""
        mock_runs = MagicMock()
        gw = self._make_gateway(run_service=mock_runs)
        resolved = _make_resolved()

        await gw._on_success(resolved, MagicMock())

        mock_runs.update_run.assert_called_once()

    def test_resolved_execution_has_output_context_field(self):
        """ResolvedExecution.output_context defaults to None."""
        resolved = _make_resolved()
        assert resolved.output_context is None
