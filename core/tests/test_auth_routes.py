from __future__ import annotations

import json
from pathlib import Path

from core import auth
from lab import paths


def _workspace(root: Path, project_id: str) -> None:
    (root / "content").mkdir(parents=True, exist_ok=True)
    (root / "projects" / project_id).mkdir(parents=True, exist_ok=True)
    (root / "lab.toml").write_text('[workspace]\nname = "test"\n', encoding="utf-8")


def _login(client, username: str, password: str):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def test_login_is_required_and_seed_passwords_are_sha256(client) -> None:
    client.post("/api/auth/logout")

    page = client.get("/", follow_redirects=False)
    api = client.get("/api/workspaces")

    assert page.status_code == 303
    assert page.headers["location"].startswith("/login?next=")
    assert api.status_code == 401
    store = json.loads(auth.auth_file().read_text(encoding="utf-8"))
    users = {row["username"]: row for row in store["users"]}
    assert users["jesus"]["role"] == "admin"
    assert users["cesar"]["role"] == "user"
    assert users["miriam"]["role"] == "user"
    assert users["jesus"]["password_sha256"] == auth.password_sha256("jesus")
    assert "password" not in users["jesus"]


def test_admin_assigns_one_workspace_and_user_cannot_see_the_other(
    client, monorepo: Path, tmp_path: Path,
) -> None:
    _workspace(monorepo, "alpha")
    other = tmp_path / "other"
    _workspace(other, "beta")
    paths.register_workspace(monorepo, name="Main", active=True)
    paths.register_workspace(other, name="Other", active=False)

    assigned = client.patch("/api/admin/users/cesar", json={"workspaces": ["main"]})
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
    assert client.patch(
        "/api/admin/users/cesar", json={"workspaces": ["main", "other"]},
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
    assert client.patch("/api/admin/users/miriam", json={"workspaces": ["main"]}).status_code == 200
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
    assert _login(client, "cesar", "cesar").status_code == 200
    old_cookie = client.cookies.get(auth.SESSION_COOKIE)
    client.post("/api/auth/login", json={"username": "jesus", "password": "jesus"})

    changed = client.patch("/api/admin/users/cesar", json={"password": "new-pass"})

    assert changed.status_code == 200, changed.text
    assert auth.verify_session(old_cookie) is None
    client.post("/api/auth/logout")
    assert _login(client, "cesar", "cesar").status_code == 401
    assert _login(client, "cesar", "new-pass").status_code == 200
