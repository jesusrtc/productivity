from __future__ import annotations

from core.routes import settings as settings_route


def test_agents_available_rejects_gh_without_standalone_copilot(monkeypatch) -> None:
    def fake_which(cmd: str) -> str | None:
        return f"/fake/{cmd}" if cmd == "gh" else None

    monkeypatch.setattr(settings_route.shutil, "which", fake_which)

    assert settings_route.agents_available() == {
        "claude": False,
        "codex": False,
        "copilot": False,
    }


def test_agents_available_prefers_actual_agent_bins(monkeypatch) -> None:
    def fake_which(cmd: str) -> str | None:
        return f"/fake/{cmd}" if cmd in {"claude", "codex", "copilot"} else None

    monkeypatch.setattr(settings_route.shutil, "which", fake_which)

    assert settings_route.agents_available() == {
        "claude": True,
        "codex": True,
        "copilot": True,
    }


def test_settings_autopilot_roundtrip(client, monorepo) -> None:
    r = client.get("/api/settings")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["autopilot"] == {"claude": True, "codex": False, "copilot": False}
    assert body["autopilotFlags"]["copilot"] == "--autopilot"

    r = client.post("/api/settings", json={"autopilot": {"copilot": True}})
    assert r.status_code == 200, r.text
    assert r.json()["autopilot"]["copilot"] is True
    # merge semantics: claude's default-on survives a partial patch
    assert r.json()["autopilot"]["claude"] is True

    r = client.post("/api/settings", json={"autopilot": {"gemini": True}})
    assert r.status_code == 400


def test_context_checks_and_legacy_sync_leave_instructions_untouched(client, monorepo):
    agents = monorepo / "AGENTS.md"
    agents.write_text("User-owned instructions\n")
    claude = monorepo / "CLAUDE.md"
    claude.symlink_to("AGENTS.md")
    response = client.get("/api/agents/context")
    assert response.status_code == 200
    assert response.json()["ok"]
    assert response.json()["legacy_links"]
    response = client.post("/api/agents/sync")
    assert response.status_code == 200
    assert response.json()["actions"] == []
    assert agents.read_text() == "User-owned instructions\n"
    assert claude.is_symlink()


def test_agent_context_reads_the_installed_launch_guide(client, monkeypatch):
    import sys
    import types
    guide = '# Framework instructions\nRead local workspace instructions too.\n'
    module = types.ModuleType('lab.agent_context')
    module.read_context = lambda: guide
    monkeypatch.setitem(sys.modules, 'lab.agent_context', module)
    response = client.get('/api/agents/context/guide')
    assert response.status_code == 200
    assert response.json() == {'content': guide}


def test_agent_context_instantiates_owning_paths_for_objective_and_worktree(client, monorepo, seed_workspace, tmp_path):
    import os
    from pathlib import Path
    from lab import objectives, settings
    workspace = seed_workspace('client')
    first = objectives.mutate(monorepo, 'client', {'type': 'create', 'name': 'Audit'})['objectives'][0]
    second = objectives.mutate(monorepo, 'client', {'type': 'create', 'name': 'Recovery'})['objectives'][1]
    tree = tmp_path / 'checkouts' / 'audit'
    tree.mkdir(parents=True)
    settings.update_global(monorepo, {'worktreesFolder': str(tree.parent)})
    for root in [monorepo, workspace, Path(first['path']), Path(second['path']), tree]:
        (root / 'AGENTS.md').write_text('Scope rules\n')
    for source in [workspace, Path(first['path']), tree]:
        response = client.get('/api/agents/context/guide', params={
            'path': str(source), 'workspace_id': 'client', 'objective_id': first['id']})
        assert response.status_code == 200, response.text
        content = response.json()['content']
        assert f'Source folder: `{source}`' in content
        for label, root in [('Vault', monorepo), ('Workspace', workspace), ('Objective', Path(first['path']))]:
            assert f'- {label} root: `{root}`; instructions: `{root / "AGENTS.md"}`' in content
        assert '{{' not in content
    response = client.get('/api/agents/context/guide', params={
        'path': str(tree), 'workspace_id': 'client', 'objective_id': second['id']})
    content = response.json()['content']
    assert str(Path(second['path']) / 'AGENTS.md') in content
    assert str(Path(first['path']) / 'AGENTS.md') not in content


def test_agent_context_rejects_invalid_scope_and_unapproved_source(client, monorepo, seed_workspace, tmp_path):
    workspace = seed_workspace('client')
    url = '/api/agents/context/guide'
    assert client.get(url, params={'path': str(workspace), 'objective_id': 'missing'}).status_code == 400
    assert client.get(url, params={'path': str(workspace), 'workspace_id': 'client', 'objective_id': 'missing'}).status_code == 404
    assert client.get(url, params={'path': str(workspace), 'workspace_id': '../outside'}).status_code == 400
    outside = tmp_path / 'unapproved'
    outside.mkdir()
    assert client.get(url, params={'path': str(outside)}).status_code == 403


def test_lab_docs_are_readable_outside_vault_without_arbitrary_file_access(client):
    from pathlib import Path
    from lab.agent_context import documentation, read_context
    response = client.get('/api/agents/context/documents')
    assert response.status_code == 200 and response.json() == documentation()
    for doc in response.json():
        assert Path(doc['path']).is_absolute()
        response = client.get('/api/agents/context/document', params={'name': doc['name']})
        assert response.status_code == 200
        assert response.json() == {**doc, 'content': read_context(doc['name'])}
    for name in ['overview', '../AGENTS.md', '/etc/passwd']:
        assert client.get('/api/agents/context/document', params={'name': name}).status_code == 404
