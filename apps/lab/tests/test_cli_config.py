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


def test_resolve_agent_project_override_beats_global(monorepo: Path, seed_project) -> None:
    seed_project("p")
    runner = CliRunner()
    runner.invoke(main, ["config", "set", "defaultAgent", "codex"])
    # No project override yet → inherits the global default.
    assert settings.resolve_agent(monorepo, "p") == "codex"
    # Project override wins.
    runner.invoke(main, ["project", "set", "p", "agent", "claude"])
    assert settings.resolve_agent(monorepo, "p") == "claude"
    # Clearing the override falls back to global again.
    runner.invoke(main, ["project", "set", "p", "agent", "none"])
    assert settings.resolve_agent(monorepo, "p") == "codex"


def test_resolve_agent_unknown_project_falls_back(monorepo: Path) -> None:
    # A non-existent project id must never raise — just use the default.
    assert settings.resolve_agent(monorepo, "__missing__") == settings.DEFAULT_AGENT
    assert paths.config_file(monorepo) == monorepo / ".agents" / "config.json"
