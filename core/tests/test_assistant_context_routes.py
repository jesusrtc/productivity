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


def test_instruction_files_include_assistant_and_hidden_copilot_without_scanning(client, tmp_path, monkeypatch):
    root = tmp_path / "assistant"
    root.mkdir()
    monkeypatch.setattr(paths, "assistant_root", lambda: root)
    (root / "AGENTS.md").write_text("Assistant instructions\n")
    (root / "CLAUDE.md").symlink_to("AGENTS.md")
    (root / ".github").mkdir()
    (root / ".github/copilot-instructions.md").write_text("Copilot instructions\n")
    (root / "nested").mkdir()
    (root / "nested/AGENTS.md").write_text("Nested instructions\n")
    (root / "notes.md").write_text("Notes\n")
    # Instruction discovery must remain bounded even in a large workspace.
    original_iterdir = type(root).iterdir
    def no_scan(directory):
        if directory == root or root in directory.parents:
            raise AssertionError("Instruction lookup must not walk directories")
        return original_iterdir(directory)
    monkeypatch.setattr(type(root), "iterdir", no_scan)
    response = client.get("/api/agents/context/files", params={"path": str(root)})
    assert response.status_code == 200, response.text
    files = response.json()
    assert [row["path"] for row in files] == ["AGENTS.md", "CLAUDE.md", ".github/copilot-instructions.md"]
    assert files[1]["is_symlink"] and files[1]["symlink_target"] == "AGENTS.md"
    nested = client.get("/api/agents/context/files", params={"path": str(root / "nested")})
    assert nested.status_code == 200, nested.text
    assert [row["path"] for row in nested.json()] == ["AGENTS.md"]


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
    assert client.get("/api/agents/context/files", params={"path": str(root)}).status_code in {403, 404}
