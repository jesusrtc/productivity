from __future__ import annotations

import json
import stat
from pathlib import Path

from fastapi.testclient import TestClient

from core import auth
from lab import paths


def _vault(root: Path, workspace_id: str) -> None:
    (root / "content").mkdir(parents=True, exist_ok=True)
    (root / "workspaces" / workspace_id).mkdir(parents=True, exist_ok=True)
    (root / "lab.toml").write_text('[vault]\nname = "test"\n', encoding="utf-8")


def _login(client, username: str, password: str):
    return client.post("/api/auth/login", json={"username": username, "password": password})


def _create_user(
    client, username: str, password: str, *, vaults: list[str] | None = None,
):
    return client.post("/api/admin/users", json={
        "username": username,
        "name": username.title(),
        "role": "user",
        "password": password,
        "vaults": vaults or [],
    })


def test_login_is_required_and_seed_passwords_are_sha256(client) -> None:
    client.post("/api/auth/logout")

    page = client.get("/", follow_redirects=False)
    api = client.get("/api/vaults")

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
            params={"path": "workspaces/demo/analysis.ipynb"},
            headers=headers,
        )
        denied_elsewhere = local_client.get("/api/workspaces", headers=headers)
        denied_bad_token = local_client.get(
            "/api/nb/session",
            params={"path": "workspaces/demo/analysis.ipynb"},
            headers={"Authorization": "Bearer wrong-token-value-that-is-long-enough"},
        )
        denied_legacy_header = local_client.get(
            "/api/nb/session",
            params={"path": "workspaces/demo/analysis.ipynb"},
            headers={"X-Lab-Local-Automation": "1"},
        )

    with TestClient(app, client=("10.0.0.8", 50000)) as remote_client:
        denied_remote = remote_client.get(
            "/api/nb/session",
            params={"path": "workspaces/demo/analysis.ipynb"},
            headers=headers,
        )

    assert allowed.status_code == 200, allowed.text
    assert denied_elsewhere.status_code == 401
    assert denied_bad_token.status_code == 401
    assert denied_legacy_header.status_code == 401
    assert denied_remote.status_code == 401


