from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from core import fsguard
from core.routes import vault as vault_route
from lab import paths


def _seed_vault(root: Path, workspace_id: str) -> None:
    (root / "content").mkdir(parents=True, exist_ok=True)
    pdir = root / "workspaces" / workspace_id
    pdir.mkdir(parents=True, exist_ok=True)
    (root / "lab.toml").write_text("[vault]\nname = \"test\"\n", encoding="utf-8")
    (pdir / "workspace.json").write_text(json.dumps({
        "id": workspace_id,
        "name": workspace_id,
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


def test_vaults_list_includes_current(client, monorepo: Path) -> None:
    paths.register_vault(monorepo, name="Main", active=True)

    r = client.get("/api/vaults")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["current"]["path"] == str(monorepo.resolve())
    assert body["vaults"][0]["active"] is True


def test_vault_switch_replaces_active_index(client, monorepo: Path, tmp_path: Path) -> None:
    _seed_vault(monorepo, "alpha")
    other = tmp_path / "other"
    _seed_vault(other, "beta")
    paths.register_vault(monorepo, name="Main", active=True)
    paths.register_vault(other, name="Other", active=False)

    r = client.post("/api/vaults/use", json={"id": "other"})

    assert r.status_code == 200, r.text
    assert r.json()["current"]["path"] == str(other.resolve())
    assert client.get("/api/index").json()["workspaces"][0]["id"] == "beta"
    assert client.app.state.index_cache.root == other.resolve()
    assert paths.active_vault() == other.resolve()
    assert not paths.port_file(monorepo).exists()
    assert paths.port_file(other).exists()


def test_vault_switch_refreshes_vault_root_in_cached_index_shell(
    client, monorepo: Path, tmp_path: Path,
) -> None:
    _seed_vault(monorepo, "alpha")
    other = tmp_path / "other"
    _seed_vault(other, "beta")
    paths.register_vault(monorepo, name="Main", active=True)
    paths.register_vault(other, name="Other", active=False)

    first = client.get("/")
    assert first.status_code == 200
    assert f'window.LAB_VAULT_ROOT = "{monorepo.resolve()}"' in first.text

    switched = client.post("/api/vaults/use", json={"id": "other"})
    assert switched.status_code == 200, switched.text

    reloaded = client.get("/")
    assert reloaded.status_code == 200
    assert f'window.LAB_VAULT_ROOT = "{other.resolve()}"' in reloaded.text
    assert f'window.LAB_VAULT_ROOT = "{monorepo.resolve()}"' not in reloaded.text


# ─── /api/vaults/workspaces ───────────────────────────────────────────────


def test_vault_workspaces_lists_ids_per_vault(client, monorepo: Path, tmp_path: Path) -> None:
    _seed_vault(monorepo, "alpha")
    other = tmp_path / "other"
    _seed_vault(other, "beta")
    (other / "workspaces" / "gamma").mkdir(parents=True)
    paths.register_vault(monorepo, name="Main", active=True)
    paths.register_vault(other, name="Other", active=False)

    r = client.get("/api/vaults/workspaces")

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["active"] == "main"
    rows = {w["id"]: w for w in body["vaults"]}
    assert rows["main"]["unavailable"] is False
    assert rows["main"]["workspaces"] == ["alpha"]
    assert rows["main"]["workspace_rows"][0]["path"] == str(monorepo / "workspaces" / "alpha")
    assert rows["main"]["workspace_rows"][0]["vault"] == "main"
    assert rows["main"]["color"].startswith("#")
    assert rows["other"]["unavailable"] is False
    assert sorted(rows["other"]["workspaces"]) == ["beta", "gamma"]


def test_vault_appearance_is_vault_scoped(
    client, monorepo: Path, tmp_path: Path,
) -> None:
    _seed_vault(monorepo, "alpha")
    other = tmp_path / "other"
    _seed_vault(other, "beta")
    paths.register_vault(monorepo, name="Main", active=True)
    paths.register_vault(other, name="Other", active=False)

    updated = client.patch(
        "/api/vaults/other/appearance",
        json={"name": "Research", "color": "#a371f7"},
    )

    assert updated.status_code == 200, updated.text
    assert updated.json()["name"] == "Research"
    listing = client.get("/api/vaults/workspaces").json()
    rows = {w["id"]: w for w in listing["vaults"]}
    assert rows["other"]["name"] == "Research"
    assert rows["other"]["color"] == "#a371f7"
    assert rows["main"]["name"] == "Main"
    assert client.app.state.index_cache.root == monorepo.resolve()


def test_vault_config_can_target_non_active_vault(
    client, monorepo: Path, tmp_path: Path,
) -> None:
    _seed_vault(monorepo, "alpha")
    other = tmp_path / "other"
    _seed_vault(other, "beta")
    paths.register_vault(monorepo, name="Main", active=True)
    paths.register_vault(other, name="Other", active=False)
    (other / "vault.json").write_text(json.dumps({
        "version": 1,
        "name": "Other Config",
    }), encoding="utf-8")

    fetched = client.get("/api/vault/config?vault=other")

    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["root"] == str(other.resolve())
    assert fetched.json()["config"]["name"] == "Other Config"


def test_vault_workspaces_marks_stalled_vault_unavailable_without_failing_others(
    client, monorepo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single stalled/wedged vault volume must not blank the whole
    dashboard: its entry gets `unavailable: true` (empty `workspaces`), but
    every other registered vault still lists normally."""
    _seed_vault(monorepo, "alpha")
    dead = tmp_path / "dead-ssd"
    _seed_vault(dead, "beta")
    paths.register_vault(monorepo, name="Main", active=True)
    paths.register_vault(dead, name="Dead", active=False)

    dead_resolved = dead.resolve()
    real_guarded = fsguard.guarded

    def _fake_guarded(root: Path, fn, *args, **kwargs):
        if Path(root).resolve() == dead_resolved:
            raise HTTPException(
                status_code=503,
                detail=f"resource is not available for vault {fsguard.vault_name(root)}",
            )
        return real_guarded(root, fn, *args, **kwargs)

    monkeypatch.setattr(vault_route.fsguard, "guarded", _fake_guarded)

    r = client.get("/api/vaults/workspaces")

    assert r.status_code == 200, r.text
    body = r.json()
    rows = {w["id"]: w for w in body["vaults"]}
    assert rows["main"]["unavailable"] is False
    assert rows["main"]["workspaces"] == ["alpha"]
    assert rows["dead"]["unavailable"] is True
    assert rows["dead"]["workspaces"] == []
    assert rows["dead"]["detail"] == "resource is not available for vault Dead"
