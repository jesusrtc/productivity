"""Tests for /api/git/* — the dashboard push buttons.

These tests do NOT exercise a real git push. They patch
``subprocess.run`` so the route handler sees a canned
CompletedProcess and asserts on the endpoint's translation of
stdout/stderr/exit-code into HTTP.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["make"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_push_productivity_success(client) -> None:
    with patch("core.routes.git.subprocess.run",
               return_value=_completed(0, stdout="Everything up-to-date")) as run:
        r = client.post("/api/git/push-productivity")
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "Everything up-to-date"
    assert run.call_args.args[0] == ["make", "push-productivity"]


def test_push_productivity_dirty_tree_returns_409(client) -> None:
    with patch("core.routes.git.subprocess.run",
               return_value=_completed(1, stderr="productivity: working tree is dirty. Commit changes before pushing.")):
        r = client.post("/api/git/push-productivity")
    assert r.status_code == 409, r.text
    assert "working tree is dirty" in r.json()["detail"]


def test_sync_content_success(client) -> None:
    with patch("core.routes.git.subprocess.run",
               return_value=_completed(0, stdout="[main abc1234] Sync content 2026-04-29 15:00")) as run:
        r = client.post("/api/git/sync-content")
    assert r.status_code == 200, r.text
    assert "Sync content" in r.json()["message"]
    assert run.call_args.args[0] == ["make", "push-content"]


def test_sync_content_push_failure_returns_409(client) -> None:
    with patch("core.routes.git.subprocess.run",
               return_value=_completed(1, stderr="fatal: no upstream")):
        r = client.post("/api/git/sync-content")
    assert r.status_code == 409, r.text
    assert "no upstream" in r.json()["detail"]


def test_timeout_returns_504(client) -> None:
    with patch("core.routes.git.subprocess.run",
               side_effect=subprocess.TimeoutExpired(cmd=["make"], timeout=30)):
        r = client.post("/api/git/push-productivity")
    assert r.status_code == 504
    assert "timed out" in r.json()["detail"]


def test_update_restart_pulls_main_then_schedules_process_exec(client, monorepo) -> None:
    from core.routes import git as git_route

    with (
        patch.object(git_route, "_RESTART_SCHEDULED", False),
        patch.object(
            git_route,
            "_run_git",
            side_effect=["main", "Updating e9c9234..1a655c1", "1a655c1"],
        ) as run_git,
        patch.object(git_route.paths, "find_framework_root", return_value=monorepo),
        patch.object(git_route, "_schedule_exec_restart") as schedule,
    ):
        response = client.post("/api/git/update-restart")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "status": "restarting",
        "message": "Updating e9c9234..1a655c1",
        "revision": "1a655c1",
        "boot_id": git_route._BOOT_ID,
    }
    assert [call.args[1] for call in run_git.call_args_list] == [
        ["rev-parse", "--abbrev-ref", "HEAD"],
        ["pull", "--rebase", "--autostash", "origin", "main"],
        ["rev-parse", "--short", "HEAD"],
    ]
    schedule.assert_called_once_with(monorepo)


def test_update_restart_requires_main_branch(client) -> None:
    from core.routes import git as git_route

    with (
        patch.object(git_route, "_RESTART_SCHEDULED", False),
        patch.object(git_route, "_run_git", return_value="feature/test"),
        patch.object(git_route, "_schedule_exec_restart") as schedule,
    ):
        response = client.post("/api/git/update-restart")

    assert response.status_code == 409
    assert "main" in response.json()["detail"]
    schedule.assert_not_called()


def test_update_restart_surfaces_pull_failure_and_does_not_restart(client) -> None:
    from core.routes import git as git_route

    with (
        patch.object(git_route, "_RESTART_SCHEDULED", False),
        patch.object(
            git_route,
            "_run_git",
            side_effect=["main", HTTPException(status_code=409, detail="rebase conflict")],
        ),
        patch.object(git_route, "_schedule_exec_restart") as schedule,
    ):
        response = client.post("/api/git/update-restart")

    assert response.status_code == 409
    assert response.json()["detail"] == "rebase conflict"
    schedule.assert_not_called()
    assert git_route._RESTART_SCHEDULED is False


def test_runtime_reports_current_boot_id(client) -> None:
    from core.routes import git as git_route

    response = client.get("/api/git/runtime")

    assert response.status_code == 200
    assert response.json()["boot_id"] == git_route._BOOT_ID
    assert isinstance(response.json()["pid"], int)


def test_exec_restart_replaces_current_process_from_framework_root(monorepo) -> None:
    import sys

    from core.routes import git as git_route

    with (
        patch.object(git_route.os, "chdir") as chdir,
        patch.object(git_route.os, "execv") as execv,
    ):
        git_route._exec_current_process(monorepo)

    chdir.assert_called_once_with(monorepo)
    execv.assert_called_once_with(sys.executable, [sys.executable, "-m", "core"])


def test_make_stop_uses_requested_port_when_workspace_port_file_is_missing(tmp_path) -> None:
    root = Path(__file__).resolve().parents[2]
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    trace = tmp_path / "lsof-args.txt"
    lsof = fake_bin / "lsof"
    lsof.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> "$LAB_LSOF_TRACE"\nexit 1\n')
    lsof.chmod(0o755)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    env = os.environ.copy()
    env.update({
        "LAB_LSOF_TRACE": str(trace),
        "LAB_WORKSPACE": str(workspace),
        "PATH": f"{fake_bin}:{env['PATH']}",
    })

    result = subprocess.run(
        ["make", "-s", "_stop-quiet", "PORT=54321"],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    calls = trace.read_text().splitlines()
    assert len(calls) == 2
    assert all("-iTCP:54321" in call for call in calls)
