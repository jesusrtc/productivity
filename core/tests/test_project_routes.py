import json
import subprocess
from pathlib import Path
from types import SimpleNamespace


def _request(root):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(index_cache=SimpleNamespace(root=root)),
        ),
    )


def test_list_projects_empty(client) -> None:
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == []


def test_list_projects_returns_index_slice(client, seed_project) -> None:
    seed_project("alpha")
    seed_project("beta")
    r = client.get("/api/projects")
    ids = [p["id"] for p in r.json()]
    assert ids == ["alpha", "beta"]


def test_list_projects_filter_by_status(client, seed_project, monorepo) -> None:
    alpha = seed_project("alpha")
    beta = seed_project("beta")
    data = json.loads((beta / "project.json").read_text())
    data["status"] = "archived"
    (beta / "project.json").write_text(json.dumps(data))

    r = client.get("/api/projects?status=active")
    ids = [p["id"] for p in r.json()]
    assert ids == ["alpha"]

    r = client.get("/api/projects?status=archived")
    ids = [p["id"] for p in r.json()]
    assert ids == ["beta"]


def test_get_single_project_returns_full_json(client, seed_project) -> None:
    seed_project("alpha", description="Alpha desc")
    r = client.get("/api/projects/alpha")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "alpha"
    assert body["description"] == "Alpha desc"
    assert body["worktrees"] == []


def test_get_single_project_missing(client) -> None:
    r = client.get("/api/projects/nope")
    assert r.status_code == 404


def test_get_single_project_rejects_bad_id(client) -> None:
    r = client.get("/api/projects/..%2Fbad")
    assert r.status_code in {400, 404}


def test_get_project_tasks_empty(client, seed_project) -> None:
    seed_project("alpha")
    r = client.get("/api/projects/alpha/tasks")
    assert r.status_code == 200
    assert r.json() == {"next_id": 1, "tasks": []}


def test_get_project_tasks_reflects_on_disk(client, seed_project) -> None:
    import json as _json
    pdir = seed_project("alpha")
    (pdir / "tasks.json").write_text(_json.dumps({
        "next_id": 2,
        "tasks": [{"id": 1, "title": "hi", "status": "todo", "priority": "P1",
                   "loe": None, "due": None, "tags": [], "labels": [],
                   "blocker": None, "notes_file": None,
                   "created": "2026-04-17", "updated": "2026-04-17", "closed_at": None}],
    }))
    r = client.get("/api/projects/alpha/tasks")
    body = r.json()
    assert body["next_id"] == 2
    assert body["tasks"][0]["title"] == "hi"


def test_get_project_tasks_missing_project(client) -> None:
    r = client.get("/api/projects/nope/tasks")
    assert r.status_code == 404


def test_get_self_project_tasks_reads_framework_root(tmp_path, monkeypatch) -> None:
    from core.routes import project as project_routes

    workspace = tmp_path / "workspace"
    framework = tmp_path / "framework"
    (workspace / "content").mkdir(parents=True)
    (framework / "content").mkdir(parents=True)
    (workspace / "content" / ".self-tasks.json").write_text(json.dumps({
        "next_id": 2,
        "tasks": [{"id": 1, "title": "workspace task"}],
    }))
    (framework / "content" / ".self-tasks.json").write_text(json.dumps({
        "next_id": 2,
        "tasks": [{"id": 1, "title": "framework task"}],
    }))
    monkeypatch.setattr(project_routes.paths, "find_framework_root", lambda: framework)

    body = project_routes.get_project_tasks("__self__", _request(workspace))

    assert body["tasks"][0]["title"] == "framework task"


def test_list_project_docs(client, seed_project) -> None:
    pdir = seed_project("alpha")
    (pdir / "docs" / "one-pager.md").write_text("# hello")
    (pdir / "notes" / "001-draft.md").write_text("# draft")
    (pdir / "assets").mkdir(exist_ok=True)
    (pdir / "assets" / "chart.png").write_bytes(b"\x89PNG")

    r = client.get("/api/projects/alpha/docs")
    assert r.status_code == 200
    files = r.json()
    paths_set = {f["path"] for f in files}
    assert "docs/one-pager.md" in paths_set
    assert "notes/001-draft.md" in paths_set
    assert "assets/chart.png" in paths_set


