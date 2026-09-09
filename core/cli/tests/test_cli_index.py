from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from lab.cli import main
from lab import paths


def test_index_rebuild_creates_file(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["index", "rebuild"])
    assert result.exit_code == 0, result.output

    index_path = paths.index_file(monorepo)
    assert index_path.is_file()
    idx = json.loads(index_path.read_text())
    assert len(idx["workspaces"]) == 1
    assert idx["workspaces"][0]["id"] == "alpha"


def test_index_rebuild_overwrites_stale(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["index", "rebuild"])
    seed_workspace("beta")
    runner.invoke(main, ["index", "rebuild"])

    idx = json.loads(paths.index_file(monorepo).read_text())
    assert {p["id"] for p in idx["workspaces"]} == {"alpha", "beta"}


def test_index_show_prints_json(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["index", "rebuild"])
    result = runner.invoke(main, ["index", "show"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert [p["id"] for p in parsed["workspaces"]] == ["alpha"]


def test_index_show_missing_rebuilds_implicitly(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["index", "show"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert [p["id"] for p in parsed["workspaces"]] == ["alpha"]
