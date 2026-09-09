from __future__ import annotations

import json
from pathlib import Path

from lab.search import search


def test_search_empty_query(monorepo: Path) -> None:
    r = search(monorepo, "")
    assert r == {"query": "", "workspaces": [], "tasks": [], "docs": []}


def test_search_matches_workspace_description(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha", description="This contains the keyword BANANA")
    r = search(monorepo, "banana")
    assert len(r["workspaces"]) == 1
    assert r["workspaces"][0]["id"] == "alpha"


def test_search_matches_workspace_tags(monorepo: Path, seed_workspace) -> None:
    alpha = seed_workspace("alpha")
    data = json.loads((alpha / "workspace.json").read_text())
    data["tags"] = ["fruit-basket"]
    (alpha / "workspace.json").write_text(json.dumps(data))
    r = search(monorepo, "fruit")
    assert len(r["workspaces"]) == 1


def test_search_matches_task_title(monorepo: Path, seed_workspace) -> None:
    pdir = seed_workspace("alpha")
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


def test_search_no_match(monorepo: Path, seed_workspace) -> None:
    seed_workspace("alpha")
    r = search(monorepo, "xyzzy-unlikely-string")
    assert r["workspaces"] == []
    assert r["tasks"] == []
    assert r["docs"] == []
