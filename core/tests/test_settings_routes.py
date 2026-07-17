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
