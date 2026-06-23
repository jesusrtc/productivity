from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


@pytest.fixture()
def monorepo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a minimal monorepo layout under tmp_path and point `LAB_ROOT` at it."""
    root = tmp_path / "productivity"
    (root / "projects").mkdir(parents=True)
    (root / "content" / "meetings").mkdir(parents=True)
    (root / "content" / "skills").mkdir()
    # Canonical per-project CLAUDE.md target (tests symlink to this).
    (root / "content" / "skills" / "project-CLAUDE.md").write_text(
        "# shared project CLAUDE.md (test fixture)\n\n"
        "Run `lab project status` for current state.\n"
    )
    # git repo marker so find_monorepo_root() works without running git
    (root / ".git").mkdir()
    (root / "CLAUDE.md").write_text("# monorepo test fixture\n")
    monkeypatch.setenv("LAB_ROOT", str(root))
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-home"))
    monkeypatch.chdir(root)
    return root


@pytest.fixture()
def seed_project(monorepo: Path):
    """Factory to create a blank project under the fixture monorepo."""
    def _create(project_id: str = "demo", *, description: str = "") -> Path:
        pdir = monorepo / "projects" / project_id
        pdir.mkdir(parents=True)
        (pdir / "project.json").write_text(json.dumps({
            "id": project_id,
            "name": project_id,
            "description": description,
            "status": "active",
            "tags": [],
            "labels": [],
            "priority": None,
            "loe": None,
            "due": None,
            "created": "2026-04-16",
            "updated": "2026-04-16",
            "worktrees": [],
            "prs": [],
            "artifacts": [],
            "pinned": [],
        }, indent=2))
        (pdir / "tasks.json").write_text(json.dumps({"next_id": 1, "tasks": []}, indent=2))
        return pdir
    return _create
