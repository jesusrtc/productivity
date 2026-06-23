from __future__ import annotations

import json
from pathlib import Path

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
