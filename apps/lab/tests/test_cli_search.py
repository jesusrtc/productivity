from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from lab.cli import main


def test_search_cli_empty_prints_no_matches(monorepo: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["search", "xyzzy"])
    assert result.exit_code == 0
    assert "no matches" in result.output.lower()


def test_search_cli_returns_project_hits(monorepo: Path, seed_project) -> None:
    seed_project("alpha", description="Has banana in it")
    runner = CliRunner()
    result = runner.invoke(main, ["search", "banana"])
    assert result.exit_code == 0
    assert "alpha" in result.output