def test_list_project_docs_missing_project(client) -> None:
    r = client.get("/api/projects/nope/docs")
    assert r.status_code == 404


def test_get_project_file_text(client, seed_project) -> None:
    pdir = seed_project("alpha")
    (pdir / "docs" / "one-pager.md").write_text("# body")
    r = client.get("/api/projects/alpha/file?path=docs/one-pager.md")
    assert r.status_code == 200
    assert "# body" in r.text


def test_get_project_file_rejects_traversal(client, seed_project) -> None:
    seed_project("alpha")
    r = client.get("/api/projects/alpha/file?path=../beta.md")
    assert r.status_code == 400


def test_get_project_file_missing(client, seed_project) -> None:
    seed_project("alpha")
    r = client.get("/api/projects/alpha/file?path=notes/999.md")
    assert r.status_code == 404


def test_project_files_marks_symlinks(client, seed_project) -> None:
    pdir = seed_project("alpha")
    (pdir / "AGENTS.md").write_text("# canonical\n")
    (pdir / "CLAUDE.md").symlink_to("AGENTS.md")
    (pdir / "real-docs").mkdir()
    (pdir / "real-docs" / "note.md").write_text("# note\n")
    (pdir / "linked-docs").symlink_to("real-docs", target_is_directory=True)
    (pdir / ".claude").mkdir()
    (pdir / ".claude" / "skills").symlink_to("../real-docs", target_is_directory=True)

    r = client.get(f"/api/project-files?path={pdir}")
    assert r.status_code == 200
    files = {f["path"]: f for f in r.json()}

    assert files["CLAUDE.md"]["is_symlink"] is True
    assert files["CLAUDE.md"]["symlink_target"] == "AGENTS.md"
    assert "is_symlink" not in files["AGENTS.md"]
    assert files["linked-docs"]["type"] == "dir"
    assert files["linked-docs"]["is_symlink"] is True
    assert files["linked-docs"]["symlink_target"] == "real-docs"
    assert files["linked-docs/note.md"]["type"] == "file"

    r = client.get(f"/api/project-files?path={pdir}&include_dotfiles=true")
    assert r.status_code == 200
    files = {f["path"]: f for f in r.json()}
    assert files[".claude/skills"]["type"] == "dir"
    assert files[".claude/skills"]["is_symlink"] is True
    assert files[".claude/skills"]["symlink_target"] == "../real-docs"


def test_project_files_includes_mtime_for_every_file_type(client, seed_project) -> None:
    pdir = seed_project("recent-files")
    (pdir / "docs" / "note.md").write_text("# note\n")
    (pdir / "script.py").write_text("print('ok')\n")
    (pdir / "notebooks").mkdir()
    (pdir / "notebooks" / "analysis.ipynb").write_text("{}\n")

    r = client.get(f"/api/project-files?path={pdir}")
    assert r.status_code == 200
    files = {f["path"]: f for f in r.json()}

    for path in ("docs/note.md", "script.py", "notebooks/analysis.ipynb"):
        assert isinstance(files[path]["mtime"], float)


