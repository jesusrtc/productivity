from __future__ import annotations

import json
from pathlib import Path

from lab.search import search


def test_search_empty_query(monorepo: Path) -> None:
    r = search(monorepo, "")
    assert r == {"query": "", "projects": [], "tasks": [], "docs": []}


def test_search_matches_project_description(monorepo: Path, seed_project) -> None:
    seed_project("alpha", description="This contains the keyword BANANA")
    r = search(monorepo, "banana")
    assert len(r["projects"]) == 1
    assert r["projects"][0]["id"] == "alpha"


def test_search_matches_project_tags(monorepo: Path, seed_project) -> None:
    alpha = seed_project("alpha")
    data = json.loads((alpha / "project.json").read_text())
    data["tags"] = ["fruit-basket"]
    (alpha / "project.json").write_text(json.dumps(data))
    r = search(monorepo, "fruit")
    assert len(r["projects"]) == 1


def test_search_matches_task_title(monorepo: Path, seed_project) -> None:
    pdir = seed_project("alpha")
    (pdir / "tasks.json").write_text(json.dumps({
        "next_id": 2,
        "tasks": [{
            "id": 1, "title": "Review BANANA shipment", "status": "todo", "priority": "P2",
            "loe": None, "due": None, "tags": [], "labels": [], "blocker": None,
            "notes_file": None, "created": "2026-04-17", "updated": "2026-04-17", "closed_at": None,
        }],
    }))
    r = search(monorepo, "banana")
    assert len(r["tasks"]) == 1
    assert r["tasks"][0]["task_id"] == 1


def test_search_matches_md_docs(monorepo: Path) -> None:
    (monorepo / "content" / "meetings" / "notes.md").write_text(
        "# Meeting\nTopic: banana logistics\nFollow-up next week.",
        encoding="utf-8",
    )
    r = search(monorepo, "banana logistics")
    assert len(r["docs"]) == 1
    assert "content/meetings/notes.md" in r["docs"][0]["path"]
    assert "banana logistics" in r["docs"][0]["snippet"].lower()


def test_search_no_match(monorepo: Path, seed_project) -> None:
    seed_project("alpha")
    r = search(monorepo, "xyzzy-unlikely-string")
    assert r["projects"] == []
    assert r["tasks"] == []
    assert r["docs"] == []
