from __future__ import annotations

import pytest
from click.testing import CliRunner

from lab.cli import main


def test_task_group_help() -> None:
    runner = CliRunner()
    result = runner.invoke(main, ["task", "--help"])
    assert result.exit_code == 0, result.output
    assert "task" in result.output.lower()


import json
from pathlib import Path

from lab.cli import main


def test_task_new_basic(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    result = runner.invoke(main, [
        "task", "new", "Draft one-pager",
        "--workspace", "alpha", "--priority", "P1",
    ])
    assert result.exit_code == 0, result.output
    tasks = json.loads((monorepo / "workspaces" / "alpha" / "tasks.json").read_text())
    assert tasks["next_id"] == 2
    assert len(tasks["tasks"]) == 1
    t = tasks["tasks"][0]
    assert t["id"] == 1
    assert t["title"] == "Draft one-pager"
    assert t["priority"] == "P1"
    assert t["status"] == "todo"


def test_task_new_with_file_creates_notes(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    result = runner.invoke(main, [
        "task", "new", "Review one-pager with Jesus",
        "--workspace", "alpha", "--priority", "P1", "--file",
    ])
    assert result.exit_code == 0, result.output
    notes_dir = monorepo / "workspaces" / "alpha" / "notes"
    notes = list(notes_dir.iterdir())
    assert len(notes) == 1
    content = notes[0].read_text()
    assert "Review one-pager with Jesus" in content


def test_task_new_auto_detects_workspace_from_pwd(monorepo: Path, seed_workspace, monkeypatch) -> None:
    pdir = seed_workspace("alpha")
    monkeypatch.chdir(pdir)
    runner = CliRunner()
    result = runner.invoke(main, ["task", "new", "Inline task", "--priority", "P2"])
    assert result.exit_code == 0, result.output


def test_task_new_requires_priority(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["task", "new", "No priority", "--workspace", "alpha"])
    assert result.exit_code != 0


def test_task_new_full_fields(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    result = runner.invoke(main, [
        "task", "new", "Review", "--workspace", "alpha",
        "--priority", "P1", "--loe", "0.5", "--due", "2026-04-20",
        "--tags", "review,meet", "--labels", "sample-charts",
    ])
    assert result.exit_code == 0, result.output
    t = json.loads((monorepo / "workspaces" / "alpha" / "tasks.json").read_text())["tasks"][0]
    assert t["loe"] == 0.5
    assert t["due"] == "2026-04-20"
    assert t["tags"] == ["review", "meet"]
    assert t["labels"] == ["sample-charts"]


def test_task_new_next_id_increments(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "a", "--workspace", "alpha", "--priority", "P2"])
    runner.invoke(main, ["task", "new", "b", "--workspace", "alpha", "--priority", "P2"])
    tasks = json.loads((monorepo / "workspaces" / "alpha" / "tasks.json").read_text())
    assert tasks["next_id"] == 3
    assert [t["id"] for t in tasks["tasks"]] == [1, 2]


def test_task_ls_empty(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["task", "ls", "--workspace", "alpha"])
    assert result.exit_code == 0
    assert "no tasks" in result.output.lower()


def test_task_ls_cross_workspace(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    seed_workspace("beta")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "alpha-task", "--workspace", "alpha", "--priority", "P1"])
    runner.invoke(main, ["task", "new", "beta-task", "--workspace", "beta", "--priority", "P2"])
    result = runner.invoke(main, ["task", "ls"])
    assert result.exit_code == 0
    assert "alpha-task" in result.output
    assert "beta-task" in result.output


def test_task_ls_filter_by_status(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "open-one", "--workspace", "alpha", "--priority", "P2"])
    runner.invoke(main, ["task", "new", "will-close", "--workspace", "alpha", "--priority", "P2"])
    runner.invoke(main, ["task", "done", "2", "--workspace", "alpha"])

    result = runner.invoke(main, ["task", "ls", "--workspace", "alpha", "--status", "open"])
    assert "open-one" in result.output
    assert "will-close" not in result.output

    result = runner.invoke(main, ["task", "ls", "--workspace", "alpha", "--status", "done"])
    assert "will-close" in result.output
    assert "open-one" not in result.output


def test_task_ls_filter_by_due_window(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    from datetime import date, timedelta
    near = (date.today() + timedelta(days=3)).isoformat()
    far = (date.today() + timedelta(days=30)).isoformat()
    runner.invoke(main, ["task", "new", "near", "--workspace", "alpha", "--priority", "P2", "--due", near])
    runner.invoke(main, ["task", "new", "far", "--workspace", "alpha", "--priority", "P2", "--due", far])

    result = runner.invoke(main, ["task", "ls", "--workspace", "alpha", "--due", "7d"])
    assert "near" in result.output
    assert "far" not in result.output


def test_task_done_sets_closed_at(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "ship it", "--workspace", "alpha", "--priority", "P1"])
    result = runner.invoke(main, ["task", "done", "1", "--workspace", "alpha"])
    assert result.exit_code == 0, result.output
    t = json.loads((monorepo / "workspaces" / "alpha" / "tasks.json").read_text())["tasks"][0]
    assert t["status"] == "done"
    assert t["closed_at"] is not None