def test_sidebar_worktrees_lists_only_matching_repository_worktrees(client, monorepo) -> None:
    source = monorepo / "source-repo"
    project = source / "projects" / "alpha"
    project.mkdir(parents=True)
    (project / "README.md").write_text("alpha\n")
    subprocess.run(["git", "init"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Lab Test"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.email", "lab@example.test"], cwd=source, check=True)
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=source, check=True, capture_output=True)

    parent = monorepo / "sidebar-worktrees"
    parent.mkdir()
    (parent / "feature-a").mkdir()
    subprocess.run(
        [
            "git", "worktree", "add", "-b", "feature-a",
            str(parent / "feature-a" / "source-repo"),
        ],
        cwd=source,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "worktree", "add", "-b", "feature-direct", str(parent / "feature-direct")],
        cwd=source,
        check=True,
        capture_output=True,
    )

    unrelated = monorepo / "unrelated-repo"
    unrelated.mkdir()
    (unrelated / "README.md").write_text("unrelated\n")
    subprocess.run(["git", "init"], cwd=unrelated, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Lab Test"], cwd=unrelated, check=True)
    subprocess.run(["git", "config", "user.email", "lab@example.test"], cwd=unrelated, check=True)
    subprocess.run(["git", "add", "."], cwd=unrelated, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=unrelated, check=True, capture_output=True)
    (parent / "other-feature").mkdir()
    subprocess.run(
        [
            "git", "worktree", "add", "-b", "other-feature",
            str(parent / "other-feature" / "unrelated-repo"),
        ],
        cwd=unrelated,
        check=True,
        capture_output=True,
    )

    (parent / "ordinary-folder").mkdir()
    (parent / "README.md").write_text("not a worktree\n")
    wrapper = monorepo / "projects" / "wrapper"
    wrapper.mkdir()

    response = client.get(
        "/api/sidebar-worktrees",
        params={"path": str(parent), "repo": str(project), "scope": str(wrapper)},
    )

    assert response.status_code == 200
    assert response.json() == {
        "path": str(parent.resolve()),
        "repo": str(project.resolve()),
        "folders": [
            {
                "name": "feature-a",
                "path": str((parent / "feature-a").resolve()),
                "repo": str(
                    (parent / "feature-a" / "source-repo" / "projects" / "alpha").resolve()
                ),
            },
            {
                "name": "feature-direct",
                "path": str((parent / "feature-direct" / "projects" / "alpha").resolve()),
                "repo": str((parent / "feature-direct" / "projects" / "alpha").resolve()),
            },
        ],
    }


def test_sidebar_worktrees_prefers_git_scope_and_accepts_checkout_path(
    client, monorepo,
) -> None:
    source = monorepo / "projects" / "direct-repo"
    source.mkdir()
    (source / ".gitignore").write_text(".worktrees/\n")
    (source / "README.md").write_text("direct repo\n")
    subprocess.run(["git", "init"], cwd=source, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Lab Test"], cwd=source, check=True)
    subprocess.run(["git", "config", "user.email", "lab@example.test"], cwd=source, check=True)
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=source, check=True, capture_output=True)

    parent = source / ".worktrees"
    checkout = parent / "feature-a"
    subprocess.run(
        ["git", "worktree", "add", "-b", "feature-a", str(checkout)],
        cwd=source,
        check=True,
        capture_output=True,
    )

    response = client.get(
        "/api/sidebar-worktrees",
        params={
            # The UI should forgive pasting the checkout itself instead of
            # requiring users to manually trim it back to the parent folder.
            "path": str(checkout),
            # Project metadata can retain a checkout path after it was moved
            # or deleted. An exact Git project root must win over that stale
            # registered path.
            "repo": str(parent / "missing-checkout"),
            "scope": str(source),
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "path": str(parent.resolve()),
        "repo": str(source.resolve()),
        "folders": [
            {
                "name": "feature-a",
                "path": str(checkout.resolve()),
                "repo": str(checkout.resolve()),
            },
        ],
    }


def test_sidebar_worktrees_rejects_missing_folder(client, monorepo) -> None:
    response = client.get(
        "/api/sidebar-worktrees",
        params={
            "path": str(monorepo / "missing-worktrees"),
            "repo": str(monorepo),
        },
    )
    assert response.status_code == 404
    assert response.json()["detail"] == "Worktree folder not found"


def test_project_files_includes_deep_files_without_nested_git_marker(
    client, seed_project,
) -> None:
    """Real source paths must not depend on detecting nested Git metadata."""
    import os
    import time

    pdir = seed_project("nested-repository-files")
    nested_repo = pdir / "repositories" / "queries"
    tools = (
        nested_repo / "forge" / "experimental" / "cached-queries"
        / "cached_queries" / "tools"
    )
    tools.mkdir(parents=True)
    leaf = tools / "query_helper.py"
    leaf.write_text("VALUE = 1\n")
    future_ts = time.time() + 10_000
    os.utime(leaf, (future_ts, future_ts))
    rel = str(leaf.relative_to(pdir))

    listed = client.get(f"/api/project-files?path={pdir}")
    assert listed.status_code == 200
    assert rel in {row["path"] for row in listed.json()}

    mtime = client.get(f"/api/project-mtime?path={pdir}")
    assert mtime.status_code == 200
    assert mtime.json()["mtime"] >= future_ts


def test_project_entry_create_rename_and_delete(client, seed_project) -> None:
    pdir = seed_project("explorer")

    created = client.post("/api/project-entry", json={
        "path": str(pdir), "parent": "docs", "name": "draft.md", "kind": "file",
    })
    assert created.status_code == 200
    assert (pdir / "docs" / "draft.md").is_file()

    folder = client.post("/api/project-entry", json={
        "path": str(pdir), "parent": "docs", "name": "research", "kind": "folder",
    })
    assert folder.status_code == 200
    assert (pdir / "docs" / "research").is_dir()

    renamed = client.patch("/api/project-entry", json={
        "path": str(pdir), "entry": "docs/draft.md", "new_name": "notes.md",
    })
    assert renamed.status_code == 200
    assert renamed.json()["renamed_to"] == "docs/notes.md"
    assert not (pdir / "docs" / "draft.md").exists()
    assert (pdir / "docs" / "notes.md").is_file()

    deleted = client.request("DELETE", "/api/project-entry", json={
        "path": str(pdir), "entry": "docs/research",
    })
    assert deleted.status_code == 200
    assert not (pdir / "docs" / "research").exists()


def test_project_entry_creates_valid_repository_notebook(client, seed_project) -> None:
    pdir = seed_project("notebook-create")
    (pdir / "notebooks").mkdir()

    created = client.post("/api/project-entry", json={
        "path": str(pdir),
        "parent": "notebooks",
        "name": "analysis",
        "kind": "notebook",
    })

    assert created.status_code == 200, created.text
    assert created.json()["entry"] == "notebooks/analysis.ipynb"
    target = pdir / "notebooks" / "analysis.ipynb"
    notebook = json.loads(target.read_text(encoding="utf-8"))
    assert notebook["nbformat"] == 4
    assert notebook["nbformat_minor"] == 5
    assert notebook["cells"] == []
    assert notebook["metadata"]["kernelspec"]["name"] == "python3"


def test_project_entry_rejects_traversal_and_collisions(client, seed_project) -> None:
    pdir = seed_project("explorer-safe")
    (pdir / "docs" / "kept.md").write_text("safe")

    traversal = client.request("DELETE", "/api/project-entry", json={
        "path": str(pdir), "entry": "../project.json",
    })
    assert traversal.status_code == 400

    bad_name = client.patch("/api/project-entry", json={
        "path": str(pdir), "entry": "docs/kept.md", "new_name": "../gone.md",
    })
    assert bad_name.status_code == 400

    collision = client.post("/api/project-entry", json={
        "path": str(pdir), "parent": "docs", "name": "kept.md", "kind": "file",
    })
    assert collision.status_code == 409
    assert (pdir / "docs" / "kept.md").read_text() == "safe"


def test_project_diff_file_and_git_history(client, seed_project, monorepo) -> None:
    pdir = seed_project("explorer-git")
    source = pdir / "docs" / "note.txt"
    source.write_text("before\n")
    subprocess.run(["git", "init"], cwd=monorepo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Lab Test"], cwd=monorepo, check=True)
    subprocess.run(["git", "config", "user.email", "lab@example.test"], cwd=monorepo, check=True)
    subprocess.run(["git", "add", "."], cwd=monorepo, check=True)
    subprocess.run(["git", "commit", "-m", "add note"], cwd=monorepo, check=True, capture_output=True)
    source.write_text("after\n")
    companion = pdir / "docs" / "companion.txt"
    companion.write_text("same commit\n")
    subprocess.run([
        "git", "add", str(source.relative_to(monorepo)),
        str(companion.relative_to(monorepo)),
    ], cwd=monorepo, check=True)
    subprocess.run(["git", "commit", "-m", "update note"], cwd=monorepo, check=True, capture_output=True)

    history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "docs/note.txt",
    })
    assert history.status_code == 200
    commits = history.json()["commits"]
    assert [commit["message"] for commit in commits[:2]] == ["update note", "add note"]

    root_commit_diff = client.get("/api/commit-diff", params={
        "repo": str(monorepo), "sha": commits[1]["sha"],
    })
    assert root_commit_diff.status_code == 200
    assert any(
        item["filename"] == str(source.relative_to(monorepo))
        for item in root_commit_diff.json()["files"]
    )

    commit_diff = client.get("/api/project-entry/history-diff", params={
        "path": str(pdir), "file": "docs/note.txt", "sha": commits[0]["sha"],
    })
    assert commit_diff.status_code == 200
    commit_body = commit_diff.json()
    parsed = commit_body["files"][0]
    assert parsed["filename"] == str(source.relative_to(monorepo))
    assert str(companion.relative_to(monorepo)) in commit_body["changed_files"]
    assert parsed["additions"] == 1
    assert parsed["deletions"] == 1

    source.write_text("working tree\n")
    pending_companion = pdir / "docs" / "pending-companion.txt"
    pending_companion.write_text("also pending\n")
    working_history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "docs/note.txt",
    })
    assert working_history.status_code == 200
    working = working_history.json()["commits"][0]
    assert working["sha"] == "WORKTREE"
    assert working["message"] == "Uncommitted changes"
    assert working["states"] == ["unstaged"]

    working_diff = client.get("/api/project-entry/history-diff", params={
        "path": str(pdir), "file": "docs/note.txt", "sha": "WORKTREE",
    })
    assert working_diff.status_code == 200
    working_body = working_diff.json()
    working_parsed = working_body["files"][0]
    assert working_parsed["filename"] == str(source.relative_to(monorepo))
    assert str(pending_companion.relative_to(monorepo)) in working_body["changed_files"]
    assert working_parsed["additions"] == 1
    assert working_parsed["deletions"] == 1

    subprocess.run(
        ["git", "add", str(source.relative_to(monorepo))],
        cwd=monorepo, check=True,
    )
    staged_history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "docs/note.txt",
    })
    assert staged_history.json()["commits"][0]["states"] == ["staged"]

    source.write_text("working over staged\n")
    mixed_history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "docs/note.txt",
    })
    assert mixed_history.json()["commits"][0]["states"] == ["staged", "unstaged"]

    untracked = pdir / "docs" / "new.txt"
    untracked.write_text("brand new\n")
    untracked_history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "docs/new.txt",
    })
    assert untracked_history.status_code == 200
    assert untracked_history.json()["commits"][0]["states"] == ["untracked"]
    untracked_diff = client.get("/api/project-entry/history-diff", params={
        "path": str(pdir), "file": "docs/new.txt", "sha": "WORKTREE",
    })
    assert untracked_diff.status_code == 200
    assert untracked_diff.json()["files"][0]["additions"] == 1

    empty_untracked = pdir / "docs" / "empty.txt"
    empty_untracked.touch()
    empty_history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "docs/empty.txt",
    })
    assert empty_history.status_code == 200
    assert empty_history.json()["commits"][0]["states"] == ["untracked"]

    patch = pdir / "docs" / "change.diff"
    patch.write_text(subprocess.run(
        ["git", "show", "--format=", "--no-color", commits[0]["sha"]],
        cwd=monorepo, check=True, capture_output=True, text=True,
    ).stdout)
    rendered = client.get("/api/project-diff-file", params={
        "path": str(pdir), "file": "docs/change.diff",
    })
    assert rendered.status_code == 200
    rendered_note = next(
        item for item in rendered.json()["files"]
        if item["filename"].endswith("docs/note.txt")
    )
    assert rendered_note["additions"] == 1


