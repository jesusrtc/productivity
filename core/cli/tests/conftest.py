from __future__ import annotations

import json
import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_vault_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A developer shell that exports LAB_VAULT would otherwise point
    tests at their real vault (it wins over LAB_ROOT in
    find_vault_root). Same guard as core/tests/conftest.py."""
    monkeypatch.delenv("LAB_VAULT", raising=False)
    monkeypatch.delenv("LAB_WORKSPACE", raising=False)
    # Client-global .env settings (notably LAB_ASSISTANT_HOME) must not leak
    # real user paths into isolated tests. Individual parser tests override it.
    monkeypatch.setenv("LAB_ENV_FILE", str(tmp_path / "missing-client.env"))


@pytest.fixture()
def monorepo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Create a minimal monorepo layout under tmp_path and point `LAB_ROOT` at it."""
    root = tmp_path / "productivity"
    (root / "workspaces").mkdir(parents=True)
    (root / "content" / "meetings").mkdir(parents=True)
    (root / "content" / "skills").mkdir()
    # Canonical per-workspace CLAUDE.md target (tests symlink to this).
    (root / "content" / "skills" / "workspace-CLAUDE.md").write_text(
        "# shared workspace CLAUDE.md (test fixture)\n\n"
        "Run `lab workspace status` for current state.\n"
    )
    # git repo marker so find_monorepo_root() works without running git
    (root / ".git").mkdir()
    (root / "CLAUDE.md").write_text("# monorepo test fixture\n")
    monkeypatch.setenv("LAB_VAULT", str(root))
    monkeypatch.setenv("LAB_ROOT", str(root))
    monkeypatch.setenv("LAB_HOME", str(tmp_path / ".lab-home"))
    monkeypatch.chdir(root)
    return root


@pytest.fixture()
def seed_workspace(monorepo: Path):
    """Factory to create a blank workspace under the fixture monorepo."""
    def _create(workspace_id: str = "demo", *, description: str = "") -> Path:
        pdir = monorepo / "workspaces" / workspace_id
        pdir.mkdir(parents=True)
        (pdir / "workspace.json").write_text(json.dumps({
            "id": workspace_id,
            "name": workspace_id,
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


@pytest.fixture(autouse=True)
def _isolated_repository_prefixes(monkeypatch, tmp_path_factory):
    """Examples belong to fixtures, never to the shipped repository defaults."""
    from lab import mp
    config = tmp_path_factory.mktemp("prefix-config") / "repo-prefixes.json"
    config.write_text(json.dumps({
        "sample-charts": "charts", "sample-rules": "rules",
        "sample-service": "service", "sample-guides": "im",
        "document-review": "documents",
    }))
    monkeypatch.setattr(mp, "_CONFIG_FILE", config)
