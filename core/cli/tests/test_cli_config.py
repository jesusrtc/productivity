from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from lab import paths, settings
from lab.cli import main


def test_config_defaults(monorepo: Path) -> None:
    runner = CliRunner()
    r = runner.invoke(main, ["config", "show"])
    assert r.exit_code == 0, r.output
    assert "defaultAgent = 'claude'" in r.output
    assert "theme = 'dark'" in r.output


def test_config_set_persists_and_get(monorepo: Path) -> None:
    runner = CliRunner()
    r = runner.invoke(main, ["config", "set", "defaultAgent", "codex"])
    assert r.exit_code == 0, r.output
    cfg = json.loads((monorepo / ".agents" / "config.json").read_text())
    assert cfg["defaultAgent"] == "codex"
    g = runner.invoke(main, ["config", "get", "defaultAgent"])
    assert g.exit_code == 0
    assert g.output.strip() == "codex"


def test_config_rejects_bad_agent(monorepo: Path) -> None:
    runner = CliRunner()
    r = runner.invoke(main, ["config", "set", "defaultAgent", "bogus"])
    assert r.exit_code != 0
    assert "not one of" in r.output


def test_config_rejects_unknown_key(monorepo: Path) -> None:
    runner = CliRunner()
    r = runner.invoke(main, ["config", "set", "nope", "x"])
    assert r.exit_code != 0
    assert "unknown setting" in r.output


def test_resolve_agent_workspace_override_beats_global(monorepo: Path, seed_workspace) -> None:
    seed_workspace("p")
    runner = CliRunner()
    runner.invoke(main, ["config", "set", "defaultAgent", "codex"])
    # No workspace override yet → inherits the global default.
    assert settings.resolve_agent(monorepo, "p") == "codex"
    # Workspace override wins.
    runner.invoke(main, ["workspace", "set", "p", "agent", "claude"])
    assert settings.resolve_agent(monorepo, "p") == "claude"
    # Clearing the override falls back to global again.
    runner.invoke(main, ["workspace", "set", "p", "agent", "none"])
    assert settings.resolve_agent(monorepo, "p") == "codex"


def test_resolve_agent_unknown_workspace_falls_back(monorepo: Path) -> None:
    # A non-existent workspace id must never raise — just use the default.
    assert settings.resolve_agent(monorepo, "__missing__") == settings.DEFAULT_AGENT
    assert paths.config_file(monorepo) == monorepo / ".agents" / "config.json"


def test_autopilot_defaults(monorepo: Path) -> None:
    from lab import settings

    cfg = settings.load(monorepo)
    assert cfg["autopilot"] == {"claude": True, "codex": False, "copilot": False}
    assert settings.resolve_autopilot(monorepo, "claude") is True
    assert settings.resolve_autopilot(monorepo, "copilot") is False


def test_autopilot_update_merges_per_agent(monorepo: Path) -> None:
    from lab import settings

    settings.update(monorepo, {"autopilot": {"copilot": True}})
    cfg = settings.load(monorepo)
    # copilot flipped on, claude default preserved, codex untouched.
    assert cfg["autopilot"] == {"claude": True, "codex": False, "copilot": True}

    settings.update(monorepo, {"autopilot": {"claude": False}})
    assert settings.load(monorepo)["autopilot"] == {
        "claude": False, "codex": False, "copilot": True,
    }


def test_autopilot_rejects_bad_shapes(monorepo: Path) -> None:
    import pytest as _pytest

    from lab import settings

    with _pytest.raises(settings.SettingsError):
        settings.update(monorepo, {"autopilot": {"gemini": True}})
    with _pytest.raises(settings.SettingsError):
        settings.update(monorepo, {"autopilot": {"claude": "yes"}})
    with _pytest.raises(settings.SettingsError):
        settings.update(monorepo, {"autopilot": ["claude"]})


def test_global_cli_settings_match_ui_and_warn_when_legacy_is_shadowed(monorepo: Path, tmp_path) -> None:
    runner = CliRunner()
    other = tmp_path / 'another-vault'
    other.mkdir()
    result = runner.invoke(main, ['config', 'set', '--global', 'defaultAgent', 'codex'])
    assert result.exit_code == 0, result.output
    assert settings.resolve_agent(other) == 'codex'
    assert json.loads(settings.client_settings_file().read_text()) == {'defaultAgent': 'codex'}
    legacy = runner.invoke(main, ['config', 'set', 'defaultAgent', 'copilot'])
    assert legacy.exit_code == 0 and 'Use --global' in legacy.output
    assert settings.resolve_agent(monorepo) == 'codex'
    assert runner.invoke(main, ['config', 'get', 'defaultAgent']).output.strip() == 'codex'