def test_notebook_git_history_returns_side_by_side_cell_revisions(
    client, seed_project, monorepo,
) -> None:
    def notebook(source: str, output: str, execution_count: int) -> dict:
        return {
            "nbformat": 4,
            "nbformat_minor": 5,
            "metadata": {},
            "cells": [{
                "cell_type": "code",
                "metadata": {},
                "source": [source],
                "execution_count": execution_count,
                "outputs": [{"output_type": "stream", "name": "stdout", "text": [output]}],
            }],
        }

    pdir = seed_project("explorer-notebook-history")
    notebooks = pdir / "notebooks"
    notebooks.mkdir()
    path = notebooks / "review.ipynb"
    path.write_text(json.dumps(notebook("print('before')\n", "before\n", 1)))

    subprocess.run(["git", "init"], cwd=monorepo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Lab Test"], cwd=monorepo, check=True)
    subprocess.run(["git", "config", "user.email", "lab@example.test"], cwd=monorepo, check=True)
    subprocess.run(["git", "add", "."], cwd=monorepo, check=True)
    subprocess.run(["git", "commit", "-m", "add notebook"], cwd=monorepo, check=True, capture_output=True)

    path.write_text(json.dumps(notebook("print('after')\n", "after\n", 2)))
    subprocess.run(["git", "add", str(path.relative_to(monorepo))], cwd=monorepo, check=True)
    subprocess.run(["git", "commit", "-m", "update notebook"], cwd=monorepo, check=True, capture_output=True)

    history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "notebooks/review.ipynb",
    })
    latest = history.json()["commits"][0]
    committed = client.get("/api/project-entry/history-diff", params={
        "path": str(pdir),
        "file": "notebooks/review.ipynb",
        "sha": latest["sha"],
    })
    assert committed.status_code == 200
    notebook_diff = committed.json()["notebook"]
    assert notebook_diff["before_cells"] == 1
    assert notebook_diff["after_cells"] == 1
    assert notebook_diff["changed_cells"] == 1
    cell = notebook_diff["cells"][0]
    assert cell["status"] == "modified"
    assert cell["base_cell"]["source"] == "print('before')\n"
    assert cell["cell"]["source"] == "print('after')\n"

    # A working-tree-only output change is also a first-class review entry.
    path.write_text(json.dumps(notebook("print('after')\n", "working\n", 3)))
    working_history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "notebooks/review.ipynb",
    })
    assert working_history.json()["commits"][0]["sha"] == "WORKTREE"
    working = client.get("/api/project-entry/history-diff", params={
        "path": str(pdir),
        "file": "notebooks/review.ipynb",
        "sha": "WORKTREE",
    })
    assert working.status_code == 200
    working_body = working.json()
    assert working_body["kind"] == "working-tree"
    assert working_body["states"] == ["unstaged"]
    working_cell = working_body["notebook"]["cells"][0]
    assert working_cell["status"] == "output_changed"
    assert working_cell["base_cell"]["outputs"][0]["content"] == "after\n"
    assert working_cell["cell"]["outputs"][0]["content"] == "working\n"

    untracked_path = notebooks / "new-review.ipynb"
    untracked_path.write_text(json.dumps(notebook("print('new')\n", "new\n", 1)))
    untracked_history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "notebooks/new-review.ipynb",
    })
    assert untracked_history.json()["commits"][0]["states"] == ["untracked"]
    untracked = client.get("/api/project-entry/history-diff", params={
        "path": str(pdir),
        "file": "notebooks/new-review.ipynb",
        "sha": "WORKTREE",
    })
    assert untracked.status_code == 200
    untracked_notebook = untracked.json()["notebook"]
    assert untracked_notebook["before_cells"] == 0
    assert untracked_notebook["after_cells"] == 1
    assert untracked_notebook["cells"][0]["status"] == "added"


