from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from lab.index import Index, build_index, read_index, write_index


def test_build_index_empty_monorepo(monorepo: Path) -> None:
    idx = build_index(monorepo)
    assert idx["projects"] == []
    assert idx["tasks"] == []
    assert "generated_at" in idx


def test_build_index_counts_tasks_per_status(monorepo: Path, seed_project) -> None:
    pdir = seed_project("alpha")
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
    assert len(idx["projects"]) == 1
    p = idx["projects"][0]
    assert p["id"] == "alpha"
    assert p["status"] == "active"
    assert p["open_task_count"] == 3
    assert p["blocked_task_count"] == 1
    assert p["task_counts"] == {"todo": 1, "in_progress": 1, "blocked": 1, "done": 1}
    assert p["earliest_task_due"] == "2026-04-20"

    assert len(idx["tasks"]) == 4
    t2 = next(t for t in idx["tasks"] if t["task_id"] == 2)
    assert t2["project_id"] == "alpha"
    assert t2["title"] == "t2"
    assert t2["due"] == "2026-04-20"
    assert t2["path"] == "knowledge/projects/alpha/tasks.json#2"


def test_build_index_preserves_project_metadata(monorepo: Path, seed_project) -> None:
    pdir = seed_project("beta")
    data = json.loads((pdir / "project.json").read_text())
    data["tags"] = ["backend"]
    data["labels"] = ["lipy-davi"]
    data["priority"] = "P1"
    data["due"] = "2026-05-01"
    (pdir / "project.json").write_text(json.dumps(data))

    idx = build_index(monorepo)
    p = idx["projects"][0]
    assert p["tags"] == ["backend"]
    assert p["labels"] == ["lipy-davi"]
    assert p["priority"] == "P1"
    assert p["due"] == "2026-05-01"
    assert p["path"] == "knowledge/projects/beta"


def test_build_index_sorts_projects_by_id(monorepo: Path, seed_project) -> None:
    seed_project("zeta")
    seed_project("alpha")
    seed_project("mu")
    idx = build_index(monorepo)
    assert [p["id"] for p in idx["projects"]] == ["alpha", "mu", "zeta"]


def test_build_index_skips_non_project_dirs(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    (monorepo / "knowledge" / "projects" / "_scratch").mkdir()
    (monorepo / "knowledge" / "projects" / "_scratch" / "note.md").write_text("hi")

    idx = build_index(monorepo)
    assert [p["id"] for p in idx["projects"]] == ["alpha"]


def test_write_and_read_index_roundtrip(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    data = build_index(monorepo)
    path = write_index(monorepo, data)
    assert path == monorepo / "knowledge" / ".index.json"
    assert path.is_file()
    loaded = read_index(monorepo)
    assert loaded == data


def test_read_index_missing_raises(monorepo: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_index(monorepo)


def test_index_type_alias_is_dict() -> None:
    assert Index is not None
