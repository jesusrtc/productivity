"""Shared viewer/terminal lookups must understand the global Assistant scope."""
from lab import paths


def test_assistant_document_metadata_needs_no_workspace_file(client, tmp_path, monkeypatch):
    root = tmp_path / "assistant"
    root.mkdir()
    monkeypatch.setattr(paths, "assistant_root", lambda: root)
    response = client.get("/api/workspace-info", params={"path": str(root)})
    assert response.status_code == 200
    assert response.json() == {"id": "__assistant__", "name": "Assistant", "artifacts": []}
    assert not list(root.iterdir())
    assert client.get("/api/workspace-info", params={"path": str(tmp_path / "unknown")}).status_code == 404


def test_assistant_agent_policy_uses_assistant_scope(client, tmp_path, monkeypatch):
    from core.routes import vault

    root = tmp_path / "assistant"
    root.mkdir()
    monkeypatch.setattr(paths, "assistant_root", lambda: root)
    monkeypatch.setattr(vault, "_vault_agent_policy", lambda path: {"root": str(path), "supported": ["codex"], "default": "codex"})
    response = client.get("/api/vault/agents?vault=__assistant__")
    assert response.status_code == 200, response.text
    assert response.json()["root"] == str(root)


def test_assistant_context_remains_admin_only(client, monorepo, tmp_path, monkeypatch):
    root = tmp_path / "assistant"
    root.mkdir()
    monkeypatch.setattr(paths, "assistant_root", lambda: root)
    paths.register_vault(monorepo, name="Main", active=True)
    created = client.post("/api/admin/users", json={
        "username": "viewer", "name": "Viewer", "role": "user",
        "password": "fixture-only", "vaults": ["main"],
    })
    assert created.status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={
        "username": "viewer", "password": "fixture-only",
    }).status_code == 200
    # Middleware conceals resources outside the user's assigned vaults.
    assert client.get("/api/workspace-info", params={"path": str(root)}).status_code in {403, 404}
    assert client.get("/api/vault/agents?vault=__assistant__").status_code in {403, 404}
