from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(cwd), *args],
        check=True, capture_output=True, text=True, timeout=10,
    )


@pytest.fixture()
def git_workspace(monorepo: Path) -> Path:
    """Turn the fixture monorepo into a real git repo with one modified and
    one untracked file under a project."""
    if shutil.which("git") is None:
        pytest.skip("git not available")
    pdir = monorepo / "projects" / "demo" / "docs"
    pdir.mkdir(parents=True)
    (pdir / "readme.md").write_text("hello\n", encoding="utf-8")
    # conftest pre-creates an empty .git marker dir; init needs it gone
    shutil.rmtree(monorepo / ".git", ignore_errors=True)
    _git(monorepo, "init", "-q")
    _git(monorepo, "add", "-A")
    _git(
        monorepo,
        "-c", "user.email=t@t", "-c", "user.name=t",
        "commit", "-qm", "init",
    )
    (pdir / "readme.md").write_text("hello CHANGED\n", encoding="utf-8")
    (pdir / "untracked.md").write_text("new\n", encoding="utf-8")
    return monorepo


def test_git_status_reports_modified_and_untracked(client, git_workspace: Path) -> None:
    r = client.get(
        "/api/git-status",
        params={"repo": str(git_workspace / "projects" / "demo")},
    )

    assert r.status_code == 200, r.text
    files = r.json()["files"]
    assert files.get("docs/readme.md") == "M"
    assert files.get("docs/untracked.md") == "U"


def test_git_status_accepts_workspace_relative_path(client, git_workspace: Path) -> None:
    r = client.get("/api/git-status", params={"repo": "projects/demo"})

    assert r.status_code == 200, r.text
    assert r.json()["files"].get("docs/readme.md") == "M"


def test_git_status_non_repo_dir_is_empty(client, monorepo: Path) -> None:
    r = client.get("/api/git-status", params={"repo": "content"})

    assert r.status_code == 200, r.text
    assert r.json() == {"files": {}, "ignored": []}


def test_git_status_rejects_escape_outside_workspace(client, monorepo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    outside.mkdir()

    for repo in (str(outside), "../", "projects/../.."):
        r = client.get("/api/git-status", params={"repo": repo})
        assert r.status_code == 400, f"{repo!r}: {r.status_code} {r.text}"
