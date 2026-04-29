"""Tests for /api/git/* — the dashboard push buttons.

These tests do NOT exercise a real git push. They install a fake
``scripts/push.sh`` under the fixture monorepo that echoes a canned
response and exits with the requested status, then assert on the
endpoint's translation of script stdout/stderr/exit-code into HTTP.
"""
from __future__ import annotations

import os
import stat
from pathlib import Path


def _install_fake_push(monorepo: Path, *, exit_code: int, stdout: str = "", stderr: str = "") -> Path:
    scripts = monorepo / "scripts"
    scripts.mkdir(exist_ok=True)
    script = scripts / "push.sh"
    # The script runs in any subdirectory; we only care about the arg.
    body = (
        "#!/usr/bin/env bash\n"
        f'echo -n {stdout!r}\n'
        f'echo -n {stderr!r} >&2\n'
        f"exit {exit_code}\n"
    )
    script.write_text(body)
    script.chmod(script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return script


def test_push_productivity_success(client, monorepo: Path) -> None:
    _install_fake_push(monorepo, exit_code=0, stdout="productivity: up to date")
    r = client.post("/api/git/push-productivity")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "ok"
    assert "up to date" in body["message"]


def test_push_productivity_dirty_tree_returns_409(client, monorepo: Path) -> None:
    _install_fake_push(
        monorepo,
        exit_code=1,
        stderr="productivity: working tree is dirty. Commit changes before pushing.",
    )
    r = client.post("/api/git/push-productivity")
    assert r.status_code == 409, r.text
    assert "working tree is dirty" in r.json()["detail"]


def test_sync_content_success(client, monorepo: Path) -> None:
    _install_fake_push(monorepo, exit_code=0, stdout="content: committed abc1234 and pushed")
    r = client.post("/api/git/sync-content")
    assert r.status_code == 200, r.text
    assert "committed abc1234" in r.json()["message"]


def test_sync_content_push_failure_returns_409(client, monorepo: Path) -> None:
    _install_fake_push(monorepo, exit_code=1, stderr="content: push failed\nfatal: no upstream")
    r = client.post("/api/git/sync-content")
    assert r.status_code == 409, r.text
    assert "push failed" in r.json()["detail"]


def test_missing_script_returns_500(client, monorepo: Path) -> None:
    # Fixture monorepo has no scripts/ — endpoint should report cleanly.
    if (monorepo / "scripts" / "push.sh").exists():
        (monorepo / "scripts" / "push.sh").unlink()
    r = client.post("/api/git/push-productivity")
    assert r.status_code == 500
    assert "push script missing" in r.json()["detail"]
