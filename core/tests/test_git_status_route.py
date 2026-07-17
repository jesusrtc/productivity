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


def test_git_status_allows_registered_repo_outside_workspace(
    client, monorepo: Path, tmp_path: Path, monkeypatch
) -> None:
    """Pinned tabs/views live outside the active workspace; anything the
    app's own repo registry lists must pass containment."""
    outside = tmp_path / "pinned-checkout"
    outside.mkdir()

    from core.routes import diff as diff_route

    monkeypatch.setattr(
        diff_route,
        "get_registered_repos",
        lambda root: [{"name": "pinned", "is_project": False,
                       "path": str(outside), "repos": [str(outside)]}],
    )

    r = client.get("/api/git-status", params={"repo": str(outside)})

    assert r.status_code == 200, r.text
    assert r.json() == {"files": {}, "ignored": []}


def test_git_status_allows_framework_root(client, monorepo: Path) -> None:
    """The Productivity self-view is rooted at the framework checkout, which
    lives outside the active workspace."""
    from lab import paths as lab_paths

    r = client.get(
        "/api/git-status",
        params={"repo": str(lab_paths.find_framework_root())},
    )

    assert r.status_code == 200, r.text
