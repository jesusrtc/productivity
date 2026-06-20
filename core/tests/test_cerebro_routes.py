from __future__ import annotations

from pathlib import Path


def test_cerebro_tree_empty(client, monorepo: Path) -> None:
    r = client.get("/api/cerebro/tree")
    assert r.status_code == 200
    tree = r.json()
    # Fresh fixture: projects/ + meetings/ exist (created by the monorepo fixture).
    names = {n["name"] for n in tree if n["type"] == "dir"}
    assert {"projects", "meetings"}.issubset(names)


def test_cerebro_tree_lists_md_files(client, monorepo: Path) -> None:
    wikis = monorepo / "content" / "wikis" / "generic"
    wikis.mkdir(parents=True, exist_ok=True)
    (wikis / "note.md").write_text("# hi\n")
    (wikis / "binary.png").write_bytes(b"\x89PNG\r\n")

    r = client.get("/api/cerebro/tree")
    tree = r.json()
    wikis_node = next(n for n in tree if n["name"] == "wikis")
    generic = next(n for n in wikis_node["children"] if n["name"] == "generic")
    kinds = {c["name"]: c["type"] for c in generic["children"]}
    assert kinds["note.md"] == "markdown"
    assert kinds["binary.png"] == "file"


def test_cerebro_tree_skips_dotfiles_by_default(client, monorepo: Path) -> None:
    (monorepo / "content" / ".sessions.json").write_text("{}")
    tree = client.get("/api/cerebro/tree").json()
    names = {n["name"] for n in tree}
    assert ".sessions.json" not in names

    tree_all = client.get("/api/cerebro/tree?include_hidden=true").json()
    names_all = {n["name"] for n in tree_all}
    assert ".sessions.json" in names_all


def test_cerebro_tree_includes_projects_tree(client, monorepo: Path, seed_project) -> None:
    seed_project("demo")
    (monorepo / "content" / "projects" / "demo" / "docs").mkdir(exist_ok=True)
    (monorepo / "content" / "projects" / "demo" / "docs" / "one-pager.md").write_text("# one-pager")

    tree = client.get("/api/cerebro/tree").json()
    projects = next(n for n in tree if n["name"] == "projects")
    demo = next(n for n in projects["children"] if n["name"] == "demo")
    doc_names = [c["name"] for c in demo["children"]]
    assert "docs" in doc_names or "project.json" in doc_names
