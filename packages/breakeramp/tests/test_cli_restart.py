"""Tests for BreakerAmp restart CLI (enterprise: run_id + --service / -s)."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner

from breakeramp import cli


class _FakeService:
    def __init__(self, environments_dir: Path) -> None:
        self.environments_dir = environments_dir


def _write_environment(
    path: Path,
    run_id: str,
    outputs: dict,
    phase: str = "APPLIED",
    environment: str = "cloud-dev",
) -> Path:
    env_path = path / f"{run_id}.json"
    env_path.write_text(
        json.dumps(
            {
                "amp_run_id": run_id,
                "environment": environment,
                "phase": phase,
                "blueprint_id": environment,
                "runtime": {},
                "blueprint_name": "cloud-dev",
                "environment_outputs": outputs,
            }
        )
    )
    return env_path


def test_restart_service_flag_restarts_container(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environments_dir = tmp_path / "environments"
    environments_dir.mkdir()
    _write_environment(
        environments_dir,
        "amp-run-123",
        {
            "redis": {"container_id": "redis-container"},
            "amprealize-api": {"container_id": "api-container"},
            "web-console": {"container_id": "web-container"},
        },
    )

    calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(cli, "get_service", lambda: _FakeService(environments_dir))
    monkeypatch.setattr("subprocess.run", fake_run)

    result = CliRunner().invoke(
        cli.app,
        ["restart", "--service", "amprealize-api"],
    )

    assert result.exit_code == 0
    assert "Restarted 1 service" in result.output
    assert "amprealize-api" in result.output
    assert ["podman", "container", "exists", "api-container"] in calls
    assert ["podman", "start", "api-container"] in calls
    assert ["podman", "start", "redis-container"] not in calls


def test_restart_service_short_flag_aliases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environments_dir = tmp_path / "environments"
    environments_dir.mkdir()
    _write_environment(
        environments_dir,
        "amp-run-123",
        {"amprealize-api": {"container_id": "api-container"}},
    )

    calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(cli, "get_service", lambda: _FakeService(environments_dir))
    monkeypatch.setattr("subprocess.run", fake_run)

    result = CliRunner().invoke(cli.app, ["restart", "-s", "amprealize-api"])

    assert result.exit_code == 0
    assert ["podman", "start", "api-container"] in calls


def test_restart_unknown_service_reports_nothing_to_restart(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enterprise: unknown --service yields empty targets and exits 0 (unlike OSS, which exits 1)."""
    environments_dir = tmp_path / "environments"
    environments_dir.mkdir()
    _write_environment(
        environments_dir,
        "amp-run-123",
        {
            "gateway": {"container_id": "gateway-container"},
            "whiteboard-sync": {"container_id": "whiteboard-container"},
        },
    )

    monkeypatch.setattr(cli, "get_service", lambda: _FakeService(environments_dir))

    result = CliRunner().invoke(cli.app, ["restart", "--service", "amprealize-api"])

    assert result.exit_code == 0
    assert "not found" in result.output.lower()
    assert "nothing to restart" in result.output.lower()


def test_restart_explicit_run_id_selects_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environments_dir = tmp_path / "environments"
    environments_dir.mkdir()
    _write_environment(
        environments_dir,
        "amp-dev-run",
        {"amprealize-api": {"container_id": "dev-api-container"}},
        environment="dev",
    )
    _write_environment(
        environments_dir,
        "amp-test-run",
        {"amprealize-api": {"container_id": "test-api-container"}},
        environment="test",
    )

    calls: list[list[str]] = []

    def fake_run(args: list[str], **kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(cli, "get_service", lambda: _FakeService(environments_dir))
    monkeypatch.setattr("subprocess.run", fake_run)

    result = CliRunner().invoke(
        cli.app,
        ["restart", "amp-test-run", "--service", "amprealize-api"],
    )

    assert result.exit_code == 0
    assert ["podman", "container", "exists", "test-api-container"] in calls
    assert ["podman", "start", "test-api-container"] in calls
    assert ["podman", "start", "dev-api-container"] not in calls


def test_restart_wait_invokes_stack_poll(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environments_dir = tmp_path / "environments"
    environments_dir.mkdir()
    _write_environment(
        environments_dir,
        "amp-run-123",
        {
            "amprealize-api": {"container_id": "api-container"},
        },
    )

    monkeypatch.setattr(cli, "get_service", lambda: _FakeService(environments_dir))
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: SimpleNamespace(returncode=0, stderr="", stdout=""),
    )

    calls: list[dict] = []

    def fake_wait(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "attempts": 1, "elapsed_s": 0.1, "last_error": None}

    monkeypatch.setattr(cli, "_run_stack_wait_poll", fake_wait)

    result = CliRunner().invoke(
        cli.app,
        ["restart", "--service", "amprealize-api", "--wait"],
    )

    assert result.exit_code == 0
    assert any(c.get("strict") is False for c in calls)
    assert "Stack healthy" in result.output or "✓ Stack healthy" in result.output


def test_wait_health_invokes_stack_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def fake_wait(**kwargs):
        calls.append(kwargs)
        return {"ok": True, "attempts": 1, "elapsed_s": 0.05, "last_error": None}

    monkeypatch.setattr(cli, "_run_stack_wait_poll", fake_wait)

    result = CliRunner().invoke(cli.app, ["wait-health"])

    assert result.exit_code == 0
    assert calls and calls[0].get("strict") is False
    assert "Stack healthy" in result.output or "✓ Stack healthy" in result.output
