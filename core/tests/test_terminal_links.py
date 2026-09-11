"""Link ownership and unlinking must never affect the running terminal."""
from concurrent.futures import ThreadPoolExecutor


from .test_term_routes import isolated_prefix  # noqa: F401


def test_file_transfer_and_independent_scope_links(client, seed_workspace, isolated_prefix,
                                                  monorepo, monkeypatch):
    from core.routes import term

    monkeypatch.setattr(term, "_known_vaults", lambda _: [{"id": monorepo.name, "path": monorepo}])
    seed_workspace("demo")
    seed_workspace("other")
    sessions = []
    for workspace, name in [("demo", "first"), ("demo", "second"), ("other", "third")]:
        response = client.post("/api/term/sessions", json={
            "workspace_id": workspace, "name": name, "kind": "terminal", "start_fresh": True})
        assert response.status_code == 200, response.text
        sessions.append(response.json())

    def patch(index, **changes):
        response = client.patch("/api/term/sessions/metadata", json={
            "workspace_id": "other" if index == 2 else "demo",
            "name": sessions[index]["logical_name"], **changes})
        assert response.status_code == 200, response.text
        return response.json()

    root = str(monorepo / "workspaces" / "demo")
    scope = {"base_root": root, "project_root": root, "root": root, "label": "demo"}
    file = {"root": root, "path": "docs/notes.md"}
    patch(0, linked_file=file, label="notes.md", linked_scope=scope)
    moved = patch(1, linked_file={"root": root + "/docs", "path": "./notes.md"},
                  label="notes.md", linked_scope=scope)
    previous = moved["displaced"][0]["session"]
    assert "linked_file" not in previous and "label" not in previous
    assert previous["linked_scope"]["root"] == root
    rows = client.get("/api/term/sessions?workspace_id=demo").json()
    assert len(rows) == 2
    assert all(row["linked_scope"]["root"] == root for row in rows)
    assert sum(bool(row.get("linked_file")) for row in rows) == 1

    # Moving the file across workspace tabs also clears its old owner.
    patch(1, label="Custom title")
    moved = patch(2, linked_file=file, linked_scope=scope)
    assert moved["displaced"][0]["session"]["label"] == "Custom title"
    assert not moved["displaced"][0]["current_workspace"]
    rows = client.get("/api/term/sessions?workspace_id=demo").json()
    assert not any(row.get("linked_file") for row in rows)

    changed = patch(2, linked_file={"root": root, "path": "other.md"})["session"]
    assert changed["linked_file"]["path"] == "other.md"
    removed = patch(2, linked_scope=None)["session"]
    assert "linked_scope" not in removed and removed["linked_file"]["path"] == "other.md"
    removed = patch(2, linked_file=None)["session"]
    assert "linked_file" not in removed
    assert len(client.get("/api/term/sessions?workspace_id=other").json()) == 1


def test_simultaneous_file_assignments_leave_one_owner(monkeypatch, tmp_path):
    from core.routes import term

    # Real durable metadata, isolated from registered vaults and live tmux.
    monkeypatch.setattr(term.auth, "request_root", lambda _: tmp_path)
    monkeypatch.setattr(term, "_vault_root_for", lambda *_: tmp_path)
    monkeypatch.setattr(term, "_require_workspace_access", lambda *_: {})
    monkeypatch.setattr(term, "_known_vaults", lambda _: [{"path": tmp_path}])
    monkeypatch.setattr(term, "_known_workspace_ids", lambda _: ["demo"])
    monkeypatch.setattr(term, "_workspace_json", lambda root, workspace: root / (workspace + ".json"))
    monkeypatch.setattr(term, "_vault_id_for_root", lambda *_: "test")
    monkeypatch.setattr(term, "_load_meta", lambda _: {})
    monkeypatch.setattr(term, "_save_meta", lambda *_: None)
    term._save_workspace(tmp_path, "demo", {"sessions": [{"name": "one"}, {"name": "two"}]})

    def assign(name):
        return term.update_session_metadata(term.SessionMetadata(
            workspace_id="demo", name=name, linked_file={"root": str(tmp_path), "path": "notes.md"}), None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(row["ok"] for row in pool.map(assign, ["one", "two"]))
    saved = term._get_workspace_sessions(tmp_path, "demo")
    assert sum(bool(row.get("linked_file")) for row in saved) == 1