def test_task_reopen_clears_closed_at(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "ship", "--workspace", "alpha", "--priority", "P1"])
    runner.invoke(main, ["task", "done", "1", "--workspace", "alpha"])
    result = runner.invoke(main, ["task", "reopen", "1", "--workspace", "alpha"])
    assert result.exit_code == 0, result.output
    t = json.loads((monorepo / "workspaces" / "alpha" / "tasks.json").read_text())["tasks"][0]
    assert t["status"] == "in_progress"
    assert t["closed_at"] is None


def test_task_done_missing_task(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    result = runner.invoke(main, ["task", "done", "99", "--workspace", "alpha"])
    assert result.exit_code != 0


def test_task_block_sets_blocker(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "blocked-task", "--workspace", "alpha", "--priority", "P2"])
    result = runner.invoke(main, ["task", "block", "1", "waiting on legal", "--workspace", "alpha"])
    assert result.exit_code == 0, result.output
    t = json.loads((monorepo / "workspaces" / "alpha" / "tasks.json").read_text())["tasks"][0]
    assert t["status"] == "blocked"
    assert t["blocker"] == "waiting on legal"


def test_task_unblock_clears(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "t", "--workspace", "alpha", "--priority", "P2"])
    runner.invoke(main, ["task", "block", "1", "stuck", "--workspace", "alpha"])
    result = runner.invoke(main, ["task", "unblock", "1", "--workspace", "alpha"])
    assert result.exit_code == 0
    t = json.loads((monorepo / "workspaces" / "alpha" / "tasks.json").read_text())["tasks"][0]
    assert t["status"] == "in_progress"
    assert t["blocker"] is None


def test_task_show(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "Review", "--workspace", "alpha", "--priority", "P1", "--file"])
    result = runner.invoke(main, ["task", "show", "1", "--workspace", "alpha"])
    assert result.exit_code == 0
    assert "Review" in result.output
    assert "P1" in result.output
    # Notes file content is shown too
    assert "# Review" in result.output


def test_task_set_field(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "T", "--workspace", "alpha", "--priority", "P2"])
    result = runner.invoke(main, ["task", "set", "1", "priority", "P0", "--workspace", "alpha"])
    assert result.exit_code == 0, result.output
    t = json.loads((monorepo / "workspaces" / "alpha" / "tasks.json").read_text())["tasks"][0]
    assert t["priority"] == "P0"


def test_task_set_rejects_unknown_field(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "T", "--workspace", "alpha", "--priority", "P2"])
    result = runner.invoke(main, ["task", "set", "1", "foo", "bar", "--workspace", "alpha"])
    assert result.exit_code != 0


def test_task_set_tags_csv(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "T", "--workspace", "alpha", "--priority", "P2"])
    runner.invoke(main, ["task", "set", "1", "tags", "a,b", "--workspace", "alpha"])
    t = json.loads((monorepo / "workspaces" / "alpha" / "tasks.json").read_text())["tasks"][0]
    assert t["tags"] == ["a", "b"]


def test_task_ls_filter_by_tag(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "reviewed", "--workspace", "alpha", "--priority", "P2", "--tags", "review"])
    runner.invoke(main, ["task", "new", "other", "--workspace", "alpha", "--priority", "P2"])
    result = runner.invoke(main, ["task", "ls", "--tag", "review"])
    assert result.exit_code == 0
    assert "reviewed" in result.output
    assert "other" not in result.output


def test_task_ls_filter_by_label(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "labeled", "--workspace", "alpha", "--priority", "P2", "--labels", "sample-charts"])
    runner.invoke(main, ["task", "new", "other", "--workspace", "alpha", "--priority", "P2"])
    result = runner.invoke(main, ["task", "ls", "--label", "sample-charts"])
    assert result.exit_code == 0
    assert "labeled" in result.output
    assert "other" not in result.output


def test_task_ls_due_bad_format(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "t", "--workspace", "alpha", "--priority", "P2"])
    result = runner.invoke(main, ["task", "ls", "--workspace", "alpha", "--due", "foo"])
    assert result.exit_code != 0
    assert "nd" in result.output.lower()


def test_task_set_loe_invalid(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    runner = CliRunner()
    runner.invoke(main, ["task", "new", "t", "--workspace", "alpha", "--priority", "P2"])
    result = runner.invoke(main, ["task", "set", "1", "loe", "abc", "--workspace", "alpha"])
    assert result.exit_code != 0
    assert "not a number" in result.output.lower()