def test_project_git_history_uses_nearest_nested_repository(
    client, seed_project, monorepo,
) -> None:
    pdir = seed_project("explorer-nested-git")
    subprocess.run(["git", "init"], cwd=monorepo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Outer Test"], cwd=monorepo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "outer@example.test"],
        cwd=monorepo, check=True,
    )

    nested = pdir / "docs" / "nested-repo"
    nested.mkdir()
    source = nested / "inside.txt"
    source.write_text("nested before\n")
    subprocess.run(["git", "init"], cwd=nested, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Nested Test"], cwd=nested, check=True)
    subprocess.run(
        ["git", "config", "user.email", "nested@example.test"],
        cwd=nested, check=True,
    )
    subprocess.run(["git", "add", "inside.txt"], cwd=nested, check=True)
    subprocess.run(
        ["git", "commit", "-m", "nested initial"],
        cwd=nested, check=True, capture_output=True,
    )
    source.write_text("nested after\n")

    history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "docs/nested-repo/inside.txt",
    })
    assert history.status_code == 200
    body = history.json()
    assert Path(body["repo"]) == nested
    assert body["repo_file"] == "inside.txt"
    assert [item["message"] for item in body["commits"]] == [
        "Uncommitted changes", "nested initial",
    ]

    working_diff = client.get("/api/project-entry/history-diff", params={
        "path": str(pdir),
        "file": "docs/nested-repo/inside.txt",
        "sha": "WORKTREE",
    })
    assert working_diff.status_code == 200
    parsed = working_diff.json()["files"][0]
    assert parsed["filename"] == "inside.txt"
    assert parsed["additions"] == 1
    assert parsed["deletions"] == 1

    new_source = nested / "brand-new.txt"
    new_source.write_text("new in nested repo\n")
    new_history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "docs/nested-repo/brand-new.txt",
    })
    assert new_history.status_code == 200
    new_body = new_history.json()
    assert Path(new_body["repo"]) == nested
    assert new_body["commits"][0]["states"] == ["untracked"]

    new_diff = client.get("/api/project-entry/history-diff", params={
        "path": str(pdir),
        "file": "docs/nested-repo/brand-new.txt",
        "sha": "WORKTREE",
    })
    assert new_diff.status_code == 200
    assert new_diff.json()["files"][0]["status"] == "added"
    assert new_diff.json()["files"][0]["additions"] == 1


