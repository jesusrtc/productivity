from __future__ import annotations

import json
import stat
from pathlib import Path

from fastapi.testclient import TestClient

from core import auth
from lab import paths


def _workspace(root: Path, project_id: str) -> None:
    (root / "content").mkdir(parents=True, exist_ok=True)
    (root / "projects" / project_id).mkdir(parents=True, exist_ok=True)
    (root / "lab.toml").write_text('[workspace]\nname = "test"\n', encoding="utf-8")


def _login(client, username: str, password: str):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _create_user(
    client, username: str, password: str, *, workspaces: list[str] | None = None,
):
    return client.post("/api/admin/users", json={
        "username": username,
        "name": username.title(),
        "role": "user",
        "password": password,
        "workspaces": workspaces or [],
    })


def test_login_is_required_and_seed_passwords_are_sha256(client) -> None:
    client.post("/api/auth/logout")

    page = client.get("/", follow_redirects=False)
    api = client.get("/api/workspaces")

    assert page.status_code == 303
    assert page.headers["location"].startswith("/login?next=")
    assert api.status_code == 401
    store = json.loads(auth.auth_file().read_text(encoding="utf-8"))
    users = {row["username"]: row for row in store["users"]}
    assert list(users) == ["admin"]
    assert users["admin"]["role"] == "admin"
    assert users["admin"]["password_sha256"] == auth.password_sha256("admin")
    assert "password" not in users["admin"]
    assert _login(client, "jesus", "jesus").status_code == 401


def test_local_cli_bearer_is_secret_endpoint_scoped_and_loopback_only(
    monorepo: Path,
) -> None:
    from core.main import create_app

    app = create_app()
    with TestClient(app, client=("127.0.0.1", 50000)) as local_client:
        token_path = paths.local_cli_token_file()
        token = paths.read_local_cli_token()
        assert token is not None
        assert stat.S_IMODE(token_path.stat().st_mode) == 0o600
        headers = {"Authorization": f"Bearer {token}"}

        allowed = local_client.get(
            "/api/nb/session",
            params={"path": "projects/demo/analysis.ipynb"},
            headers=headers,
        )
        denied_elsewhere = local_client.get("/api/projects", headers=headers)
        denied_bad_token = local_client.get(
            "/api/nb/session",
            params={"path": "projects/demo/analysis.ipynb"},
            headers={"Authorization": "Bearer wrong-token-value-that-is-long-enough"},
        )
        denied_legacy_header = local_client.get(
            "/api/nb/session",
            params={"path": "projects/demo/analysis.ipynb"},
            headers={"X-Lab-Local-Automation": "1"},
        )

    with TestClient(app, client=("10.0.0.8", 50000)) as remote_client:
        denied_remote = remote_client.get(
            "/api/nb/session",
            params={"path": "projects/demo/analysis.ipynb"},
            headers=headers,
        )

    assert allowed.status_code == 200, allowed.text
    assert denied_elsewhere.status_code == 401
    assert denied_bad_token.status_code == 401
    assert denied_legacy_header.status_code == 401
    assert denied_remote.status_code == 401


def test_local_cli_bearer_preserves_requested_workspace_scope(
    monorepo: Path, tmp_path: Path,
) -> None:
    from core.main import create_app

    _workspace(monorepo, "demo")
    paths.register_workspace(monorepo, name="Main", active=True)
    other = tmp_path / "other"
    _workspace(other, "demo")
    (other / "projects" / "demo" / "runtime.json").write_text(
        json.dumps({"mode": "local"}), encoding="utf-8",
    )
    notebook = other / "projects" / "demo" / "analysis.ipynb"
    notebook.write_text(json.dumps({
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [{
            "id": "cell-one",
            "cell_type": "code",
            "metadata": {},
            "source": ["print(1)"],
            "execution_count": None,
            "outputs": [],
        }],
    }), encoding="utf-8")
    paths.register_workspace(other, name="Other", active=False)

    app = create_app()
    with TestClient(app, client=("127.0.0.1", 50000)) as local_client:
        token = paths.read_local_cli_token()
        assert token is not None
        headers = {"Authorization": f"Bearer {token}"}
        selected = local_client.get(
            "/api/nb/session",
            params={
                "path": "projects/demo/analysis.ipynb",
                "workspace": "other",
            },
            headers=headers,
        )
        deleted = local_client.post(
            "/api/nb/cell/delete",
            json={
                "path": "projects/demo/analysis.ipynb",
                "workspace": "other",
                "cell_id": "cell-one",
            },
            headers=headers,
        )
        unknown = local_client.get(
            "/api/nb/session",
            params={
                "path": "projects/demo/analysis.ipynb",
                "workspace": "missing",
            },
            headers=headers,
        )

    assert selected.status_code == 200, selected.text
    assert selected.json()["provider"] == "local"
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["remaining_cells"] == 0
    assert unknown.status_code == 404


def test_version_one_store_is_replaced_by_the_builtin_admin(client) -> None:
    auth.auth_file().write_text(json.dumps({
        "version": 1,
        "secret": "legacy-secret",
        "users": [
            {"username": "jesus", "name": "Jesus", "role": "admin", "password_sha256": "old", "workspaces": [], "disabled": False},
            {"username": "cesar", "name": "Cesar", "role": "user", "password_sha256": "old", "workspaces": [], "disabled": False},
        ],
    }), encoding="utf-8")

    store = auth.load_store()

    assert store["version"] == auth.STORE_VERSION
    assert [row["username"] for row in store["users"]] == ["admin"]
    assert auth.authenticate("admin", "admin") is not None


