def test_index_exposes_framework_and_active_workspace_roots_separately(
    client, monorepo, monkeypatch,
) -> None:
    framework_root = monorepo.parent / "framework-checkout"
    framework_root.mkdir()
    monkeypatch.setenv("LAB_FRAMEWORK_ROOT", str(framework_root))

    r = client.get("/")

    assert r.status_code == 200
    assert f'window.LAB_MONOREPO_ROOT = "{framework_root.resolve()}"' in r.text
    assert f'window.LAB_WORKSPACE_ROOT = "{monorepo.resolve()}"' in r.text


def test_get_index_empty(client) -> None:
    r = client.get("/api/index")
    assert r.status_code == 200
    body = r.json()
    assert body["projects"] == []
    assert body["tasks"] == []
    assert "generated_at" in body


def test_productivity_view_renders_without_mode_flag(client) -> None:
    r = client.get("/?view=productivity")
    assert r.status_code == 200
    assert '<body class="self-active">' in r.text
    assert "Lab Workbench" in r.text
    assert "window.LAB_MONOREPO_ROOT" in r.text


def test_productivity_is_default_and_workspace_selector_is_retired(client) -> None:
    r = client.get("/")

    assert r.status_code == 200
    assert '<body class="self-active">' in r.text
    assert 'id="workspaceSelect"' not in r.text
    assert 'id="homeLink"' not in r.text


def test_retired_home_and_standalone_views_are_not_shipped(client) -> None:
    r = client.get("/")

    assert r.status_code == 200
    for retired_id in (
        "homeView",
        "codeSearchView",
        "logsView",
        "newProjectModal",
        "fieldPopover",
        "descModal",
        "snoozeModal",
    ):
        assert f'id="{retired_id}"' not in r.text
    assert ">Pinned<" not in r.text
    assert ">Snoozed<" not in r.text
    assert ">Timeline<" not in r.text


def test_frontend_declares_cross_workspace_navigation_surfaces() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    script = (root / "core/src/core/static/js/lab-app.js").read_text()

    assert "function fetchWorkspaceCatalog" in script
    assert "function goToWorkspace(workspaceId" in script
    assert "function showScopedCodeSearch" in script
    assert "function selfShowAdmin" in script
    assert "function workspaceSaveAppearance" in script
    assert "function projectSaveDisplayName" in script
    assert "Name shown in tabs" in script
    assert "_projectDisplayName(project)" in script
    assert "currentProject.path === project.path && currentProject.display_name" in script
    assert "_setProjectDisplayName(projectPath, projectDisplayName)" in script
    assert "if (!currentProject || currentProject.path !== projectPath) return;" in script
    assert "/api/workspaces/use" not in script
    server_bar = script[
        script.index("async function refreshAttrsBar"):
        script.index("// ─── Proxies modal")
    ]
    assert 'data-act="proxies"' in server_bar
    for retired_field in ("priority", "due", "loe", "description", "snooze", "hold"):
        assert retired_field not in server_bar.lower()


def test_get_index_reflects_seeded_projects(client, seed_project) -> None:
    seed_project("alpha")
    seed_project("beta")
    r = client.get("/api/index")
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["projects"]]
    assert ids == ["alpha", "beta"]


def test_get_index_reflects_task_counts(client, seed_project) -> None:
    import json as _json
    pdir = seed_project("alpha")
    (pdir / "tasks.json").write_text(_json.dumps({
        "next_id": 3,
        "tasks": [
            {"id": 1, "title": "t", "status": "todo", "priority": "P1",
             "loe": None, "due": None, "tags": [], "labels": [], "blocker": None,
             "notes_file": None, "created": "2026-04-17", "updated": "2026-04-17", "closed_at": None},
            {"id": 2, "title": "u", "status": "done", "priority": "P1",
             "loe": None, "due": None, "tags": [], "labels": [], "blocker": None,
             "notes_file": None, "created": "2026-04-17", "updated": "2026-04-17",
             "closed_at": "2026-04-17T09:00:00-07:00"},
        ],
    }))
    r = client.get("/api/index")
    p = r.json()["projects"][0]
    assert p["open_task_count"] == 1
    assert p["task_counts"]["done"] == 1
