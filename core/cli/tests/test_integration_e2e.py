from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from lab.cli import main


def test_full_workspace_lifecycle(monorepo: Path) -> None:
    """Create workspace → add tasks → flip statuses → list → archive."""
    runner = CliRunner()

    # Create two workspaces
    r = runner.invoke(main, ["workspace", "new", "inbox", "--desc", "Catch-all"])
    assert r.exit_code == 0, r.output
    r = runner.invoke(main, ["workspace", "new", "charts-test", "--desc", "Test", "--priority", "P1"])
    assert r.exit_code == 0, r.output

    # Add tasks to charts-test
    for i, (title, pri) in enumerate([("draft", "P1"), ("review", "P1"), ("ship", "P2")], start=1):
        r = runner.invoke(main, ["task", "new", title, "--workspace", "charts-test", "--priority", pri])
        assert r.exit_code == 0, r.output

    # Add a reminder to inbox
    r = runner.invoke(main, [
        "task", "new", "email someone", "--workspace", "inbox", "--priority", "P3",
    ])
    assert r.exit_code == 0

    # Flip states
    runner.invoke(main, ["task", "done", "1", "--workspace", "charts-test"])
    runner.invoke(main, ["task", "block", "2", "waiting on Jesus", "--workspace", "charts-test"])

    # Cross-workspace ls
    r = runner.invoke(main, ["task", "ls"])
    assert r.exit_code == 0
    assert "draft" in r.output
    assert "email someone" in r.output

    # Filter: open tasks only
    r = runner.invoke(main, ["task", "ls", "--status", "open"])
    assert "draft" not in r.output  # done
    assert "review" in r.output      # blocked still counts as open
    assert "ship" in r.output
    assert "email someone" in r.output

    # Filter: high-priority (P0/P1) open
    r = runner.invoke(main, ["task", "ls", "--status", "open", "--priority", "P0,P1"])
    assert "review" in r.output
    assert "ship" not in r.output     # P2
    assert "email someone" not in r.output  # P3

    # Archive charts-test
    runner.invoke(main, ["workspace", "archive", "charts-test"])
    r = runner.invoke(main, ["workspace", "ls", "--status", "active"])
    assert "charts-test" not in r.output
    assert "inbox" in r.output

    # Verify on-disk state
    charts = json.loads((monorepo / "workspaces" / "charts-test" / "workspace.json").read_text())
    assert charts["status"] == "archived"
    tasks = json.loads((monorepo / "workspaces" / "charts-test" / "tasks.json").read_text())
    statuses = {t["id"]: t["status"] for t in tasks["tasks"]}
    assert statuses == {1: "done", 2: "blocked", 3: "todo"}