def test_project_git_history_supports_new_files_before_first_commit(
    client, seed_project,
) -> None:
    pdir = seed_project("explorer-unborn-git")
    nested = pdir / "repositories" / "fresh-repo"
    nested.mkdir(parents=True)
    subprocess.run(["git", "init"], cwd=nested, check=True, capture_output=True)
    source = nested / "new.txt"
    source.write_text("brand new\n")

    history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "repositories/fresh-repo/new.txt",
    })
    assert history.status_code == 200
    assert history.json()["commits"][0]["states"] == ["untracked"]

    diff = client.get("/api/project-entry/history-diff", params={
        "path": str(pdir),
        "file": "repositories/fresh-repo/new.txt",
        "sha": "WORKTREE",
    })
    assert diff.status_code == 200
    assert diff.json()["files"][0]["status"] == "added"
    assert diff.json()["files"][0]["additions"] == 1


def test_set_project_hold_with_duration(client, seed_project) -> None:
    pdir = seed_project("alpha")
    r = client.post("/api/projects/alpha/hold", json={
        "duration": "2d",
        "reason": "PR review",
        "url": "https://example.com/pr/1",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    hold = body["hold"]
    assert hold["reason"] == "PR review"
    assert hold["url"] == "https://example.com/pr/1"
    assert hold["until"]  # non-empty ISO timestamp
    # Persisted to disk
    stored = json.loads((pdir / "project.json").read_text())
    assert stored["hold"]["reason"] == "PR review"


def test_set_project_hold_with_until_date(client, seed_project) -> None:
    seed_project("alpha")
    r = client.post("/api/projects/alpha/hold", json={"until": "2099-01-15"})
    assert r.status_code == 200
    hold = r.json()["hold"]
    assert hold["until"].startswith("2099-01-15")


def test_set_project_hold_requires_one_of_duration_or_until(client, seed_project) -> None:
    seed_project("alpha")
    r = client.post("/api/projects/alpha/hold", json={"reason": "x"})
    assert r.status_code == 400


def test_set_project_hold_rejects_both_duration_and_until(client, seed_project) -> None:
    seed_project("alpha")
    r = client.post("/api/projects/alpha/hold", json={
        "duration": "2d", "until": "2099-01-15",
    })
    assert r.status_code == 400


def test_set_project_hold_rejects_bad_duration(client, seed_project) -> None:
    seed_project("alpha")
    r = client.post("/api/projects/alpha/hold", json={"duration": "2 weeks"})
    assert r.status_code == 400


def test_clear_project_hold(client, seed_project) -> None:
    pdir = seed_project("alpha")
    client.post("/api/projects/alpha/hold", json={"duration": "1d"})
    r = client.delete("/api/projects/alpha/hold")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    stored = json.loads((pdir / "project.json").read_text())
    assert stored["hold"] is None


def test_clear_project_hold_when_none(client, seed_project) -> None:
    seed_project("alpha")
    r = client.delete("/api/projects/alpha/hold")
    assert r.status_code == 200


def test_hold_missing_project(client) -> None:
    r = client.post("/api/projects/nope/hold", json={"duration": "1d"})
    assert r.status_code == 404


# ─── /api/project-mtime perf regression guard ──────────────────────────────
#
# Background: the 2s-interval poll from the client used to walk the entire
# monorepo (including .venv + repositories + .git) with rglob("*"), stalling
# the event loop for 20+ seconds per tick. The fix skips the same heavy
# subtrees /api/project-files already filters out and caps recursion depth.
# These tests plant those exact subtree shapes and assert the endpoint
# ignores them — protecting the performance contract, not just correctness.


def test_project_mtime_skips_venv_and_node_modules(monorepo, client, seed_project) -> None:
    """Plant a heavy .venv-like tree whose newest mtime is clearly AFTER
    any real project file. If project-mtime walks it, ``latest`` will
    pick up that timestamp. If the skip list works, it won't."""
    import os
    import time

    pdir = seed_project("heavy")
    # Real project file (older).
    doc = pdir / "docs" / "note.md"
    doc.write_text("hi")
    old_ts = time.time() - 10_000
    os.utime(doc, (old_ts, old_ts))

    # Plant a .venv with a much-newer file that MUST be skipped.
    venv = pdir / ".venv" / "lib" / "site-packages" / "foo"
    venv.mkdir(parents=True)
    tainted = venv / "tainted.py"
    tainted.write_text("x")
    future_ts = time.time() + 1_000_000
    os.utime(tainted, (future_ts, future_ts))

    # Also plant a node_modules with a tainted mtime.
    nm = pdir / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    tainted2 = nm / "tainted.js"
    tainted2.write_text("x")
    os.utime(tainted2, (future_ts, future_ts))

    r = client.get(f"/api/project-mtime?path={pdir}")
    assert r.status_code == 200
    mt = r.json()["mtime"]
    # If the skip list works, mt reflects ``pdir`` itself + its children
    # but never the tainted .venv / node_modules files.
    assert mt < future_ts, (
        f"project-mtime walked a skipped subtree (mt={mt}, future={future_ts}). "
        f"Confirm SKIP_DIRS in api_project_mtime includes .venv + node_modules."
    )


def test_project_mtime_fast_on_large_tree(seed_project, client) -> None:
    """Explicit p95 budget (p95<500ms). Plant a few hundred files inside
    allowed subdirs — the walk should still be comfortably sub-second.
    Pre-fix this test wouldn't exist because the endpoint was >20s on
    the real monorepo; this guard prevents silent regression to the old
    ``rglob("*")`` behavior."""
    import time

    pdir = seed_project("bulk")
    # 200 real-shape files across 20 docs/ subfolders.
    for i in range(20):
        sub = pdir / "docs" / f"sub-{i}"
        sub.mkdir(parents=True)
        for j in range(10):
            (sub / f"note-{j}.md").write_text("x")

    samples: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        r = client.get(f"/api/project-mtime?path={pdir}")
        samples.append(time.perf_counter() - t0)
        assert r.status_code == 200
    # After discarding the warmup sample, p95 must be < 500ms. Observed
    # on a dev laptop: ~20ms. This budget is ~25× headroom.
    hot = sorted(samples[1:])
    p95 = hot[-1] if hot else 0.0
    assert p95 < 0.5, (
        f"project-mtime p95 = {p95*1000:.1f}ms exceeds 500ms budget. "
        f"Samples (ms): {[f'{s*1000:.1f}' for s in samples]}. "
        f"Check for reintroduced rglob / missing SKIP_DIRS."
    )


def test_project_mtime_depth_capped(seed_project, client) -> None:
    """Walk depth is capped so a pathological deeply-nested tree can't
    hang the endpoint. Plant 30-level-deep dirs and confirm we return
    without hanging — the cap leaves room for real source trees but still
    excludes this 30-level pathological tail."""
    pdir = seed_project("deep")
    p = pdir
    for _ in range(30):
        p = p / "dir"
        p.mkdir()
    (p / "leaf.txt").write_text("x")

    r = client.get(f"/api/project-mtime?path={pdir}")
    assert r.status_code == 200
    assert "mtime" in r.json()
