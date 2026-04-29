"""Tests for /api/git/* — the dashboard push buttons.

These tests do NOT exercise a real git push. They install a fake ``make``
binary on PATH that echoes a canned response and exits with the requested
status, then assert on the endpoint's translation of make stdout/stderr/
exit-code into HTTP.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest


def _install_fake_make(
    bin_dir: Path,
    *,
    exit_code: int,
    stdout: str = "",
    stderr: str = "",
) -> Path:
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "make"
    body = (
        "#!/usr/bin/env bash\n"
        f'echo -n {stdout!r}\n'
        f'echo -n {stderr!r} >&2\n'
        f"exit {exit_code}\n"
    )
    fake.write_text(body)
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return fake


@pytest.fixture()
def fake_make_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Prepend a tmp dir to PATH so a fake `make` shadows the real one."""
    bin_dir = tmp_path / "fake_bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    return bin_dir


def test_push_productivity_success(client, fake_make_path: Path) -> None:
    _install_fake_make(fake_make_path, exit_code=0, stdout="Everything up-to-date")
    r = client.post("/api/git/push-productivity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert "up-to-date" in body["message"]


def test_push_productivity_dirty_tree_returns_409(client, fake_make_path: Path) -> None:
    _install_fake_make(
        fake_make_path,
        exit_code=1,
        stderr="productivity: working tree is dirty. Commit changes before pushing.",
    )
    r = client.post("/api/git/push-productivity")
    assert r.status_code == 409, r.text
    assert "working tree is dirty" in r.json()["detail"]


def test_sync_content_success(client, fake_make_path: Path) -> None:
    _install_fake_make(
        fake_make_path,
        exit_code=0,
        stdout="[main abc1234] Sync content 2026-04-29 15:00",
    )
    r = client.post("/api/git/sync-content")
    assert r.status_code == 200, r.text
    assert "Sync content" in r.json()["message"]


def test_sync_content_push_failure_returns_409(client, fake_make_path: Path) -> None:
    _install_fake_make(fake_make_path, exit_code=1, stderr="fatal: no upstream")
    r = client.post("/api/git/sync-content")
    assert r.status_code == 409, r.text
    assert "no upstream" in r.json()["detail"]