def test_builtin_admin_is_fixed(client) -> None:
    response = client.patch("/api/admin/users/admin", json={"password": "changed"})

    assert response.status_code == 400
    assert auth.authenticate("admin", "admin") is not None


def test_admin_assigns_one_workspace_and_user_cannot_see_the_other(
    client, monorepo: Path, tmp_path: Path,
) -> None:
    _workspace(monorepo, "alpha")
    other = tmp_path / "other"
    _workspace(other, "beta")
    paths.register_workspace(monorepo, name="Main", active=True)
    paths.register_workspace(other, name="Other", active=False)

    assigned = _create_user(client, "cesar", "cesar", workspaces=["main"])
    assert assigned.status_code == 200, assigned.text
    client.post("/api/auth/logout")
    assert _login(client, "Cesar", "cesar").status_code == 200

    listing = client.get("/api/workspaces/projects")
    denied = client.get("/api/workspace/config", params={"workspace": "other"})
    edited = client.patch(
        "/api/workspaces/main/appearance",
        json={"name": "Cesar workspace", "color": "#3fb950"},
    )

    assert listing.status_code == 200, listing.text
    assert [row["id"] for row in listing.json()["workspaces"]] == ["main"]
    assert denied.status_code == 404
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "Cesar workspace"


def test_project_routes_use_the_workspace_selected_by_the_page(
    client, monorepo: Path, tmp_path: Path,
) -> None:
    _workspace(monorepo, "shared")
    other = tmp_path / "other"
    _workspace(other, "shared")
    (monorepo / "projects" / "shared" / "project.json").write_text(
        json.dumps({"id": "shared", "name": "Main copy"}), encoding="utf-8",
    )
    (other / "projects" / "shared" / "project.json").write_text(
        json.dumps({"id": "shared", "name": "Other copy"}), encoding="utf-8",
    )
    paths.register_workspace(monorepo, name="Main", active=True)
    paths.register_workspace(other, name="Other", active=False)
    assert _create_user(
        client, "cesar", "cesar", workspaces=["main", "other"],
    ).status_code == 200
    client.post("/api/auth/logout")
    assert _login(client, "cesar", "cesar").status_code == 200

    response = client.get(
        "/api/projects/shared",
        headers={"referer": f"http://testserver/?project={other / 'projects' / 'shared'}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Other copy"


def test_user_terminal_access_is_workspace_scoped_and_home_is_admin_only(
    client, monorepo: Path, tmp_path: Path, monkeypatch,
) -> None:
    _workspace(monorepo, "alpha")
    other = tmp_path / "other"
    _workspace(other, "beta")
    paths.register_workspace(monorepo, name="Main", active=True)
    paths.register_workspace(other, name="Other", active=False)
    assert _create_user(client, "miriam", "miriam", workspaces=["main"]).status_code == 200
    client.post("/api/auth/logout")
    assert _login(client, "miriam", "miriam").status_code == 200

    from core.routes import term
    monkeypatch.setattr(term, "_sessions_for_root", lambda root, project_id: [])
    monkeypatch.setattr(term, "_get_project_sessions", lambda root, project_id: [])

    allowed = client.get("/api/term/sessions", params={"project_id": "alpha", "workspace": "main"})
    denied = client.get("/api/term/sessions", params={"project_id": "beta", "workspace": "other"})
    home = client.get("/api/term/sessions", params={"project_id": "__self__"})

    assert allowed.status_code == 200, allowed.text
    assert denied.status_code == 404
    assert home.status_code == 403


def test_admin_can_register_workspace_and_grant_it_to_user(
    client, tmp_path: Path,
) -> None:
    root = tmp_path / "team-space"
    _workspace(root, "demo")

    added = client.post("/api/workspaces", json={
        "path": str(root),
        "name": "Team Space",
        "create": False,
    })
    workspace_id = added.json()["workspace"]["id"]
    assert _create_user(client, "miriam", "miriam").status_code == 200
    granted = client.patch("/api/admin/users/miriam", json={"workspaces": [workspace_id]})

    assert added.status_code == 200, added.text
    assert granted.status_code == 200, granted.text
    assert granted.json()["user"]["workspaces"] == [workspace_id]


def test_admin_can_create_a_new_empty_workspace(client, tmp_path: Path) -> None:
    root = tmp_path / "brand-new"

    response = client.post("/api/workspaces", json={
        "path": str(root),
        "name": "Brand New",
        "create": True,
    })

    assert response.status_code == 200, response.text
    assert (root / "lab.toml").is_file()
    assert (root / "projects").is_dir()
    assert not (root / "projects" / "example").exists()


def test_admin_can_change_password_and_old_session_is_invalidated(client) -> None:
    assert _create_user(client, "cesar", "cesar").status_code == 200
    assert _login(client, "cesar", "cesar").status_code == 200
    old_cookie = client.cookies.get(auth.SESSION_COOKIE)
    client.post("/api/auth/login", json={"username": "admin", "password": "admin"})

    changed = client.patch("/api/admin/users/cesar", json={"password": "new-pass"})

    assert changed.status_code == 200, changed.text
    assert auth.verify_session(old_cookie) is None
    client.post("/api/auth/logout")
    assert _login(client, "cesar", "cesar").status_code == 401
    assert _login(client, "cesar", "new-pass").status_code == 200