def test_local_cli_bearer_preserves_requested_vault_scope(
    monorepo: Path, tmp_path: Path,
) -> None:
    from core.main import create_app

    _vault(monorepo, "demo")
    paths.register_vault(monorepo, name="Main", active=True)
    other = tmp_path / "other"
    _vault(other, "demo")
    (other / "workspaces" / "demo" / "runtime.json").write_text(
        json.dumps({"mode": "local"}), encoding="utf-8",
    )
    notebook = other / "workspaces" / "demo" / "analysis.ipynb"
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
    paths.register_vault(other, name="Other", active=False)

    app = create_app()
    with TestClient(app, client=("127.0.0.1", 50000)) as local_client:
        token = paths.read_local_cli_token()
        assert token is not None
        headers = {"Authorization": f"Bearer {token}"}
        selected = local_client.get(
            "/api/nb/session",
            params={
                "path": "workspaces/demo/analysis.ipynb",
                "vault": "other",
            },
            headers=headers,
        )
        deleted = local_client.post(
            "/api/nb/cell/delete",
            json={
                "path": "workspaces/demo/analysis.ipynb",
                "vault": "other",
                "cell_id": "cell-one",
            },
            headers=headers,
        )
        unknown = local_client.get(
            "/api/nb/session",
            params={
                "path": "workspaces/demo/analysis.ipynb",
                "vault": "missing",
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
            {"username": "jesus", "name": "Jesus", "role": "admin", "password_sha256": "old", "vaults": [], "disabled": False},
            {"username": "cesar", "name": "Cesar", "role": "user", "password_sha256": "old", "vaults": [], "disabled": False},
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


def test_admin_assigns_one_vault_and_user_cannot_see_the_other(
    client, monorepo: Path, tmp_path: Path,
) -> None:
    _vault(monorepo, "alpha")
    other = tmp_path / "other"
    _vault(other, "beta")
    paths.register_vault(monorepo, name="Main", active=True)
    paths.register_vault(other, name="Other", active=False)

    assigned = _create_user(client, "cesar", "cesar", vaults=["main"])
    assert assigned.status_code == 200, assigned.text
    client.post("/api/auth/logout")
    assert _login(client, "Cesar", "cesar").status_code == 200

    listing = client.get("/api/vaults/workspaces")
    denied = client.get("/api/vault/config", params={"vault": "other"})
    edited = client.patch(
        "/api/vaults/main/appearance",
        json={"name": "Cesar vault", "color": "#3fb950"},
    )

    assert listing.status_code == 200, listing.text
    assert [row["id"] for row in listing.json()["vaults"]] == ["main"]
    assert denied.status_code == 404
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "Cesar vault"


def test_workspace_routes_use_the_vault_selected_by_the_page(
    client, monorepo: Path, tmp_path: Path,
) -> None:
    _vault(monorepo, "shared")
    other = tmp_path / "other"
    _vault(other, "shared")
    (monorepo / "workspaces" / "shared" / "workspace.json").write_text(
        json.dumps({"id": "shared", "name": "Main copy"}), encoding="utf-8",
    )
    (other / "workspaces" / "shared" / "workspace.json").write_text(
        json.dumps({"id": "shared", "name": "Other copy"}), encoding="utf-8",
    )
    paths.register_vault(monorepo, name="Main", active=True)
    paths.register_vault(other, name="Other", active=False)
    assert _create_user(
        client, "cesar", "cesar", vaults=["main", "other"],
    ).status_code == 200
    client.post("/api/auth/logout")
    assert _login(client, "cesar", "cesar").status_code == 200

    response = client.get(
        "/api/workspaces/shared",
        headers={"referer": f"http://testserver/?workspace={other / 'workspaces' / 'shared'}"},
    )

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Other copy"


def test_user_terminal_access_is_vault_scoped_and_home_is_admin_only(
    client, monorepo: Path, tmp_path: Path, monkeypatch,
) -> None:
    _vault(monorepo, "alpha")
    other = tmp_path / "other"
    _vault(other, "beta")
    paths.register_vault(monorepo, name="Main", active=True)
    paths.register_vault(other, name="Other", active=False)
    assert _create_user(client, "miriam", "miriam", vaults=["main"]).status_code == 200
    client.post("/api/auth/logout")
    assert _login(client, "miriam", "miriam").status_code == 200

    from core.routes import term
    monkeypatch.setattr(term, "_sessions_for_root", lambda root, workspace_id: [])
    monkeypatch.setattr(term, "_get_workspace_sessions", lambda root, workspace_id: [])

    allowed = client.get("/api/term/sessions", params={"workspace_id": "alpha", "vault": "main"})
    denied = client.get("/api/term/sessions", params={"workspace_id": "beta", "vault": "other"})
    home = client.get("/api/term/sessions", params={"workspace_id": "__self__"})

    assert allowed.status_code == 200, allowed.text
    assert denied.status_code == 404
    assert home.status_code == 403


def test_admin_can_register_vault_and_grant_it_to_user(
    client, tmp_path: Path,
) -> None:
    root = tmp_path / "team-space"
    _vault(root, "demo")

    added = client.post("/api/vaults", json={
        "path": str(root),
        "name": "Team Space",
        "create": False,
    })
    vault_id = added.json()["vault"]["id"]
    assert _create_user(client, "miriam", "miriam").status_code == 200
    granted = client.patch("/api/admin/users/miriam", json={"vaults": [vault_id]})

    assert added.status_code == 200, added.text
    assert granted.status_code == 200, granted.text
    assert granted.json()["user"]["vaults"] == [vault_id]


def test_admin_can_create_a_new_empty_vault(client, tmp_path: Path) -> None:
    root = tmp_path / "brand-new"

    response = client.post("/api/vaults", json={
        "path": str(root),
        "name": "Brand New",
        "create": True,
    })

    assert response.status_code == 200, response.text
    assert (root / "lab.toml").is_file()
    assert (root / "workspaces").is_dir()
    assert not (root / "workspaces" / "example").exists()


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
