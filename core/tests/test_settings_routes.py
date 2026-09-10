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
