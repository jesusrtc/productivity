from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from core import fsguard
from core.routes import workspace as workspace_route
from lab import paths


def _seed_workspace(root: Path, project_id: str) -> None:
    (root / "content").mkdir(parents=True, exist_ok=True)
    pdir = root / "projects" / project_id
    pdir.mkdir(parents=True, exist_ok=True)
    (root / "lab.toml").write_text("[workspace]\nname = \"test\"\n", encoding="utf-8")
    (pdir / "project.json").write_text(json.dumps({
        "id": project_id,
        "name": project_id,
        "description": "",
        "status": "active",
        "tags": [],
        "labels": [],
        "priority": None,
        "loe": None,
        "due": None,
        "created": "2026-04-17",
        "updated": "2026-04-17",
        "worktrees": [],
        "prs": [],
        "artifacts": [],
        "pinned": [],
    }, indent=2), encoding="utf-8")
    (pdir / "tasks.json").write_text(json.dumps({"next_id": 1, "tasks": []}), encoding="utf-8")


def test_workspaces_list_includes_current(client, monorepo: Path) -> None:
    paths.register_workspace(monorepo, name="Main", active=True)

    r = client.get("/api/workspaces")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["current"]["path"] == str(monorepo.resolve())
    assert body["workspaces"][0]["active"] is True


def test_workspace_switch_replaces_active_index(client, monorepo: Path, tmp_path: Path) -> None:
    _seed_workspace(monorepo, "alpha")
    other = tmp_path / "other"
    _seed_workspace(other, "beta")
    paths.register_workspace(monorepo, name="Main", active=True)
    paths.register_workspace(other, name="Other", active=False)

    r = client.post("/api/workspaces/use", json={"id": "other"})

    assert r.status_code == 200, r.text
    assert r.json()["current"]["path"] == str(other.resolve())
    assert client.get("/api/index").json()["projects"][0]["id"] == "beta"
    assert client.app.state.index_cache.root == other.resolve()
    assert paths.active_workspace() == other.resolve()
    assert not paths.port_file(monorepo).exists()
    assert paths.port_file(other).exists()


# ─── /api/workspaces/projects ───────────────────────────────────────────────


def test_workspace_projects_lists_ids_per_workspace(client, monorepo: Path, tmp_path: Path) -> None:
    _seed_workspace(monorepo, "alpha")
    other = tmp_path / "other"
    _seed_workspace(other, "beta")
    (other / "projects" / "gamma").mkdir(parents=True)
    paths.register_workspace(monorepo, name="Main", active=True)
    paths.register_workspace(other, name="Other", active=False)

    r = client.get("/api/workspaces/projects")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] == "main"
    rows = {w["id"]: w for w in body["workspaces"]}
    assert rows["main"]["unavailable"] is False
    assert rows["main"]["projects"] == ["alpha"]
    assert rows["other"]["unavailable"] is False
    assert sorted(rows["other"]["projects"]) == ["beta", "gamma"]


def test_workspace_projects_marks_stalled_workspace_unavailable_without_failing_others(
    client, monorepo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single stalled/wedged workspace volume must not blank the whole
    dashboard: its entry gets `unavailable: true` (empty `projects`), but
    every other registered workspace still lists normally."""
    _seed_workspace(monorepo, "alpha")
    dead = tmp_path / "dead-ssd"
    _seed_workspace(dead, "beta")
    paths.register_workspace(monorepo, name="Main", active=True)
    paths.register_workspace(dead, name="Dead", active=False)

    dead_resolved = dead.resolve()
    real_guarded = fsguard.guarded

    def _fake_guarded(root: Path, fn, *args, **kwargs):
        if Path(root).resolve() == dead_resolved:
            raise HTTPException(
                status_code=503,
                detail=f"resource is not available for workspace {fsguard.workspace_name(root)}",
            )
        return real_guarded(root, fn, *args, **kwargs)

    monkeypatch.setattr(workspace_route.fsguard, "guarded", _fake_guarded)

    r = client.get("/api/workspaces/projects")

    assert r.status_code == 200, r.text
    body = r.json()
    rows = {w["id"]: w for w in body["workspaces"]}
    assert rows["main"]["unavailable"] is False
    assert rows["main"]["projects"] == ["alpha"]
    assert rows["dead"]["unavailable"] is True
    assert rows["dead"]["projects"] == []
    assert rows["dead"]["detail"] == "resource is not available for workspace Dead"
