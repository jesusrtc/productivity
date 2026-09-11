import json
from types import SimpleNamespace

import pytest

from lab import paths


def _request(root):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(index_cache=SimpleNamespace(root=root)),
        ),
    )


def test_post_workspace_new_creates_on_disk(client, monorepo) -> None:
    r = client.post("/api/workspaces", json={
        "id": "alpha",
        "description": "Alpha description",
        "priority": "P1",
        "tags": ["x", "y"],
        "labels": [],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == "alpha"
    assert body["priority"] == "P1"

    on_disk = json.loads((monorepo / "workspaces" / "alpha" / "workspace.json").read_text())
    assert on_disk["description"] == "Alpha description"
    assert on_disk["tags"] == ["x", "y"]


def test_post_workspace_new_rejects_duplicate(client, seed_workspace) -> None:
    seed_workspace("alpha")
    r = client.post("/api/workspaces", json={"id": "alpha"})
    assert r.status_code == 400
    assert "already exists" in r.json()["detail"].lower()


def test_post_workspace_new_rejects_bad_id(client) -> None:
    r = client.post("/api/workspaces", json={"id": "Bad ID!"})
    assert r.status_code == 400


@pytest.mark.parametrize(("name", "workspace_id"), [
    ("  Charts Vision  ", "charts-vision"),
    ("Investigación", "investigacion"),
    ("研究", "workspace"),
    ("../../My Project", "my-project"),
])
def test_post_workspace_new_needs_only_a_name(client, monorepo, name, workspace_id):
    r = client.post("/api/workspaces", json={"name": name})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == workspace_id
    assert r.json()["name"] == name.strip()
    stored = json.loads((monorepo / "workspaces" / workspace_id / "workspace.json").read_text())
    assert stored["name"] == name.strip()


def test_post_workspace_name_collision_keeps_existing_workspace(client, seed_workspace):
    seed_workspace("charts-vision", description="Keep me")
    r = client.post("/api/workspaces", json={"name": "Charts Vision"})
    assert r.status_code == 200, r.text
    assert r.json()["id"] == "charts-vision-2"
    assert r.json()["name"] == "Charts Vision"
    original = client.get("/api/workspaces/charts-vision")
    assert original.status_code == 200
    assert original.json()["description"] == "Keep me"


@pytest.mark.parametrize("body", [{}, {"name": "   "}])
def test_post_workspace_new_rejects_empty_name(client, body):
    r = client.post("/api/workspaces", json=body)
    assert r.status_code == 400
    assert r.json()["detail"] == "Enter a workspace name"


def test_post_workspace_new_targets_registered_vault_without_switching(
    client, monorepo, tmp_path,
) -> None:
    other = tmp_path / "other"
    (other / "workspaces").mkdir(parents=True)
    (other / "content").mkdir()
    paths.write_vault_registry({
        "active": "main",
        "vaults": [
            {"id": "main", "name": "main", "path": str(monorepo)},
            {"id": "other", "name": "other", "path": str(other)},
        ],
    })

    r = client.post("/api/workspaces", json={"name": "Elsewhere", "vault": "other"})

    assert r.status_code == 200, r.text
    assert (other / "workspaces" / "elsewhere" / "workspace.json").is_file()
    assert not (monorepo / "workspaces" / "elsewhere").exists()
    assert paths.read_vault_registry()["active"] == "main"


def test_post_workspace_new_unknown_vault_is_404(client) -> None:
    r = client.post("/api/workspaces", json={"id": "alpha", "vault": "missing"})
    assert r.status_code == 404


def test_workspace_name_is_a_display_alias_and_id_stays_stable(
    client, monorepo, seed_workspace,
) -> None:
    seed_workspace("remotion-manim")

    r = client.post(
        "/api/workspaces/remotion-manim/field",
        json={"field": "name", "value": "Video Studio"},
    )

    assert r.status_code == 200, r.text
    assert r.json()["id"] == "remotion-manim"
    assert r.json()["name"] == "Video Studio"
    assert (monorepo / "workspaces" / "remotion-manim").is_dir()

    repos = client.get("/api/repos")
    workspace = next(row for row in repos.json() if row["name"] == "remotion-manim")
    assert workspace["display_name"] == "Video Studio"


def test_workspace_name_update_accepts_unregistered_active_vault_id(
    client, monorepo, seed_workspace,
) -> None:
    seed_workspace("remotion-manim")

    r = client.post(
        f"/api/workspaces/remotion-manim/field?vault={monorepo.name}",
        json={"field": "name", "value": "Motion Lab"},
    )

    assert r.status_code == 200, r.text
    assert r.json()["name"] == "Motion Lab"


def test_workspace_name_update_targets_registered_vault_without_switching(
    client, monorepo, tmp_path,
) -> None:
    other = tmp_path / "other"
    (other / "workspaces").mkdir(parents=True)
    (other / "content").mkdir()
    paths.write_vault_registry({
        "active": "main",
        "vaults": [
            {"id": "main", "name": "main", "path": str(monorepo)},
            {"id": "other", "name": "other", "path": str(other)},
        ],
    })
    created = client.post(
        "/api/workspaces",
        json={"id": "remotion-manim", "vault": "other"},
    )
    assert created.status_code == 200, created.text

    r = client.post(
        "/api/workspaces/remotion-manim/field?vault=other",
        json={"field": "name", "value": "Animations"},
    )

    assert r.status_code == 200, r.text
    stored = json.loads((other / "workspaces" / "remotion-manim" / "workspace.json").read_text())
    assert stored["id"] == "remotion-manim"
    assert stored["name"] == "Animations"
    assert paths.read_vault_registry()["active"] == "main"


def test_post_task_new(client, seed_workspace) -> None:
    seed_workspace("alpha")
    r = client.post("/api/tasks", json={
        "workspace_id": "alpha",
        "title": "Draft",
        "priority": "P1",
        "tags": ["review"],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == 1
    assert body["title"] == "Draft"
    assert body["status"] == "todo"


def test_post_self_task_uses_framework_root(tmp_path, monkeypatch) -> None:
    from core.routes import mutation as mutation_routes

    vault = tmp_path / "vault"
    framework = tmp_path / "framework"
    (vault / "content").mkdir(parents=True)
    (framework / "content").mkdir(parents=True)
    seen: dict[str, object] = {}

    def fake_run_lab(args, *, root):
        seen["args"] = args
        seen["root"] = root
        (root / "content" / ".self-tasks.json").write_text(json.dumps({
            "next_id": 2,
            "tasks": [{
                "id": 1,
                "title": "Framework task",
                "status": "todo",
                "priority": "P1",
            }],
        }))

    monkeypatch.setattr(mutation_routes.paths, "find_framework_root", lambda: framework)
    monkeypatch.setattr(mutation_routes, "_run_lab", fake_run_lab)

    body = mutation_routes.NewTask(
        workspace_id="__self__",
        title="Framework task",
        priority="P1",
    )
    created = mutation_routes.create_task(body, _request(vault))

    assert seen["root"] == framework
    assert seen["args"][:5] == ["task", "new", "Framework task", "--workspace", "__self__"]
    assert created["title"] == "Framework task"
    assert not (vault / "content" / ".self-tasks.json").exists()


def test_post_task_status_done(client, seed_workspace) -> None:
    seed_workspace("alpha")
    client.post("/api/tasks", json={"workspace_id": "alpha", "title": "t", "priority": "P2"})
    r = client.post("/api/tasks/alpha/1/status", json={"status": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"
    assert r.json()["closed_at"] is not None


def test_post_task_status_blocked_requires_reason(client, seed_workspace) -> None:
    seed_workspace("alpha")
    client.post("/api/tasks", json={"workspace_id": "alpha", "title": "t", "priority": "P2"})
    r = client.post("/api/tasks/alpha/1/status", json={"status": "blocked"})
    assert r.status_code == 400

    r = client.post("/api/tasks/alpha/1/status", json={"status": "blocked", "reason": "waiting on x"})
    assert r.status_code == 200
    assert r.json()["blocker"] == "waiting on x"


def test_post_task_update_field(client, seed_workspace) -> None:
    seed_workspace("alpha")
    client.post("/api/tasks", json={"workspace_id": "alpha", "title": "t", "priority": "P2"})
    r = client.post("/api/tasks/alpha/1/update", json={"field": "priority", "value": "P0"})
    assert r.status_code == 200
    assert r.json()["priority"] == "P0"


def test_post_pr(client, seed_workspace) -> None:
    seed_workspace("alpha")
    r = client.post("/api/workspaces/alpha/prs", json={
        "url": "https://example/pr/1", "mp": "sample-charts", "title": "t", "status": "open",
    })
    assert r.status_code == 200, r.text
    assert r.json()["prs"][0]["url"] == "https://example/pr/1"


def test_delete_pr(client, seed_workspace) -> None:
    seed_workspace("alpha")
    client.post("/api/workspaces/alpha/prs", json={"url": "https://example/1"})
    client.post("/api/workspaces/alpha/prs", json={"url": "https://example/2"})
    r = client.delete("/api/workspaces/alpha/prs/0")
    assert r.status_code == 200
    assert [p["url"] for p in r.json()["prs"]] == ["https://example/2"]


def test_post_artifact(client, seed_workspace) -> None:
    seed_workspace("alpha")
    r = client.post("/api/workspaces/alpha/artifacts", json={
        "url": "https://docs.google.com/x", "type": "google_doc", "title": "D",
    })
    assert r.status_code == 200
    arts = r.json()["artifacts"]
    assert len(arts) == 1
    assert arts[0]["type"] == "google_doc"


def test_delete_artifact(client, seed_workspace) -> None:
    seed_workspace("alpha")
    client.post("/api/workspaces/alpha/artifacts", json={"url": "https://a"})
    r = client.delete("/api/workspaces/alpha/artifacts/1")
    assert r.status_code == 200
    assert r.json()["artifacts"] == []


# ─── tab_open persistence ────────────────────────────────────────────────


def test_post_tab_open_persists_to_workspace_json(client, monorepo, seed_workspace) -> None:
    seed_workspace("alpha")
    r = client.post("/api/workspaces/alpha/tab", json={"open": True})
    assert r.status_code == 200, r.text
    assert r.json()["tab_open"] is True

    on_disk = json.loads((monorepo / "workspaces" / "alpha" / "workspace.json").read_text())
    assert on_disk["tab_open"] is True


def test_post_tab_close_persists_to_workspace_json(client, monorepo, seed_workspace) -> None:
    seed_workspace("alpha")
    client.post("/api/workspaces/alpha/tab", json={"open": True})
    r = client.post("/api/workspaces/alpha/tab", json={"open": False})
    assert r.status_code == 200, r.text
    assert r.json()["tab_open"] is False

    on_disk = json.loads((monorepo / "workspaces" / "alpha" / "workspace.json").read_text())
    assert on_disk["tab_open"] is False


def test_post_tab_unknown_workspace_returns_404(client) -> None:
    r = client.post("/api/workspaces/nonexistent/tab", json={"open": True})
    assert r.status_code == 404


def test_repos_includes_tab_open_field(client, monorepo, seed_workspace) -> None:
    seed_workspace("alpha")
    seed_workspace("beta")
    client.post("/api/workspaces/alpha/tab", json={"open": True})
    r = client.get("/api/repos")
    assert r.status_code == 200
    by_name = {p["name"]: p for p in r.json() if p.get("is_workspace")}
    assert by_name["alpha"]["tab_open"] is True
    # beta never had tab_open written; defaults to False.
    assert by_name["beta"]["tab_open"] is False
