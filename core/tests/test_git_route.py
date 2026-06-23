"""Tests for /api/git/* — the dashboard push buttons.

These tests do NOT exercise a real git push. They patch
``subprocess.run`` so the route handler sees a canned
CompletedProcess and asserts on the endpoint's translation of
stdout/stderr/exit-code into HTTP.
"""
from __future__ import annotations

import subprocess
from unittest.mock import patch


def _completed(returncode: int, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=["make"], returncode=returncode, stdout=stdout, stderr=stderr)


def test_push_productivity_hidden_without_dev_mode(client) -> None:
    r = client.post("/api/git/push-productivity")
    assert r.status_code == 404
    assert "dev mode" in r.json()["detail"]


def test_push_productivity_success(client, monkeypatch) -> None:
    monkeypatch.setenv("LAB_DEV_MODE", "1")
    with patch("core.routes.git.subprocess.run",
               return_value=_completed(0, stdout="Everything up-to-date")) as run:
        r = client.post("/api/git/push-productivity")
    assert r.status_code == 200, r.text
    assert r.json()["message"] == "Everything up-to-date"
    assert run.call_args.args[0] == ["make", "push-productivity"]


def test_push_productivity_dirty_tree_returns_409(client, monkeypatch) -> None:
    monkeypatch.setenv("LAB_DEV_MODE", "1")
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


def test_timeout_returns_504(client, monkeypatch) -> None:
    monkeypatch.setenv("LAB_DEV_MODE", "1")
    with patch("core.routes.git.subprocess.run",
               side_effect=subprocess.TimeoutExpired(cmd=["make"], timeout=30)):
        r = client.post("/api/git/push-productivity")
    assert r.status_code == 504
    assert "timed out" in r.json()["detail"]
