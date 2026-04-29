from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from lab.cli import main


def test_index_rebuild_creates_file(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["index", "rebuild"])
    assert result.exit_code == 0, result.output

    index_path = monorepo / "content" / ".index.json"
    assert index_path.is_file()
    idx = json.loads(index_path.read_text())
    assert len(idx["projects"]) == 1
    assert idx["projects"][0]["id"] == "alpha"


def test_index_rebuild_overwrites_stale(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["index", "rebuild"])
    seed_project("beta")
    runner.invoke(main, ["index", "rebuild"])

    idx = json.loads((monorepo / "content" / ".index.json").read_text())
    assert {p["id"] for p in idx["projects"]} == {"alpha", "beta"}


def test_index_show_prints_json(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    runner.invoke(main, ["index", "rebuild"])
    result = runner.invoke(main, ["index", "show"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert [p["id"] for p in parsed["projects"]] == ["alpha"]


def test_index_show_missing_rebuilds_implicitly(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["index", "show"])
    assert result.exit_code == 0
    parsed = json.loads(result.output)
    assert [p["id"] for p in parsed["projects"]] == ["alpha"]
