from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from lab.index import Index, build_index, read_index, write_index
from lab import paths


def test_build_index_empty_monorepo(monorepo: Path) -> None:
    idx = build_index(monorepo)
    assert idx["workspaces"] == []
    assert idx["tasks"] == []
    assert "generated_at" in idx


def test_build_index_counts_tasks_per_status(monorepo: Path, seed_workspace) -> None:
    pdir = seed_workspace("alpha")
    tasks = {
        "next_id": 5,
        "tasks": [
            {"id": 1, "title": "t1", "status": "todo", "priority": "P1",
             "loe": None, "due": None, "tags": [], "labels": [], "blocker": None,
             "notes_file": None, "created": "2026-04-16", "updated": "2026-04-16", "closed_at": None},
            {"id": 2, "title": "t2", "status": "in_progress", "priority": "P2",
             "loe": None, "due": "2026-04-20", "tags": ["x"], "labels": [], "blocker": None,
             "notes_file": None, "created": "2026-04-16", "updated": "2026-04-16", "closed_at": None},
            {"id": 3, "title": "t3", "status": "done", "priority": "P2",
             "loe": None, "due": None, "tags": [], "labels": [], "blocker": None,
             "notes_file": None, "created": "2026-04-16", "updated": "2026-04-16",
             "closed_at": "2026-04-16T12:00:00-07:00"},
            {"id": 4, "title": "t4", "status": "blocked", "priority": "P3",
             "loe": None, "due": None, "tags": [], "labels": [], "blocker": "x",
             "notes_file": None, "created": "2026-04-16", "updated": "2026-04-16", "closed_at": None},
        ],
    }
    (pdir / "tasks.json").write_text(json.dumps(tasks))

    idx = build_index(monorepo)
    assert len(idx["workspaces"]) == 1
    p = idx["workspaces"][0]
    assert p["id"] == "alpha"
    assert p["status"] == "active"
    assert p["open_task_count"] == 3
    assert p["blocked_task_count"] == 1
    assert p["task_counts"] == {"todo": 1, "in_progress": 1, "blocked": 1, "done": 1}
    assert p["earliest_task_due"] == "2026-04-20"

    assert len(idx["tasks"]) == 4
    t2 = next(t for t in idx["tasks"] if t["task_id"] == 2)
    assert t2["workspace_id"] == "alpha"
    assert t2["title"] == "t2"
    assert t2["due"] == "2026-04-20"
    assert t2["path"] == "workspaces/alpha/tasks.json#2"


def test_build_index_preserves_workspace_metadata(monorepo: Path, seed_workspace) -> None:
    pdir = seed_workspace("beta")
    data = json.loads((pdir / "workspace.json").read_text())
    data["tags"] = ["backend"]
    data["labels"] = ["sample-charts"]
    data["priority"] = "P1"
    data["due"] = "2026-05-01"
    (pdir / "workspace.json").write_text(json.dumps(data))

    idx = build_index(monorepo)
    p = idx["workspaces"][0]
    assert p["tags"] == ["backend"]
    assert p["labels"] == ["sample-charts"]
    assert p["priority"] == "P1"
    assert p["due"] == "2026-05-01"
    assert p["path"] == "workspaces/beta"


def test_build_index_sorts_workspaces_by_id(monorepo: Path, seed_workspace) -> None:
    seed_workspace("zeta")
    seed_workspace("alpha")
    seed_workspace("mu")
    idx = build_index(monorepo)
    assert [p["id"] for p in idx["workspaces"]] == ["alpha", "mu", "zeta"]


def test_build_index_skips_non_workspace_dirs(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    (monorepo / "workspaces" / "_scratch").mkdir()
    (monorepo / "workspaces" / "_scratch" / "note.md").write_text("hi")

    idx = build_index(monorepo)
    assert [p["id"] for p in idx["workspaces"]] == ["alpha"]


def test_write_and_read_index_roundtrip(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    data = build_index(monorepo)
    path = write_index(monorepo, data)
    assert path == paths.index_file(monorepo)
    assert path.is_file()
    loaded = read_index(monorepo)
    assert loaded == data


def test_read_index_missing_raises(monorepo: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_index(monorepo)


def test_index_type_alias_is_dict() -> None:
    assert Index is not None


def test_build_index_includes_prs_and_counts(monorepo: Path, seed_workspace) -> None:
    pdir = seed_workspace("gamma")
    data = json.loads((pdir / "workspace.json").read_text())
    data["prs"] = [
        {"mp": "sample-charts", "status": "open", "title": "Add retries", "url": "https://x/1"},
        {"mp": "sample-charts", "status": "merged", "title": "Old fix", "url": "https://x/2"},
        {"mp": "sample-charts", "status": "closed", "title": "Stale", "url": "https://x/3"},
        {"mp": "sample-charts", "status": "open", "title": "Second open", "url": "https://x/4"},
    ]
    (pdir / "workspace.json").write_text(json.dumps(data))

    idx = build_index(monorepo)
    p = idx["workspaces"][0]
    assert len(p["prs"]) == 4
    assert p["pr_counts"] == {"open": 2, "merged": 1, "closed": 1, "other": 0}


def test_build_index_pr_counts_defaults_when_empty(monorepo: Path, seed_workspace) -> None:
    seed_workspace("delta")
    idx = build_index(monorepo)
    p = idx["workspaces"][0]
    assert p["prs"] == []
    assert p["pr_counts"] == {"open": 0, "merged": 0, "closed": 0, "other": 0}
